"""Price references from old priced files, price-list import, priced templates, approved vendor register,
and technical vs financial evaluation of quotations."""
import pytest
from fastapi.testclient import TestClient

from conftest import SAMPLES
from app.main import app


@pytest.fixture(scope="module")
def c():
    with TestClient(app) as client:
        yield client


def ok(r):
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="module")
def H(c):
    def login(u, p):
        return {"Authorization": "Bearer " + ok(c.post("/api/auth/login", data={"username": u, "password": p}))["access_token"]}
    admin = login("admin", "admin123")
    for u, roles in (("est2", ["estimator"]), ("buy2", ["procurement"]), ("gm2", ["management"])):
        c.post("/api/users", headers=admin, json={"username": u, "password": "pass1234", "roles": roles})
    return {"admin": admin, **{u: login(u, "pass1234") for u in ("est2", "buy2", "gm2")}}


def test_reference_import_and_comparison(c, H):
    with open(SAMPLES / "priced_boq_2024_reference.xlsx", "rb") as f:
        r = ok(c.post("/api/references/import", headers=H["est2"], files={"file": ("old.xlsx", f)},
                      data={"name": "مبنى إداري — الشيخ زايد 2024", "project_type": "building", "outcome": "lost",
                            "reference_date": "2024-06-01", "rate_basis": "final"}))
    assert r["priced"] == 18 and r["tender"]["code"].startswith("REF-2024-")
    refs = ok(c.get("/api/references", headers=H["admin"]))
    assert any(x["reference_import"] and x["items"] == 18 for x in refs)
    hits = ok(c.get("/api/references/search?q=خرسانة مسلحة للأسقف والكمرات&unit=م3", headers=H["admin"]))
    assert hits[0]["final_rate"] == 9400 and hits[0]["date"] == "2024-06-01"
    # estimator cannot see final (selling) reference rates
    assert not ok(c.get("/api/references/search?q=خرسانة مسلحة للأسقف&unit=م3", headers=H["est2"]))

    # a new tender: use a reference rate, then compare the estimate against the reference
    t = ok(c.post("/api/tenders", headers=H["admin"], json={"name": "مبنى جديد", "project_type": "building"}))
    it = ok(c.post(f"/api/tenders/{t['id']}/boq/items", headers=H["admin"], json={"item_ref": "1", "description": "بالمتر المكعب خرسانة مسلحة للأسقف والكمرات", "unit": "م3", "quantity": 100}))
    e = ok(c.post(f"/api/tenders/{t['id']}/estimates", headers=H["admin"], json={}))
    src = ok(c.get(f"/api/estimates/{e['id']}/items/{it['id']}/sources", headers=H["admin"]))
    ref = next(h for h in src["history"] if h["reference_import"])
    ok(c.post(f"/api/estimates/{e['id']}/items/{it['id']}/from-history", headers=H["admin"], json={"history_item_id": ref["item_id"], "score": ref["score"]}))
    lines = ok(c.get(f"/api/estimates/{e['id']}/lines", headers=H["admin"]))
    assert lines[0]["unit_price"] == 9400 and lines[0]["approved"] is False and lines[0]["source"] == "history"
    ok(c.post(f"/api/estimates/{e['id']}/lines/approve", headers=H["admin"], json={}))
    cmp_ = ok(c.get(f"/api/estimates/{e['id']}/reference", headers=H["admin"]))
    row = cmp_["items"][0]
    assert row["references"][0]["tender_code"] == r["tender"]["code"] and row["deviation_pct"] is not None

    # save the item's build-up as a priced template and apply it elsewhere
    tpl = ok(c.post("/api/templates/from-item", headers=H["admin"], json={"estimate_id": e["id"], "item_id": it["id"], "name": "سقف خرساني — مرجعي"}))
    it2 = ok(c.post(f"/api/tenders/{t['id']}/boq/items", headers=H["admin"], json={"item_ref": "2", "description": "سقف", "unit": "م3", "quantity": 10}))
    ok(c.post(f"/api/estimates/{e['id']}/apply-template", headers=H["admin"], json={"template_id": tpl["id"], "item_ids": [it2["id"]]}))
    l2 = [x for x in ok(c.get(f"/api/estimates/{e['id']}/lines", headers=H["admin"])) if x["boq_item_id"] == it2["id"]]
    assert l2[0]["unit_price"] == 9400


def test_price_list_import(c, H):
    with open(SAMPLES / "reference_price_list.xlsx", "rb") as f:
        r = ok(c.post("/api/resources/import", headers=H["est2"], files={"file": ("pl.xlsx", f)}))
    assert r["created"] == 3 and r["updated"] == 2       # M-CON-350 and M-STL already in the library
    res = {x["code"]: x for x in ok(c.get("/api/resources", headers=H["est2"]))}
    assert res["M-STL"]["price"] == 40500 and res["M-STL"]["price_date"] == "2026-10-28"
    assert res["L-ELEC"]["kind"] == "labor" and res["E-CRANE"]["kind"] == "equipment"


def test_vendor_register_and_quote_evaluation(c, H):
    s = ok(c.post("/api/suppliers", headers=H["buy2"], json={"name": "مورد جديد للكهرباء", "kind": "supplier", "trades": ["Electrical"], "project_types": ["building"]}))
    assert s["status"] == "pending" and not s["approval_valid"]
    assert c.post(f"/api/suppliers/{s['id']}/status", headers=H["buy2"], json={"status": "approved"}).status_code == 403
    s = ok(c.post(f"/api/suppliers/{s['id']}/status", headers=H["gm2"], json={"status": "approved", "valid_months": 1}))
    assert s["approval_valid"]
    assert any(a["supplier_id"] == s["id"] for a in ok(c.get("/api/suppliers-alerts?days=40", headers=H["buy2"])))
    ok(c.post(f"/api/suppliers/{s['id']}/documents", headers=H["buy2"], files={"file": ("cr.pdf", b"%PDF-1.4")},
              data={"kind": "commercial_register", "expiry_date": "2026-11-20"}))
    ok(c.post(f"/api/suppliers/{s['id']}/evaluations", headers=H["buy2"], json={"quality": 5, "delivery": 4, "price": 3, "cooperation": 4}))
    s = next(x for x in ok(c.get("/api/suppliers?trade=elec", headers=H["buy2"])) if x["id"] == s["id"])
    assert s["rating"] == 4.0 and s["documents"] == 1
    assert c.post(f"/api/suppliers/{s['id']}/status", headers=H["gm2"], json={"status": "blacklisted"}).status_code == 422  # reason required

    # technical vs financial evaluation in the comparison sheet
    t = ok(c.post("/api/tenders", headers=H["admin"], json={"name": "تقييم عروض", "project_type": "building"}))
    it = ok(c.post(f"/api/tenders/{t['id']}/boq/items", headers=H["admin"], json={"item_ref": "1", "description": "كابلات", "unit": "m", "quantity": 100}))
    pk = ok(c.post(f"/api/tenders/{t['id']}/packages", headers=H["admin"], json={"name": "كهرباء"}))
    ok(c.patch("/api/boq/items", headers=H["admin"], json=[{"id": it["id"], "package_id": pk["id"]}]))
    other = ok(c.post("/api/suppliers", headers=H["buy2"], json={"name": "مورد غير معتمد"}))
    qa = ok(c.post(f"/api/tenders/{t['id']}/quotations", headers=H["buy2"], json={"package_id": pk["id"], "supplier_id": s["id"], "lines": [{"boq_item_id": it["id"], "unit_rate": 100}]}))
    qb = ok(c.post(f"/api/tenders/{t['id']}/quotations", headers=H["buy2"], json={"package_id": pk["id"], "supplier_id": other["id"], "lines": [{"boq_item_id": it["id"], "unit_rate": 80}]}))
    crit = ok(c.get("/api/settings", headers=H["admin"]))["quote_evaluation"]["criteria"]
    ok(c.patch(f"/api/quotations/{qa['id']}", headers=H["buy2"], json={"tech_scores": {k["key"]: 5 for k in crit}}))
    ok(c.patch(f"/api/quotations/{qb['id']}", headers=H["buy2"], json={"tech_scores": {k["key"]: 2 for k in crit}}))
    cmp_ = ok(c.get(f"/api/packages/{pk['id']}/comparison", headers=H["buy2"]))
    ev = {r["quotation_id"]: r for r in cmp_["evaluation"]["rows"]}
    assert ev[qa["id"]]["technical_pct"] == 100 and ev[qb["id"]]["technical_pct"] == 40
    assert ev[qb["id"]]["financial_pct"] == 100 and ev[qa["id"]]["financial_pct"] == 80
    assert ev[qa["id"]]["combined_pct"] == pytest.approx(0.4 * 100 + 0.6 * 80)
    assert not ev[qb["id"]]["passes_technical"]          # below the 60 % technical pass mark → not ranked
    assert cmp_["evaluation"]["recommended"] == qa["id"]  # cheaper quote fails technically
    flags = {q["quotation_id"]: q["flags"] for q in cmp_["quotations"]}
    assert any(f["code"] == "vendor_not_approved" for f in flags[qb["id"]])


def test_cost_index_normalisation_and_offer_letter(c, H):
    ok(c.put("/api/settings/cost_indices", headers=H["admin"], json={"source": "test", "values": {"2024-06": 100, "2026-10": 150}}))
    hits = ok(c.get("/api/references/search?q=خرسانة مسلحة للأسقف والكمرات&unit=م3", headers=H["admin"]))
    ref = next(h for h in hits if h["tender_code"].startswith("REF-2024"))
    assert ref["index_factor"] == 1.5 and ref["adj_final_rate"] == 9400 * 1.5
    t = ok(c.post("/api/tenders", headers=H["admin"], json={"name": "عرض مالي", "project_type": "building", "owner": "شركة س", "duration_months": 10}))
    it = ok(c.post(f"/api/tenders/{t['id']}/boq/items", headers=H["admin"], json={"item_ref": "1", "description": "بالمتر المكعب خرسانة مسلحة للأسقف والكمرات", "unit": "م3", "quantity": 10}))
    e = ok(c.post(f"/api/tenders/{t['id']}/estimates", headers=H["admin"], json={}))
    ok(c.put(f"/api/estimates/{e['id']}/items/{it['id']}/lines", headers=H["admin"], json=[{"kind": "subcontract", "coefficient": 1, "unit_price": 12000}]))
    cmp_ = ok(c.get(f"/api/estimates/{e['id']}/reference", headers=H["admin"]))
    assert cmp_["items"][0]["flag"] in ("green", "amber", "red")
    ok(c.patch(f"/api/estimates/{e['id']}", headers=H["admin"], json={"params": {"material_escalation_pct": 10, "price_adjustment": {"enabled": True, "components": [{"name": "حديد", "weight": 50, "expected_change_pct": 10}]}}}))
    s = ok(c.get(f"/api/estimates/{e['id']}/calc", headers=H["admin"]))["summary"]
    assert s["escalation_recovery_pct"] == 5 and s["escalation_carried_pct"] == 5
    letter = ok(c.post(f"/api/estimates/{e['id']}/offer-letter", headers=H["admin"], json={"clarifications": [0, 2], "extra": ["تحفظ خاص"]}))
    assert "شركة س" in letter["text"] and "3) تحفظ خاص" in letter["text"] and "الإجمالي شامل الضريبة" in letter["text"]
    assert "الإجمالي" not in ok(c.post(f"/api/estimates/{e['id']}/offer-letter", headers=H["est2"], json={}))["text"]
