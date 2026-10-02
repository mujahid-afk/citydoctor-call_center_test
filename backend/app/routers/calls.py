"""Call history + call logging from the browser softphone (no audio passes through here)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..schemas import AISummaryIn, AISummaryOut, AIStatus, CallCreate, CallOut, CallOutcomeIn, CallUpdate, Stats
from ..services import ai_service, call_service

router = APIRouter(prefix="/api", tags=["calls"])

DbSession = Annotated[Session, Depends(get_db)]


def call_filters(
    direction: Annotated[str | None, Query(pattern="^(inbound|outbound)$")] = None,
    search: str | None = None,
    brand_id: int | None = None,
    status_: Annotated[str | None, Query(alias="status")] = None,
    outcome: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
) -> call_service.CallFilters:
    return call_service.CallFilters(
        direction=direction, search=search or None, brand_id=brand_id, status=status_ or None,
        outcome=outcome or None, date_from=date_from, date_to=date_to, limit=limit,
    )


Filters = Annotated[call_service.CallFilters, Depends(call_filters)]


@router.get("/stats", response_model=Stats)
def stats(db: DbSession, filters: Filters):
    """Dashboard counters. Accepts the same filters as GET /api/calls."""
    return call_service.compute_stats(db, filters)


@router.get("/calls", response_model=list[CallOut])
def list_calls(db: DbSession, filters: Filters):
    """Newest first. Filters: direction, status, outcome, brand_id, search, date_from, date_to."""
    return call_service.list_calls(db, filters)


@router.post("/calls", response_model=CallOut, status_code=status.HTTP_201_CREATED)
def create_call(payload: CallCreate, db: DbSession):
    """Log a call (softphone: inbound -> status=ringing, outbound -> status=calling)."""
    return call_service.create_call(db, payload)


@router.get("/calls/{call_id}", response_model=CallOut)
def get_call(call_id: int, db: DbSession):
    return call_service.get_call_or_404(db, call_id)


@router.patch("/calls/{call_id}", response_model=CallOut)
def update_call(call_id: int, payload: CallUpdate, db: DbSession):
    """Update status as the call progresses, or attach ElevenLabs data later
    (elevenlabs_conversation_id, summary, transcript, recording_url)."""
    return call_service.update_call(db, call_service.get_call_or_404(db, call_id), payload)


@router.post("/calls/{call_id}/outcome", response_model=CallOut)
def set_outcome(call_id: int, payload: CallOutcomeIn, db: DbSession):
    update = CallUpdate(outcome=payload.outcome, **({"notes": payload.notes} if payload.notes is not None else {}))
    return call_service.update_call(db, call_service.get_call_or_404(db, call_id), update)


@router.get("/ai/status", response_model=AIStatus)
def ai_status():
    """Whether AI summaries are available (OPENAI_API_KEY set). Never returns the key."""
    enabled = ai_service.ai_enabled()
    return AIStatus(enabled=enabled, model=get_settings().openai_model if enabled else None)


@router.post("/calls/{call_id}/ai-summary", response_model=AISummaryOut)
def ai_summary(call_id: int, payload: AISummaryIn, db: DbSession):
    """Summarize the call with OpenAI, save the summary on the call and suggest an outcome."""
    call = call_service.get_call_or_404(db, call_id)
    result = ai_service.summarize_call(call, payload.notes)
    if result["summary"]:
        call = call_service.update_call(db, call, CallUpdate(summary=result["summary"]))
    return AISummaryOut(**result, call=call)
