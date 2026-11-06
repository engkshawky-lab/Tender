"""Stage 3 (steps 7–8): BOQ import / take-off check, cost coding, Supply/Apply scope, packaging;
plus the preliminary schedule (step 11) and value-engineering alternatives."""
import re
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Body, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import get_current_user, require, require_any
from ..db import get_db
from ..models import (AISuggestion, BoqItem, BoqSource, CostCode, Document, Estimate, Package, SchedulePhase, Tender,
                      User, VEAlternative)
from ..services.estimating import suggest_cost_codes
from ..services.excel_boq import parse_boq
from ..services.textnorm import normalize
from .common import apply, get_or_404, row, tender_of
from .tenders import store_document

router = APIRouter(prefix="/api")

SELF_PERFORM = {"B02", "B03", "B04", "I02"}  # civil / structure / roads usually self-performed


def detect_scope(desc: str) -> str:
    n = normalize(desc)
    if re.search(r"تركيب فقط|تنفيذ فقط|install(ation)? only|apply only|labou?r only|مصنعيه", n):
        return "apply"
    if re.search(r"توريد فقط|supply only|supply of\b(?!.*(install|lay|fix))", n):
        return "supply"
    return "supply_apply"


def detect_provisional(desc: str) -> bool:
    n = normalize(desc)
    return bool(re.search(r"مبلغ احتياطي|مبلغ تقديري|provisional sum|prime cost|p\.c\. sum|\bps\b", n))


@router.post("/tenders/{tid}/boq/preview")
async def preview(tid: int, file: UploadFile = File(...), db: Session = Depends(get_db), u: User = Depends(require("boq.edit"))):
    tender_of(db, tid)
    data = await file.read()
    if not (file.filename or "").lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(422, "Upload the owner's BOQ as .xlsx (PDF BOQs: use the AI document reader)")
    parsed = parse_boq(data)
    doc = store_document(db, tid, file, data, "boq", title=file.filename or "BOQ", user_id=u.id)
    db.commit()
    return {"document_id": doc.id, "mapping": parsed.mapping, "warnings": parsed.warnings,
            "rows": [r.__dict__ for r in parsed.rows[:500]], "count": len(parsed.rows),
            "items": sum(1 for r in parsed.rows if not r.is_section)}


@router.post("/tenders/{tid}/boq/import")
def import_boq(tid: int, data: dict = Body(...), db: Session = Depends(get_db), u: User = Depends(require("boq.edit"))):
    t = tender_of(db, tid)
    doc = get_or_404(db, Document, data["document_id"])
    if db.scalar(select(Estimate.id).where(Estimate.tender_id == tid, Estimate.status == "approved")) and data.get("replace"):
        raise HTTPException(409, "An approved estimate exists — create a new tender revision instead of replacing the BOQ")
    parsed = parse_boq(Path(doc.storage_path).read_bytes(), data.get("mapping"))
    if not parsed.mapping:
        raise HTTPException(422, "No BOQ header found; send an explicit mapping")
    if data.get("replace"):
        for it in db.scalars(select(BoqItem).where(BoqItem.tender_id == tid)).all():
            db.delete(it)
        db.flush()
    src = BoqSource(tender_id=tid, document_id=doc.id, mapping=parsed.mapping)
    db.add(src)
    db.flush()
    start = (db.scalar(select(BoqItem.seq).where(BoqItem.tender_id == tid).order_by(BoqItem.seq.desc())) or 0) + 1
    new_items = []
    for i, r in enumerate(parsed.rows):
        it = BoqItem(tender_id=tid, source_id=src.id, seq=start + i, sheet=r.sheet, row_index=r.row, item_ref=r.ref,
                     description=r.description, unit=r.unit, quantity=r.quantity or 0, is_section=r.is_section,
                     section=r.section, scope=detect_scope(r.description))
        if not r.is_section and detect_provisional(r.description):
            it.is_provisional = True
            it.provisional_amount = r.rate * (r.quantity or 1) if r.rate else None
        db.add(it)
        new_items.append(it)
    db.flush()
    # cost-code suggestions (need estimator approval — spec rules 2–3)
    priced = [it for it in new_items if not it.is_section]
    sugg = suggest_cost_codes(db, priced, t.project_type)
    for it in priced:
        best = (sugg.get(it.id) or [None])[0]
        if best:
            db.add(AISuggestion(tender_id=tid, kind="cost_code", target=str(it.id), payload=best,
                                source={"boq_item_id": it.id, "item_ref": it.item_ref}, confidence=min(1.0, best["score"] * 1.5),
                                engine="similarity"))
    if t.status in ("intake", "go_no_go", "study"):
        t.status = "pricing"
    db.commit()
    return {"imported": len(priced), "sections": len(new_items) - len(priced), "source_id": src.id, "warnings": parsed.warnings}


@router.get("/tenders/{tid}/boq")
def boq(tid: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    items = db.scalars(select(BoqItem).where(BoqItem.tender_id == tid).order_by(BoqItem.seq)).all()
    codes = {c.id: c for c in db.scalars(select(CostCode)).all()}
    out = []
    for it in items:
        d = row(it)
        cc = codes.get(it.cost_code_id)
        d["cost_code"] = cc.code if cc else None
        d["cost_code_name"] = cc.name_ar if cc else None
        out.append(d)
    return out


ITEM_FIELDS = ["item_ref", "description", "unit", "quantity", "is_section", "section", "scope", "cost_code_id", "package_id",
               "is_provisional", "provisional_amount", "checked_quantity", "qty_remark", "notes"]


@router.post("/tenders/{tid}/boq/items")
def add_item(tid: int, data: dict = Body(...), db: Session = Depends(get_db), _: User = Depends(require("boq.edit"))):
    seq = (db.scalar(select(BoqItem.seq).where(BoqItem.tender_id == tid).order_by(BoqItem.seq.desc())) or 0) + 1
    it = apply(BoqItem(tender_id=tid, seq=seq), data, ITEM_FIELDS)
    if "scope" not in data:
        it.scope = detect_scope(it.description)
    db.add(it)
    db.commit()
    return row(it)


@router.patch("/boq/items")
def bulk_update(data: list = Body(...), db: Session = Depends(get_db), _: User = Depends(require("boq.edit"))):
    out = []
    for d in data:
        it = get_or_404(db, BoqItem, d["id"])
        apply(it, d, ITEM_FIELDS)
        out.append(row(it))
    db.commit()
    return out


@router.delete("/boq/items/{iid}")
def delete_item(iid: int, db: Session = Depends(get_db), _: User = Depends(require("boq.edit"))):
    db.delete(get_or_404(db, BoqItem, iid))
    db.commit()
    return {"ok": True}


@router.post("/tenders/{tid}/boq/accept-cost-codes")
def accept_cost_codes(tid: int, data: dict = Body(default={}), db: Session = Depends(get_db), u: User = Depends(require("boq.edit"))):
    """Accept cost-code suggestions — all pending, or the given ids; optional min_confidence."""
    q = select(AISuggestion).where(AISuggestion.tender_id == tid, AISuggestion.kind == "cost_code", AISuggestion.status == "pending")
    if data.get("ids"):
        q = q.where(AISuggestion.id.in_(data["ids"]))
    n = 0
    for s in db.scalars(q).all():
        if s.confidence < float(data.get("min_confidence", 0)):
            continue
        it = db.get(BoqItem, int(s.target))
        if it:
            it.cost_code_id = s.payload["cost_code_id"]
            s.status, s.decided_by, s.decided_at = "accepted", u.id, datetime.utcnow()
            n += 1
    db.commit()
    return {"accepted": n}


@router.get("/boq/items/{iid}/cost-code-suggestions")
def item_cc_suggestions(iid: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    it = get_or_404(db, BoqItem, iid)
    t = db.get(Tender, it.tender_id)
    return suggest_cost_codes(db, [it], t.project_type)[it.id]


# ---------------------------------------------------------------- packages (step 8)
PKG_FIELDS = ["name", "trade", "execution", "scope", "required_on_site_month", "selected_quotation_id", "selected_apply_quotation_id"]


@router.get("/tenders/{tid}/packages")
def packages(tid: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    out = []
    for p in db.scalars(select(Package).where(Package.tender_id == tid).order_by(Package.id)).all():
        d = row(p)
        d["items"] = len(db.scalars(select(BoqItem.id).where(BoqItem.package_id == p.id)).all())
        out.append(d)
    return out


@router.post("/tenders/{tid}/packages")
def create_package(tid: int, data: dict = Body(...), db: Session = Depends(get_db), _: User = Depends(require("boq.edit"))):
    p = apply(Package(tender_id=tid), data, PKG_FIELDS)
    db.add(p)
    db.commit()
    return row(p)


@router.patch("/packages/{pid}")
def update_package(pid: int, data: dict = Body(...), db: Session = Depends(get_db),
                   _: User = Depends(require_any("boq.edit", "procurement.manage"))):
    p = apply(get_or_404(db, Package, pid), data, PKG_FIELDS)
    db.commit()
    return row(p)


@router.delete("/packages/{pid}")
def delete_package(pid: int, db: Session = Depends(get_db), _: User = Depends(require("boq.edit"))):
    db.delete(get_or_404(db, Package, pid))
    db.commit()
    return {"ok": True}


@router.post("/tenders/{tid}/packages/auto")
def auto_packages(tid: int, db: Session = Depends(get_db), _: User = Depends(require("boq.edit"))):
    """Group coded items by cost-code division into packages (self-perform for civil/structure/roads)."""
    codes = {c.id: c for c in db.scalars(select(CostCode)).all()}
    existing = {p.trade: p for p in db.scalars(select(Package).where(Package.tender_id == tid)).all()}
    n = 0
    for it in db.scalars(select(BoqItem).where(BoqItem.tender_id == tid, BoqItem.is_section.is_(False), BoqItem.package_id.is_(None))).all():
        cc = codes.get(it.cost_code_id)
        if not cc:
            continue
        div = cc
        while div.parent_id and div.level > 1:
            div = codes[div.parent_id]
        pk = existing.get(div.code)
        if not pk:
            pk = Package(tender_id=tid, name=div.name_ar, trade=div.code,
                         execution="self" if div.code in SELF_PERFORM else "subcontract",
                         scope="supply_apply")
            db.add(pk)
            db.flush()
            existing[div.code] = pk
        it.package_id = pk.id
        n += 1
    db.commit()
    return {"assigned": n, "packages": len(existing)}


# ---------------------------------------------------------------- schedule (step 11)
@router.get("/tenders/{tid}/schedule")
def schedule(tid: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    t = tender_of(db, tid)
    return {"duration_months": t.duration_months,
            "phases": [row(p) for p in db.scalars(select(SchedulePhase).where(SchedulePhase.tender_id == tid)
                                                  .order_by(SchedulePhase.start_month)).all()]}


@router.put("/tenders/{tid}/schedule")
def put_schedule(tid: int, data: dict = Body(...), db: Session = Depends(get_db), _: User = Depends(require("schedule.edit"))):
    t = tender_of(db, tid)
    if data.get("duration_months"):
        t.duration_months = int(data["duration_months"])
    for p in db.scalars(select(SchedulePhase).where(SchedulePhase.tender_id == tid)).all():
        db.delete(p)
    for p in data.get("phases", []):
        db.add(apply(SchedulePhase(tender_id=tid), p, ["name", "start_month", "duration_months", "weight_pct"]))
    db.commit()
    return schedule(tid, db)


@router.get("/tenders/{tid}/schedule/suggest")
def suggest_schedule(tid: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """Suggest a duration from similar past tenders of the same type (median), with phase split by package."""
    t = tender_of(db, tid)
    past = [x.duration_months for x in db.scalars(select(Tender).where(Tender.id != tid, Tender.project_type == t.project_type,
                                                                       Tender.duration_months.is_not(None))).all()]
    past.sort()
    median = past[len(past) // 2] if past else None
    return {"suggested_months": median, "based_on": len(past)}


# ---------------------------------------------------------------- value engineering
VE_FIELDS = ["boq_item_id", "description", "alternative_rate", "lead_time_days", "status", "notes"]


@router.get("/tenders/{tid}/ve")
def ve(tid: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return [row(v) for v in db.scalars(select(VEAlternative).where(VEAlternative.tender_id == tid)).all()]


@router.post("/tenders/{tid}/ve")
def create_ve(tid: int, data: dict = Body(...), db: Session = Depends(get_db), _: User = Depends(require("pricing.edit"))):
    v = apply(VEAlternative(tender_id=tid), data, VE_FIELDS)
    db.add(v)
    db.commit()
    return row(v)


@router.patch("/ve/{vid}")
def update_ve(vid: int, data: dict = Body(...), db: Session = Depends(get_db), _: User = Depends(require("pricing.edit"))):
    v = apply(get_or_404(db, VEAlternative, vid), data, VE_FIELDS)
    db.commit()
    return row(v)


@router.delete("/ve/{vid}")
def delete_ve(vid: int, db: Session = Depends(get_db), _: User = Depends(require("pricing.edit"))):
    db.delete(get_or_404(db, VEAlternative, vid))
    db.commit()
    return {"ok": True}
