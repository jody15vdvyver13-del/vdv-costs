from datetime import datetime
from pydantic import BaseModel


class IncomingSlip(BaseModel):
    message_sid: str
    sender: str          # WhatsApp number e.g. whatsapp:+27821234567
    job_reference: str   # Validated VDV-JOB-YYYY-NNN
    media_url: str       # URL of the slip image
    media_content_type: str
    received_at: datetime
