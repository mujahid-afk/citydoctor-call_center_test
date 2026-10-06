"""Pydantic request/response schemas."""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict, Field


def _as_utc(value: datetime) -> datetime:
    """SQLite returns naive datetimes; they are stored as UTC, so mark them as such."""
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


UTCDateTime = Annotated[datetime, AfterValidator(_as_utc)]

Direction = Literal["inbound", "outbound"]
Status = Literal["ringing", "calling", "answered", "completed", "missed", "rejected", "failed", "transferred"]
Outcome = Literal[
    "booked", "inquiry", "interested", "not_interested", "callback", "transferred", "completed", "failed"
]
BookingStatusLiteral = Literal["confirmed", "rescheduled", "cancelled", "completed"]

_PHONE_RE = re.compile(r"^\+?[0-9]{3,15}$")
_TIME_RE = re.compile(r"^([01][0-9]|2[0-3]):[0-5][0-9]$")


def normalize_phone(value: str) -> str:
    """Strip spaces/dashes/brackets; accepts E.164, national numbers and short extensions."""
    cleaned = re.sub(r"[\s\-().]", "", value or "")
    if cleaned.startswith("00"):
        cleaned = "+" + cleaned[2:]
    if not _PHONE_RE.match(cleaned):
        raise ValueError("Phone number must contain 3-15 digits, optionally starting with +")
    return cleaned


HIDDEN_CALLER = "anonymous"


def normalize_caller_id(value: object) -> str:
    """Caller ID of a call: a phone number when there is one, else 'anonymous'.

    Unlike a customer's phone, a call is never rejected over its caller ID: withheld
    numbers arrive as 'anonymous', 'Restricted', 'unknown' or nothing at all.
    """
    cleaned = re.sub(r"[\s\-().]", "", str(value or ""))
    if cleaned.startswith("00"):
        cleaned = "+" + cleaned[2:]
    return cleaned if re.fullmatch(r"\+?[0-9*#]{1,32}", cleaned) else HIDDEN_CALLER


def validate_time(value: str) -> str:
    if not _TIME_RE.match(value):
        raise ValueError("Time must be in HH:MM (24h) format")
    return value


def validate_not_past(value: date) -> date:
    if value < date.today():
        raise ValueError("Appointment date is in the past")
    return value


def _label(limit: int) -> AfterValidator:
    """PBX-supplied labels: trimmed and truncated rather than rejected, so a call is never lost over a label."""
    return AfterValidator(lambda v: (v.strip()[:limit] or None) if v is not None else None)


Phone = Annotated[str, AfterValidator(normalize_phone)]
CallerId = Annotated[str, BeforeValidator(normalize_caller_id)]
TimeHHMM = Annotated[str, AfterValidator(validate_time)]
AppointmentDate = Annotated[date, AfterValidator(validate_not_past)]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------- brands
class BrandOut(ORMModel):
    id: int
    name: str
    phone_number: str
    elevenlabs_agent_id: str | None
    active: bool
    created_at: UTCDateTime


class BrandUpdate(BaseModel):
    phone_number: str | None = None
    elevenlabs_agent_id: str | None = None
    active: bool | None = None


# ---------------------------------------------------------------- queues
class QueueOut(ORMModel):
    id: int
    name: str
    brand_id: int | None
    brand_name: str | None
    department: str | None
    number: str | None
    active: bool
    created_at: UTCDateTime


class QueueCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    brand_id: int | None = None
    department: str | None = Field(default=None, max_length=80)
    number: str | None = Field(default=None, max_length=20)


class QueueUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    brand_id: int | None = None
    department: str | None = Field(default=None, max_length=80)
    number: str | None = Field(default=None, max_length=20)
    active: bool | None = None


# ---------------------------------------------------------------- customers
class CustomerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    phone: Phone
    email: str | None = None
    notes: str | None = None


class CustomerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    phone: Phone | None = None
    email: str | None = None
    notes: str | None = None


class CustomerOut(ORMModel):
    id: int
    name: str
    phone: str
    email: str | None
    notes: str | None
    created_at: UTCDateTime
    updated_at: UTCDateTime


# ---------------------------------------------------------------- calls
class CallOut(ORMModel):
    id: int
    direction: Direction
    customer_id: int | None
    customer_name: str | None
    customer_phone: str
    brand_id: int | None
    brand_name: str | None
    brand_number: str | None
    queue_id: int | None
    queue_name: str | None
    ivr_path: str | None
    queue_entered_at: UTCDateTime | None
    wait_seconds: int | None
    sip_call_id: str | None
    sip_extension: str | None
    elevenlabs_conversation_id: str | None
    status: Status
    outcome: Outcome | None
    purpose: str | None
    started_at: UTCDateTime
    answered_at: UTCDateTime | None
    ended_at: UTCDateTime | None
    duration_seconds: int | None
    summary: str | None
    transcript: str | None
    recording_url: str | None
    booking_id: int | None
    booking_reference: str | None
    notes: str | None
    is_mock: bool
    created_at: UTCDateTime
    updated_at: UTCDateTime


class CallCreate(BaseModel):
    direction: Direction
    customer_phone: CallerId = HIDDEN_CALLER
    status: Status
    customer_id: int | None = None
    customer_name: str | None = None
    brand_id: int | None = None
    brand_name: Annotated[str | None, _label(120)] = None  # X-Brand for inbound calls
    brand_number: str | None = None
    # Inbound routing from the FreePBX INVITE headers (X-Queue, X-IVR-Path, X-Queue-Start).
    queue_name: Annotated[str | None, _label(80)] = None
    ivr_path: Annotated[str | None, _label(200)] = None
    queue_entered_at: datetime | None = None
    sip_call_id: str | None = None
    sip_extension: str | None = None
    purpose: str | None = None
    notes: str | None = None
    started_at: datetime | None = None
    is_mock: bool = False


class CallUpdate(BaseModel):
    status: Status | None = None
    outcome: Outcome | None = None
    purpose: str | None = None
    customer_id: int | None = None
    customer_name: str | None = None
    brand_id: int | None = None
    sip_call_id: str | None = None
    sip_extension: str | None = None
    elevenlabs_conversation_id: str | None = None
    answered_at: datetime | None = None
    ended_at: datetime | None = None
    duration_seconds: int | None = Field(default=None, ge=0)
    summary: str | None = None
    transcript: str | None = None
    recording_url: str | None = None
    booking_id: int | None = None
    notes: str | None = None


class CallOutcomeIn(BaseModel):
    outcome: Outcome
    notes: str | None = None


class Stats(BaseModel):
    total_calls: int
    inbound_calls: int
    outbound_calls: int
    answered: int
    missed: int
    failed: int
    in_progress: int
    bookings: int
    average_duration_seconds: int
    average_wait_seconds: int


class BreakdownRow(BaseModel):
    """One row of the per-queue / per-brand report."""

    id: int | None
    name: str
    brand_name: str | None = None
    department: str | None = None
    total_calls: int
    inbound_calls: int
    outbound_calls: int
    answered: int
    missed: int
    failed: int
    bookings: int
    answer_rate: int  # percent of calls answered
    average_wait_seconds: int
    max_wait_seconds: int
    average_duration_seconds: int


# ---------------------------------------------------------------- bookings
class BookingCreate(BaseModel):
    customer_id: int
    service: str = Field(min_length=1, max_length=120)
    appointment_date: AppointmentDate
    appointment_time: TimeHHMM
    call_id: int | None = None
    notes: str | None = None


class BookingUpdate(BaseModel):
    service: str | None = None
    appointment_date: AppointmentDate | None = None
    appointment_time: TimeHHMM | None = None
    status: BookingStatusLiteral | None = None
    notes: str | None = None


class BookingOut(ORMModel):
    id: int
    reference: str
    customer_id: int
    customer_name: str | None
    call_id: int | None
    service: str
    appointment_date: date
    appointment_time: str
    status: BookingStatusLiteral
    notes: str | None
    created_at: UTCDateTime


class CustomerLookup(BaseModel):
    customer: CustomerOut
    recent_calls: list[CallOut]
    bookings: list[BookingOut]


# ---------------------------------------------------------------- AI
class AISummaryIn(BaseModel):
    # Unsaved notes from the UI; falls back to the call's saved notes.
    notes: str | None = None


class AISummaryOut(BaseModel):
    summary: str
    suggested_outcome: Outcome | None
    next_action: str
    call: CallOut


class AIStatus(BaseModel):
    enabled: bool
    model: str | None
