import asyncio
import logging

from app.models import IncomingSlip
from app.ocr import download_image, extract_slip_data
from app.queue import slip_queue

logger = logging.getLogger(__name__)


async def process_slip(slip: IncomingSlip) -> None:
    logger.info(
        "Processing slip %s for job %s from %s",
        slip.message_sid,
        slip.job_reference,
        slip.sender,
    )
    image_bytes = await download_image(slip.media_url)
    result = await extract_slip_data(
        image_bytes,
        slip.media_content_type,
        job_reference=slip.job_reference,
    )
    logger.info(
        "Extraction complete for slip %s: readable=%s confidence=%.2f supplier=%r",
        slip.message_sid,
        result.readable,
        result.confidence,
        result.supplier,
    )


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
