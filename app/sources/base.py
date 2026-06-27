"""Interface des fournisseurs de données macro.

Permet de brancher FRED, OANDA, IG, ou un mock sans toucher au moteur.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class MacroInputs:
    """Le jeu de données brutes attendu par le moteur de scoring."""
    timestamp: datetime

    # Structurels
    real_rates_10y: float          # TIPS 10Y, variation récente (bps)
    dxy_daily: float               # variation DXY daily (%)
    cot_net_specs: float           # positionnement net spéculatif
    breakeven_10y: float = 0.0     # breakeven inflation 10Y, variation (#2)

    # Tactiques
    price_momentum: float = 0.0    # pente prix XAU court terme
    dxy_intraday: float = 0.0      # variation DXY intraday (%)
    yield_momentum_10y: float = 0.0  # momentum rendement nominal
    rate_expect_2y: float = 0.0    # variation 2Y US = anticip. taux Fed (#2)

    # Contexte
    xau_price: Optional[float] = None
    real_rates_level: Optional[float] = None  # niveau absolu (pour divergence)
    next_event_hours: Optional[float] = None
    next_event_name: Optional[str] = None     # ex. "CPI (inflation US)"

    # Sentiment (optionnel)
    retail_long_pct: Optional[float] = None
    put_call_gld: Optional[float] = None
    fear_greed: Optional[float] = None
    headlines: Optional[list] = None  # list[NewsItem]

    def structural_dict(self) -> dict[str, float]:
        # breakeven_10y reste un CONTEXTE (non scoré : n'améliore pas l'edge).
        return {
            "real_rates_10y": self.real_rates_10y,
            "dxy_daily": self.dxy_daily,
            "cot_net_specs": self.cot_net_specs,
        }

    def tactical_dict(self) -> dict[str, float]:
        # rate_expect_2y reste un CONTEXTE (non scoré).
        return {
            "price_momentum": self.price_momentum,
            "dxy_intraday": self.dxy_intraday,
            "yield_momentum_10y": self.yield_momentum_10y,
        }


class DataProvider(ABC):
    """Contrat que tout fournisseur doit respecter."""

    @abstractmethod
    async def fetch(self) -> MacroInputs:
        """Récupère et assemble le snapshot de données brutes."""
        ...
