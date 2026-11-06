"""Runtime configuration (environment variables only — business ratios live in the Settings table)."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("TP_DATA_DIR", BASE_DIR / "data"))
UPLOAD_DIR = DATA_DIR / "uploads"
DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR / 'tender.db'}")
def _secret() -> str:
    """TP_SECRET_KEY, or a random key generated once and kept in the data directory."""
    if os.getenv("TP_SECRET_KEY"):
        return os.environ["TP_SECRET_KEY"]
    f = DATA_DIR / "secret.key"
    if not f.exists():
        import secrets
        f.write_text(secrets.token_urlsafe(48))
        f.chmod(0o600)
    return f.read_text().strip()


SECRET_KEY = _secret()
TOKEN_HOURS = int(os.getenv("TP_TOKEN_HOURS", "12"))

# AI: when ANTHROPIC_API_KEY is not set (and TP_AI_ENABLED is not "on") the platform
# falls back to the offline rule-based extractor so every workflow still runs.
AI_MODEL = os.getenv("TP_AI_MODEL", "claude-opus-5-5")
AI_ENABLED = os.getenv("TP_AI_ENABLED", "auto")  # auto | on | off

FRONTEND_DIST = Path(os.getenv("TP_FRONTEND_DIST", BASE_DIR.parent / "frontend" / "dist"))
