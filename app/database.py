# app/database.py — Configuration SQLAlchemy (PostgreSQL production)

from __future__ import annotations

import os
from typing import Generator

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker, declarative_base

load_dotenv()

# URL de connexion (doit venir de .env ou des variables d'environnement)
DATABASE_URL: str = os.environ["DATABASE_URL"]  # Erreur claire si absent
print("DATABASE_URL UTILISÉE :", DATABASE_URL)

# Base pour les modèles
Base = declarative_base()

# Engine PostgreSQL
engine = create_engine(
    DATABASE_URL,
    echo=bool(int(os.getenv("SQL_ECHO", "0"))),  # SQL_ECHO=1 pour voir les requêtes SQL
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

# Dépendance FastAPI pour avoir une session DB par requête
def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
