"""SQLAlchemy ORM models.

No SIP or VPN credentials are ever stored here.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    """Naive UTC timestamp (SQLite has no timezone support; the API marks it as UTC)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class CallStatus(str, Enum):
    ringing = "ringing"
    calling = "calling"
    answered = "answered"
    completed = "completed"
    missed = "missed"
    rejected = "rejected"
    failed = "failed"
    transferred = "transferred"


ACTIVE_CALL_STATUSES = {"ringing", "calling", "answered"}
TERMINAL_CALL_STATUSES = {"completed", "missed", "rejected", "failed", "transferred"}
ANSWERED_CALL_STATUSES = {"answered", "completed", "transferred"}


class BookingStatus(str, Enum):
    confirmed = "confirmed"
    rescheduled = "rescheduled"
    cancelled = "cancelled"
    completed = "completed"


def booking_reference(booking_id: int | None) -> str | None:
    return f"BK-{1000 + booking_id}" if booking_id else None


class Brand(Base):
    __tablename__ = "brands"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    # The brand's DID; inbound calls are matched to a brand by the called number.
    phone_number: Mapped[str] = mapped_column(String(40), index=True)
    elevenlabs_agent_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Queue(Base):
    """A FreePBX call queue (one per brand/department), matched by the X-Queue INVITE header.

    Unknown queue names are created automatically the first time a call arrives from them.
    """

    __tablename__ = "queues"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Exactly as FreePBX sends it in X-Queue, e.g. "CD-Booking" (matched case-insensitively).
    name: Mapped[str] = mapped_column(String(80), unique=True)
    brand_id: Mapped[int | None] = mapped_column(ForeignKey("brands.id"), nullable=True, index=True)
    department: Mapped[str | None] = mapped_column(String(80), nullable=True)
    # FreePBX queue number (e.g. 400), for reference only.
    number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    brand: Mapped[Brand | None] = relationship()

    @property
    def brand_name(self) -> str | None:
        return self.brand.name if self.brand else None


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    phone: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    calls: Mapped[list[Call]] = relationship(back_populates="customer")
    bookings: Mapped[list[Booking]] = relationship(back_populates="customer")


class Call(Base):
    __tablename__ = "calls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    direction: Mapped[str] = mapped_column(String(10), index=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), nullable=True)
    customer_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    customer_phone: Mapped[str] = mapped_column(String(40), index=True)
    brand_id: Mapped[int | None] = mapped_column(ForeignKey("brands.id"), nullable=True, index=True)
    brand_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    brand_number: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # Inbound routing reported by FreePBX (X-Queue / X-IVR-Path / X-Queue-Start headers).
    queue_id: Mapped[int | None] = mapped_column(ForeignKey("queues.id"), nullable=True, index=True)
    queue_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    ivr_path: Mapped[str | None] = mapped_column(String(200), nullable=True)
    queue_entered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Inbound: seconds the caller waited for an agent (queue entry, or ring start, until answer/hang-up).
    wait_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sip_call_id: Mapped[str | None] = mapped_column(String(200), index=True, nullable=True)
    sip_extension: Mapped[str | None] = mapped_column(String(80), nullable=True)
    elevenlabs_conversation_id: Mapped[str | None] = mapped_column(String(120), index=True, nullable=True)
    status: Mapped[str] = mapped_column(String(20), index=True)
    outcome: Mapped[str | None] = mapped_column(String(20), index=True, nullable=True)
    purpose: Mapped[str | None] = mapped_column(String(120), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    recording_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # No DB-level FK to avoid a circular calls <-> bookings constraint in SQLite.
    booking_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # True for calls made with the mock softphone or created by the seed script.
    is_mock: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    customer: Mapped[Customer | None] = relationship(back_populates="calls")

    @property
    def booking_reference(self) -> str | None:
        return booking_reference(self.booking_id)


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
