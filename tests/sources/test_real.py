"""Tests du RealProvider (app/sources/real.py) — composition des feeds."""
from __future__ import annotations

import pytest

from app.core.orchestrator import GoldMacroOrchestrator
from app.sentiment.models import NewsItem, PositioningInputs
from app.sources.base import MacroInputs
from app.sources.cot import CotProvider
from app.sources.price import StaticPriceFeed
from app.sources.real import RealProvider

_OBS = {"observations": [{"value": "2.0"}, {"value": "2.1"}]}
_COT_ROW = {"report_date_as_yyyy_mm_dd": "2026-06-16",
            "m_money_positions_long_all": "128528",
            "m_money_positions_short_all": "15610"}


def _patch_cot(monkeypatch):
    import app.sources.cot as cot

    class _Resp:
        def raise_for_status(self): return None
        def json(self): return [_COT_ROW]

    class _C:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, *a, **k): return _Resp()

    monkeypatch.setattr(cot.httpx, "AsyncClient", _C)


def _build(monkeypatch, **kw) -> RealProvider:
    _patch_cot(monkeypatch)
    rp = RealProvider(fred_api_key="x", **kw)

    async def fake_series(series_id, days=30, **k):
        return [2.0, 2.1]

    monkeypatch.setattr(rp.macro, "_series", fake_series)
    return rp


async def test_real_provider_macro_core(monkeypatch):
    rp = _build(monkeypatch, price_feed=StaticPriceFeed(2400.0))
    mi = await rp.fetch()
    assert isinstance(mi, MacroInputs)
    assert mi.xau_price == 2400.0
    assert mi.cot_net_specs == pytest.approx(112918.0)  # COT live composé
    # sentiment absent -> champs None (dégradation gracieuse)
    assert mi.retail_long_pct is None
    assert mi.headlines is None


async def test_real_provider_with_sentiment(monkeypatch):
    async def positioning():
        return PositioningInputs(retail_long_pct=72.0, fear_greed=80.0)

    def news():
        return [NewsItem(text="Gold rallies on rate cut bets")]

    rp = _build(monkeypatch, price_feed=StaticPriceFeed(2400.0),
                positioning_feed=positioning, news_feed=news)
    mi = await rp.fetch()
    assert mi.retail_long_pct == 72.0
    assert mi.fear_greed == 80.0
    assert mi.headlines and mi.headlines[0].text.startswith("Gold")


async def test_real_provider_drives_orchestrator(monkeypatch):
    rp = _build(monkeypatch, price_feed=StaticPriceFeed(2400.0))
    orch = GoldMacroOrchestrator(provider=rp)
    snap = await orch.run_cycle()
    assert snap.xau_price == 2400.0
    assert -100.0 <= snap.structural.composite <= 100.0


async def test_real_provider_no_price_degrades(monkeypatch):
    rp = _build(monkeypatch)  # pas de price_feed
    mi = await rp.fetch()
    assert mi.xau_price is None  # dégradé, pas d'exception
