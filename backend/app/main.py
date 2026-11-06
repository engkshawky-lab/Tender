import warnings

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import exc as sa_exc

from . import audit  # noqa: F401  (registers the audit-log listener)
from .config import FRONTEND_DIST
from .db import Base, SessionLocal, engine
from .engine.pricing import PricingError
from .routers import admin, boq, estimates, procurement, references, tenders, vendors
from .services.seed import seed_base

warnings.filterwarnings("ignore", category=sa_exc.SAWarning, message=".*Decimal.*")

app = FastAPI(title="Tender Pricing Platform", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_methods=["*"], allow_headers=["*"])

for r in (admin.router, tenders.router, boq.router, procurement.router, estimates.router, references.router, vendors.router):
    app.include_router(r)


@app.exception_handler(PricingError)
def _pricing_error(_req: Request, exc: PricingError):
    return JSONResponse(status_code=422, content={"detail": str(exc)})


@app.on_event("startup")
def _startup():
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed_base(db)


@app.get("/api/health")
def health():
    from .services.ai import engine_name
    return {"ok": True, "ai": engine_name()}


if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        f = FRONTEND_DIST / path
        if path and f.is_file():
            return FileResponse(f)
        return FileResponse(FRONTEND_DIST / "index.html")
