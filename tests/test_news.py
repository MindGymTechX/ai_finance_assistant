from datetime import datetime, timezone

from src.utils.news import fetch_news, parse_rss

RSS = b"""<?xml version="1.0"?><rss><channel>
<item><title>HDFC Bank Q2 profit rises</title><link>https://ex.com/1</link><pubDate>Mon, 16 Nov 2026 10:00:00 GMT</pubDate></item>
<item><title>HDFC Bank Q2 profit rises</title><link>https://ex.com/dup</link><pubDate>Mon, 16 Nov 2026 09:00:00 GMT</pubDate></item>
<item><title>Old story</title><link>https://ex.com/old</link><pubDate>Mon, 02 Nov 2026 10:00:00 GMT</pubDate></item>
<item><title>No date</title><link>https://ex.com/x</link></item>
</channel></rss>"""
NOW = datetime(2026, 11, 18, tzinfo=timezone.utc)


def test_parse_rss_skips_undated():
    assert len(parse_rss(RSS, "Yahoo Finance")) == 3


def test_fetch_filters_old_and_duplicates():
    r = fetch_news("HDFCBANK.NS", days=7, http_get=lambda url: RSS, now=NOW)
    assert r["status"] == "ok" and r["source"] == "Yahoo Finance"
    assert [i["headline"] for i in r["items"]] == ["HDFC Bank Q2 profit rises"]
    assert r["items"][0]["published_at"] == "16-Nov-2026"


def test_topic_uses_google_news_and_no_news():
    seen = {}

    def get(url):
        seen["url"] = url
        return b"<rss><channel></channel></rss>"
    r = fetch_news("Indian IT sector", http_get=get, now=NOW)
    assert "news.google.com" in seen["url"] and r["status"] == "no_news"


def test_error_is_not_no_news():
    def boom(url):
        raise TimeoutError("down")
    r = fetch_news("INFY.NS", http_get=boom, retry_sleep=lambda s: None)
    assert r["status"] == "error" and r["items"] == []
