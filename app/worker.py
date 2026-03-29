import asyncio
import logging

from app.cfo_alerts import send_cfo_alert
from app.classifier import classify_slip
from app.database import AsyncSessionLocal
from app.ledger import post_to_ledger
from app.models import IncomingSlip
from app.ocr import download_image, extract_slip_data
from app.queue import slip_queue
from app.twilio_reply import (
    build_confirmation_message,
    build_error_message,
    send_whatsapp_reply,
)

logger = logging.getLogger(__name__)


async def process_slip(slip: IncomingSlip) -> None:
    logger.info(
        "Processing slip %s for job %s from %s",
        slip.message_sid,
        slip.job_reference,
        slip.sender,
    )

    # ── 1. Download and OCR ───────────────────────────────────────────────────
    image_bytes = await download_image(slip.media_url)
    extracted = await extract_slip_data(
        image_bytes,
        slip.media_content_type,
        job_reference=slip.job_reference,
    )
    logger.info(
        "Extraction complete for slip %s: readable=%s confidence=%.2f supplier=%r",
        slip.message_sid,
        extracted.readable,
        extracted.confidence,
        extracted.supplier,
    )

    # ── 2. Classify COG code ──────────────────────────────────────────────────
    category_code = classify_slip(extracted)
    logger.info("Classified slip %s as %s", slip.message_sid, category_code.value)

    # ── 3. Exception checks + ledger post ─────────────────────────────────────
    async with AsyncSessionLocal() as db:
        result = await post_to_ledger(db, slip, extracted, category_code)

    # ── 4. Send CFO alert if exceptions raised ────────────────────────────────
    if result is not None and result.exception_types:
        job_ref = extracted.job_reference or slip.job_reference
        await send_cfo_alert(result.cost_entry, job_ref, result.exception_types)

    # ── 5. Send WhatsApp confirmation ─────────────────────────────────────────
    if result is None:
        # Job not found or job reference invalid — no DB entry created
        reason = "invalid_job_reference" if not extracted.job_reference else "job_not_found"
        reply = build_error_message(extracted.job_reference or slip.job_reference, reason)
    else:
        reply = build_confirmation_message(
            result.cost_entry,
            extracted.job_reference or slip.job_reference,
            result.exception_types,
        )

    await send_whatsapp_reply(to=slip.sender, body=reply)


async def run_worker() -> None:
    """Consume slips from the queue indefinitely."""
    logger.info("OCR worker started")
    while True:
        slip: IncomingSlip = await slip_queue.get()
        try:
            await process_slip(slip)
        except Exception:
            logger.exception(
                "Failed to process slip %s — skipping",
                slip.message_sid,
            )
        finally:
            slip_queue.task_done()
