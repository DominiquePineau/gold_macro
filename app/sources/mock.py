"""Provider mock : génère des données réalistes pour démo/tests.

Simule un scénario de marché évolutif pour montrer le système en action
(bascules, alignements, divergences) sans dépendre d'APIs externes.
"""
from __future__ import annotations

import math
import random
from datetime import datetime, timedelta

from app.sources.base import DataProvider, MacroInputs
from app.sentiment.models import NewsItem


_MOCK_HEADLINES_BULL = [
    "Gold surges as Fed signals rate cuts amid recession fears",
    "Safe haven demand spikes on geopolitical tensions",
    "Central banks ramp up gold buying, dollar weakens",
]
_MOCK_HEADLINES_BEAR = [
    "Gold tumbles as Fed turns hawkish, yields rise sharply",
    "Strong dollar pressures bullion, risk-on mood returns",
    "Treasury yields surge, gold sees heavy selloff",
]


class MockProvider(DataProvider):
    """Génère une trajectoire scénarisée déterministe (seed fixe)."""

    def __init__(self, seed: int = 42):
        self.rng = random.Random(seed)
        self.tick = 0
        self.xau = 2350.0
        self.real_rates_level = 1.85

    async def fetch(self) -> MacroInputs:
        t = self.tick
        self.tick += 1

        # Scénario : taux réels qui montent puis se retournent à mi-parcours
        phase = math.sin(t / 8.0)
        rate_change = -phase * 4 + self.rng.uniform(-1, 1)  # bps
        self.real_rates_level += rate_change / 100

        dxy_d = -phase * 0.4 + self.rng.uniform(-0.15, 0.15)
        dxy_i = -phase * 0.2 + self.rng.uniform(-0.1, 0.1)

        # le prix répond (inversement) aux taux réels, avec du bruit
        self.xau += -rate_change * 1.5 + self.rng.uniform(-5, 5)

        cot = phase * 30000 + self.rng.uniform(-5000, 5000)
        price_mom = phase * 0.5 + self.rng.uniform(-0.2, 0.2)
        yield_mom = -phase * 0.3 + self.rng.uniform(-0.1, 0.1)

        # événement macro tous les ~12 ticks
        next_event = (12 - (t % 12)) * 0.5

        # --- sentiment simulé ---
        # retail tend à suivre le prix (donc à se tromper aux extrêmes)
        retail_long = 50 + phase * 25 + self.rng.uniform(-5, 5)
        put_call = 1.0 - phase * 0.3 + self.rng.uniform(-0.1, 0.1)
        fear_greed = 50 + phase * 30 + self.rng.uniform(-5, 5)

        # headlines cohérentes avec la phase macro
        pool = _MOCK_HEADLINES_BULL if phase > 0 else _MOCK_HEADLINES_BEAR
        headlines = [
            NewsItem(text=self.rng.choice(pool), source="mock",
                     published=datetime.utcnow())
            for _ in range(3)
        ]

        return MacroInputs(
            timestamp=datetime.utcnow() + timedelta(hours=t),
            real_rates_10y=rate_change,
            dxy_daily=dxy_d,
            cot_net_specs=cot,
            price_momentum=price_mom,
            dxy_intraday=dxy_i,
            yield_momentum_10y=yield_mom,
            xau_price=round(self.xau, 2),
            real_rates_level=round(self.real_rates_level, 3),
            next_event_hours=round(next_event, 1),
            retail_long_pct=round(retail_long, 1),
            put_call_gld=round(put_call, 2),
            fear_greed=round(fear_greed, 1),
            headlines=headlines,
        )
