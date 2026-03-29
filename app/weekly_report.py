"""
Weekly CFO report — runs every Friday, sends WhatsApp summary to management.

Checks once per hour whether it is Friday and whether the report has been sent
today. Uses a simple in-memory sentinel to avoid duplicate sends per process.
"""

import asyncio
import logging
import os
from datetime import date, datetime, timezone

from app.database import AsyncSessionLocal
from app.dashboard import _cost_by_job, _budget_by_job, _margin, _margin_alert
from app.db_models import CostEntry, CostEntryStatus, Job, JobStatus
from app.twilio_reply import send_whatsapp_reply

from sqlalchemy import func, select

logger = logging.getLogger(__name__)

_last_report_date: date | None = None  # per-process sentinel


async def generate_report_text(db) -> str:
    """Query the DB and format the weekly WhatsApp report message."""
    from sqlalchemy.ext.asyncio import AsyncSession

    jobs = (await db.scalars(
        select(Job).where(Job.status == JobStatus.active).order_by(Job.reference)
    )).all()

    if not jobs:
        return "\U0001F4CA Weekly Cost Report: No active jobs."

    cost_map = await _cost_by_job(db)
    budget_map = await _budget_by_job(db)

    alert_jobs = []
    lines = ["\U0001F4CA *Weekly Job Cost Report*\n"]

    for job in jobs:
        total_cost = cost_map.get(job.id, 0.0)
        budget_total = budget_map.get(job.id, 0.0)
        margin_pct = _margin(job.contract_value, total_cost)
        alert = _margin_alert(margin_pct)

        margin_str = f"{margin_pct:.1f}%" if margin_pct is not None else "N/A"
        budget_util = (
            f"{total_cost / budget_total * 100:.0f}% of budget"
            if budget_total > 0
            else "no budget set"
        )
        flag = " \u26A0\uFE0F" if alert else ""
        lines.append(
            f"• {job.reference}: R{total_cost:,.0f} spent | {budget_util} | margin {margin_str}{flag}"
        )
        if alert:
            alert_jobs.append(job.reference)

    if alert_jobs:
        lines.append(f"\n\u26A0\uFE0F Low margin alert: {', '.join(alert_jobs)}")

    # Count exceptions this week
    exception_count = await db.scalar(
        select(func.count(CostEntry.id)).where(
            CostEntry.status == CostEntryStatus.exception
        )
    )
    if exception_count:
        lines.append(f"\n\U0001F6A8 {exception_count} cost entr{'y' if exception_count == 1 else 'ies'} pending CFO review")

    today = datetime.now(timezone.utc).strftime("%d %b %Y")
    lines.append(f"\n_Generated {today}_")
    return "\n".join(lines)


async def send_weekly_report() -> None:
    recipients_raw = os.environ.get("MANAGEMENT_WHATSAPP_NUMBERS", "")
    if not recipients_raw:
        logger.warning("MANAGEMENT_WHATSAPP_NUMBERS not set — skipping weekly report")
        return

    recipients = [r.strip() for r in recipients_raw.split(",") if r.strip()]
    async with AsyncSessionLocal() as db:
        text = await generate_report_text(db)

    for number in recipients:
        await send_whatsapp_reply(to=number, body=text)
        logger.info("Weekly report sent to %s", number)


async def run_weekly_report_scheduler() -> None:
    """Background task: check once per hour, send on Fridays."""
    global _last_report_date
    logger.info("Weekly report scheduler started")
    while True:
        await asyncio.sleep(3600)  # check hourly
        now = datetime.now(timezone.utc)
        today = now.date()
        if now.weekday() == 4 and _last_report_date != today:  # 4 = Friday
            try:
                await send_weekly_report()
                _last_report_date = today
            except Exception:
                logger.exception("Weekly report failed")
