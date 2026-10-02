"""AI call summaries via Azure OpenAI (Azure AI Foundry), server-side only.

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
    settings = get_settings()
    return bool(settings.azure_api_key and settings.azure_endpoint)


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


def _error_message(response: httpx.Response) -> str:
    try:
        error = response.json().get("error", {})
        return error.get("message") or error.get("code") or response.text[:200]
    except ValueError:
        return response.text[:200]


def _chat(body: dict) -> dict:
    """POST to the Azure deployment endpoint; fall back to the v1 endpoint if the deployment route 404s."""
    settings = get_settings()
    headers = {"api-key": settings.azure_api_key}
    deployment_url = (
        f"{settings.azure_endpoint}/openai/deployments/{settings.azure_deployment}"
        f"/chat/completions?api-version={settings.azure_api_version}"
    )
    try:
        response = httpx.post(deployment_url, json=body, headers=headers, timeout=45)
        if response.status_code == 404:
            response = httpx.post(
                f"{settings.azure_endpoint}/openai/v1/chat/completions",
                json={**body, "model": settings.azure_deployment},
                headers=headers,
                timeout=45,
            )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Could not reach Azure OpenAI: {exc}") from exc

    if response.status_code >= 400:
        message = _error_message(response)
        logger.warning("Azure OpenAI error %s: %s", response.status_code, message)
        hint = " (check AZURE_OPENAI_DEPLOYMENT matches the deployment name in Azure AI Foundry)" if response.status_code == 404 else ""
        raise HTTPException(status_code=502, detail=f"Azure OpenAI error {response.status_code}: {message}{hint}")
    return response.json()


def summarize_call(call: Call, notes: str | None = None) -> dict:
    """Return {"summary", "suggested_outcome", "next_action"}; raises HTTPException on failure."""
    if not ai_enabled():
        raise HTTPException(
            status_code=503,
            detail="AI is not configured: set AZURE_API_KEY and Azure_open_ai_endpoint in backend/.env and restart.",
        )

    data = _chat(
        {
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": _call_context(call, notes)},
            ],
        }
    )
    try:
        parsed = json.loads(data["choices"][0]["message"]["content"])
    except (KeyError, IndexError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=502, detail="Azure OpenAI returned an unexpected response.") from exc

    outcome = str(parsed.get("suggested_outcome") or "").strip().lower().replace(" ", "_")
    return {
        "summary": str(parsed.get("summary") or "").strip(),
        "suggested_outcome": outcome if outcome in OUTCOMES else None,
        "next_action": str(parsed.get("next_action") or "").strip(),
    }
