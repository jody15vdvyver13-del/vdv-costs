import enum
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class CategoryCode(str, enum.Enum):
    COG_01 = "COG-01"
    COG_02 = "COG-02"
    COG_03 = "COG-03"
    COG_04 = "COG-04"
    COG_05 = "COG-05"
    COG_06 = "COG-06"
    COG_07 = "COG-07"
    COG_08 = "COG-08"


class JobStatus(str, enum.Enum):
    active = "active"
    completed = "completed"
    cancelled = "cancelled"


class CostEntryStatus(str, enum.Enum):
    pending = "pending"
    posted = "posted"
    exception = "exception"


class VendorStatus(str, enum.Enum):
    approved = "approved"
    suspended = "suspended"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("reference", name="uq_jobs_reference"),
        CheckConstraint(
            r"reference ~ '^VDV-JOB-\d{4}-\d{3}$'",
            name="ck_jobs_reference_format",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    reference: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[Optional[str]] = mapped_column(String(200))  # human-friendly internal name
    description: Mapped[Optional[str]] = mapped_column(String(500))
    contract_value: Mapped[Optional[float]] = mapped_column(Numeric(14, 2))
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, name="job_status", create_type=False), default=JobStatus.active, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    budgets: Mapped[List["Budget"]] = relationship(back_populates="job", cascade="all, delete-orphan")
    cost_entries: Mapped[List["CostEntry"]] = relationship(back_populates="job", cascade="all, delete-orphan")


class Budget(Base):
    __tablename__ = "budgets"
    __table_args__ = (
        UniqueConstraint("job_id", "category_code", name="uq_budgets_job_category"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    category_code: Mapped[CategoryCode] = mapped_column(
        Enum(CategoryCode, name="category_code", create_type=False), nullable=False
    )
    budgeted_amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)

    job: Mapped["Job"] = relationship(back_populates="budgets")


class ApprovedVendor(Base):
    __tablename__ = "approved_vendors"
    __table_args__ = (
        UniqueConstraint("name", name="uq_approved_vendors_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[VendorStatus] = mapped_column(
        Enum(VendorStatus, name="vendor_status", create_type=False),
        default=VendorStatus.approved,
        nullable=False,
    )


class CostEntry(Base):
    __tablename__ = "cost_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    supplier: Mapped[str] = mapped_column(String(200), nullable=False)
    date: Mapped[Optional[str]] = mapped_column(String(10))  # ISO 8601 YYYY-MM-DD
    amount_excl_vat: Mapped[Optional[float]] = mapped_column(Numeric(14, 2))
    amount_incl_vat: Mapped[Optional[float]] = mapped_column(Numeric(14, 2))
    category_code: Mapped[Optional[CategoryCode]] = mapped_column(
        Enum(CategoryCode, name="category_code", create_type=False), nullable=True
    )
    description: Mapped[Optional[str]] = mapped_column(String(500))
    slip_image_url: Mapped[Optional[str]] = mapped_column(String(1000))
    submitter_phone: Mapped[Optional[str]] = mapped_column(String(50))  # WhatsApp sender e.g. whatsapp:+27...
    status: Mapped[CostEntryStatus] = mapped_column(
        Enum(CostEntryStatus, name="cost_entry_status", create_type=False),
        default=CostEntryStatus.pending,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    job: Mapped["Job"] = relationship(back_populates="cost_entries")
    exceptions: Mapped[List["Exception_"]] = relationship(back_populates="cost_entry", cascade="all, delete-orphan")


class Exception_(Base):
    __tablename__ = "exceptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    cost_entry_id: Mapped[int] = mapped_column(
        ForeignKey("cost_entries.id", ondelete="CASCADE"), nullable=False
    )
    exception_type: Mapped[str] = mapped_column(String(100), nullable=False)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    resolved_by: Mapped[Optional[str]] = mapped_column(String(200))

    cost_entry: Mapped["CostEntry"] = relationship(back_populates="exceptions")
