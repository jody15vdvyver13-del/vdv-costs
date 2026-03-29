import logging
import os
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Form, HTTPException, Request, Response
from twilio.request_validator import RequestValidator

from app.models import IncomingSlip
from app.queue import enqueue

logger = logging.getLogger(__name__)

router = APIRouter()

JOB_REF_RE = re.compile(r"\bVDV-JOB-\d{4}-\d{3}\b")


def _validate_twilio_signature(request: Request, form_body: dict) -> None:
    auth_token = os.environ.get("TWILIO_AUTH_TOKEN", "")
    if not auth_token:
        logger.warning("TWILIO_AUTH_TOKEN not set — skipping signature validation")
        return
    validator = RequestValidator(auth_token)
    signature = request.headers.get("X-Twilio-Signature", "")
    url = str(request.url)
    if not validator.validate(url, form_body, signature):
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")


@router.post("/webhook/whatsapp")
async def whatsapp_webhook(
    request: Request,
    MessageSid: str = Form(...),
    From: str = Form(...),
    To: str = Form(...),
    Body: str = Form(""),
    NumMedia: int = Form(0),
    MediaUrl0: str = Form(None),
    MediaContentType0: str = Form(None),
) -> Response:
    # Build the raw form dict for signature validation
    form_data = await request.form()
    form_dict = dict(form_data)
    _validate_twilio_signature(request, form_dict)

    # Check allowed senders (optional config)
    allowed_raw = os.environ.get("ALLOWED_SENDERS", "")
    if allowed_raw:
        allowed = {s.strip() for s in allowed_raw.split(",")}
        sender_number = From.replace("whatsapp:", "")
        if sender_number not in allowed:
            logger.warning("Rejected message from unlisted sender %s", From)
            return Response(content="<Response/>", media_type="application/xml")

    # Validate: must have at least one media attachment
    if NumMedia < 1 or not MediaUrl0:
        logger.warning(
            "Rejected message %s from %s — no media attached (NumMedia=%d)",
            MessageSid,
            From,
            NumMedia,
        )
        return Response(content="<Response/>", media_type="application/xml")

    # Validate: caption must contain a job reference
    match = JOB_REF_RE.search(Body)
    if not match:
        logger.warning(
            "Rejected message %s from %s — no valid job reference in caption: %r",
            MessageSid,
            From,
            Body,
        )
        return Response(content="<Response/>", media_type="application/xml")

    slip = IncomingSlip(
        message_sid=MessageSid,
        sender=From,
        job_reference=match.group(),
        media_url=MediaUrl0,
        media_content_type=MediaContentType0 or "image/jpeg",
        received_at=datetime.now(timezone.utc),
    )

    await enqueue(slip)

    # Return empty TwiML immediately — processing happens asynchronously
    return Response(content="<Response/>", media_type="application/xml")
