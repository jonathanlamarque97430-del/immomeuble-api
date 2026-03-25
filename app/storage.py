"""
app/storage.py — Stockage en mémoire (Phase 1 MVP).

Interface identique à ce que sera crud.py (Phase 2 PostgreSQL).
Pour migrer : remplacer les imports de storage par crud dans les routers.
"""

from __future__ import annotations
from typing import Optional
from app.schemas import PackDomain, PropertyRead

_properties: dict[str, PropertyRead] = {}
_packs:      dict[str, PackDomain]   = {}


def save_property(prop: PropertyRead) -> PropertyRead:
    _properties[prop.id] = prop
    return prop


def save_pack(pack: PackDomain) -> PackDomain:
    _packs[pack.id] = pack
    return pack


def get_pack(pack_id: str) -> Optional[PackDomain]:
    return _packs.get(pack_id)


def get_property(property_id: str) -> Optional[PropertyRead]:
    return _properties.get(property_id)
