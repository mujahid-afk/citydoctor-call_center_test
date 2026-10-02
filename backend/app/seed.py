"""Seed demo data: 6 brands, 10 customers, 10 inbound calls, 10 outbound calls, 5 bookings.

Usage (from backend/):
    python -m app.seed            # seed only if the database is empty
    python -m app.seed --reset    # drop everything and re-seed
"""

from __future__ import annotations

import argparse
import random
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .database import Base, SessionLocal, engine, init_db
from .models import Booking, BookingStatus, Brand, Call, Customer, booking_reference, utcnow
from .services.mock_simulator import (
    BRAND_SERVICES,
    DEMO_RECORDING_URL,
    BookingInfo,
    build_inbound_conversation,
    build_outbound_conversation,
)
from .adapters.call_events import format_transcript

BRANDS = [
    ("City Doctor", "+97142000101", "City Doctor AI"),
    ("DripHub", "+97142000102", "DripHub AI"),
    ("ProPeptides", "+97142000103", "ProPeptides AI"),
    ("PhysioHub", "+97142000104", "PhysioHub AI"),
    ("Girls Formula", "+97142000105", "Girls Formula AI"),
    ("Guys Formula", "+97142000106", "Guys Formula AI"),
]

CUSTOMERS = [
    ("John Doe", "+971501234567", "john.doe@example.com"),
    ("Sarah Ahmed", "+971502345678", "sarah.ahmed@example.com"),
    ("Mohammed Ali", "+971503456789", None),
    ("Emily Carter", "+971504567890", "emily.carter@example.com"),
    ("Fatima Hassan", "+971505678901", None),
    ("David Miller", "+971506789012", "david.miller@example.com"),
    ("Aisha Khan", "+971507890123", "aisha.khan@example.com"),
    ("Omar Farouk", "+971508901234", None),
    ("Priya Sharma", "+971509012345", "priya.sharma@example.com"),
    ("Lucas Martin", "+971551122334", None),
]

# (customer index, brand index, scenario, hours ago)
INBOUND = [
    (0, 0, "booked", 2), (1, 1, "inquiry", 5), (2, 3, "booked", 9), (3, 4, "missed", 20),
    (4, 0, "transferred", 28), (5, 5, "callback", 36), (6, 2, "booked", 50), (7, 1, "missed", 70),
    (8, 4, "inquiry", 96), (9, 3, "failed", 130),
]

# (customer index, brand index, purpose, outcome/status, hours ago)
OUTBOUND = [
    (1, 0, "Appointment Reminder", "booked", 1), (3, 3, "Booking Follow Up", "booked", 4),
    (5, 0, "Follow Up", "completed", 8), (7, 2, "Lead Qualification", "interested", 18),
    (9, 1, "Campaign", "not_interested", 26), (0, 4, "General Inquiry", "inquiry", 40),
    (2, 5, "Follow Up", "callback", 55), (4, 0, "Appointment Reminder", "no_answer", 74),
    (6, 1, "Campaign", "no_answer", 100), (8, 2, "Lead Qualification", "failed", 140),
]

SLOTS = ["09:00", "10:30", "14:00", "16:30"]


def reset_database() -> None:
    Base.metadata.drop_all(bind=engine)
    init_db()


def _future_day(offset: int) -> date:
    day = date.today() + timedelta(days=offset)
    return day + timedelta(days=1) if day.weekday() == 6 else day


def seed(db: Session) -> bool:
    """Insert demo data. Returns False (and does nothing) if data already exists."""
    if db.scalar(select(func.count(Brand.id))):
        return False

    rng = random.Random(42)
    now = utcnow()

    brands = [Brand(name=n, phone_number=p, agent_name=a, active=True) for n, p, a in BRANDS]
    customers = [
        Customer(name=n, phone=p, email=e, created_at=now - timedelta(days=30 - i))
        for i, (n, p, e) in enumerate(CUSTOMERS)
    ]
    db.add_all(brands + customers)
    db.flush()

    booking_offset = 1

    def make_booking(customer: Customer, brand: Brand, call: Call) -> BookingInfo:
        nonlocal booking_offset
        day = _future_day(booking_offset)
        slot = SLOTS[booking_offset % len(SLOTS)]
        booking_offset += 1
        service = BRAND_SERVICES[brand.name]
        booking = Booking(
            customer_id=customer.id, call_id=call.id, service=service, appointment_date=day,
            appointment_time=slot, status=BookingStatus.confirmed.value,
            notes=f"Booked by {brand.agent_name} during {call.direction} call",
            created_at=call.started_at,
        )
        db.add(booking)
        db.flush()
        call.booking_id = booking.id
        return BookingInfo(booking_reference(booking.id) or "", day, slot, service)

    def base_call(direction: str, customer: Customer, brand: Brand, hours_ago: float, n: int) -> Call:
        call = Call(
            direction=direction, customer_id=customer.id, customer_name=customer.name,
            customer_phone=customer.phone, brand_id=brand.id, brand_name=brand.name,
            brand_number=brand.phone_number, agent_name=brand.agent_name,
            started_at=now - timedelta(hours=hours_ago, minutes=rng.randint(0, 50)),
            external_call_id=f"seed-{direction[:2]}-{n:03d}",
            elevenlabs_conversation_id=f"seed_conv_{direction[:2]}_{n:03d}",
            is_mock=True, status="queued",
        )
        db.add(call)
        db.flush()
        return call

    def finish(call: Call, status: str, outcome: str | None, duration: int, transcript=None, summary=None,
               error: str | None = None) -> None:
        call.status = status
        call.outcome = outcome
        call.duration_seconds = duration
        call.ended_at = call.started_at + timedelta(seconds=duration)
        call.transcript = format_transcript(transcript) if transcript else None
        call.summary = summary
        call.error_message = error
        call.recording_url = DEMO_RECORDING_URL if duration > 0 else None
        call.created_at = call.updated_at = call.started_at

    for n, (ci, bi, scenario, hours) in enumerate(INBOUND, start=1):
        customer, brand = customers[ci], brands[bi]
        call = base_call("inbound", customer, brand, hours, n)
        if scenario == "missed":
            finish(call, "no_answer", "callback", 0, summary="Caller hung up before the AI agent answered.",
                   error="Missed call")
            continue
        if scenario == "failed":
            finish(call, "failed", "failed", 0, error="SIP trunk error: 486 Busy Here")
            continue
        booking = make_booking(customer, brand, call) if scenario == "booked" else None
        convo = build_inbound_conversation(
            customer_name=customer.name, brand=brand.name, agent_name=brand.agent_name,
            scenario=scenario, booking=booking,
        )
        finish(call, convo.status, convo.outcome, convo.duration_seconds, convo.turns, convo.summary)

    for n, (ci, bi, purpose, result, hours) in enumerate(OUTBOUND, start=1):
        customer, brand = customers[ci], brands[bi]
        call = base_call("outbound", customer, brand, hours, n)
        call.purpose = purpose
        if result == "no_answer":
            finish(call, "no_answer", "callback", 0, summary="No answer. A follow-up attempt is recommended.",
                   error="Customer did not answer")
            continue
        if result == "failed":
            finish(call, "failed", "failed", 0, summary="The call could not be connected.",
                   error="Carrier rejected the call: SIP 503 Service Unavailable")
            continue
        booking = make_booking(customer, brand, call) if result == "booked" else None
        convo = build_outbound_conversation(
            customer_name=customer.name, brand=brand.name, agent_name=brand.agent_name, purpose=purpose,
            outcome=result, custom_instructions=None, booking=booking,
        )
        finish(call, "completed", convo.outcome, convo.duration_seconds, convo.turns, convo.summary)

    db.commit()
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the Voice CRM database with demo data.")
    parser.add_argument("--reset", action="store_true", help="drop all tables and re-seed")
    args = parser.parse_args()

    if args.reset:
        reset_database()
    else:
        init_db()
    with SessionLocal() as db:
        created = seed(db)
        counts = {m.__tablename__: db.scalar(select(func.count()).select_from(m)) for m in (Brand, Customer, Call, Booking)}
    print("Seeded demo data." if created else "Database already has data (use --reset to re-seed).", counts)


if __name__ == "__main__":
    main()
