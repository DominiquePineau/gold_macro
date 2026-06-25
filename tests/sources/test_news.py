"""Tests du flux news RSS (app/sources/news.py)."""
from __future__ import annotations

from app.sentiment.models import NewsItem
from app.sources.news import NewsProvider, _is_relevant, parse_rss

_RSS = """<?xml version="1.0"?><rss><channel>
<item><title>Gold price falls below $4,000 ahead of US PCE</title>
<pubDate>Thu, 25 Jun 2026 11:00:00 GMT</pubDate></item>
<item><title>Fed officials signal caution on rate cuts</title>
<pubDate>Thu, 25 Jun 2026 09:00:00 GMT</pubDate></item>
<item><title>Local football team wins championship</title>
<pubDate>Thu, 25 Jun 2026 08:00:00 GMT</pubDate></item>
</channel></rss>"""


def test_parse_rss_extracts_items():
    items = parse_rss(_RSS, "test")
    assert len(items) == 3
    assert items[0].text.startswith("Gold price")
    assert items[0].published is not None
    assert items[0].source == "test"


def test_parse_rss_bad_xml_empty():
    assert parse_rss("not xml", "t") == []


def test_relevance_filter():
    assert _is_relevant("Gold rallies on Fed dovish turn") is True
    assert _is_relevant("Local football team wins") is False


class _Resp:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        return None


class _Client:
    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, **k):
        return _Resp(_RSS)


async def test_fetch_filters_and_sorts(monkeypatch):
    import app.sources.news as news
    monkeypatch.setattr(news.httpx, "AsyncClient", _Client)
    prov = NewsProvider(feeds=[("t", "http://x")], max_items=8)
    items = await prov.fetch_headlines()
    # le football (non pertinent) est filtré -> 2 items macro/or
    assert len(items) == 2
    assert all(_is_relevant(i.text) for i in items)
    # tri par fraîcheur : le plus récent (11:00) d'abord
    assert items[0].published >= items[1].published


async def test_fetch_dedupes(monkeypatch):
    import app.sources.news as news

    class _Dup(_Client):
        async def get(self, url, **k):
            dup = _RSS.replace("</channel>",
                               "<item><title>Gold price falls below $4,000 ahead of US PCE</title></item></channel>")
            return _Resp(dup)

    monkeypatch.setattr(news.httpx, "AsyncClient", _Dup)
    items = await NewsProvider(feeds=[("t", "http://x")]).fetch_headlines()
    titles = [i.text for i in items]
    assert len(titles) == len(set(t.lower() for t in titles))  # pas de doublon


async def test_degraded_all_feeds_fail(monkeypatch):
    import app.sources.news as news

    class _Boom(_Client):
        async def get(self, url, **k):
            raise RuntimeError("feed down")

    monkeypatch.setattr(news.httpx, "AsyncClient", _Boom)
    items = await NewsProvider(feeds=[("t", "http://x")]).fetch_headlines()
    assert items == []  # aucune exception, liste vide


async def test_max_items_cap(monkeypatch):
    import app.sources.news as news
    monkeypatch.setattr(news.httpx, "AsyncClient", _Client)
    prov = NewsProvider(feeds=[("t", "http://x")], max_items=1)
    assert len(await prov.fetch_headlines()) == 1


async def test_cache_avoids_refetch(monkeypatch):
    import app.sources.news as news
    calls = {"n": 0}

    class _Counting(_Client):
        async def get(self, url, **k):
            calls["n"] += 1
            return _Resp(_RSS)

    monkeypatch.setattr(news.httpx, "AsyncClient", _Counting)
    prov = NewsProvider(feeds=[("t", "http://x")], cache_ttl_seconds=3600)
    await prov.fetch_headlines()
    await prov.fetch_headlines()  # dans la TTL -> servi du cache
    assert calls["n"] == 1


async def test_no_cache_refetches(monkeypatch):
    import app.sources.news as news
    calls = {"n": 0}

    class _Counting(_Client):
        async def get(self, url, **k):
            calls["n"] += 1
            return _Resp(_RSS)

    monkeypatch.setattr(news.httpx, "AsyncClient", _Counting)
    prov = NewsProvider(feeds=[("t", "http://x")], cache_ttl_seconds=0)  # pas de cache
    await prov.fetch_headlines()
    await prov.fetch_headlines()
    assert calls["n"] == 2
