"""Stages 3–5 pricing: rate build-up (step 10), site overheads (12), risk / contingency / escalation (13),
finance / HO / taxes (14), markup what-if (15), spreading (16), review & approval (17), exports (18), baseline (20)."""
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import can, get_current_user, require
from ..db import get_db
from ..engine import pricing as E
from ..models import (BoqItem, BoqSource, BuildUpLine, BuildUpTemplate, CostCode, Document, Estimate, IndirectItem,
                      Package, Quotation, QuotationLine, Resource, Supplier, Tender, User)
from ..services.defaults import SCOPES
from ..services.estimating import (build_params, calculate, clone_estimate, compare_versions, default_fx, default_params,
                                   get_setting, history_rates, load_inputs, normalized_rate, result_for, run_checks,
                                   similar_history, vat_pct)
from ..services.excel_boq import build_workbook, export_priced_owner_format
from ..services.textnorm import TfIdfIndex
from .common import apply, editable_estimate, get_or_404, redact, row, tender_of

router = APIRouter(prefix="/api")
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def est_out(db: Session, est: Estimate, u: User) -> dict:
    d = row(est, exclude=("result",))
    if not can(u, "markup.view"):
        d["params"] = {k: v for k, v in (d.get("params") or {}).items() if k not in ("markup_pct", "spread_overrides")}
    names = {x.id: x.full_name or x.username for x in db.scalars(select(User)).all()}
    d["approved_by_name"] = names.get(est.approved_by)
    d["created_by_name"] = names.get(est.created_by)
    return d


@router.get("/tenders/{tid}/estimates")
def estimates(tid: int, db: Session = Depends(get_db), u: User = Depends(get_current_user)):
    return [est_out(db, e, u) for e in db.scalars(select(Estimate).where(Estimate.tender_id == tid).order_by(Estimate.version_no)).all()]


def load_indirect_template(db: Session, est: Estimate, tender: Tender):
    have = {x.template_key for x in db.scalars(select(IndirectItem).where(IndirectItem.estimate_id == est.id)).all()}
    n = 0
    for t in (get_setting(db, "indirect_templates") or {}).get(tender.project_type, []):
        if t["key"] in have:
            continue
        db.add(IndirectItem(estimate_id=est.id, category=t["category"], description=t["ar"], kind=t["kind"],
                            monthly_cost=t.get("monthly_cost", 0), quantity=t.get("quantity", 1), amount=t.get("amount", 0),
                            template_key=t["key"], currency=tender.base_currency))
        n += 1
    return n


@router.post("/tenders/{tid}/estimates")
def create_estimate(tid: int, data: dict = Body(default={}), db: Session = Depends(get_db), u: User = Depends(require("pricing.edit"))):
    t = tender_of(db, tid)
    if data.get("clone_from"):
        src = get_or_404(db, Estimate, data["clone_from"])
        est = clone_estimate(db, src, u.id, data.get("name", ""))
    else:
        n = (db.scalar(select(Estimate.version_no).where(Estimate.tender_id == tid).order_by(Estimate.version_no.desc())) or 0) + 1
        est = Estimate(tender_id=tid, version_no=n, name=data.get("name") or f"V{n}", fx_rates=default_fx(db),
                       params=default_params(db, t), created_by=u.id)
        db.add(est)
        db.flush()
        load_indirect_template(db, est, t)
    db.commit()
    return est_out(db, est, u)


MARKUP_PARAMS = {"markup_pct", "spread_overrides"}


@router.get("/estimates/{eid}")
def get_estimate(eid: int, db: Session = Depends(get_db), u: User = Depends(get_current_user)):
    est = get_or_404(db, Estimate, eid)
    return est_out(db, est, u)


@router.patch("/estimates/{eid}")
def update_estimate(eid: int, data: dict = Body(...), db: Session = Depends(get_db), u: User = Depends(get_current_user)):
    """Markup / spreading needs markup.edit (management); every other input needs pricing.edit (estimators)."""
    est = get_or_404(db, Estimate, eid)
    editable_estimate(est)
    touched = {k for k, v in (data.get("params") or {}).items() if (est.params or {}).get(k) != v}
    if touched & MARKUP_PARAMS and not can(u, "markup.edit"):
        raise HTTPException(403, "Missing permission: markup.edit")
    if (touched - MARKUP_PARAMS or "fx_rates" in data or "name" in data) and not can(u, "pricing.edit"):
        raise HTTPException(403, "Missing permission: pricing.edit")
    if "params" in data:
        est.params = {**(est.params or {}), **data["params"]}
    if "fx_rates" in data:
        est.fx_rates = {k: v for k, v in data["fx_rates"].items() if v not in (None, "")}
    if "name" in data:
        est.name = data["name"]
    db.commit()
    return est_out(db, est, u)


# ---------------------------------------------------------------- rate build-up (step 10)
LINE_FIELDS = ["kind", "part", "description", "resource_id", "unit", "coefficient", "unit_price", "currency", "waste_pct",
               "source", "source_ref", "quotation_id", "price_date", "approved", "confidence"]


@router.get("/estimates/{eid}/lines")
def all_lines(eid: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return [row(ln) for ln in db.scalars(select(BuildUpLine).where(BuildUpLine.estimate_id == eid).order_by(BuildUpLine.id)).all()]


@router.put("/estimates/{eid}/items/{iid}/lines")
def put_lines(eid: int, iid: int, lines: list = Body(...), db: Session = Depends(get_db), u: User = Depends(require("pricing.edit"))):
    est = get_or_404(db, Estimate, eid)
    editable_estimate(est)
    for ln in db.scalars(select(BuildUpLine).where(BuildUpLine.estimate_id == eid, BuildUpLine.boq_item_id == iid)).all():
        db.delete(ln)
    db.flush()
    for ln in lines:
        obj = apply(BuildUpLine(estimate_id=eid, boq_item_id=iid), ln, LINE_FIELDS)
        if obj.price_date is None and obj.source in ("manual", "library"):
            obj.price_date = date.today()
        db.add(obj)
    db.commit()
    return [row(x) for x in db.scalars(select(BuildUpLine).where(BuildUpLine.estimate_id == eid, BuildUpLine.boq_item_id == iid)).all()]


@router.post("/estimates/{eid}/lines/approve")
def approve_lines(eid: int, data: dict = Body(default={}), db: Session = Depends(get_db), u: User = Depends(require("pricing.edit"))):
    est = get_or_404(db, Estimate, eid)
    editable_estimate(est)
    q = select(BuildUpLine).where(BuildUpLine.estimate_id == eid, BuildUpLine.approved.is_(False))
    if data.get("item_id"):
        q = q.where(BuildUpLine.boq_item_id == data["item_id"])
    n = 0
    for ln in db.scalars(q).all():
        ln.approved = True
        n += 1
    from ..models import AISuggestion
    for s in db.scalars(select(AISuggestion).where(AISuggestion.kind == "rate", AISuggestion.status == "pending",
                                                   AISuggestion.target.like(f"{eid}:%"))).all():
        if not data.get("item_id") or s.target == f"{eid}:{data['item_id']}":
            s.status, s.decided_by, s.decided_at = "accepted", u.id, datetime.utcnow()
    db.commit()
    return {"approved": n}


@router.get("/estimates/{eid}/items/{iid}/sources")
def price_sources(eid: int, iid: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """All candidate prices for one item, in the priority order of the commercial review:
    1) supplier / subcontractor quotations  2) internal resource library  3) nearest previous project."""
    est = get_or_404(db, Estimate, eid)
    it = get_or_404(db, BoqItem, iid)
    vat = vat_pct(db)
    quotes = []
    for ql in db.scalars(select(QuotationLine).where(QuotationLine.boq_item_id == iid)).all():
        q = db.get(Quotation, ql.quotation_id)
        sup = db.get(Supplier, q.supplier_id)
        quotes.append({"quotation_id": q.id, "supplier": sup.name if sup else "", "scope": q.scope, "currency": q.currency,
                       "quoted": float(ql.unit_rate) if ql.unit_rate is not None else None,
                       "normalized": float(normalized_rate(q, ql.unit_rate, vat)) if ql.unit_rate is not None else None,
                       "lead_time_days": q.lead_time_days, "valid_until": q.valid_until.isoformat() if q.valid_until else None,
                       "approved": ql.approved, "received_date": q.received_date.isoformat() if q.received_date else None})
    res = db.scalars(select(Resource)).all()
    lib = []
    if res:
        idx = TfIdfIndex([(r.id, f"{r.name} {r.code}") for r in res])
        by_id = {r.id: r for r in res}
        lib = [{**row(by_id[rid]), "score": round(s, 3)} for s, rid in idx.search(it.description, k=8, min_score=0.08)]
    hist = similar_history(history_rates(db, exclude_tender_id=it.tender_id), it.description, it.unit, k=5)
    tpls = []
    if it.cost_code_id:
        tpls = [row(t) for t in db.scalars(select(BuildUpTemplate).where(BuildUpTemplate.cost_code_id == it.cost_code_id)).all()]
    return {"item": row(it), "quotations": quotes, "library": lib, "history": hist, "templates": tpls}


@router.post("/estimates/{eid}/items/{iid}/from-history")
def from_history(eid: int, iid: int, data: dict = Body(...), db: Session = Depends(get_db), u: User = Depends(require("pricing.edit"))):
    """Copy the build-up of a similar historical item as an AI-style suggestion (unapproved until accepted)."""
    est = get_or_404(db, Estimate, eid)
    editable_estimate(est)
    src_item = get_or_404(db, BoqItem, data["history_item_id"])
    src_est = db.scalars(select(Estimate).where(Estimate.tender_id == src_item.tender_id, Estimate.status == "approved")
                         .order_by(Estimate.version_no.desc())).first()
    if not src_est:
        raise HTTPException(404, "No approved estimate for that historical tender")
    src_t = db.get(Tender, src_item.tender_id)
    n = 0
    for ln in db.scalars(select(BuildUpLine).where(BuildUpLine.estimate_id == src_est.id, BuildUpLine.boq_item_id == src_item.id)).all():
        cols = {c: getattr(ln, c) for c in LINE_FIELDS}
        cols.update(source="history", source_ref=f"{src_t.code} / {src_item.item_ref}", approved=False,
                    confidence=data.get("score"), quotation_id=None)
        db.add(BuildUpLine(estimate_id=eid, boq_item_id=iid, **cols))
        n += 1
    if n == 0:  # imported reference file: only the rate is known
        r = next((x for x in (src_est.result or {}).get("items", []) if x["id"] == src_item.id), None)
        rate = (r or {}).get("direct_rate") or (r or {}).get("final_rate")
        if not rate:
            raise HTTPException(404, "No rate for that reference item")
        basis = "direct" if (r or {}).get("direct_rate") else "final (incl. overheads & profit)"
        db.add(BuildUpLine(estimate_id=eid, boq_item_id=iid, kind="subcontract", part=db.get(BoqItem, iid).scope,
                           description=f"Reference rate — {basis}", coefficient=1, unit_price=rate, currency="EGP",
                           source="history", source_ref=f"{src_t.code} / {src_item.item_ref}", approved=False,
                           confidence=data.get("score"), price_date=date.fromisoformat((src_est.result or {}).get("reference_date") or date.today().isoformat())))
        n = 1
    from ..models import AISuggestion
    db.add(AISuggestion(tender_id=est.tender_id, kind="rate", target=f"{eid}:{iid}", payload={"history_item_id": src_item.id},
                        source={"tender_code": src_t.code, "item_ref": src_item.item_ref}, confidence=float(data.get("score") or 0),
                        engine="similarity"))
    db.commit()
    return {"copied": n}


@router.post("/estimates/{eid}/apply-template")
def apply_template(eid: int, data: dict = Body(...), db: Session = Depends(get_db), _: User = Depends(require("pricing.edit"))):
    est = get_or_404(db, Estimate, eid)
    editable_estimate(est)
    tpl = get_or_404(db, BuildUpTemplate, data["template_id"])
    n = 0
    for iid in data["item_ids"]:
        for tl in tpl.lines:
            r = db.get(Resource, tl.get("resource_id")) if tl.get("resource_id") else None
            if r and tl.get("unit_price") is not None and tl.get("use_template_price"):
                r = None  # priced template: keep the template's own price
            db.add(BuildUpLine(estimate_id=eid, boq_item_id=iid, kind=tl.get("kind", r.kind if r else "material"),
                               part=tl.get("part", "supply_apply"), description=tl.get("description") or (r.name if r else ""),
                               resource_id=r.id if r else None, unit=r.unit if r else "", coefficient=tl.get("coefficient", 1),
                               unit_price=r.price if r else tl.get("unit_price", 0), currency=r.currency if r else tl.get("currency", "EGP"),
                               waste_pct=tl.get("waste_pct", r.waste_pct if r and r.waste_pct else 0), source="library",
                               source_ref=f"Template: {tpl.name}", price_date=r.price_date if r else (date.fromisoformat(tl["price_date"]) if tl.get("price_date") else date.today())))
            n += 1
    db.commit()
    return {"lines": n}


@router.get("/estimates/{eid}/analysis")
def price_analysis(eid: int, scope: str | None = None, kind: str | None = None, package_id: int | None = None,
                   source: str | None = None, db: Session = Depends(get_db), u: User = Depends(get_current_user)):
    """Price-analysis sheet with sub-filters: scope (Supply / Apply / Supply+Apply), resource kind, package, price source."""
    est = get_or_404(db, Estimate, eid)
    res = result_for(db, est)
    rows = {r["id"]: r for r in res["items"]}
    lines_by_item: dict[int, list] = {}
    for ln in db.scalars(select(BuildUpLine).where(BuildUpLine.estimate_id == eid)).all():
        lines_by_item.setdefault(ln.boq_item_id, []).append(ln)
    params = build_params(db, est, db.get(Tender, est.tender_id))
    out, totals = [], {"supply": 0.0, "apply": 0.0, "supply_apply": 0.0, "total": 0.0}
    for it in db.scalars(select(BoqItem).where(BoqItem.tender_id == est.tender_id, BoqItem.is_section.is_(False)).order_by(BoqItem.seq)).all():
        if scope and it.scope != scope and not any(ln.part == scope for ln in lines_by_item.get(it.id, [])):
            continue
        if package_id and it.package_id != package_id:
            continue
        lines = lines_by_item.get(it.id, [])
        if kind:
            lines = [ln for ln in lines if ln.kind == kind]
        if source:
            lines = [ln for ln in lines if ln.source == source]
        if scope:
            lines = [ln for ln in lines if ln.part == scope]
        if (kind or source) and not lines:
            continue
        missing: set = set()
        ldicts = []
        for ln in lines:
            uc = E.line_unit_cost(E.LineIn(ln.kind, E.dec(ln.coefficient), E.dec(ln.unit_price), ln.currency, E.dec(ln.waste_pct)), params, missing)
            ldicts.append({**row(ln), "unit_cost_base": float(uc)})
        sub = {p: sum(x["unit_cost_base"] for x in ldicts if x["part"] == p) for p in ("supply", "apply", "supply_apply")}
        r = rows.get(it.id, {})
        qty = float(it.quantity or 0)
        for p in ("supply", "apply", "supply_apply"):
            totals[p] += sub[p] * qty
        totals["total"] += sum(sub.values()) * qty
        d = {"id": it.id, "item_ref": it.item_ref, "description": it.description, "unit": it.unit, "quantity": qty,
             "scope": it.scope, "package_id": it.package_id, "lines": ldicts, "subtotals": sub,
             "direct_rate": r.get("direct_rate"), "provisional": it.is_provisional}
        if can(u, "markup.view"):
            d["final_rate"] = r.get("final_rate")
        out.append(d)
    return {"items": out, "totals": totals, "scopes": SCOPES}


# ---------------------------------------------------------------- site overheads (step 12)
IND_FIELDS = ["category", "description", "kind", "monthly_cost", "quantity", "months", "amount", "currency", "template_key", "origin", "approved"]


@router.get("/estimates/{eid}/indirects")
def indirects(eid: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return [row(x) for x in db.scalars(select(IndirectItem).where(IndirectItem.estimate_id == eid).order_by(IndirectItem.id)).all()]


@router.post("/estimates/{eid}/indirects")
def add_indirect(eid: int, data: dict = Body(...), db: Session = Depends(get_db), _: User = Depends(require("pricing.edit"))):
    editable_estimate(get_or_404(db, Estimate, eid))
    x = apply(IndirectItem(estimate_id=eid), data, IND_FIELDS)
    db.add(x)
    db.commit()
    return row(x)


@router.patch("/indirects/{xid}")
def update_indirect(xid: int, data: dict = Body(...), db: Session = Depends(get_db), _: User = Depends(require("pricing.edit"))):
    x = get_or_404(db, IndirectItem, xid)
    editable_estimate(db.get(Estimate, x.estimate_id))
    apply(x, data, IND_FIELDS)
    db.commit()
    return row(x)


@router.delete("/indirects/{xid}")
def delete_indirect(xid: int, db: Session = Depends(get_db), _: User = Depends(require("pricing.edit"))):
    x = get_or_404(db, IndirectItem, xid)
    editable_estimate(db.get(Estimate, x.estimate_id))
    db.delete(x)
    db.commit()
    return {"ok": True}


@router.post("/estimates/{eid}/indirects/template")
def indirect_template(eid: int, db: Session = Depends(get_db), _: User = Depends(require("pricing.edit"))):
    est = get_or_404(db, Estimate, eid)
    editable_estimate(est)
    n = load_indirect_template(db, est, db.get(Tender, est.tender_id))
    db.commit()
    return {"added": n}


# ---------------------------------------------------------------- calculation, what-if, checks
@router.get("/estimates/{eid}/calc")
def calc(eid: int, db: Session = Depends(get_db), u: User = Depends(get_current_user)):
    est = get_or_404(db, Estimate, eid)
    try:
        res = result_for(db, est)
    except E.PricingError as e:
        raise HTTPException(422, str(e))
    return redact(res, u)


@router.post("/estimates/{eid}/whatif")
def whatif(eid: int, data: dict = Body(...), db: Session = Depends(get_db), u: User = Depends(require("markup.view"))):
    est = get_or_404(db, Estimate, eid)
    tender, _items, e_items, e_inds, e_risks, e_phases = load_inputs(db, est)
    p = build_params(db, est, tender)
    marks = data.get("markups") or [0, 5, 7.5, 10, 12.5, 15, 20]
    return E.to_jsonable(E.what_if(e_items, e_inds, e_risks, p, e_phases, marks))


@router.get("/estimates/{eid}/checks")
def checks(eid: int, db: Session = Depends(get_db), u: User = Depends(get_current_user)):
    est = get_or_404(db, Estimate, eid)
    return run_checks(db, est, result_for(db, est) if est.status == "approved" else None)


# ---------------------------------------------------------------- approval cycle (step 17)
@router.post("/estimates/{eid}/submit")
def submit(eid: int, db: Session = Depends(get_db), u: User = Depends(require("pricing.edit"))):
    est = get_or_404(db, Estimate, eid)
    editable_estimate(est)
    errs = [c for c in run_checks(db, est) if c["severity"] == "error"]
    if errs:
        raise HTTPException(409, {"message": "Fix blocking checks before review", "checks": errs})
    est.status, est.submitted_by = "in_review", u.id
    t = db.get(Tender, est.tender_id)
    if t.status in ("pricing", "study"):
        t.status = "review"
    db.commit()
    return est_out(db, est, u)


@router.post("/estimates/{eid}/approve")
def approve(eid: int, db: Session = Depends(get_db), u: User = Depends(require("estimate.approve"))):
    est = get_or_404(db, Estimate, eid)
    if est.status != "in_review":
        raise HTTPException(409, "Only versions in review can be approved")
    res = E.to_jsonable(calculate(db, est))
    errs = [c for c in run_checks(db, est, res) if c["severity"] == "error"]
    if errs:
        raise HTTPException(409, {"message": "Blocking checks", "checks": errs})
    res["frozen_at"] = datetime.utcnow().isoformat()
    est.result = res  # frozen: exact numbers, FX rates and parameters at approval
    est.status, est.approved_by, est.approved_at = "approved", u.id, datetime.utcnow()
    t = db.get(Tender, est.tender_id)
    if t.status in ("review", "pricing", "study"):
        t.status = "approved"
    db.commit()
    return est_out(db, est, u)


@router.post("/estimates/{eid}/reject")
def reject(eid: int, data: dict = Body(default={}), db: Session = Depends(get_db), u: User = Depends(require("estimate.approve"))):
    est = get_or_404(db, Estimate, eid)
    if est.status != "in_review":
        raise HTTPException(409, "Only versions in review can be rejected")
    est.status = "rejected"  # back to stage 4 — editable again
    est.review_comments = data.get("comments", "")
    t = db.get(Tender, est.tender_id)
    if t.status == "review":
        t.status = "pricing"
    db.commit()
    return est_out(db, est, u)


@router.get("/estimates/compare/{a}/{b}")
def compare(a: int, b: int, db: Session = Depends(get_db), u: User = Depends(get_current_user)):
    ea, eb = get_or_404(db, Estimate, a), get_or_404(db, Estimate, b)
    if ea.tender_id != eb.tender_id:
        raise HTTPException(422, "Versions of different tenders")
    items = {i.id: i for i in db.scalars(select(BoqItem).where(BoqItem.tender_id == ea.tender_id)).all()}
    out = compare_versions(redact(result_for(db, ea), u), redact(result_for(db, eb), u), items)
    out["a"] = {"version": ea.version_no, "fx": ea.fx_rates, "markup": (ea.params or {}).get("markup_pct") if can(u, "markup.view") else None}
    out["b"] = {"version": eb.version_no, "fx": eb.fx_rates, "markup": (eb.params or {}).get("markup_pct") if can(u, "markup.view") else None}
    return out


# ---------------------------------------------------------------- exports
def _file(data: bytes, name: str):
    return Response(data, media_type=XLSX, headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/estimates/{eid}/export/owner.xlsx")
def export_owner(eid: int, db: Session = Depends(get_db), u: User = Depends(require("markup.view", "proposal.manage"))):
    """Priced BOQ in the owner's own workbook (same numbering, merged cells and sections)."""
    est = get_or_404(db, Estimate, eid)
    t = db.get(Tender, est.tender_id)
    res = result_for(db, est)
    rows = {r["id"]: r for r in res["items"]}
    items = db.scalars(select(BoqItem).where(BoqItem.tender_id == t.id, BoqItem.is_section.is_(False))).all()
    by_src: dict[int | None, list] = {}
    for it in items:
        r = rows.get(it.id)
        if r and it.row_index:
            by_src.setdefault(it.source_id, []).append({"sheet": it.sheet, "row": it.row_index, "rate": r["final_rate"], "amount": r["amount"]})
    src = db.scalars(select(BoqSource).where(BoqSource.tender_id == t.id).order_by(BoqSource.id.desc())).first()
    if not src or not src.document_id:
        return export_internal(eid, db, u)
    doc = db.get(Document, src.document_id)
    data = export_priced_owner_format(Path(doc.storage_path).read_bytes(), src.mapping, by_src.get(src.id, []))
    tag = "" if est.status == "approved" else "_DRAFT"
    return _file(data, f"{t.code}_V{est.version_no}{tag}_priced_BOQ.xlsx")


@router.get("/estimates/{eid}/export/internal.xlsx")
def export_internal(eid: int, db: Session = Depends(get_db), u: User = Depends(get_current_user)):
    est = get_or_404(db, Estimate, eid)
    t = db.get(Tender, est.tender_id)
    res = redact(result_for(db, est), u)
    rows = {r["id"]: r for r in res["items"]}
    show = can(u, "markup.view")
    boq_rows, sec_rows = [], []
    for it in db.scalars(select(BoqItem).where(BoqItem.tender_id == t.id).order_by(BoqItem.seq)).all():
        if it.is_section:
            sec_rows.append(len(boq_rows))
            boq_rows.append([it.item_ref, it.description, "", "", "", "", "", "", ""])
            continue
        r = rows.get(it.id, {})
        bk = r.get("by_kind") or {}
        boq_rows.append([it.item_ref, it.description, it.unit, float(it.quantity or 0), SCOPES[it.scope]["ar"],
                         bk.get("material"), bk.get("labor"), bk.get("equipment"), bk.get("subcontract"), r.get("direct_rate"),
                         r.get("direct_total")] + ([r.get("final_rate"), r.get("amount")] if show else []))
    s = res["summary"]
    summ = [[k, v] for k, v in s.items() if not isinstance(v, (dict, list))]
    lines = []
    for ln in db.scalars(select(BuildUpLine).where(BuildUpLine.estimate_id == eid)).all():
        it = db.get(BoqItem, ln.boq_item_id)
        lines.append([it.item_ref if it else "", ln.kind, SCOPES.get(ln.part, {}).get("ar", ln.part), ln.description,
                      float(ln.coefficient), float(ln.unit_price), ln.currency, float(ln.waste_pct), ln.source, ln.source_ref,
                      ln.price_date.isoformat() if ln.price_date else "", "✓" if ln.approved else "AI"])
    inds = [[x.category, x.description, x.kind, float(x.monthly_cost), float(x.quantity), float(x.months) if x.months else "",
             float(x.amount)] for x in db.scalars(select(IndirectItem).where(IndirectItem.estimate_id == eid)).all()]
    cf = [[r["month"], r["cost"], r["income"], r["balance"], r["interest"]] for r in res.get("cash_flow", [])]
    sheets = [
        {"title": "Summary", "headers": ["Item", "Value"], "rows": summ, "widths": [32, 20]},
        {"title": "BOQ", "headers": ["Ref", "Description", "Unit", "Qty", "Scope", "Material", "Labour", "Equipment",
                                     "Subcontract", "Direct rate", "Direct total"] + (["Final rate", "Amount"] if show else []),
         "rows": boq_rows, "section_rows": sec_rows, "widths": [8, 60, 8, 10, 14, 12, 12, 12, 12, 14, 16, 14, 16]},
        {"title": "Build-up", "headers": ["Ref", "Kind", "Part", "Description", "Coef.", "Unit price", "Cur", "Waste %", "Source",
                                          "Source ref", "Price date", "Approved"], "rows": lines},
        {"title": "Indirects", "headers": ["Category", "Description", "Kind", "Monthly", "Qty", "Months", "Fixed amount"], "rows": inds},
    ]
    if cf:
        sheets.append({"title": "Cash flow", "headers": ["Month", "Cost", "Income", "Balance", "Interest"], "rows": cf})
    sheets.append({"title": "Info", "headers": ["Field", "Value"], "rows": [
        ["Tender", f"{t.code} {t.name}"], ["Version", est.version_no], ["Status", est.status],
        ["FX rates", ", ".join(f"{k}={v}" for k, v in (est.fx_rates or {}).items())],
        ["Approved at", est.approved_at.isoformat() if est.approved_at else ""], ["Exported", datetime.utcnow().isoformat()]]})
    return _file(build_workbook(sheets), f"{t.code}_V{est.version_no}_estimate.xlsx")


@router.get("/estimates/{eid}/export/baseline.xlsx")
def export_baseline(eid: int, db: Session = Depends(get_db), u: User = Depends(require("markup.view"))):
    """Step 20 — on award, convert the approved estimate into the execution baseline budget (by cost code & package)."""
    est = get_or_404(db, Estimate, eid)
    if est.status != "approved":
        raise HTTPException(409, "Baseline budget is built from an approved version")
    t = db.get(Tender, est.tender_id)
    res = est.result
    rows = {r["id"]: r for r in res["items"]}
    codes = {c.id: c for c in db.scalars(select(CostCode)).all()}
    pkgs = {p.id: p for p in db.scalars(select(Package).where(Package.tender_id == t.id)).all()}
    agg: dict[tuple, dict] = {}
    for it in db.scalars(select(BoqItem).where(BoqItem.tender_id == t.id, BoqItem.is_section.is_(False))).all():
        r = rows.get(it.id) or {}
        cc = codes.get(it.cost_code_id)
        key = (cc.code if cc else "—", cc.name_ar if cc else "غير مكود", pkgs[it.package_id].name if it.package_id in pkgs else "—")
        a = agg.setdefault(key, {"material": 0, "labor": 0, "equipment": 0, "subcontract": 0, "direct": 0, "revenue": 0})
        q = r.get("quantity") or 0
        for k in ("material", "labor", "equipment", "subcontract"):
            a[k] += (r.get("by_kind") or {}).get(k, 0) * q
        a["direct"] += r.get("direct_total") or 0
        a["revenue"] += r.get("amount") or 0
    body = [[k[0], k[1], k[2], v["material"], v["labor"], v["equipment"], v["subcontract"], v["direct"], v["revenue"]]
            for k, v in sorted(agg.items())]
    s = res["summary"]
    body += [["", "مصاريف غير مباشرة للموقع / Site overheads", "", "", "", "", "", s["site_overheads"], ""],
             ["", "طوارئ / Contingency", "", "", "", "", "", s["contingency"] + s["escalation"], ""]]
    return _file(build_workbook([{"title": "Baseline budget", "headers": ["Cost code", "Name", "Package", "Material", "Labour",
                                                                            "Equipment", "Subcontract", "Budget", "Contract value"],
                                  "rows": body, "widths": [10, 40, 24, 14, 14, 14, 14, 16, 16]}]),
                 f"{t.code}_baseline_budget.xlsx")


@router.post("/estimates/{eid}/offer-letter")
def offer_letter(eid: int, data: dict = Body(default={}), db: Session = Depends(get_db), u: User = Depends(get_current_user)):
    """Financial offer covering letter: totals, validity, duration, selected clarifications / exclusions and VE options."""
    from ..models import VEAlternative
    est = get_or_404(db, Estimate, eid)
    t = db.get(Tender, est.tender_id)
    res = result_for(db, est)
    lib = get_setting(db, "clarifications_library") or []
    chosen = [lib[i]["ar"] for i in data.get("clarifications", []) if 0 <= i < len(lib)] + [x for x in data.get("extra", []) if x]
    s = res["summary"]
    show = can(u, "markup.view")
    lines = [f"السادة / {t.owner or '...'}", "تحية طيبة وبعد،",
             f"بالإشارة إلى مناقصة «{t.name}»، يسعدنا أن نتقدم بعرضنا المالي طبقًا للمقايسة المرفقة:", ""]
    if show:
        vat = s.get("vat_total") or 0
        lines += [f"• إجمالي العرض قبل ضريبة القيمة المضافة: {s['submitted_total']:,.2f} {t.base_currency}",
                  f"• ضريبة القيمة المضافة: {vat:,.2f} {t.base_currency}",
                  f"• الإجمالي شامل الضريبة: {s['submitted_total'] + vat:,.2f} {t.base_currency}"]
    if t.duration_months:
        lines.append(f"• مدة التنفيذ: {t.duration_months} شهرًا من تاريخ استلام الموقع.")
    lines.append(f"• مدة صلاحية العرض: {t.bid_validity_days or 90} يومًا من تاريخ فتح المظاريف.")
    if chosen:
        lines += ["", "التحفظات والاستيضاحات:"] + [f"{i}) {c}" for i, c in enumerate(chosen, start=1)]
    ve = db.scalars(select(VEAlternative).where(VEAlternative.tender_id == t.id, VEAlternative.status.in_(["proposed", "offered"]))).all()
    if ve and data.get("include_ve", True):
        lines += ["", "بدائل مقترحة (اختيارية) لتوفير التكلفة:"]
        for v in ve:
            it = db.get(BoqItem, v.boq_item_id) if v.boq_item_id else None
            lines.append(f"- {('البند ' + it.item_ref + ': ') if it else ''}{v.description}" + (f" — مدة التوريد {v.lead_time_days} يوم" if v.lead_time_days else ""))
    lines += ["", "وتفضلوا بقبول فائق الاحترام،"]
    return {"text": "\n".join(lines), "library": lib}
