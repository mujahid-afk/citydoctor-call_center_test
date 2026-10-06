"""Softphone console lines ([softphone] / [sip.js]) sent by the browser, kept in backend/client.log.

Lets the PBX/CRM side be debugged without access to the agent's browser console.
Auth headers are redacted in the browser before anything is logged.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..config import BACKEND_DIR

router = APIRouter(prefix="/api/client-logs", tags=["system"])

LOG_FILE = BACKEND_DIR / "client.log"
MAX_BYTES = 5_000_000


class ClientLogLine(BaseModel):
    level: str = Field(max_length=10)
    text: str = Field(max_length=20_000)
    at: str | None = None


class ClientLogBatch(BaseModel):
    lines: list[ClientLogLine] = Field(max_length=200)


@router.post("", status_code=204)
def append_client_logs(batch: ClientLogBatch) -> None:
    if LOG_FILE.exists() and LOG_FILE.stat().st_size > MAX_BYTES:
        LOG_FILE.replace(LOG_FILE.with_suffix(".log.1"))
    received = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with LOG_FILE.open("a", encoding="utf-8") as f:
        for line in batch.lines:
            f.write(f"{line.at or received} {line.level.upper():5} {line.text}\n")
