import base64
import logging
import os
from typing import Optional

import httpx
import anthropic

from app.models import ExtractedSlipData

logger = logging.getLogger(__name__)

EXTRACTION_TOOL = {
    "name": "extract_slip_data",
    "description": "Extract structured data from a supplier slip or invoice image.",
    "input_schema": {
        "type": "object",
        "properties": {
            "supplier": {
                "type": "string",
                "description": "Supplier or vendor name as printed on the slip.",
            },
            "date": {
                "type": "string",
                "description": "Date on the slip in ISO 8601 format (YYYY-MM-DD). Use null if not visible.",
            },
            "amount_excl_vat": {
                "type": "number",
                "description": "Total amount excluding VAT, as a decimal number. Use null if not visible.",
            },
            "amount_incl_vat": {
                "type": "number",
                "description": "Total amount including VAT, as a decimal number. Use null if not visible.",
            },
            "description": {
                "type": "string",
                "description": "Brief description of goods or services purchased. Use null if not visible.",
            },
            "job_reference": {
                "type": "string",
                "description": "Any job or order reference number visible on the slip (e.g. VDV-JOB-2026-001). Use null if none found.",
            },
            "readable": {
                "type": "boolean",
                "description": "True if the slip image was clear enough to extract meaningful data, false if the image is too blurry, dark, or otherwise unreadable.",
            },
            "confidence": {
                "type": "number",
                "description": "Confidence score between 0.0 and 1.0 for the overall extraction quality.",
            },
        },
        "required": ["supplier", "readable", "confidence"],
    },
}

SYSTEM_PROMPT = (
    "You are a specialist in reading South African supplier slips, tax invoices, "
    "and delivery notes. Extract all visible financial data accurately. "
    "South African VAT is 15%. Amounts are in ZAR (South African Rand). "
    "If a field is not visible or legible, omit it or set it to null."
)


async def download_image(media_url: str) -> bytes:
    """Download a Twilio media file using Basic auth."""
    account_sid = os.environ.get("TWILIO_ACCOUNT_SID", "")
    auth_token = os.environ.get("TWILIO_AUTH_TOKEN", "")
    auth = (account_sid, auth_token) if account_sid and auth_token else None

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(media_url, auth=auth, follow_redirects=True)
        response.raise_for_status()
        return response.content


def _extract_with_claude(image_bytes: bytes, media_content_type: str) -> dict:
    """Send image to Claude Vision and return extracted fields via tool use."""
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))

    encoded = base64.standard_b64encode(image_bytes).decode("utf-8")
    # Normalise content type to one Claude accepts
    safe_media_type = media_content_type.split(";")[0].strip()
    if safe_media_type not in ("image/jpeg", "image/png", "image/gif", "image/webp"):
        safe_media_type = "image/jpeg"

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        tools=[EXTRACTION_TOOL],
        tool_choice={"type": "auto"},
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": safe_media_type,
                            "data": encoded,
                        },
                    },
                    {
                        "type": "text",
                        "text": "Please extract all data from this supplier slip using the extract_slip_data tool.",
                    },
                ],
            }
        ],
    )

    for block in message.content:
        if block.type == "tool_use" and block.name == "extract_slip_data":
            return block.input  # type: ignore[return-value]

    # Fallback: Claude didn't use the tool — treat as unreadable
    logger.warning("Claude did not invoke extraction tool; marking slip as unreadable")
    return {"readable": False, "confidence": 0.0, "supplier": ""}


async def extract_slip_data(
    image_bytes: bytes,
    media_content_type: str,
    job_reference: Optional[str] = None,
) -> ExtractedSlipData:
    """Run Claude Vision extraction and return a typed result."""
    raw: dict = _extract_with_claude(image_bytes, media_content_type)
    logger.info("Raw extraction result: %s", raw)

    # job_reference from the WhatsApp caption takes precedence over anything in the image
    if job_reference:
        raw["job_reference"] = job_reference

    return ExtractedSlipData(**raw)
