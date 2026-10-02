"""Mock calling system for local testing (MOCK_CALLING_SYSTEM=true / CALLING_SYSTEM_MODE=mock).

Simulated calls travel the same path as real ones: the simulator emits the
payloads a real system would send and runs them through
``normalize_call_event`` -> ``apply_call_event``.

* Outbound simulations emit generic internal-calling-system events
  (``call.ringing``, ``call.answered``, ``call.completed`` ...).
* Inbound simulations emit ElevenLabs ``post_call_transcription`` payloads.
"""

from __future__ import annotations

import asyncio
import logging
import math
import random
import struct
import uuid
import wave
from collections.abc import Coroutine
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import SessionLocal
from ..models import ACTIVE_CALL_STATUSES, Call, CallStatus, Customer, booking_reference, utcnow
from . import booking_service
from .call_service import apply_call_event

logger = logging.getLogger(__name__)

DEMO_RECORDING_NAME = "demo-call.wav"
DEMO_RECORDING_URL = f"/recordings/{DEMO_RECORDING_NAME}"

BRAND_SERVICES = {
    "City Doctor": "Doctor Consultation",
    "DripHub": "IV Drip Therapy",
    "ProPeptides": "Peptide Therapy Consultation",
    "PhysioHub": "Physiotherapy Session",
    "Girls Formula": "Women's Health Consultation",
    "Guys Formula": "Men's Health Consultation",
}

# Outcome weights per outbound purpose (for answered calls).
PURPOSE_OUTCOMES: dict[str, list[tuple[str, int]]] = {
    "Appointment Reminder": [("booked", 5), ("completed", 3), ("callback", 2)],
    "Follow Up": [("completed", 4), ("interested", 3), ("callback", 2)],
    "Lead Qualification": [("interested", 4), ("not_interested", 3), ("callback", 2)],
    "Booking Follow Up": [("booked", 5), ("callback", 2), ("not_interested", 1)],
    "General Inquiry": [("inquiry", 5), ("completed", 2)],
    "Campaign": [("interested", 4), ("not_interested", 4), ("booked", 1)],
    "Custom": [("completed", 5), ("callback", 1)],
}

INBOUND_SCENARIOS: list[tuple[str, int]] = [
    ("booked", 5), ("completed", 5), ("transferred", 1), ("missed", 1),
]

_background_tasks: set[asyncio.Task] = set()


# --------------------------------------------------------------------------- task helpers
def spawn(coro: Coroutine[Any, Any, Any]) -> None:
    """Run a coroutine in the background, keeping a reference so it isn't GC'd."""
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


async def cancel_background_tasks() -> None:
    for task in list(_background_tasks):
        task.cancel()
    if _background_tasks:
        await asyncio.gather(*_background_tasks, return_exceptions=True)


def new_mock_ids() -> tuple[str, str]:
    """(external_call_id, conversation_id)"""
    return f"mock-{uuid.uuid4().hex[:12]}", f"mock_conv_{uuid.uuid4().hex[:16]}"


def _weighted(options: list[tuple[str, int]]) -> str:
    values, weights = zip(*options)
    return random.choices(values, weights=weights, k=1)[0]


def _first_name(name: str | None) -> str:
    return (name or "there").split()[0]


def _human_date(value: date) -> str:
    return value.strftime("%A %d %B")


def _iso(value: datetime) -> str:
    return value.replace(tzinfo=timezone.utc).isoformat()


# --------------------------------------------------------------------------- scripts
@dataclass
class MockConversation:
    turns: list[dict[str, str]]
    summary: str
    outcome: str
    status: str
    duration_seconds: int


def _turns(*pairs: tuple[str, str]) -> list[dict[str, str]]:
    return [{"role": role, "message": message} for role, message in pairs]


@dataclass
class BookingInfo:
    reference: str
    day: date
    time: str
    service: str


def build_inbound_conversation(
    *, customer_name: str, brand: str, agent_name: str, scenario: str, booking: BookingInfo | None
) -> MockConversation:
    first = _first_name(customer_name)
    service = BRAND_SERVICES.get(brand, "Consultation")
    hello = ("agent", f"Thank you for calling {brand}, this is {agent_name}. How can I help you today?")

    if scenario == "booked" and booking:
        turns = _turns(
            hello,
            ("user", f"Hi, I'd like to book a {service.lower()}, please."),
            ("agent", f"Of course. Am I speaking with {customer_name}?"),
            ("user", "Yes, that's me."),
            ("agent", f"Thanks {first}. I have {_human_date(booking.day)} at {booking.time}. Does that work?"),
            ("user", "Yes, that's perfect."),
            ("agent", f"You're booked for a {service} on {_human_date(booking.day)} at {booking.time}. "
                      f"Your reference is {booking.reference}."),
            ("user", "Thank you so much."),
            ("agent", f"You're welcome, {first}. Have a lovely day!"),
        )
        summary = (f"{customer_name} called {brand} to book a {service}. Booked {_human_date(booking.day)} "
                   f"at {booking.time} (ref {booking.reference}).")
        return MockConversation(turns, summary, "booked", "completed", random.randint(150, 290))

    if scenario == "transferred":
        turns = _turns(
            hello,
            ("user", "Hi, I have a question about my invoice and insurance claim."),
            ("agent", "Billing and insurance questions are handled by our patient services team."),
            ("user", "Can I speak to someone there?"),
            ("agent", f"Of course, {first}. Transferring you to a team member now, please hold."),
        )
        summary = f"{customer_name} asked about billing/insurance. Call transferred to patient services."
        return MockConversation(turns, summary, "transferred", "transferred", random.randint(60, 120))

    if scenario == "callback" or (scenario == "completed" and random.random() < 0.35):
        turns = _turns(
            hello,
            ("user", f"Hi, I'm interested in a {service.lower()} but I'm driving right now."),
            ("agent", "No problem. Shall we call you back later today?"),
            ("user", "Yes, after 5 pm please."),
            ("agent", f"Noted, {first}. The {brand} team will call you after 5 pm. Drive safely!"),
        )
        summary = f"{customer_name} is interested in a {service} but was busy. Callback requested after 5 pm."
        return MockConversation(turns, summary, "callback", "completed", random.randint(45, 110))

    turns = _turns(
        hello,
        ("user", f"Hi, what are your opening hours and how much is a {service.lower()}?"),
        ("agent", f"We're open daily from 8 am to 10 pm. A {service} starts from AED 350."),
        ("user", "Do you accept insurance?"),
        ("agent", "Yes, we work with most major insurers. Please bring your insurance card."),
        ("user", "Great, I'll call back to book. Thanks."),
        ("agent", f"You're welcome, {first}. Call any time."),
    )
    summary = f"{customer_name} asked about opening hours, {service} pricing and insurance. No booking yet."
    return MockConversation(turns, summary, "inquiry", "completed", random.randint(80, 200))


def build_outbound_conversation(
    *, customer_name: str, brand: str, agent_name: str, purpose: str, outcome: str,
    custom_instructions: str | None, booking: BookingInfo | None,
) -> MockConversation:
    first = _first_name(customer_name)
    service = BRAND_SERVICES.get(brand, "Consultation")

    if purpose == "Appointment Reminder" and outcome == "booked" and booking:
        turns = _turns(
            ("agent", f"Hello, this is {brand}. I am calling regarding your appointment."),
            ("user", "Yes."),
            ("agent", f"Would you like to confirm your booking for {_human_date(booking.day)} at {booking.time}?"),
            ("user", "Yes."),
            ("agent", f"Thank you {first}, your booking {booking.reference} is confirmed. See you soon!"),
        )
        summary = (f"Appointment reminder for {customer_name}. Customer confirmed the {service} on "
                   f"{_human_date(booking.day)} at {booking.time} (ref {booking.reference}).")
        return MockConversation(turns, summary, "booked", "completed", random.randint(40, 90))

    opener = ("agent", f"Hello, this is {agent_name} from {brand}. Am I speaking with {customer_name}?")
    reason = {
        "Appointment Reminder": f"I'm calling to remind you about your upcoming {service.lower()}.",
        "Follow Up": f"I'm following up on your recent visit to {brand}. How are you feeling?",
        "Lead Qualification": f"You showed interest in our {service.lower()}. What are you looking for?",
        "Booking Follow Up": f"You started booking a {service.lower()} but didn't finish. Shall I complete it?",
        "General Inquiry": f"I'm calling about your recent inquiry with {brand}.",
        "Campaign": f"This month we have 20% off a {service.lower()}. Would that interest you?",
        "Custom": custom_instructions or f"I'm calling with a quick update from {brand}.",
    }.get(purpose, f"I'm calling from {brand}.")

    closings: dict[str, tuple[list[tuple[str, str]], str]] = {
        "completed": (
            [("user", "Yes, all good, thanks for checking."),
             ("agent", f"Wonderful. Thanks for your time, {first}. Have a great day!")],
            f"{purpose} call completed. {customer_name} confirmed everything is fine.",
        ),
        "interested": (
            [("user", "That sounds interesting. Can you send me details?"),
             ("agent", f"Of course, {first}. I'll send them by WhatsApp and email right away.")],
            f"{customer_name} is interested; details to be sent by WhatsApp and email.",
        ),
        "not_interested": (
            [("user", "Thanks, but I'm not interested right now."),
             ("agent", f"No problem, {first}. Thank you for your time.")],
            f"{customer_name} is not interested at this time.",
        ),
        "callback": (
            [("user", "I'm in a meeting, can you call me tomorrow morning?"),
             ("agent", "Of course, I'll schedule a callback for tomorrow morning.")],
            f"{customer_name} was busy and asked for a callback tomorrow morning.",
        ),
        "inquiry": (
            [("user", "Yes, what's the price and do I need a referral?"),
             ("agent", f"It starts from AED 350 and no referral is needed. I'll text you the price list, {first}.")],
            f"{customer_name} asked about pricing and referrals; price list to be sent by SMS.",
        ),
    }

    if outcome == "booked" and booking:
        closing = [
            ("user", "Yes, let's book it."),
            ("agent", f"I have {_human_date(booking.day)} at {booking.time}. Shall I confirm it?"),
            ("user", "Yes please."),
            ("agent", f"Done, reference {booking.reference}. See you then, {first}!"),
        ]
        summary = (f"{purpose} call. {customer_name} booked a {service} on {_human_date(booking.day)} "
                   f"at {booking.time} (ref {booking.reference}).")
    else:
        outcome = outcome if outcome in closings else "completed"
        closing, summary = closings[outcome]

    turns = _turns(opener, ("user", "Yes, speaking."), ("agent", reason), *closing)
    return MockConversation(turns, summary, outcome, "completed", random.randint(40, 240))


# --------------------------------------------------------------------------- DB helpers
def _emit(payload: dict[str, Any]) -> Call | None:
    """Send a payload through the real normalization + update pipeline."""
    from ..adapters.calling_system_adapter import normalize_call_event  # local import: avoids a cycle

    with SessionLocal() as db:
        return apply_call_event(db, normalize_call_event(payload), raw_payload=payload)


def _load_active(db: Session, call_id: int) -> Call | None:
    call = db.get(Call, call_id)
    return call if call and call.status in ACTIVE_CALL_STATUSES else None


def _ids(call_id: int) -> dict[str, Any]:
    with SessionLocal() as db:
        call = db.get(Call, call_id)
        if not call:
            return {"crm_call_id": call_id}
        return {
            "crm_call_id": call_id,
            "call_id": call.external_call_id,
            "conversation_id": call.elevenlabs_conversation_id,
        }


def _book_for_call(db: Session, call: Call) -> BookingInfo | None:
    customer = db.get(Customer, call.customer_id) if call.customer_id else None
    if not customer:
        return None
    service = BRAND_SERVICES.get(call.brand_name, "Consultation")
    for offset in range(1, 21):
        day = date.today() + timedelta(days=offset)
        if day.weekday() == 6:  # closed on Sundays
            continue
        slots = booking_service.get_available_slots(db, day, service)
        if slots:
            slot = random.choice(slots)
            booking = booking_service.create_booking(
                db, customer=customer, service=service, appointment_date=day, appointment_time=slot,
                notes=f"Booked by {call.agent_name} during {call.direction} call", call=call,
            )
            return BookingInfo(booking_reference(booking.id) or "", day, slot, service)
    return None


def _mark_failed(call_id: int, message: str) -> None:
    with SessionLocal() as db:
        call = _load_active(db, call_id)
        if call:
            call.status = CallStatus.failed.value
            call.outcome = "failed"
            call.error_message = message
            call.ended_at = utcnow()
            call.duration_seconds = call.duration_seconds or 0
            db.commit()


def recover_interrupted_mock_calls(db: Session) -> int:
    """Mock calls left 'in progress' by a server restart can never finish; close them."""
    stuck = list(db.scalars(select(Call).where(Call.is_mock.is_(True), Call.status.in_(ACTIVE_CALL_STATUSES))))
    for call in stuck:
        call.status = CallStatus.failed.value
        call.outcome = "failed"
        call.ended_at = utcnow()
        call.duration_seconds = call.duration_seconds or 0
        call.error_message = "Mock simulation interrupted by a server restart."
    if stuck:
        db.commit()
    return len(stuck)


# --------------------------------------------------------------------------- outbound
async def simulate_outbound_call(call_id: int, scenario: str | None = None) -> None:
    """queued -> calling -> ringing -> answered -> completed (or no_answer / failed)."""
    step = get_settings().mock_step_seconds
    try:
        if scenario is None:
            roll = random.random()
            scenario = "no_answer" if roll < 0.10 else "failed" if roll < 0.15 else None

        await asyncio.sleep(step / 2)
        _emit({"event": "call.started", "status": "calling", **_ids(call_id)})
        await asyncio.sleep(step)
        _emit({"event": "call.ringing", **_ids(call_id)})
        await asyncio.sleep(step)

        if scenario == "no_answer":
            _emit({"event": "call.no_answer", "duration_seconds": 0, "outcome": "callback",
                   "summary": "No answer. A follow-up attempt is recommended.",
                   "error_message": "Customer did not answer (simulated).", **_ids(call_id)})
            return
        if scenario == "failed":
            _emit({"event": "call.failed", "duration_seconds": 0,
                   "summary": "The call could not be connected.",
                   "error_message": "Carrier rejected the call: SIP 503 Service Unavailable (simulated).",
                   **_ids(call_id)})
            return

        _emit({"event": "call.answered", **_ids(call_id)})
        await asyncio.sleep(step * 2)

        with SessionLocal() as db:
            call = _load_active(db, call_id)
            if not call:
                return
            purpose = call.purpose or "Custom"
            outcome = "booked" if scenario == "booked" else (
                "completed" if scenario == "completed" else _weighted(PURPOSE_OUTCOMES.get(purpose, PURPOSE_OUTCOMES["Custom"]))
            )
            booking = _book_for_call(db, call) if outcome == "booked" else None
            if outcome == "booked" and not booking:
                outcome = "callback"
            convo = build_outbound_conversation(
                customer_name=call.customer_name or "there", brand=call.brand_name, agent_name=call.agent_name,
                purpose=purpose, outcome=outcome, custom_instructions=call.custom_instructions, booking=booking,
            )
            ended = utcnow()
            started = ended - timedelta(seconds=convo.duration_seconds)

        _emit({
            "event": "call.completed",
            **_ids(call_id),
            "started_at": _iso(started),
            "ended_at": _iso(ended),
            "duration_seconds": convo.duration_seconds,
            "transcript": convo.turns,
            "summary": convo.summary,
            "outcome": convo.outcome,
        })
        _emit({"event": "call.recording", "recording_url": DEMO_RECORDING_URL, **_ids(call_id)})
    except asyncio.CancelledError:
        raise
    except Exception:  # noqa: BLE001 - background task must never die silently
        logger.exception("Mock outbound simulation failed for call %s", call_id)
        _mark_failed(call_id, "Mock simulation error (see server logs).")


# --------------------------------------------------------------------------- inbound
def pick_inbound_scenario() -> str:
    return _weighted(INBOUND_SCENARIOS)


async def simulate_inbound_call(call_id: int, scenario: str, instant: bool = False) -> None:
    """ringing -> answered -> completed, emitting ElevenLabs-style payloads."""
    step = 0 if instant else get_settings().mock_step_seconds
    try:
        await asyncio.sleep(step)
        if scenario == "missed":
            _emit({"event": "call.missed", "duration_seconds": 0, "outcome": "callback",
                   "summary": "Caller hung up before the AI agent answered. Call back recommended.",
                   "error_message": "Missed call (simulated).", **_ids(call_id)})
            return
        if scenario == "failed":
            _emit({"event": "call.failed", "duration_seconds": 0,
                   "error_message": "SIP trunk error: 486 Busy Here (simulated).", **_ids(call_id)})
            return

        _emit({"event": "call.answered", **_ids(call_id)})
        if scenario == "answered":
            return  # stays live; finish it with a webhook or PATCH /api/calls/{id}
        await asyncio.sleep(step * 2)

        with SessionLocal() as db:
            call = _load_active(db, call_id)
            if not call:
                return
            booking = _book_for_call(db, call) if scenario == "booked" else None
            convo = build_inbound_conversation(
                customer_name=call.customer_name or "there", brand=call.brand_name,
                agent_name=call.agent_name, scenario=scenario if (scenario != "booked" or booking) else "completed",
                booking=booking,
            )
            ended = utcnow()
            started = ended - timedelta(seconds=convo.duration_seconds)
            payload = {
                "type": "post_call_transcription",
                "event_timestamp": int(ended.replace(tzinfo=timezone.utc).timestamp()),
                "data": {
                    "agent_id": call.agent_id or "mock_agent",
                    "conversation_id": call.elevenlabs_conversation_id,
                    "status": "done",
                    "transcript": convo.turns,
                    "metadata": {
                        "start_time_unix_secs": int(started.replace(tzinfo=timezone.utc).timestamp()),
                        "call_duration_secs": convo.duration_seconds,
                        "termination_reason": "Call transferred" if convo.status == "transferred" else "end_call tool",
                        "phone_call": {
                            "direction": "inbound",
                            "external_number": call.customer_phone,
                            "agent_number": call.brand_number,
                            "type": "sip_trunking",
                            "call_sid": call.external_call_id,
                        },
                    },
                    "analysis": {
                        "call_successful": "success",
                        "transcript_summary": convo.summary,
                        "data_collection_results": {"outcome": {"value": convo.outcome}},
                    },
                    "conversation_initiation_client_data": {"dynamic_variables": {}},
                },
            }

        _emit(payload)
        _emit({"event": "call.recording", "recording_url": DEMO_RECORDING_URL, **_ids(call_id)})
    except asyncio.CancelledError:
        raise
    except Exception:  # noqa: BLE001
        logger.exception("Mock inbound simulation failed for call %s", call_id)
        _mark_failed(call_id, "Mock simulation error (see server logs).")


# --------------------------------------------------------------------------- demo audio
def ensure_demo_recording() -> None:
    """Write a short synthetic WAV so the 'Play' buttons work in mock mode."""
    settings = get_settings()
    path = settings.recordings_dir / DEMO_RECORDING_NAME
    if path.exists():
        return
    settings.recordings_dir.mkdir(parents=True, exist_ok=True)
    rate = 8000
    frames = bytearray()
    pattern = [(440, 0.6), (0, 0.25), (330, 0.8), (0, 0.3), (523, 0.5), (0, 0.25), (392, 0.9), (0, 0.4)] * 2
    for freq, seconds in pattern:
        total = int(rate * seconds)
        for i in range(total):
            if freq == 0:
                sample = 0.0
            else:
                envelope = min(1.0, i / 400, (total - i) / 400)
                sample = 0.25 * envelope * math.sin(2 * math.pi * freq * i / rate)
            frames += struct.pack("<h", int(sample * 32767))
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(bytes(frames))
