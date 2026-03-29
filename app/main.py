import logging

from dotenv import load_dotenv
from fastapi import FastAPI

from app.webhook import router as webhook_router

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)

app = FastAPI(title="VDV Slip Ingestion Service")
app.include_router(webhook_router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
