"""Helpers for local testing with the mock softphone."""

from __future__ import annotations

import random
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Brand, Customer
from ..seed import reset_and_seed

router = APIRouter(prefix="/api/testing", tags=["testing"])

DbSession = Annotated[Session, Depends(get_db)]


@router.get("/random-caller")
def random_caller(db: DbSession):
    """A plausible inbound caller for 'Simulate Incoming Call': ~70% known customers, else a new number."""
    customers = list(db.scalars(select(Customer)))
    brands = list(db.scalars(select(Brand).where(Brand.active.is_(True))))
    brand = random.choice(brands) if brands else None
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
    }


@router.post("/reset")
def reset_demo_data():
    """Drop all data and re-seed the demo dataset."""
    counts = reset_and_seed()
    return {"status": "ok", **counts}
