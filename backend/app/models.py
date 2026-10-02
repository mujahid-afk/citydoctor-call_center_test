"""SQLAlchemy ORM models."""

from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    """Naive UTC timestamp (SQLite has no timezone support; API layer marks it as UTC)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class CallDirection(str, Enum):
    inbound = "inbound"
    outbound = "outbound"


class CallStatus(str, Enum):
    queued = "queued"
    calling = "calling"
    ringing = "ringing"
    answered = "answered"
    completed = "completed"
    no_answer = "no_answer"
    failed = "failed"
    transferred = "transferred"


class CallOutcome(str, Enum):
    booked = "booked"
    inquiry = "inquiry"
    interested = "interested"
    not_interested = "not_interested"
    callback = "callback"
    transferred = "transferred"
    completed = "completed"
    failed = "failed"


class BookingStatus(str, Enum):
    confirmed = "confirmed"
    rescheduled = "rescheduled"
    cancelled = "cancelled"
    completed = "completed"


ACTIVE_CALL_STATUSES = {
    CallStatus.queued.value,
    CallStatus.calling.value,
    CallStatus.ringing.value,
    CallStatus.answered.value,
}
TERMINAL_CALL_STATUSES = {
    CallStatus.completed.value,
    CallStatus.no_answer.value,
    CallStatus.failed.value,
    CallStatus.transferred.value,
}


def booking_reference(booking_id: int | None) -> str | None:
    return f"BK-{1000 + booking_id}" if booking_id else None


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    phone: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    calls: Mapped[list[Call]] = relationship(back_populates="customer")
    bookings: Mapped[list[Booking]] = relationship(back_populates="customer")


class Brand(Base):
    __tablename__ = "brands"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    phone_number: Mapped[str] = mapped_column(String(40), index=True)
    agent_name: Mapped[str] = mapped_column(String(120))
    # Per-brand ElevenLabs agent; falls back to ELEVENLABS_AGENT_ID when empty.
    elevenlabs_agent_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # Per-brand ElevenLabs phone number ID; falls back to ELEVENLABS_PHONE_NUMBER_ID.
    elevenlabs_phone_number_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Call(Base):
    __tablename__ = "calls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # ID assigned by the existing calling system (FreePBX uniqueid, SIP Call-ID, ...).
    external_call_id: Mapped[str | None] = mapped_column(String(200), index=True, nullable=True)
    elevenlabs_conversation_id: Mapped[str | None] = mapped_column(
        String(120), unique=True, index=True, nullable=True
    )
    direction: Mapped[str] = mapped_column(String(10), index=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), nullable=True)
    customer_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    customer_phone: Mapped[str] = mapped_column(String(40), index=True)
    brand_id: Mapped[int | None] = mapped_column(ForeignKey("brands.id"), nullable=True)
    brand_name: Mapped[str] = mapped_column(String(120), index=True)
    brand_number: Mapped[str] = mapped_column(String(40), default="")
    agent_name: Mapped[str] = mapped_column(String(120), default="")
    agent_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    purpose: Mapped[str | None] = mapped_column(String(120), nullable=True)
    custom_instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), index=True, default=CallStatus.queued.value)
    outcome: Mapped[str | None] = mapped_column(String(20), index=True, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    recording_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # No DB-level FK here to avoid a circular calls <-> bookings constraint in SQLite.
    booking_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    # Last raw event received from the provider (JSON), kept for debugging.
    raw_provider_payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_mock: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    customer: Mapped[Customer | None] = relationship(back_populates="calls")

    @property
    def booking_reference(self) -> str | None:
        return booking_reference(self.booking_id)

    @property
    def recording_playback_url(self) -> str | None:
        """Browser-safe URL: always served/proxied by the backend (recordings may live on the VPN)."""
        return f"/api/calls/{self.id}/recording" if self.recording_url else None


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    call_id: Mapped[int | None] = mapped_column(ForeignKey("calls.id"), nullable=True)
    service: Mapped[str] = mapped_column(String(120))
    appointment_date: Mapped[date] = mapped_column(Date, index=True)
    appointment_time: Mapped[str] = mapped_column(String(5))
    status: Mapped[str] = mapped_column(String(20), default=BookingStatus.confirmed.value)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    customer: Mapped[Customer] = relationship(back_populates="bookings")

    @property
    def reference(self) -> str:
        return booking_reference(self.id) or ""

    @property
    def customer_name(self) -> str | None:
        return self.customer.name if self.customer else None
