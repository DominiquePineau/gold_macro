"""Tests du flux prix (app/sources/price.py) — IG mocké, read-only, mode dégradé."""
from __future__ import annotations

import pytest

from app.sources.price import IGPriceFeed, StaticPriceFeed


async def test_static_feed():
    assert await StaticPriceFeed(2400.0)() == 2400.0
    assert await StaticPriceFeed(None)() is None


async def test_ig_no_credentials_returns_none(monkeypatch):
    for v in ("IG_API_KEY", "IG_USERNAME", "IG_PASSWORD"):
        monkeypatch.delenv(v, raising=False)
    assert await IGPriceFeed()() is None


class _Resp:
    def __init__(self, payload, headers=None):
        self._p = payload
        self.headers = headers or {}

    def raise_for_status(self):
        return None

    def json(self):
        return self._p


class _IGClient:
    """Fausse session IG : /session puis /markets/{epic}."""
    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, **k):  # /session
        return _Resp({}, headers={"CST": "cst123", "X-SECURITY-TOKEN": "xst123"})

    async def get(self, url, **k):   # /markets/{epic}
        return _Resp({"snapshot": {"bid": 4190.0, "offer": 4192.0}})


async def test_ig_price_mid(monkeypatch):
    import app.sources.price as price
    monkeypatch.setattr(price.httpx, "AsyncClient", _IGClient)
    feed = IGPriceFeed(api_key="k", username="u", password="p")
    assert await feed.price() == pytest.approx(4191.0)  # mid (4190+4192)/2


async def test_ig_session_cached(monkeypatch):
    import app.sources.price as price
    calls = {"auth": 0}

    class _C(_IGClient):
        async def post(self, url, **k):
            calls["auth"] += 1
            return _Resp({}, headers={"CST": "c", "X-SECURITY-TOKEN": "x"})

    monkeypatch.setattr(price.httpx, "AsyncClient", _C)
    feed = IGPriceFeed(api_key="k", username="u", password="p")
    await feed.price()
    await feed.price()
    assert calls["auth"] == 1  # session réutilisée, pas de ré-auth


async def test_ig_degraded_on_error(monkeypatch):
    import app.sources.price as price

    class _Boom(_IGClient):
        async def post(self, url, **k):
            raise RuntimeError("IG down")

    monkeypatch.setattr(price.httpx, "AsyncClient", _Boom)
    feed = IGPriceFeed(api_key="k", username="u", password="p")
    assert await feed.price() is None  # pas d'exception, prix absent ce cycle
