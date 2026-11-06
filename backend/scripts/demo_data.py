"""Load demo data through the real API (same code path as the UI):
team users, one awarded historical tender, one active integrated-building tender mid-pricing,
and one infrastructure tender at the study stage.
    cd backend && python scripts/demo_data.py
"""
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient  # noqa: E402
from openpyxl import load_workbook  # noqa: E402

from app.main import app  # noqa: E402

SAMPLES = Path(__file__).resolve().parents[2] / "samples"


def ok(r):
    if r.status_code != 200:
        raise SystemExit(f"{r.request.method} {r.request.url} → {r.status_code}: {r.text}")
    return r.json()


def main():
    with TestClient(app) as c:
        def login(u, p):
            return {"Authorization": "Bearer " + ok(c.post("/api/auth/login", data={"username": u, "password": p}))["access_token"]}
        A = login("admin", "admin123")
        if ok(c.get("/api/tenders", headers=A)):
            print("Demo data already present — skipping")
            return
        team = [("manager", "م. أحمد سالم — مدير العطاءات", ["tender_manager"]),
                ("estimator", "م. منى فؤاد — مُسعِّر", ["estimator", "planner"]),
                ("buyer", "م. كريم عادل — مشتريات", ["procurement"]),
                ("techoffice", "م. سارة حسن — مكتب فني", ["technical_office"]),
                ("gm", "م. هشام رضا — المدير العام", ["management"])]
        for u, name, roles in team:
            ok(c.post("/api/users", headers=A, json={"username": u, "password": "demo1234", "full_name": name, "roles": roles}))
        H = {u: login(u, "demo1234") for u, _, _ in team}

        def price_building(tid, eid, items, factor=1.0):
            tpls = {x["name"]: x["id"] for x in ok(c.get("/api/templates", headers=H["estimator"]))}
            for name, refs in [("حفر بالمعدات (م3)", ["1/1"]), ("ردم رمل (م3)", ["1/2"]), ("خرسانة عادية (م3)", ["2/1"]),
                               ("خرسانة مسلحة قواعد (م3)", ["2/2", "2/3"]), ("خرسانة مسلحة أسقف (م3)", ["2/4"]),
                               ("مباني طوب 25 سم (م2)", ["3/1"]), ("بياض داخلي (م2)", ["3/2"])]:
                ok(c.post(f"/api/estimates/{eid}/apply-template", headers=H["estimator"], json={"template_id": tpls[name], "item_ids": [items[r]["id"] for r in refs]}))
            for ref, price in {"3/4": 95, "3/5": 480, "4/1": 210, "4/3": 520, "4/4": 18000, "4/5": 150, "5/1": 9500, "3/3": 1050, "4/2": 52000}.items():
                ok(c.put(f"/api/estimates/{eid}/items/{items[ref]['id']}/lines", headers=H["estimator"],
                         json=[{"kind": "subcontract", "part": items[ref]["scope"], "coefficient": 1, "unit_price": round(price * factor, 2), "source": "manual"}]))

        def import_boq(tid, file):
            with open(SAMPLES / file, "rb") as f:
                pv = ok(c.post(f"/api/tenders/{tid}/boq/preview", headers=H["estimator"], files={"file": (file, f)}))
            ok(c.post(f"/api/tenders/{tid}/boq/import", headers=H["estimator"], json={"document_id": pv["document_id"]}))
            ok(c.post(f"/api/tenders/{tid}/boq/accept-cost-codes", headers=H["estimator"], json={}))
            ok(c.post(f"/api/tenders/{tid}/packages/auto", headers=H["estimator"]))
            return {b["item_ref"]: b for b in ok(c.get(f"/api/tenders/{tid}/boq", headers=H["estimator"])) if not b["is_section"]}

        # ---- 1. historical awarded tender (feeds history suggestions & KPIs)
        h = ok(c.post("/api/tenders", headers=H["manager"], json={"name": "مبنى إداري — المعادي (2025)", "project_type": "building",
                                                                 "owner": "شركة الأفق للاستثمار", "duration_months": 12, "location": "المعادي"}))
        ok(c.post(f"/api/tenders/{h['id']}/gonogo", headers=H["gm"], json={"scores": {k: 4 for k in ["experience", "capacity", "owner_payment", "competition", "risk", "time"]}, "reason": "مشروع مشابه لخبرتنا"}))
        items = import_boq(h["id"], "owner_boq_building_ar.xlsx")
        ok(c.patch("/api/boq/items", headers=H["estimator"], json=[{"id": items["5/2"]["id"], "provisional_amount": 600000}]))
        e = ok(c.post(f"/api/tenders/{h['id']}/estimates", headers=H["estimator"], json={}))
        price_building(h["id"], e["id"], items, factor=0.92)
        ok(c.patch(f"/api/estimates/{e['id']}", headers=H["gm"], json={"params": {"markup_pct": 11}}))
        ok(c.post(f"/api/estimates/{e['id']}/submit", headers=H["estimator"]))
        ok(c.post(f"/api/estimates/{e['id']}/approve", headers=H["gm"]))
        tot = ok(c.get(f"/api/estimates/{e['id']}/calc", headers=H["gm"]))["summary"]["submitted_total"]
        t = ok(c.get(f"/api/tenders/{h['id']}", headers=H["manager"]))
        ok(c.put(f"/api/tenders/{h['id']}/submission", headers=H["manager"], json={"checklist": [{**x, "done": True} for x in t["submission_checklist"]], "mark_submitted": True}))
        ok(c.put(f"/api/tenders/{h['id']}/result", headers=H["manager"], json={
            "outcome": "won", "our_price": tot, "winner": "نحن", "reasons": "أقل سعر مع عرض فني قوي", "lessons": "أسعار التكييف حسمت الفارق",
            "competitors": [{"name": "شركة البناء الحديث", "price": round(tot * 1.04)}, {"name": "المقاولون المتحدون", "price": round(tot * 1.09)}]}))

        # ---- 2. active integrated-building tender, mid-pricing
        t = ok(c.post("/api/tenders", headers=H["manager"], json={"name": "مبنى إداري — التجمع الخامس", "project_type": "building",
                                                                 "location": "القاهرة الجديدة", "bid_bond_amount": 500000}))
        tid = t["id"]
        ok(c.post(f"/api/tenders/{tid}/gonogo", headers=H["gm"], json={"scores": {"experience": 5, "capacity": 4, "owner_payment": 4, "competition": 3, "risk": 3, "time": 3},
                                                                       "reason": "نوع مشروع نعرفه جيدًا ومالك ملتزم بالصرف"}))
        with open(SAMPLES / "particular_conditions_ar.docx", "rb") as f:
            ok(c.post(f"/api/tenders/{tid}/documents", headers=H["manager"], files={"file": ("الشروط_الخاصة.docx", f)}, data={"doc_type": "particular_conditions"}))
        ok(c.post(f"/api/tenders/{tid}/analyze", headers=H["manager"], json={}))
        for s in ok(c.get(f"/api/tenders/{tid}/suggestions", headers=H["manager"])):
            if s["kind"] == "summary_field" or (s["kind"] == "risk" and s["payload"]["category"] in ("financial", "schedule")):
                ok(c.post(f"/api/suggestions/{s['id']}/decide", headers=H["manager"], json={"action": "accept"}))
        ok(c.post(f"/api/tenders/{tid}/tasks", headers=H["manager"], json={"title": "مراجعة كميات الخرسانة على اللوحات", "step": 7, "assignee_id": 3, "due_date": "2026-11-20"}))
        ok(c.post(f"/api/tenders/{tid}/tasks", headers=H["manager"], json={"title": "طلب عروض التكييف والكهرباء", "step": 9, "assignee_id": 4, "due_date": "2026-11-22"}))
        items = import_boq(tid, "owner_boq_building_ar.xlsx")
        ok(c.patch("/api/boq/items", headers=H["estimator"], json=[{"id": items["5/2"]["id"], "provisional_amount": 750000}]))
        e = ok(c.post(f"/api/tenders/{tid}/estimates", headers=H["estimator"], json={}))
        price_building(tid, e["id"], items)
        pk = {p["trade"]: p for p in ok(c.get(f"/api/tenders/{tid}/packages", headers=H["buyer"]))}
        rfq = c.get(f"/api/packages/{pk['B09']['id']}/rfq.xlsx", headers=H["buyer"]).content
        for sup, rate, lead in (("الشركة المتحدة للتكييف", 52000, 45), ("مورد تكييف — النيل", 49500, 110)):
            wb = load_workbook(io.BytesIO(rfq)); ws = wb.active
            ws["B4"], ws["B5"], ws["B7"], ws["B8"] = sup, "EGP", lead, "30% مقدم والباقي على الاستلام"
            for r in range(1, ws.max_row + 1):
                if isinstance(ws.cell(r, 1).value, int):
                    ws.cell(r, 6).value = rate
            buf = io.BytesIO(); wb.save(buf)
            ok(c.post(f"/api/packages/{pk['B09']['id']}/quotations/upload", headers=H["buyer"], files={"file": (f"{sup}.xlsx", buf.getvalue())}))
        ok(c.patch(f"/api/packages/{pk['B09']['id']}", headers=H["buyer"], json={"required_on_site_month": 3}))
        qs = ok(c.get(f"/api/tenders/{tid}/quotations?package_id={pk['B09']['id']}", headers=H["buyer"]))
        ok(c.post(f"/api/packages/{pk['B09']['id']}/select", headers=H["buyer"], json={"quotation_id": qs[0]["id"], "estimate_id": e["id"]}))
        sup = {s["name"]: s["id"] for s in ok(c.get("/api/suppliers", headers=H["buyer"]))}
        fin = pk[items["3/3"]["cost_code"][:3]]["id"]
        q1 = ok(c.post(f"/api/tenders/{tid}/quotations", headers=H["buyer"], json={"package_id": fin, "supplier_id": sup["سيراميكا الشرق"], "scope": "supply", "currency": "USD", "lead_time_days": 60,
                                                                                 "reference": "Q-1182", "lines": [{"boq_item_id": items["3/3"]["id"], "unit_rate": 15}]}))
        q2 = ok(c.post(f"/api/tenders/{tid}/quotations", headers=H["buyer"], json={"package_id": fin, "supplier_id": sup["فريق التشطيبات الحديثة"], "scope": "apply", "currency": "EGP",
                                                                                 "reference": "T-77", "lines": [{"boq_item_id": items["3/3"]["id"], "unit_rate": 180}]}))
        for q in (q1, q2):
            ok(c.post(f"/api/packages/{fin}/select", headers=H["buyer"], json={"quotation_id": q["id"], "estimate_id": e["id"], "item_ids": [items["3/3"]["id"]]}))
        ok(c.put(f"/api/tenders/{tid}/schedule", headers=H["estimator"], json={"duration_months": 14, "phases": [
            {"name": "حفر وهيكل خرساني", "start_month": 1, "duration_months": 6, "weight_pct": 45},
            {"name": "تشطيبات وأعمال كهروميكانيكية", "start_month": 5, "duration_months": 9, "weight_pct": 50},
            {"name": "فرش وتسليم", "start_month": 13, "duration_months": 2, "weight_pct": 5}]}))
        risks = ok(c.get(f"/api/tenders/{tid}/risks", headers=H["estimator"]))
        for r, imp in zip(risks, (900000, 400000, 250000)):
            ok(c.patch(f"/api/risks/{r['id']}", headers=H["estimator"], json={"impact_amount": imp}))
        ok(c.patch(f"/api/estimates/{e['id']}", headers=H["estimator"], json={"params": {"fx_buffer_pct": 8}}))
        ok(c.patch(f"/api/estimates/{e['id']}", headers=H["gm"], json={"params": {"markup_pct": 12}}))
        ok(c.post(f"/api/tenders/{tid}/ve", headers=H["estimator"], json={"boq_item_id": items["3/3"]["id"], "description": "بورسلين محلي درجة أولى بدل المستورد", "alternative_rate": 950, "lead_time_days": 14}))

        # ---- price references, price list, cost index (illustrative values — replace with the CAPMAS bulletin)
        with open(SAMPLES / "priced_boq_2024_reference.xlsx", "rb") as f:
            ok(c.post("/api/references/import", headers=H["estimator"], files={"file": ("الشيخ_زايد_2024.xlsx", f)},
                      data={"name": "مبنى إداري — الشيخ زايد (2024)", "project_type": "building", "outcome": "lost", "reference_date": "2024-06-01", "rate_basis": "final"}))
        with open(SAMPLES / "reference_price_list.xlsx", "rb") as f:
            ok(c.post("/api/resources/import", headers=H["estimator"], files={"file": ("قائمة_أسعار_أكتوبر_2026.xlsx", f)}))
        ok(c.put("/api/settings/cost_indices", headers=A, json={"source": "قيم توضيحية للتجربة — استبدلها بنشرة الجهاز المركزي للتعبئة العامة والإحصاء",
                                                              "values": {"2024-06": 100, "2025-01": 112, "2025-06": 121, "2026-01": 133, "2026-10": 142}}))
        crit = ok(c.get("/api/settings", headers=A))["quote_evaluation"]["criteria"]
        for q, sc in zip(qs, ({"spec_compliance": 5, "approved_brand": 5, "experience": 4, "lead_time": 4, "payment_terms": 4, "scope_completeness": 4, "warranty": 4},
                              {"spec_compliance": 3, "approved_brand": 2, "experience": 3, "lead_time": 2, "payment_terms": 3, "scope_completeness": 3, "warranty": 3})):
            ok(c.patch(f"/api/quotations/{q['id']}", headers=H["buyer"], json={"tech_scores": {k["key"]: sc[k["key"]] for k in crit}}))
        ok(c.patch(f"/api/estimates/{e['id']}", headers=H["estimator"], json={"params": {"material_escalation_pct": 6}}))
        v = ok(c.post("/api/suppliers", headers=H["buyer"], json={"name": "الإلكترونيات المتقدمة — تيار خفيف", "kind": "subcontractor", "trades": ["Low current"],
                                                                 "project_types": ["building"], "contact_name": "م. ياسر", "phone": "0100 000 0000"}))
        ok(c.post(f"/api/suppliers/{v['id']}/evaluations", headers=H["buyer"], json={"quality": 4, "delivery": 3, "price": 4, "cooperation": 5, "comment": "مشروع سابق"}))

        # ---- 3. infrastructure tender at study stage
        i = ok(c.post("/api/tenders", headers=H["manager"], json={"name": "بنية تحتية — الحي السادس", "project_type": "infra", "owner": "شركة المدن الجديدة للتطوير",
                                                                 "submission_date": "2026-12-20", "site_visit_date": "2026-11-12", "duration_months": 18}))
        import_boq(i["id"], "owner_boq_infra_en.xlsx")
        print("Demo data loaded. Users (password demo1234): " + ", ".join(u for u, _, _ in team) + "  · admin / admin123")


if __name__ == "__main__":
    main()
