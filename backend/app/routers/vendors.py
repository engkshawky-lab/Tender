"""Approved Vendor List (سجل الموردين المعتمدين): register, approval cycle, documents with expiry,
performance evaluations, and alerts for expiring approvals / documents."""
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..auth import get_current_user, require
from ..config import UPLOAD_DIR
from ..db import get_db
from ..models import Quotation, Supplier, SupplierDocument, SupplierEvaluation, Tender, User
from .common import apply, get_or_404, row

router = APIRouter(prefix="/api")

SUP_FIELDS = ["name", "kind", "trades", "project_types", "brands", "contact_name", "phone", "email", "address",
              "commercial_register", "tax_card", "approval_expiry", "approved_by", "payment_terms", "notes"]
STATUSES = ("approved", "pending", "suspended", "blacklisted")


def supplier_out(db: Session, s: Supplier) -> dict:
    d = row(s)
    today = date.today()
    d["approval_valid"] = s.status == "approved" and (s.approval_expiry is None or s.approval_expiry >= today)
    d["documents"] = db.scalar(select(func.count(SupplierDocument.id)).where(SupplierDocument.supplier_id == s.id)) or 0
    d["evaluations"] = db.scalar(select(func.count(SupplierEvaluation.id)).where(SupplierEvaluation.supplier_id == s.id)) or 0
    d["quotations"] = db.scalar(select(func.count(Quotation.id)).where(Quotation.supplier_id == s.id)) or 0
    return d


@router.get("/suppliers")
def suppliers(q: str | None = None, status: str | None = None, trade: str | None = None, project_type: str | None = None,
              db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    stmt = select(Supplier).order_by(Supplier.name)
    if q:
        stmt = stmt.where(or_(Supplier.name.ilike(f"%{q}%"), Supplier.brands.ilike(f"%{q}%")))
    if status:
        stmt = stmt.where(Supplier.status == status)
    out = [supplier_out(db, s) for s in db.scalars(stmt).all()]
    if trade:
        out = [s for s in out if any(trade.lower() in t.lower() for t in (s["trades"] or []))]
    if project_type:
        out = [s for s in out if not s["project_types"] or project_type in s["project_types"]]
    return out


@router.post("/suppliers")
def create_supplier(data: dict = Body(...), db: Session = Depends(get_db), _: User = Depends(require("procurement.manage"))):
    if not data.get("name"):
        raise HTTPException(422, "name is required")
    s = apply(Supplier(status="pending"), data, SUP_FIELDS)
    db.add(s)
    db.commit()
    return supplier_out(db, s)


@router.patch("/suppliers/{sid}")
def update_supplier(sid: int, data: dict = Body(...), db: Session = Depends(get_db), _: User = Depends(require("procurement.manage"))):
    s = apply(get_or_404(db, Supplier, sid), data, SUP_FIELDS)
    db.commit()
    return supplier_out(db, s)


@router.post("/suppliers/{sid}/status")
def set_status(sid: int, data: dict = Body(...), db: Session = Depends(get_db), u: User = Depends(require("vendors.approve"))):
    """Approve / suspend / blacklist — restricted to users holding vendors.approve (management by default)."""
    s = get_or_404(db, Supplier, sid)
    st = data.get("status")
    if st not in STATUSES:
        raise HTTPException(422, f"status must be one of {STATUSES}")
    if st in ("suspended", "blacklisted") and not data.get("reason"):
        raise HTTPException(422, "A reason is required")
    s.status = st
    if st == "approved":
        s.approval_date = date.today()
        s.approved_by_user = u.id
        months = int(data.get("valid_months") or 12)
        s.approval_expiry = date.today() + timedelta(days=round(months * 30.4))
    if data.get("reason"):
        s.notes = (s.notes + "\n" if s.notes else "") + f"[{date.today()}] {st}: {data['reason']} — {u.full_name or u.username}"
    db.commit()
    return supplier_out(db, s)


# ---------------------------------------------------------------- documents
@router.get("/suppliers/{sid}/documents")
def documents(sid: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return [row(d) for d in db.scalars(select(SupplierDocument).where(SupplierDocument.supplier_id == sid).order_by(SupplierDocument.id)).all()]


@router.post("/suppliers/{sid}/documents")
async def upload(sid: int, file: UploadFile = File(...), kind: str = Form("other"), title: str = Form(""),
                 expiry_date: str | None = Form(None), db: Session = Depends(get_db), _: User = Depends(require("procurement.manage"))):
    get_or_404(db, Supplier, sid)
    d = UPLOAD_DIR / "suppliers" / str(sid)
    d.mkdir(parents=True, exist_ok=True)
    safe = "".join(ch for ch in Path(file.filename or "file").name if ch.isalnum() or ch in "._- ") or "file"
    p = d / f"{uuid.uuid4().hex[:8]}_{safe}"
    p.write_bytes(await file.read())
    doc = SupplierDocument(supplier_id=sid, kind=kind, title=title or (file.filename or ""), filename=file.filename or safe,
                           storage_path=str(p), expiry_date=date.fromisoformat(expiry_date) if expiry_date else None)
    db.add(doc)
    db.commit()
    return row(doc)


@router.get("/supplier-documents/{did}/file")
def download(did: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    d = get_or_404(db, SupplierDocument, did)
    return FileResponse(d.storage_path, filename=d.filename)


@router.delete("/supplier-documents/{did}")
def delete_doc(did: int, db: Session = Depends(get_db), _: User = Depends(require("procurement.manage"))):
    db.delete(get_or_404(db, SupplierDocument, did))
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- evaluations
EVAL_FIELDS = ["tender_id", "eval_date", "quality", "delivery", "price", "cooperation", "comment"]


@router.get("/suppliers/{sid}/evaluations")
def evaluations(sid: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    names = {u.id: u.full_name or u.username for u in db.scalars(select(User)).all()}
    codes = {t.id: t.code for t in db.scalars(select(Tender)).all()}
    return [{**row(e), "by": names.get(e.by_user), "tender_code": codes.get(e.tender_id),
             "average": (e.quality + e.delivery + e.price + e.cooperation) / 4}
            for e in db.scalars(select(SupplierEvaluation).where(SupplierEvaluation.supplier_id == sid).order_by(SupplierEvaluation.eval_date.desc())).all()]


@router.post("/suppliers/{sid}/evaluations")
def add_evaluation(sid: int, data: dict = Body(...), db: Session = Depends(get_db), u: User = Depends(require("procurement.manage"))):
    s = get_or_404(db, Supplier, sid)
    for k in ("quality", "delivery", "price", "cooperation"):
        if not 1 <= int(data.get(k, 3)) <= 5:
            raise HTTPException(422, f"{k} must be 1–5")
    e = apply(SupplierEvaluation(supplier_id=sid, by_user=u.id), data, EVAL_FIELDS)
    db.add(e)
    db.flush()
    evs = db.scalars(select(SupplierEvaluation).where(SupplierEvaluation.supplier_id == sid)).all()
    s.rating = round(sum((x.quality + x.delivery + x.price + x.cooperation) / 4 for x in evs) / len(evs), 2)
    db.commit()
    return row(e)


# ---------------------------------------------------------------- alerts
@router.get("/suppliers-alerts")
def alerts(days: int = 30, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    today, limit = date.today(), date.today() + timedelta(days=days)
    out = []
    for s in db.scalars(select(Supplier).where(Supplier.status == "approved", Supplier.approval_expiry.is_not(None),
                                               Supplier.approval_expiry <= limit)).all():
        out.append({"supplier_id": s.id, "supplier": s.name, "type": "approval", "date": s.approval_expiry.isoformat(),
                    "expired": s.approval_expiry < today})
    for d in db.scalars(select(SupplierDocument).where(SupplierDocument.expiry_date.is_not(None), SupplierDocument.expiry_date <= limit)).all():
        s = db.get(Supplier, d.supplier_id)
        out.append({"supplier_id": s.id, "supplier": s.name, "type": d.kind, "title": d.title, "date": d.expiry_date.isoformat(),
                    "expired": d.expiry_date < today})
    return sorted(out, key=lambda a: a["date"])
