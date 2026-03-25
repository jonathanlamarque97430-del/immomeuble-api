"""
app/services/generator.py — Générateur de packs LMNP adaptatif

Moteur métier (Phase 1) :
  1. Profil typologique  : small / medium / large  (property_type + rooms_count)
  2. Pièces générées     : adaptées au profil
  3. Socle LMNP          : 11 critères toujours couverts
  4. Cible locataire     : items supplémentaires (etudiant / famille / courte_duree)
  5. Gamme               : multiplicateur prix + sélection items Confort
  6. Surface             : compact si < 22 m², rangements extra si grande surface

Sortie : identique à PackOut — rien ne change côté API / frontend.
Phase 2 : remplacer build_rooms_catalogue() par un appel LLM.
Phase 3 : enrichir unit_price et product_url depuis un vrai catalogue produits.
"""

from __future__ import annotations

import uuid
from copy import deepcopy
from typing import Dict, List, Set

from sqlalchemy.orm import Session

from app.models import (
    LmnpCriterion, Pack, PackItem, PackLmnpCriterion, Property, Retailer, Room,
)

# ══════════════════════════════════════════════════════════════════════
# CONSTANTES METIER
# ══════════════════════════════════════════════════════════════════════

LMNP_REQUIRED_CODES = [
    "couchage", "occultation", "plaques_cuisson", "four_ou_microondes",
    "refrigerateur", "vaisselle", "ustensiles_cuisine", "table_chaises",
    "rangements", "luminaires", "entretien",
]

CRITERION_LABELS: Dict[str, str] = {
    "couchage":           "Couchage (lit + matelas)",
    "occultation":        "Occultation (rideaux)",
    "plaques_cuisson":    "Plaques de cuisson",
    "four_ou_microondes": "Four / micro-ondes",
    "refrigerateur":      "Refrigerateur",
    "vaisselle":          "Vaisselle & couverts",
    "ustensiles_cuisine": "Ustensiles de cuisine",
    "table_chaises":      "Table + chaises",
    "rangements":         "Rangements",
    "luminaires":         "Luminaires",
    "entretien":          "Materiel d'entretien",
}

GAMME_MULT = {"economique": 0.70, "standard": 1.0, "premium": 1.65}
COMPACT_THRESHOLD_M2 = 22.0
LARGE_SURFACE = {"small": 35.0, "medium": 55.0, "large": 80.0}


# ══════════════════════════════════════════════════════════════════════
# CATALOGUE DE BASE
# Chaque item peut avoir :
#   gamme_min     : "standard" | "premium"  → exclu si gamme inferieure
#   compact_only  : True → inclus seulement si surface compacte
#   large_only    : True → inclus seulement si grande surface
# ══════════════════════════════════════════════════════════════════════

ITEMS_CHAMBRE = [
    # Socle LMNP
    {"name": "Lit 140x200 avec sommier et matelas",   "reference": "MALM / MINNESUND",  "category": "couchage",       "retailer": "IKEA",             "tag_type": "essentiel_lmnp", "unit_price": 375, "quantity": 1, "lmnp_criteria": ["couchage"], "product_url": "https://www.ikea.com/fr/fr/cat/malm-serie-07468/"},
    {"name": "Rideaux occultants",                    "reference": "MAJGULL",           "category": "occultation",    "retailer": "IKEA",             "tag_type": "essentiel_lmnp", "unit_price": 85,  "quantity": 1, "lmnp_criteria": ["occultation"], "product_url": "https://www.ikea.com/fr/fr/p/majgull-rideau-occultant-2-panneaux-gris-clair-10558995/"},
    {"name": "Armoire 2 portes",                      "reference": "PAX OSLO",          "category": "rangements",     "retailer": "IKEA",             "tag_type": "essentiel_lmnp", "unit_price": 225, "quantity": 1, "lmnp_criteria": ["rangements"], "product_url": "https://www.ikea.com/fr/fr/p/pax-armoire-blanc-00294785/"},
    {"name": "Plafonnier chambre",                    "reference": "RANARP",            "category": "luminaires",     "retailer": "IKEA",             "tag_type": "essentiel_lmnp", "unit_price": 55,  "quantity": 1, "lmnp_criteria": ["luminaires"]},
    # Confort Standard
    {"name": "Lampe de chevet",                       "reference": "RANARP",            "category": "luminaires",     "retailer": "IKEA",             "tag_type": "confort",        "unit_price": 43,  "quantity": 1, "lmnp_criteria": [], "gamme_min": "standard"},
    {"name": "Table de chevet avec tiroir",           "reference": "OSLO",              "category": "rangement_petit","retailer": "But",              "tag_type": "confort",        "unit_price": 65,  "quantity": 1, "lmnp_criteria": [], "gamme_min": "standard"},
    # Confort Premium
    {"name": "Commode 3 tiroirs",                     "reference": "MALM",              "category": "rangements",     "retailer": "IKEA",             "tag_type": "confort",        "unit_price": 149, "quantity": 1, "lmnp_criteria": [], "gamme_min": "premium"},
    {"name": "Miroir chambre 50x150 cm",              "reference": "NISSEDAL",          "category": "miroir",         "retailer": "IKEA",             "tag_type": "confort",        "unit_price": 89,  "quantity": 1, "lmnp_criteria": [], "gamme_min": "premium"},
    {"name": "Fauteuil lecture",                      "reference": "STRANDMON",         "category": "siege",          "retailer": "IKEA",             "tag_type": "confort",        "unit_price": 249, "quantity": 1, "lmnp_criteria": [], "gamme_min": "premium", "large_only": True},
]

ITEMS_CHAMBRE_SEJOUR = [
    # Socle LMNP — compact
    {"name": "Canape-lit 2 places",                   "reference": "FRIHETEN",          "category": "couchage",       "retailer": "IKEA",             "tag_type": "essentiel_lmnp", "unit_price": 499, "quantity": 1, "lmnp_criteria": ["couchage"], "compact_only": True, "product_url": "https://www.ikea.com/fr/fr/p/friheten-canape-lit-d-angle-de-rangement-skiftebo-brun-fonce-s79131378/"},
    {"name": "Lit 90x200 avec sommier et matelas",    "reference": "MALM / MINNESUND",  "category": "couchage",       "retailer": "IKEA",             "tag_type": "essentiel_lmnp", "unit_price": 320, "quantity": 1, "lmnp_criteria": ["couchage"], "large_only": True, "product_url": "https://www.ikea.com/fr/fr/p/malm-cadre-lit-haut-blanc-20125892/"},
    {"name": "Rideaux occultants",                    "reference": "MAJGULL",           "category": "occultation",    "retailer": "IKEA",             "tag_type": "essentiel_lmnp", "unit_price": 75,  "quantity": 1, "lmnp_criteria": ["occultation"], "product_url": "https://www.ikea.com/fr/fr/p/majgull-rideau-occultant-2-panneaux-gris-clair-10558995/"},
    {"name": "Penderie / rangement vetements",        "reference": "PAX",               "category": "rangements",     "retailer": "IKEA",             "tag_type": "essentiel_lmnp", "unit_price": 160, "quantity": 1, "lmnp_criteria": ["rangements"], "product_url": "https://www.ikea.com/fr/fr/p/pax-armoire-blanc-00294785/"},
    {"name": "Table basse + 2 chaises",               "reference": "LACK / NORDMYRA",   "category": "table",          "retailer": "IKEA",             "tag_type": "essentiel_lmnp", "unit_price": 90,  "quantity": 1, "lmnp_criteria": ["table_chaises"]},
    {"name": "Luminaire (plafonnier + lampe)",        "reference": "RANARP",            "category": "luminaires",     "retailer": "IKEA",             "tag_type": "essentiel_lmnp", "unit_price": 75,  "quantity": 1, "lmnp_criteria": ["luminaires"]},
    # Confort
    {"name": "Etageres murales",                      "reference": "KALLAX",            "category": "etagere",        "retailer": "IKEA",             "tag_type": "confort",        "unit_price": 59,  "quantity": 1, "lmnp_criteria": [], "gamme_min": "standard"},
    {"name": "Tapis de sejour",                       "reference": "Set deco",          "category": "tapis",          "retailer": "Maisons du Monde", "tag_type": "confort",        "unit_price": 89,  "quantity": 1, "lmnp_criteria": [], "gamme_min": "standard"},
    {"name": "Meuble TV compact",                     "reference": "BESTA",             "category": "meuble_tv",      "retailer": "IKEA",             "tag_type": "confort",        "unit_price": 110, "quantity": 1, "lmnp_criteria": [], "gamme_min": "standard"},
    {"name": "Decoration murale (cadres)",            "reference": "Set deco",          "category": "deco",           "retailer": "Maisons du Monde", "tag_type": "confort",        "unit_price": 79,  "quantity": 1, "lmnp_criteria": [], "gamme_min": "premium"},
]

ITEMS_SEJOUR = [
    # Socle LMNP
    {"name": "Table a manger 4 personnes",            "reference": "EKEDALEN",          "category": "table",          "retailer": "IKEA",             "tag_type": "essentiel_lmnp", "unit_price": 175, "quantity": 1, "lmnp_criteria": ["table_chaises"]},
    {"name": "Chaises (x4)",                          "reference": "NORDIKA",           "category": "chaises",        "retailer": "But",              "tag_type": "essentiel_lmnp", "unit_price": 190, "quantity": 1, "lmnp_criteria": ["table_chaises"]},
    {"name": "Suspension + liseuse",                  "reference": "RANARP",            "category": "luminaires",     "retailer": "IKEA",             "tag_type": "essentiel_lmnp", "unit_price": 135, "quantity": 1, "lmnp_criteria": ["luminaires"]},
    # Confort Standard
    {"name": "Canape 2-3 places",                     "reference": "OSLO",              "category": "canape",         "retailer": "Maisons du Monde", "tag_type": "confort",        "unit_price": 500, "quantity": 1, "lmnp_criteria": [], "gamme_min": "standard"},
    {"name": "Meuble TV / rangements bas",            "reference": "BESTA",             "category": "meuble_tv",      "retailer": "IKEA",             "tag_type": "confort",        "unit_price": 140, "quantity": 1, "lmnp_criteria": [], "gamme_min": "standard"},
    {"name": "Etageres murales",                      "reference": "KALLAX",            "category": "etagere",        "retailer": "IKEA",             "tag_type": "confort",        "unit_price": 70,  "quantity": 1, "lmnp_criteria": [], "gamme_min": "standard"},
    {"name": "Tapis de salon",                        "reference": "Set deco",          "category": "tapis",          "retailer": "Maisons du Monde", "tag_type": "confort",        "unit_price": 120, "quantity": 1, "lmnp_criteria": [], "gamme_min": "standard"},
    # Confort Premium
    {"name": "Fauteuil d'appoint",                   "reference": "STRANDMON",         "category": "fauteuil",       "retailer": "IKEA",             "tag_type": "confort",        "unit_price": 249, "quantity": 1, "lmnp_criteria": [], "gamme_min": "premium"},
    {"name": "Table basse design",                    "reference": "VITTSJO",           "category": "table_basse",    "retailer": "IKEA",             "tag_type": "confort",        "unit_price": 99,  "quantity": 1, "lmnp_criteria": [], "gamme_min": "premium"},
    {"name": "Decoration murale (cadres, miroir)",    "reference": "Set deco",          "category": "deco",           "retailer": "Maisons du Monde", "tag_type": "confort",        "unit_price": 120, "quantity": 1, "lmnp_criteria": [], "gamme_min": "premium"},
    # Grande surface
    {"name": "Table a manger 6 personnes",            "reference": "EKEDALEN XL",       "category": "table",          "retailer": "IKEA",             "tag_type": "confort",        "unit_price": 265, "quantity": 1, "lmnp_criteria": [], "gamme_min": "standard", "large_only": True},
]

ITEMS_CUISINE = [
    # Socle LMNP
    {"name": "Plaques de cuisson vitroceramique",     "reference": "WHIRLPOOL 60cm",    "category": "plaques_cuisson",    "retailer": "Boulanger",     "tag_type": "essentiel_lmnp", "unit_price": 165, "quantity": 1, "lmnp_criteria": ["plaques_cuisson"]},
    {"name": "Micro-ondes 20L",                       "reference": "WHIRLPOOL MW",      "category": "four_ou_microondes", "retailer": "Boulanger",     "tag_type": "essentiel_lmnp", "unit_price": 100, "quantity": 1, "lmnp_criteria": ["four_ou_microondes"], "product_url": "https://www.boulanger.com/c/micro-onde-solo"},
    {"name": "Refrigerateur avec congelateur",        "reference": "SAMSUNG 250L",      "category": "refrigerateur",      "retailer": "Boulanger",     "tag_type": "essentiel_lmnp", "unit_price": 400, "quantity": 1, "lmnp_criteria": ["refrigerateur"], "product_url": "https://www.boulanger.com/c/refrigerateur-congelateur"},
    {"name": "Vaisselle & couverts (service 4 p.)",  "reference": "DINERA",            "category": "vaisselle",          "retailer": "IKEA",          "tag_type": "essentiel_lmnp", "unit_price": 80,  "quantity": 1, "lmnp_criteria": ["vaisselle"], "product_url": "https://www.ikea.com/fr/fr/p/dinera-service-18-pieces-beige-50269705/"},
    {"name": "Ustensiles de cuisine",                 "reference": "KAVALKAD",          "category": "ustensiles_cuisine", "retailer": "IKEA",          "tag_type": "essentiel_lmnp", "unit_price": 55,  "quantity": 1, "lmnp_criteria": ["ustensiles_cuisine"], "product_url": "https://www.ikea.com/fr/fr/p/kavalkad-ensemble-3-casseroles-gris-fonce-20302338/"},
    {"name": "Materiel d'entretien menager",          "reference": "Set entretien",     "category": "entretien",          "retailer": "Leroy Merlin",  "tag_type": "essentiel_lmnp", "unit_price": 50,  "quantity": 1, "lmnp_criteria": ["entretien"], "product_url": "https://www.leroymerlin.fr/produits/salle-de-bains-wc/nettoyage-et-entretien/"},
    # Confort Standard
    {"name": "Petit electromenager (bouilloire, grille-pain)", "reference": "KAVALKAD","category": "petit_electro",      "retailer": "IKEA",          "tag_type": "confort",        "unit_price": 105, "quantity": 1, "lmnp_criteria": [], "gamme_min": "standard"},
    {"name": "Poubelle de cuisine",                   "reference": "Set entretien",     "category": "poubelle",           "retailer": "Leroy Merlin",  "tag_type": "confort",        "unit_price": 35,  "quantity": 1, "lmnp_criteria": [], "gamme_min": "standard"},
    {"name": "Rangements cuisine (etagere)",          "reference": "OMAR",              "category": "rangements",         "retailer": "IKEA",          "tag_type": "confort",        "unit_price": 70,  "quantity": 1, "lmnp_criteria": [], "gamme_min": "standard"},
    # Confort Premium
    {"name": "Robot de cuisine multifonction",        "reference": "SILVERCREST",       "category": "petit_electro",      "retailer": "Boulanger",     "tag_type": "confort",        "unit_price": 149, "quantity": 1, "lmnp_criteria": [], "gamme_min": "premium"},
    {"name": "Cafetiere a dosettes",                  "reference": "NESPRESSO",         "category": "petit_electro",      "retailer": "Boulanger",     "tag_type": "confort",        "unit_price": 99,  "quantity": 1, "lmnp_criteria": [], "gamme_min": "premium"},
]

ITEMS_SDB = [
    {"name": "Miroir + tablette salle de bain",       "reference": "GODMORGON",         "category": "miroir",            "retailer": "IKEA",          "tag_type": "confort",        "unit_price": 120, "quantity": 1, "lmnp_criteria": [], "gamme_min": "standard"},
    {"name": "Porte-serviettes & accessoires",        "reference": "GODMORGON",         "category": "accessoires",       "retailer": "IKEA",          "tag_type": "confort",        "unit_price": 55,  "quantity": 1, "lmnp_criteria": [], "gamme_min": "standard"},
    {"name": "Tapis de bain",                         "reference": "TOFTBO",            "category": "tapis",             "retailer": "IKEA",          "tag_type": "confort",        "unit_price": 35,  "quantity": 1, "lmnp_criteria": [], "gamme_min": "standard"},
    {"name": "Set accessoires salle de bain",         "reference": "GODMORGON SET",     "category": "set_sdb",           "retailer": "IKEA",          "tag_type": "confort",        "unit_price": 43,  "quantity": 1, "lmnp_criteria": [], "gamme_min": "standard"},
    {"name": "Rangement salle de bain mural",         "reference": "SILVERAN",          "category": "rangements",        "retailer": "IKEA",          "tag_type": "confort",        "unit_price": 110, "quantity": 1, "lmnp_criteria": [], "gamme_min": "premium"},
]

# Items supplementaires par cible locataire
ITEMS_BUREAU_ETUDIANT = [
    {"name": "Bureau d'etude compact",                "reference": "MICKE",             "category": "bureau",            "retailer": "IKEA",          "tag_type": "confort",        "unit_price": 89,  "quantity": 1, "lmnp_criteria": [], "gamme_min": "standard"},
    {"name": "Chaise de bureau ergonomique",          "reference": "LOBERGET",          "category": "siege",             "retailer": "IKEA",          "tag_type": "confort",        "unit_price": 99,  "quantity": 1, "lmnp_criteria": [], "gamme_min": "standard", "product_url": "https://www.ikea.com/fr/fr/p/loberget-sibben-chaise-bureau-enfant-blanc-54397260/"},
    {"name": "Lampe de bureau LED",                   "reference": "FORSA",             "category": "luminaires",        "retailer": "IKEA",          "tag_type": "confort",        "unit_price": 35,  "quantity": 1, "lmnp_criteria": [], "gamme_min": "standard"},
]

ITEMS_FAMILLE_SEJOUR = [
    {"name": "Canape 3 places robuste",               "reference": "KIVIK",             "category": "canape",            "retailer": "IKEA",          "tag_type": "confort",        "unit_price": 650, "quantity": 1, "lmnp_criteria": [], "gamme_min": "standard"},
    {"name": "Rangements supplementaires (colonne)",  "reference": "KALLAX",            "category": "rangements",        "retailer": "IKEA",          "tag_type": "confort",        "unit_price": 95,  "quantity": 1, "lmnp_criteria": [], "gamme_min": "standard"},
    {"name": "Table a manger 6 personnes",            "reference": "EKEDALEN XL",       "category": "table",             "retailer": "IKEA",          "tag_type": "confort",        "unit_price": 265, "quantity": 1, "lmnp_criteria": [], "gamme_min": "standard"},
]

ITEMS_COURTE_DUREE = [
    {"name": "Linge de maison (draps, serviettes)",  "reference": "Set linge",          "category": "linge",             "retailer": "Maisons du Monde","tag_type": "confort",       "unit_price": 120, "quantity": 1, "lmnp_criteria": [], "gamme_min": "standard"},
    {"name": "Decoration murale (tableaux, cadres)",  "reference": "Set deco",          "category": "deco",              "retailer": "Maisons du Monde","tag_type": "confort",       "unit_price": 110, "quantity": 1, "lmnp_criteria": [], "gamme_min": "standard"},
    {"name": "Tapis salon decoratif",                 "reference": "Set deco",          "category": "tapis",             "retailer": "Maisons du Monde","tag_type": "confort",       "unit_price": 150, "quantity": 1, "lmnp_criteria": [], "gamme_min": "standard"},
    {"name": "Lampes d'ambiance (x2)",                "reference": "FADO",              "category": "luminaires",        "retailer": "IKEA",           "tag_type": "confort",       "unit_price": 79,  "quantity": 1, "lmnp_criteria": [], "gamme_min": "standard"},
    {"name": "Petit electro accueil (bouilloire, Nespresso)", "reference": "Set accueil","category": "petit_electro",    "retailer": "Boulanger",      "tag_type": "confort",       "unit_price": 159, "quantity": 1, "lmnp_criteria": [], "gamme_min": "standard"},
]


# ══════════════════════════════════════════════════════════════════════
# MOTEUR D'ADAPTATION
# ══════════════════════════════════════════════════════════════════════

def _get_typo_profile(property_type: str, rooms_count: int) -> str:
    pt = (property_type or "").lower().strip()
    if pt in ("studio", "t1"):
        return "small"
    if pt == "t2":
        return "medium"
    return "large"


def _is_compact(surface_m2: float, profile: str) -> bool:
    return profile == "small" and surface_m2 < COMPACT_THRESHOLD_M2


def _is_large_surface(surface_m2: float, profile: str) -> bool:
    return surface_m2 >= LARGE_SURFACE.get(profile, 999)


def _gamme_rank(budget_level: str) -> int:
    return {"economique": 0, "standard": 1, "premium": 2}.get(budget_level, 1)


def _filter_items(items: List[Dict], budget_level: str, compact: bool, large_surface: bool) -> List[Dict]:
    rank   = _gamme_rank(budget_level)
    result = []
    for item in items:
        if item.get("compact_only") and not compact:
            continue
        if item.get("large_only") and not large_surface:
            continue
        gamme_min = item.get("gamme_min")
        if gamme_min and rank < _gamme_rank(gamme_min):
            continue
        # Budget : on exclut les items Confort qui ont un gamme_min explicite
        if budget_level == "economique" and item["tag_type"] == "confort" and gamme_min:
            continue
        result.append(deepcopy(item))
    return result


def _apply_price_multiplier(items: List[Dict], budget_level: str) -> List[Dict]:
    mult = GAMME_MULT.get(budget_level, 1.0)
    for item in items:
        item["unit_price"] = round(item["unit_price"] * mult)
    return items


def build_rooms_catalogue(
    profile: str,
    rooms_count: int,
    tenant_profile: str,
    budget_level: str,
    compact: bool,
    large_surface: bool,
) -> List[Dict]:
    """
    Construit la liste des rooms adaptees au profil.
    Phase 2 : remplacer par generate_catalogue_from_llm(property).
    """
    def make(base):
        return _apply_price_multiplier(
            _filter_items(base, budget_level, compact, large_surface),
            budget_level,
        )

    rooms: List[Dict] = []

    # ── small (studio / T1) ───────────────────────────────────────────
    if profile == "small":
        items = make(ITEMS_CHAMBRE_SEJOUR)
        if tenant_profile == "etudiant":
            items += make(ITEMS_BUREAU_ETUDIANT)
        if tenant_profile == "courte_duree":
            items += make(ITEMS_COURTE_DUREE)
        rooms.append({"room_type": "chambre_sejour", "label": "Chambre / Sejour", "items": items})

    # ── medium (T2) ───────────────────────────────────────────────────
    elif profile == "medium":
        ch = make(ITEMS_CHAMBRE)
        if tenant_profile == "etudiant":
            ch += make(ITEMS_BUREAU_ETUDIANT)
        rooms.append({"room_type": "chambre", "label": "Chambre", "items": ch})

        sej = make(ITEMS_SEJOUR)
        if tenant_profile == "famille":
            sej += make(ITEMS_FAMILLE_SEJOUR)
        if tenant_profile == "courte_duree":
            sej += make(ITEMS_COURTE_DUREE)
        rooms.append({"room_type": "sejour", "label": "Sejour", "items": sej})

    # ── large (T3 / T4+ / colocation) ────────────────────────────────
    else:
        nb = max(2, min((rooms_count or 2) - 1, 5))
        for i in range(nb):
            label = "Chambre principale" if i == 0 else f"Chambre {i + 1}"
            ch = make(ITEMS_CHAMBRE)
            if tenant_profile == "etudiant":
                ch += make(ITEMS_BUREAU_ETUDIANT)
            rooms.append({"room_type": "chambre", "label": label, "items": ch})

        sej = make(ITEMS_SEJOUR)
        if tenant_profile == "famille":
            sej += make(ITEMS_FAMILLE_SEJOUR)
        if tenant_profile == "courte_duree":
            sej += make(ITEMS_COURTE_DUREE)
        rooms.append({"room_type": "sejour", "label": "Sejour", "items": sej})

    # Cuisine + SDB (tous profils)
    rooms.append({"room_type": "cuisine", "label": "Cuisine", "items": make(ITEMS_CUISINE)})
    rooms.append({"room_type": "sdb",     "label": "Salle de bain", "items": make(ITEMS_SDB)})

    return rooms


# ══════════════════════════════════════════════════════════════════════
# HELPERS DB
# ══════════════════════════════════════════════════════════════════════

def _get_or_create_retailer(db: Session, name: str) -> Retailer:
    r = db.query(Retailer).filter(Retailer.name == name).first()
    if r:
        return r
    r = Retailer(id=str(uuid.uuid4()), name=name)
    db.add(r)
    db.flush()
    return r


def _ensure_lmnp_criteria(db: Session) -> Dict[str, LmnpCriterion]:
    existing = {c.code: c for c in db.query(LmnpCriterion).all()}
    for code in LMNP_REQUIRED_CODES:
        if code not in existing:
            c = LmnpCriterion(
                id=str(uuid.uuid4()), code=code,
                label=CRITERION_LABELS.get(code, code.replace("_", " ").title()),
            )
            db.add(c)
            db.flush()
            existing[code] = c
    return existing


# ══════════════════════════════════════════════════════════════════════
# FONCTION PRINCIPALE
# ══════════════════════════════════════════════════════════════════════

def generate_pack_for_property(db: Session, project_id: str, property: Property) -> Pack:
    """
    Genere un Pack LMNP adaptatif.
    Sortie identique a PackOut — rien ne change cote API / frontend.
    """
    profile       = _get_typo_profile(property.property_type, property.rooms_count or 1)
    budget_level  = property.budget_level or "standard"
    surface       = float(property.surface_m2 or 40)
    compact       = _is_compact(surface, profile)
    large_surface = _is_large_surface(surface, profile)
    tenant        = property.tenant_profile or "jeune_actif"
    rooms_count   = property.rooms_count or 2

    rooms_catalogue = build_rooms_catalogue(
        profile=profile, rooms_count=rooms_count, tenant_profile=tenant,
        budget_level=budget_level, compact=compact, large_surface=large_surface,
    )

    lmnp_criteria_map = _ensure_lmnp_criteria(db)

    pack_id = str(uuid.uuid4())
    pack = Pack(id=pack_id, project_id=project_id, total_price=0, is_lmnp_compliant=False, currency="EUR")
    db.add(pack)
    db.flush()

    total_price:   int      = 0
    covered_codes: Set[str] = set()

    for room_def in rooms_catalogue:
        room_id = str(uuid.uuid4())
        room = Room(id=room_id, pack_id=pack_id, room_type=room_def["room_type"],
                    label=room_def["label"], mandatory_items_count=0, total_price=0)
        db.add(room)
        db.flush()

        room_total = mand = 0

        for item_def in room_def["items"]:
            retailer = _get_or_create_retailer(db, item_def["retailer"])
            qty      = item_def["quantity"]
            uprice   = item_def["unit_price"]
            tprice   = qty * uprice

            db.add(PackItem(
                id=str(uuid.uuid4()), pack_id=pack_id, room_id=room_id,
                retailer_id=retailer.id, name=item_def["name"],
                reference=item_def.get("reference"), category=item_def.get("category"),
                tag_type=item_def["tag_type"], unit_price=uprice, quantity=qty,
                total_price=tprice,
                product_url=item_def.get("product_url"),  # propagé depuis le catalogue
            ))

            room_total += tprice
            total_price += tprice
            if item_def["tag_type"] == "essentiel_lmnp":
                mand += 1
            for code in item_def.get("lmnp_criteria", []):
                if code in lmnp_criteria_map:
                    covered_codes.add(code)

        room.total_price = room_total
        room.mandatory_items_count = mand

    for code, crit in lmnp_criteria_map.items():
        db.add(PackLmnpCriterion(
            id=str(uuid.uuid4()), pack_id=pack_id, criterion_id=crit.id,
            is_covered=(code in covered_codes),
        ))

    pack.total_price       = total_price
    pack.is_lmnp_compliant = set(LMNP_REQUIRED_CODES).issubset(covered_codes)

    bmax = property.budget_max
    if bmax and bmax > 0:
        pack.savings_amount  = bmax - total_price
        pack.savings_percent = round((bmax - total_price) / bmax * 100, 2)

    db.flush()
    return pack
