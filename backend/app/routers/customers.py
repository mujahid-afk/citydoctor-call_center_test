"""Customer records and caller lookup."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Call, Customer
from ..schemas import CustomerCreate, CustomerLookup, CustomerOut, CustomerUpdate
from ..services.call_service import customer_lookup, find_customer_by_phone

router = APIRouter(prefix="/api/customers", tags=["customers"])

DbSession = Annotated[Session, Depends(get_db)]


def _get_or_404(db: Session, customer_id: int) -> Customer:
    customer = db.get(Customer, customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    return customer


@router.get("", response_model=list[CustomerOut])
def list_customers(db: DbSession, search: str | None = None, limit: int = 200):
    query = select(Customer).order_by(Customer.name).limit(min(limit, 1000))
    if search:
        like = f"%{search.strip()}%"
        query = query.where(or_(Customer.name.ilike(like), Customer.phone.ilike(like), Customer.email.ilike(like)))
    return list(db.scalars(query))


@router.get("/by-phone/{phone}", response_model=CustomerLookup)
def get_customer_by_phone(phone: str, db: DbSession):
    """Caller lookup for incoming calls: customer + recent calls + bookings (404 if unknown).

    Formatting differences are tolerated (+971501234567 == 0501234567).
    """
    customer = find_customer_by_phone(db, phone)
    if not customer:
        raise HTTPException(status_code=404, detail="Unknown customer")
    return customer_lookup(db, customer)


@router.post("", response_model=CustomerOut, status_code=status.HTTP_201_CREATED)
def create_customer(payload: CustomerCreate, db: DbSession):
    if find_customer_by_phone(db, payload.phone):
        raise HTTPException(status_code=409, detail="A customer with this phone number already exists")
    customer = Customer(**payload.model_dump())
    customer.name = customer.name.strip()
    db.add(customer)
    db.flush()
    # Link earlier calls from this number (e.g. the incoming call that prompted "Create Customer").
    for call in db.scalars(select(Call).where(Call.customer_id.is_(None))):
        if find_customer_by_phone(db, call.customer_phone) is customer:
            call.customer_id = customer.id
            call.customer_name = customer.name
    db.commit()
    db.refresh(customer)
    return customer


@router.get("/{customer_id}", response_model=CustomerOut)
def get_customer(customer_id: int, db: DbSession):
    return _get_or_404(db, customer_id)


@router.patch("/{customer_id}", response_model=CustomerOut)
def update_customer(customer_id: int, payload: CustomerUpdate, db: DbSession):
    customer = _get_or_404(db, customer_id)
    changes = payload.model_dump(exclude_unset=True)
    if "phone" in changes:
        other = find_customer_by_phone(db, changes["phone"])
        if other and other.id != customer.id:
            raise HTTPException(status_code=409, detail="Another customer already has this phone number")
    for key, value in changes.items():
        setattr(customer, key, value)
    if "name" in changes:
        for call in customer.calls:
            call.customer_name = customer.name
    db.commit()
    db.refresh(customer)
    return customer
