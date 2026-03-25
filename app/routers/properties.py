"""app/routers/properties.py — POST /properties/"""

from __future__ import annotations
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter
from app.schemas import PropertyBase, PropertyRead
from app import storage

router = APIRouter(prefix="/properties", tags=["properties"])


@router.post("/", response_model=PropertyRead, status_code=201)
def create_property(payload: PropertyBase) -> PropertyRead:
    """Crée et stocke une propriété sans générer de pack."""
    prop = PropertyRead(id=str(uuid4()), created_at=datetime.now(timezone.utc), **payload.model_dump())
    storage.save_property(prop)
    return prop
