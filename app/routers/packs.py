"""
app/routers/packs.py — POST /packs/generate · GET /packs/{pack_id} · GET /packs/{pack_id}/merchants
"""

from __future__ import annotations
import logging
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from app.schemas import MerchantBreakdownResponse, PackScreenResponse, PropertyBase, PropertyRead
from app.services.packs import (
    build_merchant_breakdown,
    build_pack_screen_response,
    generate_pack_for_property,
    _compute_lmnp_checklist,
)
from app import storage

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/packs", tags=["packs"])


@router.post("/generate", response_model=PackScreenResponse, status_code=201)
def generate_pack(payload: PropertyBase) -> PackScreenResponse:
    """
    Flux principal MVP :
    1. Crée la propriété
    2. Génère le pack domaine (mock) + la vue écran
    3. Stocke property + pack en mémoire
    4. Retourne PackScreenResponse (vue frontend Étape 2/4)
    """
    prop = PropertyRead(
        id=str(uuid4()),
        created_at=datetime.now(timezone.utc),
        **payload.model_dump(),
    )
    storage.save_property(prop)

    try:
        pack, screen = generate_pack_for_property(prop)
    except Exception as exc:
        logger.exception("Pack generation failed for property %s", prop.id)
        raise HTTPException(
            status_code=503,
            detail={
                "message": "L'IA n'a pas pu générer votre pack. Veuillez réessayer.",
                "retry": True,
            },
        ) from exc

    storage.save_pack(pack)
    return screen


@router.get("/{pack_id}/merchants", response_model=MerchantBreakdownResponse)
def get_pack_merchants(pack_id: str) -> MerchantBreakdownResponse:
    """
    Vue Étape 3/4 — regroupement du pack par enseigne.

    Charge PackDomain + PropertyRead depuis le storage, recalcule la
    checklist LMNP, projette vers MerchantBreakdownResponse.

    La route /merchants doit être déclarée AVANT /{pack_id} pour éviter
    que FastAPI n'interprète "merchants" comme un pack_id.
    """
    pack = storage.get_pack(pack_id)
    if pack is None:
        raise HTTPException(status_code=404, detail="Pack introuvable.")

    prop = storage.get_property(pack.property_id)
    if prop is None:
        raise HTTPException(status_code=404, detail="Propriété associée introuvable.")

    checklist = _compute_lmnp_checklist(pack)
    return build_merchant_breakdown(prop, pack, checklist)


@router.get("/{pack_id}", response_model=PackScreenResponse)
def get_pack(pack_id: str) -> PackScreenResponse:
    """
    Récupère un pack par son id et retourne la vue écran Étape 2.
    URL partageable /packs/{pack_id} — User story 7.
    """
    pack = storage.get_pack(pack_id)
    if pack is None:
        raise HTTPException(status_code=404, detail="Pack introuvable.")

    prop = storage.get_property(pack.property_id)
    if prop is None:
        raise HTTPException(status_code=404, detail="Propriété associée introuvable.")

    return build_pack_screen_response(prop, pack)
