"""CallingSystemAdapter – the ONLY seam between the CRM and the calling infrastructure.

Routers and services never talk to FreePBX / ElevenLabs / the internal API
directly; they call ``get_calling_adapter()`` and use this interface:

    adapter.start_outbound_call(customer_phone, brand, agent_id, purpose, context)
    adapter.get_call_status(call_id)
    adapter.get_call_details(call_id)

Incoming events (webhooks) go through ``normalize_call_event(payload)``.

Implementations:

* ``MockCallingSystemAdapter``       – CALLING_SYSTEM_MODE=mock / MOCK_CALLING_SYSTEM=true
* ``VpnCallingSystemAdapter``        – CALLING_SYSTEM_MODE=vpn (existing system over VPN)
* ``ElevenLabsCallingSystemAdapter`` – CALLING_SYSTEM_MODE=elevenlabs (optional, direct API)
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from ..config import get_settings
from ..services.calling_system_service import CallingSystemError, CallingSystemService
from ..services.elevenlabs_service import (
    ElevenLabsError,
    ElevenLabsService,
    is_elevenlabs_payload,
    normalize_elevenlabs_event,
)
from .call_events import NormalizedCallEvent, normalize_generic_event, normalize_status


class CallingSystemUnavailable(Exception):
    """Raised by adapters when the calling system rejects or cannot take the request."""


@dataclass
class OutboundCallResult:
    external_call_id: str | None
    conversation_id: str | None
    status: str = "calling"
    raw: dict[str, Any] = field(default_factory=dict)


# --------------------------------------------------------------------------- normalization
def normalize_call_event(payload: dict[str, Any]) -> NormalizedCallEvent:
    """Normalize an incoming event from ElevenLabs, the calling system or middleware."""
    if is_elevenlabs_payload(payload):
        return normalize_elevenlabs_event(payload)
    return normalize_generic_event(payload)


# --------------------------------------------------------------------------- interface
class CallingSystemAdapter(ABC):
    mode: str = "abstract"
    is_mock: bool = False

    @abstractmethod
    async def start_outbound_call(
        self,
        *,
        customer_phone: str,
        brand: str,
        agent_id: str | None,
        purpose: str,
        context: dict[str, Any],
    ) -> OutboundCallResult:
        """Ask the calling system to place an AI call. ``context`` carries CRM data
        (crm_call_id, customer_name, brand_number, agent_name, custom_instructions, ...)."""

    @abstractmethod
    async def get_call_status(self, call_id: str) -> str | None:
        """Return the internal status (queued/calling/.../completed) for an external call ID."""

    @abstractmethod
    async def get_call_details(self, call_id: str) -> NormalizedCallEvent | None:
        """Return full call details (transcript, summary, recording...) as a normalized event."""


# --------------------------------------------------------------------------- mock
class MockCallingSystemAdapter(CallingSystemAdapter):
    """Simulates the calling system locally; progression is written by mock_simulator."""

    mode = "mock"
    is_mock = True

    async def start_outbound_call(self, *, customer_phone, brand, agent_id, purpose, context) -> OutboundCallResult:
        from ..services import mock_simulator  # local import: avoids an import cycle

        crm_call_id = context.get("crm_call_id")
        if crm_call_id is None:
            raise CallingSystemUnavailable("Mock adapter needs context['crm_call_id'].")
        mock_simulator.spawn(mock_simulator.simulate_outbound_call(int(crm_call_id), context.get("mock_scenario")))
        return OutboundCallResult(
            external_call_id=f"mock-{uuid.uuid4().hex[:12]}",
            conversation_id=f"mock_conv_{uuid.uuid4().hex[:16]}",
            status="queued",
            raw={"mock": True},
        )

    async def get_call_status(self, call_id: str) -> str | None:
        from sqlalchemy import select

        from ..database import SessionLocal
        from ..models import Call

        with SessionLocal() as db:
            call = db.scalars(select(Call).where(Call.external_call_id == call_id)).first()
            return call.status if call else None

    async def get_call_details(self, call_id: str) -> NormalizedCallEvent | None:
        return None  # the simulator writes details straight into the database


# --------------------------------------------------------------------------- VPN / internal system
def _pick(data: dict[str, Any], *keys: str) -> Any:
    for container in (data, data.get("data") if isinstance(data.get("data"), dict) else {}):
        for key in keys:
            if container.get(key) not in (None, ""):
                return container[key]
    return None


class VpnCallingSystemAdapter(CallingSystemAdapter):
    """Talks to the existing calling system's internal HTTP API over the VPN."""

    mode = "vpn"

    def __init__(self, service: CallingSystemService | None = None) -> None:
        self.service = service or CallingSystemService()

    async def start_outbound_call(self, *, customer_phone, brand, agent_id, purpose, context) -> OutboundCallResult:
        try:
            data = await self.service.start_outbound_call(
                customer_phone=customer_phone, brand=brand, agent_id=agent_id, purpose=purpose, context=context
            )
        except CallingSystemError as exc:
            raise CallingSystemUnavailable(str(exc)) from exc
        if _pick(data, "success") is False:
            raise CallingSystemUnavailable(str(_pick(data, "message", "error") or "Calling system rejected the call"))
        external_id = _pick(data, "call_id", "external_call_id", "id", "uniqueid", "call_sid", "sip_call_id")
        return OutboundCallResult(
            external_call_id=str(external_id) if external_id is not None else None,
            conversation_id=_pick(data, "conversation_id", "elevenlabs_conversation_id"),
            status=normalize_status(_pick(data, "status")) or "calling",
            raw=data,
        )

    async def get_call_status(self, call_id: str) -> str | None:
        try:
            data = await self.service.get_call_status(call_id)
        except CallingSystemError as exc:
            raise CallingSystemUnavailable(str(exc)) from exc
        return normalize_status(_pick(data, "status", "state"))

    async def get_call_details(self, call_id: str) -> NormalizedCallEvent | None:
        try:
            data = await self.service.get_call_details(call_id)
        except CallingSystemError as exc:
            raise CallingSystemUnavailable(str(exc)) from exc
        event = normalize_call_event(data if "event" in data or is_elevenlabs_payload(data) else {"event": "call.update", **data})
        if event.event_type == "unknown":
            event.event_type = "update"
        event.external_call_id = event.external_call_id or call_id
        return event


# --------------------------------------------------------------------------- ElevenLabs direct (optional)
class ElevenLabsCallingSystemAdapter(CallingSystemAdapter):
    """Uses ElevenLabs' outbound-call API, which dials through the existing SIP trunk."""

    mode = "elevenlabs"

    def __init__(self, service: ElevenLabsService | None = None) -> None:
        self.service = service or ElevenLabsService()

    async def start_outbound_call(self, *, customer_phone, brand, agent_id, purpose, context) -> OutboundCallResult:
        dynamic_variables = {
            "customer_name": str(context.get("customer_name") or ""),
            "purpose": purpose,
            "custom_instructions": str(context.get("custom_instructions") or ""),
            "brand_name": brand,
            "brand_number": str(context.get("brand_number") or ""),
            "call_direction": "outbound",
            "crm_call_id": str(context.get("crm_call_id") or ""),
        }
        try:
            data = await self.service.start_outbound_call(
                agent_id=agent_id,
                phone_number_id=context.get("elevenlabs_phone_number_id"),
                customer_phone=customer_phone,
                dynamic_variables=dynamic_variables,
            )
        except ElevenLabsError as exc:
            raise CallingSystemUnavailable(str(exc)) from exc
        return OutboundCallResult(
            external_call_id=data.get("sip_call_id") or data.get("callSid"),
            conversation_id=data.get("conversation_id"),
            status="calling",
            raw=data,
        )

    async def get_call_status(self, call_id: str) -> str | None:
        details = await self.get_call_details(call_id)
        return details.status if details else None

    async def get_call_details(self, call_id: str) -> NormalizedCallEvent | None:
        """``call_id`` is the ElevenLabs conversation ID."""
        try:
            data = await self.service.get_conversation(call_id)
        except ElevenLabsError as exc:
            raise CallingSystemUnavailable(str(exc)) from exc
        return normalize_elevenlabs_event(data)


# --------------------------------------------------------------------------- factory
def get_calling_adapter(mode: str | None = None) -> CallingSystemAdapter:
    mode = mode or get_settings().effective_calling_mode
    if mode == "vpn":
        return VpnCallingSystemAdapter()
    if mode == "elevenlabs":
        return ElevenLabsCallingSystemAdapter()
    return MockCallingSystemAdapter()
