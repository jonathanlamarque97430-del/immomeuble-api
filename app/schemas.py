"""
app/schemas.py — Modèles Pydantic IMMOMEUBLE MVP

Trois familles de modèles :

1. DOMAINE (Property, Pack, Room, PackItem)
   → représentent les entités métier stockées / manipulées côté serveur.
   → serviront de base pour le mapping SQL (SQLAlchemy) en Phase 2.

2. VUE ÉTAPE 2 (PackScreenResponse et sous-modèles)
   → adaptés à l'écran "Votre pack LMNP" (Étape 2/4) du frontend.
   → calculés à partir des modèles domaine par le service packs.py.
   → contiennent des champs dénormalisés (totaux par pièce, checklist LMNP, etc.).

3. VUE ÉTAPE 3 (MerchantBreakdownResponse et sous-modèles)
   → vue "Sourcing par enseigne" (Étape 3/4).
   → projection du même PackDomain regroupée par enseigne.
   → exposée via GET /packs/{pack_id}/merchants.

Évolution prévue :
- Phase 2 : brancher LLM à la place de _mock_generate_pack_for_property.
- Phase 3 : remplir MerchantItem.url + unit_price depuis le vrai catalogue produits.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

# ─────────────────────────────────────────────────────────────────────────────
# Enums (Literal — plus robustes que pattern= en Pydantic v2)
# ─────────────────────────────────────────────────────────────────────────────

CibleLocataire = Literal["etudiant", "jeune_actif", "famille", "courte_duree", "professionnel"]
NiveauGamme    = Literal["economique", "standard", "premium"]
PriorityLevel  = Literal["mandatory", "recommended", "optional"]
RoomType       = Literal["bedroom", "living_room", "kitchen", "bathroom", "entrance", "office", "balcony", "other"]
TypeLocation   = Literal["longue_duree", "courte_duree"]

LmnpStatus     = Literal["compliant", "ok_with_minor_missing", "non_compliant"]

# ─────────────────────────────────────────────────────────────────────────────
# DOMAINE — Property
# ─────────────────────────────────────────────────────────────────────────────

class PropertyBase(BaseModel):
    """Paramètres saisis par l'utilisateur (entrée formulaire)."""

    model_config = ConfigDict(extra="forbid")

    type_de_bien:             str              = Field(..., min_length=1, description="Ex: studio, T1, T2, coloc")
    surface_totale:           float            = Field(..., ge=5,         description="Surface en m²")
    nb_pieces:                int              = Field(..., ge=1)
    cible_locataire:          CibleLocataire
    niveau_gamme:             NiveauGamme
    budget_min:               float            = Field(..., ge=0)
    budget_max:               float            = Field(..., ge=0)
    localisation_ville:       str              = Field(..., min_length=1)
    localisation_code_postal: str              = Field(..., min_length=4, max_length=10)
    style_souhaite:           Optional[str]    = None
    type_location:            Optional[TypeLocation] = None

    @model_validator(mode="after")
    def budget_coherent(self) -> PropertyBase:
        if self.budget_max < self.budget_min:
            raise ValueError(f"budget_max ({self.budget_max}) doit être ≥ budget_min ({self.budget_min})")
        return self

    @property
    def budget_total(self) -> float:
        """Budget indicatif central = milieu de la fourchette."""
        return round((self.budget_min + self.budget_max) / 2, 2)


class PropertyRead(PropertyBase):
    """Property persistée — ajoute id + created_at."""
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id:         str
    created_at: datetime


# ─────────────────────────────────────────────────────────────────────────────
# DOMAINE — Pack / Room / PackItem
# ─────────────────────────────────────────────────────────────────────────────

class PackItemDomain(BaseModel):
    """Item de mobilier/équipement — niveau domaine (stocké en base)."""

    model_config = ConfigDict(extra="forbid")

    id:              str
    category:        str           = Field(..., min_length=1)
    name:            str           = Field(..., min_length=1)
    quantity:        int           = Field(..., ge=1)
    priority:        PriorityLevel
    unit_budget_min: float         = Field(..., ge=0)
    unit_budget_max: float         = Field(..., ge=0)
    notes:           Optional[str] = None

    @model_validator(mode="after")
    def budget_range_valid(self) -> PackItemDomain:
        if self.unit_budget_max < self.unit_budget_min:
            raise ValueError(f"unit_budget_max < unit_budget_min pour '{self.name}'")
        return self

    @property
    def unit_price_estimated(self) -> float:
        """Prix unitaire moyen estimé."""
        return round((self.unit_budget_min + self.unit_budget_max) / 2, 2)

    @property
    def total_price_estimated(self) -> float:
        return round(self.unit_price_estimated * self.quantity, 2)


class RoomDomain(BaseModel):
    """Pièce — niveau domaine."""

    model_config = ConfigDict(extra="forbid")

    id:                str
    type:              RoomType
    name:              str              = Field(..., min_length=1)
    surface_estimated: Optional[float] = Field(default=None, ge=0)
    items:             List[PackItemDomain] = Field(..., min_length=1)

    @property
    def room_total_cost(self) -> float:
        return round(sum(i.total_price_estimated for i in self.items), 2)


class PackDomain(BaseModel):
    """Pack LMNP — niveau domaine (stocké en base)."""

    model_config = ConfigDict(extra="forbid")

    id:                   str
    property_id:          str
    total_cost_estimated: float            = Field(..., ge=0)
    currency:             str              = Field(default="EUR", min_length=3, max_length=3)
    notes:                Optional[str]    = None
    rooms:                List[RoomDomain] = Field(..., min_length=1)
    created_at:           datetime
    version:              int              = 1


# ─────────────────────────────────────────────────────────────────────────────
# VUE — PackScreenResponse (écran "Votre pack LMNP", Étape 2/4)
# ─────────────────────────────────────────────────────────────────────────────

class PackScreenProperty(BaseModel):
    """Contexte du bien pour l'affichage écran."""
    type_de_bien:     str
    surface_totale:   float
    nb_pieces:        int
    ville:            str
    code_postal:      str
    cible_locataire:  CibleLocataire
    style_souhaite:   Optional[str]
    niveau_gamme:     NiveauGamme
    budget_total:     float
    budget_min:       float
    budget_max:       float


class PackSummary(BaseModel):
    """Résumé global du pack pour l'en-tête de l'écran."""
    title:                       str
    total_cost_estimated:        float
    currency:                    str
    lmnp_compliant:              bool
    lmnp_missing_categories:     List[str]
    lmnp_missing_items_example:  List[str]
    economy_vs_budget:           float   # budget_max - total (négatif = dépassement)
    economy_vs_budget_percent:   float


class PackScreenBrand(BaseModel):
    """Référence enseigne/marque pour un item (sourcing simple — Phase 1)."""
    brand: str
    label: Optional[str] = None   # ex: "MALM / MINNESUND"
    url:   Optional[str] = None   # lien produit (Phase 3 — sourcing réel)


class PackScreenItem(BaseModel):
    """Item enrichi pour l'affichage écran (vue dénormalisée)."""
    item_id:          str
    category:         str
    name:             str
    priority:         PriorityLevel
    quantity:         int
    unit_price:       float         # moyenne (min+max)/2 — remplacé par prix réel en Phase 3
    total_price:      float
    brands:           List[PackScreenBrand] = Field(default_factory=list)
    is_lmnp_mandatory: bool
    notes:            Optional[str] = None


class PackScreenRoom(BaseModel):
    """Pièce enrichie pour l'affichage écran."""
    room_id:          str
    type:             RoomType
    name:             str
    surface_estimated: Optional[float]
    room_total_cost:  float
    items:            List[PackScreenItem]


class LmnpChecklist(BaseModel):
    """Checklist de conformité LMNP calculée post-génération."""
    categories_covered:  List[str]
    categories_missing:  List[str]
    global_status:       LmnpStatus
    notes:               Optional[str] = None

    @property
    def is_compliant(self) -> bool:
        """Raccourci pratique pour les tests / UI."""
        return self.global_status == "compliant"


class PackScreenResponse(BaseModel):
    """
    Réponse complète pour l'écran 'Votre pack LMNP' (POST /packs/generate).

    Contient :
    - project_id / step : métadonnées de navigation frontend
    - property          : contexte du bien (vue dénormalisée)
    - pack_summary      : résumé global (coût, conformité, économie)
    - rooms             : pièces avec items enrichis (prix, marques)
    - lmnp_checklist    : conformité détaillée par catégorie

    Distinct du modèle domaine PackDomain (stocké en base) :
    PackDomain = entité métier brute
    PackScreenResponse = projection calculée pour le frontend
    """
    project_id:   str
    pack_id:      str
    step:         int = 2
    property:     PackScreenProperty
    pack_summary: PackSummary
    rooms:        List[PackScreenRoom]
    lmnp_checklist: LmnpChecklist


# ─────────────────────────────────────────────────────────────────────────────
# VUE ÉTAPE 3 — MerchantBreakdownResponse (écran "Voir enseignes", Étape 3/4)
# ─────────────────────────────────────────────────────────────────────────────

class MerchantItem(BaseModel):
    """
    Ligne produit dans le récapitulatif par enseigne.

    - item_name  : nom enrichi (item.name + brand.label si disponible)
    - unit_price : prix unitaire estimé (moyenne budget_min/max) — remplacé par prix réel Phase 3
    - reference  : référence produit enseigne (Phase 3)
    - url        : lien produit cliquable (Phase 3)
    """
    room_name:   str
    item_id:     str
    item_name:   str
    quantity:    int             = Field(..., ge=1)
    unit_price:  float           = Field(..., ge=0)
    total_price: float           = Field(..., ge=0)
    reference:   Optional[str]  = None
    url:         Optional[str]  = None


class MerchantBlock(BaseModel):
    """
    Bloc pour une enseigne : nom, logo, items, sous-total.

    Trié par merchant_subtotal décroissant dans MerchantBreakdownResponse.
    Les items sont triés par (room_name, item_name).
    """
    merchant_name:     str
    merchant_logo:     Optional[str]       = None   # URL logo (Phase 3)
    items:             List[MerchantItem]  = Field(default_factory=list)
    merchant_subtotal: float               = Field(..., ge=0)


class MerchantSummary(BaseModel):
    """
    Résumé global de l'écran Étape 3/4.

    - total_amount     : doit refléter pack.total_cost_estimated (±arrondi)
    - total_items      : nombre de lignes items (pas somme des quantités)
    - lmnp_status      : réutilisé depuis LmnpChecklist (pas recalculé)
    """
    total_amount:              float
    total_merchants:           int
    total_items:               int
    lmnp_status:               LmnpStatus
    lmnp_missing_categories:   List[str]  = Field(default_factory=list)


class MerchantBreakdownResponse(BaseModel):
    """
    Vue complète pour l'écran Étape 3/4 « Voir enseignes ».
    Exposée via GET /packs/{pack_id}/merchants.

    Projection de PackDomain + LmnpChecklist → regroupement par enseigne.
    Même patron que PackScreenResponse : calculée à la demande, jamais stockée.

    merchants : liste des enseignes triées par merchant_subtotal DESC
    summary   : métriques globales + statut LMNP
    """
    project_id: str
    pack_id:    str
    step:       int = 3
    merchants:  List[MerchantBlock]
    summary:    MerchantSummary
