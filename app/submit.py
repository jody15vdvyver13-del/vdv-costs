"""
Worker slip submission endpoint — web-based alternative to WhatsApp.

POST /submit/slip   multipart/form-data
  - job_id        int    (from active job dropdown)
  - team_name     str    (from team dropdown)
  - slip          file   (image of the slip)
"""
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.db_models import Job, JobStatus
from app.models import IncomingSlip
from app.queue import enqueue

logger = logging.getLogger(__name__)

router = APIRouter(tags=["submit"])

_STATIC_DIR = Path(__file__).parent / "static"

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB

# Configurable team list — override with TEAMS env var (comma-separated)
DEFAULT_TEAMS = ["Team A", "Team B", "Team C", "Management"]


def _get_teams() -> list[str]:
    raw = os.environ.get("TEAMS", "")
    if raw.strip():
        return [t.strip() for t in raw.split(",") if t.strip()]
    return DEFAULT_TEAMS


@router.get("/submit", include_in_schema=False)
async def submit_ui() -> FileResponse:
    return FileResponse(_STATIC_DIR / "submit.html")


@router.get("/submit/config")
async def submit_config(db: AsyncSession = Depends(get_db)):
    """Return active jobs and team list for the submit form dropdowns."""
    jobs = (await db.scalars(
        select(Job)
        .where(Job.status == JobStatus.active)
        .order_by(Job.name, Job.reference)
    )).all()
    return {
        "jobs": [
            {"id": j.id, "label": j.name or j.description or j.reference, "reference": j.reference}
            for j in jobs
        ],
        "teams": _get_teams(),
    }


@router.post("/submit/slip")
async def submit_slip(
    job_id: int = Form(...),
    team_name: str = Form(...),
    slip: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    # Validate job exists and is active
    job = await db.get(Job, job_id)
    if not job or job.status != JobStatus.active:
        raise HTTPException(status_code=404, detail="Job not found or inactive")

    # Validate content type
    content_type = (slip.content_type or "image/jpeg").split(";")[0].strip()
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported file type: {content_type}. Use JPEG, PNG, WebP, or GIF.",
        )

    # Read and size-check image
    image_bytes = await slip.read()
    if len(image_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 10 MB)")
    if not image_bytes:
        raise HTTPException(status_code=422, detail="Empty file uploaded")

    incoming = IncomingSlip(
        message_sid=f"web-{uuid.uuid4().hex}",
        sender=f"web:{team_name}",
        job_reference=job.reference,
        media_url="",  # unused for web uploads
        media_content_type=content_type,
        received_at=datetime.now(timezone.utc),
        image_bytes=image_bytes,
        team_name=team_name,
    )

    await enqueue(incoming)
    logger.info(
        "Web slip queued: job=%s team=%s size=%d bytes",
        job.reference,
        team_name,
        len(image_bytes),
    )

    return JSONResponse({"status": "queued", "job_reference": job.reference})
