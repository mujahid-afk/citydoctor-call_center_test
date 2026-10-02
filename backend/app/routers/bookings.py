"""Dummy booking + availability APIs (SQLite-backed)."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from ..models import Booking, Call, Customer
from ..schemas import BookingConfirmation, BookingCreate, BookingOut, BookingUpdate
from ..services import booking_service

router = APIRouter(prefix="/api", tags=["bookings"])

DbSession = Annotated[Session, Depends(get_db)]


@router.get("/availability", response_model=list[str])
def availability(db: DbSession, date: date, service: str | None = None):  # noqa: A002 - query name per spec
    """Fake free slots for a date, e.g. ["09:00", "10:30", "14:00", "16:30"]."""
    return booking_service.get_available_slots(db, date, service)


@router.get("/bookings", response_model=list[BookingOut])
def list_bookings(
    db: DbSession,
    customer_id: int | None = None,
    status_: Annotated[str | None, Query(alias="status")] = None,
    limit: int = 200,
):
    query = (
        select(Booking)
        .options(selectinload(Booking.customer))
        .order_by(Booking.created_at.desc(), Booking.id.desc())
        .limit(min(limit, 1000))
    )
    if customer_id:
        query = query.where(Booking.customer_id == customer_id)
    if status_:
        query = query.where(Booking.status == status_)
    return list(db.scalars(query))


@router.post("/bookings", response_model=BookingConfirmation, status_code=status.HTTP_201_CREATED)
def create_booking(payload: BookingCreate, db: DbSession):
    customer = db.get(Customer, payload.customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    call = None
    if payload.call_id is not None:
        call = db.get(Call, payload.call_id)
        if not call:
            raise HTTPException(status_code=404, detail="Call not found")
    booking = booking_service.create_booking(
        db,
        customer=customer,
        service=payload.service,
        appointment_date=payload.appointment_date,
        appointment_time=payload.appointment_time,
        notes=payload.notes,
        call=call,
    )
    return BookingConfirmation(
        message=f"Booking {booking.reference} confirmed for {booking.appointment_date} at {booking.appointment_time}",
        booking=BookingOut.model_validate(booking),
    )


@router.get("/bookings/{booking_id}", response_model=BookingOut)
def get_booking(booking_id: str, db: DbSession):
    """Accepts a numeric ID or a reference such as BK-1001."""
    return booking_service.get_booking_or_404(db, booking_id)


@router.put("/bookings/{booking_id}", response_model=BookingOut)
def update_booking(booking_id: str, payload: BookingUpdate, db: DbSession):
    booking = booking_service.get_booking_or_404(db, booking_id)
    changes = payload.model_dump(exclude_unset=True)
    new_date = changes.get("appointment_date", booking.appointment_date)
    new_time = changes.get("appointment_time", booking.appointment_time)
    new_service = changes.get("service", booking.service)
    if (new_date, new_time, new_service) != (booking.appointment_date, booking.appointment_time, booking.service):
        booking_service.ensure_slot_free(db, new_date, new_time, new_service, exclude_id=booking.id)
    if (new_date, new_time) != (booking.appointment_date, booking.appointment_time):
        changes.setdefault("status", "rescheduled")
    for field, value in changes.items():
        setattr(booking, field, value)
    db.commit()
    db.refresh(booking)
    return booking


@router.delete("/bookings/{booking_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_booking(booking_id: str, db: DbSession):
    booking = booking_service.get_booking_or_404(db, booking_id)
    for call in db.scalars(select(Call).where(Call.booking_id == booking.id)):
        call.booking_id = None
    db.delete(booking)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
