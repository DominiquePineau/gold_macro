"""Connecteur FRED (Federal Reserve Economic Data).

Récupère les séries macro réelles. Nécessite une clé API gratuite :
https://fred.stlouisfed.org/docs/api/api_key.html

Séries utilisées :
  - DFII10 : taux réel 10 ans (TIPS)
  - DGS10  : rendement nominal 10 ans
  - DTWEXBGS : dollar index pondéré (proxy DXY)

Le COT vient d'une source séparée (CFTC), branché ailleurs.
Ce connecteur calcule les variations/momentum à partir des niveaux bruts.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Optional

import httpx

from app.core.stats import RollingWindow, pct_change, slope
from app.sources.base import DataProvider, MacroInputs

FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"


class FredProvider(DataProvider):
    """Provider basé sur FRED + un flux prix XAU externe injecté."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("FRED_API_KEY")
        if not self.api_key:
            raise ValueError("FRED_API_KEY manquante (env ou argument).")
        # historiques pour calculer momentum/pentes
        self._tips = RollingWindow(252)
        self._nominal = RollingWindow(252)
        self._dxy = RollingWindow(252)
        self._xau = RollingWindow(252)

    async def _series(self, series_id: str, days: int = 30) -> list[float]:
        start = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
        params = {
            "series_id": series_id,
            "api_key": self.api_key,
            "file_type": "json",
            "observation_start": start,
            "sort_order": "asc",
        }
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(FRED_BASE, params=params)
            r.raise_for_status()
            data = r.json()
        out = []
        for obs in data.get("observations", []):
            v = obs.get("value")
            if v not in (".", "", None):
                try:
                    out.append(float(v))
                except ValueError:
                    pass
        return out

    async def fetch(self, xau_price: Optional[float] = None,
                    cot_net_specs: float = 0.0,
                    next_event_hours: Optional[float] = None) -> MacroInputs:
        tips = await self._series("DFII10")
        nominal = await self._series("DGS10")
        dxy = await self._series("DTWEXBGS")

        for v in tips:
            self._tips.push(v)
        for v in nominal:
            self._nominal.push(v)
        for v in dxy:
            self._dxy.push(v)
        if xau_price is not None:
            self._xau.push(xau_price)

        # variations récentes (en bps pour les taux : *100)
        tips_chg = ((tips[-1] - tips[-2]) * 100) if len(tips) >= 2 else 0.0
        dxy_daily = pct_change(dxy, 1) if len(dxy) >= 2 else 0.0
        dxy_intraday = pct_change(dxy, 1) if len(dxy) >= 2 else 0.0  # daily proxy
        yield_mom = slope(self._nominal.values(), lookback=5)
        price_mom = slope(self._xau.values(), lookback=10) if len(self._xau) >= 3 else 0.0

        return MacroInputs(
            timestamp=datetime.utcnow(),
            real_rates_10y=tips_chg,
            dxy_daily=dxy_daily,
            cot_net_specs=cot_net_specs,
            price_momentum=price_mom,
            dxy_intraday=dxy_intraday,
            yield_momentum_10y=yield_mom,
            xau_price=xau_price,
            real_rates_level=tips[-1] if tips else None,
            next_event_hours=next_event_hours,
        )
