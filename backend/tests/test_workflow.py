"""End-to-end: one tender through the 20-step cycle, via the HTTP API, with role permissions."""
import io
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook

from conftest import SAMPLES
from app.main import app


@pytest.fixture(scope="module")
def c():
    with TestClient(app) as client:
        yield client


def login(c, user, pw):
    r = c.post("/api/auth/login", data={"username": user, "password": pw})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="module")
def H(c):
    admin = login(c, "admin", "admin123")
    for u, roles in (("estimator", ["estimator"]), ("buyer", ["procurement", "estimator"]), ("gm", ["management"]),
                     ("tm", ["tender_manager"])):
        r = c.post("/api/users", headers=admin, json={"username": u, "password": "pass1234", "full_name": u, "roles": roles})
        assert r.status_code == 200, r.text
    return {"admin": admin, **{u: login(c, u, "pass1234") for u in ("estimator", "buyer", "gm", "tm")}}


def ok(r):
    assert r.status_code == 200, r.text
    return r.json()


def test_full_cycle(c, H):
    # ---- step 1: intake
    t = ok(c.post("/api/tenders", headers=H["tm"], json={"name": "مبنى إداري التجمع الخامس", "project_type": "building",
                                                        "owner": "", "bid_bond_amount": 500000}))
    tid = t["id"]
    assert t["code"].startswith("TND-")
    assert len(t["submission_checklist"]) >= 5
    # estimator cannot register tenders
    assert c.post("/api/tenders", headers=H["estimator"], json={"name": "x"}).status_code == 403

    # ---- step 2: go / no-go (management only, reason required)
    assert c.post(f"/api/tenders/{tid}/gonogo", headers=H["tm"], json={"scores": {}, "reason": "x"}).status_code == 403
    assert c.post(f"/api/tenders/{tid}/gonogo", headers=H["gm"], json={"scores": {"experience": 5}}).status_code == 422
    g = ok(c.post(f"/api/tenders/{tid}/gonogo", headers=H["gm"], json={
        "scores": {"experience": 5, "capacity": 4, "owner_payment": 4, "competition": 3, "risk": 3, "time": 4},
        "reason": "نوع مشروع نعرفه ومالك ملتزم"}))
    assert g["gonogo"]["decision"] == "go" and g["status"] == "study"

    # ---- steps 3–5: documents, AI analysis, accept suggestions
    with open(SAMPLES / "particular_conditions_ar.docx", "rb") as f:
        d = ok(c.post(f"/api/tenders/{tid}/documents", headers=H["tm"], files={"file": ("particular_conditions_ar.docx", f)},
                      data={"doc_type": "particular_conditions"}))
    assert d["text_status"] == "extracted"
    a = ok(c.post(f"/api/tenders/{tid}/analyze", headers=H["tm"], json={}))
    assert a["engine"] == "offline-rules" and a["created"] > 10
    sugg = ok(c.get(f"/api/tenders/{tid}/suggestions", headers=H["tm"]))
    assert all(s["source"]["file"] and s["source"]["page"] for s in sugg)  # every suggestion cites file + page
    for s in sugg:
        action = "reject" if s["kind"] == "risk" and s["payload"]["category"] == "fx" else "accept"
        ok(c.post(f"/api/suggestions/{s['id']}/decide", headers=H["tm"], json={"action": action}))
    t = ok(c.get(f"/api/tenders/{tid}", headers=H["tm"]))
    assert t["submission_date"] == "2026-12-10" and t["site_visit_date"] == "2026-11-18" and t["rfi_deadline"] == "2026-11-25"
    assert t["duration_months"] == 14 and t["bid_validity_days"] == 90
    assert t["summary"]["retention"]["numeric"] == 5 and t["summary"]["retention"]["page"] == 1
    assert len(ok(c.get(f"/api/tenders/{tid}/risks", headers=H["tm"]))) >= 3
    assert "يرجى التوضيح" in ok(c.get(f"/api/tenders/{tid}/rfis/letter", headers=H["tm"]))["text"]
    dash = ok(c.get("/api/dashboard", headers=H["tm"]))
    assert dash["ai_acceptance_rate"] is not None and dash["ai_acceptance_rate"] < 100

    # ---- step 6: site visit checklist by project type
    sv = ok(c.get(f"/api/tenders/{tid}/site-visit", headers=H["tm"]))
    assert {x["key"] for x in sv["checklist"]} >= {"soil", "owner_rules", "existing_mep"}
    sv["checklist"][0].update(status="issue", notes="مياه جوفية على عمق 2 م")
    out = ok(c.put(f"/api/tenders/{tid}/site-visit", headers=H["tm"], json=sv))
    assert any(s["type"] == "risk" for s in out["suggestions"])

    # ---- steps 7–8: BOQ import, cost coding, scope detection, packages
    with open(SAMPLES / "owner_boq_building_ar.xlsx", "rb") as f:
        pv = ok(c.post(f"/api/tenders/{tid}/boq/preview", headers=H["estimator"], files={"file": ("boq.xlsx", f)}))
    assert pv["items"] == 18
    ok(c.post(f"/api/tenders/{tid}/boq/import", headers=H["estimator"], json={"document_id": pv["document_id"]}))
    ok(c.post(f"/api/tenders/{tid}/boq/accept-cost-codes", headers=H["estimator"], json={}))
    boq = ok(c.get(f"/api/tenders/{tid}/boq", headers=H["estimator"]))
    items = {b["item_ref"]: b for b in boq if not b["is_section"]}
    assert items["2/2"]["row_index"] == 11 and "الشدات" in items["2/2"]["description"]
    assert items["4/5"]["scope"] == "apply"           # "تركيب فقط"
    assert items["3/3"]["scope"] == "supply_apply"    # "توريد وتركيب"
    assert items["5/2"]["is_provisional"]
    assert items["2/4"]["cost_code"].startswith("B03.04")
    assert items["4/2"]["cost_code"].startswith("B09")
    ok(c.post(f"/api/tenders/{tid}/packages/auto", headers=H["estimator"]))
    pk = {p["trade"]: p for p in ok(c.get(f"/api/tenders/{tid}/packages", headers=H["estimator"]))}
    assert pk["B03"]["execution"] == "self" and pk["B09"]["execution"] == "subcontract"
    ok(c.patch("/api/boq/items", headers=H["estimator"], json=[{"id": items["5/2"]["id"], "provisional_amount": 750000},
                                                               {"id": items["2/4"]["id"], "checked_quantity": 820}]))

    # ---- step 10: estimate V1, build-up from templates + manual lines
    est = ok(c.post(f"/api/tenders/{tid}/estimates", headers=H["estimator"], json={}))
    eid = est["id"]
    assert est["params"]["retention_pct"] == 5 and est["params"]["advance_payment_pct"] == 10  # pre-filled from summary
    assert "markup_pct" not in est["params"]  # hidden from the estimator
    tpls = {x["name"]: x for x in ok(c.get("/api/templates", headers=H["estimator"]))}
    def tpl(name, refs):
        ok(c.post(f"/api/estimates/{eid}/apply-template", headers=H["estimator"],
                  json={"template_id": tpls[name]["id"], "item_ids": [items[r]["id"] for r in refs]}))
    tpl("حفر بالمعدات (م3)", ["1/1"]); tpl("ردم رمل (م3)", ["1/2"]); tpl("خرسانة عادية (م3)", ["2/1"])
    tpl("خرسانة مسلحة قواعد (م3)", ["2/2", "2/3"]); tpl("خرسانة مسلحة أسقف (م3)", ["2/4"])
    tpl("مباني طوب 25 سم (م2)", ["3/1"]); tpl("بياض داخلي (م2)", ["3/2"])
    manual = {"3/4": 95, "3/5": 480, "4/1": 210, "4/3": 520, "4/4": 18000, "4/5": 150, "5/1": 9500}
    for ref, price in manual.items():
        ok(c.put(f"/api/estimates/{eid}/items/{items[ref]['id']}/lines", headers=H["estimator"],
                 json=[{"kind": "subcontract", "part": items[ref]["scope"], "coefficient": 1, "unit_price": price, "source": "manual"}]))

    # ---- step 9: RFQ round-trip for HVAC; Supply & Apply split for imported porcelain
    sup = {s["name"]: s["id"] for s in ok(c.get("/api/suppliers", headers=H["buyer"]))}
    rfq = c.get(f"/api/packages/{pk['B09']['id']}/rfq.xlsx", headers=H["buyer"])
    assert rfq.status_code == 200
    def fill(rate, lead, supplier):
        wb = load_workbook(io.BytesIO(rfq.content))
        ws = wb.active
        ws["B4"], ws["B7"] = supplier, lead
        for r in range(1, ws.max_row + 1):
            if isinstance(ws.cell(r, 1).value, int):
                ws.cell(r, 6).value = rate
        buf = io.BytesIO(); wb.save(buf); return buf.getvalue()
    q1 = ok(c.post(f"/api/packages/{pk['B09']['id']}/quotations/upload", headers=H["buyer"],
                   files={"file": ("q1.xlsx", fill(52000, 45, "الشركة المتحدة للتكييف"))}))
    q2 = ok(c.post(f"/api/packages/{pk['B09']['id']}/quotations/upload", headers=H["buyer"],
                   files={"file": ("q2.xlsx", fill(47000, 120, "مورد تكييف جديد"))}))
    assert q1["lines"][0]["unit_rate"] == 52000 and q2["supplier"] == "مورد تكييف جديد"
    ok(c.patch(f"/api/quotations/{q2['id']}", headers=H["buyer"], json={"includes_vat": True}))  # levelled by removing VAT
    ok(c.patch(f"/api/packages/{pk['B09']['id']}", headers=H["buyer"], json={"required_on_site_month": 3}))
    cmp_ = ok(c.get(f"/api/packages/{pk['B09']['id']}/comparison?estimate_id={eid}", headers=H["buyer"]))
    cols = {x["quotation_id"]: x for x in cmp_["quotations"]}
    assert abs(cols[q2["id"]]["total_base"] - 47000 / 1.14 * 48) < 0.01
    assert cmp_["lowest_complete"] == q2["id"]
    assert any(f["code"] == "lead_time" for f in cols[q2["id"]]["flags"])  # 120 days > month 3
    ok(c.post(f"/api/packages/{pk['B09']['id']}/select", headers=H["buyer"], json={"quotation_id": q1["id"], "estimate_id": eid}))

    por = items["3/3"]["id"]
    fin_pkg = pk[items["3/3"]["cost_code"][:3]]["id"]
    qs = ok(c.post(f"/api/tenders/{tid}/quotations", headers=H["buyer"], json={
        "package_id": fin_pkg, "supplier_id": sup["سيراميكا الشرق"], "scope": "supply", "currency": "USD", "lead_time_days": 60,
        "lines": [{"boq_item_id": por, "unit_rate": 15}]}))
    qa = ok(c.post(f"/api/tenders/{tid}/quotations", headers=H["buyer"], json={
        "package_id": fin_pkg, "supplier_id": sup["فريق التشطيبات الحديثة"], "scope": "apply", "currency": "EGP",
        "lines": [{"boq_item_id": por, "unit_rate": 180}]}))
    ok(c.post(f"/api/packages/{fin_pkg}/select", headers=H["buyer"], json={"quotation_id": qs["id"], "estimate_id": eid, "item_ids": [por]}))
    ok(c.post(f"/api/packages/{fin_pkg}/select", headers=H["buyer"], json={"quotation_id": qa["id"], "estimate_id": eid, "item_ids": [por]}))
    an = ok(c.get(f"/api/estimates/{eid}/analysis?scope=supply", headers=H["estimator"]))
    por_row = next(x for x in an["items"] if x["id"] == por)
    assert por_row["subtotals"]["supply"] == 15 * 48.5 and all(l["part"] == "supply" for l in por_row["lines"])
    full = ok(c.get(f"/api/estimates/{eid}/analysis", headers=H["estimator"]))
    por_full = next(x for x in full["items"] if x["id"] == por)
    assert por_full["subtotals"] == {"supply": 15 * 48.5, "apply": 180, "supply_apply": 0}

    # ---- steps 11–14: schedule, overheads, risk values, FX buffer for imported items
    ok(c.put(f"/api/tenders/{tid}/schedule", headers=H["admin"], json={"duration_months": 14, "phases": [
        {"name": "هيكل خرساني", "start_month": 1, "duration_months": 6, "weight_pct": 45},
        {"name": "تشطيبات و MEP", "start_month": 5, "duration_months": 9, "weight_pct": 50},
        {"name": "فرش وتسليم", "start_month": 13, "duration_months": 2, "weight_pct": 5}]}))
    risks = ok(c.get(f"/api/tenders/{tid}/risks", headers=H["estimator"]))
    ok(c.patch(f"/api/risks/{risks[0]['id']}", headers=H["estimator"], json={"impact_amount": 400000, "probability_pct": 25}))
    ok(c.patch(f"/api/estimates/{eid}", headers=H["estimator"], json={"params": {"fx_buffer_pct": 8}}))
    # the estimator may not set markup
    assert c.patch(f"/api/estimates/{eid}", headers=H["estimator"], json={"params": {"markup_pct": 30}}).status_code == 403

    # ---- steps 15–16: markup what-if & spreading (management)
    wi = ok(c.post(f"/api/estimates/{eid}/whatif", headers=H["gm"], json={"markups": [5, 10, 15]}))
    assert wi[0]["price"] < wi[1]["price"] < wi[2]["price"]
    assert c.post(f"/api/estimates/{eid}/whatif", headers=H["estimator"], json={}).status_code == 403
    ok(c.patch(f"/api/estimates/{eid}", headers=H["gm"], json={"params": {"markup_pct": 12, "spread_overrides": {str(items["1/1"]["id"]): {"factor": 1.4}}}}))
    calc = ok(c.get(f"/api/estimates/{eid}/calc", headers=H["gm"]))
    s = calc["summary"]
    assert s["direct_by_part"]["supply"] > 0 and s["direct_by_part"]["apply"] > 0
    assert s["escalation_fx"] == pytest.approx(0.08 * 2400 * 15 * 48.5)
    assert s["finance"] > 0 and abs(s["rounding_diff"]) < 50
    redacted = ok(c.get(f"/api/estimates/{eid}/calc", headers=H["estimator"]))
    assert redacted.get("redacted") and "profit" not in redacted["summary"] and "final_rate" not in redacted["items"][0]

    # ---- step 17: checks, submit, approve (management) — lock
    chk = ok(c.get(f"/api/estimates/{eid}/checks", headers=H["estimator"]))
    assert not [x for x in chk if x["severity"] == "error"], chk
    assert any(x["code"] == "qty_diff" for x in chk)
    ok(c.post(f"/api/estimates/{eid}/submit", headers=H["estimator"]))
    assert c.post(f"/api/estimates/{eid}/approve", headers=H["estimator"]).status_code == 403
    ok(c.post(f"/api/estimates/{eid}/approve", headers=H["gm"]))
    assert c.put(f"/api/estimates/{eid}/items/{por}/lines", headers=H["estimator"], json=[]).status_code == 409  # locked

    # ---- step 18: priced BOQ in the owner's own workbook
    assert c.get(f"/api/estimates/{eid}/export/owner.xlsx", headers=H["estimator"]).status_code == 403
    ex = c.get(f"/api/estimates/{eid}/export/owner.xlsx", headers=H["admin"])
    assert ex.status_code == 200
    wb = load_workbook(io.BytesIO(ex.content))
    ws = wb["المقايسة"]
    assert "A1:F1" in [str(r) for r in ws.merged_cells.ranges]          # owner layout preserved
    assert ws["F6"].value == "=D6*E6"                                     # owner formulas kept
    final = {r["id"]: r for r in calc["items"]}
    assert ws["E13"].value == final[items["2/4"]["id"]]["final_rate"]
    total = sum(Decimal(str(ws.cell(r, 4).value)) * Decimal(str(ws.cell(r, 5).value or 0))
                for r in range(5, 30) if isinstance(ws.cell(r, 4).value, (int, float)))
    assert abs(float(total) - calc["summary"]["submitted_total"]) < 0.5   # reconciles with the engine
    assert c.get(f"/api/estimates/{eid}/export/internal.xlsx", headers=H["estimator"]).status_code == 200

    # ---- versions: clone, change markup, compare
    v2 = ok(c.post(f"/api/tenders/{tid}/estimates", headers=H["estimator"], json={"clone_from": eid}))
    ok(c.patch(f"/api/estimates/{v2['id']}", headers=H["gm"], json={"params": {"markup_pct": 8}}))
    cmpv = ok(c.get(f"/api/estimates/compare/{eid}/{v2['id']}", headers=H["gm"]))
    assert cmpv["summary"]["submitted_total"]["b"] < cmpv["summary"]["submitted_total"]["a"]
    assert cmpv["a"]["fx"] == cmpv["b"]["fx"]

    # ---- steps 19–20: submission, result, baseline, knowledge base
    t = ok(c.get(f"/api/tenders/{tid}", headers=H["tm"]))
    assert c.put(f"/api/tenders/{tid}/submission", headers=H["tm"], json={"mark_submitted": True}).status_code == 409
    ok(c.put(f"/api/tenders/{tid}/submission", headers=H["tm"], json={"checklist": [{**x, "done": True} for x in t["submission_checklist"]], "mark_submitted": True}))
    ok(c.put(f"/api/tenders/{tid}/result", headers=H["tm"], json={"outcome": "won", "our_price": s["submitted_total"],
                                                                 "reasons": "أقل سعر فني مقبول", "lessons": "عروض التكييف حسمت السعر",
                                                                 "competitors": [{"name": "منافس أ", "price": s["submitted_total"] * 1.06}]}))
    res = ok(c.get(f"/api/tenders/{tid}/result", headers=H["gm"]))
    assert res["competitors"][0]["diff_pct"] < 0
    bl = c.get(f"/api/estimates/{eid}/export/baseline.xlsx", headers=H["gm"])
    assert bl.status_code == 200
    kp = ok(c.get("/api/kpis", headers=H["gm"]))
    assert kp["by_type"]["building"]["won"] >= 1 and any(x["code"] == t["code"] and x["status"] == "won" for x in kp["tenders"])

    # a new tender now gets history-based price suggestions and outlier checks
    t2 = ok(c.post("/api/tenders", headers=H["tm"], json={"name": "مبنى إداري 2", "project_type": "building"}))
    it = ok(c.post(f"/api/tenders/{t2['id']}/boq/items", headers=H["estimator"], json={
        "item_ref": "1", "description": "بالمتر المكعب خرسانة مسلحة للأسقف والكمرات", "unit": "م3", "quantity": 500}))
    e2 = ok(c.post(f"/api/tenders/{t2['id']}/estimates", headers=H["estimator"], json={}))
    src = ok(c.get(f"/api/estimates/{e2['id']}/items/{it['id']}/sources", headers=H["estimator"]))
    mine = next(h for h in src["history"] if h["tender_code"] == t["code"])
    ok(c.post(f"/api/estimates/{e2['id']}/items/{it['id']}/from-history", headers=H["estimator"],
              json={"history_item_id": mine["item_id"], "score": mine["score"]}))
    chk2 = ok(c.get(f"/api/estimates/{e2['id']}/checks", headers=H["estimator"]))
    assert any(x["code"] == "ai_unapproved" for x in chk2)       # AI/history suggestion blocks until approved
    ok(c.post(f"/api/estimates/{e2['id']}/lines/approve", headers=H["estimator"], json={}))
    chk2 = ok(c.get(f"/api/estimates/{e2['id']}/checks", headers=H["estimator"]))
    assert not any(x["code"] == "ai_unapproved" for x in chk2)

    # ---- audit trail
    log = ok(c.get(f"/api/audit?tender_id={tid}", headers=H["gm"]))
    assert any(e["entity"] == "estimates" and e["action"] == "update" and "status" in e["changes"] for e in log)
    assert any(e["user"] == "gm" for e in log)


def test_infra_boq_and_no_go(c, H):
    t = ok(c.post("/api/tenders", headers=H["tm"], json={"name": "بنية تحتية الحي السادس", "project_type": "infra"}))
    with open(SAMPLES / "owner_boq_infra_en.xlsx", "rb") as f:
        pv = ok(c.post(f"/api/tenders/{t['id']}/boq/preview", headers=H["estimator"], files={"file": ("infra.xlsx", f)}))
    assert set(pv["mapping"]) == {"Bill 1 - Roads", "Bill 2 - Networks"}
    ok(c.post(f"/api/tenders/{t['id']}/boq/import", headers=H["estimator"], json={"document_id": pv["document_id"]}))
    ok(c.post(f"/api/tenders/{t['id']}/boq/accept-cost-codes", headers=H["estimator"], json={}))
    items = {b["item_ref"]: b for b in ok(c.get(f"/api/tenders/{t['id']}/boq", headers=H["estimator"])) if not b["is_section"]}
    assert items["A.5"]["cost_code"].startswith("I02.03")   # asphalt
    assert items["B.1"]["cost_code"].startswith("I03.01")   # HDPE water
    assert items["B.4"]["cost_code"].startswith("I04.02")   # manholes
    assert items["C.1"]["cost_code"].startswith("I05.03")   # street lighting
    assert items["C.4"]["is_provisional"]
    sv = ok(c.get(f"/api/tenders/{t['id']}/site-visit", headers=H["tm"]))
    assert {x["key"] for x in sv["checklist"]} >= {"traffic", "existing_utilities"}
    g = ok(c.post(f"/api/tenders/{t['id']}/gonogo", headers=H["gm"], json={"scores": {"experience": 1, "capacity": 2}, "reason": "طاقة غير متاحة"}))
    assert g["status"] == "declined" and "نعتذر" in g["gonogo"]["apology_letter"]
