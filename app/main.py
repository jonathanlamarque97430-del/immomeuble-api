"""
app/main.py — IMMOMEUBLE FastAPI v2

Nouveautés v2 :
- SQLAlchemy + SQLite (dev) / PostgreSQL (prod)
- Router /projects avec les 4 endpoints
- Création automatique des tables au démarrage
- Ancien router /packs conservé (rétrocompatibilité)
"""

from __future__ import annotations
import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import engine
from app.models import Base
from app.routers import properties, packs
from app.routers import projects  # nouveau

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)

# Création automatique des tables (dev). En prod : utiliser Alembic.
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="IMMOMEUBLE API",
    description=(
        "Génération de packs mobilier LMNP.\n\n"
        "**v2** : SQLAlchemy + SQLite/PostgreSQL, endpoints /projects.\n"
        "**v1** : endpoints /packs (conservés pour rétrocompatibilité)."
    ),
    version="2.0.0",
)

# CORS : origines autorisées (prod via variable d'environnement)
# Exemple prod : ALLOWED_ORIGINS="https://monapp.com,https://admin.monapp.com"
_raw_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:3000")
ALLOWED_ORIGINS = [o.strip() for o in _raw_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(projects.router)   # /projects/** — v2 (frontend v13)
app.include_router(packs.router)      # /packs/**    — v1 (rétrocompatibilité)
app.include_router(properties.router) # /properties/ — v1


@app.get("/health", tags=["system"])
def health() -> dict:
    return {
        "status": "ok",
        "version": "2.0.0",
        "storage": "sqlite+sqlalchemy",
    }
