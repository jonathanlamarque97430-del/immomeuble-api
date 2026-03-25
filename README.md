# IMMOMEUBLE — MVP v2

Plateforme IA qui génère des packs de mobilier LMNP conformes au décret 2015-981,
optimisés par profil typologique, gamme et cible locataire.

## Stack technique

| Couche | Technologie |
|---|---|
| Backend | FastAPI (Python 3.11+) |
| ORM | SQLAlchemy 2.0 + Pydantic v2 |
| Base de données | SQLite (dev) / PostgreSQL (prod) |
| Frontend React | React 18 + TypeScript + Vite |
| Frontend standalone | HTML/JS/CSS monofichier (démo) |
| Tests | pytest (89 tests production) |
| CI | GitHub Actions |

## Structure du projet

```
immomeuble/
├── app/
│   ├── main.py              # FastAPI app + CORS
│   ├── database.py          # Engine SQLAlchemy (SQLite/PostgreSQL)
│   ├── models.py            # 8 tables SQLAlchemy
│   ├── schemas.py           # Schémas Pydantic v1 (rétrocompat)
│   ├── schemas_v2.py        # Schémas Pydantic v2 (production)
│   ├── routers/
│   │   ├── projects.py      # /projects — 5 endpoints v2
│   │   └── packs.py         # /packs — endpoints v1
│   └── services/
│       └── generator.py     # Moteur adaptatif LMNP (catalogue + règles)
├── frontend/
│   ├── immomeuble-mvp-v15.html  # Démo standalone (ouvrir via http-server)
│   └── src/
│       ├── FlowLMNP.tsx         # Orchestrateur v1+v2
│       ├── steps/               # Step1 → Step4
│       ├── types/               # Types TS v1 + v2
│       └── api/immomeuble.ts    # Client HTTP
├── tests/
│   ├── test_projects.py     # 89 tests production (API v2)
│   └── test_api.py          # 35 tests rétrocompat (API v1)
├── conftest.py
├── requirements.txt
└── .github/workflows/test.yml  # CI GitHub Actions
```

## Démarrage local

```bash
# Backend
python -m venv .venv
.venv/Scripts/activate          # Windows
source .venv/bin/activate       # Mac/Linux
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Frontend standalone (démo)
cd frontend
python -m http.server 8080
# → http://localhost:8080/immomeuble-mvp-v15.html
```

## API v2 — Endpoints /projects

| Méthode | URL | Description |
|---|---|---|
| POST | /projects | Crée un projet + génère le pack |
| GET | /projects/{id}/pack | Récupère le pack (étape 2) |
| GET | /projects/{id}/retailers | Sourcing par enseigne (étape 3) |
| GET | /projects/{id}/summary | Résumé achat (étape 4) |
| GET | /projects/{id} | Accès direct par ID (partage) |

### Payload POST /projects

```json
{
  "property": {
    "property_type": "T2",
    "surface_m2": 45,
    "rooms_count": 2,
    "city": "Paris",
    "postal_code": "75011",
    "tenant_profile": "jeune_actif",
    "budget_level": "standard",
    "decor_style": "scandinave"
  }
}
```

Valeurs possibles :
- `property_type` : studio, T1, T2, T3, T4
- `tenant_profile` : jeune_actif, etudiant, famille, courte_duree
- `budget_level` : economique, standard, premium
- `decor_style` : scandinave, industriel, boheme, classique, moderne

## Moteur adaptatif LMNP

### Règles métier

1. **Profil typologique** : small (studio/T1) / medium (T2) / large (T3+)
2. **Pièces générées** : adaptées au profil
   - small → chambre_sejour + cuisine + SDB
   - medium → chambre + séjour + cuisine + SDB
   - large → N chambres + séjour + cuisine + SDB
3. **Socle LMNP** : 11 critères décret 2015-981 toujours couverts
4. **Cible locataire** : items supplémentaires (bureau étudiant, rangements famille, déco courte durée)
5. **Gamme** : économique ×0.70 / standard ×1.0 / premium ×1.65
6. **Surface** : compact <22m² → canapé-lit / grande surface → items large_only

### 11 critères LMNP (décret 2015-981)

| Code | Libellé |
|---|---|
| couchage | Lit + matelas |
| occultation | Rideaux occultants |
| plaques_cuisson | Plaques de cuisson |
| four_ou_microondes | Four / micro-ondes |
| refrigerateur | Réfrigérateur avec congélateur |
| vaisselle | Vaisselle & couverts |
| ustensiles_cuisine | Ustensiles de cuisine |
| table_chaises | Table + chaises |
| rangements | Rangements (armoire) |
| luminaires | Luminaires |
| entretien | Matériel d'entretien |

## Tests

```bash
# Lancer tous les tests
pytest tests/ -v

# Tests production uniquement (API v2)
pytest tests/test_projects.py -v

# Avec couverture
pip install pytest-cov
pytest tests/ --cov=app --cov-report=term-missing
```

Résultat attendu : **89 passed** (test_projects.py) + **35 passed** (test_api.py)

## Variables d'environnement

| Variable | Défaut | Description |
|---|---|---|
| DATABASE_URL | sqlite:///./immomeuble.db | URL SQLAlchemy |
| ALLOWED_ORIGINS | * | CORS origins (prod : mettre le domaine) |
| SQL_ECHO | (vide) | Activer logs SQL (SQL_ECHO=1) |

## Schéma de données (8 tables)

```
projects          → id (UUID), public_slug, created_at
properties        → project_id (FK), property_type, surface_m2, ...
packs             → project_id (FK), total_price, is_lmnp_compliant
rooms             → pack_id (FK), room_type, label, total_price
pack_items        → room_id (FK), name, retailer, tag_type, unit_price
retailers         → id, name, website_url
lmnp_criteria     → id, code, label
pack_lmnp_criteria→ pack_id (FK), criterion_id (FK), is_covered
```

## Ce qui manque pour la production complète

- [ ] Authentification (JWT ou API key par client)
- [ ] Migration vers PostgreSQL
- [ ] Déploiement serveur (Railway / Render / Fly.io)
- [ ] Liens d'affiliation réels (Awin, Effinity, Tradedoubler)
- [ ] Prix catalogue synchronisés (flux produit quotidien)
- [ ] Frontend React buildé et servi

## Auteur

Projet IMMOMEUBLE — MVP développé avec Claude (Anthropic)
