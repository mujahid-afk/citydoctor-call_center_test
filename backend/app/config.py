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


def _first_env(*names: str) -> str:
    for name in names:
        value = _env(name)
        if value:
            return value
    return ""


def _azure_resource_url(url: str) -> str:
    """Accept a resource or a Foundry *project* endpoint and return the resource base URL.

    https://x.services.ai.azure.com/api/projects/p -> https://x.services.ai.azure.com
    """
    url = url.strip().rstrip("/")
    for marker in ("/api/projects", "/openai"):
        if marker in url:
            url = url.split(marker, 1)[0]
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
    azure_api_key: str
    azure_endpoint: str
    azure_deployment: str
    azure_api_version: str
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
        azure_api_key=_first_env("AZURE_OPENAI_API_KEY", "AZURE_API_KEY"),
        azure_endpoint=_azure_resource_url(
            _first_env("AZURE_OPENAI_ENDPOINT", "Azure_open_ai_endpoint", "AZURE_OPEN_AI_ENDPOINT",
                       "Azure_project_endpoint", "AZURE_PROJECT_ENDPOINT")
        ),
        azure_deployment=_first_env("AZURE_OPENAI_DEPLOYMENT", "AZURE_OPENAI_MODEL") or "gpt-4.1-mini",
        azure_api_version=_env("AZURE_OPENAI_API_VERSION", "2024-10-21"),
        cors_origins=origins,
    )
