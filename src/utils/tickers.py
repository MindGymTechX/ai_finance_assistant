"""Name -> NSE ticker aliases and sectors for common Indian large caps and indices.
Used for FR5 name resolution and for portfolio sector mix without a slow API call."""
from __future__ import annotations

import re

INDICES = {
    "nifty": "^NSEI", "nifty 50": "^NSEI", "nifty50": "^NSEI",
    "sensex": "^BSESN", "bse sensex": "^BSESN",
    "bank nifty": "^NSEBANK", "nifty bank": "^NSEBANK",
    "nifty it": "^CNXIT",
}

# ticker (without suffix) -> (display name, sector, extra aliases)
COMPANIES: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "RELIANCE": ("Reliance Industries", "Energy", ("reliance", "ril")),
    "TCS": ("Tata Consultancy Services", "IT", ("tcs", "tata consultancy")),
    "INFY": ("Infosys", "IT", ("infosys",)),
    "HCLTECH": ("HCL Technologies", "IT", ("hcl", "hcl tech")),
    "WIPRO": ("Wipro", "IT", ("wipro",)),
    "TECHM": ("Tech Mahindra", "IT", ("tech mahindra",)),
    "LTIM": ("LTIMindtree", "IT", ("ltimindtree", "lti mindtree")),
    "HDFCBANK": ("HDFC Bank", "Financials", ("hdfc bank", "hdfc")),
    "ICICIBANK": ("ICICI Bank", "Financials", ("icici bank", "icici")),
    "SBIN": ("State Bank of India", "Financials", ("sbi", "state bank")),
    "KOTAKBANK": ("Kotak Mahindra Bank", "Financials", ("kotak", "kotak bank")),
    "AXISBANK": ("Axis Bank", "Financials", ("axis bank", "axis")),
    "BAJFINANCE": ("Bajaj Finance", "Financials", ("bajaj finance",)),
    "BAJAJFINSV": ("Bajaj Finserv", "Financials", ("bajaj finserv",)),
    "LICI": ("Life Insurance Corporation", "Financials", ("lic",)),
    "HINDUNILVR": ("Hindustan Unilever", "Consumer", ("hul", "hindustan unilever")),
    "ITC": ("ITC", "Consumer", ("itc",)),
    "NESTLEIND": ("Nestle India", "Consumer", ("nestle",)),
    "BRITANNIA": ("Britannia Industries", "Consumer", ("britannia",)),
    "TATACONSUM": ("Tata Consumer Products", "Consumer", ("tata consumer",)),
    "ASIANPAINT": ("Asian Paints", "Consumer", ("asian paints",)),
    "TITAN": ("Titan Company", "Consumer", ("titan",)),
    "MARUTI": ("Maruti Suzuki", "Auto", ("maruti", "maruti suzuki")),
    "TATAMOTORS": ("Tata Motors", "Auto", ("tata motors",)),
    "M&M": ("Mahindra & Mahindra", "Auto", ("mahindra", "m&m")),
    "BAJAJ-AUTO": ("Bajaj Auto", "Auto", ("bajaj auto",)),
    "EICHERMOT": ("Eicher Motors", "Auto", ("eicher", "royal enfield")),
    "SUNPHARMA": ("Sun Pharmaceutical", "Healthcare", ("sun pharma",)),
    "DRREDDY": ("Dr. Reddy's Laboratories", "Healthcare", ("dr reddy", "dr reddys")),
    "CIPLA": ("Cipla", "Healthcare", ("cipla",)),
    "APOLLOHOSP": ("Apollo Hospitals", "Healthcare", ("apollo",)),
    "LT": ("Larsen & Toubro", "Industrials", ("l&t", "larsen")),
    "ADANIENT": ("Adani Enterprises", "Industrials", ("adani enterprises", "adani")),
    "ADANIPORTS": ("Adani Ports", "Industrials", ("adani ports",)),
    "ULTRACEMCO": ("UltraTech Cement", "Materials", ("ultratech",)),
    "TATASTEEL": ("Tata Steel", "Materials", ("tata steel",)),
    "JSWSTEEL": ("JSW Steel", "Materials", ("jsw steel",)),
    "HINDALCO": ("Hindalco Industries", "Materials", ("hindalco",)),
    "NTPC": ("NTPC", "Utilities", ("ntpc",)),
    "POWERGRID": ("Power Grid Corporation", "Utilities", ("power grid",)),
    "TATAPOWER": ("Tata Power", "Utilities", ("tata power",)),
    "ONGC": ("ONGC", "Energy", ("ongc",)),
    "COALINDIA": ("Coal India", "Energy", ("coal india",)),
    "BHARTIARTL": ("Bharti Airtel", "Telecom", ("airtel", "bharti airtel")),
    "ZOMATO": ("Zomato (Eternal)", "Consumer", ("zomato", "eternal")),
    "DMART": ("Avenue Supermarts (DMart)", "Consumer", ("dmart", "avenue supermarts")),
    "NIFTYBEES": ("Nippon India Nifty 50 BeES ETF", "Index ETF", ("niftybees", "nifty bees")),
    "GOLDBEES": ("Nippon India Gold BeES ETF", "Gold", ("goldbees", "gold bees")),
}

_TICKER_RE = re.compile(r"^[A-Z0-9&\-]{2,15}(\.(NS|BO))?$")


def sector_of(ticker: str) -> str | None:
    base = ticker.split(".")[0].upper()
    return COMPANIES.get(base, (None, None, ()))[1]


def name_of(ticker: str) -> str | None:
    base = ticker.split(".")[0].upper()
    return COMPANIES.get(base, (None, None, ()))[0]


def resolve(query: str, suffix: str = ".NS") -> dict:
    """Return {"status": "ok", "ticker", "name"} | {"status": "ambiguous", "candidates"} | {"status": "not_found"}."""
    q = query.strip()
    ql = q.lower()
    if ql in INDICES:
        return {"status": "ok", "ticker": INDICES[ql], "name": q.title()}
    if q.startswith("^"):
        return {"status": "ok", "ticker": q.upper(), "name": q.upper()}
    base = q.upper().split(".")[0]
    if base in COMPANIES:
        return {"status": "ok", "ticker": base + suffix if "." not in q else q.upper(), "name": COMPANIES[base][0]}
    exact = [t for t, (_, _, al) in COMPANIES.items() if ql in al or ql == COMPANIES[t][0].lower()]
    if len(exact) == 1:
        return {"status": "ok", "ticker": exact[0] + suffix, "name": COMPANIES[exact[0]][0]}
    partial = sorted({t for t, (name, _, al) in COMPANIES.items()
                      if ql in name.lower() or any(ql in a for a in al)})
    if len(partial) == 1:
        return {"status": "ok", "ticker": partial[0] + suffix, "name": COMPANIES[partial[0]][0]}
    if len(partial) > 1:
        return {"status": "ambiguous",
                "candidates": [{"ticker": t + suffix, "name": COMPANIES[t][0]} for t in partial]}
    if q == q.upper() and _TICKER_RE.match(q):  # looks like a ticker we don't know: trust it
        return {"status": "ok", "ticker": q if "." in q else q + suffix, "name": q}
    return {"status": "not_found"}
