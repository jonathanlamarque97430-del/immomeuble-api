"""
tests/test_projects.py — Suite de tests production IMMOMEUBLE (API v2)

Couverture complète pour mise en production :
  1. Structure API           — forme exacte de chaque réponse
  2. Profils typologiques    — small / medium / large, règles de pièces
  3. Conformité LMNP         — 11 critères décret 2015-981
  4. Catalogue item par item — chaque critère LMNP couvert par le bon item
  5. Gammes                  — Budget < Standard < Premium
  6. Cibles locataires       — étudiant, famille, courte_duree
  7. Cohérence financière    — totaux, prix unitaires x quantités
  8. Endpoints GET           — /pack, /retailers, /summary, /{id}
  9. Flow E2E                — POST → GET pack → GET retailers → GET summary
  10. Validation Pydantic    — entrées invalides → 422
  11. Robustesse             — IDs inconnus, cas limites

Lance avec : pytest tests/test_projects.py -v
"""

from __future__ import annotations
import os
import pytest

os.environ["DATABASE_URL"] = "sqlite:///./test_immomeuble.db"

from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from app.main import app
from app.database import get_db, engine as app_engine
from app.models import Base, LmnpCriterion
from app.services.generator import LMNP_REQUIRED_CODES

TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=app_engine)

def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)

@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.drop_all(bind=app_engine)
    Base.metadata.create_all(bind=app_engine)
    yield
    Base.metadata.drop_all(bind=app_engine)


BASE_PAYLOAD = {
    "property_type": "T2", "surface_m2": 45, "rooms_count": 2,
    "city": "Sete", "postal_code": "34200",
    "tenant_profile": "jeune_actif", "budget_level": "standard",
    "decor_style": "scandinave",
}

def post_project(overrides=None):
    payload = {**BASE_PAYLOAD, **(overrides or {})}
    r = client.post("/projects", json={"property": payload})
    assert r.status_code == 201, f"POST /projects a echoue ({r.status_code}): {r.text}"
    return r.json()

def all_items(data):
    return [item for room in data["pack"]["rooms"] for item in room["items"]]

def item_names(data):
    return [i["name"].lower() for i in all_items(data)]

def covered_criteria(data):
    return {e["code"] for e in data["pack"]["lmnp_checklist"] if e["is_covered"]}


# ══════════════════════════════════════════════════════════════════════
# 1. STRUCTURE
# ══════════════════════════════════════════════════════════════════════

class TestStructure:

    def test_post_returns_201(self):
        r = client.post("/projects", json={"property": BASE_PAYLOAD})
        assert r.status_code == 201

    def test_project_pack_response_shape(self):
        data = post_project()
        for field in ("project_id", "public_slug", "property", "pack"):
            assert field in data

    def test_pack_shape(self):
        pack = post_project()["pack"]
        for field in ("id", "total_price", "is_lmnp_compliant", "rooms", "lmnp_checklist"):
            assert field in pack
        assert isinstance(pack["rooms"], list)
        assert isinstance(pack["lmnp_checklist"], list)

    def test_property_shape(self):
        prop = post_project()["property"]
        for field in ("property_type", "surface_m2", "rooms_count",
                      "city", "postal_code", "tenant_profile", "budget_level"):
            assert field in prop

    def test_room_shape(self):
        rooms = post_project()["pack"]["rooms"]
        assert len(rooms) > 0
        for field in ("id", "room_type", "label", "mandatory_items_count", "total_price", "items"):
            assert field in rooms[0]

    def test_item_shape(self):
        items = all_items(post_project())
        assert len(items) > 0
        for field in ("id", "name", "retailer", "tag_type", "unit_price", "quantity", "total_price"):
            assert field in items[0]

    def test_lmnp_checklist_shape(self):
        checklist = post_project()["pack"]["lmnp_checklist"]
        assert len(checklist) > 0
        for entry in checklist:
            for field in ("code", "label", "is_covered"):
                assert field in entry

    def test_public_slug_readable(self):
        slug = post_project()["public_slug"]
        assert "-" in slug and slug == slug.lower() and len(slug) > 8

    def test_project_id_is_string(self):
        pid = post_project()["project_id"]
        assert isinstance(pid, str) and len(pid) > 0

    def test_tag_type_values_valid(self):
        for item in all_items(post_project()):
            assert item["tag_type"] in ("essentiel_lmnp", "confort"), (
                f"tag_type invalide : {item['tag_type']} sur '{item['name']}'"
            )


# ══════════════════════════════════════════════════════════════════════
# 2. PROFILS TYPOLOGIQUES
# ══════════════════════════════════════════════════════════════════════

class TestProfilTypologique:

    def test_t2_medium_4_rooms(self):
        rooms = post_project()["pack"]["rooms"]
        types = {r["room_type"] for r in rooms}
        assert len(rooms) == 4
        assert {"chambre", "sejour", "cuisine", "sdb"} == types

    def test_studio_compact_chambre_sejour(self):
        rooms = post_project({"property_type": "studio", "surface_m2": 18, "rooms_count": 1})["pack"]["rooms"]
        types = [r["room_type"] for r in rooms]
        assert "chambre_sejour" in types
        assert "chambre" not in types

    def test_t3_large_2_chambres(self):
        rooms = post_project({"property_type": "T3", "surface_m2": 68, "rooms_count": 3})["pack"]["rooms"]
        chambres = [r for r in rooms if r["room_type"] == "chambre"]
        assert len(chambres) >= 2

    def test_studio_compact_canape_lit(self):
        names = item_names(post_project({"property_type": "studio", "surface_m2": 18, "rooms_count": 1}))
        assert any("canap" in n for n in names), "Studio compact doit avoir un canape-lit"

    def test_t1_treated_as_studio(self):
        rooms = post_project({"property_type": "T1", "surface_m2": 32, "rooms_count": 1})["pack"]["rooms"]
        types = {r["room_type"] for r in rooms}
        assert "chambre_sejour" in types


# ══════════════════════════════════════════════════════════════════════
# 3. CONFORMITE LMNP — 11 CRITERES DECRET 2015-981
# ══════════════════════════════════════════════════════════════════════

class TestLMNPCompliance:

    def test_t2_standard_lmnp_compliant(self):
        assert post_project()["pack"]["is_lmnp_compliant"] is True

    def test_studio_compact_lmnp_compliant(self):
        assert post_project({"property_type": "studio", "surface_m2": 18, "rooms_count": 1})["pack"]["is_lmnp_compliant"] is True

    def test_t3_famille_lmnp_compliant(self):
        assert post_project({"property_type": "T3", "surface_m2": 68, "rooms_count": 3, "tenant_profile": "famille"})["pack"]["is_lmnp_compliant"] is True

    def test_economique_lmnp_compliant(self):
        assert post_project({"budget_level": "economique"})["pack"]["is_lmnp_compliant"] is True

    def test_premium_lmnp_compliant(self):
        assert post_project({"budget_level": "premium"})["pack"]["is_lmnp_compliant"] is True

    def test_11_criteres_dans_checklist(self):
        checklist = post_project()["pack"]["lmnp_checklist"]
        codes = {e["code"] for e in checklist}
        for code in LMNP_REQUIRED_CODES:
            assert code in codes, f"Code LMNP manquant : {code}"

    def test_tous_criteres_couverts_t2(self):
        couverts = covered_criteria(post_project())
        for code in LMNP_REQUIRED_CODES:
            assert code in couverts, f"Critere non couvert en T2 Standard : {code}"

    def test_tous_criteres_couverts_studio(self):
        couverts = covered_criteria(post_project({"property_type": "studio", "surface_m2": 18, "rooms_count": 1}))
        for code in LMNP_REQUIRED_CODES:
            assert code in couverts, f"Critere non couvert en studio : {code}"

    def test_tous_criteres_couverts_economique(self):
        couverts = covered_criteria(post_project({"budget_level": "economique"}))
        for code in LMNP_REQUIRED_CODES:
            assert code in couverts, f"Critere non couvert en gamme Budget : {code}"


# ══════════════════════════════════════════════════════════════════════
# 4. CATALOGUE ITEM PAR ITEM
# ══════════════════════════════════════════════════════════════════════

class TestCatalogueItems:

    def test_couchage_present(self):
        names = item_names(post_project())
        assert any("lit" in n or "canap" in n for n in names)

    def test_occultation_presente(self):
        names = item_names(post_project())
        assert any("rideau" in n or "occult" in n for n in names)

    def test_plaques_cuisson_presentes(self):
        names = item_names(post_project())
        assert any("plaque" in n or "cuisson" in n for n in names)

    def test_microondes_present(self):
        names = item_names(post_project())
        assert any("micro" in n or "four" in n for n in names)

    def test_refrigerateur_present(self):
        names = item_names(post_project())
        assert any("refrig" in n or "frigo" in n for n in names)

    def test_vaisselle_presente(self):
        names = item_names(post_project())
        assert any("vaisselle" in n or "couvert" in n for n in names)

    def test_ustensiles_presents(self):
        names = item_names(post_project())
        assert any("ustensile" in n or "casserole" in n for n in names)

    def test_table_presente(self):
        names = item_names(post_project())
        assert any("table" in n for n in names)

    def test_chaises_presentes(self):
        names = item_names(post_project())
        assert any("chaise" in n for n in names)

    def test_rangements_presents(self):
        names = item_names(post_project())
        assert any("armoire" in n or "rangement" in n or "penderie" in n for n in names)

    def test_luminaires_presents(self):
        names = item_names(post_project())
        assert any("lumina" in n or "plafonnier" in n or "suspension" in n or "lampe" in n for n in names)

    def test_entretien_present(self):
        names = item_names(post_project())
        assert any("entretien" in n or "menager" in n for n in names)

    def test_nb_essentiels_ge_nb_criteres(self):
        items = all_items(post_project())
        essentiels = [i for i in items if i["tag_type"] == "essentiel_lmnp"]
        assert len(essentiels) >= len(LMNP_REQUIRED_CODES)

    def test_items_essentiels_ont_retailer(self):
        for item in all_items(post_project()):
            if item["tag_type"] == "essentiel_lmnp":
                assert item.get("retailer"), f"Retailer vide sur '{item['name']}'"


# ══════════════════════════════════════════════════════════════════════
# 5. GAMMES
# ══════════════════════════════════════════════════════════════════════

class TestGammes:

    def _total(self, level):
        return post_project({"budget_level": level})["pack"]["total_price"]

    def _count_confort(self, level):
        return sum(1 for i in all_items(post_project({"budget_level": level})) if i["tag_type"] == "confort")

    def test_ordre_prix(self):
        b, s, p = self._total("economique"), self._total("standard"), self._total("premium")
        assert b < s < p, f"Ordre prix incorrect : budget={b} standard={s} premium={p}"

    def test_budget_moins_confort(self):
        assert self._count_confort("economique") < self._count_confort("standard")

    def test_premium_plus_confort(self):
        assert self._count_confort("premium") > self._count_confort("standard")

    def test_ratio_budget_standard(self):
        ratio = self._total("economique") / self._total("standard")
        assert 0.25 <= ratio <= 0.85, f"Ratio Budget/Standard : {ratio:.2f}"

    def test_ratio_premium_standard(self):
        ratio = self._total("premium") / self._total("standard")
        assert 1.40 <= ratio <= 2.50, f"Ratio Premium/Standard : {ratio:.2f}"

    def test_essentiel_stable_toutes_gammes(self):
        for level in ("economique", "standard", "premium"):
            couverts = covered_criteria(post_project({"budget_level": level}))
            for code in LMNP_REQUIRED_CODES:
                assert code in couverts, f"Gamme '{level}' : critere '{code}' non couvert"

    def test_total_positif_toutes_gammes(self):
        for level in ("economique", "standard", "premium"):
            assert self._total(level) > 0


# ══════════════════════════════════════════════════════════════════════
# 6. CIBLES LOCATAIRES
# ══════════════════════════════════════════════════════════════════════

class TestCiblesLocataires:

    def test_etudiant_a_bureau(self):
        names = item_names(post_project({"tenant_profile": "etudiant"}))
        assert any("bureau" in n for n in names)

    def test_famille_a_rangements_supplementaires(self):
        def count_r(profile):
            data = post_project({"tenant_profile": profile, "property_type": "T3", "surface_m2": 68, "rooms_count": 3})
            return sum(1 for i in all_items(data) if "rangement" in i["name"].lower())
        assert count_r("famille") >= count_r("jeune_actif")

    def test_courte_duree_a_linge(self):
        names = item_names(post_project({"tenant_profile": "courte_duree"}))
        assert any("linge" in n or "drap" in n or "serviette" in n for n in names)

    def test_courte_duree_a_decoration(self):
        names = item_names(post_project({"tenant_profile": "courte_duree"}))
        assert any("deco" in n or "tableau" in n or "cadre" in n for n in names)

    def test_toutes_cibles_lmnp_compliant(self):
        for profile in ("jeune_actif", "etudiant", "courte_duree"):
            data = post_project({"tenant_profile": profile})
            assert data["pack"]["is_lmnp_compliant"] is True, f"Profil '{profile}' non conforme LMNP"

    def test_famille_t3_lmnp_compliant(self):
        data = post_project({"tenant_profile": "famille", "property_type": "T3", "surface_m2": 68, "rooms_count": 3})
        assert data["pack"]["is_lmnp_compliant"] is True


# ══════════════════════════════════════════════════════════════════════
# 7. COHERENCE FINANCIERE
# ══════════════════════════════════════════════════════════════════════

class TestCoherenceFinanciere:

    def test_total_positif(self):
        assert post_project()["pack"]["total_price"] > 0

    def test_pack_total_egal_somme_rooms(self):
        data = post_project()
        pack = data["pack"]
        rooms_sum = sum(r["total_price"] for r in pack["rooms"])
        assert pack["total_price"] == rooms_sum

    def test_room_total_egal_somme_items(self):
        for room in post_project()["pack"]["rooms"]:
            items_sum = sum(i["total_price"] for i in room["items"])
            assert room["total_price"] == items_sum, (
                f"Room '{room['label']}': {room['total_price']} != {items_sum}"
            )

    def test_item_total_egal_prix_x_qte(self):
        for item in all_items(post_project()):
            expected = item["unit_price"] * item["quantity"]
            assert item["total_price"] == expected, (
                f"'{item['name']}': {item['unit_price']}x{item['quantity']} != {item['total_price']}"
            )

    def test_unit_price_positif(self):
        for item in all_items(post_project()):
            assert item["unit_price"] > 0, f"unit_price <= 0 sur '{item['name']}'"

    def test_quantity_positive(self):
        for item in all_items(post_project()):
            assert item["quantity"] > 0, f"quantity <= 0 sur '{item['name']}'"

    def test_mandatory_items_count_coherent(self):
        for room in post_project()["pack"]["rooms"]:
            essentiels = sum(1 for i in room["items"] if i["tag_type"] == "essentiel_lmnp")
            assert room["mandatory_items_count"] == essentiels, (
                f"Room '{room['label']}': mandatory_items_count={room['mandatory_items_count']} != {essentiels}"
            )


# ══════════════════════════════════════════════════════════════════════
# 8. ENDPOINTS GET
# ══════════════════════════════════════════════════════════════════════

class TestEndpointsGet:

    def test_get_pack_200(self):
        pid = post_project()["project_id"]
        assert client.get(f"/projects/{pid}/pack").status_code == 200

    def test_get_pack_project_id_coherent(self):
        data = post_project()
        pid = data["project_id"]
        assert client.get(f"/projects/{pid}/pack").json()["project_id"] == pid

    def test_get_pack_404(self):
        assert client.get("/projects/inconnu/pack").status_code == 404

    def test_get_retailers_200(self):
        pid = post_project()["project_id"]
        assert client.get(f"/projects/{pid}/retailers").status_code == 200

    def test_get_retailers_structure(self):
        pid = post_project()["project_id"]
        data = client.get(f"/projects/{pid}/retailers").json()
        for field in ("retailers", "total_amount", "retailer_count"):
            assert field in data

    def test_get_retailers_non_vide(self):
        pid = post_project()["project_id"]
        data = client.get(f"/projects/{pid}/retailers").json()
        assert len(data["retailers"]) > 0

    def test_get_retailers_subtotaux(self):
        pid = post_project()["project_id"]
        data = client.get(f"/projects/{pid}/retailers").json()
        assert sum(r["subtotal"] for r in data["retailers"]) == data["total_amount"]

    def test_get_retailers_room_label(self):
        pid = post_project()["project_id"]
        data = client.get(f"/projects/{pid}/retailers").json()
        for retailer in data["retailers"]:
            for item in retailer["items"]:
                assert item.get("room_label"), f"room_label vide sur '{item.get('name')}'"

    def test_get_retailers_retailer_count(self):
        pid = post_project()["project_id"]
        data = client.get(f"/projects/{pid}/retailers").json()
        assert data["retailer_count"] == len(data["retailers"])

    def test_get_retailers_404(self):
        assert client.get("/projects/inconnu/retailers").status_code == 404

    def test_get_summary_200(self):
        pid = post_project()["project_id"]
        assert client.get(f"/projects/{pid}/summary").status_code == 200

    def test_get_summary_structure(self):
        pid = post_project()["project_id"]
        data = client.get(f"/projects/{pid}/summary").json()
        for field in ("total_amount", "is_lmnp_compliant", "lmnp_checklist", "retailers_summary"):
            assert field in data

    def test_get_summary_404(self):
        assert client.get("/projects/inconnu/summary").status_code == 404

    def test_get_root_200(self):
        pid = post_project()["project_id"]
        assert client.get(f"/projects/{pid}").status_code == 200

    def test_get_root_project_id(self):
        data = post_project()
        pid = data["project_id"]
        assert client.get(f"/projects/{pid}").json()["project_id"] == pid

    def test_get_root_404(self):
        assert client.get("/projects/inconnu").status_code == 404


# ══════════════════════════════════════════════════════════════════════
# 9. FLOW E2E COMPLET
# ══════════════════════════════════════════════════════════════════════

class TestFlowE2E:

    def test_flow_t2_standard(self):
        post_data = post_project()
        pid = post_data["project_id"]
        total = post_data["pack"]["total_price"]

        pack_data = client.get(f"/projects/{pid}/pack").json()
        assert pack_data["pack"]["total_price"] == total

        retailers_data = client.get(f"/projects/{pid}/retailers").json()
        assert retailers_data["total_amount"] == total, (
            f"retailers.total_amount ({retailers_data['total_amount']}) != pack.total_price ({total})"
        )

        summary_data = client.get(f"/projects/{pid}/summary").json()
        assert summary_data["total_amount"] == total
        assert summary_data["is_lmnp_compliant"] is True

    def test_flow_studio_compact(self):
        post_data = post_project({"property_type": "studio", "surface_m2": 18, "rooms_count": 1})
        pid = post_data["project_id"]
        total = post_data["pack"]["total_price"]

        assert client.get(f"/projects/{pid}/retailers").json()["total_amount"] == total
        assert client.get(f"/projects/{pid}/summary").json()["is_lmnp_compliant"] is True

    def test_flow_t3_famille_premium(self):
        post_data = post_project({
            "property_type": "T3", "surface_m2": 80, "rooms_count": 3,
            "tenant_profile": "famille", "budget_level": "premium"
        })
        pid = post_data["project_id"]
        total = post_data["pack"]["total_price"]

        assert client.get(f"/projects/{pid}/pack").json()["pack"]["total_price"] == total
        assert client.get(f"/projects/{pid}/retailers").json()["total_amount"] == total

    def test_deux_projets_independants(self):
        pid1 = post_project()["project_id"]
        pid2 = post_project({"city": "Montpellier", "postal_code": "34000"})["project_id"]
        assert pid1 != pid2

    def test_slug_unique(self):
        slug1 = post_project()["public_slug"]
        slug2 = post_project()["public_slug"]
        assert slug1 != slug2


# ══════════════════════════════════════════════════════════════════════
# 10. VALIDATION PYDANTIC
# ══════════════════════════════════════════════════════════════════════

class TestValidation:

    def _post(self, payload):
        return client.post("/projects", json={"property": payload}).status_code

    def test_payload_vide_422(self):
        assert self._post({}) == 422

    def test_surface_trop_petite_422(self):
        assert self._post({**BASE_PAYLOAD, "surface_m2": 2}) == 422

    def test_budget_inverse_422(self):
        assert self._post({**BASE_PAYLOAD, "budget_min": 8000, "budget_max": 2000}) == 422

    def test_rooms_count_zero_422(self):
        assert self._post({**BASE_PAYLOAD, "rooms_count": 0}) == 422

    def test_rooms_count_trop_grand_422(self):
        assert self._post({**BASE_PAYLOAD, "rooms_count": 20}) == 422

    def test_property_type_manquant_422(self):
        payload = {k: v for k, v in BASE_PAYLOAD.items() if k != "property_type"}
        assert self._post(payload) == 422


# ══════════════════════════════════════════════════════════════════════
# 11. ROBUSTESSE
# ══════════════════════════════════════════════════════════════════════

class TestRobustesse:

    def test_grande_surface_t2(self):
        data = post_project({"surface_m2": 60})
        assert data["pack"]["is_lmnp_compliant"] is True
        assert data["pack"]["total_price"] > 0

    def test_petite_surface_t2(self):
        assert post_project({"surface_m2": 30})["pack"]["total_price"] > 0

    def test_tous_types_bien_valides(self):
        for ptype, rooms in [("studio", 1), ("T2", 2), ("T3", 3)]:
            data = post_project({"property_type": ptype, "rooms_count": rooms})
            assert data["pack"]["is_lmnp_compliant"] is True, f"Type '{ptype}' non conforme LMNP"

    def test_response_json_parseable(self):
        import json
        r = client.post("/projects", json={"property": BASE_PAYLOAD})
        assert r.status_code == 201
        assert isinstance(r.json(), dict)
