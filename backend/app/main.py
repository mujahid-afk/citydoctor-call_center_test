"""FastAPI entrypoint: `uvicorn app.main:app --reload --port 8000` (run from backend/)."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from .config import get_settings
from .database import SessionLocal, init_db
from .routers import bookings, calls, customers, testing, tools, webhooks
from .seed import seed
from .services import mock_simulator

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("voice_crm")

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    mock_simulator.ensure_demo_recording()
    with SessionLocal() as db:
        if settings.auto_seed and seed(db):
            logger.info("Database was empty: demo data seeded.")
        recovered = mock_simulator.recover_interrupted_mock_calls(db)
        if recovered:
            logger.info("Closed %s mock call(s) interrupted by a restart.", recovered)
    logger.info(
        "Calling system mode: %s%s",
        settings.effective_calling_mode,
        f" ({settings.mock_reason})" if settings.mock_reason else "",
    )
    yield
    await mock_simulator.cancel_background_tasks()


app = FastAPI(
    title="Voice CRM",
    version="0.1.0",
    description="MVP CRM for inbound/outbound AI calls over the existing FreePBX + ElevenLabs stack.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

for module in (calls, customers, bookings, webhooks, testing, tools):
    app.include_router(module.router)

settings.recordings_dir.mkdir(parents=True, exist_ok=True)
app.mount("/recordings", StaticFiles(directory=settings.recordings_dir), name="recordings")


@app.get("/api/health", tags=["system"])
def health() -> dict:
    """Liveness + integration status (booleans only, no secrets)."""
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        database = "ok"
    except Exception as exc:  # noqa: BLE001
        database = f"error: {exc}"
    return {
        "status": "ok" if database == "ok" else "degraded",
        "database": database,
        "calling_system": {
            "mode": settings.effective_calling_mode,
            "configured_mode": settings.calling_system_mode,
            "mock": settings.mock_mode,
            "mock_reason": settings.mock_reason,
            "base_url_configured": bool(settings.calling_system_base_url),
            "api_key_configured": bool(settings.calling_system_api_key),
            "freepbx_host_configured": bool(settings.vpn_internal_freepbx_host),
            "webhook_secret_configured": bool(settings.calling_system_webhook_secret),
        },
        "elevenlabs": {
            "api_key_configured": bool(settings.elevenlabs_api_key),
            "webhook_secret_configured": bool(settings.elevenlabs_webhook_secret),
        },
        "webhook_path": "/api/webhooks/calls",
    }
