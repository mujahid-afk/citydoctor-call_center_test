"""ElevenLabs-specific code (kept isolated from the rest of the app).

* ``normalize_elevenlabs_event`` – converts ElevenLabs webhook / conversation
  payloads into the provider-neutral ``NormalizedCallEvent``.
* ``ElevenLabsService`` – webhook signature verification, conversation /
  audio lookups and (optional) direct outbound calls via the ElevenLabs API.

The ElevenLabs API key is only ever used here, on the backend.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import time
from datetime import timedelta
from typing import Any

import httpx

from ..adapters.call_events import (
    NormalizedCallEvent,
    format_transcript,
    from_unix,
    normalize_outcome,
    to_int,
    utc_now_naive,
)
from ..config import Settings, get_settings

logger = logging.getLogger(__name__)

SIGNATURE_TOLERANCE_SECONDS = 30 * 60
ELEVENLABS_WEBHOOK_TYPES = {"post_call_transcription", "post_call_audio", "call_initiation_failure"}


class ElevenLabsError(Exception):
    """Raised when the ElevenLabs API returns an error or is unreachable."""


def is_elevenlabs_payload(payload: dict[str, Any]) -> bool:
    if payload.get("type") in ELEVENLABS_WEBHOOK_TYPES:
        return True
    # Raw conversation object from GET /v1/convai/conversations/{id}
    return "event" not in payload and "conversation_id" in payload and isinstance(payload.get("transcript"), list)


# --------------------------------------------------------------------------- normalization
def normalize_elevenlabs_event(payload: dict[str, Any]) -> NormalizedCallEvent:
    raw_type = str(payload.get("type") or "")
    if raw_type == "post_call_transcription":
        return _normalize_conversation(payload.get("data") or {}, raw_type)
    if raw_type == "post_call_audio":
        return _normalize_audio(payload.get("data") or {}, raw_type)
    if raw_type == "call_initiation_failure":
        return _normalize_initiation_failure(payload.get("data") or {}, raw_type)
    if is_elevenlabs_payload(payload):
        return _normalize_conversation(payload, "conversation")
    return NormalizedCallEvent(event_type="unknown", source="elevenlabs", raw_type=raw_type or None)


def _data_collection_value(analysis: dict[str, Any], key: str) -> str | None:
    item = (analysis.get("data_collection_results") or {}).get(key)
    value = item.get("value") if isinstance(item, dict) else item
    return None if value in (None, "") else str(value).strip()


def _normalize_conversation(data: dict[str, Any], raw_type: str) -> NormalizedCallEvent:
    metadata = data.get("metadata") or {}
    analysis = data.get("analysis") or {}
    phone_call = metadata.get("phone_call") or {}
    dyn = (data.get("conversation_initiation_client_data") or {}).get("dynamic_variables") or {}

    direction = phone_call.get("direction") or dyn.get("call_direction")
    if direction == "outbound":
        # For outbound calls ElevenLabs' caller/called system variables are swapped.
        customer_phone = phone_call.get("external_number") or dyn.get("system__called_number")
        brand_number = phone_call.get("agent_number") or dyn.get("system__caller_id")
    else:
        customer_phone = phone_call.get("external_number") or dyn.get("system__caller_id")
        brand_number = phone_call.get("agent_number") or dyn.get("system__called_number")

    started_at = from_unix(metadata.get("start_time_unix_secs"))
    duration = to_int(metadata.get("call_duration_secs"))
    ended_at = started_at + timedelta(seconds=duration) if started_at and duration is not None else None

    turns = data.get("transcript") or []
    customer_spoke = any(t.get("role") == "user" and (t.get("message") or "").strip() for t in turns)
    conv_status = str(data.get("status") or "").lower()
    termination = str(metadata.get("termination_reason") or "").lower()

    if conv_status == "failed":
        status = "failed"
    elif conv_status in {"initiated", "in-progress"}:
        status = "answered" if customer_spoke else "calling"
    elif "transfer" in termination:
        status = "transferred"
    elif direction == "outbound" and not customer_spoke and (duration or 0) < 5:
        status = "no_answer"
    else:
        status = "completed"

    # Configure a Data Collection item called "outcome" on the agent to fill this.
    outcome = normalize_outcome(
        _data_collection_value(analysis, "outcome") or _data_collection_value(analysis, "call_outcome")
    )

    return NormalizedCallEvent(
        event_type=status if status in {"failed", "transferred", "no_answer", "completed"} else "answered",
        source="elevenlabs",
        raw_type=raw_type,
        crm_call_id=to_int(dyn.get("crm_call_id")),
        external_call_id=phone_call.get("call_sid"),
        conversation_id=data.get("conversation_id"),
        direction=direction,
        customer_phone=customer_phone,
        customer_name=_data_collection_value(analysis, "customer_name") or dyn.get("customer_name"),
        brand_name=dyn.get("brand_name") or None,
        brand_number=brand_number,
        agent_id=data.get("agent_id"),
        status=status,
        outcome=outcome,
        purpose=_data_collection_value(analysis, "purpose") or dyn.get("purpose") or None,
        started_at=started_at,
        ended_at=ended_at,
        duration_seconds=duration,
        transcript=format_transcript(turns),
        summary=analysis.get("transcript_summary") or None,
        has_provider_audio=bool(data.get("has_audio")),
    )


def _normalize_audio(data: dict[str, Any], raw_type: str) -> NormalizedCallEvent:
    audio: bytes | None = None
    if data.get("full_audio"):
        try:
            audio = base64.b64decode(data["full_audio"])
        except (ValueError, TypeError):
            logger.warning("Could not decode ElevenLabs post_call_audio payload")
    return NormalizedCallEvent(
        event_type="recording",
        source="elevenlabs",
        raw_type=raw_type,
        conversation_id=data.get("conversation_id"),
        agent_id=data.get("agent_id"),
        recording_audio=audio,
    )


def _normalize_initiation_failure(data: dict[str, Any], raw_type: str) -> NormalizedCallEvent:
    reason = str(data.get("failure_reason") or "unknown").lower()
    body = (data.get("metadata") or {}).get("body") or {}
    status = "no_answer" if reason in {"no-answer", "no_answer", "busy"} else "failed"
    return NormalizedCallEvent(
        event_type=status,
        source="elevenlabs",
        raw_type=raw_type,
        conversation_id=data.get("conversation_id"),
        external_call_id=body.get("CallSid") or body.get("call_sid"),
        agent_id=data.get("agent_id"),
        status=status,
        error_message=f"Call initiation failed: {reason}",
        ended_at=utc_now_naive(),
        duration_seconds=0,
    )


# --------------------------------------------------------------------------- API client
class ElevenLabsService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    @property
    def configured(self) -> bool:
        return bool(self.settings.elevenlabs_api_key)

    def _headers(self) -> dict[str, str]:
        return {"xi-api-key": self.settings.elevenlabs_api_key}

    async def start_outbound_call(
        self,
        *,
        agent_id: str | None,
        phone_number_id: str | None,
        customer_phone: str,
        dynamic_variables: dict[str, str],
    ) -> dict[str, Any]:
        """POST /v1/convai/sip-trunk/outbound-call (or twilio). Context goes in dynamic variables."""
        if not self.configured:
            raise ElevenLabsError("ELEVENLABS_API_KEY is not configured.")
        agent_id = agent_id or self.settings.elevenlabs_agent_id
        phone_number_id = phone_number_id or self.settings.elevenlabs_phone_number_id
        if not agent_id:
            raise ElevenLabsError("No ElevenLabs agent ID (brand or ELEVENLABS_AGENT_ID).")
        if not phone_number_id:
            raise ElevenLabsError("No ElevenLabs phone number ID (brand or ELEVENLABS_PHONE_NUMBER_ID).")

        transport = "twilio" if self.settings.elevenlabs_outbound_transport == "twilio" else "sip-trunk"
        url = f"{self.settings.elevenlabs_base_url}/v1/convai/{transport}/outbound-call"
        body = {
            "agent_id": agent_id,
            "agent_phone_number_id": phone_number_id,
            "to_number": customer_phone,
            "conversation_initiation_client_data": {"dynamic_variables": dynamic_variables},
        }
        data = await self._request("POST", url, json=body)
        if data.get("success") is False:
            raise ElevenLabsError(f"ElevenLabs rejected the call: {data.get('message') or data}")
        return data

    async def get_conversation(self, conversation_id: str) -> dict[str, Any]:
        url = f"{self.settings.elevenlabs_base_url}/v1/convai/conversations/{conversation_id}"
        return await self._request("GET", url)

    async def get_conversation_audio(self, conversation_id: str) -> bytes:
        if not self.configured:
            raise ElevenLabsError("ELEVENLABS_API_KEY is not configured.")
        url = f"{self.settings.elevenlabs_base_url}/v1/convai/conversations/{conversation_id}/audio"
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.get(url, headers=self._headers())
        except httpx.HTTPError as exc:
            raise ElevenLabsError(f"Could not reach ElevenLabs: {exc}") from exc
        if response.status_code >= 400:
            raise ElevenLabsError(f"ElevenLabs audio error {response.status_code}")
        return response.content

    async def _request(self, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        if not self.configured:
            raise ElevenLabsError("ELEVENLABS_API_KEY is not configured.")
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.request(method, url, headers=self._headers(), **kwargs)
        except httpx.HTTPError as exc:
            raise ElevenLabsError(f"Could not reach ElevenLabs: {exc}") from exc
        try:
            data = response.json()
        except ValueError:
            data = {}
        if not isinstance(data, dict):
            data = {"data": data}
        if response.status_code >= 400:
            detail = data.get("detail") or data.get("message") or response.text[:300]
            raise ElevenLabsError(f"ElevenLabs API error {response.status_code}: {detail}")
        return data

    def verify_webhook_signature(self, raw_body: bytes, signature_header: str | None) -> bool:
        """Verify ``ElevenLabs-Signature: t=<unix>,v0=<hex hmac_sha256(secret, f"{t}.{body}")>``.

        Returns True when ELEVENLABS_WEBHOOK_SECRET is not configured.
        """
        secret = self.settings.elevenlabs_webhook_secret
        if not secret:
            return True
        if not signature_header:
            return False
        parts = dict(p.strip().split("=", 1) for p in signature_header.split(",") if "=" in p)
        timestamp, signature = parts.get("t"), parts.get("v0")
        if not timestamp or not signature:
            return False
        try:
            if abs(time.time() - int(timestamp)) > SIGNATURE_TOLERANCE_SECONDS:
                return False
        except ValueError:
            return False
        expected = hmac.new(secret.encode(), f"{timestamp}.".encode() + raw_body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)
