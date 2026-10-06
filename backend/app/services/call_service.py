"""Call business logic: filtering, statistics, customer/brand/queue matching and lifecycle rules.

The browser softphone reports call progress (POST /api/calls, PATCH /api/calls/{id});
this module keeps the records consistent (answered_at, ended_at, duration, links).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, replace
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from ..models import (
    ACTIVE_CALL_STATUSES,
    ANSWERED_CALL_STATUSES,
    TERMINAL_CALL_STATUSES,
    Booking,
    Brand,
    Call,
    Customer,
    Queue,
    utcnow,
)
from ..schemas import CallCreate, CallUpdate

logger = logging.getLogger("voice_crm.calls")


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


def label_key(value: str | None) -> str:
    """Loose label comparison: 'City Doctor', 'CityDoctor' and 'city-doctor' are the same brand."""
    return re.sub(r"[^a-z0-9]", "", (value or "").lower())


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
    key = label_key(name)
    if key:
        for brand in db.scalars(select(Brand)):
            if label_key(brand.name) == key:
                return brand
    suffix = _phone_suffix(number)
    if suffix:
        for brand in db.scalars(select(Brand)):
            if _phone_suffix(brand.phone_number) == suffix:
                return brand
    return None


def find_queue(db: Session, name: str | None) -> Queue | None:
    key = label_key(name)
    if not key:
        return None
    for queue in db.scalars(select(Queue)):
        if label_key(queue.name) == key:
            return queue
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
    queue_id: int | None = None
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
    if filters.queue_id:
        query = query.where(Call.queue_id == filters.queue_id)
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


_STAT_COLUMNS = (Call.direction, Call.status, Call.booking_id, Call.duration_seconds, Call.wait_seconds)


def _average(values: list[int]) -> int:
    return round(sum(values) / len(values)) if values else 0


def _summarize(rows) -> dict[str, int]:
    answered = [r for r in rows if r.status in ANSWERED_CALL_STATUSES]
    finished = sum(r.status not in ACTIVE_CALL_STATUSES for r in rows)
    waits = [r.wait_seconds for r in rows if r.direction == "inbound" and r.wait_seconds is not None]
    return {
        "total_calls": len(rows),
        "inbound_calls": sum(r.direction == "inbound" for r in rows),
        "outbound_calls": sum(r.direction == "outbound" for r in rows),
        "answered": len(answered),
        "missed": sum(r.status in {"missed", "rejected"} for r in rows),
        "failed": sum(r.status == "failed" for r in rows),
        "in_progress": len(rows) - finished,
        "bookings": sum(bool(r.booking_id) for r in rows),
        "answer_rate": round(100 * sum(r.status not in ACTIVE_CALL_STATUSES for r in answered) / finished) if finished else 0,
        # Talk time of answered calls.
        "average_duration_seconds": _average([r.duration_seconds for r in answered if r.duration_seconds]),
        # Average speed of answer: wait of answered inbound calls. Max includes abandoned calls.
        "average_wait_seconds": _average(
            [r.wait_seconds for r in answered if r.direction == "inbound" and r.wait_seconds is not None]
        ),
        "max_wait_seconds": max(waits, default=0),
    }


def compute_stats(db: Session, filters: CallFilters) -> dict[str, int]:
    return _summarize(db.execute(_apply_filters(select(*_STAT_COLUMNS), filters)).all())


def compute_breakdown(db: Session, filters: CallFilters, by: str) -> list[dict]:
    """Per-queue (inbound only) or per-brand report rows, busiest first."""
    if by == "queue":
        filters = replace(filters, direction="inbound")
        key_col, name_col, fallback = Call.queue_id, Call.queue_name, "No queue"
        queues = {q.id: q for q in db.scalars(select(Queue).options(selectinload(Queue.brand)))}
    else:
        key_col, name_col, fallback = Call.brand_id, Call.brand_name, "No brand"
        queues = {}
    rows = db.execute(_apply_filters(select(key_col.label("key"), name_col.label("name"), *_STAT_COLUMNS), filters)).all()

    groups: dict[tuple, list] = {}
    for row in rows:
        # Calls without an id are grouped by the label they arrived with (e.g. an unknown X-Brand).
        groups.setdefault((row.key, None if row.key else row.name), []).append(row)

    report = []
    for (key, name), group in groups.items():
        queue = queues.get(key)
        report.append({
            "id": key,
            "name": queue.name if queue else (group[0].name if key else name) or fallback,
            "brand_name": queue.brand_name if queue else None,
            "department": queue.department if queue else None,
            **_summarize(group),
        })
    report.sort(key=lambda r: (-r["total_calls"], r["name"].lower()))
    return report


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
    if call.direction == "inbound" and call.wait_seconds is None:
        # Caller's wait: from entering the queue (or the INVITE reaching us) until answer or hang-up.
        until = call.answered_at or (call.ended_at if call.status in TERMINAL_CALL_STATUSES else None)
        if until:
            since = call.queue_entered_at or call.started_at
            call.wait_seconds = max(0, int((until - since).total_seconds()))


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


def _create_queue(db: Session, name: str, brand: Brand | None) -> Queue:
    """First call from a queue the CRM doesn't know yet: remember it (edit it via PATCH /api/queues/{id})."""
    queue = Queue(name=name.strip(), brand_id=brand.id if brand else None)
    db.add(queue)
    db.flush()
    logger.info("New queue %r registered from an incoming call (brand: %s)", queue.name, brand.name if brand else "unknown")
    return queue


def create_call(db: Session, payload: CallCreate) -> Call:
    if payload.customer_id and not db.get(Customer, payload.customer_id):
        raise HTTPException(status_code=404, detail="Customer not found")
    data = payload.model_dump()
    data["started_at"] = naive_utc(data["started_at"]) or utcnow()
    data["queue_entered_at"] = naive_utc(data["queue_entered_at"])
    call = Call(**data)
    _link_customer(db, call)

    # Brand: explicit id > X-Brand label > the queue's brand > called DID.
    brand = resolve_brand(db, brand_id=payload.brand_id, name=payload.brand_name)
    queue = find_queue(db, payload.queue_name)
    if brand is None and queue and queue.brand_id:
        brand = db.get(Brand, queue.brand_id)
    if brand is None:
        brand = resolve_brand(db, number=payload.brand_number)
    if queue is None and label_key(payload.queue_name):
        queue = _create_queue(db, payload.queue_name, brand)
    _link_brand(db, call, brand)
    if queue:
        call.queue_id = queue.id
        call.queue_name = queue.name
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
