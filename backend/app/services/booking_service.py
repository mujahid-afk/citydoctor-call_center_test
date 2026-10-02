"""Dummy booking / availability logic backed by SQLite."""

from __future__ import annotations

import re
from datetime import date

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Booking, BookingStatus, Call, Customer

# Fake clinic schedule. Some services get a slightly different template so the
# dummy API feels a little more realistic.
DEFAULT_SLOTS = ["09:00", "10:30", "14:00", "16:30"]
SERVICE_SLOTS: dict[str, list[str]] = {
    "physio": ["08:30", "10:00", "11:30", "15:00", "17:30"],
    "iv": ["09:30", "11:00", "13:00", "15:30", "18:00"],
    "drip": ["09:30", "11:00", "13:00", "15:30", "18:00"],
}


def slots_for_service(service: str | None) -> list[str]:
    key = (service or "").lower()
    for keyword, slots in SERVICE_SLOTS.items():
        if keyword in key:
            return slots
    return DEFAULT_SLOTS


def get_available_slots(db: Session, appointment_date: date, service: str | None) -> list[str]:
    """Template slots minus those already booked for that date and service.

    Each service has its own calendar; ``service`` may be a keyword ("doctor").
    """
    query = select(Booking.appointment_time).where(
        Booking.appointment_date == appointment_date,
        Booking.status != BookingStatus.cancelled.value,
    )
    if service:
        query = query.where(Booking.service.ilike(f"%{service.strip()}%"))
    taken = set(db.scalars(query))
    return [slot for slot in slots_for_service(service) if slot not in taken]


def ensure_slot_free(
    db: Session, appointment_date: date, appointment_time: str, service: str, exclude_id: int | None = None
) -> None:
    query = select(Booking).where(
        Booking.appointment_date == appointment_date,
        Booking.appointment_time == appointment_time,
        func.lower(Booking.service) == service.strip().lower(),
        Booking.status != BookingStatus.cancelled.value,
    )
    if exclude_id is not None:
        query = query.where(Booking.id != exclude_id)
    if db.scalars(query).first():
        raise HTTPException(
            status_code=409, detail=f"{service} slot {appointment_date} {appointment_time} is already booked"
        )


def parse_booking_ref(value: str | int) -> int:
    """Accept 7, '7' or 'BK-1007' and return the numeric booking ID."""
    text = str(value).strip().upper()
    match = re.fullmatch(r"BK-?(\d+)", text)
    if match:
        number = int(match.group(1))
        return number - 1000 if number > 1000 else number
    if text.isdigit():
        return int(text)
    raise HTTPException(status_code=422, detail=f"Invalid booking reference: {value}")


def get_booking_or_404(db: Session, booking_ref: str | int) -> Booking:
    booking = db.get(Booking, parse_booking_ref(booking_ref))
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    return booking


def create_booking(
    db: Session,
    *,
    customer: Customer,
    service: str,
    appointment_date: date,
    appointment_time: str,
    notes: str | None = None,
    call: Call | None = None,
) -> Booking:
    ensure_slot_free(db, appointment_date, appointment_time, service)
    booking = Booking(
        customer_id=customer.id,
        call_id=call.id if call else None,
        service=service,
        appointment_date=appointment_date,
        appointment_time=appointment_time,
        notes=notes,
        status=BookingStatus.confirmed.value,
    )
    db.add(booking)
    db.flush()
    if call is not None:
        call.booking_id = booking.id
        call.outcome = "booked"
    db.commit()
    db.refresh(booking)
    return booking
