"""Call business logic: querying, statistics and applying normalized provider events."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from ..config import get_settings
from ..models import (
    ACTIVE_CALL_STATUSES,
    TERMINAL_CALL_STATUSES,
    Brand,
    Call,
    CallDirection,
    CallStatus,
    Customer,
    utcnow,
)
from ..schemas import normalize_phone
from ..adapters.call_events import NormalizedCallEvent
from ..adapters.calling_system_adapter import CallingSystemAdapter, CallingSystemUnavailable

logger = logging.getLogger(__name__)

ANSWERED_STATUSES = {"answered", "completed", "transferred"}
UNKNOWN_CALLER_NAME = "Unknown Caller"


# --------------------------------------------------------------------------- queries
@dataclass
class CallFilters:
    direction: str | None = None
    search: str | None = None
    brand: str | None = None
    agent: str | None = None
    status: str | None = None
    outcome: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    limit: int = 200


def naive_utc(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _apply_filters(query, filters: CallFilters, include_direction: bool = True):
    if include_direction and filters.direction:
        query = query.where(Call.direction == filters.direction)
    if filters.brand:
        query = query.where(Call.brand_name == filters.brand)
    if filters.agent:
        query = query.where(Call.agent_name == filters.agent)
    if filters.status:
        query = query.where(Call.status == filters.status)
    if filters.outcome:
        query = query.where(Call.outcome == filters.outcome)
    if filters.date_from:
        query = query.where(Call.started_at >= naive_utc(filters.date_from))
    if filters.date_to:
        query = query.where(Call.started_at <= naive_utc(filters.date_to))
    if filters.search:
        term = filters.search.strip()
        like = f"%{term}%"
        digits = re.sub(r"\D", "", term)
        conditions = [Call.customer_name.ilike(like), Call.customer_phone.ilike(like)]
        if digits:
            conditions.append(Call.customer_phone.ilike(f"%{digits}%"))
        query = query.where(or_(*conditions))
    return query


def list_calls(db: Session, filters: CallFilters) -> list[Call]:
    query = select(Call).options(selectinload(Call.customer))
    query = _apply_filters(query, filters)
    query = query.order_by(Call.started_at.desc(), Call.id.desc()).limit(filters.limit)
    return list(db.scalars(query))


def get_call_or_404(db: Session, call_id: int) -> Call:
    call = db.scalars(select(Call).options(selectinload(Call.customer)).where(Call.id == call_id)).first()
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")
    return call


def compute_stats(db: Session, filters: CallFilters) -> dict:
    """Aggregate counters per direction (direction filter is ignored)."""
    query = select(Call.direction, Call.status, Call.booking_id)
    query = _apply_filters(query, filters, include_direction=False)
    result = {
        d: {"total": 0, "answered": 0, "missed": 0, "no_answer": 0, "failed": 0, "in_progress": 0, "bookings": 0}
        for d in ("inbound", "outbound")
    }
    for direction, status, booking_id in db.execute(query):
        bucket = result.get(direction)
        if bucket is None:
            continue
        bucket["total"] += 1
        if status in ANSWERED_STATUSES:
            bucket["answered"] += 1
        if status == CallStatus.no_answer.value:
            bucket["no_answer"] += 1
        if status == CallStatus.failed.value:
            bucket["failed"] += 1
        if status in {CallStatus.no_answer.value, CallStatus.failed.value}:
            bucket["missed"] += 1
        if status in ACTIVE_CALL_STATUSES:
            bucket["in_progress"] += 1
        if booking_id:
            bucket["bookings"] += 1
    return result


# --------------------------------------------------------------------------- lookups
def phone_digits(phone: str | None) -> str:
    return re.sub(r"\D", "", phone or "")


def clean_phone(phone: str) -> str:
    """Best-effort normalization for numbers coming from providers (never raises)."""
    try:
        return normalize_phone(phone)
    except ValueError:
        return phone.strip()


def find_customer_by_phone(db: Session, phone: str | None) -> Customer | None:
    digits = phone_digits(phone)
    if not digits:
        return None
    exact = db.scalars(select(Customer).where(Customer.phone == phone)).first()
    if exact:
        return exact
    # Tolerate formatting differences ("+971 50..." vs "97150...").
    for customer in db.scalars(select(Customer).where(Customer.phone.like(f"%{digits[-9:]}"))):
        if phone_digits(customer.phone).endswith(digits[-9:]):
            return customer
    return None


def get_or_create_customer(db: Session, phone: str, name: str | None = None) -> Customer:
    customer = find_customer_by_phone(db, phone)
    if customer:
        # Upgrade placeholder names once we learn the real one.
        if name and customer.name == UNKNOWN_CALLER_NAME:
            customer.name = name
        return customer
    customer = Customer(name=name or UNKNOWN_CALLER_NAME, phone=clean_phone(phone))
    db.add(customer)
    db.flush()
    return customer


def resolve_brand(
    db: Session,
    *,
    name: str | None = None,
    number: str | None = None,
    agent_id: str | None = None,
) -> Brand | None:
    if name:
        brand = db.scalars(select(Brand).where(func.lower(Brand.name) == name.lower())).first()
        if brand:
            return brand
    if agent_id:
        brand = db.scalars(select(Brand).where(Brand.elevenlabs_agent_id == agent_id)).first()
        if brand:
            return brand
    digits = phone_digits(number)
    if digits:
        for brand in db.scalars(select(Brand)):
            if phone_digits(brand.phone_number) == digits:
                return brand
    return None


def get_brand_or_404(db: Session, name: str) -> Brand:
    brand = resolve_brand(db, name=name)
    if not brand:
        raise HTTPException(status_code=404, detail=f"Brand '{name}' not found")
    return brand


def find_call_by_conversation(db: Session, conversation_id: str | None) -> Call | None:
    if not conversation_id:
        return None
    return db.scalars(select(Call).where(Call.elevenlabs_conversation_id == conversation_id)).first()


def find_latest_call_for_phone(db: Session, phone: str | None) -> Call | None:
    customer = find_customer_by_phone(db, phone)
    digits = phone_digits(phone)
    query = select(Call).order_by(Call.started_at.desc())
    if customer:
        query = query.where(or_(Call.customer_id == customer.id, Call.customer_phone == phone))
    elif digits:
        query = query.where(Call.customer_phone.like(f"%{digits[-9:]}"))
    else:
        return None
    return db.scalars(query).first()


def _find_call_for_event(db: Session, event: NormalizedCallEvent) -> Call | None:
    if event.crm_call_id:
        call = db.get(Call, event.crm_call_id)
        if call:
            return call
    call = find_call_by_conversation(db, event.conversation_id)
    if call:
        return call
    if event.external_call_id:
        call = db.scalars(select(Call).where(Call.external_call_id == event.external_call_id)).first()
        if call:
            return call
    # Fallback: an in-progress call from the same number with no provider IDs yet
    # (e.g. created by the ElevenLabs conversation-initiation webhook).
    digits = phone_digits(event.customer_phone)
    if digits:
        since = utcnow() - timedelta(hours=2)
        query = (
            select(Call)
            .where(
                Call.elevenlabs_conversation_id.is_(None),
                Call.status.in_(ACTIVE_CALL_STATUSES),
                Call.started_at >= since,
                Call.customer_phone.like(f"%{digits[-9:]}"),
            )
            .order_by(Call.started_at.desc())
        )
        if event.direction:
            query = query.where(Call.direction == event.direction)
        return db.scalars(query).first()
    return None


# --------------------------------------------------------------------------- mutations
def create_call(
    db: Session,
    *,
    direction: str,
    customer_phone: str,
    customer_name: str | None = None,
    brand: Brand | None = None,
    brand_name: str | None = None,
    brand_number: str | None = None,
    agent_name: str | None = None,
    agent_id: str | None = None,
    purpose: str | None = None,
    custom_instructions: str | None = None,
    status: str = CallStatus.queued.value,
    external_call_id: str | None = None,
    conversation_id: str | None = None,
    is_mock: bool = False,
    started_at: datetime | None = None,
) -> Call:
    """Create a call row, linking (or creating) the customer by phone."""
    customer_phone = clean_phone(customer_phone)
    customer = get_or_create_customer(db, customer_phone, customer_name)
    call = Call(
        direction=direction,
        customer_id=customer.id,
        customer_name=customer_name or customer.name,
        customer_phone=customer_phone,
        brand_id=brand.id if brand else None,
        brand_name=brand.name if brand else (brand_name or "Unknown Brand"),
        brand_number=brand_number or (brand.phone_number if brand else ""),
        agent_name=agent_name or (brand.agent_name if brand else "AI Agent"),
        agent_id=agent_id or (brand.elevenlabs_agent_id if brand else None),
        purpose=purpose,
        custom_instructions=custom_instructions,
        status=status,
        external_call_id=external_call_id,
        elevenlabs_conversation_id=conversation_id,
        is_mock=is_mock,
        started_at=started_at or utcnow(),
    )
    db.add(call)
    db.flush()
    return call


def _save_recording(call: Call, audio: bytes) -> str:
    settings = get_settings()
    settings.recordings_dir.mkdir(parents=True, exist_ok=True)
    name = f"{call.elevenlabs_conversation_id or f'call-{call.id}'}.mp3"
    (settings.recordings_dir / name).write_bytes(audio)
    return f"/recordings/{name}"


RAW_PAYLOAD_HISTORY = 10


def _scrub(value):
    """Drop base64 audio blobs before storing payloads."""
    if isinstance(value, dict):
        return {k: ("<omitted>" if k == "full_audio" else _scrub(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [_scrub(v) for v in value]
    return value


def append_raw_payload(existing: str | None, payload: dict) -> str:
    """Keep the last RAW_PAYLOAD_HISTORY provider payloads as a JSON array (oldest first)."""
    try:
        history = json.loads(existing) if existing else []
    except json.JSONDecodeError:
        history = []
    if not isinstance(history, list):
        history = [history]
    history.append({"received_at": utcnow().isoformat() + "Z", "payload": _scrub(payload)})
    return json.dumps(history[-RAW_PAYLOAD_HISTORY:], default=str)


def apply_call_event(db: Session, event: NormalizedCallEvent, raw_payload: dict | None = None) -> Call | None:
    """Apply a normalized event to the matching Call, creating it if needed."""
    if event.event_type == "unknown":
        logger.info("Ignoring unknown call event: %s", event.raw_type)
        return None

    call = _find_call_for_event(db, event)

    if call is None:
        if not event.customer_phone:
            logger.warning("No call matches event %s (%s); ignoring", event.raw_type, event.conversation_id)
            return None
        direction = event.direction or CallDirection.inbound.value
        brand = resolve_brand(db, name=event.brand_name, number=event.brand_number, agent_id=event.agent_id)
        call = create_call(
            db,
            direction=direction,
            customer_phone=event.customer_phone,
            customer_name=event.customer_name,
            brand=brand,
            brand_name=event.brand_name,
            brand_number=event.brand_number,
            agent_name=event.agent_name,
            agent_id=event.agent_id,
            status=CallStatus.ringing.value if direction == "inbound" else CallStatus.calling.value,
            started_at=event.started_at,
        )
    elif event.customer_name and (call.customer_name in (None, UNKNOWN_CALLER_NAME)):
        call.customer_name = event.customer_name
        if call.customer and call.customer.name == UNKNOWN_CALLER_NAME:
            call.customer.name = event.customer_name

    if event.conversation_id and not call.elevenlabs_conversation_id:
        call.elevenlabs_conversation_id = event.conversation_id
    if event.external_call_id and not call.external_call_id:
        call.external_call_id = event.external_call_id
    if event.agent_id and not call.agent_id:
        call.agent_id = event.agent_id

    # Never move a finished call back to an "in progress" status (late/out-of-order events).
    if event.status:
        regressing = call.status in TERMINAL_CALL_STATUSES and event.status in ACTIVE_CALL_STATUSES
        if not regressing:
            call.status = event.status

    if event.started_at:
        call.started_at = event.started_at
    if event.ended_at:
        call.ended_at = event.ended_at
    if event.duration_seconds is not None:
        call.duration_seconds = event.duration_seconds
    if event.transcript:
        call.transcript = event.transcript
    if event.summary:
        call.summary = event.summary
    if event.purpose and not call.purpose:
        call.purpose = event.purpose
    if event.error_message:
        call.error_message = event.error_message

    if event.recording_audio:
        call.recording_url = _save_recording(call, event.recording_audio)
    elif event.recording_url:
        call.recording_url = event.recording_url
    elif event.has_provider_audio and not call.recording_url and call.elevenlabs_conversation_id:
        # Fetched on demand from ElevenLabs by GET /api/calls/{id}/recording.
        call.recording_url = f"elevenlabs://{call.elevenlabs_conversation_id}"

    if event.outcome and not (call.booking_id and event.outcome == "completed"):
        # A booking made during the call wins over a generic "completed".
        call.outcome = event.outcome

    if call.status in TERMINAL_CALL_STATUSES:
        if not call.ended_at:
            call.ended_at = utcnow()
        if call.duration_seconds is None:
            answered = call.status in ANSWERED_STATUSES
            call.duration_seconds = max(0, int((call.ended_at - call.started_at).total_seconds())) if answered else 0
        if not call.outcome:
            if call.booking_id:
                call.outcome = "booked"
            elif call.status == CallStatus.transferred.value:
                call.outcome = "transferred"
            elif call.status == CallStatus.failed.value:
                call.outcome = "failed"
            elif call.status == CallStatus.completed.value:
                call.outcome = "completed"

    if raw_payload is not None:
        call.raw_provider_payload = append_raw_payload(call.raw_provider_payload, raw_payload)

    db.commit()
    db.refresh(call)
    return call


# --------------------------------------------------------------------------- outbound
async def place_outbound_call(
    db: Session,
    adapter: CallingSystemAdapter,
    *,
    customer_name: str,
    customer_phone: str,
    brand_name: str,
    agent_name: str | None,
    purpose: str,
    custom_instructions: str | None = None,
    extra_context: dict | None = None,
) -> Call:
    """Create the call record, then hand it to the calling system via the adapter.

    The record is always kept: if the calling system rejects the request or is
    unreachable, the call is stored as ``failed`` with the error message.
    """
    brand = get_brand_or_404(db, brand_name)
    call = create_call(
        db,
        direction=CallDirection.outbound.value,
        customer_phone=customer_phone,
        customer_name=customer_name,
        brand=brand,
        agent_name=agent_name,
        purpose=purpose,
        custom_instructions=custom_instructions,
        status=CallStatus.queued.value,
        is_mock=adapter.is_mock,
    )
    db.commit()

    context = {
        "crm_call_id": call.id,
        "customer_name": customer_name,
        "brand_number": call.brand_number,
        "agent_name": call.agent_name,
        "custom_instructions": custom_instructions or "",
        "elevenlabs_phone_number_id": brand.elevenlabs_phone_number_id,
        **(extra_context or {}),
    }
    try:
        result = await adapter.start_outbound_call(
            customer_phone=customer_phone,
            brand=brand.name,
            agent_id=call.agent_id or get_settings().elevenlabs_agent_id or None,
            purpose=purpose,
            context=context,
        )
    except CallingSystemUnavailable as exc:
        logger.warning("Outbound call %s failed to start: %s", call.id, exc)
        call.status = CallStatus.failed.value
        call.outcome = "failed"
        call.error_message = str(exc)
        call.ended_at = utcnow()
        call.duration_seconds = 0
        db.commit()
        db.refresh(call)
        return call

    call.external_call_id = result.external_call_id
    call.elevenlabs_conversation_id = result.conversation_id
    if call.status in ACTIVE_CALL_STATUSES:
        call.status = result.status
    call.raw_provider_payload = append_raw_payload(call.raw_provider_payload, {"outbound_response": result.raw})
    db.commit()
    db.refresh(call)
    return call
