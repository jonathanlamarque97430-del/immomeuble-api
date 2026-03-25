"""
app/models.py — Modèles SQLAlchemy IMMOMEUBLE

Entités :
  Project → Property (1-1) → Pack (1-1)
  Pack → Room[] → PackItem[]
  PackItem → Retailer (N-1)
  Pack → PackLmnpCriterion[] → LmnpCriterion

Usage :
  SQLite en développement (via DATABASE_URL = "sqlite:///./immomeuble.db")
  PostgreSQL en production  (via DATABASE_URL = "postgresql+psycopg2://...")
"""

from __future__ import annotations
from datetime import datetime, timezone
from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey,
    Integer, String, Text,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


# ─────────────────────────────────────────────────────────────────────────────
# Project — point d'entrée, lié au projet de pack LMNP
# ─────────────────────────────────────────────────────────────────────────────

class Project(Base):
    __tablename__ = "projects"

    id          = Column(String, primary_key=True)           # UUID str
    public_slug = Column(String, unique=True, index=True, nullable=False)
    created_at  = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at  = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    property = relationship("Property", back_populates="project", uselist=False,
                            cascade="all, delete-orphan")
    pack     = relationship("Pack",     back_populates="project", uselist=False,
                            cascade="all, delete-orphan")


# ─────────────────────────────────────────────────────────────────────────────
# Property — description du bien (formulaire Étape 1)
# Champs calqués sur PropertyCreate (schemas.py)
# ─────────────────────────────────────────────────────────────────────────────

class Property(Base):
    __tablename__ = "properties"

    id         = Column(String, primary_key=True)
    project_id = Column(String, ForeignKey("projects.id"), nullable=False, index=True)

    # Bien
    property_type = Column(String, nullable=False)  # T2, studio…
    surface_m2    = Column(Float,  nullable=False)
    rooms_count   = Column(Integer, nullable=False)

    # Localisation
    city        = Column(String, nullable=False)
    postal_code = Column(String, nullable=False)

    # Profil
    tenant_profile = Column(String, nullable=False)  # jeune_actif…
    rental_type    = Column(String, nullable=True)   # longue_duree / courte_duree
    decor_style    = Column(String, nullable=True)   # contemporain…

    # Budget
    budget_level = Column(String,  nullable=False)   # economique / standard / premium
    budget_min   = Column(Integer, nullable=True)
    budget_max   = Column(Integer, nullable=True)

    project = relationship("Project", back_populates="property")


# ─────────────────────────────────────────────────────────────────────────────
# Pack — pack LMNP généré
# ─────────────────────────────────────────────────────────────────────────────

class Pack(Base):
    __tablename__ = "packs"

    id         = Column(String, primary_key=True)
    project_id = Column(String, ForeignKey("projects.id"), nullable=False, index=True)

    total_price       = Column(Integer, nullable=False)  # centimes ou euros entiers
    is_lmnp_compliant = Column(Boolean, default=False)
    savings_amount    = Column(Integer, nullable=True)   # budget_max - total_price
    savings_percent   = Column(Float,   nullable=True)
    currency          = Column(String,  default="EUR")

    project = relationship("Project", back_populates="pack")
    rooms   = relationship("Room",    back_populates="pack",
                           cascade="all, delete-orphan", order_by="Room.id")
    items   = relationship("PackItem", back_populates="pack",
                           cascade="all, delete-orphan")
    lmnp_criteria_links = relationship("PackLmnpCriterion", back_populates="pack",
                                       cascade="all, delete-orphan")


# ─────────────────────────────────────────────────────────────────────────────
# Room — pièce du pack (chambre, séjour, cuisine…)
# ─────────────────────────────────────────────────────────────────────────────

class Room(Base):
    __tablename__ = "rooms"

    id      = Column(String, primary_key=True)
    pack_id = Column(String, ForeignKey("packs.id"), nullable=False, index=True)

    room_type             = Column(String,  nullable=False)  # chambre, sejour…
    label                 = Column(String,  nullable=False)  # libellé affiché
    mandatory_items_count = Column(Integer, default=0)
    total_price           = Column(Integer, default=0)

    pack  = relationship("Pack",     back_populates="rooms")
    items = relationship("PackItem", back_populates="room",
                         order_by="PackItem.name")


# ─────────────────────────────────────────────────────────────────────────────
# Retailer — enseigne (IKEA, But, Boulanger…)
# ─────────────────────────────────────────────────────────────────────────────

class Retailer(Base):
    __tablename__ = "retailers"

    id          = Column(String, primary_key=True)
    name        = Column(String, unique=True, nullable=False)
    website_url = Column(String, nullable=True)

    items = relationship("PackItem", back_populates="retailer")


# ─────────────────────────────────────────────────────────────────────────────
# PackItem — ligne d'item mobilier (lit, canapé, plaques…)
# ─────────────────────────────────────────────────────────────────────────────

class PackItem(Base):
    __tablename__ = "pack_items"

    id          = Column(String, primary_key=True)
    pack_id     = Column(String, ForeignKey("packs.id"),     nullable=False, index=True)
    room_id     = Column(String, ForeignKey("rooms.id"),     nullable=True,  index=True)
    retailer_id = Column(String, ForeignKey("retailers.id"), nullable=False)

    name      = Column(String, nullable=False)
    reference = Column(String, nullable=True)
    category  = Column(String, nullable=True)

    # "essentiel_lmnp" | "confort"
    tag_type  = Column(String, nullable=False)

    unit_price  = Column(Integer, nullable=False)  # € entiers
    quantity    = Column(Integer, nullable=False, default=1)
    total_price = Column(Integer, nullable=False)

    product_url = Column(Text, nullable=True)  # Phase 3

    pack     = relationship("Pack",     back_populates="items")
    room     = relationship("Room",     back_populates="items")
    retailer = relationship("Retailer", back_populates="items")


# ─────────────────────────────────────────────────────────────────────────────
# LmnpCriterion — catalogue des critères décret 2015-981
# ─────────────────────────────────────────────────────────────────────────────

class LmnpCriterion(Base):
    __tablename__ = "lmnp_criteria"

    id          = Column(String, primary_key=True)
    code        = Column(String, unique=True, nullable=False)  # "couchage"…
    label       = Column(String, nullable=False)               # "Couchage (lit + matelas)"
    description = Column(Text,   nullable=True)

    packs = relationship("PackLmnpCriterion", back_populates="criterion")


# ─────────────────────────────────────────────────────────────────────────────
# PackLmnpCriterion — liaison Pack ↔ LmnpCriterion avec statut is_covered
# ─────────────────────────────────────────────────────────────────────────────

class PackLmnpCriterion(Base):
    __tablename__ = "pack_lmnp_criteria"

    id           = Column(String, primary_key=True)
    pack_id      = Column(String, ForeignKey("packs.id"),         nullable=False, index=True)
    criterion_id = Column(String, ForeignKey("lmnp_criteria.id"), nullable=False)

    is_covered = Column(Boolean, default=False)

    pack      = relationship("Pack",          back_populates="lmnp_criteria_links")
    criterion = relationship("LmnpCriterion", back_populates="packs")
