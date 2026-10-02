"""AI call summaries via the OpenAI Chat Completions API (server-side only).

The API key never leaves the backend. Only CRM call metadata, agent notes and
the transcript (if any) are sent - no audio.
"""

from __future__ import annotations

import json
import logging

import httpx
from fastapi import HTTPException

from ..config import get_settings
from ..models import Call

logger = logging.getLogger(__name__)

OUTCOMES = ["booked", "inquiry", "interested", "not_interested", "callback", "transferred", "completed", "failed"]

SYSTEM_PROMPT = (
    "You are a call-centre assistant for a group of UAE healthcare/wellness brands. "
    "Given a phone call's metadata, the agent's notes and an optional transcript, return JSON with: "
    '"summary" (2-4 short sentences, factual, no invented details), '
    f'"suggested_outcome" (one of: {", ".join(OUTCOMES)}), '
    '"next_action" (one short sentence, or empty string). '
    "If information is missing, say so briefly instead of guessing."
)


def ai_enabled() -> bool:
    return bool(get_settings().openai_api_key)


def _call_context(call: Call, notes: str | None) -> str:
    lines = [
        f"Direction: {call.direction}",
        f"Brand: {call.brand_name or 'unknown'}",
        f"Customer: {call.customer_name or 'unknown'} ({call.customer_phone})",
        f"Purpose: {call.purpose or 'not set'}",
        f"Status: {call.status}",
        f"Talk time (seconds): {call.duration_seconds if call.duration_seconds is not None else 'unknown'}",
        f"Current outcome: {call.outcome or 'not set'}",
        f"Booking: {call.booking_reference or 'none'}",
        f"Agent notes: {notes or call.notes or '(none)'}",
    ]
    if call.transcript:
        lines.append(f"Transcript:\n{call.transcript[:12000]}")
    return "\n".join(lines)


def summarize_call(call: Call, notes: str | None = None) -> dict:
    """Return {"summary", "suggested_outcome", "next_action"}; raises HTTPException on failure."""
    settings = get_settings()
    if not settings.openai_api_key:
        raise HTTPException(status_code=503, detail="AI is not configured: set OPENAI_API_KEY in backend/.env and restart.")

    body = {
        "model": settings.openai_model,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _call_context(call, notes)},
        ],
    }
    try:
        response = httpx.post(
            f"{settings.openai_base_url}/chat/completions",
            json=body,
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            timeout=45,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Could not reach OpenAI: {exc}") from exc

    if response.status_code >= 400:
        try:
            message = response.json().get("error", {}).get("message", "")
        except ValueError:
            message = response.text[:200]
        logger.warning("OpenAI error %s: %s", response.status_code, message)
        raise HTTPException(status_code=502, detail=f"OpenAI error {response.status_code}: {message}")

    try:
        content = response.json()["choices"][0]["message"]["content"]
        data = json.loads(content)
    except (KeyError, IndexError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=502, detail="OpenAI returned an unexpected response.") from exc

    outcome = str(data.get("suggested_outcome") or "").strip().lower().replace(" ", "_")
    return {
        "summary": str(data.get("summary") or "").strip(),
        "suggested_outcome": outcome if outcome in OUTCOMES else None,
        "next_action": str(data.get("next_action") or "").strip(),
    }
