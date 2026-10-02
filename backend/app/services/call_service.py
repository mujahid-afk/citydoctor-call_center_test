"""Call business logic: filtering, statistics, customer/brand matching and lifecycle rules.

The browser softphone reports call progress (POST /api/calls, PATCH /api/calls/{id});
this module keeps the records consistent (answered_at, ended_at, duration, links).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from ..models import (
    ACTIVE_CALL_STATUSES,
    ANSWERED_CALL_STATUSES,
    TERMINAL_CALL_STATUSES,
    Booking,
    Brand,
    Call,
    Customer,
    utcnow,
)
from ..schemas import CallCreate, CallUpdate


# --------------------------------------------------------------------------- helpers
def naive_utc(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def phone_digits(phone: str | None) -> str:
    return re.sub(r"\D", "", phone or "")


def _phone_suffix(phone: str | None) -> str:
    """Last 9 digits: matches +971501234567, 971501234567 and 0501234567 alike."""
    return phone_digits(phone)[-9:]


# --------------------------------------------------------------------------- lookups
def find_customer_by_phone(db: Session, phone: str | None) -> Customer | None:
    suffix = _phone_suffix(phone)
    if not suffix:
        return None
    exact = db.scalars(select(Customer).where(Customer.phone == phone)).first()
    if exact:
        return exact
    if len(suffix) < 6:  # short extensions only match exactly
        return None
    for customer in db.scalars(select(Customer).where(Customer.phone.like(f"%{suffix}"))):
        if _phone_suffix(customer.phone) == suffix:
            return customer
    return None


def resolve_brand(
    db: Session, *, brand_id: int | None = None, name: str | None = None, number: str | None = None
) -> Brand | None:
    if brand_id:
        return db.get(Brand, brand_id)
    if name:
        brand = db.scalars(select(Brand).where(func.lower(Brand.name) == name.strip().lower())).first()
        if brand:
            return brand
    suffix = _phone_suffix(number)
    if suffix:
        for brand in db.scalars(select(Brand)):
            if _phone_suffix(brand.phone_number) == suffix:
                return brand
    return None


def get_call_or_404(db: Session, call_id: int) -> Call:
    call = db.get(Call, call_id)
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")
    return call


# --------------------------------------------------------------------------- listing / stats
@dataclass
class CallFilters:
    direction: str | None = None
    search: str | None = None
    brand_id: int | None = None
    status: str | None = None
    outcome: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    limit: int = 200


def _apply_filters(query, filters: CallFilters, include_direction: bool = True):
    if include_direction and filters.direction:
        query = query.where(Call.direction == filters.direction)
    if filters.brand_id:
        query = query.where(Call.brand_id == filters.brand_id)
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
        conditions = [Call.customer_name.ilike(f"%{term}%"), Call.customer_phone.ilike(f"%{term}%")]
        digits = phone_digits(term)
        if digits:
            conditions.append(Call.customer_phone.ilike(f"%{digits}%"))
        query = query.where(or_(*conditions))
    return query


def list_calls(db: Session, filters: CallFilters) -> list[Call]:
    query = _apply_filters(select(Call), filters)
    query = query.order_by(Call.started_at.desc(), Call.id.desc()).limit(filters.limit)
    return list(db.scalars(query))


def compute_stats(db: Session, filters: CallFilters) -> dict[str, int]:
    rows = db.execute(
        _apply_filters(select(Call.direction, Call.status, Call.booking_id, Call.duration_seconds), filters)
    ).all()
    talk_times = [r.duration_seconds for r in rows if r.status in ANSWERED_CALL_STATUSES and r.duration_seconds]
    return {
        "total_calls": len(rows),
        "inbound_calls": sum(r.direction == "inbound" for r in rows),
        "outbound_calls": sum(r.direction == "outbound" for r in rows),
        "answered": sum(r.status in ANSWERED_CALL_STATUSES for r in rows),
        "missed": sum(r.status in {"missed", "rejected"} for r in rows),
        "failed": sum(r.status == "failed" for r in rows),
        "in_progress": sum(r.status in ACTIVE_CALL_STATUSES for r in rows),
        "bookings": sum(bool(r.booking_id) for r in rows),
        "average_duration_seconds": round(sum(talk_times) / len(talk_times)) if talk_times else 0,
    }


# --------------------------------------------------------------------------- lifecycle
def _apply_lifecycle(call: Call, explicit_duration: bool) -> None:
    """Fill timestamps/duration implied by the status (unless the client sent them)."""
    now = utcnow()
    if call.status == "answered" and call.answered_at is None:
        call.answered_at = now
    if call.status in TERMINAL_CALL_STATUSES:
        if call.ended_at is None:
            call.ended_at = now
        if not explicit_duration and call.duration_seconds is None:
            # Duration = talk time; unanswered calls have 0.
            start = call.answered_at
            call.duration_seconds = max(0, int((call.ended_at - start).total_seconds())) if start else 0
        if call.outcome is None and call.booking_id:
            call.outcome = "booked"


def _link_customer(db: Session, call: Call) -> None:
    if call.customer_id:
        customer = db.get(Customer, call.customer_id)
    else:
        customer = find_customer_by_phone(db, call.customer_phone)
    if customer:
        call.customer_id = customer.id
        call.customer_name = customer.name


def _link_brand(db: Session, call: Call, brand: Brand | None) -> None:
    if brand:
        call.brand_id = brand.id
        call.brand_name = brand.name
        call.brand_number = call.brand_number or brand.phone_number


def create_call(db: Session, payload: CallCreate) -> Call:
    if payload.customer_id and not db.get(Customer, payload.customer_id):
        raise HTTPException(status_code=404, detail="Customer not found")
    data = payload.model_dump()
    data["started_at"] = naive_utc(data["started_at"]) or utcnow()
    call = Call(**data)
    _link_customer(db, call)
    brand = resolve_brand(db, brand_id=payload.brand_id, name=payload.brand_name, number=payload.brand_number)
    _link_brand(db, call, brand)
    _apply_lifecycle(call, explicit_duration=False)
    db.add(call)
    db.commit()
    db.refresh(call)
    return call


def update_call(db: Session, call: Call, payload: CallUpdate) -> Call:
    changes = payload.model_dump(exclude_unset=True)
    for key in ("answered_at", "ended_at"):
        if changes.get(key) is not None:
            changes[key] = naive_utc(changes[key])

    if changes.get("booking_id") is not None and not db.get(Booking, changes["booking_id"]):
        raise HTTPException(status_code=404, detail="Booking not found")
    if changes.get("customer_id") is not None and not db.get(Customer, changes["customer_id"]):
        raise HTTPException(status_code=404, detail="Customer not found")

    # Never move a finished call back to an in-progress status (late events).
    if changes.get("status") in ACTIVE_CALL_STATUSES and call.status in TERMINAL_CALL_STATUSES:
        changes.pop("status")

    for key, value in changes.items():
        setattr(call, key, value)

    if changes.get("customer_id"):
        _link_customer(db, call)
    if changes.get("brand_id"):
        call.brand_number = None
        _link_brand(db, call, db.get(Brand, changes["brand_id"]))
    _apply_lifecycle(call, explicit_duration="duration_seconds" in changes)
    db.commit()
    db.refresh(call)
    return call


def customer_lookup(db: Session, customer: Customer) -> dict:
    calls = db.scalars(
        select(Call).where(Call.customer_id == customer.id).order_by(Call.started_at.desc()).limit(10)
    )
    bookings = db.scalars(
        select(Booking)
        .options(selectinload(Booking.customer))
        .where(Booking.customer_id == customer.id)
        .order_by(Booking.appointment_date.desc(), Booking.appointment_time.desc())
    )
    return {"customer": customer, "recent_calls": list(calls), "bookings": list(bookings)}
