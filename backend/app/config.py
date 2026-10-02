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


def _resolve_database_url(url: str) -> str:
    """Make relative SQLite paths independent of the current working directory."""
    prefix = "sqlite:///"
    if url.startswith(prefix) and not url.startswith("sqlite:////") and ":memory:" not in url:
        path = Path(url[len(prefix):])
        if not path.is_absolute():
            return f"{prefix}{(BACKEND_DIR / path).resolve().as_posix()}"
    return url


@dataclass(frozen=True)
class Settings:
    app_env: str
    app_host: str
    app_port: int
    database_url: str
    frontend_url: str
    log_level: str
    auto_seed: bool
    cors_origins: list[str] = field(default_factory=list)


@lru_cache
def get_settings() -> Settings:
    frontend_url = _env("FRONTEND_URL", "http://localhost:5173")
    origins = [o.strip() for o in _env("CORS_ORIGINS", frontend_url).split(",") if o.strip()]
    if frontend_url not in origins:
        origins.append(frontend_url)
    return Settings(
        app_env=_env("APP_ENV", "development"),
        app_host=_env("APP_HOST", "0.0.0.0"),
        app_port=int(_env("APP_PORT", "8000") or 8000),
        database_url=_resolve_database_url(_env("DATABASE_URL", "sqlite:///./voice_crm.db")),
        frontend_url=frontend_url,
        log_level=_env("LOG_LEVEL", "INFO").upper(),
        auto_seed=_env_bool("AUTO_SEED", True),
        cors_origins=origins,
    )
