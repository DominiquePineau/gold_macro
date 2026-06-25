"""Modèles de données pour le moteur de scoring XAU/USD."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class Bias(str, Enum):
    STRONG_BULL = "STRONG_BULL"
    BULL = "BULL"
    NEUTRAL = "NEUTRAL"
    BEAR = "BEAR"
    STRONG_BEAR = "STRONG_BEAR"

    @classmethod
    def from_score(cls, score: float) -> "Bias":
        if score >= 50:
            return cls.STRONG_BULL
        if score >= 15:
            return cls.BULL
        if score <= -50:
            return cls.STRONG_BEAR
        if score <= -15:
            return cls.BEAR
        return cls.NEUTRAL


class Timeframe(str, Enum):
    STRUCTURAL = "structural"  # HTF : taux réels, COT, DXY daily
    TACTICAL = "tactical"      # LTF : momentum prix, DXY intraday, event proximity


@dataclass
class SignalComponent:
    """Une composante individuelle du score (un facteur macro)."""
    name: str
    raw_value: float          # valeur brute (ex: variation TIPS en bps)
    zscore: float             # valeur normalisée
    weight: float             # poids dans le composite
    contribution: float       # zscore * weight * direction
    direction: int            # +1 ou -1 (relation avec l'or)
    note: str = ""

    @property
    def abs_contribution(self) -> float:
        return abs(self.contribution)


@dataclass
class TimeframeScore:
    timeframe: Timeframe
    composite: float                      # -100 à +100
    bias: Bias
    components: list[SignalComponent] = field(default_factory=list)

    def top_driver(self) -> Optional[SignalComponent]:
        if not self.components:
            return None
        return max(self.components, key=lambda c: c.abs_contribution)


@dataclass
class Alert:
    kind: str          # BIAS_FLIP, DIVERGENCE, ALIGNMENT, EVENT_PROXIMITY
    severity: str      # INFO, WARNING, CRITICAL
    message: str
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class GoldSnapshot:
    """Photo complète à un instant T."""
    timestamp: datetime
    structural: TimeframeScore
    tactical: TimeframeScore
    alerts: list[Alert] = field(default_factory=list)
    xau_price: Optional[float] = None
    sentiment: Optional["object"] = None  # SentimentScore (évite import circulaire)

    @property
    def aligned(self) -> bool:
        """Les deux timeframes pointent dans la même direction ?"""
        s, t = self.structural.composite, self.tactical.composite
        return (s > 15 and t > 15) or (s < -15 and t < -15)
