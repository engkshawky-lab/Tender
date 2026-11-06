"""Glue between the database and the pure pricing engine: building inputs, quotation levelling,
comparison sheets, automated pre-approval checks and version snapshots."""
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..engine import pricing as E
from ..models import (BoqItem, BuildUpLine, CostCode, Estimate, IndirectItem, Package, Quotation,
                      QuotationLine, Risk, SchedulePhase, Setting, Supplier, Tender)
from .defaults import DEFAULT_SETTINGS
from .textnorm import TfIdfIndex, normalize

HISTORY_STATUSES = ("won", "lost", "historical", "submitted")


def get_setting(db: Session, key: str):
    s = db.get(Setting, key)
    return s.value if s is not None else DEFAULT_SETTINGS.get(key)


def dec(x) -> Decimal:
    return E.dec(x)


# ---------------------------------------------------------------- params
PARAM_KEYS = list(DEFAULT_SETTINGS["pricing_defaults"].keys())


def default_params(db: Session, tender: Tender) -> dict:
    p = dict(get_setting(db, "pricing_defaults"))
    if tender.bid_validity_days:
        p["bid_validity_days"] = tender.bid_validity_days
    # pre-fill from the approved tender summary when available
    s = tender.summary or {}
    for field, key in (("advance_payment", "advance_payment_pct"), ("retention", "retention_pct"),
                       ("performance_bond", "performance_bond_pct")):
        v = (s.get(field) or {}).get("numeric")
        if v is not None:
            p[key] = v
            if field == "advance_payment":
                p["advance_guarantee_pct"] = v
    pt = (s.get("payment_terms") or {}).get("numeric")
    if pt:
        p["payment_delay_months"] = max(1, round(float(pt) / 30))
    p["spread_overrides"] = {}
    return p


def default_fx(db: Session) -> dict:
    fx = dict(get_setting(db, "fx_rates") or {})
    fx.pop("as_of", None)
    return fx


def build_params(db: Session, est: Estimate, tender: Tender) -> E.Params:
    raw = {**default_params(db, tender), **(est.params or {})}
    taxes = [E.TaxIn(t["name"], dec(t["rate_pct"]), t.get("mode", "on_top")) for t in (raw.get("taxes") or get_setting(db, "taxes"))]
    overrides = {}
    for k, v in (raw.get("spread_overrides") or {}).items():
        overrides[int(k)] = v
    return E.Params(
        base_currency=tender.base_currency or "EGP",
        fx_rates={k: dec(v) for k, v in (est.fx_rates or {}).items() if v not in (None, "")},
        duration_months=int(raw.get("duration_months") or tender.duration_months or 12),
        markup_pct=dec(raw.get("markup_pct")), ho_overhead_pct=dec(raw.get("ho_overhead_pct")),
        general_contingency_pct=dec(raw.get("general_contingency_pct")),
        material_escalation_pct=dec(raw.get("material_escalation_pct")), fx_buffer_pct=dec(raw.get("fx_buffer_pct")),
        escalation_recovery_pct=(E.price_adjustment_recovery((raw.get("price_adjustment") or {}).get("components", []))
                                 if (raw.get("price_adjustment") or {}).get("enabled") else Decimal(0)),
        performance_bond_pct=dec(raw.get("performance_bond_pct")), advance_guarantee_pct=dec(raw.get("advance_guarantee_pct")),
        bond_commission_pa_pct=dec(raw.get("bond_commission_pa_pct")), maintenance_months=int(raw.get("maintenance_months") or 0),
        insurance_pct=dec(raw.get("insurance_pct")), bid_bond_amount=dec(tender.bid_bond_amount),
        bid_validity_days=int(raw.get("bid_validity_days") or 90),
        advance_payment_pct=dec(raw.get("advance_payment_pct")), retention_pct=dec(raw.get("retention_pct")),
        payment_delay_months=int(raw.get("payment_delay_months") or 0), finance_rate_pa_pct=dec(raw.get("finance_rate_pa_pct")),
        include_finance=bool(raw.get("include_finance", True)), taxes=taxes, spread_overrides=overrides,
        rate_decimals=int(raw.get("rate_decimals") or 2),
    )


def load_inputs(db: Session, est: Estimate):
    tender = db.get(Tender, est.tender_id)
    items = db.scalars(select(BoqItem).where(BoqItem.tender_id == tender.id, BoqItem.is_section.is_(False)).order_by(BoqItem.seq)).all()
    lines = db.scalars(select(BuildUpLine).where(BuildUpLine.estimate_id == est.id)).all()
    by_item: dict[int, list] = {}
    for ln in lines:
        by_item.setdefault(ln.boq_item_id, []).append(E.LineIn(ln.kind, dec(ln.coefficient), dec(ln.unit_price), ln.currency,
                                                               dec(ln.waste_pct), ln.part, ln.approved, ln.id))
    e_items = [E.ItemIn(i.id, dec(i.quantity), by_item.get(i.id, []), i.is_provisional, dec(i.provisional_amount), i.scope) for i in items]
    inds = db.scalars(select(IndirectItem).where(IndirectItem.estimate_id == est.id)).all()
    e_inds = [E.IndirectIn(x.kind, dec(x.monthly_cost), dec(x.quantity), x.months, dec(x.amount), x.currency, x.category, x.id)
              for x in inds if x.approved]
    risks = db.scalars(select(Risk).where(Risk.tender_id == tender.id, Risk.include_in_contingency.is_(True), Risk.approved.is_(True))).all()
    e_risks = [E.RiskIn(dec(r.probability_pct), dec(r.impact_amount), r.id) for r in risks]
    phases = db.scalars(select(SchedulePhase).where(SchedulePhase.tender_id == tender.id)).all()
    e_phases = [E.PhaseIn(ph.start_month, ph.duration_months, dec(ph.weight_pct)) for ph in phases]
    return tender, items, e_items, e_inds, e_risks, e_phases


def calculate(db: Session, est: Estimate) -> dict:
    tender, items, e_items, e_inds, e_risks, e_phases = load_inputs(db, est)
    params = build_params(db, est, tender)
    res = E.compute(e_items, e_inds, e_risks, params, e_phases)
    res["params"] = {k: v for k, v in params.__dict__.items() if k not in ("taxes", "spread_overrides")}
    res["params"]["taxes"] = [t.__dict__ for t in params.taxes]
    return res


def result_for(db: Session, est: Estimate) -> dict:
    """Approved versions are frozen: return the snapshot. Drafts are recalculated live."""
    if est.status == "approved" and est.result:
        return est.result
    return E.to_jsonable(calculate(db, est))


# ---------------------------------------------------------------- quotations
def vat_pct(db: Session) -> Decimal:
    return sum((dec(t["rate_pct"]) for t in get_setting(db, "taxes") if t.get("mode") == "on_top"), Decimal(0))


def normalized_rate(q: Quotation, rate, vat: Decimal) -> Decimal | None:
    """Level a quoted rate to a comparable basis: net of discount, transport added, VAT removed, scope adjustment."""
    if rate is None:
        return None
    r = dec(rate) * (1 - dec(q.discount_pct) / 100)
    if not q.includes_transport:
        r *= 1 + dec(q.transport_adjust_pct) / 100
    r *= 1 + dec(q.other_adjust_pct) / 100
    if q.includes_vat and vat:
        r /= 1 + vat / 100
    return r


def comparison(db: Session, package: Package, fx: dict, base: str) -> dict:
    items = db.scalars(select(BoqItem).where(BoqItem.package_id == package.id, BoqItem.is_section.is_(False)).order_by(BoqItem.seq)).all()
    quotes = db.scalars(select(Quotation).where(Quotation.package_id == package.id)).all()
    vat = vat_pct(db)
    tender = db.get(Tender, package.tender_id)
    cols = []
    for q in quotes:
        sup = db.get(Supplier, q.supplier_id)
        lines = {ln.boq_item_id: ln for ln in q.lines}
        f = Decimal(1) if q.currency == base else dec(fx.get(q.currency) or 0)
        total, missing, cells = Decimal(0), 0, {}
        for it in items:
            ln = lines.get(it.id)
            nr = normalized_rate(q, ln.unit_rate, vat) if ln else None
            if nr is None:
                missing += 1
                cells[it.id] = None
                continue
            base_rate = nr * f
            cells[it.id] = {"quoted": ln.unit_rate, "normalized": nr, "base": base_rate, "amount": base_rate * dec(it.quantity),
                            "approved": ln.approved, "remarks": ln.remarks}
            total += base_rate * dec(it.quantity)
        flags = []
        if q.valid_until and tender.submission_date and tender.bid_validity_days:
            needed = tender.submission_date + timedelta(days=tender.bid_validity_days)
            if q.valid_until < needed:
                flags.append({"code": "validity_short", "needed": needed.isoformat()})
        if q.lead_time_days and package.required_on_site_month:
            if q.lead_time_days > package.required_on_site_month * 30:
                flags.append({"code": "lead_time", "days": q.lead_time_days, "required_month": package.required_on_site_month})
        if f == 0:
            flags.append({"code": "missing_fx", "currency": q.currency})
        if sup and not (sup.status == "approved" and (sup.approval_expiry is None or sup.approval_expiry >= date.today())):
            flags.append({"code": "vendor_not_approved", "status": sup.status})
        cols.append({"quotation_id": q.id, "supplier": sup.name if sup else "?", "supplier_rating": sup.rating if sup else None,
                     "supplier_status": sup.status if sup else None,
                     "scope": q.scope, "currency": q.currency, "total_base": total, "missing_items": missing,
                     "valid_until": q.valid_until, "lead_time_days": q.lead_time_days, "payment_terms": q.payment_terms,
                     "exclusions": q.exclusions, "includes_vat": q.includes_vat, "includes_transport": q.includes_transport,
                     "flags": flags, "cells": cells, "selected": q.id in (package.selected_quotation_id, package.selected_apply_quotation_id)})
    complete = [c for c in cols if c["missing_items"] == 0 and c["total_base"] > 0]
    lowest = min(complete, key=lambda c: c["total_base"])["quotation_id"] if complete else None
    evaluation = evaluate_quotes(db, quotes, cols, lowest)
    per_item_low = {}
    for it in items:
        vals = [(c["cells"][it.id]["base"], c["quotation_id"]) for c in cols if c["cells"].get(it.id)]
        if vals:
            per_item_low[it.id] = min(vals)[1]
    return {"package": {"id": package.id, "name": package.name, "scope": package.scope},
            "items": [{"id": i.id, "item_ref": i.item_ref, "description": i.description, "unit": i.unit,
                       "quantity": i.quantity, "scope": i.scope} for i in items],
            "quotations": cols, "lowest_complete": lowest, "lowest_per_item": per_item_low, "evaluation": evaluation}


def evaluate_quotes(db: Session, quotes: list, cols: list[dict], lowest_id: int | None) -> dict:
    """Technical vs financial evaluation. Technical % = Σ weight × score/5. Financial % = lowest complete
    levelled total ÷ this levelled total × 100 (incomplete quotes are scored but flagged). Combined = weighted sum.
    Only quotes that pass the technical mark are ranked."""
    cfg = get_setting(db, "quote_evaluation")
    crit = cfg["criteria"]
    wsum = sum(c["weight"] for c in crit) or 1
    lowest_total = next((c["total_base"] for c in cols if c["quotation_id"] == lowest_id), None)
    if lowest_total is None:
        priced = [c["total_base"] for c in cols if c["total_base"] > 0]
        lowest_total = min(priced) if priced else None
    tw, fw = Decimal(str(cfg["technical_weight"])), Decimal(str(cfg["financial_weight"]))
    rows = []
    for q, c in zip(quotes, cols):
        scores = q.tech_scores or {}
        scored = all(scores.get(k["key"]) for k in crit)
        tech = Decimal(str(sum(k["weight"] * float(scores.get(k["key"]) or 0) / 5 for k in crit) / wsum * 100))
        fin = (dec(lowest_total) / c["total_base"] * 100) if lowest_total and c["total_base"] > 0 else Decimal(0)
        combined = (tech * tw + fin * fw) / (tw + fw) if (tw + fw) else Decimal(0)
        rows.append({"quotation_id": q.id, "supplier": c["supplier"], "scope": q.scope, "scores": scores, "notes": q.tech_notes,
                     "complete_scoring": scored, "technical_pct": tech, "financial_pct": fin, "combined_pct": combined,
                     "passes_technical": tech >= Decimal(str(cfg["technical_pass_pct"])), "missing_items": c["missing_items"],
                     "total_base": c["total_base"]})
    ranked = sorted([r for r in rows if r["passes_technical"] and r["complete_scoring"]], key=lambda r: -r["combined_pct"])
    for i, r in enumerate(ranked, start=1):
        r["rank"] = i
    return {"criteria": crit, "technical_weight": cfg["technical_weight"], "financial_weight": cfg["financial_weight"],
            "technical_pass_pct": cfg["technical_pass_pct"], "rows": rows,
            "recommended": ranked[0]["quotation_id"] if ranked else None}


def apply_quotation(db: Session, est: Estimate, q: Quotation, item_ids: list[int] | None = None) -> int:
    """Write the selected quotation into the build-up of every package item (quotation = first price source).
    Supply+Apply quotes replace the whole item build-up; Supply-only or Apply-only quotes replace that part only,
    so Supply & Apply can come from two different sources."""
    vat = vat_pct(db)
    sup = db.get(Supplier, q.supplier_id)
    kind = "material" if q.scope == "supply" else "subcontract"
    n = 0
    for ln in q.lines:
        if item_ids and ln.boq_item_id not in item_ids:
            continue
        nr = normalized_rate(q, ln.unit_rate, vat)
        if nr is None:
            continue
        parts = ("supply", "apply", "supply_apply") if q.scope == "supply_apply" else (q.scope, "supply_apply")
        for old in db.scalars(select(BuildUpLine).where(BuildUpLine.estimate_id == est.id,
                                                       BuildUpLine.boq_item_id == ln.boq_item_id,
                                                       BuildUpLine.part.in_(parts))).all():
            db.delete(old)
        db.add(BuildUpLine(estimate_id=est.id, boq_item_id=ln.boq_item_id, kind=kind, part=q.scope,
                           description=f"{sup.name if sup else ''} — {q.reference}".strip(" —"), coefficient=1,
                           unit_price=nr, currency=q.currency, waste_pct=0, source="quotation",
                           source_ref=f"Q#{q.id} {sup.name if sup else ''} {q.reference}".strip(), quotation_id=q.id,
                           price_date=q.received_date or date.today(), approved=ln.approved))
        n += 1
    return n


# ---------------------------------------------------------------- similarity: cost codes & history
def suggest_cost_codes(db: Session, items: list[BoqItem], project_type: str) -> dict[int, list]:
    codes = db.scalars(select(CostCode).where(CostCode.level == 3)).all()
    pref = [c for c in codes if c.project_type in (project_type, "common")] or codes
    idx = TfIdfIndex([(c.id, f"{c.name_ar} {c.name_en} {c.keywords}") for c in pref])
    by_id = {c.id: c for c in pref}
    out = {}
    for it in items:
        hits = idx.search(it.description, k=3, min_score=0.05)
        out[it.id] = [{"cost_code_id": cid, "code": by_id[cid].code, "name": by_id[cid].name_ar, "score": round(s, 3)} for s, cid in hits]
    return out


def index_factor(db: Session, ref_date: str | None) -> float | None:
    """Latest cost index ÷ index at the reference month (nearest earlier month). None when no index table."""
    vals = (get_setting(db, "cost_indices") or {}).get("values") or {}
    if not vals or not ref_date:
        return None
    months = sorted(vals)
    ref = ref_date[:7]
    base = [m for m in months if m <= ref]
    b = vals[base[-1]] if base else vals[months[0]]
    return float(vals[months[-1]]) / float(b) if b else None


def history_rates(db: Session, exclude_tender_id: int | None = None) -> list[dict]:
    """Priced items from previous tenders (approved estimate snapshots) — the 'nearest previous project' source."""
    rows = []
    tenders = db.scalars(select(Tender).where(Tender.status.in_(HISTORY_STATUSES))).all()
    for t in tenders:
        if t.id == exclude_tender_id:
            continue
        est = db.scalars(select(Estimate).where(Estimate.tender_id == t.id, Estimate.status == "approved")
                         .order_by(Estimate.version_no.desc())).first()
        if not est or not est.result:
            continue
        res = {r["id"]: r for r in est.result.get("items", [])}
        for it in db.scalars(select(BoqItem).where(BoqItem.tender_id == t.id, BoqItem.is_section.is_(False))).all():
            r = res.get(it.id)
            if r and (r.get("direct_rate") or r.get("final_rate")):
                rows.append({"tender_code": t.code, "tender_id": t.id, "tender_name": t.name, "project_type": t.project_type,
                             "outcome": (t.result or {}).get("outcome", t.status),
                             "item_id": it.id, "item_ref": it.item_ref, "description": it.description, "unit": it.unit,
                             "direct_rate": r.get("direct_rate") or None, "final_rate": r.get("final_rate"),
                             "reference_import": bool(est.result.get("reference_import")),
                             "date": (est.result.get("reference_date") or (est.approved_at or est.created_at).date().isoformat()),
                             "by_kind": r.get("by_kind", {})})
    for row_ in rows:
        f = index_factor(db, row_["date"])
        row_["index_factor"] = f
        row_["adj_direct_rate"] = row_["direct_rate"] * f if (f and row_["direct_rate"]) else row_["direct_rate"]
        row_["adj_final_rate"] = row_["final_rate"] * f if (f and row_["final_rate"]) else row_["final_rate"]
    return rows


def unit_key(u: str) -> str:
    n = normalize(u).replace(".", "").replace(" ", "")
    aliases = {"م3": "m3", "متر3": "m3", "م2": "m2", "متر2": "m2", "مط": "m", "م": "m", "عدد": "no", "nr": "no",
               "طن": "ton", "t": "ton", "مقطوعيه": "ls", "lumpsum": "ls"}
    return aliases.get(n, n)


def similar_history(history: list[dict], description: str, unit: str, k: int = 3) -> list[dict]:
    if not history:
        return []
    cands = [h for h in history if unit_key(h["unit"]) == unit_key(unit)] or history
    idx = TfIdfIndex([(i, h["description"]) for i, h in enumerate(cands)])
    return [{**cands[i], "score": round(s, 3)} for s, i in idx.search(description, k=k, min_score=0.15)]


# ---------------------------------------------------------------- automated checks (step 17)
def run_checks(db: Session, est: Estimate, res: dict | None = None) -> list[dict]:
    res = res or E.to_jsonable(calculate(db, est))
    tender = db.get(Tender, est.tender_id)
    items = {i.id: i for i in db.scalars(select(BoqItem).where(BoqItem.tender_id == tender.id, BoqItem.is_section.is_(False))).all()}
    out: list[dict] = []

    def add(sev, code, msg, item_id=None, **kw):
        out.append({"severity": sev, "code": code, "message": msg, "item_id": item_id, **kw})

    for w in res.get("warnings", []):
        add("error", w["code"], w["message"])
    for r in res["items"]:
        it = items.get(r["id"])
        ref = it.item_ref if it else r["id"]
        if r.get("provisional"):
            continue
        if not r.get("direct_rate"):
            add("error", "unpriced", f"Item {ref} has no price", r["id"])
        if r.get("unapproved_lines"):
            add("error", "ai_unapproved", f"Item {ref}: {r['unapproved_lines']} AI-suggested line(s) not yet approved", r["id"])
        if r.get("direct_rate") and r.get("final_rate") is not None and r["final_rate"] < r["direct_rate"]:
            add("warning", "below_cost", f"Item {ref}: final rate below direct cost", r["id"])
        if it and dec(it.quantity) <= 0:
            add("warning", "zero_qty", f"Item {ref} has zero quantity", r["id"])
        if it and it.checked_quantity is not None and dec(it.quantity) and abs(dec(it.checked_quantity) - dec(it.quantity)) / dec(it.quantity) > Decimal("0.05"):
            add("info", "qty_diff", f"Item {ref}: our take-off differs >5 % from the BOQ", r["id"])
    # sum check: Σ qty × rate equals the submitted total
    s = res["summary"]
    recompute = sum(Decimal(str(r.get("amount") or 0)) for r in res["items"])
    if abs(recompute - Decimal(str(s["submitted_total"]))) > Decimal("0.05"):
        add("error", "sum_mismatch", f"Sum of item amounts {recompute} ≠ total {s['submitted_total']}")
    if abs(s.get("rounding_diff", 0)) > 1:
        add("info", "rounding", f"Rounding difference of {s['rounding_diff']:.2f} between spread rates and target price")
    # stale prices (rule 4)
    age = int(get_setting(db, "price_age_days") or 90)
    limit = date.today() - timedelta(days=age)
    for ln in db.scalars(select(BuildUpLine).where(BuildUpLine.estimate_id == est.id)).all():
        if ln.price_date and ln.price_date < limit:
            ref = items[ln.boq_item_id].item_ref if ln.boq_item_id in items else ln.boq_item_id
            add("warning", "stale_price", f"Item {ref}: price dated {ln.price_date} is older than {age} days", ln.boq_item_id)
    # outliers vs history
    hist = history_rates(db, exclude_tender_id=tender.id)
    pct = Decimal(str(get_setting(db, "outlier_pct") or 35))
    if hist:
        for r in res["items"]:
            it = items.get(r["id"])
            if not it or r.get("provisional") or not r.get("direct_rate"):
                continue
            sim = similar_history([h for h in hist if h["direct_rate"]], it.description, it.unit, k=1)
            if sim and sim[0]["score"] > 0.45:
                ref_rate = Decimal(str(sim[0]["adj_direct_rate"]))
                dev = (Decimal(str(r["direct_rate"])) - ref_rate) / ref_rate * 100
                if abs(dev) > pct:
                    add("warning", "outlier", f"Item {it.item_ref}: direct rate deviates {dev:.0f}% from {sim[0]['tender_code']} item {sim[0]['item_ref']}",
                        it.id, reference=sim[0])
    # quotations validity / lead time for selected quotes
    for pk in db.scalars(select(Package).where(Package.tender_id == tender.id)).all():
        for qid in (pk.selected_quotation_id, pk.selected_apply_quotation_id):
            q = db.get(Quotation, qid) if qid else None
            if not q:
                continue
            if q.valid_until and tender.submission_date and tender.bid_validity_days and \
                    q.valid_until < tender.submission_date + timedelta(days=tender.bid_validity_days):
                add("warning", "quote_validity", f"Package {pk.name}: selected quotation expires before our bid validity ends")
            sup = db.get(Supplier, q.supplier_id)
            if sup and sup.status != "approved":
                add("error" if sup.status == "blacklisted" else "warning", "vendor_not_approved",
                    f"Package {pk.name}: selected vendor {sup.name} is {sup.status} in the approved vendor list")
            if q.lead_time_days and pk.required_on_site_month and q.lead_time_days > pk.required_on_site_month * 30:
                add("warning", "lead_time", f"Package {pk.name}: lead time {q.lead_time_days} days exceeds required date")
    # site overheads vs template
    tpl = (get_setting(db, "indirect_templates") or {}).get(tender.project_type, [])
    keys = {x.template_key for x in db.scalars(select(IndirectItem).where(IndirectItem.estimate_id == est.id)).all()}
    missing = [t for t in tpl if t["key"] not in keys]
    if missing:
        add("info", "indirects_missing", "Indirect items in the company template not used: " + ", ".join(t["ar"] for t in missing))
    return out


def clone_estimate(db: Session, src: Estimate, user_id: int | None, name: str = "") -> Estimate:
    n = (db.scalar(select(Estimate.version_no).where(Estimate.tender_id == src.tender_id).order_by(Estimate.version_no.desc())) or 0) + 1
    new = Estimate(tender_id=src.tender_id, version_no=n, name=name or f"V{n}", status="draft", fx_rates=dict(src.fx_rates or {}),
                   params=dict(src.params or {}), cloned_from_id=src.id, created_by=user_id)
    db.add(new)
    db.flush()
    cols = [c.key for c in BuildUpLine.__table__.columns if c.key not in ("id", "estimate_id")]
    for ln in db.scalars(select(BuildUpLine).where(BuildUpLine.estimate_id == src.id)).all():
        db.add(BuildUpLine(estimate_id=new.id, **{c: getattr(ln, c) for c in cols}))
    icols = [c.key for c in IndirectItem.__table__.columns if c.key not in ("id", "estimate_id")]
    for x in db.scalars(select(IndirectItem).where(IndirectItem.estimate_id == src.id)).all():
        db.add(IndirectItem(estimate_id=new.id, **{c: getattr(x, c) for c in icols}))
    return new


def compare_versions(a_res: dict, b_res: dict, items: dict[int, BoqItem]) -> dict:
    ai = {r["id"]: r for r in a_res["items"]}
    bi = {r["id"]: r for r in b_res["items"]}
    rows = []
    for iid in sorted(set(ai) | set(bi), key=lambda i: items[i].seq if i in items else 0):
        a, b = ai.get(iid, {}), bi.get(iid, {})
        if a.get("final_rate") != b.get("final_rate") or a.get("direct_rate") != b.get("direct_rate"):
            it = items.get(iid)
            rows.append({"id": iid, "item_ref": it.item_ref if it else "", "description": it.description if it else "",
                         "a_direct": a.get("direct_rate"), "b_direct": b.get("direct_rate"),
                         "a_rate": a.get("final_rate"), "b_rate": b.get("final_rate"),
                         "a_amount": a.get("amount"), "b_amount": b.get("amount")})
    keys = ["direct", "site_overheads", "contingency", "escalation", "ho_overheads", "finance", "bonds_insurance",
            "taxes_in_price", "profit", "submitted_total", "vat_total", "total_incl_vat"]
    summary = {k: {"a": a_res["summary"].get(k), "b": b_res["summary"].get(k)} for k in keys}
    return {"items": rows, "summary": summary}
