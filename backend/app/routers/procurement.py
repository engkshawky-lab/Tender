"""Step 9 — RFQs and quotations (moved to Release 1 per the commercial review: quotations are the primary
price source for finishes, MEP, furniture and most infrastructure packages)."""
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import get_current_user, require
from ..db import get_db
from ..engine.pricing import to_jsonable
from ..models import AISuggestion, BoqItem, Estimate, Package, Quotation, QuotationLine, Supplier, User
from ..services import ai
from ..services.defaults import SCOPES
from ..services.estimating import apply_quotation, comparison
from ..services.excel_boq import build_rfq, read_rfq
from ..services.textnorm import normalize
from .common import apply, editable_estimate, get_or_404, row, tender_of
from .tenders import store_document

router = APIRouter(prefix="/api")

Q_FIELDS = ["package_id", "supplier_id", "reference", "scope", "received_date", "valid_until", "currency", "payment_terms",
            "lead_time_days", "exclusions", "includes_vat", "includes_transport", "transport_adjust_pct", "other_adjust_pct",
            "discount_pct", "document_id", "origin", "notes", "tech_scores", "tech_notes"]


def q_out(db: Session, q: Quotation) -> dict:
    d = row(q)
    sup = db.get(Supplier, q.supplier_id)
    d["supplier"] = sup.name if sup else None
    d["lines"] = [row(ln) for ln in q.lines]
    return d


@router.get("/tenders/{tid}/quotations")
def quotations(tid: int, package_id: int | None = None, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    q = select(Quotation).where(Quotation.tender_id == tid)
    if package_id:
        q = q.where(Quotation.package_id == package_id)
    return [q_out(db, x) for x in db.scalars(q.order_by(Quotation.id)).all()]


def _set_lines(db: Session, q: Quotation, lines: list[dict], approved: bool = True):
    current = {ln.boq_item_id: ln for ln in q.lines}
    for ln in lines:
        iid = int(ln["boq_item_id"])
        obj = current.get(iid)
        if not obj:
            obj = QuotationLine(quotation_id=q.id, boq_item_id=iid)
            q.lines.append(obj)
        apply(obj, ln, ["unit_rate", "remarks"])
        obj.approved = ln.get("approved", approved)


@router.post("/tenders/{tid}/quotations")
def create_quotation(tid: int, data: dict = Body(...), db: Session = Depends(get_db), _: User = Depends(require("procurement.manage"))):
    tender_of(db, tid)
    if not data.get("supplier_id"):
        raise HTTPException(422, "supplier_id is required")
    q = apply(Quotation(tender_id=tid), data, Q_FIELDS)
    db.add(q)
    db.flush()
    _set_lines(db, q, data.get("lines", []))
    db.commit()
    return q_out(db, q)


@router.patch("/quotations/{qid}")
def update_quotation(qid: int, data: dict = Body(...), db: Session = Depends(get_db), _: User = Depends(require("procurement.manage"))):
    q = apply(get_or_404(db, Quotation, qid), data, Q_FIELDS)
    if "lines" in data:
        _set_lines(db, q, data["lines"])
    db.commit()
    return q_out(db, q)


@router.post("/quotations/{qid}/approve-lines")
def approve_lines(qid: int, db: Session = Depends(get_db), u: User = Depends(require("procurement.manage"))):
    q = get_or_404(db, Quotation, qid)
    for ln in q.lines:
        ln.approved = True
    for s in db.scalars(select(AISuggestion).where(AISuggestion.kind == "quotation", AISuggestion.target == str(qid),
                                                   AISuggestion.status == "pending")).all():
        s.status = "accepted"
        s.decided_by = u.id
    db.commit()
    return q_out(db, q)


@router.delete("/quotations/{qid}")
def delete_quotation(qid: int, db: Session = Depends(get_db), _: User = Depends(require("procurement.manage"))):
    db.delete(get_or_404(db, Quotation, qid))
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- RFQ files
def package_items(db: Session, pid: int):
    return db.scalars(select(BoqItem).where(BoqItem.package_id == pid, BoqItem.is_section.is_(False)).order_by(BoqItem.seq)).all()


@router.get("/packages/{pid}/rfq.xlsx")
def rfq(pid: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    p = get_or_404(db, Package, pid)
    t = tender_of(db, p.tender_id)
    items = [{"id": i.id, "item_ref": i.item_ref, "description": i.description, "unit": i.unit, "quantity": i.quantity}
             for i in package_items(db, pid)]
    data = build_rfq({"code": t.code, "name": t.name, "currency": t.base_currency},
                     {"name": p.name, "scope_label": f'{SCOPES[p.scope]["ar"]} / {SCOPES[p.scope]["en"]}'}, items)
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="RFQ_{t.code}_{pid}.xlsx"'})


def _find_supplier(db: Session, name: str | None, fallback_id: int | None) -> int:
    if fallback_id:
        return int(fallback_id)
    if name:
        for s in db.scalars(select(Supplier)).all():
            if normalize(s.name) == normalize(name):
                return s.id
        s = Supplier(name=name)
        db.add(s)
        db.flush()
        return s.id
    raise HTTPException(422, "Supplier unknown — choose the supplier")


@router.post("/packages/{pid}/quotations/upload")
async def upload_quotation(pid: int, file: UploadFile = File(...), supplier_id: int | None = Form(None), scope: str | None = Form(None),
                           db: Session = Depends(get_db), u: User = Depends(require("procurement.manage"))):
    """A filled RFQ template is read deterministically; any other file (PDF, e-mail, foreign Excel) goes to the AI
    reader and its lines stay unapproved until procurement accepts them."""
    p = get_or_404(db, Package, pid)
    data = await file.read()
    doc = store_document(db, p.tender_id, file, data, "quotation", title=file.filename or "quotation", user_id=u.id)
    items = package_items(db, pid)
    valid_ids = {i.id for i in items}
    rfq_data = None
    if (file.filename or "").lower().endswith(".xlsx"):
        try:
            rfq_data = read_rfq(data)
        except ValueError:
            rfq_data = None
    if rfq_data:
        meta = rfq_data["meta"]
        sid = _find_supplier(db, meta.get("supplier"), supplier_id)
        lt = meta.get("lead time (days)")
        vu = meta.get("valid until")
        q = Quotation(tender_id=p.tender_id, package_id=pid, supplier_id=sid, scope=scope or p.scope, origin="excel",
                      currency=(meta.get("currency") or "EGP")[:3], document_id=doc.id, received_date=date.today(),
                      lead_time_days=int(lt) if isinstance(lt, (int, float)) else None,
                      valid_until=vu.date() if hasattr(vu, "date") else (date.fromisoformat(vu) if isinstance(vu, str) and len(vu) >= 10 else None),
                      payment_terms=str(meta.get("payment terms") or ""), exclusions=str(meta.get("exclusions") or ""))
        db.add(q)
        db.flush()
        _set_lines(db, q, [ln for ln in rfq_data["lines"] if ln["boq_item_id"] in valid_ids], approved=True)
        db.commit()
        return q_out(db, q)
    pages = [pg.text for pg in doc.page_texts]
    try:
        out = ai.extract_quotation(file.filename or "", data, pages,
                                   [{"id": i.id, "item_ref": i.item_ref, "description": i.description, "unit": i.unit,
                                     "quantity": float(i.quantity)} for i in items])
    except ai.AIError as e:
        db.commit()  # keep the stored document
        raise HTTPException(422, str(e))
    sid = _find_supplier(db, out.get("supplier_name"), supplier_id)
    q = Quotation(tender_id=p.tender_id, package_id=pid, supplier_id=sid, scope=scope or out.get("scope") or p.scope, origin="ai",
                  currency=(out.get("currency") or "EGP")[:3], document_id=doc.id, received_date=date.today(),
                  lead_time_days=out.get("lead_time_days"), payment_terms=out.get("payment_terms", ""),
                  exclusions=out.get("exclusions", ""), includes_vat=out.get("includes_vat", False),
                  includes_transport=out.get("includes_transport", True),
                  valid_until=date.fromisoformat(out["valid_until"][:10]) if out.get("valid_until") else None)
    db.add(q)
    db.flush()
    _set_lines(db, q, [ln for ln in out.get("lines", []) if ln["boq_item_id"] in valid_ids], approved=False)
    db.add(AISuggestion(tender_id=p.tender_id, kind="quotation", target=str(q.id), payload={"lines": len(out.get("lines", []))},
                        source={"document_id": doc.id, "file": file.filename}, confidence=0.7, engine=out.get("engine", "")))
    db.commit()
    return q_out(db, q)


# ---------------------------------------------------------------- comparison & selection
@router.get("/packages/{pid}/comparison")
def package_comparison(pid: int, estimate_id: int | None = None, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    p = get_or_404(db, Package, pid)
    t = tender_of(db, p.tender_id)
    est = db.get(Estimate, estimate_id) if estimate_id else None
    fx = (est.fx_rates if est else None) or {}
    if not fx:
        from ..services.estimating import default_fx
        fx = default_fx(db)
    return to_jsonable(comparison(db, p, fx, t.base_currency))


@router.post("/packages/{pid}/select")
def select_quotation(pid: int, data: dict = Body(...), db: Session = Depends(get_db), u: User = Depends(require("procurement.manage"))):
    """Select the quotation for the package and write its rates into the estimate build-up.
    Supply & Apply split: select a Supply quote and an Apply quote (role='apply')."""
    p = get_or_404(db, Package, pid)
    q = get_or_404(db, Quotation, data["quotation_id"])
    if q.package_id != pid:
        raise HTTPException(422, "Quotation belongs to another package")
    if any(not ln.approved for ln in q.lines):
        raise HTTPException(409, "Approve the AI-extracted quotation lines first")
    est = get_or_404(db, Estimate, data["estimate_id"])
    editable_estimate(est)
    if q.scope == "apply" or data.get("role") == "apply":
        p.selected_apply_quotation_id = q.id
    else:
        p.selected_quotation_id = q.id
        if q.scope == "supply_apply":
            p.selected_apply_quotation_id = None
    n = apply_quotation(db, est, q, data.get("item_ids"))
    db.commit()
    return {"applied_items": n, "package": row(p)}
