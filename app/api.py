from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.db_models import ApprovedVendor, Budget, CostEntry, Job
from app.schemas import (
    BudgetCreate,
    BudgetRead,
    CostEntryCreate,
    CostEntryRead,
    CostEntryUpdate,
    JobCreate,
    JobRead,
    JobUpdate,
    VendorCreate,
    VendorRead,
)

router = APIRouter(prefix="/api", tags=["job-costing"])


# ── Jobs ─────────────────────────────────────────────────────────────────────

@router.post("/jobs", response_model=JobRead, status_code=201)
async def register_job(payload: JobCreate, db: AsyncSession = Depends(get_db)):
    existing = await db.scalar(select(Job).where(Job.reference == payload.reference))
    if existing:
        raise HTTPException(status_code=409, detail=f"Job {payload.reference} already exists")
    job = Job(**payload.model_dump())
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return job


@router.get("/jobs", response_model=List[JobRead])
async def list_jobs(db: AsyncSession = Depends(get_db)):
    result = await db.scalars(select(Job).order_by(Job.created_at.desc()))
    return result.all()


@router.get("/jobs/{job_id}", response_model=JobRead)
async def get_job(job_id: int, db: AsyncSession = Depends(get_db)):
    job = await db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.patch("/jobs/{job_id}", response_model=JobRead)
async def update_job(job_id: int, payload: JobUpdate, db: AsyncSession = Depends(get_db)):
    job = await db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(job, field, value)
    await db.commit()
    await db.refresh(job)
    return job


# ── Budgets ───────────────────────────────────────────────────────────────────

@router.post("/jobs/{job_id}/budgets", response_model=BudgetRead, status_code=201)
async def create_budget(
    job_id: int, payload: BudgetCreate, db: AsyncSession = Depends(get_db)
):
    job = await db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    existing = await db.scalar(
        select(Budget).where(
            Budget.job_id == job_id, Budget.category_code == payload.category_code
        )
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Budget for {payload.category_code} already exists on this job",
        )
    budget = Budget(job_id=job_id, **payload.model_dump())
    db.add(budget)
    await db.commit()
    await db.refresh(budget)
    return budget


@router.get("/jobs/{job_id}/budgets", response_model=List[BudgetRead])
async def list_budgets(job_id: int, db: AsyncSession = Depends(get_db)):
    job = await db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    result = await db.scalars(select(Budget).where(Budget.job_id == job_id))
    return result.all()


# ── Cost Entries ──────────────────────────────────────────────────────────────

@router.post("/jobs/{job_id}/cost-entries", response_model=CostEntryRead, status_code=201)
async def create_cost_entry(
    job_id: int, payload: CostEntryCreate, db: AsyncSession = Depends(get_db)
):
    job = await db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    entry = CostEntry(job_id=job_id, **payload.model_dump())
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return entry


@router.get("/jobs/{job_id}/cost-entries", response_model=List[CostEntryRead])
async def list_cost_entries(job_id: int, db: AsyncSession = Depends(get_db)):
    job = await db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    result = await db.scalars(
        select(CostEntry)
        .where(CostEntry.job_id == job_id)
        .order_by(CostEntry.created_at.desc())
    )
    return result.all()


@router.get("/cost-entries/{entry_id}", response_model=CostEntryRead)
async def get_cost_entry(entry_id: int, db: AsyncSession = Depends(get_db)):
    entry = await db.get(CostEntry, entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Cost entry not found")
    return entry


@router.patch("/cost-entries/{entry_id}", response_model=CostEntryRead)
async def update_cost_entry(
    entry_id: int, payload: CostEntryUpdate, db: AsyncSession = Depends(get_db)
):
    entry = await db.get(CostEntry, entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Cost entry not found")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(entry, field, value)
    await db.commit()
    await db.refresh(entry)
    return entry


# ── Approved Vendors ──────────────────────────────────────────────────────────

@router.post("/vendors", response_model=VendorRead, status_code=201)
async def create_vendor(payload: VendorCreate, db: AsyncSession = Depends(get_db)):
    existing = await db.scalar(
        select(ApprovedVendor).where(ApprovedVendor.name == payload.name)
    )
    if existing:
        raise HTTPException(status_code=409, detail="Vendor already exists")
    vendor = ApprovedVendor(**payload.model_dump())
    db.add(vendor)
    await db.commit()
    await db.refresh(vendor)
    return vendor


@router.get("/vendors", response_model=List[VendorRead])
async def list_vendors(db: AsyncSession = Depends(get_db)):
    result = await db.scalars(select(ApprovedVendor).order_by(ApprovedVendor.name))
    return result.all()
