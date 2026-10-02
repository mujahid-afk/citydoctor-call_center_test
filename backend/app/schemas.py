"""Pydantic request/response schemas."""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator


def _as_utc(value: datetime) -> datetime:
    """SQLite returns naive datetimes; they are stored as UTC, so mark them as such."""
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


UTCDateTime = Annotated[datetime, AfterValidator(_as_utc)]

Direction = Literal["inbound", "outbound"]
Status = Literal[
    "queued", "calling", "ringing", "answered", "completed", "no_answer", "failed", "transferred"
]
Outcome = Literal[
    "booked",
    "inquiry",
    "interested",
    "not_interested",
    "callback",
    "transferred",
    "completed",
    "failed",
]
Purpose = Literal[
    "Appointment Reminder",
    "Follow Up",
    "Lead Qualification",
    "Booking Follow Up",
    "General Inquiry",
    "Campaign",
    "Custom",
]
BookingStatusLiteral = Literal["confirmed", "rescheduled", "cancelled", "completed"]

_PHONE_RE = re.compile(r"^\+?[0-9]{6,15}$")
_TIME_RE = re.compile(r"^([01][0-9]|2[0-3]):[0-5][0-9]$")


def normalize_phone(value: str) -> str:
    """Strip spaces/dashes/brackets and validate a basic E.164-ish number."""
    cleaned = re.sub(r"[\s\-().]", "", value or "")
    if cleaned.startswith("00"):
        cleaned = "+" + cleaned[2:]
    if not _PHONE_RE.match(cleaned):
        raise ValueError("Phone number must contain 6-15 digits, optionally starting with +")
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
    agent_name: str
    elevenlabs_agent_id: str | None
    elevenlabs_phone_number_id: str | None
    active: bool
    created_at: UTCDateTime


class BrandUpdate(BaseModel):
    phone_number: str | None = None
    agent_name: str | None = None
    elevenlabs_agent_id: str | None = None
    elevenlabs_phone_number_id: str | None = None
    active: bool | None = None


# ---------------------------------------------------------------- customers
class CustomerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    phone: Phone
    email: str | None = None


class CustomerOut(ORMModel):
    id: int
    name: str
    phone: str
    email: str | None
    created_at: UTCDateTime


# ---------------------------------------------------------------- calls
class CallListItem(ORMModel):
    """Call representation for tables (no transcript / raw payload)."""

    id: int
    external_call_id: str | None
    elevenlabs_conversation_id: str | None
    direction: Direction
    customer_id: int | None
    customer_name: str | None
    customer_phone: str
    brand_id: int | None
    brand_name: str
    brand_number: str
    agent_name: str
    agent_id: str | None
    purpose: str | None
    status: Status
    outcome: Outcome | None
    started_at: UTCDateTime
    ended_at: UTCDateTime | None
    duration_seconds: int | None
    recording_url: str | None
    recording_playback_url: str | None
    booking_id: int | None
    booking_reference: str | None
    error_message: str | None
    is_mock: bool


class CallOut(CallListItem):
    custom_instructions: str | None
    transcript: str | None
    summary: str | None
    raw_provider_payload: str | None
    created_at: UTCDateTime
    updated_at: UTCDateTime


class CallUpdate(BaseModel):
    status: Status | None = None
    outcome: Outcome | None = None
    purpose: str | None = None
    summary: str | None = None
    transcript: str | None = None
    recording_url: str | None = None
    duration_seconds: int | None = Field(default=None, ge=0)
    ended_at: datetime | None = None
    booking_id: int | None = None
    customer_name: str | None = None
    external_call_id: str | None = None
    elevenlabs_conversation_id: str | None = None


class OutboundCallCreate(BaseModel):
    customer_name: str = Field(min_length=1, max_length=200)
    customer_phone: Phone
    brand: str = Field(min_length=1)
    agent_name: str | None = None
    purpose: Purpose
    custom_instructions: str | None = Field(default=None, max_length=4000)


class SideStats(BaseModel):
    total: int
    answered: int
    missed: int = 0
    no_answer: int = 0
    failed: int = 0
    in_progress: int = 0
    bookings: int = 0


class CallStats(BaseModel):
    inbound: SideStats
    outbound: SideStats


InboundScenario = Literal["answered", "completed", "missed", "transferred", "booked", "failed"]
OutboundScenario = Literal["completed", "booked", "no_answer", "failed"]


class SimulateInboundRequest(BaseModel):
    customer_name: str | None = None
    customer_phone: Phone | None = None
    brand: str | None = None
    brand_number: str | None = None
    agent_name: str | None = None
    # answered = stays live (in progress); missed = caller hung up before answer.
    # Random realistic scenario when omitted.
    scenario: InboundScenario | None = None
    # true = write the final state immediately instead of a live progression.
    instant: bool = False


class SimulateOutboundRequest(BaseModel):
    customer_name: str | None = None
    customer_phone: Phone | None = None
    brand: str | None = None
    agent_name: str | None = None
    purpose: Purpose = "Appointment Reminder"
    custom_instructions: str | None = None
    scenario: OutboundScenario | None = None


class WebhookResult(BaseModel):
    status: Literal["ok", "ignored"]
    event: str | None = None
    call_id: int | None = None
    detail: str | None = None


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
    appointment_time: str | None = None
    status: BookingStatusLiteral | None = None
    notes: str | None = None

    @field_validator("appointment_time")
    @classmethod
    def _time(cls, value: str | None) -> str | None:
        return validate_time(value) if value else value


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


class BookingConfirmation(BaseModel):
    success: bool = True
    message: str
    booking: BookingOut


# ---------------------------------------------------------------- AI tools
class ToolCreateBooking(BaseModel):
    customer_phone: Phone
    customer_name: str | None = None
    service: str
    appointment_date: date
    appointment_time: TimeHHMM
    notes: str | None = None
    conversation_id: str | None = None


class ToolRescheduleBooking(BaseModel):
    booking_id: str = Field(description="Numeric ID or reference such as BK-1001")
    new_date: date
    new_time: TimeHHMM
    conversation_id: str | None = None


class ToolCancelBooking(BaseModel):
    booking_id: str = Field(description="Numeric ID or reference such as BK-1001")
    reason: str | None = None
    conversation_id: str | None = None


class ToolSaveCallOutcome(BaseModel):
    conversation_id: str | None = None
    customer_phone: str | None = None
    outcome: Outcome
    summary: str | None = None
    purpose: str | None = None


class ToolHumanHandoff(BaseModel):
    conversation_id: str | None = None
    customer_phone: str | None = None
    reason: str | None = None
    department: str | None = None
