"""Auth, users & permissions, settings, master data (cost codes, suppliers, resources, templates), audit log."""
from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..auth import (PERMISSIONS, ROLES, get_current_user, hash_password, make_token, require, user_permissions,
                    verify_password)
from ..db import get_db
from ..models import AuditLog, BuildUpTemplate, CostCode, Resource, Setting, User
from ..services.defaults import DEFAULT_SETTINGS, PROJECT_TYPES, SCOPES, DOC_TYPES
from ..services.estimating import get_setting
from .common import apply, get_or_404, row

router = APIRouter(prefix="/api")


# ---------------------------------------------------------------- auth
@router.post("/auth/login")
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    u = db.scalar(select(User).where(User.username == form.username))
    if not u or not u.is_active or not verify_password(form.password, u.password_hash):
        raise HTTPException(401, "Wrong username or password")
    return {"access_token": make_token(u), "token_type": "bearer"}


def user_out(u: User) -> dict:
    d = row(u, exclude=("password_hash",))
    d["permissions"] = sorted(user_permissions(u))
    return d


@router.get("/auth/me")
def me(u: User = Depends(get_current_user)):
    return user_out(u)


@router.get("/meta")
def meta(_: User = Depends(get_current_user)):
    return {"roles": ROLES, "permissions": PERMISSIONS, "project_types": PROJECT_TYPES, "scopes": SCOPES,
            "doc_types": DOC_TYPES}


# ---------------------------------------------------------------- users
@router.get("/users")
def users(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return [user_out(u) for u in db.scalars(select(User).order_by(User.id)).all()]


USER_FIELDS = ["full_name", "email", "roles", "extra_permissions", "revoked_permissions", "is_active"]


@router.post("/users")
def create_user(data: dict = Body(...), db: Session = Depends(get_db), _: User = Depends(require("users.manage"))):
    if not data.get("username") or not data.get("password"):
        raise HTTPException(422, "username and password are required")
    if db.scalar(select(User).where(User.username == data["username"])):
        raise HTTPException(409, "Username already exists")
    u = apply(User(username=data["username"], password_hash=hash_password(data["password"])), data, USER_FIELDS)
    db.add(u)
    db.commit()
    return user_out(u)


@router.patch("/users/{uid}")
def update_user(uid: int, data: dict = Body(...), db: Session = Depends(get_db), _: User = Depends(require("users.manage"))):
    u = get_or_404(db, User, uid)
    apply(u, data, USER_FIELDS)
    if data.get("password"):
        u.password_hash = hash_password(data["password"])
    db.commit()
    return user_out(u)


@router.post("/auth/password")
def change_password(data: dict = Body(...), db: Session = Depends(get_db), u: User = Depends(get_current_user)):
    if not verify_password(data.get("old", ""), u.password_hash):
        raise HTTPException(400, "Old password is wrong")
    u.password_hash = hash_password(data["new"])
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- settings
@router.get("/settings")
def get_settings(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return {k: get_setting(db, k) for k in DEFAULT_SETTINGS}


@router.put("/settings/{key}")
def put_setting(key: str, value=Body(...), db: Session = Depends(get_db), _: User = Depends(require("settings.manage"))):
    if key not in DEFAULT_SETTINGS:
        raise HTTPException(404, "Unknown setting")
    s = db.get(Setting, key) or Setting(key=key)
    s.value = value
    db.add(s)
    db.commit()
    return {"key": key, "value": s.value}


# ---------------------------------------------------------------- cost codes
CC_FIELDS = ["code", "name_ar", "name_en", "parent_id", "level", "project_type", "unit", "keywords"]


@router.get("/cost-codes")
def cost_codes(project_type: str | None = None, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    q = select(CostCode).order_by(CostCode.code)
    if project_type:
        q = q.where(CostCode.project_type.in_([project_type, "common"]))
    return [row(c) for c in db.scalars(q).all()]


@router.post("/cost-codes")
def create_cc(data: dict = Body(...), db: Session = Depends(get_db), _: User = Depends(require("library.manage"))):
    c = apply(CostCode(), data, CC_FIELDS)
    db.add(c)
    db.commit()
    return row(c)


@router.patch("/cost-codes/{cid}")
def update_cc(cid: int, data: dict = Body(...), db: Session = Depends(get_db), _: User = Depends(require("library.manage"))):
    c = apply(get_or_404(db, CostCode, cid), data, CC_FIELDS)
    db.commit()
    return row(c)


# ---------------------------------------------------------------- resources
RES_FIELDS = ["code", "name", "kind", "unit", "price", "currency", "price_date", "source", "supplier_id", "cost_code_id",
              "productivity", "waste_pct", "notes"]


@router.get("/resources")
def resources(q: str | None = None, kind: str | None = None, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    stmt = select(Resource).order_by(Resource.kind, Resource.name)
    if kind:
        stmt = stmt.where(Resource.kind == kind)
    if q:
        stmt = stmt.where(or_(Resource.name.ilike(f"%{q}%"), Resource.code.ilike(f"%{q}%")))
    return [row(r) for r in db.scalars(stmt).all()]


@router.post("/resources")
def create_resource(data: dict = Body(...), db: Session = Depends(get_db), _: User = Depends(require("library.manage"))):
    r = apply(Resource(), data, RES_FIELDS)
    db.add(r)
    db.commit()
    return row(r)


@router.patch("/resources/{rid}")
def update_resource(rid: int, data: dict = Body(...), db: Session = Depends(get_db), _: User = Depends(require("library.manage"))):
    r = apply(get_or_404(db, Resource, rid), data, RES_FIELDS)
    db.commit()
    return row(r)


@router.delete("/resources/{rid}")
def delete_resource(rid: int, db: Session = Depends(get_db), _: User = Depends(require("library.manage"))):
    db.delete(get_or_404(db, Resource, rid))
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- build-up templates
@router.get("/templates")
def templates(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return [row(t) for t in db.scalars(select(BuildUpTemplate).order_by(BuildUpTemplate.name)).all()]


@router.post("/templates")
def create_template(data: dict = Body(...), db: Session = Depends(get_db), _: User = Depends(require("library.manage"))):
    t = apply(BuildUpTemplate(), data, ["name", "unit", "cost_code_id", "lines"])
    db.add(t)
    db.commit()
    return row(t)


# ---------------------------------------------------------------- audit
@router.get("/audit")
def audit(tender_id: int | None = None, entity: str | None = None, limit: int = 200,
          db: Session = Depends(get_db), _: User = Depends(require("audit.view"))):
    q = select(AuditLog).order_by(AuditLog.id.desc()).limit(min(limit, 2000))
    if tender_id:
        q = q.where(AuditLog.tender_id == tender_id)
    if entity:
        q = q.where(AuditLog.entity == entity)
    names = {u.id: u.full_name or u.username for u in db.scalars(select(User)).all()}
    return [{**row(a), "user": names.get(a.user_id, "system")} for a in db.scalars(q).all()]
