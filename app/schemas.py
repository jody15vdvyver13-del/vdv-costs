from datetime import datetime
from typing import Optional

from pydantic import BaseModel, field_validator

from app.db_models import CategoryCode, CostEntryStatus, JobStatus, VendorStatus


# ── Jobs ────────────────────────────────────────────────────────────────────

class JobCreate(BaseModel):
    reference: str
    description: Optional[str] = None
    contract_value: Optional[float] = None
    status: JobStatus = JobStatus.active

    @field_validator("reference")
    @classmethod
    def validate_reference_format(cls, v: str) -> str:
        import re
        if not re.fullmatch(r"VDV-JOB-\d{4}-\d{3}", v):
            raise ValueError("reference must match VDV-JOB-YYYY-NNN")
        return v


class JobUpdate(BaseModel):
    description: Optional[str] = None
    contract_value: Optional[float] = None
    status: Optional[JobStatus] = None


class JobRead(BaseModel):
    id: int
    reference: str
    description: Optional[str]
    contract_value: Optional[float]
    status: JobStatus
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Budgets ─────────────────────────────────────────────────────────────────

class BudgetCreate(BaseModel):
    category_code: CategoryCode
    budgeted_amount: float


class BudgetRead(BaseModel):
    id: int
    job_id: int
    category_code: CategoryCode
    budgeted_amount: float

    model_config = {"from_attributes": True}


# ── Cost Entries ─────────────────────────────────────────────────────────────

class CostEntryCreate(BaseModel):
    supplier: str
    date: Optional[str] = None
    amount_excl_vat: Optional[float] = None
    amount_incl_vat: Optional[float] = None
    category_code: Optional[CategoryCode] = None
    description: Optional[str] = None
    slip_image_url: Optional[str] = None
    status: CostEntryStatus = CostEntryStatus.pending

    @field_validator("date")
    @classmethod
    def validate_date_format(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        import re
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
            raise ValueError("date must be ISO 8601 format YYYY-MM-DD")
        return v


class CostEntryUpdate(BaseModel):
    supplier: Optional[str] = None
    date: Optional[str] = None
    amount_excl_vat: Optional[float] = None
    amount_incl_vat: Optional[float] = None
    category_code: Optional[CategoryCode] = None
    description: Optional[str] = None
    slip_image_url: Optional[str] = None
    status: Optional[CostEntryStatus] = None


class CostEntryRead(BaseModel):
    id: int
    job_id: int
    supplier: str
    date: Optional[str]
    amount_excl_vat: Optional[float]
    amount_incl_vat: Optional[float]
    category_code: Optional[CategoryCode]
    description: Optional[str]
    slip_image_url: Optional[str]
    status: CostEntryStatus
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Approved Vendors ─────────────────────────────────────────────────────────

class VendorCreate(BaseModel):
    name: str
    status: VendorStatus = VendorStatus.approved


class VendorRead(BaseModel):
    id: int
    name: str
    status: VendorStatus

    model_config = {"from_attributes": True}
