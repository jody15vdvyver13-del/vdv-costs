"""
Exception checking and ledger posting.

Pipeline:
  ExtractedSlipData + CategoryCode + IncomingSlip
    -> check all exceptions
    -> write CostEntry (posted or exception)
    -> write Exception_ records
    -> return (CostEntry, list[str]) — entry + exception type strings
"""

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db_models import ApprovedVendor, CategoryCode, CostEntry, CostEntryStatus, Exception_, Job
from app.models import ExtractedSlipData, IncomingSlip

logger = logging.getLogger(__name__)

CONFIDENCE_THRESHOLD = 0.7
HIGH_VALUE_THRESHOLD = 10_000.0
THREE_WAY_MATCH_THRESHOLD = 5_000.0
JOB_REF_RE = re.compile(r"^VDV-JOB-\d{4}-\d{3}$")
DUPLICATE_WINDOW_HOURS = 24


@dataclass
class LedgerResult:
    cost_entry: CostEntry
    exception_types: list[str]  # empty if posted cleanly


async def post_to_ledger(
    db: AsyncSession,
    slip: IncomingSlip,
    extracted: ExtractedSlipData,
    category_code: CategoryCode,
) -> Optional[LedgerResult]:
    """
    Run all exception checks and write to the DB.
    Returns None if the job reference cannot be resolved (no cost entry created).
    """
    exceptions: list[str] = []

    # ── 1. Slip unreadable ────────────────────────────────────────────────────
    if not extracted.readable or extracted.confidence < CONFIDENCE_THRESHOLD:
        exceptions.append("slip_unreadable")

    # ── 2. Job reference missing / invalid format ─────────────────────────────
    job_ref = extracted.job_reference or ""
    if not job_ref or not JOB_REF_RE.match(job_ref):
        exceptions.append("invalid_job_reference")
        # Cannot create a cost entry without a valid FK — bail early
        logger.warning("Job reference %r is missing or invalid — skipping DB insert", job_ref)
        return None

    # ── 3. Job must exist in DB ───────────────────────────────────────────────
    job: Optional[Job] = await db.scalar(select(Job).where(Job.reference == job_ref))
    if job is None:
        exceptions.append("job_not_found")
        logger.warning("Job %r not found in DB — skipping DB insert", job_ref)
        return None

    # ── 4. Amount checks ──────────────────────────────────────────────────────
    amount = extracted.amount_incl_vat or extracted.amount_excl_vat
    if amount is not None and amount > HIGH_VALUE_THRESHOLD:
        exceptions.append("high_value")
    if amount is not None and amount > THREE_WAY_MATCH_THRESHOLD:
        exceptions.append("three_way_match_required")

    # ── 5. Supplier not on approved vendor list ───────────────────────────────
    supplier_name = extracted.supplier or ""
    approved: Optional[ApprovedVendor] = await db.scalar(
        select(ApprovedVendor).where(
            func.lower(ApprovedVendor.name) == func.lower(supplier_name),
            ApprovedVendor.status == "approved",
        )
    )
    if approved is None:
        exceptions.append("unapproved_supplier")

    # ── 6. Duplicate slip detection ───────────────────────────────────────────
    if supplier_name and amount is not None and extracted.date:
        window_start = datetime.now(timezone.utc) - timedelta(hours=DUPLICATE_WINDOW_HOURS)
        duplicate = await db.scalar(
            select(CostEntry).where(
                CostEntry.job_id == job.id,
                func.lower(CostEntry.supplier) == func.lower(supplier_name),
                CostEntry.amount_incl_vat == amount,
                CostEntry.date == extracted.date,
                CostEntry.created_at >= window_start,
            )
        )
        if duplicate is not None:
            exceptions.append("duplicate_slip")

    # ── Write CostEntry ───────────────────────────────────────────────────────
    entry_status = CostEntryStatus.exception if exceptions else CostEntryStatus.posted
    entry = CostEntry(
        job_id=job.id,
        supplier=supplier_name,
        date=extracted.date,
        amount_excl_vat=extracted.amount_excl_vat,
        amount_incl_vat=extracted.amount_incl_vat,
        category_code=category_code,
        description=extracted.description,
        slip_image_url=slip.media_url,
        submitter_phone=slip.sender,
        status=entry_status,
    )
    db.add(entry)
    await db.flush()  # get entry.id before creating child records

    # ── Write Exception_ records ──────────────────────────────────────────────
    for exc_type in exceptions:
        db.add(Exception_(cost_entry_id=entry.id, exception_type=exc_type))

    await db.commit()
    await db.refresh(entry)

    logger.info(
        "Ledger post complete: entry_id=%d status=%s exceptions=%s",
        entry.id,
        entry_status.value,
        exceptions,
    )
    return LedgerResult(cost_entry=entry, exception_types=exceptions)
