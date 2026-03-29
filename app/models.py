from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class IncomingSlip(BaseModel):
    message_sid: str
    sender: str          # WhatsApp number e.g. whatsapp:+27821234567
    job_reference: str   # Validated VDV-JOB-YYYY-NNN
    media_url: str       # URL of the slip image
    media_content_type: str
    received_at: datetime


class ExtractedSlipData(BaseModel):
    supplier: str
    date: Optional[str] = None                # ISO 8601 YYYY-MM-DD
    amount_excl_vat: Optional[float] = None
    amount_incl_vat: Optional[float] = None
    description: Optional[str] = None
    job_reference: Optional[str] = None
    readable: bool
    confidence: float
