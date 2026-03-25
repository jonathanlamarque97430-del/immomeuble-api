"""
app/services/packs.py — Logique de génération et projection du pack LMNP

Deux responsabilités :

1. _mock_generate_pack(prop) → PackDomain
   Génère un pack LMNP complet conforme décret 2015-981.
   Remplacé par generate_pack_via_llm() en Phase 2 sans changer les appelants.

2. build_pack_screen_response(prop, pack) → PackScreenResponse
   Projette les modèles domaine vers la vue frontend (écran Étape 2/4).
   Calcule : totaux par pièce, résumé global, conformité LMNP, brands mock.

Séparation intentionnelle :
   generate_pack_for_property() = point d'entrée public → appelé par le router
   build_pack_screen_response() = projection → peut être recalculée à tout moment
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import uuid4

from app.schemas import (
    LmnpChecklist,
    LmnpStatus,
    MerchantBlock,
    MerchantBreakdownResponse,
    MerchantItem,
    MerchantSummary,
    PackDomain,
    PackItemDomain,
    PackScreenBrand,
    PackScreenItem,
    PackScreenProperty,
    PackScreenResponse,
    PackScreenRoom,
    PackSummary,
    PropertyRead,
    RoomDomain,
)

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Constantes LMNP (décret 2015-981)
# ─────────────────────────────────────────────────────────────────────────────

# Toutes les catégories obligatoires
LMNP_MANDATORY_CATEGORIES: set[str] = {
    "literie",
    "occultation",
    "rangement",
    "plaques_cuisson",
    "four_microondes",
    "refrigerateur",
    "vaisselle",
    "ustensiles",
    "table",
    "chaises",
    "luminaires",
    "entretien",
    # "equipements_sdb",  # recommandé mais pas bloquant pour la conformité légale
}

# Libellés pour la checklist frontend
LMNP_CATEGORY_LABELS: dict[str, str] = {
    "literie":         "couchage",
    "occultation":     "occultation",
    "rangement":       "rangements",
    "plaques_cuisson": "plaques_cuisson",
    "four_microondes": "four_ou_microondes",
    "refrigerateur":   "refrigerateur",
    "vaisselle":       "vaisselle",
    "ustensiles":      "ustensiles_cuisine",
    "table":           "table_chaises",
    "chaises":         "table_chaises",
    "luminaires":      "luminaires",
    "entretien":       "entretien",
    "equipements_sdb": "equipements_sdb",
}

# Marques mock par catégorie (remplacé par sourcing réel en Phase 3)
# Deux références par catégorie : brands[0] = principale, brands[1] = alternative
_MOCK_BRANDS: dict[str, list[dict]] = {
    "literie": [
        {"brand": "IKEA",              "label": "MALM / MINNESUND"},
        {"brand": "But",               "label": "KYOTO / CONFORT+"},
    ],
    "occultation": [
        {"brand": "IKEA",              "label": "MAJGULL"},
        {"brand": "But",               "label": "BLACKOUT"},
    ],
    "rangement": [
        {"brand": "But",               "label": "OSLO"},
        {"brand": "IKEA",              "label": "PAX"},
    ],
    "plaques_cuisson": [
        {"brand": "Boulanger",         "label": "WHIRLPOOL 60cm"},
        {"brand": "Darty",             "label": "BOSCH Serie 4"},
    ],
    "four_microondes": [
        {"brand": "Boulanger",         "label": "WHIRLPOOL MW 20L"},
        {"brand": "Darty",             "label": "SAMSUNG Grill 25L"},
    ],
    "refrigerateur": [
        {"brand": "Boulanger",         "label": "SAMSUNG 250L"},
        {"brand": "Darty",             "label": "BOSCH Combi 280L"},
    ],
    "vaisselle": [
        {"brand": "IKEA",              "label": "DINERA"},
        {"brand": "Maison du Monde",   "label": "ESSENTIEL 4p"},
    ],
    "ustensiles": [
        {"brand": "IKEA",              "label": "KAVALKAD"},
        {"brand": "Tefal",             "label": "Starter cuisine"},
    ],
    "table": [
        {"brand": "IKEA",              "label": "EKEDALEN"},
        {"brand": "Maisons du Monde",  "label": "NILS 4p"},
    ],
    "chaises": [
        {"brand": "But",               "label": "NORDIKA"},
        {"brand": "IKEA",              "label": "ADDE"},
    ],
    "luminaires": [
        {"brand": "IKEA",              "label": "RANARP"},
        {"brand": "Leroy Merlin",      "label": "Pack spots + lampadaire"},
    ],
    "entretien": [
        {"brand": "Leroy Merlin",      "label": "Set entretien"},
        {"brand": "Carrefour",         "label": "Kit ménage complet"},
    ],
    "seating": [
        {"brand": "Maisons du Monde",  "label": "OSLO 2-3 places"},
        {"brand": "IKEA",              "label": "KLIPPAN"},
    ],
    "equipements_sdb": [
        {"brand": "IKEA",              "label": "GODMORGON"},
        {"brand": "Leroy Merlin",      "label": "Pack accessoires SDB"},
    ],
}

# Items par type de pièce et niveau de gamme
_GAMME_MULT: dict[str, float] = {"economique": 0.70, "standard": 1.0, "premium": 1.65}

def _items(dicts: list[dict], gamme: str) -> list[dict]:
    m = _GAMME_MULT.get(gamme, 1.0)
    return [{**d, "unit_budget_min": round(d["unit_budget_min"] * m), "unit_budget_max": round(d["unit_budget_max"] * m)} for d in dicts]

_BEDROOM_ITEMS = [
    dict(category="literie",     name="Lit 140×200 avec sommier et matelas",    quantity=1, priority="mandatory",   unit_budget_min=250, unit_budget_max=500),
    dict(category="occultation", name="Rideaux occultants",                      quantity=1, priority="mandatory",   unit_budget_min=50,  unit_budget_max=120),
    dict(category="rangement",   name="Armoire 2 portes",                        quantity=1, priority="mandatory",   unit_budget_min=150, unit_budget_max=300),
    # Recommandés — n'affectent pas la conformité LMNP (mandatory uniquement)
    dict(category="luminaires",  name="Lampe de chevet",                         quantity=1, priority="recommended", unit_budget_min=25,  unit_budget_max=60),
    dict(category="rangement",   name="Table de chevet avec tiroir",             quantity=1, priority="recommended", unit_budget_min=40,  unit_budget_max=90),
    dict(category="table",       name="Petit bureau d'appoint",                  quantity=1, priority="recommended", unit_budget_min=70,  unit_budget_max=150),
    dict(category="chaises",     name="Chaise de bureau",                        quantity=1, priority="recommended", unit_budget_min=40,  unit_budget_max=100),
]

_LIVING_ITEMS = [
    dict(category="table",       name="Table à manger 4 personnes",              quantity=1, priority="mandatory",   unit_budget_min=100, unit_budget_max=250),
    dict(category="chaises",     name="Chaises",                                 quantity=4, priority="mandatory",   unit_budget_min=25,  unit_budget_max=70),
    dict(category="luminaires",  name="Luminaires (suspension + liseuse)",       quantity=2, priority="mandatory",   unit_budget_min=35,  unit_budget_max=100),
    dict(category="seating",     name="Canapé 2-3 places",                       quantity=1, priority="recommended", unit_budget_min=300, unit_budget_max=700),
    # Recommandés
    dict(category="seating",     name="Fauteuil d'appoint",                      quantity=1, priority="recommended", unit_budget_min=120, unit_budget_max=250),
    dict(category="rangement",   name="Meuble TV / rangements bas",              quantity=1, priority="recommended", unit_budget_min=80,  unit_budget_max=200),
    dict(category="rangement",   name="Étagères murales",                        quantity=1, priority="recommended", unit_budget_min=40,  unit_budget_max=100),
    dict(category="entretien",   name="Tapis de salon",                          quantity=1, priority="recommended", unit_budget_min=60,  unit_budget_max=180),
]

_KITCHEN_ITEMS = [
    dict(category="plaques_cuisson", name="Plaques de cuisson vitrocéramique",   quantity=1, priority="mandatory",   unit_budget_min=80,  unit_budget_max=250),
    dict(category="four_microondes", name="Micro-ondes",                         quantity=1, priority="mandatory",   unit_budget_min=50,  unit_budget_max=150),
    dict(category="refrigerateur",   name="Réfrigérateur avec congélateur",      quantity=1, priority="mandatory",   unit_budget_min=200, unit_budget_max=600),
    dict(category="vaisselle",       name="Vaisselle & couverts (service 4 p.)", quantity=1, priority="mandatory",   unit_budget_min=40,  unit_budget_max=120),
    dict(category="ustensiles",      name="Ustensiles de cuisine",               quantity=1, priority="mandatory",   unit_budget_min=30,  unit_budget_max=80),
    dict(category="entretien",       name="Matériel d'entretien ménager",        quantity=1, priority="mandatory",   unit_budget_min=30,  unit_budget_max=70),
    # Recommandés
    dict(category="ustensiles",      name="Petit électroménager (bouilloire, grille-pain)", quantity=1, priority="recommended", unit_budget_min=60, unit_budget_max=150),
    dict(category="entretien",       name="Poubelle de cuisine",                 quantity=1, priority="recommended", unit_budget_min=30,  unit_budget_max=70),
    dict(category="rangement",       name="Rangements / étagères cuisine",       quantity=1, priority="recommended", unit_budget_min=40,  unit_budget_max=100),
]

_SDB_ITEMS = [
    dict(category="equipements_sdb", name="Miroir + tablette salle de bain",    quantity=1, priority="recommended", unit_budget_min=60,  unit_budget_max=180),
    dict(category="equipements_sdb", name="Porte-serviettes & accessoires",     quantity=1, priority="recommended", unit_budget_min=30,  unit_budget_max=80),
    # Recommandés
    dict(category="equipements_sdb", name="Tapis de bain",                      quantity=1, priority="recommended", unit_budget_min=20,  unit_budget_max=50),
    dict(category="equipements_sdb", name="Set salle de bain (gobelet, porte-savon, distributeur)", quantity=1, priority="recommended", unit_budget_min=25, unit_budget_max=60),
]


# ─────────────────────────────────────────────────────────────────────────────
# 1. Génération mock du pack domaine
# ─────────────────────────────────────────────────────────────────────────────

def _make_item(d: dict) -> PackItemDomain:
    return PackItemDomain(id=str(uuid4()), **d)


def _mock_generate_pack(prop: PropertyRead) -> PackDomain:
    """
    Génère un PackDomain LMNP complet en mode mock (sans LLM).
    Couvre les 12 catégories obligatoires du décret 2015-981.

    Phase 2 : remplacer cet appel dans generate_pack_for_property()
    par await generate_pack_via_llm(prop) depuis llm_service.py.
    """
    gamme  = prop.niveau_gamme
    rooms: list[RoomDomain] = []

    nb_chambres = max(1, prop.nb_pieces - 1)
    for i in range(nb_chambres):
        rooms.append(RoomDomain(
            id=str(uuid4()),
            type="bedroom",
            name=f"Chambre {i + 1}" if nb_chambres > 1 else "Chambre",
            surface_estimated=round(prop.surface_totale * 0.25),
            items=[_make_item(d) for d in _items(_BEDROOM_ITEMS, gamme)],
        ))

    rooms.append(RoomDomain(
        id=str(uuid4()),
        type="living_room",
        name="Séjour",
        surface_estimated=round(prop.surface_totale * 0.35),
        items=[_make_item(d) for d in _items(_LIVING_ITEMS, gamme)],
    ))

    rooms.append(RoomDomain(
        id=str(uuid4()),
        type="kitchen",
        name="Cuisine",
        surface_estimated=round(prop.surface_totale * 0.15),
        items=[_make_item(d) for d in _items(_KITCHEN_ITEMS, gamme)],
    ))

    if prop.surface_totale >= 30:
        rooms.append(RoomDomain(
            id=str(uuid4()),
            type="bathroom",
            name="Salle de bain",
            surface_estimated=round(prop.surface_totale * 0.10),
            items=[_make_item(d) for d in _items(_SDB_ITEMS, gamme)],
        ))

    total = round(sum(r.room_total_cost for r in rooms), 2)

    return PackDomain(
        id=str(uuid4()),
        property_id=prop.id,
        total_cost_estimated=total,
        currency="EUR",
        notes=(
            f"Pack LMNP — {prop.type_de_bien} {prop.surface_totale}m² "
            f"— {prop.niveau_gamme} — {prop.cible_locataire} à {prop.localisation_ville}."
        ),
        rooms=rooms,
        created_at=datetime.now(timezone.utc),
        version=1,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 2. Conformité LMNP
# ─────────────────────────────────────────────────────────────────────────────

def _compute_lmnp_checklist(pack: PackDomain) -> LmnpChecklist:
    """Calcule la checklist de conformité LMNP depuis le PackDomain."""
    found_categories: set[str] = {
        item.category
        for room in pack.rooms
        for item in room.items
        if item.priority == "mandatory"
    }

    covered_labels  = sorted({LMNP_CATEGORY_LABELS.get(c, c) for c in found_categories & LMNP_MANDATORY_CATEGORIES})
    missing_raw     = LMNP_MANDATORY_CATEGORIES - found_categories
    missing_labels  = sorted({LMNP_CATEGORY_LABELS.get(c, c) for c in missing_raw})

    if not missing_labels:
        status: LmnpStatus = "compliant"
        notes = "Pack entièrement conforme au décret LMNP 2015-981."
    elif len(missing_labels) <= 2:
        status = "ok_with_minor_missing"
        notes  = f"Éléments mineurs manquants : {', '.join(missing_labels)}."
    else:
        status = "non_compliant"
        notes  = f"Catégories obligatoires manquantes : {', '.join(missing_labels)}."

    return LmnpChecklist(
        categories_covered=covered_labels,
        categories_missing=missing_labels,
        global_status=status,
        notes=notes,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 3. Projection → PackScreenResponse (vue frontend)
# ─────────────────────────────────────────────────────────────────────────────

def _screen_item(item: PackItemDomain) -> PackScreenItem:
    brands = [PackScreenBrand(**b) for b in _MOCK_BRANDS.get(item.category, [])]
    return PackScreenItem(
        item_id=item.id,
        category=item.category,
        name=item.name,
        priority=item.priority,
        quantity=item.quantity,
        unit_price=item.unit_price_estimated,
        total_price=item.total_price_estimated,
        brands=brands,
        is_lmnp_mandatory=(item.category in LMNP_MANDATORY_CATEGORIES and item.priority == "mandatory"),
        notes=item.notes,
    )


def _screen_room(room: RoomDomain) -> PackScreenRoom:
    return PackScreenRoom(
        room_id=room.id,
        type=room.type,
        name=room.name,
        surface_estimated=room.surface_estimated,
        room_total_cost=room.room_total_cost,
        items=[_screen_item(i) for i in room.items],
    )


def build_pack_screen_response(prop: PropertyRead, pack: PackDomain) -> PackScreenResponse:
    """
    Projette (PropertyRead, PackDomain) → PackScreenResponse.

    Calcule :
    - totaux par pièce et item
    - résumé global (économie vs budget, conformité)
    - checklist LMNP détaillée
    - marques mock (remplacées par sourcing réel en Phase 3)

    Cette fonction est pure (pas d'effets de bord) : peut être appelée
    à tout moment pour re-générer la vue sans toucher à la base.
    """
    checklist = _compute_lmnp_checklist(pack)

    budget_total = prop.budget_total
    economy      = round(prop.budget_max - pack.total_cost_estimated, 2)
    economy_pct  = round((economy / prop.budget_max) * 100, 1) if prop.budget_max else 0.0

    cible_label = {
        "etudiant":      "étudiant",
        "jeune_actif":   "jeune actif",
        "famille":       "famille",
        "courte_duree":  "courte durée",
        "professionnel": "professionnel",
    }.get(prop.cible_locataire, prop.cible_locataire)

    title = (
        f"Optimisé pour {cible_label} à {prop.localisation_ville} — "
        f"{prop.type_de_bien} {prop.surface_totale} m² · "
        f"{prop.niveau_gamme.capitalize()} · "
        f"{pack.total_cost_estimated:,.0f} €".replace(",", " ")
    )

    return PackScreenResponse(
        project_id=f"proj_{prop.id[:8]}",
        pack_id=pack.id,
        step=2,
        property=PackScreenProperty(
            type_de_bien=prop.type_de_bien,
            surface_totale=prop.surface_totale,
            nb_pieces=prop.nb_pieces,
            ville=prop.localisation_ville,
            code_postal=prop.localisation_code_postal,
            cible_locataire=prop.cible_locataire,
            style_souhaite=prop.style_souhaite,
            niveau_gamme=prop.niveau_gamme,
            budget_total=budget_total,
            budget_min=prop.budget_min,
            budget_max=prop.budget_max,
        ),
        pack_summary=PackSummary(
            title=title,
            total_cost_estimated=pack.total_cost_estimated,
            currency=pack.currency,
            lmnp_compliant=(checklist.global_status == "compliant"),
            lmnp_missing_categories=checklist.categories_missing,
            lmnp_missing_items_example=[],   # Phase 2 : enrichi par LLM
            economy_vs_budget=economy,
            economy_vs_budget_percent=economy_pct,
        ),
        rooms=[_screen_room(r) for r in pack.rooms],
        lmnp_checklist=checklist,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Point d'entrée public
# ─────────────────────────────────────────────────────────────────────────────

def generate_pack_for_property(prop: PropertyRead) -> tuple[PackDomain, PackScreenResponse]:
    """
    Génère le pack domaine ET la vue écran en une seule opération.

    Retourne (PackDomain, PackScreenResponse) :
    - PackDomain       → persisté en mémoire (puis SQL en Phase 2)
    - PackScreenResponse → renvoyé directement au frontend

    Phase 2 — pour brancher le LLM :
      Remplacer _mock_generate_pack(prop) par :
        pack = await generate_pack_via_llm(prop)  # depuis llm_service.py
      et rendre cette fonction async.
    """
    logger.info(
        "Generating pack — %s %sm² %s %s",
        prop.type_de_bien, prop.surface_totale, prop.niveau_gamme, prop.localisation_ville,
    )
    pack   = _mock_generate_pack(prop)
    screen = build_pack_screen_response(prop, pack)
    logger.info(
        "Pack generated — id=%s rooms=%d total=%.0f€ lmnp=%s",
        pack.id, len(pack.rooms), pack.total_cost_estimated, screen.lmnp_checklist.global_status,
    )
    return pack, screen


# ─────────────────────────────────────────────────────────────────────────────
# Projection Étape 3 — MerchantBreakdownResponse
# ─────────────────────────────────────────────────────────────────────────────

def build_merchant_breakdown(
    prop: PropertyRead,
    pack: PackDomain,
    checklist: LmnpChecklist,
) -> MerchantBreakdownResponse:
    """
    Projette (PropertyRead, PackDomain, LmnpChecklist) → MerchantBreakdownResponse.

    Algorithme :
    1. Pour chaque (room, item) → déterminer l'enseigne via _MOCK_BRANDS[item.category].
    2. Agréger les MerchantItem par merchant_name.
    3. Calculer merchant_subtotal pour chaque enseigne.
    4. Trier les enseignes par subtotal DESC, les items par (room_name, item_name).
    5. Construire le résumé global.

    Fonction pure — pas d'effets de bord, rappelable à tout moment depuis un PackDomain existant.
    Phase 3 : remplacer _MOCK_BRANDS par un vrai catalogue (reference, url, prix réels).
    """
    # ── Étape 1 & 2 : attribuer chaque item à une enseigne ────────────────────
    by_merchant: dict[str, list[MerchantItem]] = {}

    for room in pack.rooms:
        for item in room.items:
            brands = _MOCK_BRANDS.get(item.category, [])
            if brands:
                merchant_name = brands[0]["brand"]
                # Préférer le label enseigne pour le nom produit affiché
                product_label = brands[0].get("label")
                item_name = f"{item.name} — {product_label}" if product_label else item.name
                url = brands[0].get("url") or None
            else:
                merchant_name = "Autres"
                item_name     = item.name
                url           = None

            merchant_item = MerchantItem(
                room_name=room.name,
                item_id=item.id,
                item_name=item_name,
                quantity=item.quantity,
                unit_price=item.unit_price_estimated,
                total_price=item.total_price_estimated,
                reference=None,   # Phase 3 : référence catalogue
                url=url,
            )

            if merchant_name not in by_merchant:
                by_merchant[merchant_name] = []
            by_merchant[merchant_name].append(merchant_item)

    # ── Étape 3 & 4 : construire les MerchantBlock triés ─────────────────────
    merchant_blocks: list[MerchantBlock] = []

    for merchant_name, items in by_merchant.items():
        # Tri items : room_name puis item_name (lexicographique)
        sorted_items = sorted(items, key=lambda i: (i.room_name, i.item_name))
        subtotal     = round(sum(i.total_price for i in sorted_items), 2)

        merchant_blocks.append(MerchantBlock(
            merchant_name=merchant_name,
            merchant_logo=None,        # Phase 3 : URL logo enseigne
            items=sorted_items,
            merchant_subtotal=subtotal,
        ))

    # Trier les enseignes par sous-total décroissant
    merchant_blocks.sort(key=lambda b: b.merchant_subtotal, reverse=True)

    # ── Étape 5 : résumé global ───────────────────────────────────────────────
    total_amount  = round(sum(b.merchant_subtotal for b in merchant_blocks), 2)
    total_items   = sum(len(b.items) for b in merchant_blocks)

    summary = MerchantSummary(
        total_amount=total_amount,
        total_merchants=len(merchant_blocks),
        total_items=total_items,
        lmnp_status=checklist.global_status,
        lmnp_missing_categories=checklist.categories_missing,
    )

    logger.info(
        "Merchant breakdown — pack=%s merchants=%d items=%d total=%.0f€",
        pack.id, len(merchant_blocks), total_items, total_amount,
    )

    return MerchantBreakdownResponse(
        project_id=f"proj_{prop.id[:8]}",
        pack_id=pack.id,
        step=3,
        merchants=merchant_blocks,
        summary=summary,
    )
