from datetime import date, datetime
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import Boolean, Date, DateTime, Integer, Numeric, inspect
from sqlalchemy.orm import Session

from ..auth import can
from ..models import Estimate, Tender, User


def plain(v):
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    if isinstance(v, dict):
        return {str(k): plain(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [plain(x) for x in v]
    return v


def row(obj, exclude=()) -> dict:
    if obj is None:
        return None
    return {c.key: plain(getattr(obj, c.key)) for c in inspect(obj).mapper.column_attrs if c.key not in exclude}


def _coerce(col, v):
    if v is None or v == "":
        return None if col.nullable else (0 if isinstance(col.type, (Numeric, Integer)) else v)
    t = col.type
    if isinstance(t, Boolean):
        return bool(v)
    if isinstance(t, DateTime):
        return datetime.fromisoformat(v) if isinstance(v, str) else v
    if isinstance(t, Date):
        return date.fromisoformat(v[:10]) if isinstance(v, str) else v
    if isinstance(t, Numeric):
        return Decimal(str(v))
    if isinstance(t, Integer):
        return int(v)
    return v


def apply(obj, data: dict, fields: list[str]):
    cols = {c.key: c for c in obj.__table__.columns}
    for f in fields:
        if f in data:
            setattr(obj, f, _coerce(cols[f], data[f]) if f in cols else data[f])
    return obj


def get_or_404(db: Session, model, oid):
    obj = db.get(model, oid)
    if obj is None:
        raise HTTPException(404, f"{model.__name__} {oid} not found")
    return obj


def editable_estimate(est: Estimate):
    if est.status not in ("draft", "rejected"):
        raise HTTPException(409, f"Estimate V{est.version_no} is {est.status} and locked — create a new version to change it")


PRICE_KEYS = {"profit", "markup_pct", "margin_on_price_pct", "price", "total_excl_vat", "submitted_total", "rounding_diff",
              "vat", "vat_total", "total_incl_vat", "spread_factor", "bonds_insurance", "bonds_breakdown",
              "taxes_in_price", "taxes_in_price_breakdown", "cost_before_profit", "finance", "peak_cash_deficit"}


def redact(res: dict, user: User) -> dict:
    """Spec rule 8: markup and final totals are visible to management only (permission markup.view)."""
    if can(user, "markup.view") or not res:
        return res
    out = dict(res)
    out["summary"] = {k: v for k, v in res["summary"].items() if k not in PRICE_KEYS}
    out["items"] = [{k: v for k, v in r.items() if k not in ("final_rate", "amount", "factor", "override")} for r in res["items"]]
    out["cash_flow"] = []
    out["params"] = {k: v for k, v in (res.get("params") or {}).items() if k != "markup_pct"}
    out["redacted"] = True
    return out


def tender_of(db: Session, tid: int) -> Tender:
    return get_or_404(db, Tender, tid)
