"""Excel first (spec rule 6): import the owner's BOQ and write prices back into the *same* workbook,
so numbering, merged cells, sections and formatting are preserved."""
import io
from dataclasses import dataclass, field

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .textnorm import normalize, to_number

HEADER_KEYS = {
    "ref": ["item no", "item", "no.", "no", "ref", "رقم البند", "رقم", "م", "البند", "بند", "مسلسل", "s.n", "sn"],
    "desc": ["description", "desc", "وصف الاعمال", "بيان الاعمال", "الوصف", "وصف", "بيان", "الاعمال", "specification"],
    "unit": ["unit", "uom", "الوحده", "وحده", "الوحدة", "وحدة"],
    "qty": ["quantity", "qty", "الكميه", "كميه", "الكمية", "كمية"],
    "rate": ["unit rate", "unit price", "rate", "price", "سعر الوحده", "الفئه", "فئه", "السعر", "سعر"],
    "amount": ["amount", "total", "total price", "الاجمالي", "اجمالي", "القيمه", "قيمه", "الجمله", "جمله"],
}
FIELD_PRIORITY = {"desc": 0, "qty": 1, "unit": 2, "rate": 3, "amount": 4, "ref": 5}
TOTAL_WORDS = ["total", "sub total", "subtotal", "carried", "brought forward", "الاجمالي", "اجمالي", "المجموع", "مجموع", "جمله", "يرحل", "ما قبله"]
WORDS_MARKERS = ["كتابه", "words", "بالحروف"]


def _match(cell_text: str, keys: list[str]) -> int:
    t = normalize(cell_text)
    if not t or any(m in t for m in WORDS_MARKERS):
        return 0
    best = 0
    for k in keys:
        kn = normalize(k)
        if t == kn:
            best = max(best, 3)
        elif len(kn) > 2 and kn in t:
            best = max(best, 2)
    return best


def detect_header(ws, scan_rows: int = 40):
    """Return (header_row, {field: column_index}) or (None, {})."""
    best = (0, None, {})
    for r in range(1, min(ws.max_row, scan_rows) + 1):
        cols: dict[str, tuple[int, int]] = {}
        for c in range(1, min(ws.max_column, 30) + 1):
            v = ws.cell(r, c).value
            if v is None or isinstance(v, (int, float)):
                continue
            for f, keys in HEADER_KEYS.items():
                s = _match(str(v), keys)
                if s and (f not in cols or s > cols[f][1]):
                    if f == "ref" and "desc" in cols and cols["desc"][0] == c:
                        continue
                    cols[f] = (c, s)
        # a column can only be one field: keep the strongest claim
        used: dict[int, str] = {}
        for f, (c, s) in sorted(cols.items(), key=lambda kv: (-kv[1][1], FIELD_PRIORITY[kv[0]])):
            if c not in used:
                used[c] = f
        final = {f: c for c, f in used.items()}
        score = len(final) + (2 if "desc" in final else 0) + (2 if "qty" in final else 0)
        if "desc" in final and "qty" in final and score > best[0]:
            best = (score, r, final)
    return best[1], best[2]


@dataclass
class ParsedRow:
    sheet: str
    row: int
    ref: str
    description: str
    unit: str
    quantity: float | None
    is_section: bool
    section: str = ""
    rate: float | None = None


@dataclass
class ParsedBoq:
    rows: list[ParsedRow] = field(default_factory=list)
    mapping: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def _cell(ws, r, c):
    if not c:
        return None
    return ws.cell(r, c).value


def _is_total(desc: str) -> bool:
    t = normalize(desc)
    return any(t.startswith(normalize(w)) for w in TOTAL_WORDS) or t in (normalize(w) for w in TOTAL_WORDS)


def parse_boq(data: bytes, mapping_override: dict | None = None) -> ParsedBoq:
    wb = load_workbook(io.BytesIO(data), data_only=True)
    out = ParsedBoq()
    for ws in wb.worksheets:
        if mapping_override and ws.title in mapping_override:
            hdr = mapping_override[ws.title]["header_row"]
            cols = mapping_override[ws.title]["cols"]
        else:
            hdr, cols = detect_header(ws)
        if not hdr:
            continue
        out.mapping[ws.title] = {"header_row": hdr, "cols": cols}
        section = ""
        buffer: list[tuple[int, str, str]] = []  # (row, ref, desc) text-only rows

        def flush_sections():
            nonlocal section
            for (br, bref, bdesc) in buffer:
                section = bdesc.strip()
                out.rows.append(ParsedRow(ws.title, br, bref, bdesc.strip(), "", None, True, section))
            buffer.clear()

        for r in range(hdr + 1, ws.max_row + 1):
            ref = _cell(ws, r, cols.get("ref"))
            desc = _cell(ws, r, cols.get("desc"))
            unit = _cell(ws, r, cols.get("unit"))
            qty = to_number(_cell(ws, r, cols.get("qty")))
            rate = to_number(_cell(ws, r, cols.get("rate")))
            ref_s = "" if ref is None else str(ref).strip()
            if isinstance(ref, float) and ref.is_integer():
                ref_s = str(int(ref))
            desc_s = "" if desc is None else str(desc).strip()
            unit_s = "" if unit is None else str(unit).strip()
            if not desc_s and not ref_s and qty is None:
                continue
            if desc_s and _is_total(desc_s) and not unit_s:
                continue
            if qty is None and not unit_s:
                if desc_s:
                    buffer.append((r, ref_s, desc_s))
                continue
            # an item row
            if not ref_s and buffer:
                # description started on earlier rows (multi-row item): take rows from the last one that carries a ref
                start = max((i for i, b in enumerate(buffer) if b[1]), default=0)
                head = buffer[start:]
                del buffer[start:]
                flush_sections()
                ref_s = head[0][1]
                desc_s = "\n".join([b[2] for b in head] + ([desc_s] if desc_s else []))
            else:
                flush_sections()
            if not desc_s:
                out.warnings.append(f"{ws.title}!{r}: item without description")
            out.rows.append(ParsedRow(ws.title, r, ref_s, desc_s, unit_s, qty, False, section, rate))
        flush_sections()
    if not out.mapping:
        out.warnings.append("No BOQ header found (need at least Description and Quantity columns)")
    return out


def _top_left(ws, row, col):
    for rng in ws.merged_cells.ranges:
        if rng.min_row <= row <= rng.max_row and rng.min_col <= col <= rng.max_col:
            return rng.min_row, rng.min_col
    return row, col


def export_priced_owner_format(original: bytes, mapping: dict, priced: list[dict]) -> bytes:
    """priced: [{sheet, row, rate, amount}] → original workbook with rate/amount filled in."""
    wb = load_workbook(io.BytesIO(original))
    for p in priced:
        if p["sheet"] not in wb.sheetnames or not p.get("row"):
            continue
        ws = wb[p["sheet"]]
        cols = mapping.get(p["sheet"], {}).get("cols", {})
        rc, ac = cols.get("rate"), cols.get("amount")
        if rc:
            r, c = _top_left(ws, p["row"], rc)
            ws.cell(r, c).value = float(p["rate"])
        if ac:
            r, c = _top_left(ws, p["row"], ac)
            cur = ws.cell(r, c).value
            if not (isinstance(cur, str) and cur.startswith("=")):
                ws.cell(r, c).value = float(p["amount"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------- generated workbooks
HDR_FILL = PatternFill("solid", fgColor="1F3A5F")
HDR_FONT = Font(bold=True, color="FFFFFF")
SEC_FILL = PatternFill("solid", fgColor="E8EEF5")


def _sheet(wb, title, headers, rows, rtl=True, widths=None):
    ws = wb.create_sheet(title)
    ws.sheet_view.rightToLeft = rtl
    ws.append(headers)
    for c in range(1, len(headers) + 1):
        cell = ws.cell(1, c)
        cell.fill, cell.font = HDR_FILL, HDR_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for row in rows:
        ws.append(row)
    for i, w in enumerate(widths or [], start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "A2"
    return ws


def build_workbook(sheets: list[dict]) -> bytes:
    wb = Workbook()
    wb.remove(wb.active)
    for s in sheets:
        ws = _sheet(wb, s["title"][:31], s["headers"], s["rows"], s.get("rtl", True), s.get("widths"))
        for r in s.get("section_rows", []):
            for c in range(1, len(s["headers"]) + 1):
                ws.cell(r + 2, c).fill = SEC_FILL
                ws.cell(r + 2, c).font = Font(bold=True)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


RFQ_ID_HEADER = "ID"


def build_rfq(tender: dict, package: dict, items: list[dict]) -> bytes:
    """Request-for-quotation workbook per package. Suppliers fill column F; the file is read back by read_rfq()."""
    wb = Workbook()
    ws = wb.active
    ws.title = "RFQ"
    ws.sheet_view.rightToLeft = True
    meta = [("المناقصة / Tender", f"{tender['code']} — {tender['name']}"),
            ("الحزمة / Package", package["name"]),
            ("النطاق / Scope", package["scope_label"]),
            ("المورد / Supplier", ""), ("العملة / Currency", tender.get("currency", "EGP")),
            ("صلاحية العرض حتى / Valid until", ""), ("مدة التوريد (يوم) / Lead time (days)", ""),
            ("شروط الدفع / Payment terms", ""), ("الاستثناءات / Exclusions", "")]
    for i, (k, v) in enumerate(meta, start=1):
        ws.cell(i, 1, k).font = Font(bold=True)
        ws.cell(i, 2, v)
    start = len(meta) + 2
    headers = [RFQ_ID_HEADER, "رقم البند / Ref", "الوصف / Description", "الوحدة / Unit", "الكمية / Qty",
               "سعر الوحدة / Unit rate", "الإجمالي / Amount", "ملاحظات / Remarks"]
    for c, h in enumerate(headers, start=1):
        cell = ws.cell(start, c, h)
        cell.fill, cell.font = HDR_FILL, HDR_FONT
    for i, it in enumerate(items, start=start + 1):
        ws.cell(i, 1, it["id"])
        ws.cell(i, 2, it["item_ref"])
        ws.cell(i, 3, it["description"]).alignment = Alignment(wrap_text=True)
        ws.cell(i, 4, it["unit"])
        ws.cell(i, 5, float(it["quantity"]))
        ws.cell(i, 7, f"=E{i}*F{i}")
    for col, w in zip("ABCDEFGH", (6, 10, 60, 8, 10, 14, 16, 25)):
        ws.column_dimensions[col].width = w
    ws.column_dimensions["A"].hidden = True
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def read_rfq(data: bytes) -> dict:
    wb = load_workbook(io.BytesIO(data), data_only=True)
    ws = wb.active
    meta, lines, header_row = {}, [], None
    for r in range(1, min(ws.max_row, 30) + 1):
        if ws.cell(r, 1).value == RFQ_ID_HEADER:
            header_row = r
            break
        k, v = ws.cell(r, 1).value, ws.cell(r, 2).value
        if k:
            meta[str(k).split("/")[-1].strip().lower()] = v
    if not header_row:
        raise ValueError("Not an RFQ template generated by the platform")
    for r in range(header_row + 1, ws.max_row + 1):
        iid = ws.cell(r, 1).value
        if iid is None:
            continue
        lines.append({"boq_item_id": int(iid), "unit_rate": to_number(ws.cell(r, 6).value),
                      "remarks": ws.cell(r, 8).value or ""})
    return {"meta": meta, "lines": lines}
