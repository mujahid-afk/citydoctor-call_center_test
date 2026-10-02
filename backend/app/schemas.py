"""Pydantic request/response schemas."""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field


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


def validate_time(value: str) -> str:
    if not _TIME_RE.match(value):
        raise ValueError("Time must be in HH:MM (24h) format")
    return value


Phone = Annotated[str, AfterValidator(normalize_phone)]
TimeHHMM = Annotated[str, AfterValidator(validate_time)]


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
    customer_phone: Phone
    status: Status
    customer_id: int | None = None
    customer_name: str | None = None
    brand_id: int | None = None
    brand_name: str | None = None
    brand_number: str | None = None
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


# ---------------------------------------------------------------- bookings
class BookingCreate(BaseModel):
    customer_id: int
    service: str = Field(min_length=1, max_length=120)
    appointment_date: date
    appointment_time: TimeHHMM
    call_id: int | None = None
    notes: str | None = None


class BookingUpdate(BaseModel):
    service: str | None = None
    appointment_date: date | None = None
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
