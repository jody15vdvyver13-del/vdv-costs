"""
CFO dashboard API endpoints.

GET /dashboard/jobs            — all active jobs with cost, budget, margin
GET /dashboard/jobs/{job_id}   — drill-down with per-category breakdown
GET /dashboard/recent-entries  — last N posted/exception entries across all jobs
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.classifier import COG_LABELS
from app.database import get_db
from app.db_models import Budget, CategoryCode, CostEntry, CostEntryStatus, Job, JobStatus
from app.schemas import CategoryBreakdown, DashboardJob, JobSummary, RecentEntry

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

MARGIN_ALERT_THRESHOLD = 10.0  # percent — jobs below this are highlighted red
RECENT_ENTRIES_LIMIT = 50


def _margin(contract_value: Optional[float], total_cost: float) -> Optional[float]:
    if not contract_value:
        return None
    return (contract_value - total_cost) / contract_value * 100


def _margin_alert(margin_pct: Optional[float]) -> bool:
    return margin_pct is not None and margin_pct < MARGIN_ALERT_THRESHOLD


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _cost_by_job(db: AsyncSession) -> dict[int, float]:
    """Return {job_id: total_posted_cost} for all jobs."""
    rows = await db.execute(
        select(
            CostEntry.job_id,
            func.coalesce(
                func.sum(func.coalesce(CostEntry.amount_incl_vat, CostEntry.amount_excl_vat, 0.0)),
                0.0,
            ).label("total_cost"),
        )
        .where(CostEntry.status == CostEntryStatus.posted)
        .group_by(CostEntry.job_id)
    )
    return {row.job_id: float(row.total_cost) for row in rows}


async def _budget_by_job(db: AsyncSession) -> dict[int, float]:
    """Return {job_id: total_budgeted} for all jobs."""
    rows = await db.execute(
        select(
            Budget.job_id,
            func.coalesce(func.sum(Budget.budgeted_amount), 0.0).label("budget_total"),
        ).group_by(Budget.job_id)
    )
    return {row.job_id: float(row.budget_total) for row in rows}


async def _cost_by_category(db: AsyncSession, job_id: int) -> dict[str, float]:
    """Return {category_code: actual_cost} for a single job (posted entries only)."""
    rows = await db.execute(
        select(
            CostEntry.category_code,
            func.coalesce(
                func.sum(func.coalesce(CostEntry.amount_incl_vat, CostEntry.amount_excl_vat, 0.0)),
                0.0,
            ).label("actual"),
        )
        .where(CostEntry.job_id == job_id, CostEntry.status == CostEntryStatus.posted)
        .group_by(CostEntry.category_code)
    )
    return {str(row.category_code): float(row.actual) for row in rows if row.category_code}


async def _budgets_for_job(db: AsyncSession, job_id: int) -> dict[str, float]:
    """Return {category_code: budgeted_amount} for a single job."""
    rows = await db.scalars(select(Budget).where(Budget.job_id == job_id))
    return {b.category_code.value: float(b.budgeted_amount) for b in rows.all()}


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/jobs", response_model=list[JobSummary])
async def list_dashboard_jobs(db: AsyncSession = Depends(get_db)):
    """All active jobs with cost vs. budget summary and gross margin."""
    jobs = (await db.scalars(
        select(Job).where(Job.status == JobStatus.active).order_by(Job.reference)
    )).all()

    cost_map = await _cost_by_job(db)
    budget_map = await _budget_by_job(db)

    result = []
    for job in jobs:
        total_cost = cost_map.get(job.id, 0.0)
        budget_total = budget_map.get(job.id, 0.0)
        margin_pct = _margin(job.contract_value, total_cost)
        result.append(
            JobSummary(
                id=job.id,
                reference=job.reference,
                description=job.description,
                contract_value=job.contract_value,
                total_cost=total_cost,
                budget_total=budget_total,
                margin_pct=margin_pct,
                margin_alert=_margin_alert(margin_pct),
            )
        )
    return result


@router.get("/jobs/{job_id}", response_model=DashboardJob)
async def get_dashboard_job(job_id: int, db: AsyncSession = Depends(get_db)):
    """Job drill-down: per-category cost vs. budget breakdown + recent entries."""
    job = await db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    cost_map = await _cost_by_job(db)
    budget_map = await _budget_by_job(db)
    cat_cost = await _cost_by_category(db, job_id)
    cat_budget = await _budgets_for_job(db, job_id)

    # Build category breakdown for all 8 COG codes
    categories = []
    for code in CategoryCode:
        budgeted = cat_budget.get(code.value, 0.0)
        actual = cat_cost.get(code.value, 0.0)
        utilisation_pct = (actual / budgeted * 100) if budgeted > 0 else None
        categories.append(
            CategoryBreakdown(
                category_code=code.value,
                label=COG_LABELS.get(code, code.value),
                budgeted=budgeted,
                actual=actual,
                utilisation_pct=utilisation_pct,
            )
        )

    # Recent entries for this job
    raw_entries = (await db.scalars(
        select(CostEntry)
        .where(CostEntry.job_id == job_id)
        .order_by(CostEntry.created_at.desc())
        .limit(20)
    )).all()
    recent = [
        RecentEntry(
            id=e.id,
            job_reference=job.reference,
            supplier=e.supplier,
            amount=e.amount_incl_vat or e.amount_excl_vat,
            category_code=e.category_code.value if e.category_code else None,
            status=e.status,
            slip_image_url=e.slip_image_url,
            created_at=e.created_at,
        )
        for e in raw_entries
    ]

    total_cost = cost_map.get(job.id, 0.0)
    budget_total = budget_map.get(job.id, 0.0)
    margin_pct = _margin(job.contract_value, total_cost)

    return DashboardJob(
        id=job.id,
        reference=job.reference,
        description=job.description,
        contract_value=job.contract_value,
        total_cost=total_cost,
        budget_total=budget_total,
        margin_pct=margin_pct,
        margin_alert=_margin_alert(margin_pct),
        categories=categories,
        recent_entries=recent,
    )


@router.get("/recent-entries", response_model=list[RecentEntry])
async def recent_entries(limit: int = 50, db: AsyncSession = Depends(get_db)):
    """Latest cost entries across all jobs (for the feed)."""
    limit = min(limit, RECENT_ENTRIES_LIMIT)
    rows = (await db.execute(
        select(CostEntry, Job.reference.label("job_reference"))
        .join(Job, CostEntry.job_id == Job.id)
        .order_by(CostEntry.created_at.desc())
        .limit(limit)
    )).all()

    return [
        RecentEntry(
            id=row.CostEntry.id,
            job_reference=row.job_reference,
            supplier=row.CostEntry.supplier,
            amount=row.CostEntry.amount_incl_vat or row.CostEntry.amount_excl_vat,
            category_code=row.CostEntry.category_code.value if row.CostEntry.category_code else None,
            status=row.CostEntry.status,
            slip_image_url=row.CostEntry.slip_image_url,
            created_at=row.CostEntry.created_at,
        )
        for row in rows
    ]
