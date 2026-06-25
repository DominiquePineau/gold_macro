"""RealProvider : compose les sources réelles en un MacroInputs complet.

Remplace MockProvider en production. Compose :
  - macro (taux/dollar)   : FredProvider  (FRED)
  - positionnement COT    : CotProvider   (CFTC)
  - prix XAU live         : price_feed injecté (ex. IGPriceFeed)  [optionnel]
  - calendrier macro      : calendar injecté                       [optionnel]
  - sentiment positionn.  : positioning_feed injecté               [optionnel]
  - news (NLP)            : news_feed injecté                      [optionnel]

Les feeds optionnels absents -> champs laissés à None (dégradation gracieuse :
l'orchestrateur ignore proprement les couches sans données).
"""
from __future__ import annotations

import inspect
from typing import Optional

from app.sentiment.models import PositioningInputs
from app.sources.base import DataProvider, MacroInputs
from app.sources.cot import CotProvider
from app.sources.fred import Feed, FredProvider


async def _resolve(feed: Optional[Feed], default=None):
    if feed is None:
        return default
    res = feed()
    if inspect.isawaitable(res):
        res = await res
    return res if res is not None else default


class RealProvider(DataProvider):
    """Provider de production composant FRED + COT + feeds live optionnels."""

    def __init__(self, *, fred_api_key: Optional[str] = None,
                 price_feed: Optional[Feed] = None,
                 calendar: Optional[Feed] = None,
                 positioning_feed: Optional[Feed] = None,
                 news_feed: Optional[Feed] = None,
                 cot_provider: Optional[CotProvider] = None):
        cot = cot_provider or CotProvider()
        self.macro = FredProvider(
            api_key=fred_api_key,
            price_feed=price_feed,
            cot_feed=cot.net_specs,
            calendar=calendar,
        )
        self.positioning_feed = positioning_feed
        self.news_feed = news_feed

    async def fetch(self) -> MacroInputs:
        # 1) socle macro (FRED + COT + prix + calendrier) via FredProvider.
        mi = await self.macro.fetch()

        # 2) sentiment de positionnement (optionnel).
        pos = await _resolve(self.positioning_feed)
        if isinstance(pos, PositioningInputs):
            mi.retail_long_pct = pos.retail_long_pct
            mi.put_call_gld = pos.put_call_gld
            mi.fear_greed = pos.fear_greed

        # 3) news pour le NLP (optionnel) : liste de NewsItem.
        news = await _resolve(self.news_feed)
        if news:
            mi.headlines = news

        return mi
