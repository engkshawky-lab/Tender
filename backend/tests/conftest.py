import os
import sys
import tempfile
from pathlib import Path

_tmp = tempfile.mkdtemp(prefix="tp-test-")
os.environ.setdefault("TP_DATA_DIR", _tmp)
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_tmp}/test.db")
os.environ["TP_AI_ENABLED"] = "off"
os.environ.setdefault("TP_FRONTEND_DIST", str(Path(_tmp) / "nodist"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
SAMPLES = Path(__file__).resolve().parents[2] / "samples"
