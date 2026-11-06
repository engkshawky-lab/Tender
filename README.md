# منصة تسعير المناقصات — Tender Pricing Platform

This platform runs a tender from the invitation to the result in **5 stages and 20 steps**, as set out in the spec
«مواصفات برنامج تسعير المناقصات بالذكاء الاصطناعي». It also includes the commercial sector's review and the additions
requested since. The work types are **integrated building projects** (excavation and concrete structure, finishes,
MEP and furniture) and **infrastructure** (mechanical, electrical, networks and roads).

> **The AI suggests, a person approves.** Every calculation runs in fixed code (`backend/app/engine/pricing.py`). The
> AI only reads, extracts and suggests. Each suggestion shows its source (file and page, or the past project and item)
> and a confidence score. It is highlighted in a different colour and has no effect on the price until someone approves it.

## Running it

```bash
cd frontend && npm install && npx vite build && cd ..
```

```bash
cd backend && pip install -r requirements.txt
```

```bash
cd backend && python scripts/demo_data.py
```

```bash
cd backend && uvicorn app.main:app --port 8000
```

Open http://localhost:8000. The default login is `admin / admin123`; change it with `TP_ADMIN_PASSWORD`. The demo users
are `manager`, `estimator`, `buyer`, `techoffice` and `gm`, all with the password `demo1234`.

To run on the company server or in the cloud with PostgreSQL:

```bash
DB_PASSWORD=... ADMIN_PASSWORD=... ANTHROPIC_API_KEY=... docker compose up -d --build
```

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | PostgreSQL in production (`postgresql+psycopg://…`). SQLite is used when it is not set. |
| `ANTHROPIC_API_KEY` | Enables Claude for reading documents (including Arabic OCR), the chat assistant and reading PDF quotations. Without it, a rule-based Arabic/English extractor runs instead. |
| `TP_AI_MODEL` | Defaults to `claude-opus-5-5`. |
| `TP_SECRET_KEY` | Session signing key. If it is not set, a random key is generated and saved in the data folder. |
| `TP_DATA_DIR` | Folder for uploaded files and the local database. |

Tests (all 20 steps through the API, permissions, the pricing engine, price references and the vendor register):
`cd backend && python -m pytest`. All 15 tests pass on SQLite and on PostgreSQL 16.

## Coverage

| Spec step | What the platform does |
|---|---|
| 1 Intake | Tender register with a fixed code, all key dates, a deadline-alerts dashboard and task assignment |
| 2 Go/No-Go | Weighted criteria set in Settings, a required reason, history of similar tenders, and an apology letter on No-Go |
| 3 Documents | Register with revisions and "latest revision" status, text extracted with page numbers, and addendum vs original comparison |
| 4–5 Analysis | Extraction of contract terms, risks and RFIs, each with file and page. The tender summary is approved term by term. Risk register (probability × impact) and RFI log with an RFI letter. Chat assistant over the documents. |
| 6 Site visit | Checklist by project type, photos with location, and issues turned into risks or overhead items |
| 7–8 BOQ | Import of the owner's Excel BOQ (header detection, merged cells, multi-row descriptions, sections, Arabic-Indic digits). Take-off check, automatic cost coding with approval, **Supply / Apply / Supply+Apply scope**, and packages (self-performed or subcontracted) |
| 9 RFQ | RFQ Excel file per package that is read back exactly. AI reading of PDF and e-mail quotes. Levelled comparison sheet (VAT, transport, discount, scope adjustment, currency). **Technical vs financial evaluation.** Lead-time, validity and unapproved-vendor warnings |
| 10 Rate build-up | Material, labour (productivity), equipment and subcontract lines, each tagged Supply or Apply. Price-source order: **quotation → library → previous project**. Templates, including priced ones |
| 11–14 | Schedule phases or S-curve, site overheads templates by project type, contingency from the risk register, material escalation and FX buffer, **price-adjustment clause**, finance cost from the cash flow, head-office overheads, bonds, insurance and taxes from Settings |
| 15–16 | Markup what-if scenarios (management only), proportional spreading with manual overrides, and a visible rounding difference |
| 17 Review | Automated checks (unpriced items, sum check, unapproved AI suggestions, old prices, outliers vs history, quote validity, lead time, unapproved vendor). Approval locks the version and freezes its exchange rates. Rejection returns it to stage 4 |
| 18–19 | **Priced BOQ written into the owner's own workbook**, internal estimate workbook, financial offer letter with a clarifications library, and submission checklist |
| 20 | Result, competitor prices, lessons learned, win rate by project type, and the approved estimate exported as the execution baseline budget |

**Spec design rules.**
1. Calculations run in fixed code.
2. Every suggestion shows its source.
3. A human approves before a suggestion affects the price, and the AI acceptance rate is measured.
4. Every price carries a date, currency and source, and the version keeps the exchange rate it used.
5. Versions and a full audit log are kept.
6. Excel comes first.
7. The interface is Arabic and English.
8. Permissions decide who sees markup and final prices.
9. Ratios live in Settings, not in code.

**The commercial review's changes.**
- Quotations are the first price source.
- Procurement is in the first release.
- Value-engineering alternatives are included.
- Supplier lead times are tracked.
- Imported items are linked to the FX scenarios.
- One user can hold several roles, with per-user permission adjustments.
- Real owner BOQs are used as test files.

**Later additions.**
- Price references from old priced files, adjusted by a cost index.
- Priced templates.
- Price-list import.
- Approved vendor register.
- Technical and financial quote evaluation.
- The research on 10 leading platforms led to adding index normalisation, colour flags against the references, price-adjustment clause modelling, and a clarifications library with an offer letter.

## Before go-live
- **Taxes.** The default VAT is 14% added on top, in line with the 2025 change that moved construction from the 5% schedule tax to 14% VAT. Confirm the rate and the input-VAT treatment with your tax adviser and set them in Settings.
- **Cost index.** The demo index values are illustrative only. Replace them with the CAPMAS bulletin or another index you rely on.
- **Starting prices.** The resource library, overhead templates and default ratios are starting values. Review them with the pricing team.
- **AI data use.** Confirm in writing that the AI provider does not train on company data (spec rule 8).
- **Database migrations.** Data-model changes after go-live need a migration tool (Alembic). The current setup creates the tables automatically.

## Next releases (per the spec and the research)
- Crew-based and parametric item analysis (HeavyBid, B2W).
- Take-off from PDF/CAD drawings, then BIM.
- Linking BOQ items to the programme and exporting to Primavera P6 or MS Project.
- An online RFQ portal for suppliers.
- Sending RFQs from inside the platform by e-mail.
- Separately priced alternates and options.
- Monte Carlo analysis for contingency.
- Actual costs feeding back into the library after award.
