"""
tests/test_api.py — Tests IMMOMEUBLE MVP v0.3

Lance avec : pytest tests/ -v
"""

from __future__ import annotations
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.schemas import PackScreenResponse, PropertyBase
from app.services.packs import (
    _mock_generate_pack,
    _compute_lmnp_checklist,
    LMNP_MANDATORY_CATEGORIES,
)

client = TestClient(app)

VALID = {
    "type_de_bien":             "T2",
    "surface_totale":           45,
    "nb_pieces":                2,
    "cible_locataire":          "jeune_actif",
    "niveau_gamme":             "standard",
    "budget_min":               3000,
    "budget_max":               6000,
    "localisation_ville":       "Paris",
    "localisation_code_postal": "75011",
}


# ── Schémas ────────────────────────────────────────────────────────────────────

class TestPropertyBase:
    def test_valid(self):
        p = PropertyBase(**VALID)
        assert p.type_de_bien == "T2"
        assert p.budget_total == 4500.0

    def test_budget_inversion_raises(self):
        with pytest.raises(Exception, match="budget_max"):
            PropertyBase(**{**VALID, "budget_min": 8000, "budget_max": 1000})

    def test_invalid_cible(self):
        with pytest.raises(Exception):
            PropertyBase(**{**VALID, "cible_locataire": "inconnu"})

    def test_invalid_gamme(self):
        with pytest.raises(Exception):
            PropertyBase(**{**VALID, "niveau_gamme": "luxe"})


# ── POST /properties/ ──────────────────────────────────────────────────────────

class TestProperties:
    def test_creates(self):
        r = client.post("/properties/", json=VALID)
        assert r.status_code == 201
        assert "id" in r.json()

    def test_422_on_bad_surface(self):
        r = client.post("/properties/", json={**VALID, "surface_totale": 2})
        assert r.status_code == 422


# ── POST /packs/generate ───────────────────────────────────────────────────────

class TestGeneratePack:
    def test_returns_pack_screen(self):
        r = client.post("/packs/generate", json=VALID)
        assert r.status_code == 201
        data = r.json()
        # Champs racine
        assert "project_id" in data
        assert "pack_id"    in data
        assert data["step"] == 2

    def test_property_context(self):
        r = client.post("/packs/generate", json=VALID).json()
        p = r["property"]
        assert p["type_de_bien"]  == "T2"
        assert p["ville"]         == "Paris"
        assert p["budget_min"]    == 3000
        assert p["budget_max"]    == 6000
        assert p["budget_total"]  == 4500.0

    def test_pack_summary(self):
        r = client.post("/packs/generate", json=VALID).json()
        s = r["pack_summary"]
        assert s["total_cost_estimated"] > 0
        assert s["currency"] == "EUR"
        assert "economy_vs_budget" in s
        assert "economy_vs_budget_percent" in s
        assert isinstance(s["lmnp_compliant"], bool)

    def test_rooms_present(self):
        r = client.post("/packs/generate", json=VALID).json()
        rooms = r["rooms"]
        assert len(rooms) >= 2
        for room in rooms:
            assert room["room_total_cost"] > 0
            assert len(room["items"]) > 0

    def test_items_have_prices_and_brands(self):
        r = client.post("/packs/generate", json=VALID).json()
        for room in r["rooms"]:
            for item in room["items"]:
                assert item["unit_price"] > 0
                assert item["total_price"] > 0
                assert item["priority"] in ("mandatory", "recommended", "optional")
                assert isinstance(item["is_lmnp_mandatory"], bool)

    def test_lmnp_checklist_present(self):
        r = client.post("/packs/generate", json=VALID).json()
        cl = r["lmnp_checklist"]
        assert "categories_covered" in cl
        assert "categories_missing" in cl
        assert cl["global_status"] in ("compliant", "ok_with_minor_missing", "non_compliant")

    def test_economy_sign(self):
        # budget_max 10 000 >> coût estimé → économie positive
        r = client.post("/packs/generate", json={**VALID, "budget_max": 10000}).json()
        assert r["pack_summary"]["economy_vs_budget"] > 0

    def test_gamme_premium_more_expensive(self):
        r_eco = client.post("/packs/generate", json={**VALID, "niveau_gamme": "economique"}).json()
        r_pre = client.post("/packs/generate", json={**VALID, "niveau_gamme": "premium"}).json()
        assert r_eco["pack_summary"]["total_cost_estimated"] < r_pre["pack_summary"]["total_cost_estimated"]

    def test_t3_has_two_bedrooms(self):
        r = client.post("/packs/generate", json={**VALID, "type_de_bien": "T3", "nb_pieces": 3, "surface_totale": 65}).json()
        bedrooms = [ro for ro in r["rooms"] if ro["type"] == "bedroom"]
        assert len(bedrooms) == 2

    def test_missing_field_422(self):
        payload = {k: v for k, v in VALID.items() if k != "type_de_bien"}
        assert client.post("/packs/generate", json=payload).status_code == 422


# ── GET /packs/{pack_id} ───────────────────────────────────────────────────────

class TestGetPack:
    def test_retrieves_pack(self):
        gen = client.post("/packs/generate", json=VALID).json()
        r   = client.get(f"/packs/{gen['pack_id']}")
        assert r.status_code == 200
        assert r.json()["pack_id"] == gen["pack_id"]

    def test_unknown_404(self):
        assert client.get("/packs/00000000-fake").status_code == 404


# ── GET /packs/{pack_id}/merchants ────────────────────────────────────────────

class TestMerchantBreakdown:
    def test_merchants_endpoint_returns_blocks(self):
        gen     = client.post("/packs/generate", json=VALID).json()
        pack_id = gen["pack_id"]

        r    = client.get(f"/packs/{pack_id}/merchants")
        assert r.status_code == 200
        data = r.json()

        assert "merchants"  in data
        assert "summary"    in data
        assert data["pack_id"]                  == pack_id
        assert data["step"]                     == 3
        assert data["summary"]["total_merchants"] >= 1
        assert data["summary"]["total_items"]     >= 1

    def test_merchant_subtotals_match_total(self):
        gen      = client.post("/packs/generate", json=VALID).json()
        pack_id  = gen["pack_id"]
        total_pack = gen["pack_summary"]["total_cost_estimated"]

        data = client.get(f"/packs/{pack_id}/merchants").json()
        subtotal = sum(m["merchant_subtotal"] for m in data["merchants"])

        # Tolérance arrondi flottant
        assert abs(subtotal - total_pack) < 1.0, (
            f"Sous-totaux enseignes ({subtotal:.2f} €) incohérents "
            f"avec total pack ({total_pack:.2f} €)"
        )

    def test_unknown_pack_merchants_404(self):
        r = client.get("/packs/00000000-fake/merchants")
        assert r.status_code == 404

    def test_merchants_sorted_by_subtotal_desc(self):
        gen     = client.post("/packs/generate", json=VALID).json()
        data    = client.get(f"/packs/{gen['pack_id']}/merchants").json()
        subs    = [m["merchant_subtotal"] for m in data["merchants"]]
        assert subs == sorted(subs, reverse=True), \
            f"Enseignes non triées DESC : {subs}"

    def test_each_merchant_has_name_and_items(self):
        gen  = client.post("/packs/generate", json=VALID).json()
        data = client.get(f"/packs/{gen['pack_id']}/merchants").json()
        for merchant in data["merchants"]:
            assert merchant["merchant_name"], "merchant_name vide"
            assert len(merchant["items"]) >= 1, (
                f"Enseigne '{merchant['merchant_name']}' sans items"
            )

    def test_each_item_has_required_fields(self):
        gen  = client.post("/packs/generate", json=VALID).json()
        data = client.get(f"/packs/{gen['pack_id']}/merchants").json()
        for merchant in data["merchants"]:
            for item in merchant["items"]:
                assert item["item_name"],    "item_name vide"
                assert item["room_name"],    "room_name vide"
                assert item["quantity"] >= 1
                assert item["unit_price"]  >= 0
                assert item["total_price"] >= 0
                # Cohérence : total = unit × qty (à 0.01 près)
                expected = round(item["unit_price"] * item["quantity"], 2)
                assert abs(item["total_price"] - expected) < 0.02, (
                    f"total_price incohérent pour '{item['item_name']}' : "
                    f"{item['total_price']} vs {expected}"
                )

    def test_summary_lmnp_status_valid(self):
        gen  = client.post("/packs/generate", json=VALID).json()
        data = client.get(f"/packs/{gen['pack_id']}/merchants").json()
        assert data["summary"]["lmnp_status"] in (
            "compliant", "ok_with_minor_missing", "non_compliant"
        )

    def test_summary_total_equals_summary_field(self):
        gen     = client.post("/packs/generate", json=VALID).json()
        data    = client.get(f"/packs/{gen['pack_id']}/merchants").json()
        summary = data["summary"]
        merchants = data["merchants"]
        computed  = round(sum(m["merchant_subtotal"] for m in merchants), 2)
        assert abs(summary["total_amount"] - computed) < 0.02, (
            f"summary.total_amount ({summary['total_amount']}) "
            f"≠ somme des subtotals ({computed})"
        )

    def test_total_items_count_matches_items(self):
        gen     = client.post("/packs/generate", json=VALID).json()
        data    = client.get(f"/packs/{gen['pack_id']}/merchants").json()
        counted = sum(len(m["items"]) for m in data["merchants"])
        assert data["summary"]["total_items"] == counted, (
            f"summary.total_items ({data['summary']['total_items']}) "
            f"≠ items comptés ({counted})"
        )

    def test_no_items_lost_vs_pack(self):
        """Vérifie que le nombre de lignes items dans le breakdown
        égale le nombre total d'items dans le pack d'origine."""
        gen      = client.post("/packs/generate", json=VALID).json()
        pack_id  = gen["pack_id"]
        pack_items_count = sum(len(room["items"]) for room in gen["rooms"])

        data = client.get(f"/packs/{pack_id}/merchants").json()
        breakdown_items_count = sum(len(m["items"]) for m in data["merchants"])

        assert breakdown_items_count == pack_items_count, (
            f"Items perdus : breakdown={breakdown_items_count} "
            f"vs pack={pack_items_count}"
        )

    def test_project_id_format(self):
        gen  = client.post("/packs/generate", json=VALID).json()
        data = client.get(f"/packs/{gen['pack_id']}/merchants").json()
        assert data["project_id"].startswith("proj_"), \
            f"project_id mal formé : {data['project_id']}"



class TestLMNPCompliance:
    def test_standard_pack_compliant(self):
        from datetime import datetime, timezone
        from uuid import uuid4
        from app.schemas import PropertyRead
        prop = PropertyRead(id=str(uuid4()), created_at=datetime.now(timezone.utc), **VALID)
        pack = _mock_generate_pack(prop)
        result = _compute_lmnp_checklist(pack)
        assert result.is_compliant or result.global_status in ("compliant", "ok_with_minor_missing"), \
            f"Manquants : {result.categories_missing}"

    def test_all_mandatory_categories_in_pack(self):
        from datetime import datetime, timezone
        from uuid import uuid4
        from app.schemas import PropertyRead
        prop = PropertyRead(id=str(uuid4()), created_at=datetime.now(timezone.utc), **VALID)
        pack = _mock_generate_pack(prop)
        found = {i.category for r in pack.rooms for i in r.items if i.priority == "mandatory"}
        missing = LMNP_MANDATORY_CATEGORIES - found
        assert not missing, f"Catégories LMNP manquantes dans le mock : {missing}"

    def test_studio_compliant(self):
        payload = {**VALID, "type_de_bien": "studio", "nb_pieces": 1, "surface_totale": 22}
        r = client.post("/packs/generate", json=payload).json()
        assert r["lmnp_checklist"]["global_status"] in ("compliant", "ok_with_minor_missing")

    def test_sdb_added_for_large_surface(self):
        r = client.post("/packs/generate", json={**VALID, "surface_totale": 55}).json()
        types = [ro["type"] for ro in r["rooms"]]
        assert "bathroom" in types

    def test_sdb_not_added_for_small_surface(self):
        r = client.post("/packs/generate", json={**VALID, "surface_totale": 22}).json()
        types = [ro["type"] for ro in r["rooms"]]
        assert "bathroom" not in types


# ── Health ─────────────────────────────────────────────────────────────────────

def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
