import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import router as api_router
from app.dashboard import router as dashboard_router
from app.webhook import router as webhook_router
from app.weekly_report import run_weekly_report_scheduler
from app.worker import run_worker

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)

_STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    worker_task = asyncio.create_task(run_worker())
    report_task = asyncio.create_task(run_weekly_report_scheduler())
    yield
    for task in (worker_task, report_task):
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="VDV Slip Ingestion Service", lifespan=lifespan)
app.include_router(webhook_router)
app.include_router(api_router)
app.include_router(dashboard_router)

if _STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/dashboard-ui", include_in_schema=False)
async def dashboard_ui() -> FileResponse:
    return FileResponse(_STATIC_DIR / "dashboard.html")
