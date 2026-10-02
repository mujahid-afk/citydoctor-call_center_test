"""Test helpers: simulate inbound/outbound calls and check calling-system connectivity."""

from __future__ import annotations

import random
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..adapters.calling_system_adapter import MockCallingSystemAdapter
from ..config import get_settings
from ..database import get_db
from ..models import Brand, CallStatus, Customer
from ..schemas import CallOut, SimulateInboundRequest, SimulateOutboundRequest
from ..services import call_service, mock_simulator
from ..services.calling_system_service import CallingSystemService

router = APIRouter(prefix="/api/testing", tags=["testing"])

DbSession = Annotated[Session, Depends(get_db)]


def _random_customer(db: Session) -> tuple[str, str]:
    customers = list(db.scalars(select(Customer)))
    if customers:
        customer = random.choice(customers)
        return customer.name, customer.phone
    return "Test Caller", f"+97150{random.randint(1000000, 9999999)}"


def _brand(db: Session, name: str | None, number: str | None = None) -> Brand:
    if name or number:
        brand = call_service.resolve_brand(db, name=name, number=number)
        if not brand:
            raise HTTPException(status_code=404, detail=f"Brand '{name or number}' not found")
        return brand
    brands = list(db.scalars(select(Brand).where(Brand.active.is_(True))))
    if not brands:
        raise HTTPException(status_code=409, detail="No brands configured; run the seed script")
    return random.choice(brands)


@router.post("/simulate-inbound-call", response_model=CallOut, status_code=status.HTTP_201_CREATED)
async def simulate_inbound_call(payload: SimulateInboundRequest, db: DbSession):
    """Create a realistic inbound call (as if FreePBX -> ElevenLabs had received it).

    scenario: answered | completed | missed | transferred | booked | failed (random if omitted).
    All body fields are optional; missing ones are filled from seed data.
    """
    if payload.customer_phone:
        name, phone = payload.customer_name or "Unknown Caller", payload.customer_phone
    else:
        name, phone = _random_customer(db)
        name = payload.customer_name or name
    brand = _brand(db, payload.brand, None if payload.brand else payload.brand_number)
    scenario = payload.scenario or mock_simulator.pick_inbound_scenario()
    external_id, conversation_id = mock_simulator.new_mock_ids()

    call = call_service.create_call(
        db,
        direction="inbound",
        customer_phone=phone,
        customer_name=name,
        brand=brand,
        brand_number=payload.brand_number,
        agent_name=payload.agent_name,
        status=CallStatus.ringing.value,
        external_call_id=external_id,
        conversation_id=conversation_id,
        is_mock=True,
    )
    db.commit()

    if payload.instant:
        await mock_simulator.simulate_inbound_call(call.id, scenario, instant=True)
    else:
        mock_simulator.spawn(mock_simulator.simulate_inbound_call(call.id, scenario))
    db.expire_all()
    return call_service.get_call_or_404(db, call.id)


@router.post("/simulate-outbound-call", response_model=CallOut, status_code=status.HTTP_201_CREATED)
async def simulate_outbound_call(payload: SimulateOutboundRequest, db: DbSession):
    """Run an outbound call through the MOCK adapter, whatever CALLING_SYSTEM_MODE is.

    scenario: completed | booked | no_answer | failed (random if omitted).
    """
    if payload.customer_phone:
        name, phone = payload.customer_name or "Test Customer", payload.customer_phone
    else:
        name, phone = _random_customer(db)
        name = payload.customer_name or name
    brand = _brand(db, payload.brand)
    return await call_service.place_outbound_call(
        db,
        MockCallingSystemAdapter(),
        customer_name=name,
        customer_phone=phone,
        brand_name=brand.name,
        agent_name=payload.agent_name,
        purpose=payload.purpose,
        custom_instructions=payload.custom_instructions,
        extra_context={"mock_scenario": payload.scenario},
    )


@router.get("/calling-system-check")
async def calling_system_check():
    """Check VPN reachability of the internal calling-system API and FreePBX host."""
    settings = get_settings()
    result = await CallingSystemService(settings).check_connectivity()
    return {"mode": settings.effective_calling_mode, "mock_reason": settings.mock_reason, **result}
