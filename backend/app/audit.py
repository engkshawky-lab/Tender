"""Automatic audit trail (spec rule 5): every insert / update / delete records who changed what and when."""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import event, inspect
from sqlalchemy.orm import Session

from .db import current_user_id
from .models import AISuggestion, AuditLog, DocumentPage

SKIP = {AuditLog, DocumentPage, AISuggestion}
SKIP_FIELDS = {"password_hash", "result"}


def _plain(v):
    if isinstance(v, Decimal):
        return str(v)
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    return v


def _pk(obj) -> str:
    ident = inspect(obj).identity
    return "/".join(str(x) for x in ident) if ident else str(getattr(obj, "id", ""))


def _tender_id(obj):
    tid = getattr(obj, "tender_id", None)
    if tid is None and obj.__class__.__name__ == "Tender":
        tid = obj.id
    return tid


@event.listens_for(Session, "after_flush")
def _audit(session: Session, _ctx):
    uid = session.info.get("user_id") or current_user_id.get()
    entries = []
    for obj in session.new:
        if type(obj) in SKIP:
            continue
        cols = {c.key: _plain(getattr(obj, c.key)) for c in inspect(obj).mapper.column_attrs if c.key not in SKIP_FIELDS}
        entries.append(AuditLog(user_id=uid, action="create", entity=obj.__tablename__, entity_id=_pk(obj),
                                tender_id=_tender_id(obj), changes=cols))
    for obj in session.dirty:
        if type(obj) in SKIP or not session.is_modified(obj):
            continue
        st = inspect(obj)
        changes = {}
        for attr in st.mapper.column_attrs:
            if attr.key in SKIP_FIELDS:
                continue
            hist = st.attrs[attr.key].history
            if hist.has_changes():
                old = hist.deleted[0] if hist.deleted else None
                new = hist.added[0] if hist.added else None
                if _plain(old) != _plain(new):
                    changes[attr.key] = [_plain(old), _plain(new)]
        if changes:
            entries.append(AuditLog(user_id=uid, action="update", entity=obj.__tablename__, entity_id=_pk(obj),
                                    tender_id=_tender_id(obj), changes=changes))
    for obj in session.deleted:
        if type(obj) in SKIP:
            continue
        entries.append(AuditLog(user_id=uid, action="delete", entity=obj.__tablename__, entity_id=_pk(obj),
                                tender_id=_tender_id(obj), changes={}))
    if entries:
        # add_all inside after_flush is persisted by the next flush in the same transaction
        session.add_all(entries)
