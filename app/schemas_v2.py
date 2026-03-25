"""
app/schemas_v2.py — Schemas Pydantic alignés sur models.py + frontend v13

Nomenclature :
  *Create  → payload reçu du frontend (POST /projects)
  *Out     → réponse envoyée au frontend
  ProjectPackResponse → forme principale réutilisée pour POST + GET /projects/{id}/pack

Alignement frontend :
  PropertyCreateInput  ↔ PropertyCreate
  ProjectPackResponse  ↔ ProjectPackResponse (même nom, même shape)
  tag_type             → "essentiel_lmnp" | "confort"  (PackItemOut)
  c.code               → LmnpCriterionStatus.code
"""

from __future__ import annotations
from typing import List, Literal, Optional
from pydantic import BaseModel, Field, model_validator

# Valeurs autorisées pour tag_type — validées automatiquement par Pydantic
TagType = Literal["essentiel_lmnp", "confort"]


# ─────────────────────────────────────────────────────────────────────────────
# INPUT — POST /projects
# Correspond à PropertyCreateInput côté TypeScript
# ─────────────────────────────────────────────────────────────────────────────

class PropertyCreate(BaseModel):
    """
    Description du bien saisie à l'Étape 1.
    Champs calqués sur models.Property (snake_case SQLAlchemy).
    """
    property_type:  str            # T2, studio, coloc…
    surface_m2:     float          = Field(..., ge=5, le=500)
    rooms_count:    int            = Field(..., ge=1, le=10)

    city:           str            = Field(..., min_length=1)
    postal_code:    str            = Field(..., min_length=4, max_length=10)

    tenant_profile: str            # etudiant, jeune_actif, famille…
    rental_type:    Optional[str]  = None   # longue_duree / courte_duree
    decor_style:    Optional[str]  = None   # contemporain, scandinave…

    budget_level:   str            # economique / standard / premium
    budget_min:     Optional[int]  = None
    budget_max:     Optional[int]  = None

    @model_validator(mode="after")
    def budget_coherent(self) -> "PropertyCreate":
        if self.budget_min is not None and self.budget_max is not None:
            if self.budget_max < self.budget_min:
                raise ValueError("budget_max doit être ≥ budget_min")
        return self


class ProjectCreate(BaseModel):
    """Corps de POST /projects — enveloppe autour de PropertyCreate."""
    property: PropertyCreate


# ─────────────────────────────────────────────────────────────────────────────
# OUTPUT — GET /projects/{id}/pack + POST /projects
# ─────────────────────────────────────────────────────────────────────────────

class LmnpCriterionStatus(BaseModel):
    """
    Un critère de conformité LMNP.
    code  → clé stable (ex: "couchage") — utilisé par le frontend via c.code
    label → libellé affiché (ex: "Couchage (lit + matelas)")
    """
    code:       str
    label:      str
    is_covered: bool


class PackItemOut(BaseModel):
    """
    Ligne item pour l'affichage Étape 2 + Étape 3.
    tag_type → "essentiel_lmnp" | "confort"  (remplace is_lmnp_mandatory)
    retailer → nom de l'enseigne dénormalisé (string)
    """
    id:          str
    name:        str
    reference:   Optional[str] = None
    retailer:    str                    # nom enseigne (dénormalisé)
    tag_type:    TagType                # validé par Pydantic : "essentiel_lmnp" | "confort"
    unit_price:  int
    quantity:    int
    total_price: int
    product_url: Optional[str] = None


class RoomOut(BaseModel):
    """
    Pièce avec ses items — Étape 2.
    room_type → clé stable (chambre, sejour, cuisine, sdb…)
    label     → libellé affiché (vient du catalogue)
    """
    id:                    str
    room_type:             str
    label:                 str
    mandatory_items_count: int
    total_price:           int
    items:                 List[PackItemOut]


class PropertyOut(BaseModel):
    """Rappel du brief — intégré dans ProjectPackResponse."""
    property_type:  str
    surface_m2:     float
    rooms_count:    int
    city:           str
    postal_code:    str
    tenant_profile: str
    rental_type:    Optional[str] = None
    decor_style:    Optional[str] = None
    budget_level:   str
    budget_min:     Optional[int] = None
    budget_max:     Optional[int] = None


class PackOut(BaseModel):
    """
    Pack complet avec pièces et checklist LMNP.
    rooms[]         → RoomOut[]           (dans PackOut, pas à la racine)
    lmnp_checklist  → LmnpCriterionStatus[] (dans PackOut)
    """
    id:                str
    total_price:       int
    is_lmnp_compliant: bool
    savings_amount:    Optional[int]   = None
    savings_percent:   Optional[float] = None
    rooms:             List[RoomOut]
    lmnp_checklist:    List[LmnpCriterionStatus]


class ProjectPackResponse(BaseModel):
    """
    Réponse principale — réutilisée pour :
      POST /projects
      GET  /projects/{id}
      GET  /projects/{id}/pack

    Shape attendue côté frontend v13 :
      data.project_id, data.public_slug
      data.property   → PropertyOut
      data.pack       → PackOut { rooms[], lmnp_checklist[] }
    """
    project_id:  str
    public_slug: str
    property:    PropertyOut
    pack:        PackOut


# ─────────────────────────────────────────────────────────────────────────────
# OUTPUT — GET /projects/{id}/retailers  (Étape 3)
# ─────────────────────────────────────────────────────────────────────────────

class RetailerItemOut(BaseModel):
    """Ligne item enrichie pour la vue enseigne — inclut room_label."""
    item_id:     str
    room_label:  str           # libellé de la pièce (dénormalisé)
    name:        str
    reference:   Optional[str] = None
    tag_type:    TagType       # validé par Pydantic : "essentiel_lmnp" | "confort"
    unit_price:  int
    quantity:    int
    total_price: int
    product_url: Optional[str] = None


class RetailerBlockOut(BaseModel):
    """Bloc enseigne — Étape 3."""
    retailer_id:     str
    name:            str
    website_url:     Optional[str] = None
    subtotal:        int
    item_count:      int
    essential_count: int    # items tag_type == "essentiel_lmnp"
    comfort_count:   int    # items tag_type == "confort"
    items:           List[RetailerItemOut]


class RetailersResponse(BaseModel):
    """Réponse de GET /projects/{id}/retailers."""
    total_amount:      int
    retailer_count:    int
    item_count:        int
    order_count:       int
    is_lmnp_compliant: bool
    retailers:         List[RetailerBlockOut]  # triés par subtotal DESC


# ─────────────────────────────────────────────────────────────────────────────
# OUTPUT — GET /projects/{id}/summary  (Étape 4)
# ─────────────────────────────────────────────────────────────────────────────

class RetailerSummaryLine(BaseModel):
    name:     str
    subtotal: int


class SummaryResponse(BaseModel):
    """Réponse de GET /projects/{id}/summary."""
    project_id:        str
    public_slug:       str
    total_amount:      int
    budget_max:        Optional[int] = None
    savings_amount:    Optional[int] = None
    is_lmnp_compliant: bool
    retailers_summary: List[RetailerSummaryLine]   # triés par subtotal DESC
    lmnp_checklist:    List[LmnpCriterionStatus]
