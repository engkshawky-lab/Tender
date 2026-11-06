"""Hand-checked cases for the deterministic engine — the same arithmetic an estimator does in Excel."""
from decimal import Decimal as D

import pytest

from app.engine.pricing import (IndirectIn, ItemIn, LineIn, Params, PhaseIn, PricingError, RiskIn, TaxIn,
                                compute, s_curve_weights)


def simple_items():
    # Item 1: 100 m3 RC — material 1.05 m3 concrete @ 2,000 + 2 % waste, labour 1/4 day @ 800, equipment 0.5 h @ 400
    it1 = ItemIn(1, D(100), [
        LineIn("material", D("1.05"), D(2000), waste_pct=D(2), part="supply"),
        LineIn("labor", D("0.25"), D(800), part="apply"),
        LineIn("equipment", D("0.5"), D(400), part="apply"),
    ])
    # Item 2: 50 m2 imported tiles, Supply + Apply split — supply in USD, apply by installer in EGP
    it2 = ItemIn(2, D(50), [
        LineIn("material", D(1), D(20), currency="USD", part="supply"),
        LineIn("subcontract", D(1), D(150), part="apply"),
    ])
    return [it1, it2]


def test_direct_cost_build_up_and_supply_apply_split():
    p = Params(fx_rates={"USD": D(50)}, duration_months=10)
    r = compute(simple_items(), [], [], p)
    rows = {x["id"]: x for x in r["items"]}
    # 1.05*2000*1.02 = 2142 ; 0.25*800 = 200 ; 0.5*400 = 200  → 2542 / m3
    assert rows[1]["direct_rate"] == D("2542")
    # 20*50 + 150 = 1150 / m2
    assert rows[2]["direct_rate"] == D("1150")
    s = r["summary"]
    assert s["direct"] == D("254200") + D("57500")
    assert s["direct_by_part"]["supply"] == D(2142 * 100 + 1000 * 50)
    assert s["direct_by_part"]["apply"] == D(400 * 100 + 150 * 50)
    assert s["foreign_cost"] == D(50000)
    # no markup, no indirects → price equals direct cost
    assert s["price"] == s["direct"]
    assert s["submitted_total"] == s["direct"]


def test_full_chain_matches_manual_calculation():
    items = [ItemIn(1, D(10), [LineIn("subcontract", D(1), D(1000))])]  # D = 10,000
    ind = [IndirectIn("time", monthly_cost=D(100), quantity=D(2), months=None),  # 100*2*10 = 2,000
           IndirectIn("fixed", amount=D(500))]                                   # 500
    risks = [RiskIn(D(50), D(1000))]                                            # 500
    p = Params(duration_months=10, general_contingency_pct=D(1),                 # 100
               ho_overhead_pct=D(5), markup_pct=D(10), insurance_pct=D(1),
               taxes=[TaxIn("VAT", D(14), "on_top")])
    s = compute(items, ind, risks, p)["summary"]
    assert s["site_overheads"] == D(2500)
    assert s["contingency"] == D(600)
    H = D("0.05") * (D(10000) + D(2500) + D(600))
    assert s["ho_overheads"] == H
    C0 = D(10000) + D(2500) + D(600) + H
    expected_price = C0 * D("1.1") / (1 - D("0.01") * D("1.1"))
    assert s["price"] == expected_price
    # insurance is exactly 1 % of price, profit exactly 10 % of cost before profit
    assert abs(s["bonds_insurance"] - expected_price * D("0.01")) < D("0.0000001")
    assert abs(s["profit"] - s["cost_before_profit"] * D("0.10")) < D("0.0000001")
    assert s["vat_total"] == s["submitted_total"] * D("0.14")


def test_spreading_proportional_and_manual_override_keeps_total():
    items = [ItemIn(1, D(10), [LineIn("material", D(1), D(100))]),
             ItemIn(2, D(20), [LineIn("material", D(1), D(50))]),
             ItemIn(3, D(1), [], is_provisional=True, provisional_amount=D(5000))]
    p = Params(markup_pct=D(20), spread_overrides={1: {"rate": D(130)}})
    r = compute(items, [], [], p)
    s = r["summary"]
    assert s["price"] == D(2400)                           # (1000+1000) * 1.2
    rows = {x["id"]: x for x in r["items"]}
    assert rows[1]["final_rate"] == D("130.00")           # manual rate
    assert rows[2]["amount"] == D("1100.00")              # remainder 2400-1300 absorbed by item 2
    assert rows[3]["amount"] == D(5000)                   # provisional sum untouched
    assert s["submitted_total"] == D(2400) + D(5000)
    assert s["rounding_diff"] == 0


def test_rounding_difference_is_reported_not_hidden():
    items = [ItemIn(1, D(3), [LineIn("material", D(1), D(100))])]
    p = Params(markup_pct=D("7.777"))
    s = compute(items, [], [], p)["summary"]
    assert s["submitted_total"] == D("323.34")             # 3 × 107.78
    assert s["rounding_diff"] == s["submitted_total"] - s["price"]


def test_finance_cost_positive_with_delay_and_retention():
    items = [ItemIn(1, D(1), [LineIn("subcontract", D(1), D(1_000_000))])]
    p = Params(duration_months=6, markup_pct=D(10), retention_pct=D(5), payment_delay_months=2,
               finance_rate_pa_pct=D(24), maintenance_months=12)
    s = compute(items, [], [], p)["summary"]
    assert s["finance"] > 0
    assert s["price"] > D(1_100_000)
    # an advance payment reduces the finance cost
    p2 = Params(**{**p.__dict__, "advance_payment_pct": D(20)})
    assert compute(items, [], [], p2)["summary"]["finance"] < s["finance"]


def test_missing_fx_rate_is_flagged():
    items = [ItemIn(1, D(1), [LineIn("material", D(1), D(10), currency="EUR")])]
    r = compute(items, [], [], Params())
    assert any(w["code"] == "missing_fx" for w in r["warnings"])


def test_s_curve_sums_to_one_and_phases_respected():
    w = s_curve_weights(12)
    assert abs(sum(w) - 1) < D("1e-20")
    assert w[0] < w[5]
    items = [ItemIn(1, D(1), [LineIn("subcontract", D(1), D(1000))])]
    p = Params(duration_months=4, finance_rate_pa_pct=D(12))
    r = compute(items, [], [], p, [PhaseIn(1, 2, D(50)), PhaseIn(3, 2, D(50))])
    months = [row["cost"] for row in r["cash_flow"][1:5]]
    assert all(abs(m - months[0]) < D("0.0001") for m in months)


def test_impossible_percentages_raise():
    items = [ItemIn(1, D(1), [LineIn("material", D(1), D(10))])]
    with pytest.raises(PricingError):
        compute(items, [], [], Params(markup_pct=D(10), insurance_pct=D(95)))


def test_price_adjustment_clause_reduces_carried_escalation():
    from app.engine.pricing import price_adjustment_recovery
    items = [ItemIn(1, D(100), [LineIn("material", D(1), D(1000))])]           # material 100,000
    rec = price_adjustment_recovery([{"weight": 30, "expected_change_pct": 20}, {"weight": 20, "expected_change_pct": 10}])
    assert rec == D(8)                                                          # 0.3×20 + 0.2×10
    s0 = compute(items, [], [], Params(material_escalation_pct=D(12)))["summary"]
    s1 = compute(items, [], [], Params(material_escalation_pct=D(12), escalation_recovery_pct=rec))["summary"]
    assert s0["escalation_material"] == D(12000) and s1["escalation_material"] == D(4000)
    s2 = compute(items, [], [], Params(material_escalation_pct=D(5), escalation_recovery_pct=rec))["summary"]
    assert s2["escalation_material"] == 0                                       # never negative
