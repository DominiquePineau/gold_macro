"""Tests du MockProvider (app/sources/mock.py) — déterminisme + intégration."""
from __future__ import annotations

from app.core.orchestrator import GoldMacroOrchestrator
from app.sources.base import MacroInputs
from app.sources.mock import MockProvider


async def test_mock_fetch_returns_complete_inputs():
    out = await MockProvider(seed=42).fetch()
    assert isinstance(out, MacroInputs)
    assert out.xau_price is not None
    assert out.headlines and len(out.headlines) == 3
    assert out.retail_long_pct is not None


async def test_mock_is_deterministic():
    a = await MockProvider(seed=42).fetch()
    b = await MockProvider(seed=42).fetch()
    assert a.xau_price == b.xau_price
    assert a.cot_net_specs == b.cot_net_specs


async def test_mock_drives_full_pipeline():
    orch = GoldMacroOrchestrator(provider=MockProvider(seed=7))
    snap = None
    for _ in range(6):
        snap = await orch.run_cycle()
    assert snap is not None
    assert -100.0 <= snap.structural.composite <= 100.0
    assert -100.0 <= snap.tactical.composite <= 100.0
    assert snap.sentiment is not None
