"""Seed demo data: 6 brands, 10 customers, 10 inbound calls, 10 outbound calls, 5 bookings.

Usage (from backend/):
    python -m app.seed            # create tables; seed only if the database is empty
    python -m app.seed --reset    # drop everything and re-seed
"""

from __future__ import annotations

import argparse
import random
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .database import Base, SessionLocal, engine, init_db
from .models import Booking, Brand, Call, Customer, booking_reference, utcnow

# Fake DIDs: replace with the real numbers via PATCH /api/brands/{id}.
BRANDS = [
    ("City Doctor", "+97142000101"),
    ("DripHub", "+97142000102"),
    ("ProPeptides", "+97142000103"),
    ("PhysioHub", "+97142000104"),
    ("Girls Formula", "+97142000105"),
    ("Guys Formula", "+97142000106"),
]

SERVICES = {
    "City Doctor": "Doctor Consultation",
    "DripHub": "IV Drip Therapy",
    "ProPeptides": "Peptide Therapy Consultation",
    "PhysioHub": "Physiotherapy Session",
    "Girls Formula": "Women's Health Consultation",
    "Guys Formula": "Men's Health Consultation",
}

CUSTOMERS = [
    ("John Doe", "+971501234567", "john.doe@example.com", "Prefers morning appointments."),
    ("Sarah Ahmed", "+971502345678", "sarah.ahmed@example.com", None),
    ("Mohammed Ali", "+971503456789", None, "Arabic speaker."),
    ("Emily Carter", "+971504567890", "emily.carter@example.com", None),
    ("Fatima Hassan", "+971505678901", None, None),
    ("David Miller", "+971506789012", "david.miller@example.com", "Insurance: Daman."),
    ("Aisha Khan", "+971507890123", "aisha.khan@example.com", None),
    ("Omar Farouk", "+971508901234", None, None),
    ("Priya Sharma", "+971509012345", "priya.sharma@example.com", None),
    ("Lucas Martin", "+971551122334", None, None),
]

# (customer, brand, status, outcome, handled_by_ai, hours_ago)
INBOUND = [
    (0, 0, "completed", "booked", True, 2), (1, 1, "completed", "inquiry", True, 5),
    (2, 3, "completed", "booked", False, 9), (3, 4, "missed", None, False, 20),
    (4, 0, "transferred", "transferred", True, 28), (5, 5, "completed", "callback", False, 36),
    (6, 2, "completed", "booked", True, 50), (7, 1, "rejected", None, False, 70),
    (8, 4, "completed", "interested", True, 96), (9, 3, "failed", "failed", False, 130),
]

# (customer, brand, purpose, status, outcome, hours_ago)
OUTBOUND = [
    (1, 0, "Appointment Reminder", "completed", "booked", 1), (3, 3, "Booking Follow Up", "completed", "booked", 4),
    (5, 0, "Follow Up", "completed", "completed", 8), (7, 2, "Lead Qualification", "completed", "interested", 18),
    (9, 1, "Campaign", "completed", "not_interested", 26), (0, 4, "General Inquiry", "completed", "inquiry", 40),
    (2, 5, "Follow Up", "completed", "callback", 55), (4, 0, "Appointment Reminder", "missed", None, 74),
    (6, 1, "Campaign", "rejected", None, 100), (8, 2, "Lead Qualification", "failed", "failed", 140),
]

SLOTS = ["09:00", "10:30", "14:00", "16:30"]

INBOUND_SCRIPTS = {
    "booked": ("Hi, I'd like to book a {service}.", "Booked a {service} ({ref})."),
    "inquiry": ("Hi, what are your opening hours and prices?", "Asked about opening hours and pricing."),
    "transferred": ("I have a billing question about my invoice.", "Billing question; transferred to patient services."),
    "callback": ("I'm driving, can you call me back after 5pm?", "Requested a callback after 5pm."),
    "interested": ("Do you have any offers this month?", "Interested in current offers; details sent by WhatsApp."),
}

OUTBOUND_SCRIPTS = {
    "booked": ("Yes, please confirm the booking.", "Customer confirmed the {service} ({ref})."),
    "completed": ("All good, thank you for checking.", "Follow-up completed; customer is doing well."),
    "interested": ("That sounds interesting, send me details.", "Customer is interested; details to be sent."),
    "not_interested": ("No thanks, not right now.", "Customer not interested at this time."),
    "inquiry": ("How much does it cost?", "Customer asked about pricing."),
    "callback": ("I'm in a meeting, call me tomorrow.", "Callback requested for tomorrow morning."),
}


def _transcript(agent_open: str, customer_line: str, agent_close: str) -> str:
    return f"AI: {agent_open}\nCustomer: {customer_line}\nAI: {agent_close}\nCustomer: Thank you, bye."


def _future_day(offset: int) -> date:
    day = date.today() + timedelta(days=offset)
    return day + timedelta(days=1) if day.weekday() == 6 else day


def seed(db: Session) -> bool:
    """Insert demo data. Returns False (and does nothing) when brands already exist."""
    if db.scalar(select(func.count(Brand.id))):
        return False

    rng = random.Random(7)
    now = utcnow()
    brands = [Brand(name=name, phone_number=number, active=True) for name, number in BRANDS]
    customers = [
        Customer(name=n, phone=p, email=e, notes=notes, created_at=now - timedelta(days=40 - i))
        for i, (n, p, e, notes) in enumerate(CUSTOMERS)
    ]
    db.add_all(brands + customers)
    db.flush()

    booking_count = 0

    def add_call(direction: str, customer: Customer, brand: Brand, status: str, outcome: str | None,
                 hours_ago: float, n: int, ai: bool, purpose: str | None = None) -> Call:
        started = now - timedelta(hours=hours_ago, minutes=rng.randint(0, 50))
        answered = status in {"completed", "transferred"}
        ring = rng.randint(4, 15)
        duration = rng.randint(45, 300) if answered else 0
        call = Call(
            direction=direction, customer_id=customer.id, customer_name=customer.name,
            customer_phone=customer.phone, brand_id=brand.id, brand_name=brand.name,
            brand_number=brand.phone_number, sip_call_id=f"seed-{direction[:2]}-{n:03d}@pbx",
            sip_extension=None if ai else rng.choice(["9001", "9002"]),
            elevenlabs_conversation_id=f"conv_seed_{direction[:2]}_{n:03d}" if ai and answered else None,
            status=status, outcome=outcome, purpose=purpose, started_at=started,
            answered_at=started + timedelta(seconds=ring) if answered else None,
            ended_at=started + timedelta(seconds=ring + duration), duration_seconds=duration,
            is_mock=True, created_at=started, updated_at=started,
        )
        db.add(call)
        db.flush()
        return call

    def add_booking(call: Call, customer: Customer, brand: Brand) -> str:
        nonlocal booking_count
        booking_count += 1
        booking = Booking(
            customer_id=customer.id, call_id=call.id, service=SERVICES[brand.name],
            appointment_date=_future_day(booking_count), appointment_time=SLOTS[booking_count % len(SLOTS)],
            status="confirmed", notes=f"Booked during {call.direction} call", created_at=call.started_at,
        )
        db.add(booking)
        db.flush()
        call.booking_id = booking.id
        return booking_reference(booking.id) or ""

    for n, (ci, bi, status, outcome, ai, hours) in enumerate(INBOUND, start=1):
        customer, brand = customers[ci], brands[bi]
        call = add_call("inbound", customer, brand, status, outcome, hours, n, ai)
        if status == "missed":
            call.notes = "Caller hung up before the call was answered."
        elif status == "rejected":
            call.notes = "Rejected by agent (busy)."
        elif status == "failed":
            call.notes = "WebRTC media failure (ICE failed)."
        elif outcome in INBOUND_SCRIPTS:
            ref = add_booking(call, customer, brand) if outcome == "booked" else ""
            line, summary = INBOUND_SCRIPTS[outcome]
            service = SERVICES[brand.name].lower()
            if ai:
                call.transcript = _transcript(
                    f"Thank you for calling {brand.name}. How can I help you today?",
                    line.format(service=service),
                    f"Done. {summary.format(service=service, ref=ref)}",
                )
                call.summary = f"{customer.name}: " + summary.format(service=service, ref=ref)
            else:
                call.notes = summary.format(service=service, ref=ref)

    for n, (ci, bi, purpose, status, outcome, hours) in enumerate(OUTBOUND, start=1):
        customer, brand = customers[ci], brands[bi]
        call = add_call("outbound", customer, brand, status, outcome, hours, n, ai=False, purpose=purpose)
        if status == "missed":
            call.notes = "No answer (480 Temporarily Unavailable)."
        elif status == "rejected":
            call.notes = "Customer declined the call (486 Busy Here)."
        elif status == "failed":
            call.notes = "Call failed: 503 Service Unavailable from PBX."
        else:
            ref = add_booking(call, customer, brand) if outcome == "booked" else ""
            line, summary = OUTBOUND_SCRIPTS[outcome]
            call.notes = summary.format(service=SERVICES[brand.name].lower(), ref=ref)

    db.commit()
    return True


def counts(db: Session) -> dict[str, int]:
    return {m.__tablename__: db.scalar(select(func.count()).select_from(m)) or 0 for m in (Brand, Customer, Call, Booking)}


def reset_and_seed() -> dict[str, int]:
    Base.metadata.drop_all(bind=engine)
    init_db()
    with SessionLocal() as db:
        seed(db)
        return counts(db)


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the Voice CRM database with demo data.")
    parser.add_argument("--reset", action="store_true", help="drop all tables and re-seed")
    args = parser.parse_args()
    if args.reset:
        print("Database reset and seeded:", reset_and_seed())
        return
    init_db()
    with SessionLocal() as db:
        created = seed(db)
        print("Seeded demo data:" if created else "Database already has data (use --reset to re-seed):", counts(db))


if __name__ == "__main__":
    main()
