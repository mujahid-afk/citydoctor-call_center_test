"""Provider-neutral call event model + normalizer for the generic/internal event format.

Provider-specific payloads (ElevenLabs, the internal calling system, middleware)
are converted into ``NormalizedCallEvent`` before anything touches the database.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

VALID_STATUSES = {
    "queued", "calling", "ringing", "answered", "completed", "no_answer", "failed", "transferred",
}
VALID_OUTCOMES = {
    "booked", "inquiry", "interested", "not_interested", "callback", "transferred", "completed", "failed",
}

# External status vocabulary (FreePBX/Asterisk, Twilio-ish, ElevenLabs, ...) -> internal status.
STATUS_ALIASES = {
    "queued": "queued", "initiated": "queued", "pending": "queued", "created": "queued",
    "calling": "calling", "dialing": "calling", "originating": "calling", "started": "calling",
    "ringing": "ringing", "ring": "ringing", "alerting": "ringing",
    "answered": "answered", "in-progress": "answered", "in_progress": "answered", "up": "answered",
    "connected": "answered", "active": "answered",
    "completed": "completed", "complete": "completed", "ended": "completed", "hangup": "completed",
    "done": "completed", "finished": "completed",
    "no_answer": "no_answer", "no-answer": "no_answer", "noanswer": "no_answer", "busy": "no_answer",
    "missed": "no_answer", "unanswered": "no_answer",
    "failed": "failed", "error": "failed", "congestion": "failed", "canceled": "failed",
    "cancelled": "failed", "chanunavail": "failed", "rejected": "failed",
    "transferred": "transferred", "transfer": "transferred",
}

# Logical event name -> (event_type, implied status). None = status unchanged.
EVENT_ALIASES: dict[str, tuple[str, str | None]] = {
    "call.started": ("started", None),
    "call.ringing": ("ringing", "ringing"),
    "call.answered": ("answered", "answered"),
    "call.connected": ("answered", "answered"),
    "call.completed": ("completed", "completed"),
    "call.ended": ("completed", "completed"),
    "call.failed": ("failed", "failed"),
    "call.no_answer": ("no_answer", "no_answer"),
    "call.missed": ("no_answer", "no_answer"),
    "call.transferred": ("transferred", "transferred"),
    "call.transcript": ("transcript", None),
    "call.summary": ("summary", None),
    "call.recording": ("recording", None),
}


@dataclass
class NormalizedCallEvent:
    """Internal representation of a call event; only non-None fields are applied."""

    event_type: str  # started|ringing|answered|completed|failed|no_answer|transferred|transcript|summary|recording|unknown
    source: str = "generic"
    raw_type: str | None = None
    crm_call_id: int | None = None
    external_call_id: str | None = None
    conversation_id: str | None = None
    direction: str | None = None
    customer_phone: str | None = None
    customer_name: str | None = None
    brand_name: str | None = None
    brand_number: str | None = None
    agent_id: str | None = None
    agent_name: str | None = None
    status: str | None = None
    outcome: str | None = None
    purpose: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    duration_seconds: int | None = None
    transcript: str | None = None
    summary: str | None = None
    recording_url: str | None = None
    recording_audio: bytes | None = None
    has_provider_audio: bool = False
    error_message: str | None = None


# --------------------------------------------------------------------------- helpers
def utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def from_unix(value: Any) -> datetime | None:
    try:
        return datetime.fromtimestamp(float(value), tz=timezone.utc).replace(tzinfo=None)
    except (TypeError, ValueError, OSError):
        return None


def parse_datetime(value: Any) -> datetime | None:
    """Parse ISO strings or unix timestamps into naive UTC datetimes."""
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return from_unix(value)
    text = str(value).strip()
    if text.replace(".", "", 1).isdigit():
        return from_unix(text)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def to_int(value: Any) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def normalize_status(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return STATUS_ALIASES.get(str(value).strip().lower())


def normalize_outcome(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip().lower().replace(" ", "_").replace("-", "_")
    return text if text in VALID_OUTCOMES else None


def format_transcript(turns: Any) -> str | None:
    """Accept a string or a list of {role, message} turns; return 'AI: ...' / 'Customer: ...' lines."""
    if not turns:
        return None
    if isinstance(turns, str):
        return turns.strip() or None
    lines: list[str] = []
    for turn in turns:
        if not isinstance(turn, dict):
            continue
        message = str(turn.get("message") or turn.get("text") or "").strip()
        if not message:
            continue
        role = str(turn.get("role") or turn.get("speaker") or "").lower()
        speaker = "AI" if role in {"agent", "ai", "assistant", "bot"} else "Customer"
        lines.append(f"{speaker}: {message}")
    return "\n".join(lines) or None


def _first(data: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = data.get(key)
        if value not in (None, ""):
            return value
    return None


# --------------------------------------------------------------------------- generic normalizer
def normalize_generic_event(payload: dict[str, Any]) -> NormalizedCallEvent:
    """Normalize the internal/middleware event format.

    Expected (all fields optional except ``event``)::

        {
          "event": "call.completed",          # see EVENT_ALIASES
          "call_id": "1712345.67",            # external call ID (or external_call_id)
          "conversation_id": "conv_...",      # ElevenLabs conversation ID
          "crm_call_id": 42,                  # our ID, echoed back for outbound calls
          "direction": "inbound",
          "customer_phone": "+971...", "customer_name": "John",
          "brand": "City Doctor", "brand_number": "+971...",
          "agent_id": "...", "agent_name": "City Doctor AI",
          "status": "completed", "outcome": "booked", "purpose": "...",
          "started_at": "...", "ended_at": "...", "duration_seconds": 120,
          "transcript": "..." | [{"role": "agent", "message": "..."}],
          "summary": "...", "recording_url": "http://..."
        }

    A nested ``data`` object is also accepted.
    """
    raw_type = str(_first(payload, "event", "event_type", "type") or "").strip()
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    key = raw_type.lower().replace("_", ".", 1) if raw_type.lower().startswith("call_") else raw_type.lower()
    event_type, implied_status = EVENT_ALIASES.get(key, ("unknown", None))

    status = normalize_status(data.get("status")) or implied_status
    if event_type == "unknown" and status:
        # A bare status update without a recognised event name.
        event_type = status

    return NormalizedCallEvent(
        event_type=event_type,
        source=str(payload.get("source") or "generic"),
        raw_type=raw_type or None,
        crm_call_id=to_int(_first(data, "crm_call_id", "client_reference")),
        external_call_id=_as_str(_first(data, "external_call_id", "call_id", "uniqueid", "call_sid")),
        conversation_id=_as_str(_first(data, "conversation_id", "elevenlabs_conversation_id")),
        direction=_first(data, "direction"),
        customer_phone=_as_str(_first(data, "customer_phone", "caller_id", "from", "external_number")),
        customer_name=_first(data, "customer_name", "caller_name"),
        brand_name=_first(data, "brand", "brand_name"),
        brand_number=_as_str(_first(data, "brand_number", "called_number", "to", "did")),
        agent_id=_first(data, "agent_id"),
        agent_name=_first(data, "agent_name"),
        status=status,
        outcome=normalize_outcome(data.get("outcome")),
        purpose=_first(data, "purpose"),
        started_at=parse_datetime(data.get("started_at")),
        ended_at=parse_datetime(data.get("ended_at")),
        duration_seconds=to_int(_first(data, "duration_seconds", "duration")),
        transcript=format_transcript(data.get("transcript")),
        summary=_first(data, "summary"),
        recording_url=_first(data, "recording_url"),
        error_message=_first(data, "error_message", "error"),
    )


def _as_str(value: Any) -> str | None:
    return None if value is None else str(value)
