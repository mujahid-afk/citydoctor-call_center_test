"""Call history, outbound triggering and call details."""

from __future__ import annotations

import mimetypes
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from ..adapters.calling_system_adapter import CallingSystemUnavailable, get_calling_adapter
from ..config import get_settings
from ..database import get_db
from ..models import Booking
from ..schemas import CallListItem, CallOut, CallStats, CallUpdate, OutboundCallCreate
from ..services import call_service
from ..services.calling_system_service import CallingSystemError, CallingSystemService
from ..services.elevenlabs_service import ElevenLabsError, ElevenLabsService

router = APIRouter(prefix="/api/calls", tags=["calls"])

DbSession = Annotated[Session, Depends(get_db)]


def call_filters(
    direction: Annotated[str | None, Query(pattern="^(inbound|outbound)$")] = None,
    search: str | None = None,
    brand: str | None = None,
    agent: str | None = None,
    status_: Annotated[str | None, Query(alias="status")] = None,
    outcome: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
) -> call_service.CallFilters:
    return call_service.CallFilters(
        direction=direction,
        search=search or None,
        brand=brand or None,
        agent=agent or None,
        status=status_ or None,
        outcome=outcome or None,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
    )


Filters = Annotated[call_service.CallFilters, Depends(call_filters)]


@router.get("", response_model=list[CallListItem])
def list_calls(db: DbSession, filters: Filters):
    """List calls, newest first. Supports direction/brand/agent/status/outcome/search/date filters."""
    return call_service.list_calls(db, filters)


@router.get("/stats", response_model=CallStats)
def call_stats(db: DbSession, filters: Filters):
    """Inbound/outbound counters for the dashboard cards (same filters as the list, minus direction)."""
    return call_service.compute_stats(db, filters)


@router.post("/outbound", response_model=CallOut, status_code=status.HTTP_201_CREATED)
async def start_outbound_call(payload: OutboundCallCreate, db: DbSession):
    """Create an outbound call record and ask the calling system (via the adapter) to dial."""
    return await call_service.place_outbound_call(
        db,
        get_calling_adapter(),
        customer_name=payload.customer_name,
        customer_phone=payload.customer_phone,
        brand_name=payload.brand,
        agent_name=payload.agent_name,
        purpose=payload.purpose,
        custom_instructions=payload.custom_instructions,
    )


@router.get("/{call_id}", response_model=CallOut)
def get_call(call_id: int, db: DbSession):
    return call_service.get_call_or_404(db, call_id)


@router.patch("/{call_id}", response_model=CallOut)
def update_call(call_id: int, payload: CallUpdate, db: DbSession):
    call = call_service.get_call_or_404(db, call_id)
    changes = payload.model_dump(exclude_unset=True)
    if "booking_id" in changes and changes["booking_id"] is not None and not db.get(Booking, changes["booking_id"]):
        raise HTTPException(status_code=404, detail="Booking not found")
    if "ended_at" in changes and changes["ended_at"] is not None:
        changes["ended_at"] = call_service.naive_utc(changes["ended_at"])
    for field, value in changes.items():
        setattr(call, field, value)
    db.commit()
    db.refresh(call)
    return call


@router.post("/{call_id}/sync", response_model=CallOut)
async def sync_call(call_id: int, db: DbSession):
    """Pull the latest status/transcript from the calling system (useful when webhooks can't reach us)."""
    call = call_service.get_call_or_404(db, call_id)
    if call.is_mock:
        return call
    adapter = get_calling_adapter()
    lookup_id = call.elevenlabs_conversation_id if adapter.mode == "elevenlabs" else call.external_call_id
    if not lookup_id:
        raise HTTPException(status_code=409, detail="This call has no ID in the calling system yet.")
    try:
        event = await adapter.get_call_details(lookup_id)
    except CallingSystemUnavailable as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if event is None:
        return call
    event.crm_call_id = call.id
    return call_service.apply_call_event(db, event)


@router.get("/{call_id}/recording")
async def get_recording(call_id: int, db: DbSession):
    """Serve or proxy the call recording.

    Recordings may live on the VPN (FreePBX) or at ElevenLabs, which the
    browser cannot reach directly, so the backend always serves them.
    """
    call = call_service.get_call_or_404(db, call_id)
    url = call.recording_url
    if not url:
        raise HTTPException(status_code=404, detail="No recording for this call")

    if url.startswith("/recordings/"):
        recordings_dir = get_settings().recordings_dir.resolve()
        path = (recordings_dir / url.removeprefix("/recordings/")).resolve()
        if recordings_dir not in path.parents or not path.is_file():
            raise HTTPException(status_code=404, detail="Recording file not found")
        return FileResponse(path, media_type=mimetypes.guess_type(path.name)[0] or "audio/mpeg")

    try:
        if url.startswith("elevenlabs://"):
            audio = await ElevenLabsService().get_conversation_audio(url.removeprefix("elevenlabs://"))
            return Response(content=audio, media_type="audio/mpeg")
        if url.startswith(("http://", "https://")):
            content, content_type = await CallingSystemService().fetch_bytes(url)
            return Response(content=content, media_type=content_type)
    except (ElevenLabsError, CallingSystemError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    raise HTTPException(status_code=404, detail="Unsupported recording location")
