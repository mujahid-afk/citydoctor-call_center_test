"""FastAPI entrypoint: `uvicorn app.main:app --reload --port 8000` (run from backend/).

FastAPI handles CRM data only. Voice/audio never passes through it: the browser
softphone talks SIP over WSS directly to FreePBX.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from .config import get_settings
from .database import SessionLocal, init_db
from .routers import bookings, brands, calls, client_logs, customers, queues, testing
from .seed import seed
from .services import call_service

settings = get_settings()
logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("voice_crm")


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    with SessionLocal() as db:
        call_service.close_stale_calls(db)
    if settings.auto_seed:
        with SessionLocal() as db:
            if seed(db):
                logger.info("Database was empty: demo data seeded.")
    logger.info("Voice CRM API ready (%s). Database: %s", settings.app_env, settings.database_url)
    yield


app = FastAPI(
    title="Voice CRM",
    version="0.2.0",
    description="CRM API for the browser WebRTC softphone (FreePBX + ElevenLabs stack).",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

for module in (calls, customers, bookings, brands, queues, testing, client_logs):
    app.include_router(module.router)


@app.get("/api/health", tags=["system"])
def health() -> dict:
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        database = "ok"
    except Exception as exc:  # noqa: BLE001
        logger.error("Database health check failed: %s", exc)
        database = "error"
    return {"status": "ok" if database == "ok" else "degraded", "database": database, "app_env": settings.app_env}
