from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class IncomingSlip(BaseModel):
    message_sid: str
    sender: str                          # WhatsApp number or "web:{team_name}"
    job_reference: str                   # Validated VDV-JOB-YYYY-NNN
    media_url: str                       # URL of the slip image (or empty for web uploads)
    media_content_type: str
    received_at: datetime
    image_bytes: Optional[bytes] = None  # Set for web uploads; skips HTTP download
    team_name: Optional[str] = None      # Team name from web form

    model_config = {"arbitrary_types_allowed": True}


class ExtractedSlipData(BaseModel):
    supplier: str
    date: Optional[str] = None                # ISO 8601 YYYY-MM-DD
    amount_excl_vat: Optional[float] = None
    amount_incl_vat: Optional[float] = None
    description: Optional[str] = None
    job_reference: Optional[str] = None
    readable: bool
    confidence: float
