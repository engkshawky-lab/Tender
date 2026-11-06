"""Data model — the entities from the spec (section: قاعدة البيانات) plus the commercial review additions:
scope (Supply / Apply / Supply+Apply), value-engineering alternatives, supplier lead time, multi-role users."""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (JSON, Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text,
                        UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

Money = Numeric(20, 6)


def now():
    return datetime.utcnow()


# ---------------------------------------------------------------- users, settings, audit
class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True)
    full_name: Mapped[str] = mapped_column(String(200), default="")
    email: Mapped[str] = mapped_column(String(200), default="")
    password_hash: Mapped[str] = mapped_column(String(200))
    roles: Mapped[list] = mapped_column(JSON, default=list)            # one user may hold several roles
    extra_permissions: Mapped[list] = mapped_column(JSON, default=list)
    revoked_permissions: Mapped[list] = mapped_column(JSON, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[dict | list | float | str | None] = mapped_column(JSON)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    action: Mapped[str] = mapped_column(String(20))
    entity: Mapped[str] = mapped_column(String(60))
    entity_id: Mapped[str] = mapped_column(String(40))
    tender_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    changes: Mapped[dict] = mapped_column(JSON, default=dict)
    at: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)


class AISuggestion(Base):
    """Every AI proposal is logged with its source; accept/reject is recorded to measure AI quality."""
    __tablename__ = "ai_suggestions"
    id: Mapped[int] = mapped_column(primary_key=True)
    tender_id: Mapped[int | None] = mapped_column(ForeignKey("tenders.id", ondelete="CASCADE"), nullable=True)
    kind: Mapped[str] = mapped_column(String(40))           # summary_field | risk | rfi | cost_code | rate | quote_line | indirect | ...
    target: Mapped[str] = mapped_column(String(120), default="")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    source: Mapped[dict] = mapped_column(JSON, default=dict)  # {document_id, file, page} or {tender_code, item}
    confidence: Mapped[float] = mapped_column(default=0.0)
    engine: Mapped[str] = mapped_column(String(60), default="")  # model id or "offline-rules"
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|accepted|edited|rejected
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    decided_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


# ---------------------------------------------------------------- master data
class CostCode(Base):
    __tablename__ = "cost_codes"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True)
    name_ar: Mapped[str] = mapped_column(String(300))
    name_en: Mapped[str] = mapped_column(String(300), default="")
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("cost_codes.id"), nullable=True)
    level: Mapped[int] = mapped_column(default=1)            # 1 division, 2 work type, 3 standard item
    project_type: Mapped[str] = mapped_column(String(20), default="common")  # building | infra | common
    unit: Mapped[str] = mapped_column(String(20), default="")
    keywords: Mapped[str] = mapped_column(Text, default="")


class Supplier(Base):
    """Approved Vendor List (AVL) entry — suppliers and subcontractors."""
    __tablename__ = "suppliers"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(20), default="supplier")  # supplier | subcontractor | both
    status: Mapped[str] = mapped_column(String(20), default="pending")  # approved | pending | suspended | blacklisted
    trades: Mapped[list] = mapped_column(JSON, default=list)
    project_types: Mapped[list] = mapped_column(JSON, default=list)    # building | infra
    brands: Mapped[str] = mapped_column(Text, default="")               # brands / manufacturers represented
    rating: Mapped[float] = mapped_column(default=3.0)
    contact_name: Mapped[str] = mapped_column(String(200), default="")
    phone: Mapped[str] = mapped_column(String(60), default="")
    email: Mapped[str] = mapped_column(String(200), default="")
    address: Mapped[str] = mapped_column(Text, default="")
    commercial_register: Mapped[str] = mapped_column(String(60), default="")
    tax_card: Mapped[str] = mapped_column(String(60), default="")
    approval_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    approval_expiry: Mapped[date | None] = mapped_column(Date, nullable=True)
    approved_by_user: Mapped[int | None] = mapped_column(Integer, nullable=True)
    approved_by: Mapped[str] = mapped_column(Text, default="")   # owners / consultants that approved this vendor
    payment_terms: Mapped[str] = mapped_column(Text, default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class SupplierDocument(Base):
    __tablename__ = "supplier_documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(30), default="other")  # commercial_register | tax_card | iso | catalogue | approval_letter | other
    title: Mapped[str] = mapped_column(String(300), default="")
    filename: Mapped[str] = mapped_column(String(300))
    storage_path: Mapped[str] = mapped_column(String(500))
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class SupplierEvaluation(Base):
    """Performance evaluation after a project or delivery — drives the supplier rating."""
    __tablename__ = "supplier_evaluations"
    id: Mapped[int] = mapped_column(primary_key=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id", ondelete="CASCADE"), index=True)
    tender_id: Mapped[int | None] = mapped_column(ForeignKey("tenders.id", ondelete="SET NULL"), nullable=True)
    eval_date: Mapped[date] = mapped_column(Date, default=date.today)
    quality: Mapped[int] = mapped_column(default=3)
    delivery: Mapped[int] = mapped_column(default=3)
    price: Mapped[int] = mapped_column(default=3)
    cooperation: Mapped[int] = mapped_column(default=3)
    comment: Mapped[str] = mapped_column(Text, default="")
    by_user: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Resource(Base):
    __tablename__ = "resources"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40), default="")
    name: Mapped[str] = mapped_column(String(300))
    kind: Mapped[str] = mapped_column(String(20))   # material | labor | equipment | subcontract
    unit: Mapped[str] = mapped_column(String(20))
    price: Mapped[Decimal] = mapped_column(Money)
    currency: Mapped[str] = mapped_column(String(3), default="EGP")
    price_date: Mapped[date] = mapped_column(Date, default=date.today)
    source: Mapped[str] = mapped_column(String(200), default="")
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id"), nullable=True)
    cost_code_id: Mapped[int | None] = mapped_column(ForeignKey("cost_codes.id"), nullable=True)
    productivity: Mapped[Decimal | None] = mapped_column(Money, nullable=True)  # labour/equipment: units per day
    waste_pct: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")


class BuildUpTemplate(Base):
    """Reusable rate analysis for a standard item (e.g. 1 m3 RC slab)."""
    __tablename__ = "buildup_templates"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(300))
    unit: Mapped[str] = mapped_column(String(20))
    cost_code_id: Mapped[int | None] = mapped_column(ForeignKey("cost_codes.id"), nullable=True)
    lines: Mapped[list] = mapped_column(JSON, default=list)  # [{kind, part, resource_id, description, coefficient, waste_pct}]


# ---------------------------------------------------------------- tender
class Tender(Base):
    __tablename__ = "tenders"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(300))
    owner: Mapped[str] = mapped_column(String(200), default="")
    consultant: Mapped[str] = mapped_column(String(200), default="")
    project_type: Mapped[str] = mapped_column(String(20), default="building")  # building (متكامل) | infra
    client_type: Mapped[str] = mapped_column(String(20), default="private")
    location: Mapped[str] = mapped_column(String(300), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(30), default="intake")
    # intake | go_no_go | study | pricing | review | approved | submitted | won | lost | cancelled | declined | historical
    invitation_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    site_visit_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    rfi_deadline: Mapped[date | None] = mapped_column(Date, nullable=True)
    submission_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    bid_bond_amount: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    bid_validity_days: Mapped[int | None] = mapped_column(nullable=True)
    duration_months: Mapped[int | None] = mapped_column(nullable=True)
    base_currency: Mapped[str] = mapped_column(String(3), default="EGP")
    assignments: Mapped[dict] = mapped_column(JSON, default=dict)     # {role: [user_id,...]}
    gonogo: Mapped[dict] = mapped_column(JSON, default=dict)          # {scores, weighted, decision, reason, by, at}
    summary: Mapped[dict] = mapped_column(JSON, default=dict)         # approved Tender Summary fields {key:{value,source,page}}
    submission_checklist: Mapped[list] = mapped_column(JSON, default=list)
    result: Mapped[dict] = mapped_column(JSON, default=dict)          # {outcome, date, our_price, winner, winning_price, reasons, lessons}
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    documents = relationship("Document", back_populates="tender", cascade="all, delete-orphan")


class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[int] = mapped_column(primary_key=True)
    tender_id: Mapped[int] = mapped_column(ForeignKey("tenders.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(300))
    step: Mapped[int | None] = mapped_column(nullable=True)  # 1..20 workflow step
    assignee_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="open")  # open | done


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    tender_id: Mapped[int] = mapped_column(ForeignKey("tenders.id", ondelete="CASCADE"))
    doc_type: Mapped[str] = mapped_column(String(30), default="other")
    # drawings | specs | boq | general_conditions | particular_conditions | addendum | invitation | quotation | site_photo | submission | other
    title: Mapped[str] = mapped_column(String(300))
    filename: Mapped[str] = mapped_column(String(300))
    storage_path: Mapped[str] = mapped_column(String(500))
    mime: Mapped[str] = mapped_column(String(120), default="")
    revision: Mapped[str] = mapped_column(String(20), default="0")
    issue_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    supersedes_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id"), nullable=True)
    is_latest: Mapped[bool] = mapped_column(Boolean, default=True)
    pages: Mapped[int] = mapped_column(default=0)
    text_status: Mapped[str] = mapped_column(String(20), default="pending")  # extracted | needs_ocr | none | failed
    uploaded_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    tender = relationship("Tender", back_populates="documents")
    page_texts = relationship("DocumentPage", cascade="all, delete-orphan", order_by="DocumentPage.page_no")


class DocumentPage(Base):
    __tablename__ = "document_pages"
    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    page_no: Mapped[int] = mapped_column()
    text: Mapped[str] = mapped_column(Text, default="")


class Risk(Base):
    __tablename__ = "risks"
    id: Mapped[int] = mapped_column(primary_key=True)
    tender_id: Mapped[int] = mapped_column(ForeignKey("tenders.id", ondelete="CASCADE"))
    description: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(40), default="contractual")
    probability_pct: Mapped[Decimal] = mapped_column(Money, default=0)
    impact_amount: Mapped[Decimal] = mapped_column(Money, default=0)
    mitigation: Mapped[str] = mapped_column(Text, default="")
    include_in_contingency: Mapped[bool] = mapped_column(Boolean, default=True)
    source_document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
    source_page: Mapped[int | None] = mapped_column(nullable=True)
    origin: Mapped[str] = mapped_column(String(20), default="manual")   # manual | ai | site_visit
    approved: Mapped[bool] = mapped_column(Boolean, default=True)       # AI items stay unapproved until a human accepts
    confidence: Mapped[float | None] = mapped_column(nullable=True)


class RFI(Base):
    __tablename__ = "rfis"
    id: Mapped[int] = mapped_column(primary_key=True)
    tender_id: Mapped[int] = mapped_column(ForeignKey("tenders.id", ondelete="CASCADE"))
    number: Mapped[int] = mapped_column(default=1)
    question: Mapped[str] = mapped_column(Text)
    reference: Mapped[str] = mapped_column(String(300), default="")
    source_document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
    source_page: Mapped[int | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft | sent | answered
    answer: Mapped[str] = mapped_column(Text, default="")
    answer_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    pricing_impact: Mapped[str] = mapped_column(Text, default="")
    impact_amount: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    origin: Mapped[str] = mapped_column(String(20), default="manual")
    approved: Mapped[bool] = mapped_column(Boolean, default=True)


class SiteVisit(Base):
    __tablename__ = "site_visits"
    id: Mapped[int] = mapped_column(primary_key=True)
    tender_id: Mapped[int] = mapped_column(ForeignKey("tenders.id", ondelete="CASCADE"))
    visit_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    attendees: Mapped[str] = mapped_column(Text, default="")
    checklist: Mapped[list] = mapped_column(JSON, default=list)  # [{key,label,status,notes}]
    summary: Mapped[str] = mapped_column(Text, default="")
    photos: Mapped[list] = mapped_column(JSON, default=list)     # [{document_id, caption, lat, lng}]


class Package(Base):
    __tablename__ = "packages"
    id: Mapped[int] = mapped_column(primary_key=True)
    tender_id: Mapped[int] = mapped_column(ForeignKey("tenders.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(200))
    name_en: Mapped[str] = mapped_column(String(200), default="")
    trade: Mapped[str] = mapped_column(String(60), default="")
    execution: Mapped[str] = mapped_column(String(20), default="subcontract")  # self | subcontract | supply_only | mixed
    scope: Mapped[str] = mapped_column(String(20), default="supply_apply")     # supply | apply | supply_apply
    required_on_site_month: Mapped[int | None] = mapped_column(nullable=True)  # for lead-time checks
    selected_quotation_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    selected_apply_quotation_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # Supply & Apply split


class BoqSource(Base):
    __tablename__ = "boq_sources"
    id: Mapped[int] = mapped_column(primary_key=True)
    tender_id: Mapped[int] = mapped_column(ForeignKey("tenders.id", ondelete="CASCADE"))
    document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
    mapping: Mapped[dict] = mapped_column(JSON, default=dict)  # {sheet:{header_row, cols:{ref,desc,unit,qty,rate,amount}}}
    imported_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class BoqItem(Base):
    __tablename__ = "boq_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    tender_id: Mapped[int] = mapped_column(ForeignKey("tenders.id", ondelete="CASCADE"), index=True)
    source_id: Mapped[int | None] = mapped_column(ForeignKey("boq_sources.id", ondelete="SET NULL"), nullable=True)
    seq: Mapped[int] = mapped_column(default=0)
    sheet: Mapped[str] = mapped_column(String(120), default="")
    row_index: Mapped[int | None] = mapped_column(nullable=True)
    item_ref: Mapped[str] = mapped_column(String(40), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    unit: Mapped[str] = mapped_column(String(20), default="")
    quantity: Mapped[Decimal] = mapped_column(Money, default=0)
    is_section: Mapped[bool] = mapped_column(Boolean, default=False)
    section: Mapped[str] = mapped_column(String(300), default="")
    scope: Mapped[str] = mapped_column(String(20), default="supply_apply")  # supply | apply | supply_apply
    cost_code_id: Mapped[int | None] = mapped_column(ForeignKey("cost_codes.id", ondelete="SET NULL"), nullable=True)
    package_id: Mapped[int | None] = mapped_column(ForeignKey("packages.id", ondelete="SET NULL"), nullable=True)
    is_provisional: Mapped[bool] = mapped_column(Boolean, default=False)
    provisional_amount: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    checked_quantity: Mapped[Decimal | None] = mapped_column(Money, nullable=True)  # our take-off check
    qty_remark: Mapped[str] = mapped_column(Text, default="")
    notes: Mapped[str] = mapped_column(Text, default="")


class Quotation(Base):
    __tablename__ = "quotations"
    id: Mapped[int] = mapped_column(primary_key=True)
    tender_id: Mapped[int] = mapped_column(ForeignKey("tenders.id", ondelete="CASCADE"))
    package_id: Mapped[int | None] = mapped_column(ForeignKey("packages.id", ondelete="CASCADE"), nullable=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"))
    reference: Mapped[str] = mapped_column(String(100), default="")
    scope: Mapped[str] = mapped_column(String(20), default="supply_apply")  # what the quote covers
    received_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="EGP")
    payment_terms: Mapped[str] = mapped_column(Text, default="")
    lead_time_days: Mapped[int | None] = mapped_column(nullable=True)
    exclusions: Mapped[str] = mapped_column(Text, default="")
    includes_vat: Mapped[bool] = mapped_column(Boolean, default=False)
    includes_transport: Mapped[bool] = mapped_column(Boolean, default=True)
    transport_adjust_pct: Mapped[Decimal] = mapped_column(Money, default=0)  # added when transport excluded
    other_adjust_pct: Mapped[Decimal] = mapped_column(Money, default=0)      # scope-levelling adjustment
    discount_pct: Mapped[Decimal] = mapped_column(Money, default=0)
    document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
    origin: Mapped[str] = mapped_column(String(20), default="manual")  # manual | excel | ai
    notes: Mapped[str] = mapped_column(Text, default="")
    tech_scores: Mapped[dict] = mapped_column(JSON, default=dict)   # {criterion_key: 1..5} technical evaluation
    tech_notes: Mapped[str] = mapped_column(Text, default="")
    lines = relationship("QuotationLine", cascade="all, delete-orphan")


class QuotationLine(Base):
    __tablename__ = "quotation_lines"
    id: Mapped[int] = mapped_column(primary_key=True)
    quotation_id: Mapped[int] = mapped_column(ForeignKey("quotations.id", ondelete="CASCADE"), index=True)
    boq_item_id: Mapped[int] = mapped_column(ForeignKey("boq_items.id", ondelete="CASCADE"))
    unit_rate: Mapped[Decimal | None] = mapped_column(Money, nullable=True)  # None = not quoted (scope gap)
    remarks: Mapped[str] = mapped_column(Text, default="")
    approved: Mapped[bool] = mapped_column(Boolean, default=True)  # AI-extracted lines need acceptance
    __table_args__ = (UniqueConstraint("quotation_id", "boq_item_id"),)


class SchedulePhase(Base):
    __tablename__ = "schedule_phases"
    id: Mapped[int] = mapped_column(primary_key=True)
    tender_id: Mapped[int] = mapped_column(ForeignKey("tenders.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(200))
    start_month: Mapped[int] = mapped_column(default=1)
    duration_months: Mapped[int] = mapped_column(default=1)
    weight_pct: Mapped[Decimal] = mapped_column(Money, default=0)  # share of total cost


class VEAlternative(Base):
    __tablename__ = "ve_alternatives"
    id: Mapped[int] = mapped_column(primary_key=True)
    tender_id: Mapped[int] = mapped_column(ForeignKey("tenders.id", ondelete="CASCADE"))
    boq_item_id: Mapped[int | None] = mapped_column(ForeignKey("boq_items.id", ondelete="CASCADE"), nullable=True)
    description: Mapped[str] = mapped_column(Text)
    alternative_rate: Mapped[Decimal] = mapped_column(Money, default=0)
    lead_time_days: Mapped[int | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="proposed")  # proposed | offered | accepted | rejected
    notes: Mapped[str] = mapped_column(Text, default="")


class Competitor(Base):
    __tablename__ = "competitor_prices"
    id: Mapped[int] = mapped_column(primary_key=True)
    tender_id: Mapped[int] = mapped_column(ForeignKey("tenders.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(200))
    price: Mapped[Decimal] = mapped_column(Money)
    rank: Mapped[int | None] = mapped_column(nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")


# ---------------------------------------------------------------- estimate versions
class Estimate(Base):
    __tablename__ = "estimates"
    id: Mapped[int] = mapped_column(primary_key=True)
    tender_id: Mapped[int] = mapped_column(ForeignKey("tenders.id", ondelete="CASCADE"), index=True)
    version_no: Mapped[int] = mapped_column(default=1)
    name: Mapped[str] = mapped_column(String(200), default="")
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft | in_review | approved | rejected
    fx_rates: Mapped[dict] = mapped_column(JSON, default=dict)        # frozen per version: {"USD": 48.5}
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # frozen calculation at approval
    review_comments: Mapped[str] = mapped_column(Text, default="")
    cloned_from_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    submitted_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    approved_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    __table_args__ = (UniqueConstraint("tender_id", "version_no"),)


class BuildUpLine(Base):
    __tablename__ = "buildup_lines"
    id: Mapped[int] = mapped_column(primary_key=True)
    estimate_id: Mapped[int] = mapped_column(ForeignKey("estimates.id", ondelete="CASCADE"), index=True)
    boq_item_id: Mapped[int] = mapped_column(ForeignKey("boq_items.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20))        # material | labor | equipment | subcontract
    part: Mapped[str] = mapped_column(String(20), default="supply_apply")  # supply | apply | supply_apply
    description: Mapped[str] = mapped_column(String(300), default="")
    resource_id: Mapped[int | None] = mapped_column(ForeignKey("resources.id", ondelete="SET NULL"), nullable=True)
    unit: Mapped[str] = mapped_column(String(20), default="")
    coefficient: Mapped[Decimal] = mapped_column(Money, default=1)  # qty of resource per BOQ unit (1/productivity for labour)
    unit_price: Mapped[Decimal] = mapped_column(Money, default=0)
    currency: Mapped[str] = mapped_column(String(3), default="EGP")
    waste_pct: Mapped[Decimal] = mapped_column(Money, default=0)
    source: Mapped[str] = mapped_column(String(20), default="manual")  # quotation | library | history | manual | ai
    source_ref: Mapped[str] = mapped_column(String(300), default="")
    quotation_id: Mapped[int | None] = mapped_column(ForeignKey("quotations.id", ondelete="SET NULL"), nullable=True)
    price_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    approved: Mapped[bool] = mapped_column(Boolean, default=True)  # AI-suggested lines start False
    confidence: Mapped[float | None] = mapped_column(nullable=True)


class IndirectItem(Base):
    __tablename__ = "indirect_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    estimate_id: Mapped[int] = mapped_column(ForeignKey("estimates.id", ondelete="CASCADE"), index=True)
    category: Mapped[str] = mapped_column(String(40), default="site_staff")
    description: Mapped[str] = mapped_column(String(300))
    description_en: Mapped[str] = mapped_column(String(300), default="")
    kind: Mapped[str] = mapped_column(String(10), default="time")  # time | fixed
    monthly_cost: Mapped[Decimal] = mapped_column(Money, default=0)
    quantity: Mapped[Decimal] = mapped_column(Money, default=1)   # e.g. number of engineers / cars
    months: Mapped[Decimal | None] = mapped_column(Money, nullable=True)  # None = full project duration
    amount: Mapped[Decimal] = mapped_column(Money, default=0)      # fixed items
    currency: Mapped[str] = mapped_column(String(3), default="EGP")
    template_key: Mapped[str] = mapped_column(String(60), default="")
    origin: Mapped[str] = mapped_column(String(20), default="manual")
    approved: Mapped[bool] = mapped_column(Boolean, default=True)
