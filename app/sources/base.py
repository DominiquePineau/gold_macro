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

    # Tactiques
    price_momentum: float          # pente prix XAU court terme
    dxy_intraday: float            # variation DXY intraday (%)
    yield_momentum_10y: float      # momentum rendement nominal

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
        return {
            "real_rates_10y": self.real_rates_10y,
            "dxy_daily": self.dxy_daily,
            "cot_net_specs": self.cot_net_specs,
        }

    def tactical_dict(self) -> dict[str, float]:
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
