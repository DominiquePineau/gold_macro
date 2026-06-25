"""Tests du FredProvider (app/sources/fred.py) — contrat ABC + injection de feeds."""
from __future__ import annotations

import inspect

import pytest

from app.sources.base import DataProvider, MacroInputs
from app.sources.fred import FredProvider


# --------------------------------------------------------------------------- #
# Contrat
# --------------------------------------------------------------------------- #
def test_missing_api_key_raises(monkeypatch):
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    with pytest.raises(ValueError):
        FredProvider(api_key=None)


def test_fetch_respects_abc_signature():
    """fetch(self) ne doit prendre AUCUN argument requis (conforme à DataProvider)."""
    sig = inspect.signature(FredProvider.fetch)
    params = [p for p in sig.parameters.values() if p.name != "self"]
    assert params == []  # plus de xau_price/cot_net_specs/next_event_hours


def test_is_dataprovider_subclass():
    assert issubclass(FredProvider, DataProvider)


# --------------------------------------------------------------------------- #
# Assemblage avec feeds injectés (réseau FRED mocké via _series)
# --------------------------------------------------------------------------- #
def _patch_series(provider, monkeypatch):
    series = {
        "DFII10": [1.90, 2.00, 2.10],     # TIPS -> dernier delta = +10 bps
        "DGS10": [4.0, 4.1, 4.2, 4.3, 4.4],
        "DTWEXBGS": [100.0, 101.0],       # +1 % daily
    }

    async def fake_series(series_id, days=30):
        return series[series_id]

    monkeypatch.setattr(provider, "_series", fake_series)


async def test_fetch_with_sync_feeds(monkeypatch):
    p = FredProvider(api_key="x",
                     price_feed=lambda: 2400.0,
                     cot_feed=lambda: 123.0,
                     calendar=lambda: 3.0)
    _patch_series(p, monkeypatch)
    out = await p.fetch()
    assert isinstance(out, MacroInputs)
    assert out.xau_price == 2400.0
    assert out.cot_net_specs == 123.0
    assert out.next_event_hours == 3.0
    assert out.real_rates_10y == pytest.approx(10.0)  # (2.10-2.00)*100
    assert out.real_rates_level == pytest.approx(2.10)
    assert out.dxy_daily == pytest.approx(1.0)


async def test_fetch_with_async_feeds(monkeypatch):
    async def price():
        return 1950.0

    async def cot():
        return -50.0

    p = FredProvider(api_key="x", price_feed=price, cot_feed=cot)
    _patch_series(p, monkeypatch)
    out = await p.fetch()
    assert out.xau_price == 1950.0
    assert out.cot_net_specs == -50.0
    assert out.next_event_hours is None  # pas de calendrier -> défaut


async def test_fetch_without_feeds_uses_defaults(monkeypatch):
    p = FredProvider(api_key="x")
    _patch_series(p, monkeypatch)
    out = await p.fetch()
    assert out.xau_price is None
    assert out.cot_net_specs == 0.0
    assert out.next_event_hours is None


# --------------------------------------------------------------------------- #
# Robustesse réseau : retries + cache + mode dégradé (Phase 2.3)
# --------------------------------------------------------------------------- #
class _Resp:
    def __init__(self, payload):
        self._p = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._p


def _client_failing_then_ok(fail_times: int, payload):
    state = {"n": 0}

    class _C:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, *a, **k):
            state["n"] += 1
            if state["n"] <= fail_times:
                raise RuntimeError("FRED réseau KO")
            return _Resp(payload)

    return _C, state


_OBS = {"observations": [{"value": "2.0"}, {"value": "2.1"}, {"value": "."}]}


async def test_series_retries_then_succeeds(monkeypatch):
    import app.sources.fred as fred
    Client, state = _client_failing_then_ok(2, _OBS)  # échoue 2x, réussit la 3e
    monkeypatch.setattr(fred.httpx, "AsyncClient", Client)
    p = FredProvider(api_key="x")
    out = await p._series("DFII10", retries=3, backoff=0.0)
    assert out == [2.0, 2.1]      # "." ignoré
    assert state["n"] == 3        # 2 échecs + 1 succès


async def test_series_falls_back_to_cache(monkeypatch):
    import app.sources.fred as fred
    p = FredProvider(api_key="x")
    # 1er appel OK -> met en cache
    OkClient, _ = _client_failing_then_ok(0, _OBS)
    monkeypatch.setattr(fred.httpx, "AsyncClient", OkClient)
    assert await p._series("DGS10", retries=1, backoff=0.0) == [2.0, 2.1]
    # FRED tombe -> repli sur cache
    BoomClient, _ = _client_failing_then_ok(99, _OBS)
    monkeypatch.setattr(fred.httpx, "AsyncClient", BoomClient)
    assert await p._series("DGS10", retries=2, backoff=0.0) == [2.0, 2.1]


async def test_series_empty_when_fail_and_no_cache(monkeypatch):
    import app.sources.fred as fred
    BoomClient, _ = _client_failing_then_ok(99, _OBS)
    monkeypatch.setattr(fred.httpx, "AsyncClient", BoomClient)
    p = FredProvider(api_key="x")
    assert await p._series("DTWEXBGS", retries=2, backoff=0.0) == []  # dégradé, pas d'exception


async def test_substitutable_for_orchestrator(monkeypatch):
    """FredProvider doit pouvoir piloter l'orchestrateur comme MockProvider."""
    from app.core.orchestrator import GoldMacroOrchestrator

    p = FredProvider(api_key="x", price_feed=lambda: 2400.0, cot_feed=lambda: 10.0)
    _patch_series(p, monkeypatch)
    orch = GoldMacroOrchestrator(provider=p)
    snap = await orch.run_cycle()
    assert snap.xau_price == 2400.0
    assert -100.0 <= snap.structural.composite <= 100.0
