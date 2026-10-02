"""Server tools the ElevenLabs AI agent can call during a conversation.

Configure them in ElevenLabs as "Webhook" tools pointing to
``https://<public-backend>/api/tools/...``. Pass ``conversation_id`` using the
``{{system__conversation_id}}`` dynamic variable so results link to the call.
"""

from __future__ import annotations

import datetime as dt
import hmac
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..models import Booking, BookingStatus, Call, CallStatus
from ..schemas import (
    BookingOut,
    ToolCancelBooking,
    ToolCreateBooking,
    ToolHumanHandoff,
    ToolRescheduleBooking,
    ToolSaveCallOutcome,
    normalize_phone,
)
from ..services import booking_service, call_service


def verify_tools_key(x_tools_key: Annotated[str | None, Header()] = None) -> None:
    expected = get_settings().tools_api_key
    if expected and not hmac.compare_digest(x_tools_key or "", expected):
        raise HTTPException(status_code=401, detail="Invalid X-Tools-Key")


router = APIRouter(prefix="/api/tools", tags=["ai-tools"], dependencies=[Depends(verify_tools_key)])

DbSession = Annotated[Session, Depends(get_db)]

HANDOFF_NUMBERS = {
    "billing": "+97140000101",
    "medical": "+97140000102",
    "default": "+97140000100",
}


def _call_for(db: Session, conversation_id: str | None, phone: str | None) -> Call | None:
    return call_service.find_call_by_conversation(db, conversation_id) or (
        call_service.find_latest_call_for_phone(db, phone) if phone else None
    )


def _booking_dict(booking: Booking) -> dict[str, Any]:
    return BookingOut.model_validate(booking).model_dump(mode="json")


@router.get("/customer")
def tool_customer_lookup(phone: str, db: DbSession):
    """Look up a caller by phone: profile, upcoming bookings and call count."""
    try:
        phone = normalize_phone(phone)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    customer = call_service.find_customer_by_phone(db, phone)
    if not customer:
        return {"found": False, "message": "No customer found with this phone number."}
    upcoming = db.scalars(
        select(Booking)
        .where(
            Booking.customer_id == customer.id,
            Booking.appointment_date >= dt.date.today(),
            Booking.status != BookingStatus.cancelled.value,
        )
        .order_by(Booking.appointment_date, Booking.appointment_time)
    )
    return {
        "found": True,
        "customer": {"id": customer.id, "name": customer.name, "phone": customer.phone, "email": customer.email},
        "upcoming_bookings": [_booking_dict(b) for b in upcoming],
        "total_calls": len(customer.calls),
    }


@router.get("/availability")
def tool_availability(db: DbSession, date: dt.date | None = None, service: str | None = None):  # noqa: A002
    day = date or dt.date.today()
    slots = booking_service.get_available_slots(db, day, service)
    return {"date": day.isoformat(), "service": service, "available_slots": slots}


@router.post("/create-booking")
def tool_create_booking(payload: ToolCreateBooking, db: DbSession):
    customer = call_service.get_or_create_customer(db, payload.customer_phone, payload.customer_name)
    call = _call_for(db, payload.conversation_id, None)
    booking = booking_service.create_booking(
        db,
        customer=customer,
        service=payload.service,
        appointment_date=payload.appointment_date,
        appointment_time=payload.appointment_time,
        notes=payload.notes,
        call=call,
    )
    return {
        "success": True,
        "booking_reference": booking.reference,
        "message": f"Booked {booking.service} on {booking.appointment_date} at {booking.appointment_time}.",
        "booking": _booking_dict(booking),
    }


@router.post("/reschedule-booking")
def tool_reschedule_booking(payload: ToolRescheduleBooking, db: DbSession):
    booking = booking_service.get_booking_or_404(db, payload.booking_id)
    if booking.status == BookingStatus.cancelled.value:
        raise HTTPException(status_code=409, detail="Booking is cancelled")
    booking_service.ensure_slot_free(
        db, payload.new_date, payload.new_time, booking.service, exclude_id=booking.id
    )
    booking.appointment_date = payload.new_date
    booking.appointment_time = payload.new_time
    booking.status = BookingStatus.rescheduled.value
    db.commit()
    db.refresh(booking)
    return {"success": True, "message": f"Rescheduled to {booking.appointment_date} at {booking.appointment_time}.",
            "booking": _booking_dict(booking)}


@router.post("/cancel-booking")
def tool_cancel_booking(payload: ToolCancelBooking, db: DbSession):
    booking = booking_service.get_booking_or_404(db, payload.booking_id)
    booking.status = BookingStatus.cancelled.value
    if payload.reason:
        booking.notes = f"{booking.notes + chr(10) if booking.notes else ''}Cancelled: {payload.reason}"
    db.commit()
    db.refresh(booking)
    return {"success": True, "message": f"Booking {booking.reference} cancelled.", "booking": _booking_dict(booking)}


@router.post("/save-call-outcome")
def tool_save_call_outcome(payload: ToolSaveCallOutcome, db: DbSession):
    call = _call_for(db, payload.conversation_id, payload.customer_phone)
    if not call:
        raise HTTPException(status_code=404, detail="No matching call found")
    call.outcome = payload.outcome
    if payload.summary:
        call.summary = payload.summary
    if payload.purpose:
        call.purpose = payload.purpose
    db.commit()
    return {"success": True, "call_id": call.id, "outcome": call.outcome}


@router.post("/human-handoff")
def tool_human_handoff(payload: ToolHumanHandoff, db: DbSession):
    """Mark the call as transferred and return the (dummy) number to transfer to."""
    call = _call_for(db, payload.conversation_id, payload.customer_phone)
    department = (payload.department or "default").lower()
    transfer_to = HANDOFF_NUMBERS.get(department, HANDOFF_NUMBERS["default"])
    if call:
        call.status = CallStatus.transferred.value
        call.outcome = "transferred"
        if payload.reason:
            call.summary = f"{call.summary + chr(10) if call.summary else ''}Handoff reason: {payload.reason}"
        db.commit()
    return {
        "success": True,
        "transfer_to": transfer_to,
        "department": department,
        "call_id": call.id if call else None,
        "message": "Transferring you to a team member now.",
    }
