"""Incoming call events from ElevenLabs, the existing calling system or middleware."""

from __future__ import annotations

import hmac
import json
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..adapters.calling_system_adapter import normalize_call_event
from ..config import get_settings
from ..database import get_db
from ..models import CallStatus
from ..schemas import WebhookResult
from ..services import call_service
from ..services.elevenlabs_service import ElevenLabsService, is_elevenlabs_payload

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])

DbSession = Annotated[Session, Depends(get_db)]


async def _read_verified_json(request: Request) -> dict[str, Any]:
    """Parse the body and enforce whichever webhook secret applies.

    * ElevenLabs payloads / requests with an ``ElevenLabs-Signature`` header are
      verified with ELEVENLABS_WEBHOOK_SECRET (HMAC-SHA256), when configured.
    * Other senders must send ``X-Webhook-Secret: <CALLING_SYSTEM_WEBHOOK_SECRET>``,
      when configured.
    """
    settings = get_settings()
    raw = await request.body()
    try:
        payload = json.loads(raw or b"{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Body must be valid JSON") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Body must be a JSON object")

    signature = request.headers.get("elevenlabs-signature")
    if signature or is_elevenlabs_payload(payload):
        if not ElevenLabsService(settings).verify_webhook_signature(raw, signature):
            raise HTTPException(status_code=401, detail="Invalid ElevenLabs webhook signature")
    elif settings.calling_system_webhook_secret:
        provided = request.headers.get("x-webhook-secret", "")
        if not hmac.compare_digest(provided, settings.calling_system_webhook_secret):
            raise HTTPException(status_code=401, detail="Invalid X-Webhook-Secret")
    return payload


@router.post("/calls", response_model=WebhookResult)
async def call_events_webhook(request: Request, db: DbSession):
    """Generic call-event webhook (call.started / ringing / answered / completed / failed /
    no_answer / transcript / summary / recording, or native ElevenLabs post-call payloads)."""
    payload = await _read_verified_json(request)
    event = normalize_call_event(payload)
    if event.event_type == "unknown":
        # 200 so senders don't retry/disable the webhook for event types we don't use.
        return WebhookResult(status="ignored", event=event.raw_type, detail="Unrecognised event type")
    call = call_service.apply_call_event(db, event, raw_payload=payload)
    if call is None:
        return WebhookResult(status="ignored", event=event.event_type, detail="No matching call and no customer phone")
    return WebhookResult(status="ok", event=event.event_type, call_id=call.id)


@router.post("/elevenlabs", response_model=WebhookResult)
async def elevenlabs_webhook(request: Request, db: DbSession):
    """Alias of /api/webhooks/calls for ElevenLabs' post-call webhook setting."""
    return await call_events_webhook(request, db)


@router.post("/elevenlabs/conversation-init")
async def elevenlabs_conversation_init(request: Request, db: DbSession):
    """ElevenLabs 'conversation initiation client data' webhook for inbound calls.

    ElevenLabs calls this when an inbound call starts with
    ``{"caller_id", "agent_id", "called_number", "call_sid"}``. We register the
    inbound call as answered and return customer context as dynamic variables.
    """
    payload = await _read_verified_json(request)
    caller_id = str(payload.get("caller_id") or "").strip()
    called_number = str(payload.get("called_number") or "").strip() or None
    agent_id = payload.get("agent_id")

    variables: dict[str, str] = {"customer_name": "", "customer_known": "false", "brand_name": "", "crm_call_id": ""}
    if caller_id:
        customer = call_service.find_customer_by_phone(db, caller_id)
        brand = call_service.resolve_brand(db, number=called_number, agent_id=agent_id)
        call = call_service.create_call(
            db,
            direction="inbound",
            customer_phone=caller_id,
            customer_name=customer.name if customer else None,
            brand=brand,
            brand_number=called_number,
            agent_id=agent_id,
            external_call_id=payload.get("call_sid"),
            status=CallStatus.answered.value,
        )
        call.raw_provider_payload = call_service.append_raw_payload(None, payload)
        db.commit()
        variables.update(
            customer_name=customer.name if customer else "",
            customer_known="true" if customer else "false",
            brand_name=call.brand_name,
            crm_call_id=str(call.id),
        )
    return {"type": "conversation_initiation_client_data", "dynamic_variables": variables}
