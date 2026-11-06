"""Stages 1, 2 and 5: tender register & dashboard, Go/No-Go, tasks, documents, AI tender analysis, risks, RFIs,
site visit, chat assistant, submission checklist and post-tender results."""
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth import can, get_current_user, require
from ..config import UPLOAD_DIR
from ..db import get_db
from ..models import (AISuggestion, BoqItem, Competitor, Document, DocumentPage, Estimate, RFI, Risk, SiteVisit,
                      Task, Tender, User)
from ..services import ai
from ..services.documents import compare_texts, extract_pages
from ..services.estimating import get_setting, result_for
from .common import apply, get_or_404, plain, row, tender_of

router = APIRouter(prefix="/api")

TENDER_FIELDS = ["name", "owner", "consultant", "project_type", "client_type", "location", "description", "status",
                 "invitation_date", "site_visit_date", "rfi_deadline", "submission_date", "bid_bond_amount",
                 "bid_validity_days", "duration_months", "base_currency", "assignments"]
ACTIVE = ("intake", "go_no_go", "study", "pricing", "review", "approved")


def next_code(db: Session) -> str:
    year = date.today().year
    n = db.scalar(select(func.count(Tender.id)).where(Tender.code.like(f"TND-{year}-%"))) or 0
    while True:
        n += 1
        code = f"TND-{year}-{n:03d}"
        if not db.scalar(select(Tender.id).where(Tender.code == code)):
            return code


def latest_estimate(db: Session, tid: int) -> Estimate | None:
    return db.scalars(select(Estimate).where(Estimate.tender_id == tid).order_by(Estimate.version_no.desc())).first()


def tender_out(db: Session, t: Tender, u: User, with_total=True) -> dict:
    d = row(t)
    if with_total and can(u, "markup.view"):
        est = db.scalars(select(Estimate).where(Estimate.tender_id == t.id, Estimate.status == "approved")
                         .order_by(Estimate.version_no.desc())).first()
        if est and est.result:
            d["approved_total"] = est.result["summary"].get("submitted_total")
            d["approved_version"] = est.version_no
    if t.submission_date:
        d["days_to_submission"] = (t.submission_date - date.today()).days
    return d


# ---------------------------------------------------------------- register & dashboard
@router.get("/tenders")
def list_tenders(status: str | None = None, db: Session = Depends(get_db), u: User = Depends(get_current_user)):
    q = select(Tender).order_by(Tender.created_at.desc())
    if status:
        q = q.where(Tender.status == status)
    return [tender_out(db, t, u) for t in db.scalars(q).all()]


@router.post("/tenders")
def create_tender(data: dict = Body(...), db: Session = Depends(get_db), u: User = Depends(require("tender.manage"))):
    if not data.get("name"):
        raise HTTPException(422, "name is required")
    t = apply(Tender(code=data.get("code") or next_code(db), created_by=u.id), data, TENDER_FIELDS)
    tpl = get_setting(db, "submission_checklist") or []
    t.submission_checklist = [{"ar": x["ar"], "en": x["en"], "done": False} for x in tpl]
    db.add(t)
    db.commit()
    return tender_out(db, t, u)


@router.get("/tenders/{tid}")
def get_tender(tid: int, db: Session = Depends(get_db), u: User = Depends(get_current_user)):
    return tender_out(db, tender_of(db, tid), u)


@router.patch("/tenders/{tid}")
def update_tender(tid: int, data: dict = Body(...), db: Session = Depends(get_db), u: User = Depends(require("tender.manage"))):
    t = apply(tender_of(db, tid), data, TENDER_FIELDS)
    db.commit()
    return tender_out(db, t, u)


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db), u: User = Depends(get_current_user)):
    tenders = db.scalars(select(Tender)).all()
    today = date.today()
    alerts = []
    for t in tenders:
        if t.status not in ACTIVE:
            continue
        for f, label in (("site_visit_date", "site_visit"), ("rfi_deadline", "rfi_deadline"), ("submission_date", "submission")):
            d = getattr(t, f)
            if d and today - timedelta(days=1) <= d <= today + timedelta(days=21):
                alerts.append({"tender_id": t.id, "code": t.code, "name": t.name, "type": label, "date": d.isoformat(),
                               "days": (d - today).days})
    alerts.sort(key=lambda a: a["days"])
    by_status: dict[str, int] = {}
    for t in tenders:
        by_status[t.status] = by_status.get(t.status, 0) + 1
    won, lost = by_status.get("won", 0), by_status.get("lost", 0)
    dec_q = select(AISuggestion.status, func.count()).where(AISuggestion.status != "pending").group_by(AISuggestion.status)
    ai_counts = dict(db.execute(dec_q).all())
    decided = sum(ai_counts.values())
    accepted = ai_counts.get("accepted", 0) + ai_counts.get("edited", 0)
    my_tasks = db.scalars(select(Task).where(Task.assignee_id == u.id, Task.status == "open").order_by(Task.due_date)).all()
    return {
        "alerts": alerts, "by_status": by_status,
        "active": sum(1 for t in tenders if t.status in ACTIVE),
        "win_rate": (won / (won + lost) * 100) if (won + lost) else None, "won": won, "lost": lost,
        "ai_acceptance_rate": (accepted / decided * 100) if decided else None, "ai_decided": decided,
        "ai_engine": ai.engine_name(),
        "my_tasks": [{**row(x), "tender_code": db.get(Tender, x.tender_id).code} for x in my_tasks],
    }


# ---------------------------------------------------------------- go / no-go (step 2)
@router.post("/tenders/{tid}/gonogo")
def gonogo(tid: int, data: dict = Body(...), db: Session = Depends(get_db), u: User = Depends(require("gonogo.decide"))):
    t = tender_of(db, tid)
    cfg = get_setting(db, "gonogo")
    scores = data.get("scores", {})  # {key: 1..5}
    total_w = sum(c["weight"] for c in cfg["criteria"]) or 1
    weighted = sum(c["weight"] * float(scores.get(c["key"], 0)) / 5 for c in cfg["criteria"]) / total_w * 100
    decision = data.get("decision") or ("go" if weighted >= cfg["threshold_pct"] else "no_go")
    if not data.get("reason"):
        raise HTTPException(422, "A documented reason is required for the decision")
    t.gonogo = {"scores": scores, "weighted": round(weighted, 1), "threshold": cfg["threshold_pct"], "decision": decision,
                "reason": data["reason"], "by": u.full_name or u.username, "at": datetime.utcnow().isoformat()}
    if decision == "no_go":
        t.status = "declined"
        t.gonogo["apology_letter"] = (
            f"السادة / {t.owner or '...'}\nتحية طيبة وبعد،\n"
            f"بالإشارة إلى دعوتكم الكريمة للمشاركة في مناقصة «{t.name}»، نشكركم على ثقتكم، ونعتذر عن عدم التقدم بعطاء "
            "في هذه المناقصة نظرًا لارتباطاتنا الحالية، ونأمل أن تتاح لنا فرصة التعاون في مشروعات قادمة.\nوتفضلوا بقبول فائق الاحترام،")
        t.gonogo["apology_letter_en"] = (
            f"Dear {t.owner or 'Sirs'},\n"
            f"Thank you for inviting us to tender for “{t.name}”. We regret that, owing to our current commitments, we are unable "
            "to submit a bid on this occasion. We value the invitation and look forward to working with you on future projects.\nYours faithfully,")
    elif t.status in ("intake", "go_no_go"):
        t.status = "study"
    db.commit()
    return row(t)


@router.get("/tenders/{tid}/gonogo/history")
def gonogo_history(tid: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """Similar past tenders (same type & client type) with their outcomes — guides the decision."""
    t = tender_of(db, tid)
    past = db.scalars(select(Tender).where(Tender.id != tid, Tender.project_type == t.project_type,
                                           Tender.status.in_(["won", "lost", "submitted", "declined", "historical"]))).all()
    won = sum(1 for p in past if p.status == "won")
    lost = sum(1 for p in past if p.status == "lost")
    scored = [p.gonogo.get("weighted") for p in past if p.gonogo and p.gonogo.get("weighted") is not None]
    return {"similar": [{"code": p.code, "name": p.name, "status": p.status, "score": (p.gonogo or {}).get("weighted")} for p in past],
            "win_rate": (won / (won + lost) * 100) if (won + lost) else None,
            "avg_score": sum(scored) / len(scored) if scored else None}


# ---------------------------------------------------------------- tasks
@router.get("/tenders/{tid}/tasks")
def tasks(tid: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return [row(x) for x in db.scalars(select(Task).where(Task.tender_id == tid).order_by(Task.due_date)).all()]


@router.post("/tenders/{tid}/tasks")
def create_task(tid: int, data: dict = Body(...), db: Session = Depends(get_db), _: User = Depends(require("tender.manage"))):
    x = apply(Task(tender_id=tid), data, ["title", "step", "assignee_id", "due_date", "status"])
    db.add(x)
    db.commit()
    return row(x)


@router.patch("/tasks/{xid}")
def update_task(xid: int, data: dict = Body(...), db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    x = apply(get_or_404(db, Task, xid), data, ["title", "step", "assignee_id", "due_date", "status"])
    db.commit()
    return row(x)


# ---------------------------------------------------------------- documents (step 3)
def save_upload(tid: int, f: UploadFile, data: bytes) -> Path:
    d = UPLOAD_DIR / str(tid)
    d.mkdir(parents=True, exist_ok=True)
    safe = "".join(ch for ch in Path(f.filename or "file").name if ch.isalnum() or ch in "._- ") or "file"
    p = d / f"{uuid.uuid4().hex[:10]}_{safe}"
    p.write_bytes(data)
    return p


def store_document(db: Session, tid: int, f: UploadFile, data: bytes, doc_type: str, title: str = "", revision: str = "0",
                   supersedes_id: int | None = None, user_id: int | None = None, issue_date: date | None = None) -> Document:
    path = save_upload(tid, f, data)
    pages, status = extract_pages(f.filename or "", data)
    doc = Document(tender_id=tid, doc_type=doc_type, title=title or (f.filename or "document"), filename=f.filename or "file",
                   storage_path=str(path), mime=f.content_type or "", revision=revision or "0", supersedes_id=supersedes_id,
                   pages=len(pages), text_status=status, uploaded_by=user_id, issue_date=issue_date)
    db.add(doc)
    db.flush()
    for i, txt in enumerate(pages, start=1):
        db.add(DocumentPage(document_id=doc.id, page_no=i, text=txt))
    if supersedes_id:
        old = db.get(Document, supersedes_id)
        if old and old.tender_id == tid:
            old.is_latest = False
    return doc


@router.get("/tenders/{tid}/documents")
def documents(tid: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return [row(d) for d in db.scalars(select(Document).where(Document.tender_id == tid).order_by(Document.doc_type, Document.id)).all()]


@router.post("/tenders/{tid}/documents")
async def upload_document(tid: int, file: UploadFile = File(...), doc_type: str = Form("other"), title: str = Form(""),
                          revision: str = Form("0"), supersedes_id: int | None = Form(None), issue_date: str | None = Form(None),
                          db: Session = Depends(get_db), u: User = Depends(require("documents.manage"))):
    tender_of(db, tid)
    data = await file.read()
    doc = store_document(db, tid, file, data, doc_type, title, revision, supersedes_id, u.id,
                         date.fromisoformat(issue_date) if issue_date else None)
    db.commit()
    return row(doc)


@router.patch("/documents/{did}")
def update_document(did: int, data: dict = Body(...), db: Session = Depends(get_db), _: User = Depends(require("documents.manage"))):
    d = apply(get_or_404(db, Document, did), data, ["doc_type", "title", "revision", "issue_date", "is_latest", "supersedes_id"])
    db.commit()
    return row(d)


@router.get("/documents/{did}/file")
def download(did: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    d = get_or_404(db, Document, did)
    return FileResponse(d.storage_path, filename=d.filename, media_type=d.mime or "application/octet-stream")


@router.get("/documents/{did}/pages")
def doc_pages(did: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    d = get_or_404(db, Document, did)
    return [{"page": p.page_no, "text": p.text} for p in d.page_texts]


@router.get("/documents/{did}/compare/{other}")
def compare(did: int, other: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """Addendum vs original — highlights changed, added and removed lines."""
    a, b = get_or_404(db, Document, other), get_or_404(db, Document, did)
    return {"original": row(a), "revised": row(b),
            "changes": compare_texts([p.text for p in a.page_texts], [p.text for p in b.page_texts])}


def tender_pages(db: Session, tid: int, doc_ids: list[int] | None = None):
    q = select(Document).where(Document.tender_id == tid, Document.is_latest.is_(True))
    if doc_ids:
        q = q.where(Document.id.in_(doc_ids))
    pages, scanned = [], []
    for d in db.scalars(q).all():
        if d.doc_type in ("site_photo", "quotation", "submission"):
            continue
        if d.text_status == "needs_ocr" and d.filename.lower().endswith(".pdf"):
            scanned.append({"file": d.filename, "document_id": d.id, "data": Path(d.storage_path).read_bytes()})
            continue
        for p in d.page_texts:
            if p.text.strip():
                pages.append({"file": d.filename, "page": p.page_no, "text": p.text, "document_id": d.id})
    return pages, scanned


# ---------------------------------------------------------------- AI tender analysis (steps 4–5)
@router.post("/tenders/{tid}/analyze")
def analyze(tid: int, data: dict = Body(default={}), db: Session = Depends(get_db), u: User = Depends(require("analysis.manage"))):
    tender_of(db, tid)
    pages, scanned = tender_pages(db, tid, data.get("document_ids"))
    if not pages and not scanned:
        raise HTTPException(400, "No readable documents — upload the tender documents first")
    try:
        out = ai.analyze_tender(pages, scanned)
    except ai.AIError as e:
        raise HTTPException(502, str(e))
    files = {p["file"]: p["document_id"] for p in pages} | {s["file"]: s["document_id"] for s in scanned}
    # replace previous pending suggestions of these kinds
    for old in db.scalars(select(AISuggestion).where(AISuggestion.tender_id == tid, AISuggestion.status == "pending",
                                                     AISuggestion.kind.in_(["summary_field", "risk", "rfi"]))).all():
        db.delete(old)
    created = 0
    for kind, key in (("summary_field", "summary"), ("risk", "risks"), ("rfi", "rfis")):
        for s in out.get(key, []):
            src = {"file": s.get("file"), "page": s.get("page"), "document_id": files.get(s.get("file")), "quote": s.get("quote")}
            db.add(AISuggestion(tender_id=tid, kind=kind, target=s.get("field", ""), payload=s, source=src,
                                confidence=float(s.get("confidence") or 0), engine=out.get("engine", "")))
            created += 1
    db.commit()
    return {"created": created, "engine": out.get("engine"), "notes": out.get("notes", [])}


@router.get("/tenders/{tid}/suggestions")
def suggestions(tid: int, status: str = "pending", kind: str | None = None, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    q = select(AISuggestion).where(AISuggestion.tender_id == tid)
    if status != "all":
        q = q.where(AISuggestion.status == status)
    if kind:
        q = q.where(AISuggestion.kind == kind)
    return [row(s) for s in db.scalars(q.order_by(AISuggestion.kind, AISuggestion.id)).all()]


DATE_FIELDS = {"site_visit_date", "rfi_deadline", "submission_date"}


@router.post("/suggestions/{sid}/decide")
def decide(sid: int, data: dict = Body(...), db: Session = Depends(get_db), u: User = Depends(require("analysis.manage"))):
    """accept | reject. An edited payload is recorded as 'edited' (counts as accepted for AI quality metrics)."""
    s = get_or_404(db, AISuggestion, sid)
    if s.status != "pending":
        raise HTTPException(409, "Already decided")
    action = data.get("action")
    payload = {**s.payload, **(data.get("payload") or {})}
    s.decided_by, s.decided_at = u.id, datetime.utcnow()
    if action == "reject":
        s.status = "rejected"
        db.commit()
        return row(s)
    s.status = "edited" if data.get("payload") else "accepted"
    t = db.get(Tender, s.tender_id)
    created = None
    if s.kind == "summary_field":
        summ = dict(t.summary or {})
        summ[s.target] = {"value": payload.get("value"), "numeric": payload.get("numeric"), "date": payload.get("date"),
                          "file": s.source.get("file"), "page": s.source.get("page"), "document_id": s.source.get("document_id"),
                          "approved_by": u.full_name or u.username}
        t.summary = summ
        if s.target in DATE_FIELDS and payload.get("date"):
            setattr(t, s.target, date.fromisoformat(payload["date"][:10]))
        if s.target == "duration" and payload.get("numeric"):
            t.duration_months = int(round(float(payload["numeric"])))
        if s.target == "bid_validity" and payload.get("numeric"):
            t.bid_validity_days = int(payload["numeric"])
        if s.target in ("owner", "consultant") and not getattr(t, s.target):
            val = str(payload.get("value", "")).split(":", 1)[-1].strip(" .")
            setattr(t, s.target, val[:200])
    elif s.kind == "risk":
        created = Risk(tender_id=t.id, description=payload["description"], category=payload.get("category", "other"),
                       probability_pct=payload.get("probability_pct") or 0, impact_amount=payload.get("impact_amount") or 0,
                       mitigation=payload.get("mitigation", ""), source_document_id=s.source.get("document_id"),
                       source_page=s.source.get("page"), origin="ai", approved=True, confidence=s.confidence)
    elif s.kind == "rfi":
        n = (db.scalar(select(func.max(RFI.number)).where(RFI.tender_id == t.id)) or 0) + 1
        created = RFI(tender_id=t.id, number=n, question=payload["question"], reference=payload.get("reference", ""),
                      source_document_id=s.source.get("document_id"), source_page=s.source.get("page"), origin="ai")
    if created is not None:
        db.add(created)
    db.commit()
    return {**row(s), "created": row(created) if created is not None else None}


# ---------------------------------------------------------------- risks & RFIs
RISK_FIELDS = ["description", "category", "probability_pct", "impact_amount", "mitigation", "include_in_contingency",
               "source_document_id", "source_page", "origin", "approved"]


@router.get("/tenders/{tid}/risks")
def risks(tid: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    out = []
    for r in db.scalars(select(Risk).where(Risk.tender_id == tid).order_by(Risk.id)).all():
        d = row(r)
        d["expected_value"] = float(r.probability_pct or 0) / 100 * float(r.impact_amount or 0)
        out.append(d)
    return out


@router.post("/tenders/{tid}/risks")
def create_risk(tid: int, data: dict = Body(...), db: Session = Depends(get_db), _: User = Depends(require("analysis.manage"))):
    r = apply(Risk(tender_id=tid), data, RISK_FIELDS)
    db.add(r)
    db.commit()
    return row(r)


@router.patch("/risks/{rid}")
def update_risk(rid: int, data: dict = Body(...), db: Session = Depends(get_db), _: User = Depends(require("analysis.manage"))):
    r = apply(get_or_404(db, Risk, rid), data, RISK_FIELDS)
    db.commit()
    return row(r)


@router.delete("/risks/{rid}")
def delete_risk(rid: int, db: Session = Depends(get_db), _: User = Depends(require("analysis.manage"))):
    db.delete(get_or_404(db, Risk, rid))
    db.commit()
    return {"ok": True}


RFI_FIELDS = ["question", "reference", "source_document_id", "source_page", "status", "answer", "answer_date",
              "pricing_impact", "impact_amount"]


@router.get("/tenders/{tid}/rfis")
def rfis(tid: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return [row(r) for r in db.scalars(select(RFI).where(RFI.tender_id == tid).order_by(RFI.number)).all()]


@router.post("/tenders/{tid}/rfis")
def create_rfi(tid: int, data: dict = Body(...), db: Session = Depends(get_db), _: User = Depends(require("analysis.manage"))):
    n = (db.scalar(select(func.max(RFI.number)).where(RFI.tender_id == tid)) or 0) + 1
    r = apply(RFI(tender_id=tid, number=n), data, RFI_FIELDS)
    db.add(r)
    db.commit()
    return row(r)


@router.patch("/rfis/{rid}")
def update_rfi(rid: int, data: dict = Body(...), db: Session = Depends(get_db), _: User = Depends(require("analysis.manage"))):
    r = apply(get_or_404(db, RFI, rid), data, RFI_FIELDS)
    db.commit()
    return row(r)


@router.get("/tenders/{tid}/rfis/letter")
def rfi_letter(tid: int, lang: str = "ar", db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    t = tender_of(db, tid)
    items = db.scalars(select(RFI).where(RFI.tender_id == tid, RFI.status == "draft").order_by(RFI.number)).all()
    if lang == "en":
        lines = [f"To: {t.consultant or t.owner or '...'}", f"Subject: Tender clarifications — {t.name} ({t.code})", "",
                 "Dear Sirs,", "We would be grateful for your clarification of the following points:", ""]
        lines += [f"{r.number}) {r.question}" + (f"  [Ref: {r.reference}]" if r.reference else "") for r in items]
        lines += ["", "Yours faithfully,"]
        return {"text": "\n".join(lines), "count": len(items)}
    lines = [f"السادة / {t.consultant or t.owner or '...'}", "تحية طيبة وبعد،",
             f"بالإشارة إلى مناقصة «{t.name}» ({t.code})، نرجو التكرم بإفادتنا بالاستيضاحات التالية:", ""]
    for r in items:
        lines.append(f"{r.number}) {r.question}" + (f"  [المرجع: {r.reference}]" if r.reference else ""))
    lines += ["", "وتفضلوا بقبول فائق الاحترام،"]
    return {"text": "\n".join(lines), "count": len(items)}


# ---------------------------------------------------------------- site visit (step 6)
@router.get("/tenders/{tid}/site-visit")
def get_site_visit(tid: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    t = tender_of(db, tid)
    sv = db.scalar(select(SiteVisit).where(SiteVisit.tender_id == tid))
    if not sv:
        tpl = (get_setting(db, "site_visit_templates") or {}).get(t.project_type, [])
        sv = SiteVisit(tender_id=tid, checklist=[{"key": c["key"], "label": c["ar"], "label_en": c["en"], "status": "", "notes": ""} for c in tpl])
        db.add(sv)
        db.commit()
    return row(sv)


@router.put("/tenders/{tid}/site-visit")
def put_site_visit(tid: int, data: dict = Body(...), db: Session = Depends(get_db), _: User = Depends(require("analysis.manage"))):
    sv = db.scalar(select(SiteVisit).where(SiteVisit.tender_id == tid)) or SiteVisit(tender_id=tid)
    apply(sv, data, ["visit_date", "attendees", "checklist", "summary"])
    db.add(sv)
    db.commit()
    return {**row(sv), "suggestions": ai.site_visit_suggestions(sv.checklist or [], sv.summary or "")}


@router.post("/tenders/{tid}/site-visit/photos")
async def site_photo(tid: int, file: UploadFile = File(...), caption: str = Form(""), lat: float | None = Form(None),
                     lng: float | None = Form(None), db: Session = Depends(get_db), u: User = Depends(require("analysis.manage"))):
    data = await file.read()
    doc = store_document(db, tid, file, data, "site_photo", caption or file.filename, user_id=u.id)
    sv = db.scalar(select(SiteVisit).where(SiteVisit.tender_id == tid)) or SiteVisit(tender_id=tid)
    sv.photos = [*(sv.photos or []), {"document_id": doc.id, "caption": caption, "lat": lat, "lng": lng}]
    db.add(sv)
    db.commit()
    return row(sv)


# ---------------------------------------------------------------- chat assistant
@router.post("/tenders/{tid}/chat")
def chat(tid: int, data: dict = Body(...), db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    pages, _s = tender_pages(db, tid)
    try:
        return ai.chat(data.get("question", ""), pages)
    except ai.AIError as e:
        raise HTTPException(502, str(e))


# ---------------------------------------------------------------- submission & post-tender (steps 19–20)
@router.put("/tenders/{tid}/submission")
def submission(tid: int, data: dict = Body(...), db: Session = Depends(get_db), u: User = Depends(require("proposal.manage"))):
    t = tender_of(db, tid)
    t.submission_checklist = data.get("checklist", t.submission_checklist)
    if data.get("mark_submitted"):
        if not all(x.get("done") for x in t.submission_checklist):
            raise HTTPException(409, "Complete the submission checklist first")
        if not db.scalar(select(Estimate.id).where(Estimate.tender_id == tid, Estimate.status == "approved")):
            raise HTTPException(409, "No approved estimate version")
        t.status = "submitted"
    db.commit()
    return row(t)


@router.put("/tenders/{tid}/result")
def result(tid: int, data: dict = Body(...), db: Session = Depends(get_db), u: User = Depends(require("proposal.manage"))):
    t = tender_of(db, tid)
    outcome = data.get("outcome")
    if outcome not in ("won", "lost", "cancelled"):
        raise HTTPException(422, "outcome must be won, lost or cancelled")
    t.result = {k: data.get(k) for k in ("outcome", "date", "our_price", "winner", "winning_price", "reasons", "lessons")}
    t.status = outcome
    for c in db.scalars(select(Competitor).where(Competitor.tender_id == tid)).all():
        db.delete(c)
    for c in data.get("competitors", []):
        if c.get("name") and c.get("price") not in (None, ""):
            db.add(apply(Competitor(tender_id=tid), c, ["name", "price", "rank", "notes"]))
    db.commit()
    return {**row(t), "competitors": [row(c) for c in db.scalars(select(Competitor).where(Competitor.tender_id == tid)).all()]}


@router.get("/tenders/{tid}/result")
def get_result(tid: int, db: Session = Depends(get_db), u: User = Depends(get_current_user)):
    t = tender_of(db, tid)
    comps = [row(c) for c in db.scalars(select(Competitor).where(Competitor.tender_id == tid).order_by(Competitor.price)).all()]
    ours = None
    est = db.scalars(select(Estimate).where(Estimate.tender_id == tid, Estimate.status == "approved").order_by(Estimate.version_no.desc())).first()
    if est and can(u, "markup.view"):
        ours = result_for(db, est)["summary"]["submitted_total"]
        for c in comps:
            c["diff_pct"] = (ours - c["price"]) / c["price"] * 100 if c["price"] else None
    return {"result": t.result, "competitors": comps, "our_total": ours}


@router.get("/kpis")
def kpis(db: Session = Depends(get_db), u: User = Depends(get_current_user)):
    rows = []
    for t in db.scalars(select(Tender).where(Tender.status.in_(["won", "lost"]))).all():
        comps = db.scalars(select(Competitor).where(Competitor.tender_id == t.id)).all()
        rows.append({"code": t.code, "name": t.name, "type": t.project_type, "status": t.status,
                     "our_price": (t.result or {}).get("our_price") if can(u, "markup.view") else None,
                     "lowest_competitor": min((float(c.price) for c in comps), default=None) if can(u, "markup.view") else None,
                     "reasons": (t.result or {}).get("reasons"), "lessons": (t.result or {}).get("lessons")})
    by_type = {}
    for r in rows:
        bt = by_type.setdefault(r["type"], {"won": 0, "lost": 0})
        bt[r["status"]] += 1
    return {"tenders": rows, "by_type": {k: {**v, "win_rate": v["won"] / (v["won"] + v["lost"]) * 100} for k, v in by_type.items()}}
