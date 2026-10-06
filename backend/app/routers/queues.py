"""FreePBX queues (per brand/department), matched to inbound calls by the X-Queue header."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from ..models import Brand, Call, Queue
from ..schemas import QueueCreate, QueueOut, QueueUpdate
from ..services.call_service import find_queue

router = APIRouter(prefix="/api/queues", tags=["queues"])

DbSession = Annotated[Session, Depends(get_db)]


def _check(db: Session, queue_id: int | None, name: str | None, brand_id: int | None) -> None:
    if brand_id is not None and not db.get(Brand, brand_id):
        raise HTTPException(status_code=404, detail="Brand not found")
    other = find_queue(db, name)
    if other and other.id != queue_id:
        raise HTTPException(status_code=409, detail=f"Queue {other.name!r} already exists")


@router.get("", response_model=list[QueueOut])
def list_queues(db: DbSession, active_only: bool = False, brand_id: int | None = None):
    query = select(Queue).options(selectinload(Queue.brand)).order_by(Queue.name)
    if active_only:
        query = query.where(Queue.active.is_(True))
    if brand_id:
        query = query.where(Queue.brand_id == brand_id)
    return list(db.scalars(query))


@router.post("", response_model=QueueOut, status_code=status.HTTP_201_CREATED)
def create_queue(payload: QueueCreate, db: DbSession):
    """Register a queue up front (otherwise it is created on its first call). `name` must match X-Queue."""
    _check(db, None, payload.name, payload.brand_id)
    queue = Queue(**payload.model_dump())
    queue.name = queue.name.strip()
    db.add(queue)
    db.commit()
    db.refresh(queue)
    return queue


@router.patch("/{queue_id}", response_model=QueueOut)
def update_queue(queue_id: int, payload: QueueUpdate, db: DbSession):
    """Set a queue's brand, department, FreePBX number, name or active flag."""
    queue = db.get(Queue, queue_id)
    if not queue:
        raise HTTPException(status_code=404, detail="Queue not found")
    changes = payload.model_dump(exclude_unset=True)
    for key in ("name", "active"):
        if changes.get(key, False) is None:
            changes.pop(key)
    _check(db, queue.id, changes.get("name"), changes.get("brand_id"))
    for key, value in changes.items():
        setattr(queue, key, value.strip() if key == "name" else value)
    if "name" in changes:
        db.execute(update(Call).where(Call.queue_id == queue.id).values(queue_name=queue.name))
    db.commit()
    db.refresh(queue)
    return queue
