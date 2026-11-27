"""News fetching from free RSS feeds (no key): Yahoo Finance per ticker, Google News for topics.
Returns structured items with published_at (NFR4: every news item shows its timestamp)."""
from __future__ import annotations

import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Callable

from src.utils.retry import with_retry

YAHOO_RSS = "https://feeds.finance.yahoo.com/rss/2.0/headline?s={s}&region=IN&lang=en-IN"
GOOGLE_RSS = "https://news.google.com/rss/search?q={q}&hl=en-IN&gl=IN&ceid=IN:en"


def _http_get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 FinAI-education"})
    with urllib.request.urlopen(req, timeout=10) as r:  # noqa: S310 - fixed https URLs
        return r.read()


def parse_rss(xml_bytes: bytes, source: str) -> list[dict]:
    root = ET.fromstring(xml_bytes)
    items = []
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        pub = it.findtext("pubDate")
        try:
            published = parsedate_to_datetime(pub) if pub else None
            if published and published.tzinfo is None:
                published = published.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            published = None
        src = it.findtext("source") or source
        if title and published:
            items.append({"headline": title, "url": link, "published_at": published, "source": src})
    return items


def fetch_news(query: str, days: int = 7, max_items: int = 8,
               http_get: Callable[[str], bytes] = _http_get, now: datetime | None = None,
               retry_sleep=None) -> dict:
    """query: a ticker like 'HDFCBANK.NS' (Yahoo feed) or free text like 'Indian IT sector' (Google News).
    Returns {"status": ok|no_news|error, "items": [...], "query", "source"}."""
    is_ticker = query.isupper() and " " not in query
    if is_ticker:
        url, source = YAHOO_RSS.format(s=urllib.parse.quote(query)), "Yahoo Finance"
    else:
        url, source = GOOGLE_RSS.format(q=urllib.parse.quote(f"{query} when:{days}d")), "Google News"
    kwargs = {"sleep": retry_sleep} if retry_sleep else {}
    try:
        raw = with_retry(lambda: http_get(url), **kwargs)
        items = parse_rss(raw, source)
    except Exception as e:  # noqa: BLE001
        return {"status": "error", "items": [], "query": query, "source": source, "error": str(e)}
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=days)
    seen, fresh = set(), []
    for it in sorted(items, key=lambda x: x["published_at"], reverse=True):
        key = it["headline"].lower()[:80]
        if it["published_at"] >= cutoff and key not in seen:
            seen.add(key)
            fresh.append({**it, "published_at": it["published_at"].strftime("%d-%b-%Y")})
    fresh = fresh[:max_items]
    return {"status": "ok" if fresh else "no_news", "items": fresh, "query": query, "source": source}
