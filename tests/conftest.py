"""Fixtures partagées pour la suite de tests."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.sentiment.models import NewsItem, PositioningInputs
from app.sources.base import MacroInputs


@pytest.fixture
def now_utc() -> datetime:
    """Instant de référence fixe (tz-aware) pour des tests déterministes."""
    return datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def neutral_inputs(now_utc) -> MacroInputs:
    """Un MacroInputs neutre (toutes valeurs à 0) pour tester le pipeline."""
    return MacroInputs(
        timestamp=now_utc,
        real_rates_10y=0.0,
        dxy_daily=0.0,
        cot_net_specs=0.0,
        price_momentum=0.0,
        dxy_intraday=0.0,
        yield_momentum_10y=0.0,
        xau_price=2400.0,
        real_rates_level=2.0,
    )


@pytest.fixture
def bullish_headline(now_utc) -> NewsItem:
    return NewsItem(text="Gold surges on safe haven demand as dollar weakens",
                    source="test", published=now_utc)


@pytest.fixture
def positioning_neutral() -> PositioningInputs:
    return PositioningInputs(retail_long_pct=50.0, put_call_gld=1.0, fear_greed=50.0)
