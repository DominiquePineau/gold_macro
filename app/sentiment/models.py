"""Modèles pour la couche sentiment."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class SentimentLabel(str, Enum):
    EXTREME_FEAR = "EXTREME_FEAR"
    FEAR = "FEAR"
    NEUTRAL = "NEUTRAL"
    GREED = "GREED"
    EXTREME_GREED = "EXTREME_GREED"

    @classmethod
    def from_score(cls, score: float) -> "SentimentLabel":
        # score sur [-100, +100] : +100 = greed extrême (haussier brut)
        if score >= 60:
            return cls.EXTREME_GREED
        if score >= 20:
            return cls.GREED
        if score <= -60:
            return cls.EXTREME_FEAR
        if score <= -20:
            return cls.FEAR
        return cls.NEUTRAL


@dataclass
class NewsItem:
    """Une headline / item textuel à analyser."""
    text: str
    source: str = ""
    published: Optional[datetime] = None
    # rempli par l'analyse NLP :
    polarity: Optional[float] = None     # -1 (baissier or) à +1 (haussier or)
    relevance: Optional[float] = None    # 0 à 1 : pertinence pour XAU
    rationale: str = ""


@dataclass
class PositioningInputs:
    """Données de positionnement quantitatif (contrarian)."""
    retail_long_pct: Optional[float] = None   # % retail long (broker)
    put_call_gld: Optional[float] = None       # ratio put/call options GLD
    fear_greed: Optional[float] = None         # indice 0-100 (CNN-like)


@dataclass
class SentimentScore:
    composite: float                # -100 à +100 (déjà orienté trading)
    label: SentimentLabel
    positioning_score: Optional[float] = None
    textual_score: Optional[float] = None
    contrarian_flip: bool = False   # un extrême a inversé le signal ?
    items_analyzed: int = 0
    note: str = ""
    timestamp: datetime = field(default_factory=datetime.utcnow)
