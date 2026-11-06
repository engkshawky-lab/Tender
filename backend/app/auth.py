"""Authentication (JWT) and role/permission model.
A user may hold several roles (commercial review); permissions = union of role permissions
+ extra_permissions − revoked_permissions, so access can be tuned per user."""
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from .config import SECRET_KEY, TOKEN_HOURS
from .db import current_user_id, get_db
from .models import User

PERMISSIONS = {
    "tender.manage": "Register tenders, dates, assignments",
    "gonogo.decide": "Take the Go / No-Go decision",
    "documents.manage": "Upload and classify documents",
    "analysis.manage": "Tender summary, risks, RFIs, site visit",
    "boq.edit": "Import / edit the BOQ, packages, cost codes",
    "pricing.edit": "Rate build-up, indirects, contingency",
    "procurement.manage": "Suppliers, RFQs, quotations, comparison",
    "schedule.edit": "Preliminary schedule & cash-flow inputs",
    "markup.view": "See markup, profit and final prices",
    "markup.edit": "Set markup and price spreading",
    "estimate.approve": "Approve / reject an estimate version",
    "proposal.manage": "Submission checklist, exports, results",
    "library.manage": "Resource library, templates, cost codes, price references",
    "vendors.approve": "Approve / suspend / blacklist vendors in the approved vendor list",
    "settings.manage": "Company settings (taxes, weights, ratios)",
    "users.manage": "Users and permissions",
    "audit.view": "Read the audit log",
}

ROLES = {
    "admin": list(PERMISSIONS),
    "tender_manager": ["tender.manage", "documents.manage", "analysis.manage", "proposal.manage", "schedule.edit", "audit.view"],
    "estimator": ["boq.edit", "pricing.edit", "analysis.manage", "documents.manage", "library.manage"],
    "procurement": ["procurement.manage", "library.manage", "documents.manage"],
    "planner": ["schedule.edit"],
    "technical_office": ["documents.manage", "analysis.manage", "proposal.manage"],
    "management": ["vendors.approve", "gonogo.decide", "markup.view", "markup.edit", "estimate.approve", "audit.view", "tender.manage"],
}


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode(), hashed.encode())
    except ValueError:
        return False


def user_permissions(u: User) -> set[str]:
    perms: set[str] = set()
    for r in u.roles or []:
        perms.update(ROLES.get(r, []))
    perms.update(u.extra_permissions or [])
    perms.difference_update(u.revoked_permissions or [])
    return perms


def make_token(u: User) -> str:
    exp = datetime.now(timezone.utc) + timedelta(hours=TOKEN_HOURS)
    return jwt.encode({"sub": str(u.id), "exp": exp}, SECRET_KEY, algorithm="HS256")


oauth2 = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def get_current_user(token: str | None = Depends(oauth2), db: Session = Depends(get_db)) -> User:
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    try:
        data = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    u = db.get(User, int(data["sub"]))
    if not u or not u.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User inactive")
    current_user_id.set(u.id)
    db.info["user_id"] = u.id  # read by the audit listener (same session for the whole request)
    return u


def require(*perms: str):
    def dep(u: User = Depends(get_current_user)) -> User:
        have = user_permissions(u)
        missing = [p for p in perms if p not in have]
        if missing:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Missing permission: {', '.join(missing)}")
        return u
    return dep


def require_any(*perms: str):
    def dep(u: User = Depends(get_current_user)) -> User:
        if not set(perms) & user_permissions(u):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Missing permission: one of {', '.join(perms)}")
        return u
    return dep


def can(u: User, perm: str) -> bool:
    return perm in user_permissions(u)
