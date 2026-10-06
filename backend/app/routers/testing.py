"""Helpers for local testing with the mock softphone."""

from __future__ import annotations

import random
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Brand, Call, Customer, Queue
from ..seed import reset_and_seed

router = APIRouter(prefix="/api/testing", tags=["testing"])

DbSession = Annotated[Session, Depends(get_db)]


@router.get("/random-caller")
def random_caller(db: DbSession):
    """A plausible inbound caller for 'Simulate Incoming Call': ~70% known customers, else a new number.

    Also returns what FreePBX would put in the INVITE headers: brand, queue, IVR path and how long
    the caller has already waited in the queue.
    """
    customers = list(db.scalars(select(Customer)))
    brands = list(db.scalars(select(Brand).where(Brand.active.is_(True))))
    queues = list(db.scalars(select(Queue).where(Queue.active.is_(True), Queue.brand_id.is_not(None))))
    queue = random.choice(queues) if queues else None
    brand = next((b for b in brands if queue and b.id == queue.brand_id), None) or (random.choice(brands) if brands else None)
    if customers and random.random() < 0.7:
        customer = random.choice(customers)
        phone, name = customer.phone, customer.name
    else:
        phone, name = f"+9715{random.choice('024568')}{random.randint(1000000, 9999999)}", None
    return {
        "customer_phone": phone,
        "customer_name": name,
        "brand_id": brand.id if brand else None,
        "brand_name": brand.name if brand else None,
        "brand_number": brand.phone_number if brand else None,
        "queue_name": queue.name if queue else None,
        "ivr_path": f"ivr-7>ivr-{8 + brands.index(brand)}" if queue and brand else None,
        "wait_seconds": random.randint(3, 90) if queue else 0,
    }


@router.post("/reset")
def reset_demo_data(db: DbSession):
    """Drop all data and re-seed the demo dataset. Refused once real (non-mock) calls exist."""
    if db.scalars(select(Call.id).where(Call.is_mock.is_(False)).limit(1)).first():
        raise HTTPException(
            status_code=409,
            detail="The database has real calls, so it was not reset. Use `python -m app.seed --reset` to wipe it deliberately.",
        )
    db.close()
    counts = reset_and_seed()
    return {"status": "ok", **counts}
