import asyncio
import logging
from app.models import IncomingSlip

logger = logging.getLogger(__name__)

# In-process queue — VDV-18 OCR worker will consume from this.
# Replace with Celery/Redis when scaling beyond a single process.
slip_queue: asyncio.Queue[IncomingSlip] = asyncio.Queue()


async def enqueue(slip: IncomingSlip) -> None:
    await slip_queue.put(slip)
    logger.info(
        "Queued slip %s from %s for job %s (queue size: %d)",
        slip.message_sid,
        slip.sender,
        slip.job_reference,
        slip_queue.qsize(),
    )
