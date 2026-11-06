"""Text extraction with page numbers, so every extracted term can cite file + page."""
import difflib
import io
from pathlib import Path

PAGE_CHARS = 3000  # DOCX has no physical pages; group paragraphs into ~3000-char "sections"


def extract_pages(filename: str, data: bytes) -> tuple[list[str], str]:
    """Return (page_texts, status). status: extracted | needs_ocr | none | failed"""
    ext = Path(filename).suffix.lower()
    try:
        if ext == ".pdf":
            import pdfplumber
            pages = []
            with pdfplumber.open(io.BytesIO(data)) as pdf:
                for pg in pdf.pages:
                    pages.append(pg.extract_text() or "")
            text_chars = sum(len(p.strip()) for p in pages)
            if pages and text_chars < 20 * len(pages):
                return pages, "needs_ocr"  # scanned PDF — the AI reads it as a document (Arabic/English OCR)
            return pages, "extracted"
        if ext == ".docx":
            from docx import Document
            doc = Document(io.BytesIO(data))
            parts = [p.text for p in doc.paragraphs if p.text.strip()]
            for t in doc.tables:
                for row in t.rows:
                    parts.append(" | ".join(c.text.strip() for c in row.cells))
            pages, cur = [], ""
            for p in parts:
                if len(cur) + len(p) > PAGE_CHARS and cur:
                    pages.append(cur)
                    cur = ""
                cur += p + "\n"
            if cur:
                pages.append(cur)
            return pages, "extracted" if pages else "none"
        if ext in (".xlsx", ".xlsm"):
            from openpyxl import load_workbook
            wb = load_workbook(io.BytesIO(data), data_only=True, read_only=True)
            pages = []
            for ws in wb.worksheets:
                lines = []
                for row in ws.iter_rows(values_only=True):
                    vals = [str(v) for v in row if v not in (None, "")]
                    if vals:
                        lines.append(" | ".join(vals))
                pages.append(f"[{ws.title}]\n" + "\n".join(lines))
            return pages, "extracted"
        if ext in (".txt", ".csv", ".md", ".eml"):
            return [data.decode("utf-8", errors="replace")], "extracted"
        if ext in (".png", ".jpg", ".jpeg", ".webp", ".gif", ".tif", ".tiff"):
            return [], "needs_ocr"
        return [], "none"
    except Exception:  # noqa: BLE001 - a broken file must not break the upload
        return [], "failed"


def compare_texts(old_pages: list[str], new_pages: list[str]) -> list[dict]:
    """Deterministic addendum-vs-original comparison: changed / added / removed lines."""
    old = [ln.strip() for p in old_pages for ln in p.splitlines() if ln.strip()]
    new = [ln.strip() for p in new_pages for ln in p.splitlines() if ln.strip()]
    out = []
    sm = difflib.SequenceMatcher(a=old, b=new, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        out.append({"change": {"replace": "changed", "delete": "removed", "insert": "added"}[tag],
                    "old": old[i1:i2], "new": new[j1:j2]})
    return out
