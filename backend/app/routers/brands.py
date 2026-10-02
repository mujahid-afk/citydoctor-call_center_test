"""Brand configuration (one codebase, many brands/DIDs)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Brand
from ..schemas import BrandOut, BrandUpdate

router = APIRouter(prefix="/api/brands", tags=["brands"])

DbSession = Annotated[Session, Depends(get_db)]


@router.get("", response_model=list[BrandOut])
def list_brands(db: DbSession, active_only: bool = False):
    query = select(Brand).order_by(Brand.id)
    if active_only:
        query = query.where(Brand.active.is_(True))
    return list(db.scalars(query))


@router.patch("/{brand_id}", response_model=BrandOut)
def update_brand(brand_id: int, payload: BrandUpdate, db: DbSession):
    """Set a brand's DID, ElevenLabs agent ID or active flag."""
    brand = db.get(Brand, brand_id)
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(brand, key, value)
    db.commit()
    db.refresh(brand)
    return brand
