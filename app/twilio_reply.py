"""Send WhatsApp reply messages via Twilio REST API using httpx."""

import logging
import os
from typing import Optional

import httpx

from app.classifier import COG_LABELS
from app.db_models import CategoryCode, CostEntry, CostEntryStatus

logger = logging.getLogger(__name__)

# Human-readable descriptions for each exception type
_EXCEPTION_MESSAGES: dict[str, str] = {
    "slip_unreadable": "slip image was unreadable or low confidence",
    "invalid_job_reference": "job reference is missing or invalid",
    "job_not_found": "job reference not found in the system",
    "high_value": "amount exceeds R10,000 approval threshold",
    "unapproved_supplier": "supplier is not on the approved vendor list",
    "duplicate_slip": "possible duplicate slip detected within 24 hours",
    "three_way_match_required": "three-way match required (PO + delivery note + invoice)",
}


async def send_whatsapp_reply(
    to: str,
    body: str,
    from_number: Optional[str] = None,
) -> None:
    """POST a WhatsApp message via the Twilio Messages API."""
    account_sid = os.environ.get("TWILIO_ACCOUNT_SID", "")
    auth_token = os.environ.get("TWILIO_AUTH_TOKEN", "")
    whatsapp_from = from_number or os.environ.get("TWILIO_WHATSAPP_FROM", "")

    if not account_sid or not auth_token or not whatsapp_from:
        logger.warning(
            "Twilio credentials or TWILIO_WHATSAPP_FROM not set — skipping reply to %s", to
        )
        return

    url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
    payload = {"To": to, "From": whatsapp_from, "Body": body}

    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(url, data=payload, auth=(account_sid, auth_token))

    if response.status_code not in (200, 201):
        logger.error(
            "Twilio reply failed: status=%d body=%s",
            response.status_code,
            response.text[:200],
        )
    else:
        logger.info("WhatsApp reply sent to %s", to)


def build_confirmation_message(
    entry: CostEntry,
    job_reference: str,
    exception_types: list[str],
) -> str:
    """Build the confirmation or exception message to send back to the submitter."""
    amount = entry.amount_incl_vat or entry.amount_excl_vat
    amount_str = f"R{amount:,.0f}" if amount is not None else "R?"
    description = entry.description or entry.supplier
    cog_label = COG_LABELS.get(CategoryCode(entry.category_code), "Other") if entry.category_code else "Uncategorised"
    cog_code = entry.category_code.value if entry.category_code else "COG-?"

    if entry.status == CostEntryStatus.posted:
        return (
            f"\u2713 {job_reference}: {description} {amount_str} "
            f"captured under {cog_label} ({cog_code})"
        )

    # Exception path
    reasons = "; ".join(
        _EXCEPTION_MESSAGES.get(e, e) for e in exception_types
    )
    return (
        f"\u26A0 {job_reference}: {description} {amount_str} "
        f"flagged for review — {reasons}"
    )


def build_error_message(job_reference: str, reason: str) -> str:
    """Build a message for cases where no cost entry could be created."""
    friendly = _EXCEPTION_MESSAGES.get(reason, reason)
    return f"\u274C {job_reference or 'Unknown job'}: slip rejected — {friendly}"


def build_rejection_notice(entry_id: int, job_reference: str, reason: str) -> str:
    """Build the rejection notification sent back to the original slip submitter."""
    return (
        f"\u274C Entry #{entry_id} for {job_reference} was rejected by the CFO"
        + (f": {reason}" if reason else "")
        + ". Please resubmit with corrections."
    )
