"""Réception des alertes TradingView (entrée) — ingestion des setups Pine.

TradingView envoie un webhook (JSON libre) quand une alerte Pine se déclenche.
On parse de façon souple (symbol / action / price / strategy / message), on
stocke les plus récentes en mémoire (ring buffer), et l'API les expose +
le dashboard les affiche À CÔTÉ du biais macro.

NB : Pine ne peut pas lire de données externes sur un chart → on ne fait que
l'ENTRÉE (TradingView → moteur), pas la sortie vers le graphique.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class TradingViewSignal:
    received_at: datetime
    symbol: str
    action: str           # BUY/SELL/LONG/SHORT/EXIT... (texte libre normalisé)
    price: Optional[float]
    strategy: str
    message: str
    raw: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "received_at": self.received_at.isoformat(),
            "symbol": self.symbol, "action": self.action, "price": self.price,
            "strategy": self.strategy, "message": self.message,
        }


def _num(v) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def parse_tv_payload(body: dict, *, now: Optional[datetime] = None) -> TradingViewSignal:
    """Parse souple d'une charge utile d'alerte TradingView.

    Accepte les variantes courantes : action/side/signal, price/close,
    strategy/strategy_name, message/text/comment. Champs inconnus -> raw.
    """
    g = body.get
    action = (g("action") or g("side") or g("signal") or "").upper().strip()
    return TradingViewSignal(
        received_at=now or datetime.now(timezone.utc),
        symbol=str(g("symbol") or g("ticker") or "XAUUSD").upper(),
        action=action,
        price=_num(g("price") if g("price") is not None else g("close")),
        strategy=str(g("strategy") or g("strategy_name") or g("name") or ""),
        message=str(g("message") or g("text") or g("comment") or ""),
        raw=dict(body),
    )


class TradingViewStore:
    """Tampon mémoire des dernières alertes TradingView reçues."""

    def __init__(self, maxlen: int = 50):
        self._items: deque[TradingViewSignal] = deque(maxlen=maxlen)

    def add(self, signal: TradingViewSignal) -> None:
        self._items.appendleft(signal)

    def recent(self, n: int = 20) -> list[TradingViewSignal]:
        return list(self._items)[:n]

    @property
    def latest(self) -> Optional[TradingViewSignal]:
        return self._items[0] if self._items else None

    def __len__(self) -> int:
        return len(self._items)
