import math

from src.utils.finance_math import analyze_portfolio, project_goal

RET = {"cautious": 8.0, "moderate": 10.0, "aggressive": 12.0}


def test_portfolio_totals_and_pnl():
    h = [{"symbol": "INFY.NS", "quantity": 10, "avg_price": 1000},
         {"symbol": "HDFCBANK.NS", "quantity": 10, "avg_price": 1500}]
    a = analyze_portfolio(h, {"INFY.NS": 1200, "HDFCBANK.NS": 1500}, {"INFY.NS": "IT", "HDFCBANK.NS": "Financials"})
    assert a["status"] == "ok"
    assert a["total_value"] == 27000 and a["invested"] == 25000 and a["pnl"] == 2000
    assert a["pnl_pct"] == 8.0
    assert math.isclose(sum(r["weight_pct"] for r in a["holdings"]), 100, abs_tol=0.05)


def test_concentration_flags_stock_and_sector():
    h = [{"symbol": "INFY.NS", "quantity": 60, "avg_price": 100},
         {"symbol": "TCS.NS", "quantity": 30, "avg_price": 100},
         {"symbol": "ITC.NS", "quantity": 10, "avg_price": 100}]
    sectors = {"INFY.NS": "IT", "TCS.NS": "IT", "ITC.NS": "Consumer"}
    a = analyze_portfolio(h, {k: 100 for k in sectors}, sectors, 20, 40)
    types = {(f["type"], f["name"]) for f in a["concentration_flags"]}
    assert ("single_stock", "INFY.NS") in types and ("sector", "IT") in types
    assert a["risk_level"] == "High"


def test_funds_not_flagged_as_single_stock_and_expense_ratio():
    h = [{"symbol": "Index Fund", "quantity": 100, "avg_price": 10, "asset_type": "mutual_fund",
          "current_price": 12, "expense_ratio": 0.2, "plan": "direct"},
         {"symbol": "Active Fund", "quantity": 100, "avg_price": 10, "asset_type": "mutual_fund",
          "current_price": 12, "expense_ratio": 1.8, "plan": "regular"}]
    a = analyze_portfolio(h, {})
    assert not [f for f in a["concentration_flags"] if f["type"] == "single_stock"]
    assert a["weighted_expense_ratio_pct"] == 1.0
    assert a["regular_plan_funds"] == ["Active Fund"]
    assert a["total_value"] == 2400


def test_missing_price_falls_back_and_is_reported():
    a = analyze_portfolio([{"symbol": "X.NS", "quantity": 1, "avg_price": 50}], {"X.NS": None})
    assert a["total_value"] == 50 and a["prices_unavailable_for"] == ["X.NS"]


def test_nan_and_empty_inputs_are_safe():
    assert analyze_portfolio([], {})["status"] == "empty"
    a = analyze_portfolio([{"symbol": "A", "quantity": 1, "avg_price": 10, "expense_ratio": float("nan"),
                            "sector": float("nan"), "current_price": float("nan")}], {})
    assert a["total_value"] == 10 and a["weighted_expense_ratio_pct"] is None


def test_goal_sip_matches_annuity_due_formula():
    r = project_goal(2_500_000, 8, 300_000, "moderate", 6.0, RET, "2026-11-01")
    assert r["status"] == "ok"
    assert r["future_target"] == round(2_500_000 * 1.06 ** 8)
    monthly = 1.10 ** (1 / 12) - 1
    n = 96
    gap = r["future_target"] - 300_000 * 1.10 ** 8
    expected = gap / (((1 + monthly) ** n - 1) / monthly * (1 + monthly))
    assert abs(r["monthly_sip"] - expected) < 1
    assert r["scenarios"]["cautious"] > r["scenarios"]["moderate"] > r["scenarios"]["aggressive"]
    assert abs(r["projection"][-1]["value"] - r["future_target"]) / r["future_target"] < 0.01


def test_goal_already_funded_and_invalid_inputs():
    r = project_goal(100_000, 10, 1_000_000, "cautious", 6.0, RET)
    assert r["monthly_sip"] == 0
    assert project_goal(0, 5, 0, "moderate", 6, RET)["status"] == "invalid"
    assert project_goal(100, 5, 0, "yolo", 6, RET)["status"] == "invalid"
