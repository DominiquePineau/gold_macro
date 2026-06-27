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

import asyncio
import inspect
import os
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable, Optional, Union

import httpx

from app.core.stats import RollingWindow, pct_change, slope
from app.sources.base import DataProvider, MacroInputs

FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"


async def _sleep(seconds: float) -> None:
    """Indirection sur asyncio.sleep (monkeypatchable en test)."""
    await asyncio.sleep(seconds)

# Un "feed" est un callable sans argument renvoyant une valeur (ou un awaitable
# de valeur). Permet d'injecter prix XAU / COT / calendrier sans violer l'ABC
# `DataProvider.fetch(self) -> MacroInputs`.
Feed = Callable[[], Union[object, Awaitable[object]]]


class FredProvider(DataProvider):
    """Provider FRED conforme à l'ABC : `fetch(self)` sans argument.

    Les dépendances externes (prix XAU live, positionnement COT, calendrier macro)
    sont **injectées au __init__** sous forme de feeds (callables sync ou async),
    et non passées à `fetch()`. Cela rend `FredProvider` substituable à
    `MockProvider` sans changer l'orchestrateur (cf. IMPLEMENTATION_PLAN §1.6).
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        price_feed: Optional[Feed] = None,   # () -> prix XAU courant (float|None)
        cot_feed: Optional[Feed] = None,     # () -> net specs CFTC (float)
        calendar: Optional[Feed] = None,     # () -> heures avant prochain event (float|None)
    ):
        self.api_key = api_key or os.environ.get("FRED_API_KEY")
        if not self.api_key:
            raise ValueError("FRED_API_KEY manquante (env ou argument).")
        self._price_feed = price_feed
        self._cot_feed = cot_feed
        self._calendar = calendar
        # historiques pour calculer momentum/pentes
        self._tips = RollingWindow(252)
        self._nominal = RollingWindow(252)
        self._dxy = RollingWindow(252)
        self._xau = RollingWindow(252)
        # cache des dernières séries réussies (repli si FRED est down)
        self._series_cache: dict[str, list[float]] = {}

    @staticmethod
    async def _resolve(feed: Optional[Feed], default: object) -> object:
        """Appelle un feed (sync ou async) ; renvoie `default` si absent."""
        if feed is None:
            return default
        result = feed()
        if inspect.isawaitable(result):
            result = await result
        return result if result is not None else default

    async def _series(self, series_id: str, days: int = 30, *,
                      retries: int = 3, backoff: float = 0.5) -> list[float]:
        """Récupère une série FRED, avec retries et repli sur cache si FRED down.

        Réessaie `retries` fois (backoff linéaire) en cas d'erreur réseau/HTTP.
        En cas d'échec total : renvoie la dernière série connue (cache) si
        disponible, sinon une liste vide (mode dégradé, jamais d'exception qui
        casse le cycle).
        """
        start = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
        params = {
            "series_id": series_id,
            "api_key": self.api_key,
            "file_type": "json",
            "observation_start": start,
            "sort_order": "asc",
        }
        last_err: Exception | None = None
        for attempt in range(retries):
            try:
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
                if out:
                    self._series_cache[series_id] = out  # succès -> on met en cache
                return out
            except Exception as exc:  # réseau, HTTP, JSON...
                last_err = exc
                await _sleep(backoff * (attempt + 1))
        # échec total -> repli sur le cache (mode dégradé)
        return self._series_cache.get(series_id, [])

    async def fetch(self) -> MacroInputs:
        # Dépendances externes résolues via les feeds injectés (conforme à l'ABC).
        xau_price: Optional[float] = await self._resolve(self._price_feed, None)
        cot_net_specs: float = float(await self._resolve(self._cot_feed, 0.0))
        next_event_hours: Optional[float] = await self._resolve(self._calendar, None)

        tips = await self._series("DFII10")
        nominal = await self._series("DGS10")
        dxy = await self._series("DTWEXBGS")
        breakeven = await self._series("T10YIE")   # anticipations d'inflation 10Y (#2)
        dgs2 = await self._series("DGS2")           # taux 2Y = anticip. taux Fed (#2)

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
        be_chg = ((breakeven[-1] - breakeven[-2]) * 100) if len(breakeven) >= 2 else 0.0
        dgs2_chg = ((dgs2[-1] - dgs2[-2]) * 100) if len(dgs2) >= 2 else 0.0

        return MacroInputs(
            timestamp=datetime.now(timezone.utc),
            real_rates_10y=tips_chg,
            dxy_daily=dxy_daily,
            cot_net_specs=cot_net_specs,
            breakeven_10y=be_chg,
            price_momentum=price_mom,
            dxy_intraday=dxy_intraday,
            yield_momentum_10y=yield_mom,
            rate_expect_2y=dgs2_chg,
            xau_price=xau_price,
            real_rates_level=tips[-1] if tips else None,
            next_event_hours=next_event_hours,
        )
