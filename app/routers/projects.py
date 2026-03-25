"""
app/routers/projects.py — Endpoints /projects

POST   /projects                  → crée Project + Property + Pack (via générateur)
GET    /projects/{id}             → ProjectPackResponse
GET    /projects/{id}/pack        → ProjectPackResponse  (alias)
GET    /projects/{id}/retailers   → RetailersResponse    (Étape 3)
GET    /projects/{id}/summary     → SummaryResponse      (Étape 4)

Ordre des routes : les routes spécifiques (/retailers, /pack, /summary)
sont déclarées AVANT /{id} pour éviter la capture par le path parameter.
"""

from __future__ import annotations

import logging
import re
import unicodedata
import uuid
from collections import defaultdict
from typing import Dict, List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import Pack, PackItem, PackLmnpCriterion, Project, Property, Room
from app.schemas_v2 import (
    LmnpCriterionStatus,
    PackItemOut,
    PackOut,
    ProjectCreate,
    ProjectPackResponse,
    PropertyOut,
    RetailerBlockOut,
    RetailerItemOut,
    RetailersResponse,
    RetailerSummaryLine,
    RoomOut,
    SummaryResponse,
)
from app.services.generator import generate_pack_for_property

def _make_slug(city: str, prop_type: str, budget: str) -> str:
    """
    Génère un slug lisible pour public_slug.
    Ex: "paris-t2-standard-3f2a1b8c"
    """
    # Normalisation Unicode : "Sète" → "Sete", "Île-de-France" → "Ile-de-France"
    def _ascii(s: str) -> str:
        return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    base = f"{_ascii(city)}-{_ascii(prop_type)}-{_ascii(budget)}".lower()
    base = re.sub(r"[^a-z0-9-]", "-", base)   # remplace tout caractère non alphanum
    base = re.sub(r"-{2,}", "-", base).strip("-")  # dédouble les tirets
    base = base[:40] or "pack"                 # limite la longueur
    return f"{base}-{str(uuid.uuid4())[:8]}"   # unicité garantie


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/projects", tags=["projects"])


# ─────────────────────────────────────────────────────────────────────────────
# Helpers — projection SQL → schemas Pydantic
# ─────────────────────────────────────────────────────────────────────────────

def _build_property_out(prop: Property) -> PropertyOut:
    return PropertyOut(
        property_type=prop.property_type,
        surface_m2=prop.surface_m2,
        rooms_count=prop.rooms_count,
        city=prop.city,
        postal_code=prop.postal_code,
        tenant_profile=prop.tenant_profile,
        rental_type=prop.rental_type,
        decor_style=prop.decor_style,
        budget_level=prop.budget_level,
        budget_min=prop.budget_min,
        budget_max=prop.budget_max,
    )


def _build_lmnp_checklist(pack: Pack) -> List[LmnpCriterionStatus]:
    """
    Construit la checklist depuis pack.lmnp_criteria_links.
    Tri : critères couverts d'abord, puis non couverts.
    """
    return sorted(
        [
            LmnpCriterionStatus(
                code=link.criterion.code,
                label=link.criterion.label,
                is_covered=link.is_covered,
            )
            for link in pack.lmnp_criteria_links
        ],
        key=lambda c: (not c.is_covered, c.code),
    )


def _build_pack_out(pack: Pack) -> PackOut:
    """Projette un Pack SQLAlchemy vers PackOut (rooms dans PackOut)."""
    rooms_out: List[RoomOut] = []

    for room in sorted(pack.rooms, key=lambda r: r.id):
        items_out: List[PackItemOut] = [
            PackItemOut(
                id=item.id,
                name=item.name,
                reference=item.reference,
                retailer=item.retailer.name,   # dénormalisé
                tag_type=item.tag_type,
                unit_price=item.unit_price,
                quantity=item.quantity,
                total_price=item.total_price,
                product_url=item.product_url,
            )
            for item in sorted(room.items, key=lambda i: i.name)
        ]
        rooms_out.append(
            RoomOut(
                id=room.id,
                room_type=room.room_type,
                label=room.label,
                mandatory_items_count=room.mandatory_items_count,
                total_price=room.total_price,
                items=items_out,
            )
        )

    return PackOut(
        id=pack.id,
        total_price=pack.total_price,
        is_lmnp_compliant=pack.is_lmnp_compliant,
        savings_amount=pack.savings_amount,
        savings_percent=pack.savings_percent,
        rooms=rooms_out,
        lmnp_checklist=_build_lmnp_checklist(pack),
    )


def _build_project_pack_response(project: Project) -> ProjectPackResponse:
    return ProjectPackResponse(
        project_id=project.id,
        public_slug=project.public_slug,
        property=_build_property_out(project.property),
        pack=_build_pack_out(project.pack),
    )


def _get_project_or_404(project_id: str, db: Session) -> Project:
    """
    Charge le projet avec toutes ses relations en UNE SEULE requête SQL.
    joinedload évite le N+1 sur pack.rooms → room.items → item.retailer
    et sur pack.lmnp_criteria_links → criterion.
    """
    project = (
        db.query(Project)
        .options(
            joinedload(Project.property),
            joinedload(Project.pack)
                .joinedload(Pack.rooms)
                .joinedload(Room.items)
                .joinedload(PackItem.retailer),
            joinedload(Project.pack)
                .joinedload(Pack.lmnp_criteria_links)
                .joinedload(PackLmnpCriterion.criterion),
        )
        .filter(Project.id == project_id)
        .first()
    )
    if not project:
        raise HTTPException(status_code=404, detail="Projet introuvable.")
    if not project.property:
        raise HTTPException(status_code=404, detail="Propriété introuvable pour ce projet.")
    if not project.pack:
        raise HTTPException(status_code=404, detail="Pack non encore généré pour ce projet.")
    return project


# ─────────────────────────────────────────────────────────────────────────────
# POST /projects — création + génération
# ─────────────────────────────────────────────────────────────────────────────

@router.post("", response_model=ProjectPackResponse, status_code=201)
def create_project(
    payload: ProjectCreate,
    db: Session = Depends(get_db),
) -> ProjectPackResponse:
    """
    Flux principal Étape 1 → 2 :
    1. Crée Project (id + public_slug)
    2. Crée Property depuis payload.property
    3. Appelle generate_pack_for_property → Pack en base
    4. Retourne ProjectPackResponse (frontend Étape 2)
    """
    p = payload.property

    # ── Project ───────────────────────────────────────────────────────────────
    project_id  = str(uuid.uuid4())
    public_slug = _make_slug(city=p.city, prop_type=p.property_type, budget=p.budget_level)

    project = Project(id=project_id, public_slug=public_slug)
    db.add(project)
    db.flush()

    # ── Property ──────────────────────────────────────────────────────────────
    prop = Property(
        id=str(uuid.uuid4()),
        project_id=project_id,
        property_type=p.property_type,
        surface_m2=p.surface_m2,
        rooms_count=p.rooms_count,
        city=p.city,
        postal_code=p.postal_code,
        tenant_profile=p.tenant_profile,
        rental_type=p.rental_type,
        decor_style=p.decor_style,
        budget_level=p.budget_level,
        budget_min=p.budget_min,
        budget_max=p.budget_max,
    )
    db.add(prop)
    db.flush()

    # ── Pack ──────────────────────────────────────────────────────────────────
    try:
        generate_pack_for_property(db=db, project_id=project_id, property=prop)
    except Exception as exc:
        db.rollback()
        logger.exception("Échec génération pack pour project %s", project_id)
        raise HTTPException(
            status_code=503,
            detail={
                "message": "L'IA n'a pas pu générer votre pack. Veuillez réessayer.",
                "retry": True,
            },
        ) from exc

    db.commit()

    # Rechargement explicite pour que les relations soient disponibles
    db.refresh(project)
    return _build_project_pack_response(project)


# ─────────────────────────────────────────────────────────────────────────────
# GET /projects/{id}/pack  — alias explicite (Étape 2 rafraîchissement)
# Déclaré AVANT /{id} pour éviter la capture du path parameter
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/{project_id}/pack", response_model=ProjectPackResponse)
def get_project_pack(
    project_id: str,
    db: Session = Depends(get_db),
) -> ProjectPackResponse:
    """GET /projects/{id}/pack — retourne ProjectPackResponse (Étape 2)."""
    project = _get_project_or_404(project_id, db)
    return _build_project_pack_response(project)


# ─────────────────────────────────────────────────────────────────────────────
# GET /projects/{id}/retailers — vue enseignes (Étape 3)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/{project_id}/retailers", response_model=RetailersResponse)
def get_project_retailers(
    project_id: str,
    db: Session = Depends(get_db),
) -> RetailersResponse:
    """
    Regroupe les PackItems par enseigne, triés par sous-total décroissant.
    Calcule essential_count / comfort_count par enseigne.
    """
    project = _get_project_or_404(project_id, db)
    pack    = project.pack
    prop    = project.property

    # Index room_id → label
    room_labels: Dict[str, str] = {r.id: r.label for r in pack.rooms}

    # Groupement par enseigne
    by_retailer: Dict[str, dict] = {}

    for room in pack.rooms:
        for item in room.items:
            rname = item.retailer.name
            rid   = item.retailer.id

            if rid not in by_retailer:
                by_retailer[rid] = {
                    "retailer_id": rid,
                    "name":        rname,
                    "website_url": item.retailer.website_url,
                    "subtotal":    0,
                    "items":       [],
                }

            by_retailer[rid]["subtotal"]    += item.total_price
            by_retailer[rid]["items"].append(
                RetailerItemOut(
                    item_id=item.id,
                    room_label=room_labels.get(item.room_id, ""),
                    name=item.name,
                    reference=item.reference,
                    tag_type=item.tag_type,
                    unit_price=item.unit_price,
                    quantity=item.quantity,
                    total_price=item.total_price,
                    product_url=item.product_url,
                )
            )

    # Tri par sous-total DESC + calcul essential/comfort
    retailers_out: List[RetailerBlockOut] = []
    for r in sorted(by_retailer.values(), key=lambda x: x["subtotal"], reverse=True):
        ess = sum(1 for i in r["items"] if i.tag_type == "essentiel_lmnp")
        cft = len(r["items"]) - ess
        retailers_out.append(
            RetailerBlockOut(
                retailer_id=r["retailer_id"],
                name=r["name"],
                website_url=r["website_url"],
                subtotal=r["subtotal"],
                item_count=len(r["items"]),
                essential_count=ess,
                comfort_count=cft,
                items=sorted(r["items"], key=lambda i: (i.room_label, i.name)),
            )
        )

    total_items = sum(len(r.items) for r in retailers_out)

    return RetailersResponse(
        total_amount=pack.total_price,
        retailer_count=len(retailers_out),
        item_count=total_items,
        order_count=len(retailers_out),
        is_lmnp_compliant=pack.is_lmnp_compliant,
        retailers=retailers_out,
    )


# ─────────────────────────────────────────────────────────────────────────────
# GET /projects/{id}/summary — résumé Étape 4
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/{project_id}/summary", response_model=SummaryResponse)
def get_project_summary(
    project_id: str,
    db: Session = Depends(get_db),
) -> SummaryResponse:
    """Résumé financier + conformité + répartition enseignes pour l'Étape 4."""
    project = _get_project_or_404(project_id, db)
    pack    = project.pack
    prop    = project.property

    # Répartition par enseigne (sous-totaux uniquement)
    retailer_totals: Dict[str, int] = defaultdict(int)
    for item in pack.items:
        retailer_totals[item.retailer.name] += item.total_price

    retailers_summary = [
        RetailerSummaryLine(name=name, subtotal=total)
        for name, total in sorted(retailer_totals.items(), key=lambda x: -x[1])
    ]

    return SummaryResponse(
        project_id=project.id,
        public_slug=project.public_slug,
        total_amount=pack.total_price,
        budget_max=prop.budget_max,
        savings_amount=pack.savings_amount,
        is_lmnp_compliant=pack.is_lmnp_compliant,
        retailers_summary=retailers_summary,
        lmnp_checklist=_build_lmnp_checklist(pack),
    )


# ─────────────────────────────────────────────────────────────────────────────
# GET /projects/{id}  — point d'entrée URL partageable
# Déclaré EN DERNIER (après /pack, /retailers, /summary)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/{project_id}", response_model=ProjectPackResponse)
def get_project(
    project_id: str,
    db: Session = Depends(get_db),
) -> ProjectPackResponse:
    """GET /projects/{id} — URL partageable, retourne ProjectPackResponse."""
    project = _get_project_or_404(project_id, db)
    return _build_project_pack_response(project)
