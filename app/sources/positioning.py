"""Proxy de sentiment de positionnement (choix utilisateur : "proxy").

Faute de source gratuite fiable pour le retail L/S ou le put/call GLD (payant),
on construit un **proxy Fear & Greed maison** dérivé du PRIX de l'or :
  - momentum fort + faible volatilité  -> GREED (score > 50)
  - momentum négatif + forte volatilité -> FEAR  (score < 50)

⚠️ Ce n'est PAS un indicateur de positionnement réel : c'est un proxy de
sentiment dérivé du prix (donc corrélé au prix, pas indépendant). Il alimente
`fear_greed` ; `retail_long_pct` et `put_call_gld` restent None (non dispo).
Sa valeur principale reste la DÉTECTION DE DIVERGENCE sentiment/prix (gérée par
le détecteur) plus que le niveau absolu.
"""
from __future__ import annotations

import math
import os
import sqlite3
import statistics
from typing import Optional

from app.sentiment.models import PositioningInputs
from app.sources.price import DEFAULT_TRADE_DB


def fear_greed_proxy(closes: list[float], *, mom_window: int = 10,
                     vol_window: int = 20) -> float:
    """Proxy Fear&Greed [0,100] à partir d'une série de clôtures (50 = neutre).

    Ratio type Sharpe (momentum / volatilité) passé en tanh pour borner.
    """
    if len(closes) < max(mom_window, vol_window) + 1:
        return 50.0
    rets = [closes[i] / closes[i - 1] - 1.0 for i in range(1, len(closes))
            if closes[i - 1] != 0]
    if len(rets) < vol_window:
        return 50.0
    vol = statistics.pstdev(rets[-vol_window:]) or 1e-9
    mom = closes[-1] / closes[-1 - mom_window] - 1.0
    sharpe = mom / (vol * math.sqrt(mom_window))
    score = 50.0 + 50.0 * math.tanh(sharpe)
    return max(0.0, min(100.0, score))


class ProxyPositioningFeed:
    """Feed positionnement (proxy) : lit le prix XAU du flux trade et renvoie F&G."""

    def __init__(self, *, db_path: Optional[str] = None, instrument: str = "XAUUSD",
                 timeframe: str = "1h", n: int = 60, mom_window: int = 10,
                 vol_window: int = 20):
        self.db_path = db_path or os.environ.get("TRADE_DB_PATH") or DEFAULT_TRADE_DB
        self.instrument = instrument
        self.timeframe = timeframe
        self.n = n
        self.mom_window = mom_window
        self.vol_window = vol_window

    def _recent_closes(self) -> list[float]:
        if not os.path.exists(self.db_path):
            return []
        con = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True, timeout=5)
        try:
            cur = con.execute(
                "SELECT close FROM candle_data WHERE instrument=? AND timeframe=? "
                "ORDER BY timestamp DESC LIMIT ?",
                (self.instrument, self.timeframe, self.n),
            )
            rows = cur.fetchall()
        finally:
            con.close()
        return [float(r[0]) for r in reversed(rows)]  # ordre chronologique

    async def positioning(self) -> Optional[PositioningInputs]:
        """Renvoie un PositioningInputs avec fear_greed (proxy) ou None si pas de data."""
        closes = self._recent_closes()
        if len(closes) < max(self.mom_window, self.vol_window) + 1:
            return None
        fg = fear_greed_proxy(closes, mom_window=self.mom_window, vol_window=self.vol_window)
        return PositioningInputs(fear_greed=fg)

    async def __call__(self) -> Optional[PositioningInputs]:
        return await self.positioning()
