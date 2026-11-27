"""All numbers FinAI shows are computed here, never by the LLM (NFR2). Pure functions."""
from __future__ import annotations

from collections import defaultdict

EQUITY_TYPES = {"stock", "equity_fund", "etf", "mutual_fund"}
DIVERSIFIED_TYPES = {"equity_fund", "etf", "mutual_fund", "debt_fund"}


def _num(v) -> float | None:
    """float or None (treats None, '', NaN and junk as missing)."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f != f else f


def _str(v) -> str | None:
    if v is None or (isinstance(v, float) and v != v):
        return None
    s = str(v).strip()
    return s or None


def _pct(part: float, total: float) -> float:
    return round(100 * part / total, 2) if total else 0.0


def analyze_portfolio(holdings: list[dict], prices: dict[str, float | None],
                      sectors: dict[str, str | None] | None = None,
                      single_stock_limit_pct: float = 20, single_sector_limit_pct: float = 40) -> dict:
    """holdings: [{symbol, quantity, avg_price, asset_type?, sector?, expense_ratio?, plan?}]
    prices: live price per symbol (None if unavailable -> falls back to buy price, flagged)."""
    if not holdings:
        return {"status": "empty", "message": "No holdings entered yet."}
    sectors = sectors or {}
    rows, total, invested = [], 0.0, 0.0
    by_sector: dict[str, float] = defaultdict(float)
    by_type: dict[str, float] = defaultdict(float)
    price_gaps = []
    for h in holdings:
        sym = str(h["symbol"]).strip()
        qty = _num(h.get("quantity")) or 0.0
        avg = _num(h.get("avg_price")) or 0.0
        if qty <= 0:
            continue
        atype = str(h.get("asset_type") or "stock").lower()
        live, entered = _num(prices.get(sym)), _num(h.get("current_price"))
        if live:
            price, basis = live, "live"
        elif entered:
            price, basis = entered, "entered"
        else:
            price, basis = avg, "buy price"
            price_gaps.append(sym)
        value, cost = qty * price, qty * avg
        if atype in DIVERSIFIED_TYPES:
            sector = _str(h.get("sector")) or {"debt_fund": "Debt fund"}.get(atype, "Diversified fund")
        else:
            sector = _str(h.get("sector")) or sectors.get(sym) or ("Gold" if atype == "gold" else "Other/unknown")
        rows.append({"symbol": sym, "asset_type": atype, "sector": sector, "quantity": qty,
                     "avg_price": round(avg, 2), "price": round(price, 2), "value": round(value, 2),
                     "invested": round(cost, 2), "pnl": round(value - cost, 2),
                     "pnl_pct": _pct(value - cost, cost), "live_price": bool(live), "price_basis": basis,
                     "expense_ratio": _num(h.get("expense_ratio")), "plan": _str(h.get("plan"))})
        total += value
        invested += cost
        by_sector[sector] += value
        by_type[atype] += value
    if total <= 0:
        return {"status": "empty", "message": "Holdings have no value."}
    for r in rows:
        r["weight_pct"] = _pct(r["value"], total)
    rows.sort(key=lambda r: r["value"], reverse=True)

    hhi_h = sum((r["value"] / total) ** 2 for r in rows)
    hhi_s = sum((v / total) ** 2 for v in by_sector.values())
    diversification = round(50 * (1 - hhi_h) + 50 * (1 - hhi_s))

    flags = []
    for r in rows:
        if r["asset_type"] == "stock" and r["weight_pct"] > single_stock_limit_pct:
            flags.append({"type": "single_stock", "name": r["symbol"], "weight_pct": r["weight_pct"],
                          "limit_pct": single_stock_limit_pct})
    for s, v in by_sector.items():
        w = _pct(v, total)
        if s not in ("Diversified fund", "Debt fund") and w > single_sector_limit_pct:
            flags.append({"type": "sector", "name": s, "weight_pct": w, "limit_pct": single_sector_limit_pct})

    equity_pct = _pct(sum(v for t, v in by_type.items() if t in EQUITY_TYPES), total)
    if equity_pct >= 80:
        risk = "High" if (flags or len(rows) < 5) else "Medium-high"
    elif equity_pct >= 50:
        risk = "Medium"
    else:
        risk = "Low"

    funds = [r for r in rows if r["expense_ratio"] is not None]
    fund_value = sum(r["value"] for r in funds)
    weighted_er = round(sum(r["value"] * float(r["expense_ratio"]) for r in funds) / fund_value, 2) if fund_value else None
    regular_plans = [r["symbol"] for r in rows if (r.get("plan") or "").lower() == "regular"]

    return {
        "status": "ok",
        "total_value": round(total, 2), "invested": round(invested, 2),
        "pnl": round(total - invested, 2), "pnl_pct": _pct(total - invested, invested),
        "holdings": rows,
        "sector_allocation": {k: _pct(v, total) for k, v in sorted(by_sector.items(), key=lambda kv: -kv[1])},
        "asset_allocation": {k: _pct(v, total) for k, v in sorted(by_type.items(), key=lambda kv: -kv[1])},
        "equity_pct": equity_pct,
        "diversification_score": diversification,
        "diversification_method": "0-100; half from spread across holdings, half across sectors (1 - HHI)",
        "concentration_flags": flags,
        "risk_level": risk,
        "weighted_expense_ratio_pct": weighted_er,
        "regular_plan_funds": regular_plans,
        "prices_unavailable_for": price_gaps,
    }


def project_goal(target_amount: float, years: float, current_savings: float, risk: str,
                 inflation_pct: float, expected_return_pct: dict[str, float],
                 assumptions_as_of: str = "", target_in_todays_money: bool = True) -> dict:
    """Monthly SIP needed to reach a goal. Target is in today's rupees unless stated otherwise."""
    if target_amount <= 0 or years <= 0:
        return {"status": "invalid", "message": "Target amount and years must be positive."}
    risk = (risk or "moderate").lower()
    if risk not in expected_return_pct:
        return {"status": "invalid", "message": f"Risk must be one of {sorted(expected_return_pct)}."}

    def sip_for(annual_pct: float) -> dict:
        a = annual_pct / 100
        r = (1 + a) ** (1 / 12) - 1
        n = round(years * 12)
        fv_target = target_amount * (1 + inflation_pct / 100) ** years if target_in_todays_money else target_amount
        fv_savings = current_savings * (1 + a) ** years
        gap = max(0.0, fv_target - fv_savings)
        factor = ((1 + r) ** n - 1) / r * (1 + r) if r else n
        sip = gap / factor if factor else gap
        return {"annual_return_pct": annual_pct, "future_target": round(fv_target),
                "savings_grow_to": round(fv_savings), "monthly_sip": round(sip),
                "lump_sum_today_instead": round(gap / (1 + a) ** years)}

    main = sip_for(expected_return_pct[risk])
    a = expected_return_pct[risk] / 100
    r = (1 + a) ** (1 / 12) - 1
    projection, value = [], current_savings
    for m in range(1, round(years * 12) + 1):
        value = (value + main["monthly_sip"]) * (1 + r)
        if m % 12 == 0 or m == round(years * 12):
            projection.append({"year": round(m / 12, 1), "value": round(value),
                               "invested": round(current_savings + main["monthly_sip"] * m)})
    return {
        "status": "ok", "target_today": round(target_amount), "years": years,
        "current_savings": round(current_savings), "risk": risk, "inflation_pct": inflation_pct,
        **main,
        "scenarios": {k: sip_for(v)["monthly_sip"] for k, v in expected_return_pct.items()},
        "projection": projection,
        "assumptions": f"{expected_return_pct[risk]}% yearly return for a {risk} profile, "
                       f"{inflation_pct}% inflation, as of {assumptions_as_of}. Returns are not guaranteed.",
    }
