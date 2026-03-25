"""
app/services/generator.py — Générateur de packs LMNP adaptatif v3

Architecture :
  1. Profil typologique  : small | medium | large  (property_type + rooms_count)
  2. Gabarits de rooms   : catalogues d'items par room_type, alignés LMNP
  3. Socle LMNP          : 11 critères décret 2015-981, toujours couverts
  4. Cible locataire     : items supplémentaires (etudiant / famille / courte_duree)
  5. Gamme               : multiplicateur prix + filtrage items Confort (gamme_min)
  6. Surface             : compact si < 22 m², extra rangements si grande surface

room_type values (alignés frontend v2 + spec Perplexity) :
  bedroom, living_room, kitchen, bathroom, chambre_sejour (studio compact)

tag_type values (alignés schemas_v2.py) :
  "essentiel_lmnp"  → item obligatoire LMNP
  "confort"         → item de confort (optionnel selon gamme)

lmnp_criteria par item : liste des codes LMNP couverts par cet item
  → permet le calcul automatique de is_lmnp_compliant + lmnp_checklist

Phase 2 : remplacer build_rooms_catalogue() par generate_catalogue_from_llm(property).
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
# CONSTANTES MÉTIER
# ══════════════════════════════════════════════════════════════════════

LMNP_REQUIRED_CODES = [
    "couchage", "occultation", "plaques_cuisson", "four_ou_microondes",
    "refrigerateur", "vaisselle", "ustensiles_cuisine", "table_chaises",
    "rangements", "luminaires", "entretien",
]

CRITERION_LABELS: Dict[str, str] = {
    "couchage":           "Couchage (lit + matelas)",
    "occultation":        "Occultation (rideaux occultants)",
    "plaques_cuisson":    "Plaques de cuisson",
    "four_ou_microondes": "Four / micro-ondes",
    "refrigerateur":      "Réfrigérateur avec congélateur",
    "vaisselle":          "Vaisselle & couverts",
    "ustensiles_cuisine": "Ustensiles de cuisine",
    "table_chaises":      "Table + chaises",
    "rangements":         "Rangements (armoire, meubles)",
    "luminaires":         "Luminaires",
    "entretien":          "Matériel d'entretien",
}

GAMME_MULT = {"economique": 0.70, "standard": 1.0, "premium": 1.65}
COMPACT_THRESHOLD_M2 = 22.0
LARGE_SURFACE = {"small": 35.0, "medium": 55.0, "large": 80.0}


# ══════════════════════════════════════════════════════════════════════
# CATALOGUE D'ITEMS PAR ROOM TYPE
#
# Chaque item :
#   name          : libellé affiché
#   reference     : référence produit enseigne (ex: "MALM / MINNESUND")
#   category      : catégorie fonctionnelle interne
#   retailer      : enseigne (IKEA, Boulanger…)
#   tag_type      : "essentiel_lmnp" | "confort"
#   unit_price    : prix unitaire en € (gamme standard)
#   quantity      : quantité
#   lmnp_criteria : codes LMNP couverts par cet item
#   product_url   : lien produit (Phase 3)
#   gamme_min     : "standard" | "premium" → exclu si gamme inférieure
#   compact_only  : True → inclus seulement si studio compact (< 22m²)
#   large_only    : True → inclus seulement si grande surface
# ══════════════════════════════════════════════════════════════════════

# ─────────────────────────────────────────────────────────────────────
# BEDROOM — chambre séparée (T2/T3/T4)
# ─────────────────────────────────────────────────────────────────────

ITEMS_BEDROOM = [
    # Socle LMNP — couchage
    {"name": "Lit 140x200 avec sommier",        "reference": "MALM",        "category": "couchage",    "retailer": "IKEA",   "tag_type": "essentiel_lmnp", "unit_price": 249, "quantity": 1, "lmnp_criteria": ["couchage"],    "product_url": "https://www.ikea.com/fr/fr/p/malm-cadre-lit-haut-blanc-20125892/"},
    {"name": "Matelas 140x200",                 "reference": "MINNESUND",   "category": "couchage",    "retailer": "IKEA",   "tag_type": "essentiel_lmnp", "unit_price": 129, "quantity": 1, "lmnp_criteria": ["couchage"],    "product_url": "https://www.ikea.com/fr/fr/p/minnesund-matelas-ferme-blanc-40305289/"},
    # Socle LMNP — occultation
    {"name": "Rideaux occultants chambre",       "reference": "MAJGULL",     "category": "occultation", "retailer": "IKEA",   "tag_type": "essentiel_lmnp", "unit_price": 85,  "quantity": 1, "lmnp_criteria": ["occultation"], "product_url": "https://www.ikea.com/fr/fr/p/majgull-rideau-occultant-2-panneaux-gris-clair-10558995/"},
    # Socle LMNP — rangements
    {"name": "Armoire 2 portes",                "reference": "PAX OSLO",    "category": "rangements",  "retailer": "IKEA",   "tag_type": "essentiel_lmnp", "unit_price": 225, "quantity": 1, "lmnp_criteria": ["rangements"],  "product_url": "https://www.ikea.com/fr/fr/p/pax-armoire-blanc-00294785/"},
    {"name": "Table de chevet",                 "reference": "HEMNES",      "category": "rangements",  "retailer": "IKEA",   "tag_type": "essentiel_lmnp", "unit_price": 69,  "quantity": 1, "lmnp_criteria": ["rangements"]},
    # Socle LMNP — luminaires
    {"name": "Plafonnier chambre",              "reference": "RANARP",      "category": "luminaires",  "retailer": "IKEA",   "tag_type": "essentiel_lmnp", "unit_price": 55,  "quantity": 1, "lmnp_criteria": ["luminaires"]},
    # Confort Économique+ — lampe de chevet incluse dès économique
    {"name": "Lampe de chevet",                 "reference": "RANARP",      "category": "luminaires",  "retailer": "IKEA",   "tag_type": "confort",        "unit_price": 43,  "quantity": 1, "lmnp_criteria": []},
    # Confort Premium
    {"name": "Commode 3 tiroirs",               "reference": "MALM",        "category": "rangements",  "retailer": "IKEA",   "tag_type": "confort",        "unit_price": 149, "quantity": 1, "lmnp_criteria": [], "gamme_min": "premium"},
    {"name": "Miroir chambre 50x150 cm",        "reference": "NISSEDAL",    "category": "miroir",      "retailer": "IKEA",   "tag_type": "confort",        "unit_price": 89,  "quantity": 1, "lmnp_criteria": [], "gamme_min": "premium"},
    {"name": "Fauteuil lecture",                "reference": "STRANDMON",   "category": "siege",       "retailer": "IKEA",   "tag_type": "confort",        "unit_price": 249, "quantity": 1, "lmnp_criteria": [], "gamme_min": "premium", "large_only": True},
]

# Items bureau — ajoutés à la chambre pour profil etudiant / jeune_actif
# Bureau + chaise : pas de gamme_min → inclus dès économique (critique pour étudiant)
# Lampe de bureau : gamme_min standard → optionnelle en économique
ITEMS_BUREAU = [
    {"name": "Bureau compact 120 cm",           "reference": "MICKE",       "category": "bureau",      "retailer": "IKEA",   "tag_type": "confort",        "unit_price": 89,  "quantity": 1, "lmnp_criteria": [], "product_url": "https://www.ikea.com/fr/fr/p/micke-bureau-blanc-90214308/"},
    {"name": "Chaise de bureau",                "reference": "LOBERGET",    "category": "bureau",      "retailer": "IKEA",   "tag_type": "confort",        "unit_price": 49,  "quantity": 1, "lmnp_criteria": []},
    {"name": "Lampe de bureau LED",             "reference": "FORSA",       "category": "luminaires",  "retailer": "IKEA",   "tag_type": "confort",        "unit_price": 35,  "quantity": 1, "lmnp_criteria": [], "gamme_min": "standard"},
]

# ─────────────────────────────────────────────────────────────────────
# LIVING_ROOM — séjour séparé (T2/T3/T4)
# ─────────────────────────────────────────────────────────────────────

ITEMS_LIVING_ROOM = [
    # Socle LMNP — table + chaises
    {"name": "Table à manger 4 personnes",      "reference": "EKEDALEN",    "category": "table",       "retailer": "IKEA",             "tag_type": "essentiel_lmnp", "unit_price": 175, "quantity": 1, "lmnp_criteria": ["table_chaises"]},
    {"name": "Chaises repas (x4)",              "reference": "NORDIKA",     "category": "chaises",     "retailer": "But",              "tag_type": "essentiel_lmnp", "unit_price": 190, "quantity": 1, "lmnp_criteria": ["table_chaises"]},
    # Socle LMNP — occultation séjour
    {"name": "Rideaux séjour",                  "reference": "HANNALILL",   "category": "occultation", "retailer": "IKEA",             "tag_type": "essentiel_lmnp", "unit_price": 55,  "quantity": 1, "lmnp_criteria": ["occultation"]},
    # Socle LMNP — luminaires séjour
    {"name": "Suspension + liseuse",            "reference": "RANARP",      "category": "luminaires",  "retailer": "IKEA",             "tag_type": "essentiel_lmnp", "unit_price": 135, "quantity": 1, "lmnp_criteria": ["luminaires"]},
    # Confort Économique+ — canapé inclus dès économique (essentiel confort séjour)
    {"name": "Canapé 2-3 places",               "reference": "KIVIK",       "category": "canape",      "retailer": "IKEA",             "tag_type": "confort",        "unit_price": 549, "quantity": 1, "lmnp_criteria": []},
    # Confort Standard — meuble TV, étagères, tapis, table basse
    {"name": "Table basse",                     "reference": "VITTSJO",     "category": "table_basse", "retailer": "IKEA",             "tag_type": "confort",        "unit_price": 65,  "quantity": 1, "lmnp_criteria": [], "gamme_min": "standard"},
    {"name": "Meuble TV / rangements bas",      "reference": "BESTA",       "category": "meuble_tv",   "retailer": "IKEA",             "tag_type": "confort",        "unit_price": 140, "quantity": 1, "lmnp_criteria": [], "gamme_min": "standard"},
    {"name": "Étagères murales",                "reference": "KALLAX",      "category": "etagere",     "retailer": "IKEA",             "tag_type": "confort",        "unit_price": 70,  "quantity": 1, "lmnp_criteria": [], "gamme_min": "standard"},
    {"name": "Tapis de salon",                  "reference": "Set déco",    "category": "tapis",       "retailer": "Maisons du Monde", "tag_type": "confort",        "unit_price": 120, "quantity": 1, "lmnp_criteria": [], "gamme_min": "standard"},
    # Confort Premium — fauteuil + déco
    {"name": "Fauteuil d'appoint",              "reference": "STRANDMON",   "category": "fauteuil",    "retailer": "IKEA",             "tag_type": "confort",        "unit_price": 249, "quantity": 1, "lmnp_criteria": [], "gamme_min": "premium"},
    {"name": "Décoration murale (cadres)",      "reference": "Set déco",    "category": "deco",        "retailer": "Maisons du Monde", "tag_type": "confort",        "unit_price": 120, "quantity": 1, "lmnp_criteria": [], "gamme_min": "premium"},
    # Grande surface
    {"name": "Table à manger 6 personnes",      "reference": "EKEDALEN XL", "category": "table",       "retailer": "IKEA",             "tag_type": "confort",        "unit_price": 265, "quantity": 1, "lmnp_criteria": [], "gamme_min": "standard", "large_only": True},
]

# Items séjour — profil famille
ITEMS_LIVING_FAMILLE = [
    {"name": "Canapé 3 places robuste",         "reference": "KIVIK",       "category": "canape",      "retailer": "IKEA",   "tag_type": "confort",        "unit_price": 650, "quantity": 1, "lmnp_criteria": [], "gamme_min": "standard"},
    {"name": "Rangements supplémentaires",      "reference": "KALLAX",      "category": "rangements",  "retailer": "IKEA",   "tag_type": "confort",        "unit_price": 95,  "quantity": 1, "lmnp_criteria": [], "gamme_min": "standard"},
]

# Items séjour — courte durée
ITEMS_COURTE_DUREE_SEJOUR = [
    {"name": "Linge de maison (draps, serviettes)", "reference": "Set linge", "category": "linge",     "retailer": "Maisons du Monde", "tag_type": "confort", "unit_price": 120, "quantity": 1, "lmnp_criteria": [], "gamme_min": "standard"},
    {"name": "Décoration murale (tableaux)",    "reference": "Set déco",    "category": "deco",        "retailer": "Maisons du Monde", "tag_type": "confort", "unit_price": 110, "quantity": 1, "lmnp_criteria": [], "gamme_min": "standard"},
    {"name": "Tapis salon décoratif",           "reference": "Set déco",    "category": "tapis",       "retailer": "Maisons du Monde", "tag_type": "confort", "unit_price": 150, "quantity": 1, "lmnp_criteria": [], "gamme_min": "standard"},
    {"name": "Lampes d'ambiance (x2)",          "reference": "FADO",        "category": "luminaires",  "retailer": "IKEA",             "tag_type": "confort", "unit_price": 79,  "quantity": 1, "lmnp_criteria": [], "gamme_min": "standard"},
    {"name": "Petit électro accueil (bouilloire, Nespresso)", "reference": "Set accueil", "category": "petit_electro", "retailer": "Boulanger", "tag_type": "confort", "unit_price": 159, "quantity": 1, "lmnp_criteria": [], "gamme_min": "standard"},
]

# ─────────────────────────────────────────────────────────────────────
# KITCHEN — cuisine (tous profils)
# ─────────────────────────────────────────────────────────────────────

ITEMS_KITCHEN = [
    # Socle LMNP obligatoire
    {"name": "Plaques de cuisson vitrocéramique",            "reference": "WHIRLPOOL 60cm",  "category": "plaques_cuisson",    "retailer": "Boulanger",   "tag_type": "essentiel_lmnp", "unit_price": 165, "quantity": 1, "lmnp_criteria": ["plaques_cuisson"]},
    {"name": "Micro-ondes 20L",                              "reference": "WHIRLPOOL MW",    "category": "four_ou_microondes", "retailer": "Boulanger",   "tag_type": "essentiel_lmnp", "unit_price": 100, "quantity": 1, "lmnp_criteria": ["four_ou_microondes"], "product_url": "https://www.boulanger.com/c/micro-onde-solo"},
    {"name": "Réfrigérateur avec congélateur",               "reference": "SAMSUNG 250L",    "category": "refrigerateur",      "retailer": "Boulanger",   "tag_type": "essentiel_lmnp", "unit_price": 400, "quantity": 1, "lmnp_criteria": ["refrigerateur"],     "product_url": "https://www.boulanger.com/c/refrigerateur-congelateur"},
    # Vaisselle — 3 items distincts (spec Perplexity)
    {"name": "Lot vaisselle 4 personnes (assiettes, bols)",  "reference": "DINERA",          "category": "vaisselle",          "retailer": "IKEA",        "tag_type": "essentiel_lmnp", "unit_price": 45,  "quantity": 1, "lmnp_criteria": ["vaisselle"],         "product_url": "https://www.ikea.com/fr/fr/p/dinera-service-18-pieces-beige-50269705/"},
    {"name": "Lot couverts 4 personnes",                     "reference": "DRAGON",          "category": "vaisselle",          "retailer": "IKEA",        "tag_type": "essentiel_lmnp", "unit_price": 20,  "quantity": 1, "lmnp_criteria": ["vaisselle"]},
    {"name": "Verres et mugs (x8)",                          "reference": "POKAL / VARDAGEN","category": "vaisselle",          "retailer": "IKEA",        "tag_type": "essentiel_lmnp", "unit_price": 20,  "quantity": 1, "lmnp_criteria": ["vaisselle"]},
    # Ustensiles — 3 items distincts (spec Perplexity)
    {"name": "Batterie de cuisine (casseroles, poêles)",     "reference": "KAVALKAD",        "category": "ustensiles_cuisine", "retailer": "IKEA",        "tag_type": "essentiel_lmnp", "unit_price": 40,  "quantity": 1, "lmnp_criteria": ["ustensiles_cuisine"],"product_url": "https://www.ikea.com/fr/fr/p/kavalkad-ensemble-3-casseroles-gris-fonce-20302338/"},
    {"name": "Ustensiles cuisine (spatule, louche, fouet)",  "reference": "FULLANDAD",       "category": "ustensiles_cuisine", "retailer": "IKEA",        "tag_type": "essentiel_lmnp", "unit_price": 20,  "quantity": 1, "lmnp_criteria": ["ustensiles_cuisine"]},
    {"name": "Planche à découper",                           "reference": "LEGITIMIG",       "category": "ustensiles_cuisine", "retailer": "IKEA",        "tag_type": "essentiel_lmnp", "unit_price": 10,  "quantity": 1, "lmnp_criteria": ["ustensiles_cuisine"]},
    # Entretien obligatoire LMNP
    {"name": "Poubelle de cuisine",                          "reference": "Set entretien",   "category": "entretien",          "retailer": "Leroy Merlin","tag_type": "essentiel_lmnp", "unit_price": 25,  "quantity": 1, "lmnp_criteria": ["entretien"]},
    # Confort Économique+ — bouilloire incluse dès économique
    {"name": "Bouilloire",                                   "reference": "KAVALKAD",        "category": "petit_electro",      "retailer": "IKEA",        "tag_type": "confort",        "unit_price": 25,  "quantity": 1, "lmnp_criteria": []},
    # Confort Standard — grille-pain, égouttoir, rangements
    {"name": "Grille-pain",                                  "reference": "BRUN",            "category": "petit_electro",      "retailer": "IKEA",        "tag_type": "confort",        "unit_price": 25,  "quantity": 1, "lmnp_criteria": [], "gamme_min": "standard"},
    {"name": "Égouttoir vaisselle",                          "reference": "Set cuisine",     "category": "rangements",         "retailer": "Leroy Merlin","tag_type": "confort",        "unit_price": 20,  "quantity": 1, "lmnp_criteria": [], "gamme_min": "standard"},
    {"name": "Rangements cuisine (étagère)",                 "reference": "OMAR",            "category": "rangements",         "retailer": "IKEA",        "tag_type": "confort",        "unit_price": 70,  "quantity": 1, "lmnp_criteria": [], "gamme_min": "standard"},
    # Confort Premium
    {"name": "Robot de cuisine multifonction",               "reference": "SILVERCREST",     "category": "petit_electro",      "retailer": "Boulanger",   "tag_type": "confort",        "unit_price": 149, "quantity": 1, "lmnp_criteria": [], "gamme_min": "premium"},
    {"name": "Cafetière à dosettes",                         "reference": "NESPRESSO",       "category": "petit_electro",      "retailer": "Boulanger",   "tag_type": "confort",        "unit_price": 99,  "quantity": 1, "lmnp_criteria": [], "gamme_min": "premium"},
]

# ─────────────────────────────────────────────────────────────────────
# BATHROOM — salle de bain (tous profils)
# ─────────────────────────────────────────────────────────────────────

ITEMS_BATHROOM = [
    # Entretien obligatoire LMNP
    {"name": "Kit entretien (balai, serpillière, seau)",     "reference": "Set entretien",   "category": "entretien",   "retailer": "Leroy Merlin", "tag_type": "essentiel_lmnp", "unit_price": 35, "quantity": 1, "lmnp_criteria": ["entretien"], "product_url": "https://www.leroymerlin.fr/produits/salle-de-bains-wc/nettoyage-et-entretien/"},
    {"name": "Balai-brosse WC",                              "reference": "Set WC",          "category": "entretien",   "retailer": "Leroy Merlin", "tag_type": "essentiel_lmnp", "unit_price": 12, "quantity": 1, "lmnp_criteria": ["entretien"]},
    # Confort de base — porte-serviettes sans gamme_min (utile dès économique)
    {"name": "Porte-serviettes",                             "reference": "GRUNDTAL",        "category": "accessoires", "retailer": "IKEA",         "tag_type": "confort",        "unit_price": 15, "quantity": 1, "lmnp_criteria": []},
    # Confort Standard
    {"name": "Meuble sous-vasque ou colonne",                "reference": "GODMORGON",       "category": "rangements",  "retailer": "IKEA",         "tag_type": "confort",        "unit_price": 120,"quantity": 1, "lmnp_criteria": [], "gamme_min": "standard"},
    {"name": "Miroir salle de bain",                         "reference": "GODMORGON",       "category": "miroir",      "retailer": "IKEA",         "tag_type": "confort",        "unit_price": 69, "quantity": 1, "lmnp_criteria": [], "gamme_min": "standard"},
    {"name": "Set accessoires salle de bain",                "reference": "GODMORGON",       "category": "accessoires", "retailer": "IKEA",         "tag_type": "confort",        "unit_price": 43, "quantity": 1, "lmnp_criteria": [], "gamme_min": "standard"},
    {"name": "Tapis de bain",                                "reference": "TOFTBO",          "category": "tapis",       "retailer": "IKEA",         "tag_type": "confort",        "unit_price": 35, "quantity": 1, "lmnp_criteria": [], "gamme_min": "standard"},
    # Confort Premium
    {"name": "Rangement salle de bain mural",                "reference": "SILVERAN",        "category": "rangements",  "retailer": "IKEA",         "tag_type": "confort",        "unit_price": 110,"quantity": 1, "lmnp_criteria": [], "gamme_min": "premium"},
]

# ─────────────────────────────────────────────────────────────────────
# CHAMBRE_SEJOUR — pièce unique studio compact (< 22m²)
# ─────────────────────────────────────────────────────────────────────

ITEMS_CHAMBRE_SEJOUR = [
    # Socle LMNP — couchage compact
    {"name": "Canapé-lit 2 places",             "reference": "FRIHETEN",    "category": "couchage",    "retailer": "IKEA",             "tag_type": "essentiel_lmnp", "unit_price": 499,"quantity": 1, "lmnp_criteria": ["couchage"],    "compact_only": True, "product_url": "https://www.ikea.com/fr/fr/p/friheten-canape-lit-d-angle-de-rangement-skiftebo-brun-fonce-s79131378/"},
    {"name": "Lit 90x200 avec sommier",         "reference": "MALM",        "category": "couchage",    "retailer": "IKEA",             "tag_type": "essentiel_lmnp", "unit_price": 195,"quantity": 1, "lmnp_criteria": ["couchage"],    "large_only": True,   "product_url": "https://www.ikea.com/fr/fr/p/malm-cadre-lit-haut-blanc-20125892/"},
    {"name": "Matelas 90x200",                  "reference": "MINNESUND",   "category": "couchage",    "retailer": "IKEA",             "tag_type": "essentiel_lmnp", "unit_price": 99, "quantity": 1, "lmnp_criteria": ["couchage"],    "large_only": True},
    # Socle LMNP — occultation
    {"name": "Rideaux occultants",              "reference": "MAJGULL",     "category": "occultation", "retailer": "IKEA",             "tag_type": "essentiel_lmnp", "unit_price": 75, "quantity": 1, "lmnp_criteria": ["occultation"], "product_url": "https://www.ikea.com/fr/fr/p/majgull-rideau-occultant-2-panneaux-gris-clair-10558995/"},
    # Socle LMNP — rangements
    {"name": "Penderie / rangement vêtements",  "reference": "PAX",         "category": "rangements",  "retailer": "IKEA",             "tag_type": "essentiel_lmnp", "unit_price": 160,"quantity": 1, "lmnp_criteria": ["rangements"],  "product_url": "https://www.ikea.com/fr/fr/p/pax-armoire-blanc-00294785/"},
    # Socle LMNP — table + chaises
    {"name": "Table + 2 chaises",               "reference": "LACK / NORDMYRA", "category": "table",   "retailer": "IKEA",             "tag_type": "essentiel_lmnp", "unit_price": 90, "quantity": 1, "lmnp_criteria": ["table_chaises"]},
    # Socle LMNP — luminaires
    {"name": "Plafonnier + lampe de chevet",    "reference": "RANARP",      "category": "luminaires",  "retailer": "IKEA",             "tag_type": "essentiel_lmnp", "unit_price": 75, "quantity": 1, "lmnp_criteria": ["luminaires"]},
    # Confort Standard
    {"name": "Étagères murales",                "reference": "KALLAX",      "category": "etagere",     "retailer": "IKEA",             "tag_type": "confort",        "unit_price": 59, "quantity": 1, "lmnp_criteria": [], "gamme_min": "standard"},
    {"name": "Meuble TV compact",               "reference": "BESTA",       "category": "meuble_tv",   "retailer": "IKEA",             "tag_type": "confort",        "unit_price": 110,"quantity": 1, "lmnp_criteria": [], "gamme_min": "standard"},
    {"name": "Tapis de séjour",                 "reference": "Set déco",    "category": "tapis",       "retailer": "Maisons du Monde", "tag_type": "confort",        "unit_price": 89, "quantity": 1, "lmnp_criteria": [], "gamme_min": "standard"},
    # Confort Premium
    {"name": "Décoration murale (cadres)",      "reference": "Set déco",    "category": "deco",        "retailer": "Maisons du Monde", "tag_type": "confort",        "unit_price": 79, "quantity": 1, "lmnp_criteria": [], "gamme_min": "premium"},
]


# ══════════════════════════════════════════════════════════════════════
# MOTEUR D'ADAPTATION
# ══════════════════════════════════════════════════════════════════════

def _get_profile(property_type: str, rooms_count: int) -> str:
    """
    Profil typologique : small | medium | large.
      small  → studio / T1 (pièce unique ou chambre+séjour fusionnés)
      medium → T2 (chambre séparée + séjour séparé)
      large  → T3 / T4+ / colocation (2+ chambres)
    """
    pt = (property_type or "").lower().strip()
    if pt in ("studio", "t1"):
        return "small"
    if pt == "t2":
        return "medium"
    return "large"


def _is_compact(surface_m2: float, profile: str) -> bool:
    """Studio compact : pièce unique chambre+séjour (canapé-lit)."""
    return profile == "small" and surface_m2 < COMPACT_THRESHOLD_M2


def _is_large_surface(surface_m2: float, profile: str) -> bool:
    return surface_m2 >= LARGE_SURFACE.get(profile, 999)


def _gamme_rank(budget_level: str) -> int:
    return {"economique": 0, "standard": 1, "premium": 2}.get(budget_level, 1)


def _filter_items(
    items: List[Dict],
    budget_level: str,
    compact: bool,
    large_surface: bool,
) -> List[Dict]:
    """
    Filtre le catalogue selon :
    - compact_only / large_only (contrainte surface)
    - gamme_min (niveau de gamme requis pour l'item)
    - gamme économique → exclusion des items Confort avec gamme_min explicite
    """
    rank = _gamme_rank(budget_level)
    result = []
    for item in items:
        if item.get("compact_only") and not compact:
            continue
        if item.get("large_only") and not large_surface:
            continue
        gamme_min = item.get("gamme_min")
        if gamme_min and rank < _gamme_rank(gamme_min):
            continue
        if budget_level == "economique" and item["tag_type"] == "confort" and gamme_min:
            continue
        result.append(deepcopy(item))
    return result


def _apply_price_multiplier(items: List[Dict], budget_level: str) -> List[Dict]:
    """Applique le multiplicateur de gamme sur unit_price (plancher = 1 €)."""
    mult = GAMME_MULT.get(budget_level, 1.0)
    for item in items:
        item["unit_price"] = max(1, round(item["unit_price"] * mult))
    return items


def _make_room_items(
    base_catalogue: List[Dict],
    budget_level: str,
    compact: bool,
    large_surface: bool,
    extra_catalogues: List[List[Dict]] | None = None,
) -> List[Dict]:
    """
    Construit la liste d'items d'une room :
    1. Filtre le catalogue de base selon surface / gamme
    2. Ajoute les catalogues extra (tenant_profile, etc.)
    3. Applique le multiplicateur de gamme
    """
    items = _filter_items(base_catalogue, budget_level, compact, large_surface)
    for extra in (extra_catalogues or []):
        items += _filter_items(extra, budget_level, compact, large_surface)
    return _apply_price_multiplier(items, budget_level)


# ══════════════════════════════════════════════════════════════════════
# CONSTRUCTION DES ROOMS PAR PROFIL TYPOLOGIQUE
# ══════════════════════════════════════════════════════════════════════

def build_rooms_catalogue(
    profile: str,
    rooms_count: int,
    tenant_profile: str,
    budget_level: str,
    compact: bool,
    large_surface: bool,
) -> List[Dict]:
    """
    Construit la liste des rooms adaptées au profil typologique.

    room_type values (alignés frontend v2 + spec Perplexity) :
      chambre_sejour → studio compact (pièce unique)
      bedroom        → chambre séparée (T2/T3/T4)
      living_room    → séjour séparé  (T2/T3/T4)
      kitchen        → cuisine (tous profils)
      bathroom       → salle de bain (tous profils)

    Phase 2 : remplacer par generate_catalogue_from_llm(property).
    """

    def make(base, *extras):
        return _make_room_items(
            base, budget_level, compact, large_surface,
            extra_catalogues=list(extras) if extras else None,
        )

    rooms: List[Dict] = []

    # ── small (studio / T1) ────────────────────────────────────────────
    if profile == "small":
        extras = []
        if tenant_profile == "etudiant":
            extras.append(ITEMS_BUREAU)
        if tenant_profile == "courte_duree":
            extras.append(ITEMS_COURTE_DUREE_SEJOUR)

        rooms.append({
            "room_type": "chambre_sejour",
            "label": "Chambre / Séjour",
            "items": make(ITEMS_CHAMBRE_SEJOUR, *extras),
        })

    # ── medium (T2) ────────────────────────────────────────────────────
    elif profile == "medium":
        # Chambre (+ bureau si étudiant ou jeune_actif)
        bedroom_extras = []
        if tenant_profile in ("etudiant", "jeune_actif"):
            bedroom_extras.append(ITEMS_BUREAU)

        rooms.append({
            "room_type": "bedroom",
            "label": "Chambre",
            "items": make(ITEMS_BEDROOM, *bedroom_extras),
        })

        # Séjour (+ extras selon profil)
        living_extras = []
        if tenant_profile == "famille":
            living_extras.append(ITEMS_LIVING_FAMILLE)
        if tenant_profile == "courte_duree":
            living_extras.append(ITEMS_COURTE_DUREE_SEJOUR)

        rooms.append({
            "room_type": "living_room",
            "label": "Séjour",
            "items": make(ITEMS_LIVING_ROOM, *living_extras),
        })

    # ── large (T3 / T4+ / colocation) ──────────────────────────────────
    else:
        nb_chambres = max(2, min((rooms_count or 2) - 1, 5))

        bedroom_extras = []
        if tenant_profile in ("etudiant", "jeune_actif"):
            bedroom_extras.append(ITEMS_BUREAU)

        for i in range(nb_chambres):
            label = "Chambre principale" if i == 0 else f"Chambre {i + 1}"
            rooms.append({
                "room_type": "bedroom",
                "label": label,
                "items": make(ITEMS_BEDROOM, *bedroom_extras),
            })

        living_extras = []
        if tenant_profile == "famille":
            living_extras.append(ITEMS_LIVING_FAMILLE)
        if tenant_profile == "courte_duree":
            living_extras.append(ITEMS_COURTE_DUREE_SEJOUR)

        rooms.append({
            "room_type": "living_room",
            "label": "Séjour",
            "items": make(ITEMS_LIVING_ROOM, *living_extras),
        })

    # Cuisine (tous profils)
    rooms.append({
        "room_type": "kitchen",
        "label": "Cuisine",
        "items": make(ITEMS_KITCHEN),
    })

    # Salle de bain (tous profils — inclut le kit entretien LMNP obligatoire)
    rooms.append({
        "room_type": "bathroom",
        "label": "Salle de bain",
        "items": make(ITEMS_BATHROOM),
    })

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
                id=str(uuid.uuid4()),
                code=code,
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
    Génère un Pack LMNP adaptatif depuis une Property SQLAlchemy.

    Flux :
      1. Calcul du profil typologique (small / medium / large)
      2. Construction du catalogue de rooms adapté (gabarits + filtres)
      3. Persistance en base (Pack → Room[] → PackItem[] → Retailer[])
      4. Calcul lmnp_checklist (11 critères décret 2015-981)
      5. Calcul total_price, is_lmnp_compliant, savings_amount/percent

    Retourne le Pack persisté (non committé — le commit est fait dans le router).
    """
    profile       = _get_profile(property.property_type, property.rooms_count or 1)
    budget_level  = property.budget_level or "standard"
    surface       = float(property.surface_m2 or 40)
    compact       = _is_compact(surface, profile)
    large_surface = _is_large_surface(surface, profile)
    tenant        = property.tenant_profile or "jeune_actif"
    rooms_count   = property.rooms_count or 2

    rooms_catalogue = build_rooms_catalogue(
        profile=profile,
        rooms_count=rooms_count,
        tenant_profile=tenant,
        budget_level=budget_level,
        compact=compact,
        large_surface=large_surface,
    )

    lmnp_criteria_map = _ensure_lmnp_criteria(db)

    pack_id = str(uuid.uuid4())
    pack = Pack(
        id=pack_id,
        project_id=project_id,
        total_price=0,
        is_lmnp_compliant=False,
        currency="EUR",
    )
    db.add(pack)
    db.flush()

    total_price:   int      = 0
    covered_codes: Set[str] = set()

    for room_def in rooms_catalogue:
        room_id = str(uuid.uuid4())
        room = Room(
            id=room_id,
            pack_id=pack_id,
            room_type=room_def["room_type"],
            label=room_def["label"],
            mandatory_items_count=0,
            total_price=0,
        )
        db.add(room)
        db.flush()

        room_total = 0
        mand = 0

        for item_def in room_def["items"]:
            retailer = _get_or_create_retailer(db, item_def["retailer"])
            qty      = item_def["quantity"]
            uprice   = item_def["unit_price"]
            tprice   = qty * uprice

            db.add(PackItem(
                id=str(uuid.uuid4()),
                pack_id=pack_id,
                room_id=room_id,
                retailer_id=retailer.id,
                name=item_def["name"],
                reference=item_def.get("reference"),
                category=item_def.get("category"),
                tag_type=item_def["tag_type"],
                unit_price=uprice,
                quantity=qty,
                total_price=tprice,
                product_url=item_def.get("product_url"),
            ))

            room_total  += tprice
            total_price += tprice

            if item_def["tag_type"] == "essentiel_lmnp":
                mand += 1

            for code in item_def.get("lmnp_criteria", []):
                if code in lmnp_criteria_map:
                    covered_codes.add(code)

        room.total_price           = room_total
        room.mandatory_items_count = mand

    # Checklist LMNP — 11 critères décret 2015-981
    for code, crit in lmnp_criteria_map.items():
        db.add(PackLmnpCriterion(
            id=str(uuid.uuid4()),
            pack_id=pack_id,
            criterion_id=crit.id,
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
