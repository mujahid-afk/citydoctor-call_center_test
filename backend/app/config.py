"""Application configuration loaded from environment variables / backend/.env."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    try:
        return float(_env(name, str(default)))
    except ValueError:
        return default


def _env_list(name: str, default: str) -> list[str]:
    return [item.strip() for item in _env(name, default).split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    # --- calling system (existing FreePBX / ElevenLabs stack reached over VPN)
    calling_system_mode: str  # mock | vpn | elevenlabs
    mock_calling_system: bool
    calling_system_base_url: str
    calling_system_api_key: str
    calling_system_outbound_path: str
    calling_system_status_path: str
    calling_system_details_path: str
    calling_system_health_path: str
    calling_system_timeout: float
    calling_system_verify_tls: bool
    calling_system_webhook_secret: str
    vpn_internal_freepbx_host: str
    # --- ElevenLabs (webhooks, optional direct outbound mode)
    elevenlabs_api_key: str
    elevenlabs_agent_id: str
    elevenlabs_phone_number_id: str
    elevenlabs_webhook_secret: str
    elevenlabs_base_url: str
    elevenlabs_outbound_transport: str
    # --- app
    database_url: str
    mock_step_seconds: float
    auto_seed: bool
    tools_api_key: str
    cors_origins: list[str] = field(default_factory=list)
    recordings_dir: Path = BACKEND_DIR / "recordings"

    @property
    def effective_calling_mode(self) -> str:
        """The mode actually used. Falls back to mock when a real mode is not configured."""
        if self.mock_calling_system:
            return "mock"
        mode = self.calling_system_mode
        if mode in {"vpn", "real"}:
            return "vpn" if self.calling_system_base_url else "mock"
        if mode == "elevenlabs":
            return "elevenlabs" if self.elevenlabs_api_key else "mock"
        return "mock"

    @property
    def mock_mode(self) -> bool:
        return self.effective_calling_mode == "mock"

    @property
    def mock_reason(self) -> str | None:
        if not self.mock_mode:
            return None
        if self.mock_calling_system:
            return "MOCK_CALLING_SYSTEM=true"
        if self.calling_system_mode in {"vpn", "real"}:
            return "CALLING_SYSTEM_BASE_URL is not set"
        if self.calling_system_mode == "elevenlabs":
            return "ELEVENLABS_API_KEY is not set"
        return "CALLING_SYSTEM_MODE=mock"


@lru_cache
def get_settings() -> Settings:
    default_db = f"sqlite:///{(BACKEND_DIR / 'voice_crm.db').as_posix()}"
    return Settings(
        calling_system_mode=_env("CALLING_SYSTEM_MODE", "mock").lower(),
        mock_calling_system=_env_bool("MOCK_CALLING_SYSTEM", False),
        calling_system_base_url=_env("CALLING_SYSTEM_BASE_URL").rstrip("/"),
        calling_system_api_key=_env("CALLING_SYSTEM_API_KEY"),
        calling_system_outbound_path=_env("CALLING_SYSTEM_OUTBOUND_PATH", "/calls/outbound"),
        calling_system_status_path=_env("CALLING_SYSTEM_STATUS_PATH", "/calls/{call_id}/status"),
        calling_system_details_path=_env("CALLING_SYSTEM_DETAILS_PATH", "/calls/{call_id}"),
        calling_system_health_path=_env("CALLING_SYSTEM_HEALTH_PATH", "/health"),
        calling_system_timeout=_env_float("CALLING_SYSTEM_TIMEOUT", 15.0),
        calling_system_verify_tls=_env_bool("CALLING_SYSTEM_VERIFY_TLS", True),
        calling_system_webhook_secret=_env("CALLING_SYSTEM_WEBHOOK_SECRET"),
        vpn_internal_freepbx_host=_env("VPN_INTERNAL_FREEPBX_HOST"),
        elevenlabs_api_key=_env("ELEVENLABS_API_KEY"),
        elevenlabs_agent_id=_env("ELEVENLABS_AGENT_ID"),
        elevenlabs_phone_number_id=_env("ELEVENLABS_PHONE_NUMBER_ID"),
        elevenlabs_webhook_secret=_env("ELEVENLABS_WEBHOOK_SECRET"),
        elevenlabs_base_url=_env("ELEVENLABS_BASE_URL", "https://api.elevenlabs.io").rstrip("/"),
        elevenlabs_outbound_transport=_env("ELEVENLABS_OUTBOUND_TRANSPORT", "sip_trunk").lower(),
        database_url=_env("DATABASE_URL") or default_db,
        mock_step_seconds=max(0.0, _env_float("MOCK_STEP_SECONDS", 3.0)),
        auto_seed=_env_bool("AUTO_SEED", True),
        tools_api_key=_env("TOOLS_API_KEY"),
        cors_origins=_env_list("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"),
    )
