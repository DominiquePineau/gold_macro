"""Tests du connecteur COT CFTC (app/sources/cot.py) — fixture + cache + dégradé."""
from __future__ import annotations

import pytest

from app.sources.cot import CotProvider, CotSnapshot, parse_cot_row

# Échantillon fixturé d'une ligne CFTC (champs réels du dataset kh3c-gbw2).
_FIXTURE_ROW = {
    "report_date_as_yyyy_mm_dd": "2026-06-16T00:00:00.000",
    "market_and_exchange_names": "GOLD - COMMODITY EXCHANGE INC.",
    "m_money_positions_long_all": "128528",
    "m_money_positions_short_all": "15610",
}


def test_parse_cot_row_net():
    snap = parse_cot_row(_FIXTURE_ROW)
    assert snap.long_all == 128528.0
    assert snap.short_all == 15610.0
    assert snap.net == pytest.approx(112918.0)
    assert snap.report_date.startswith("2026-06-16")


class _FakeResp:
    def __init__(self, payload):
        self._p = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._p


class _FakeClient:
    payload = [_FIXTURE_ROW]

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, *a, **k):
        return _FakeResp(self.payload)


async def test_fetch_latest_parses(monkeypatch):
    import app.sources.cot as cot
    monkeypatch.setattr(cot.httpx, "AsyncClient", _FakeClient)
    snap = await CotProvider().fetch_latest()
    assert snap.net == pytest.approx(112918.0)


async def test_net_specs_feed(monkeypatch):
    import app.sources.cot as cot
    monkeypatch.setattr(cot.httpx, "AsyncClient", _FakeClient)
    val = await CotProvider().net_specs()
    assert val == pytest.approx(112918.0)


async def test_cache_avoids_refetch(monkeypatch):
    import app.sources.cot as cot
    calls = {"n": 0}

    class _Counting(_FakeClient):
        async def get(self, *a, **k):
            calls["n"] += 1
            return _FakeResp([_FIXTURE_ROW])

    monkeypatch.setattr(cot.httpx, "AsyncClient", _Counting)
    p = CotProvider(cache_ttl_seconds=3600)
    await p.net_specs()
    await p.net_specs()  # doit servir le cache
    assert calls["n"] == 1


async def test_degraded_mode_returns_last_known(monkeypatch):
    import app.sources.cot as cot

    # 1er appel OK -> met en cache
    monkeypatch.setattr(cot.httpx, "AsyncClient", _FakeClient)
    p = CotProvider(cache_ttl_seconds=0)  # cache toujours périmé -> refetch tenté
    first = await p.net_specs()
    assert first == pytest.approx(112918.0)

    # CFTC tombe -> on garde la dernière valeur connue (mode dégradé)
    class _Boom(_FakeClient):
        async def get(self, *a, **k):
            raise RuntimeError("CFTC down")

    monkeypatch.setattr(cot.httpx, "AsyncClient", _Boom)
    second = await p.net_specs()
    assert second == pytest.approx(112918.0)  # pas None : dernier connu


async def test_empty_response_raises(monkeypatch):
    import app.sources.cot as cot

    class _Empty(_FakeClient):
        async def get(self, *a, **k):
            return _FakeResp([])

    monkeypatch.setattr(cot.httpx, "AsyncClient", _Empty)
    with pytest.raises(ValueError):
        await CotProvider().fetch_latest()
