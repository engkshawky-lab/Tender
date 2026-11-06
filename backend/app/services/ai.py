"""AI layer — reads, extracts, suggests; never calculates (spec rule 1).

Every output carries its source (file + page) and a confidence (rule 2); callers store results as *unapproved*
suggestions that a human accepts (rule 3). With an API key the platform uses Claude; without one it falls back
to a deterministic Arabic/English rule-based extractor so the full workflow remains usable offline.

Data note (rule 8): Anthropic's commercial API terms state customer content is not used to train models —
confirm the current terms in writing before go-live."""
import base64
import json
import os
import re
from datetime import date

from ..config import AI_ENABLED, AI_MODEL
from .textnorm import TfIdfIndex, normalize, to_number


class AIError(RuntimeError):
    pass


def ai_available() -> bool:
    if AI_ENABLED == "off":
        return False
    if AI_ENABLED == "on":
        return True
    return bool(os.getenv("ANTHROPIC_API_KEY"))


def engine_name() -> str:
    return AI_MODEL if ai_available() else "offline-rules"


SUMMARY_FIELDS = {
    "owner": ("المالك", "Owner"),
    "consultant": ("الاستشاري", "Consultant"),
    "scope": ("نطاق العمل", "Scope of work"),
    "duration": ("مدة التنفيذ", "Contract duration"),
    "delay_penalty": ("غرامة التأخير", "Delay penalty"),
    "advance_payment": ("الدفعة المقدمة", "Advance payment"),
    "retention": ("نسبة الاستقطاع", "Retention"),
    "payment_terms": ("شروط ومدد الدفع", "Payment terms"),
    "bid_bond": ("التأمين الابتدائي", "Bid bond"),
    "performance_bond": ("التأمين النهائي / خطاب الضمان", "Performance bond"),
    "insurance": ("التأمينات", "Insurance"),
    "price_escalation": ("بند فروق الأسعار", "Price escalation"),
    "currency": ("العملة", "Currency"),
    "bid_validity": ("مدة صلاحية العرض", "Bid validity"),
    "approved_vendors": ("الموردين المعتمدين", "Approved vendors"),
    "maintenance_period": ("فترة الضمان والصيانة", "Defects liability period"),
    "site_visit_date": ("موعد زيارة الموقع", "Site visit date"),
    "rfi_deadline": ("آخر موعد للاستفسارات", "Clarification deadline"),
    "submission_date": ("موعد التقديم", "Submission date"),
}
RISK_CATEGORIES = ["contractual", "financial", "technical", "schedule", "site", "procurement", "fx", "other"]

_SOURCE = {"file": {"type": "string"}, "page": {"type": "integer"}, "quote": {"type": "string"},
           "confidence": {"type": "number"}}
ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "array", "items": {
            "type": "object",
            "properties": {"field": {"type": "string", "enum": list(SUMMARY_FIELDS)}, "value": {"type": "string"},
                           "numeric": {"type": ["number", "null"]}, "date": {"type": ["string", "null"]}, **_SOURCE},
            "required": ["field", "value", "numeric", "date", "file", "page", "quote", "confidence"],
            "additionalProperties": False}},
        "risks": {"type": "array", "items": {
            "type": "object",
            "properties": {"description": {"type": "string"}, "category": {"type": "string", "enum": RISK_CATEGORIES},
                           "probability_pct": {"type": "number"}, "mitigation": {"type": "string"}, **_SOURCE},
            "required": ["description", "category", "probability_pct", "mitigation", "file", "page", "quote", "confidence"],
            "additionalProperties": False}},
        "rfis": {"type": "array", "items": {
            "type": "object",
            "properties": {"question": {"type": "string"}, "reference": {"type": "string"},
                           "is_conflict": {"type": "boolean"}, **_SOURCE},
            "required": ["question", "reference", "is_conflict", "file", "page", "quote", "confidence"],
            "additionalProperties": False}},
    },
    "required": ["summary", "risks", "rfis"],
    "additionalProperties": False,
}

ANALYSIS_SYSTEM = """You are a senior tender analyst for a contractor working on integrated building projects
(excavation & concrete structure, finishes, MEP, furniture) and infrastructure (mechanical, electrical, networks, roads)
for private-sector clients, mostly in Egypt. Documents are in Arabic and/or English.
Read the tender documents and extract ONLY what is actually written:
- summary: the contract terms listed in the schema enum. One entry per field found; skip fields not stated.
  `value` is a short statement in the document's language; `numeric` the key number (percent, days, months) or null;
  `date` ISO yyyy-mm-dd when the field is a date, else null.
- risks: commercial/technical risks a pricing team must cost or mitigate (onerous penalties, fixed prices with no
  escalation, long payment periods, high retention, restricted vendors, imported materials / FX exposure, unclear scope).
  probability_pct is your estimate (0–100).
- rfis: clarification questions — conflicts between drawings, specifications and BOQ, missing or ambiguous items.
  Write the question formally, ready to send to the consultant.
Every entry MUST cite the exact `file` name and `page` number shown in the document markers and quote the supporting
sentence verbatim in `quote`. Never invent a value; confidence reflects how explicit the text is (0–1).
Do not calculate prices."""


def _client():
    import anthropic
    return anthropic.Anthropic()


def _call_json(system: str, content: list, schema: dict, effort: str = "high") -> dict:
    import anthropic
    try:
        with _client().beta.messages.stream(
            model=AI_MODEL,
            max_tokens=64000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            thinking={"type": "adaptive"},
            output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
            system=system,
            messages=[{"role": "user", "content": content}],
        ) as stream:
            msg = stream.get_final_message()
    except anthropic.AuthenticationError as e:
        raise AIError(f"AI authentication failed — check ANTHROPIC_API_KEY ({e.status_code})") from e
    except anthropic.RateLimitError as e:
        raise AIError("AI rate limit reached — retry in a minute") from e
    except anthropic.APIStatusError as e:
        raise AIError(f"AI request failed ({e.status_code}): {e.message}") from e
    except anthropic.APIConnectionError as e:
        raise AIError("Cannot reach the AI service") from e
    if msg.stop_reason == "refusal":
        raise AIError("The AI declined this request")
    if msg.stop_reason == "max_tokens":
        raise AIError("AI output was cut off — select fewer documents")
    text = next((b.text for b in msg.content if b.type == "text"), "")
    return json.loads(text)


MAX_CHARS = 1_500_000


def _doc_content(pages: list[dict], scanned: list[dict]) -> list:
    total = sum(len(p["text"]) for p in pages)
    if total > MAX_CHARS:
        raise AIError(f"Selected documents contain {total:,} characters — select fewer documents (limit {MAX_CHARS:,})")
    content: list = []
    for s in scanned:  # scanned PDFs are read natively by the model (Arabic + English OCR)
        content.append({"type": "document", "title": s["file"],
                        "source": {"type": "base64", "media_type": "application/pdf",
                                   "data": base64.b64encode(s["data"]).decode()}})
    body = "\n\n".join(f'<page file="{p["file"]}" page="{p["page"]}">\n{p["text"]}\n</page>' for p in pages)
    if body:
        content.append({"type": "text", "text": body})
    return content


# ---------------------------------------------------------------- tender analysis (module 4)
def analyze_tender(pages: list[dict], scanned: list[dict] | None = None) -> dict:
    """pages: [{file, page, text, document_id}] → {summary, risks, rfis, engine}"""
    scanned = scanned or []
    if ai_available():
        content = _doc_content(pages, scanned)
        content.append({"type": "text", "text": "Extract the tender summary, risks and clarification questions."})
        out = _call_json(ANALYSIS_SYSTEM, content, ANALYSIS_SCHEMA)
        out["engine"] = AI_MODEL
        return out
    out = offline_analyze(pages)
    if scanned:
        out["notes"] = [f"{s['file']}: scanned file — needs the AI service for OCR" for s in scanned]
    return out


_RULES = {
    "owner": ["المالك", "owner", "employer", "client"],
    "consultant": ["الاستشاري", "consultant", "engineer:"],
    "scope": ["نطاق العمل", "نطاق الاعمال", "scope of work", "the works comprise"],
    "duration": ["مده التنفيذ", "مده المشروع", "duration", "time for completion", "completion period"],
    "delay_penalty": ["غرامه التاخير", "غرامات التاخير", "delay penalt", "liquidated damages", "delay damages"],
    "advance_payment": ["دفعه مقدمه", "الدفعه المقدمه", "advance payment"],
    "retention": ["retention", "تامين اعمال", "استقطاع", "يستقطع", "محتجزات"],
    "payment_terms": ["تصرف المستخلصات", "صرف المستخلصات", "مده الدفع", "payment of interim", "payment within", "paid within"],
    "bid_bond": ["التامين الابتدايي", "تامين ابتدايي", "bid bond", "tender bond", "bid security"],
    "performance_bond": ["التامين النهايي", "تامين نهايي", "performance bond", "performance security"],
    "insurance": ["car", "وثيقه تامين", "تامين شامل", "insurance"],
    "price_escalation": ["فروق اسعار", "فروق الاسعار", "الاسعار ثابته", "price escalation", "price adjustment", "fixed price"],
    "currency": ["العمله", "currency"],
    "bid_validity": ["صلاحيه العرض", "صلاحيه العطاء", "bid validity", "validity of tender", "valid for"],
    "approved_vendors": ["الموردين المعتمدين", "موردين معتمدين", "approved vendors", "approved manufacturers", "approved suppliers"],
    "maintenance_period": ["مده الضمان", "الصيانه", "defects liability", "maintenance period"],
    "site_visit_date": ["زياره الموقع", "site visit"],
    "rfi_deadline": ["الاستفسارات", "clarification", "queries"],
    "submission_date": ["تقديم العطاءات", "موعد التقديم", "submission", "closing date"],
}
_DATE_RE = re.compile(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})|(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})")
_PCT_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:%|٪|بالمائه|percent)")
_NUM_RE = re.compile(r"(\d+(?:[.,]\d+)?)")
_CONFLICT = ["بينما", "تعارض", "يختلف", "discrepanc", "conflict", "whereas the drawings", "while the specification"]


def _sentences(text: str):
    for line in re.split(r"[\n\r]+|(?<=[.!؟?])\s+(?=[^\d])", text):
        line = line.strip()
        if len(line) > 4:
            yield line


def _dates(sentence: str) -> list[str]:
    out = []
    for m in _DATE_RE.finditer(sentence.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))):
        try:
            if m.group(1):
                d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            else:
                d = date(int(m.group(6)), int(m.group(5)), int(m.group(4)))
            out.append(d.isoformat())
        except ValueError:
            continue
    return out


def offline_analyze(pages: list[dict]) -> dict:
    summary, risks, rfis, seen = [], [], [], set()
    for p in pages:
        for sent in _sentences(p["text"]):
            n = normalize(sent)
            for field, keys in _RULES.items():
                if field in seen:
                    continue
                if field == "insurance" and not re.search(r"\bcar\b|تامين شامل|وثيقه تامين|insurance", n):
                    continue
                if any(normalize(k) in n for k in keys):
                    is_date_field = field in ("site_visit_date", "rfi_deadline", "submission_date")
                    # numbers / dates are read from the clause that holds the keyword
                    clauses = [c for c in re.split(r"[،;]|,\s+(?=\D)|\s(?=و(?:اخر|آخر|التامين|التأمين))", sent) if c.strip()]
                    clause = next((c for c in clauses if any(normalize(k) in normalize(c) for k in keys)), sent)
                    cn = normalize(clause)
                    cdates = _dates(clause)
                    if is_date_field and not cdates:
                        continue
                    pct = _PCT_RE.search(cn)
                    num = to_number(pct.group(1)) if pct else None
                    if num is None and field in ("duration", "payment_terms", "bid_validity", "maintenance_period"):
                        m = _NUM_RE.search(cn)
                        num = to_number(m.group(1)) if m else None
                    value = clause.strip() if (is_date_field or field in ("bid_bond", "performance_bond")) else sent
                    summary.append({"field": field, "value": value[:300], "numeric": num,
                                    "date": cdates[0] if is_date_field else None,
                                    "file": p["file"], "page": p["page"], "quote": sent[:300], "confidence": 0.45})
                    seen.add(field)
            # risk rules
            def add_risk(desc, cat, prob):
                risks.append({"description": desc, "category": cat, "probability_pct": prob, "mitigation": "",
                              "file": p["file"], "page": p["page"], "quote": sent[:300], "confidence": 0.4})
            if any(k in n for k in ["الاسعار ثابته", "لا يجوز المطالبه باي فروق", "fixed price", "no price adjustment", "no escalation"]):
                add_risk("أسعار ثابتة بدون فروق أسعار — خطر ارتفاع أسعار الخامات وسعر الصرف / Fixed price, no escalation", "financial", 50)
            if any(normalize(k) in n for k in _RULES["delay_penalty"]):
                pct = _PCT_RE.search(n)
                if pct and (to_number(pct.group(1)) or 0) >= 0.5:
                    add_risk("غرامة تأخير مرتفعة — يلزم برنامج زمني واقعي / High delay penalty", "schedule", 30)
            if any(normalize(k) in n for k in _RULES["payment_terms"]):
                m = _NUM_RE.search(n)
                if m and (to_number(m.group(1)) or 0) >= 45:
                    add_risk("مدة صرف المستخلصات طويلة — تكلفة تمويل / Long payment period", "financial", 60)
            if any(normalize(k) in n for k in _RULES["approved_vendors"]):
                add_risk("قائمة موردين معتمدين محدودة — تقل المنافسة بين العروض / Restricted vendor list", "procurement", 40)
            if any(k in n for k in ["مستورد", "imported", "dollar", "دولار", "يورو", "euro"]):
                add_risk("مواد مستوردة — تعرض لتغير سعر الصرف ومدد التوريد / Imported materials: FX & lead time", "fx", 40)
            if any(k in n for k in _CONFLICT):
                rfis.append({"question": f"يرجى التوضيح: {sent[:250]}", "reference": f'{p["file"]} p.{p["page"]}',
                             "is_conflict": True, "file": p["file"], "page": p["page"], "quote": sent[:300],
                             "confidence": 0.4})
    return {"summary": summary, "risks": risks, "rfis": rfis, "engine": "offline-rules"}


# ---------------------------------------------------------------- chat assistant on tender documents
CHAT_SCHEMA = {
    "type": "object",
    "properties": {"answer": {"type": "string"},
                   "sources": {"type": "array", "items": {"type": "object", "properties": {
                       "file": {"type": "string"}, "page": {"type": "integer"}, "quote": {"type": "string"}},
                       "required": ["file", "page", "quote"], "additionalProperties": False}}},
    "required": ["answer", "sources"], "additionalProperties": False,
}


def chat(question: str, pages: list[dict]) -> dict:
    if not pages:
        return {"answer": "لا توجد مستندات مستخرجة لهذه المناقصة بعد. / No extracted documents yet.", "sources": [], "engine": engine_name()}
    idx = TfIdfIndex([(i, p["text"]) for i, p in enumerate(pages)])
    hits = idx.search(question, k=8)
    chosen = [pages[i] for _, i in hits] or pages[:4]
    if ai_available():
        content = _doc_content(chosen, [])
        content.append({"type": "text", "text": f"Question: {question}\nAnswer in the language of the question, only from these pages, citing file and page."})
        out = _call_json("You answer questions about tender documents for a pricing team. Only use the provided pages; if the answer is not there, say so.",
                         content, CHAT_SCHEMA, effort="medium")
        out["engine"] = AI_MODEL
        return out
    srcs = []
    qn = set(normalize(question).split())
    for p in chosen[:3]:
        best = max(_sentences(p["text"]), key=lambda s: len(qn & set(normalize(s).split())), default="")
        srcs.append({"file": p["file"], "page": p["page"], "quote": best[:300]})
    return {"answer": "أقرب الفقرات من المستندات (وضع بدون AI): / Closest passages (offline mode):",
            "sources": srcs, "engine": "offline-rules"}


# ---------------------------------------------------------------- supplier quotation extraction (module 7)
QUOTE_SCHEMA = {
    "type": "object",
    "properties": {
        "supplier_name": {"type": "string"}, "currency": {"type": "string"},
        "valid_until": {"type": ["string", "null"]}, "lead_time_days": {"type": ["integer", "null"]},
        "payment_terms": {"type": "string"}, "exclusions": {"type": "string"},
        "includes_vat": {"type": "boolean"}, "includes_transport": {"type": "boolean"},
        "scope": {"type": "string", "enum": ["supply", "apply", "supply_apply"]},
        "lines": {"type": "array", "items": {"type": "object", "properties": {
            "boq_item_id": {"type": "integer"}, "unit_rate": {"type": ["number", "null"]},
            "remarks": {"type": "string"}, "confidence": {"type": "number"}},
            "required": ["boq_item_id", "unit_rate", "remarks", "confidence"], "additionalProperties": False}},
    },
    "required": ["supplier_name", "currency", "valid_until", "lead_time_days", "payment_terms", "exclusions",
                 "includes_vat", "includes_transport", "scope", "lines"],
    "additionalProperties": False,
}


def extract_quotation(filename: str, data: bytes, pages: list[str], items: list[dict]) -> dict:
    if not ai_available():
        raise AIError("Reading PDF / e-mail quotations needs the AI service. Offline: use the RFQ Excel template.")
    content: list = []
    if filename.lower().endswith(".pdf") and sum(len(p) for p in pages) < 50:
        content.append({"type": "document", "title": filename, "source": {
            "type": "base64", "media_type": "application/pdf", "data": base64.b64encode(data).decode()}})
    else:
        content.append({"type": "text", "text": "\n\n".join(f"<page n='{i+1}'>\n{t}\n</page>" for i, t in enumerate(pages))})
    item_list = "\n".join(f'{it["id"]} | {it["item_ref"]} | {it["description"][:200]} | {it["unit"]} | {it["quantity"]}' for it in items)
    content.append({"type": "text", "text": f"BOQ items of this package (id | ref | description | unit | qty):\n{item_list}\n\n"
                                            "Map each quoted price to the matching BOQ item id. unit_rate is the price per BOQ unit "
                                            "exactly as quoted (no conversion); null if the item is not quoted. List exclusions, "
                                            "validity, lead time, payment terms, and whether VAT and transport are included. "
                                            "scope: supply, apply (installation only) or supply_apply."})
    out = _call_json("You transcribe supplier and subcontractor quotations into a comparison table. Never compute or adjust prices.",
                     content, QUOTE_SCHEMA)
    out["engine"] = AI_MODEL
    return out


# ---------------------------------------------------------------- site visit (module 5)
def site_visit_suggestions(checklist: list[dict], summary: str) -> list[dict]:
    """Turn site-visit issues into suggested risks / indirect cost lines (offline rules; AI can refine later)."""
    out = []
    for c in checklist:
        if c.get("status") == "issue":
            note = (c.get("notes") or "").strip()
            label = c.get("label", c.get("key", ""))
            out.append({"type": "risk", "description": f"{label}: {note}" if note else label, "category": "site",
                        "probability_pct": 50, "source": "site_visit"})
            if c.get("key") in ("utilities", "storage", "traffic", "groundwater", "access"):
                out.append({"type": "indirect", "description": f"{label} — {note}" if note else label,
                            "kind": "fixed", "source": "site_visit"})
    return out
