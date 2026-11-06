"""Pricing references: old priced BOQ files (won or lost) imported as reference projects, reference price lists,
priced templates, and comparison of the current estimate against the references.
(Spec: "مهمة قبل البرمجة — أداة استيراد لملفات Excel المسعرة من مناقصات سابقة".)"""
import io
from datetime import date, datetime
from pathlib import Path

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, UploadFile
from openpyxl import load_workbook
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth import can, get_current_user, require
from ..db import get_db
from ..engine.pricing import to_jsonable
from ..models import (AISuggestion, BoqItem, BoqSource, BuildUpLine, BuildUpTemplate, Estimate, Resource, Tender, User)
from ..services.estimating import history_rates, result_for, similar_history, suggest_cost_codes
from ..services.excel_boq import _match, parse_boq
from ..services.textnorm import normalize, to_number
from .boq import detect_provisional, detect_scope
from .common import get_or_404, row
from .tenders import store_document

router = APIRouter(prefix="/api")
REF_STATUSES = ("won", "lost", "historical", "submitted")


def _ref_code(db: Session, year: int) -> str:
    n = db.scalar(select(func.count(Tender.id)).where(Tender.code.like(f"REF-{year}-%"))) or 0
    while True:
        n += 1
        code = f"REF-{year}-{n:03d}"
        if not db.scalar(select(Tender.id).where(Tender.code == code)):
            return code


@router.post("/references/import")
async def import_reference(file: UploadFile = File(...), name: str = Form(...), project_type: str = Form("building"),
                           outcome: str = Form("historical"), reference_date: str | None = Form(None), owner: str = Form(""),
                           rate_basis: str = Form("final"), notes: str = Form(""),
                           db: Session = Depends(get_db), u: User = Depends(require("library.manage"))):
    """Import an old priced BOQ (the owner format we submitted, or our internal cost sheet).
    rate_basis = final (selling rates incl. overheads & profit) | direct (cost rates)."""
    data = await file.read()
    if not (file.filename or "").lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(422, "Upload the priced BOQ as .xlsx")
    parsed = parse_boq(data)
    if not parsed.mapping:
        raise HTTPException(422, "No BOQ header found")
    if not any(m["cols"].get("rate") for m in parsed.mapping.values()):
        raise HTTPException(422, "No rate / price column found in this file")
    ref_date = date.fromisoformat(reference_date) if reference_date else date.today()
    status = outcome if outcome in ("won", "lost") else "historical"
    t = Tender(code=_ref_code(db, ref_date.year), name=name, project_type=project_type, owner=owner, status=status,
               description=notes, created_by=u.id, result={"outcome": status, "date": ref_date.isoformat(), "reference_import": True})
    db.add(t)
    db.flush()
    doc = store_document(db, t.id, file, data, "boq", title=f"Priced BOQ — {name}", user_id=u.id)
    src = BoqSource(tender_id=t.id, document_id=doc.id, mapping=parsed.mapping)
    db.add(src)
    db.flush()
    items, snap, priced, total = [], [], 0, 0.0
    for i, r in enumerate(parsed.rows):
        it = BoqItem(tender_id=t.id, source_id=src.id, seq=i + 1, sheet=r.sheet, row_index=r.row, item_ref=r.ref,
                     description=r.description, unit=r.unit, quantity=r.quantity or 0, is_section=r.is_section,
                     section=r.section, scope=detect_scope(r.description), is_provisional=(not r.is_section and detect_provisional(r.description)))
        db.add(it)
        items.append((it, r))
    db.flush()
    for it, r in items:
        if it.is_section or not r.rate:
            continue
        amount = (r.quantity or 0) * r.rate
        total += amount
        priced += 1
        snap.append({"id": it.id, "quantity": r.quantity or 0, "final_rate": r.rate, "amount": amount,
                     "direct_rate": r.rate if rate_basis == "direct" else None, "provisional": it.is_provisional})
    if not priced:
        raise HTTPException(422, "The rate column is empty — is this the priced version of the file?")
    for it, _r in items:
        if not it.is_section:
            best = (suggest_cost_codes(db, [it], project_type).get(it.id) or [None])[0]
            if best and best["score"] > 0.2:
                it.cost_code_id = best["cost_code_id"]
    est = Estimate(tender_id=t.id, version_no=1, name="Reference import", status="approved", created_by=u.id,
                   approved_by=u.id, approved_at=datetime.combine(ref_date, datetime.min.time()),
                   result={"items": snap, "reference_import": True, "rate_basis": rate_basis, "reference_date": ref_date.isoformat(),
                           "summary": {"submitted_total": total, "direct": total if rate_basis == "direct" else None}, "cash_flow": [], "warnings": []})
    db.add(est)
    db.commit()
    return {"tender": row(t), "items": sum(1 for it, _ in items if not it.is_section), "priced": priced, "total": total,
            "warnings": parsed.warnings}


@router.get("/references")
def references(db: Session = Depends(get_db), u: User = Depends(get_current_user)):
    out = []
    for t in db.scalars(select(Tender).where(Tender.status.in_(REF_STATUSES)).order_by(Tender.created_at.desc())).all():
        est = db.scalars(select(Estimate).where(Estimate.tender_id == t.id, Estimate.status == "approved").order_by(Estimate.version_no.desc())).first()
        if not est or not est.result:
            continue
        d = row(t)
        d["items"] = len([r for r in est.result["items"] if r.get("final_rate") or r.get("direct_rate")])
        d["reference_import"] = bool(est.result.get("reference_import"))
        d["rate_basis"] = est.result.get("rate_basis", "estimate")
        d["date"] = est.result.get("reference_date") or (est.approved_at.date().isoformat() if est.approved_at else None)
        if can(u, "markup.view"):
            d["total"] = est.result["summary"].get("submitted_total")
        out.append(d)
    return out


@router.get("/references/search")
def search(q: str, unit: str = "", k: int = 10, db: Session = Depends(get_db), u: User = Depends(get_current_user)):
    rows = similar_history(history_rates(db), q, unit, k=k)
    if not can(u, "markup.view"):
        rows = [{**r, "final_rate": None, "adj_final_rate": None} for r in rows if r.get("direct_rate")]
    return rows


@router.get("/estimates/{eid}/reference")
def compare_with_references(eid: int, tender_ids: str = "", db: Session = Depends(get_db), u: User = Depends(get_current_user)):
    """Item-by-item: current direct / final rate vs the nearest reference items (deviation %)."""
    est = get_or_404(db, Estimate, eid)
    res = result_for(db, est)
    cur = {r["id"]: r for r in res["items"]}
    ids = {int(x) for x in tender_ids.split(",") if x.strip()}
    hist = [h for h in history_rates(db, exclude_tender_id=est.tender_id) if not ids or h["tender_id"] in ids]
    show_final = can(u, "markup.view")
    out = []
    for it in db.scalars(select(BoqItem).where(BoqItem.tender_id == est.tender_id, BoqItem.is_section.is_(False)).order_by(BoqItem.seq)).all():
        c = cur.get(it.id, {})
        if it.is_provisional:
            continue
        refs = similar_history(hist, it.description, it.unit, k=3)
        if not show_final:
            refs = [{**r, "final_rate": None, "adj_final_rate": None} for r in refs]
        row_ = {"id": it.id, "item_ref": it.item_ref, "description": it.description, "unit": it.unit, "quantity": float(it.quantity or 0),
                "direct_rate": c.get("direct_rate"), "final_rate": c.get("final_rate") if show_final else None, "references": refs}
        best = refs[0] if refs else None
        if best:
            if row_["final_rate"] and best.get("adj_final_rate"):
                row_["deviation_pct"] = (row_["final_rate"] - best["adj_final_rate"]) / best["adj_final_rate"] * 100
                row_["basis"] = "final"
            elif row_["direct_rate"] and best.get("adj_direct_rate"):
                row_["deviation_pct"] = (row_["direct_rate"] - best["adj_direct_rate"]) / best["adj_direct_rate"] * 100
                row_["basis"] = "direct"
            if row_.get("deviation_pct") is not None:
                d = abs(row_["deviation_pct"])
                row_["flag"] = "green" if d <= 10 else "amber" if d <= 25 else "red"
        out.append(row_)
    matched = [r for r in out if r.get("deviation_pct") is not None]
    return {"items": out, "matched": len(matched), "total": len(out),
            "flags": {k: sum(1 for r in matched if r.get("flag") == k) for k in ("green", "amber", "red")},
            "avg_deviation_pct": sum(r["deviation_pct"] for r in matched) / len(matched) if matched else None,
            "references": sorted({(h["tender_id"], h["tender_code"], h["tender_name"]) for h in hist})}


# ---------------------------------------------------------------- reference price list → resource library
PRICE_LIST_KEYS = {
    "name": ["description", "item", "material", "name", "الصنف", "البيان", "الوصف", "البند", "الخامه", "اسم"],
    "unit": ["unit", "uom", "الوحده"],
    "price": ["price", "rate", "unit price", "cost", "السعر", "سعر الوحده", "الفئه", "التكلفه"],
    "currency": ["currency", "cur", "العمله"],
    "kind": ["type", "kind", "category", "النوع", "التصنيف"],
    "code": ["code", "الكود", "كود"],
    "date": ["date", "price date", "التاريخ", "تاريخ السعر"],
    "source": ["source", "supplier", "المصدر", "المورد"],
}
KIND_WORDS = {"labor": ["labour", "labor", "عماله", "يوميه", "عامل"], "equipment": ["equipment", "plant", "معدات", "معده"],
              "subcontract": ["subcontract", "باطن", "مقاول"]}


@router.post("/resources/import")
async def import_price_list(file: UploadFile = File(...), default_kind: str = Form("material"), source: str = Form(""),
                            db: Session = Depends(get_db), _: User = Depends(require("library.manage"))):
    """Reference price list (Excel) → resource library. Existing resources (same code, or same name+unit) are updated
    with the new price and date, so the library keeps one current price per resource."""
    wb = load_workbook(io.BytesIO(await file.read()), data_only=True)
    created = updated = 0
    for ws in wb.worksheets:
        hdr, cols = None, {}
        for r in range(1, min(ws.max_row, 30) + 1):
            found = {}
            for c in range(1, min(ws.max_column, 25) + 1):
                v = ws.cell(r, c).value
                if isinstance(v, str):
                    for f, keys in PRICE_LIST_KEYS.items():
                        if f not in found and _match(v, keys):
                            found[f] = c
                            break
            if "name" in found and "price" in found:
                hdr, cols = r, found
                break
        if not hdr:
            continue
        for r in range(hdr + 1, ws.max_row + 1):
            name = ws.cell(r, cols["name"]).value
            price = to_number(ws.cell(r, cols["price"]).value)
            if not name or price is None:
                continue
            get = lambda f: ws.cell(r, cols[f]).value if f in cols else None  # noqa: E731
            kind_raw = normalize(str(get("kind") or ""))
            kind = next((k for k, ws_ in KIND_WORDS.items() if any(w in kind_raw for w in ws_)), default_kind)
            dval = get("date")
            pdate = dval.date() if hasattr(dval, "date") else (date.fromisoformat(str(dval)[:10]) if dval and str(dval)[:4].isdigit() else date.today())
            code = str(get("code") or "").strip()
            unit = str(get("unit") or "").strip()
            q = select(Resource).where(Resource.code == code) if code else select(Resource).where(Resource.name == str(name).strip(), Resource.unit == unit)
            res = db.scalars(q).first()
            if not res:
                res = Resource(name=str(name).strip(), kind=kind, unit=unit, code=code, price=0)
                db.add(res)
                created += 1
            else:
                updated += 1
            res.price = price
            res.currency = (str(get("currency") or "EGP").strip().upper() or "EGP")[:3]
            res.price_date = pdate
            res.source = str(get("source") or source or file.filename)
    db.commit()
    return {"created": created, "updated": updated}


# ---------------------------------------------------------------- priced templates from an analysed item
@router.post("/templates/from-item")
def template_from_item(data: dict = Body(...), db: Session = Depends(get_db), _: User = Depends(require("library.manage"))):
    it = get_or_404(db, BoqItem, data["item_id"])
    lines = db.scalars(select(BuildUpLine).where(BuildUpLine.estimate_id == data["estimate_id"], BuildUpLine.boq_item_id == it.id)).all()
    if not lines:
        raise HTTPException(422, "The item has no build-up lines")
    t = BuildUpTemplate(name=data.get("name") or it.description[:120], unit=it.unit, cost_code_id=it.cost_code_id, lines=[
        {"resource_id": ln.resource_id, "kind": ln.kind, "part": ln.part, "description": ln.description, "coefficient": float(ln.coefficient),
         "unit_price": float(ln.unit_price), "currency": ln.currency, "waste_pct": float(ln.waste_pct),
         "price_date": ln.price_date.isoformat() if ln.price_date else None, "use_template_price": True} for ln in lines])
    db.add(t)
    db.commit()
    return row(t)
