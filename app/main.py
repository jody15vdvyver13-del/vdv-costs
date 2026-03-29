import asyncio
import logging
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI

from app.webhook import router as webhook_router
from app.worker import run_worker

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    worker_task = asyncio.create_task(run_worker())
    yield
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="VDV Slip Ingestion Service", lifespan=lifespan)
app.include_router(webhook_router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
