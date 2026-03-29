"""
CFO exception alert system.

Sends WhatsApp alerts to the CFO when cost entries have exceptions,
and handles CFO approve/reject replies.
"""

import logging
import os
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db_models import CostEntry, CostEntryStatus, Exception_
from app.twilio_reply import send_whatsapp_reply

logger = logging.getLogger(__name__)

_EXCEPTION_LABELS: dict[str, str] = {
    "slip_unreadable": "Slip unreadable / low confidence",
    "invalid_job_reference": "Invalid job reference",
    "job_not_found": "Job not found",
    "high_value": "Exceeds R10k approval threshold",
    "unapproved_supplier": "Supplier not on approved list",
    "duplicate_slip": "Possible duplicate slip (24h window)",
    "three_way_match_required": "Three-way match required (PO + delivery note + invoice)",
}


def _cfo_number() -> str:
    return os.environ.get("CFO_WHATSAPP_NUMBER", "")


def build_cfo_alert_message(
    entry: CostEntry,
    job_reference: str,
    exception_types: list[str],
) -> str:
    """Build the ⚠️ alert message to send to the CFO."""
    amount = entry.amount_incl_vat or entry.amount_excl_vat
    amount_str = f"R{amount:,.0f}" if amount is not None else "R?"
    description = entry.description or entry.supplier
    reasons = " | ".join(
        _EXCEPTION_LABELS.get(e, e) for e in exception_types
    )
    return (
        f"\u26A0\uFE0F EXCEPTION #{entry.id}: {job_reference} | "
        f"{description} {amount_str} | {entry.supplier} | "
        f"{reasons}. "
        f"Reply APPROVE {entry.id} or REJECT {entry.id} <reason>."
    )


async def send_cfo_alert(
    entry: CostEntry,
    job_reference: str,
    exception_types: list[str],
) -> None:
    """Send the exception alert to the CFO via WhatsApp."""
    cfo_number = _cfo_number()
    if not cfo_number:
        logger.warning(
            "CFO_WHATSAPP_NUMBER not set — skipping CFO alert for entry #%d",
            entry.id,
        )
        return

    message = build_cfo_alert_message(entry, job_reference, exception_types)
    await send_whatsapp_reply(to=cfo_number, body=message)
    logger.info("CFO alert sent for cost entry #%d", entry.id)


async def handle_cfo_approval(
    db: AsyncSession,
    entry_id: int,
    approved: bool,
    reason: str,
    cfo_number: str,
) -> tuple[bool, str]:
    """
    Process a CFO approve/reject reply.

    Returns (success, submitter_phone_or_error_message).
    """
    entry: CostEntry | None = await db.get(CostEntry, entry_id)
    if entry is None:
        logger.warning("CFO replied for unknown entry #%d", entry_id)
        return False, f"Entry #{entry_id} not found."

    if entry.status != CostEntryStatus.exception:
        logger.info(
            "CFO replied for entry #%d but status is %s — ignoring",
            entry_id,
            entry.status,
        )
        return False, f"Entry #{entry_id} is already {entry.status.value}."

    now = datetime.now(timezone.utc)
    resolved_by = cfo_number

    if approved:
        # Flip to posted and mark all exceptions resolved
        entry.status = CostEntryStatus.posted
        exceptions = (
            await db.scalars(
                select(Exception_).where(Exception_.cost_entry_id == entry_id)
            )
        ).all()
        for exc in exceptions:
            exc.resolved_at = now
            exc.resolved_by = resolved_by
        await db.commit()
        logger.info("Entry #%d approved by CFO and posted", entry_id)
    else:
        # Leave status as exception; just log the rejection
        exceptions = (
            await db.scalars(
                select(Exception_).where(Exception_.cost_entry_id == entry_id)
            )
        ).all()
        for exc in exceptions:
            exc.resolved_at = now
            exc.resolved_by = f"REJECTED by {resolved_by}: {reason}"
        await db.commit()
        logger.info("Entry #%d rejected by CFO: %s", entry_id, reason)

    return True, entry.submitter_phone or ""
