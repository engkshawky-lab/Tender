"""Deterministic pricing engine (spec rule 1: calculations in code, never by the LLM).

Pure functions over plain dataclasses — no database, no AI — so every number is reproducible and testable
and can be reconciled line-by-line with the current Excel workbooks.

Cost build-up (spec steps 10–16):
    D  direct cost            Σ qty × Σ(coefficient × unit_price × (1+waste%) × fx)
    I  site overheads         time-related (monthly × qty × months) + fixed
    R  contingency            Σ(probability × impact) of included risks + general contingency % × D
    E  escalation             material escalation % × material cost + FX buffer % × foreign-currency cost
    H  head-office overheads  HO % × (D + I + R + E)
    C0 = D + I + R + E + H + bid-bond cost
    F  finance cost           from the monthly cash-flow (S-curve or schedule phases), solved by fixed-point iteration
    B  bonds & insurance      % of contract price (performance bond, advance-payment guarantee, CAR insurance)
    T  taxes included in price (configurable, % of price)
    Cost before profit  = C0 + F + B + T
    Profit              = markup% × Cost before profit
    Price P             = (C0 + F)(1+m) / (1 − p(1+m))   where p = Σ price-based percentages (B and T)
    VAT (taxes on top) shown separately. Provisional sums are added at face value, outside markup.
Spreading (step 16): P is distributed over priced items proportionally to direct cost, with manual overrides.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

ZERO = Decimal(0)
ONE = Decimal(1)
HUNDRED = Decimal(100)
KINDS = ("material", "labor", "equipment", "subcontract")
PARTS = ("supply", "apply", "supply_apply")


def dec(x) -> Decimal:
    if x is None or x == "":
        return ZERO
    if isinstance(x, Decimal):
        return x
    return Decimal(str(x))


def q2(x: Decimal, places: int = 2) -> Decimal:
    return x.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------- inputs
@dataclass
class LineIn:
    kind: str
    coefficient: Decimal
    unit_price: Decimal
    currency: str = "EGP"
    waste_pct: Decimal = ZERO
    part: str = "supply_apply"
    approved: bool = True
    id: int | None = None


@dataclass
class ItemIn:
    id: int
    quantity: Decimal
    lines: list[LineIn] = field(default_factory=list)
    is_provisional: bool = False
    provisional_amount: Decimal | None = None
    scope: str = "supply_apply"


@dataclass
class IndirectIn:
    kind: str  # time | fixed
    monthly_cost: Decimal = ZERO
    quantity: Decimal = ONE
    months: Decimal | None = None
    amount: Decimal = ZERO
    currency: str = "EGP"
    category: str = ""
    id: int | None = None


@dataclass
class RiskIn:
    probability_pct: Decimal
    impact_amount: Decimal
    id: int | None = None


@dataclass
class TaxIn:
    name: str
    rate_pct: Decimal
    mode: str = "on_top"  # on_top (VAT) | in_price (stamp duty, withholding...)


@dataclass
class PhaseIn:
    start_month: int
    duration_months: int
    weight_pct: Decimal


@dataclass
class Params:
    base_currency: str = "EGP"
    fx_rates: dict[str, Decimal] = field(default_factory=dict)
    duration_months: int = 12
    markup_pct: Decimal = ZERO
    ho_overhead_pct: Decimal = ZERO
    general_contingency_pct: Decimal = ZERO
    material_escalation_pct: Decimal = ZERO
    escalation_recovery_pct: Decimal = ZERO  # part of material escalation recovered through the price-adjustment clause
    fx_buffer_pct: Decimal = ZERO
    # bonds & insurance (as % of contract price)
    performance_bond_pct: Decimal = ZERO
    advance_guarantee_pct: Decimal = ZERO   # usually = advance payment %
    bond_commission_pa_pct: Decimal = ZERO  # bank commission per annum
    maintenance_months: int = 12
    insurance_pct: Decimal = ZERO
    bid_bond_amount: Decimal = ZERO
    bid_validity_days: int = 90
    # cash flow
    advance_payment_pct: Decimal = ZERO
    retention_pct: Decimal = ZERO
    payment_delay_months: int = 2
    finance_rate_pa_pct: Decimal = ZERO
    include_finance: bool = True
    taxes: list[TaxIn] = field(default_factory=list)
    # spreading
    spread_overrides: dict[int, dict] = field(default_factory=dict)  # {item_id: {"rate": x} | {"factor": f}}
    rate_decimals: int = 2


# ---------------------------------------------------------------- helpers
class PricingError(ValueError):
    pass


def fx_factor(currency: str, p: Params, missing: set[str]) -> Decimal:
    if not currency or currency == p.base_currency:
        return ONE
    rate = p.fx_rates.get(currency)
    if rate in (None, "", 0):
        missing.add(currency)
        return ZERO
    return dec(rate)


def line_unit_cost(line: LineIn, p: Params, missing: set[str]) -> Decimal:
    return dec(line.coefficient) * dec(line.unit_price) * (ONE + dec(line.waste_pct) / HUNDRED) * fx_factor(line.currency, p, missing)


def s_curve_weights(n: int) -> list[Decimal]:
    """Smoothstep S-curve: cumulative S(x)=3x²−2x³; monthly weight = S(t/n) − S((t−1)/n). Sums to exactly 1."""
    if n <= 0:
        return []
    def s(x: Decimal) -> Decimal:
        return 3 * x * x - 2 * x * x * x
    nd = Decimal(n)
    return [s(Decimal(t) / nd) - s(Decimal(t - 1) / nd) for t in range(1, n + 1)]


def phase_weights(phases: list[PhaseIn], n: int) -> list[Decimal]:
    total_w = sum((dec(ph.weight_pct) for ph in phases), ZERO)
    if not phases or total_w <= 0:
        return s_curve_weights(n)
    horizon = max(n, max(ph.start_month + ph.duration_months - 1 for ph in phases))
    w = [ZERO] * horizon
    for ph in phases:
        dur = max(1, ph.duration_months)
        share = dec(ph.weight_pct) / total_w / Decimal(dur)
        for m in range(ph.start_month, ph.start_month + dur):
            w[m - 1] += share
    return w


# ---------------------------------------------------------------- cash flow
def cash_flow(price: Decimal, cost_excl_finance: Decimal, weights: list[Decimal], p: Params) -> dict:
    """Monthly contractor cash position. Costs are paid in the month incurred; the work value is invoiced
    monthly and paid after `payment_delay_months`, net of retention and advance recovery. The advance is
    received in month 0 and retention released after the maintenance period. Finance cost = simple monthly
    interest on every negative month-end balance."""
    n = len(weights)
    delay = max(0, p.payment_delay_months)
    release_month = n + max(0, p.maintenance_months)
    horizon = max(n + delay, release_month) + 1
    adv = dec(p.advance_payment_pct) / HUNDRED
    ret = dec(p.retention_pct) / HUNDRED
    r_month = dec(p.finance_rate_pa_pct) / HUNDRED / Decimal(12)
    out = [ZERO] * (horizon + 1)
    inc = [ZERO] * (horizon + 1)
    inc[0] += adv * price
    for i, w in enumerate(weights, start=1):
        out[i] += w * cost_excl_finance
        inc[i + delay] += w * price * (ONE - ret - adv)
    inc[release_month] += ret * price
    rows, bal, finance = [], ZERO, ZERO
    for m in range(horizon + 1):
        bal += inc[m] - out[m]
        interest = -bal * r_month if bal < 0 else ZERO
        finance += interest
        rows.append({"month": m, "cost": out[m], "income": inc[m], "balance": bal, "interest": interest})
    return {"rows": rows, "finance_cost": finance,
            "peak_deficit": -min((r["balance"] for r in rows), default=ZERO)}


# ---------------------------------------------------------------- main
def compute(items: list[ItemIn], indirects: list[IndirectIn], risks: list[RiskIn], p: Params,
            phases: list[PhaseIn] | None = None) -> dict:
    missing_fx: set[str] = set()
    warnings: list[dict] = []

    # 1. direct cost per item, split by resource kind and by Supply / Apply part
    item_rows = []
    D = material_total = foreign_total = ZERO
    by_kind = {k: ZERO for k in KINDS}
    by_part = {k: ZERO for k in PARTS}
    provisional_total = ZERO
    for it in items:
        qty = dec(it.quantity)
        if it.is_provisional:
            amt = dec(it.provisional_amount)
            provisional_total += amt
            item_rows.append({"id": it.id, "quantity": qty, "provisional": True, "direct_rate": ZERO,
                              "direct_total": ZERO, "amount": amt, "by_kind": {}, "by_part": {}})
            continue
        unit_kind = {k: ZERO for k in KINDS}
        unit_part = {k: ZERO for k in PARTS}
        unit_foreign = ZERO
        unapproved = 0
        for ln in it.lines:
            c = line_unit_cost(ln, p, missing_fx)
            kind = ln.kind if ln.kind in KINDS else "material"
            part = ln.part if ln.part in PARTS else "supply_apply"
            unit_kind[kind] += c
            unit_part[part] += c
            if ln.currency and ln.currency != p.base_currency:
                unit_foreign += c
            if not ln.approved:
                unapproved += 1
        rate = sum(unit_kind.values(), ZERO)
        total = rate * qty
        D += total
        material_total += unit_kind["material"] * qty
        foreign_total += unit_foreign * qty
        for k in KINDS:
            by_kind[k] += unit_kind[k] * qty
        for k in PARTS:
            by_part[k] += unit_part[k] * qty
        item_rows.append({"id": it.id, "quantity": qty, "provisional": False, "direct_rate": rate,
                          "direct_total": total, "by_kind": unit_kind, "by_part": unit_part,
                          "foreign_rate": unit_foreign, "unapproved_lines": unapproved})

    # 2. site overheads
    n = max(1, int(p.duration_months or 1))
    I_time = I_fixed = ZERO
    indirect_rows = []
    for ind in indirects:
        fx = fx_factor(ind.currency, p, missing_fx)
        if ind.kind == "time":
            months = dec(ind.months) if ind.months not in (None, "") else Decimal(n)
            v = dec(ind.monthly_cost) * dec(ind.quantity) * months * fx
            I_time += v
        else:
            v = dec(ind.amount) * dec(ind.quantity or 1) * fx
            I_fixed += v
        indirect_rows.append({"id": ind.id, "category": ind.category, "total": v})
    I = I_time + I_fixed

    # 3. contingency & escalation
    R_risk = sum((dec(r.probability_pct) / HUNDRED * dec(r.impact_amount) for r in risks), ZERO)
    R_general = dec(p.general_contingency_pct) / HUNDRED * D
    R = R_risk + R_general
    carried = max(ZERO, dec(p.material_escalation_pct) - dec(p.escalation_recovery_pct))
    E_mat = carried / HUNDRED * material_total
    E_fx = dec(p.fx_buffer_pct) / HUNDRED * foreign_total
    E = E_mat + E_fx

    # 4. head office & bid bond
    H = dec(p.ho_overhead_pct) / HUNDRED * (D + I + R + E)
    bid_bond_cost = dec(p.bid_bond_amount) * dec(p.bond_commission_pa_pct) / HUNDRED * Decimal(p.bid_validity_days) / Decimal(365)
    C0 = D + I + R + E + H + bid_bond_cost

    # 5. price-based percentages (bonds, insurance, taxes included in price)
    bond_years = Decimal(n + max(0, p.maintenance_months)) / Decimal(12)
    adv_years = Decimal(n) / Decimal(12)
    comm = dec(p.bond_commission_pa_pct) / HUNDRED
    pct_items = {
        "performance_bond": dec(p.performance_bond_pct) / HUNDRED * comm * bond_years,
        # the advance-payment guarantee reduces as the advance is recovered → average outstanding = 50 %
        "advance_guarantee": dec(p.advance_guarantee_pct) / HUNDRED * comm * adv_years / Decimal(2),
        "insurance": dec(p.insurance_pct) / HUNDRED,
    }
    for t in p.taxes:
        if t.mode == "in_price":
            pct_items[f"tax:{t.name}"] = dec(t.rate_pct) / HUNDRED
    psum = sum(pct_items.values(), ZERO)
    m = dec(p.markup_pct) / HUNDRED
    denom = ONE - psum * (ONE + m)
    if denom <= 0:
        raise PricingError("Price-based percentages (bonds, insurance, in-price taxes) are too high to solve the price")

    weights = phase_weights(phases or [], n)

    def solve_price(F: Decimal) -> Decimal:
        return (C0 + F) * (ONE + m) / denom

    # 6. finance cost by fixed-point iteration (price depends on finance cost and vice versa)
    F = ZERO
    cf = None
    if p.include_finance and dec(p.finance_rate_pa_pct) > 0 and D > 0:
        for _ in range(100):
            price = solve_price(F)
            cost_excl_fin = C0 + psum * price
            cf = cash_flow(price, cost_excl_fin, weights, p)
            if abs(cf["finance_cost"] - F) < Decimal("0.0001"):
                F = cf["finance_cost"]
                break
            F = cf["finance_cost"]
    P = solve_price(F)
    cf = cash_flow(P, C0 + psum * P, weights, p)
    pct_amounts = {k: v * P for k, v in pct_items.items()}
    B = sum((v for k, v in pct_amounts.items() if not k.startswith("tax:")), ZERO)
    T_in = sum((v for k, v in pct_amounts.items() if k.startswith("tax:")), ZERO)
    cost_before_profit = C0 + F + B + T_in
    profit = P - cost_before_profit

    # 7. spreading indirects + profit over priced items (step 16)
    decimals = p.rate_decimals
    priced = [r for r in item_rows if not r["provisional"]]
    override_amount = ZERO
    rest_direct = ZERO
    for r in priced:
        ov = p.spread_overrides.get(r["id"]) or p.spread_overrides.get(str(r["id"]))
        r["override"] = ov or None
        if ov and ov.get("rate") not in (None, ""):
            r["_target_amount"] = dec(ov["rate"]) * r["quantity"]
            override_amount += r["_target_amount"]
        elif ov and ov.get("factor") not in (None, ""):
            r["_target_amount"] = r["direct_total"] * dec(ov["factor"])
            override_amount += r["_target_amount"]
        else:
            rest_direct += r["direct_total"]
    remaining = P - override_amount
    if rest_direct > 0:
        k = remaining / rest_direct
    else:
        k = ZERO
        if remaining != 0 and priced:
            warnings.append({"code": "spread_no_base", "message": "No item left to absorb the remaining amount"})
    submitted = ZERO
    for r in priced:
        if "_target_amount" in r:
            exact_rate = r["_target_amount"] / r["quantity"] if r["quantity"] else ZERO
        else:
            exact_rate = r["direct_rate"] * k
        r["final_rate"] = q2(exact_rate, decimals)
        r["amount"] = q2(r["final_rate"] * r["quantity"], 2)
        r["factor"] = (r["final_rate"] / r["direct_rate"]) if r["direct_rate"] else None
        r.pop("_target_amount", None)
        submitted += r["amount"]
    for r in item_rows:
        if r["provisional"]:
            r["final_rate"] = q2(r["amount"] / r["quantity"], decimals) if r["quantity"] else ZERO
            submitted += q2(r["amount"], 2)
    total_excl_vat = P + provisional_total
    rounding_diff = submitted - total_excl_vat

    vat_rows = []
    for t in p.taxes:
        if t.mode == "on_top":
            vat_rows.append({"name": t.name, "rate_pct": dec(t.rate_pct), "amount": submitted * dec(t.rate_pct) / HUNDRED})
    vat_total = sum((v["amount"] for v in vat_rows), ZERO)

    if missing_fx:
        warnings.append({"code": "missing_fx", "message": f"Missing exchange rate for: {', '.join(sorted(missing_fx))}",
                         "currencies": sorted(missing_fx)})

    return {
        "items": item_rows,
        "indirects": indirect_rows,
        "summary": {
            "direct": D, "direct_by_kind": by_kind, "direct_by_part": by_part,
            "material_cost": material_total, "foreign_cost": foreign_total,
            "site_overheads": I, "site_overheads_time": I_time, "site_overheads_fixed": I_fixed,
            "contingency": R, "contingency_risks": R_risk, "contingency_general": R_general,
            "escalation": E, "escalation_material": E_mat, "escalation_fx": E_fx,
            "escalation_recovery_pct": dec(p.escalation_recovery_pct), "escalation_carried_pct": carried,
            "ho_overheads": H, "bid_bond_cost": bid_bond_cost,
            "finance": F, "bonds_insurance": B, "bonds_breakdown": {k: v for k, v in pct_amounts.items() if not k.startswith("tax:")},
            "taxes_in_price": T_in, "taxes_in_price_breakdown": {k[4:]: v for k, v in pct_amounts.items() if k.startswith("tax:")},
            "cost_before_profit": cost_before_profit, "profit": profit,
            "markup_pct": dec(p.markup_pct), "margin_on_price_pct": (profit / P * HUNDRED) if P else ZERO,
            "price": P, "provisional_sums": provisional_total, "total_excl_vat": total_excl_vat,
            "submitted_total": submitted, "rounding_diff": rounding_diff,
            "vat": vat_rows, "vat_total": vat_total, "total_incl_vat": submitted + vat_total,
            "spread_factor": k, "peak_cash_deficit": cf["peak_deficit"],
        },
        "cash_flow": cf["rows"],
        "warnings": warnings,
    }


def price_adjustment_recovery(components: list[dict]) -> Decimal:
    """Contract price-adjustment formula P = a + Σ wᵢ·Iᵢ/Iᵢ₀ (FIDIC 13.7 style). With expected index changes Δᵢ %
    over the contract, the recovered escalation as % of the adjustable value is Σ wᵢ·Δᵢ (wᵢ as fractions; a is fixed)."""
    return sum((dec(c.get("weight")) / HUNDRED * dec(c.get("expected_change_pct")) for c in components or []), ZERO)


def what_if(items, indirects, risks, p: Params, phases, markups: list) -> list[dict]:
    """Step 15 — 'what if' scenarios: same cost base, different markup."""
    out = []
    for mk in markups:
        pp = Params(**{**p.__dict__, "markup_pct": dec(mk), "spread_overrides": {}})
        s = compute(items, indirects, risks, pp, phases)["summary"]
        out.append({"markup_pct": dec(mk), "price": s["price"], "total_excl_vat": s["total_excl_vat"],
                    "profit": s["profit"], "total_incl_vat": s["total_excl_vat"] + sum((v["rate_pct"] / HUNDRED * s["total_excl_vat"] for v in s["vat"]), ZERO)})
    return out


def to_jsonable(obj):
    """Decimals → float (rounded to 4 dp) for API responses; the frozen snapshot keeps strings."""
    if isinstance(obj, Decimal):
        return float(q2(obj, 4))
    if isinstance(obj, dict):
        return {str(k): to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(v) for v in obj]
    return obj
