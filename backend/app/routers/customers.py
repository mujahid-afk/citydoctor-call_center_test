"""Customers and brands."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Brand, Customer
from ..schemas import BrandOut, BrandUpdate, CustomerCreate, CustomerOut
from ..services.call_service import find_customer_by_phone

router = APIRouter(prefix="/api", tags=["customers"])

DbSession = Annotated[Session, Depends(get_db)]


@router.get("/brands", response_model=list[BrandOut])
def list_brands(db: DbSession, active_only: bool = False):
    query = select(Brand).order_by(Brand.id)
    if active_only:
        query = query.where(Brand.active.is_(True))
    return list(db.scalars(query))


@router.patch("/brands/{brand_id}", response_model=BrandOut)
def update_brand(brand_id: int, payload: BrandUpdate, db: DbSession):
    """Set a brand's number / agent name / ElevenLabs agent ID / phone number ID."""
    brand = db.get(Brand, brand_id)
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(brand, field, value)
    db.commit()
    db.refresh(brand)
    return brand


@router.get("/customers", response_model=list[CustomerOut])
def list_customers(db: DbSession, search: str | None = None, limit: int = 200):
    query = select(Customer).order_by(Customer.created_at.desc(), Customer.id.desc()).limit(min(limit, 1000))
    if search:
        like = f"%{search.strip()}%"
        query = query.where(or_(Customer.name.ilike(like), Customer.phone.ilike(like), Customer.email.ilike(like)))
    return list(db.scalars(query))


@router.post("/customers", response_model=CustomerOut, status_code=status.HTTP_201_CREATED)
def create_customer(payload: CustomerCreate, db: DbSession):
    if find_customer_by_phone(db, payload.phone):
        raise HTTPException(status_code=409, detail="A customer with this phone number already exists")
    customer = Customer(name=payload.name.strip(), phone=payload.phone, email=payload.email or None)
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer


@router.get("/customers/{customer_id}", response_model=CustomerOut)
def get_customer(customer_id: int, db: DbSession):
    customer = db.get(Customer, customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    return customer
