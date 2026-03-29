import logging
import os
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Form, HTTPException, Request, Response
from twilio.request_validator import RequestValidator

from app.cfo_alerts import handle_cfo_approval
from app.database import AsyncSessionLocal
from app.models import IncomingSlip
from app.queue import enqueue
from app.twilio_reply import build_rejection_notice, send_whatsapp_reply

logger = logging.getLogger(__name__)

router = APIRouter()

JOB_REF_RE = re.compile(r"\bVDV-JOB-\d{4}-\d{3}\b")
# Matches: APPROVE 42  or  REJECT 42  or  REJECT 42 wrong amount entered
CFO_REPLY_RE = re.compile(r"^(APPROVE|REJECT)\s+(\d+)(?:\s+(.+))?$", re.IGNORECASE)


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

    # ── CFO approval/rejection reply ──────────────────────────────────────────
    cfo_number = os.environ.get("CFO_WHATSAPP_NUMBER", "")
    sender_raw = From.replace("whatsapp:", "")
    cfo_raw = cfo_number.replace("whatsapp:", "")
    if cfo_raw and sender_raw == cfo_raw:
        match = CFO_REPLY_RE.match(Body.strip())
        if match:
            action = match.group(1).upper()
            entry_id = int(match.group(2))
            reason = (match.group(3) or "").strip()
            approved = action == "APPROVE"
            async with AsyncSessionLocal() as db:
                success, submitter_or_error = await handle_cfo_approval(
                    db, entry_id, approved, reason, From
                )
            if success and not approved and submitter_or_error:
                notice = build_rejection_notice(entry_id, f"#{entry_id}", reason)
                await send_whatsapp_reply(to=submitter_or_error, body=notice)
            ack = (
                f"\u2713 Entry #{entry_id} approved and posted."
                if (success and approved)
                else (
                    f"\u2713 Entry #{entry_id} rejection recorded."
                    if success
                    else submitter_or_error
                )
            )
            await send_whatsapp_reply(to=From, body=ack)
            return Response(content="<Response/>", media_type="application/xml")
        else:
            logger.info("CFO sent unrecognised message: %r — ignoring", Body)
            return Response(content="<Response/>", media_type="application/xml")

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
