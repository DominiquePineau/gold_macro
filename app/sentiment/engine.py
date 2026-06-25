"""Combine positionnement (contrarian) et textuel (NLP) en un score unique.

Pondération asymétrique volontaire :
  - Positionnement : poids fort (signal dur, contrarian, fiable aux extrêmes)
  - Textuel : poids modéré (riche mais bruité et en retard sur le prix)

Le textuel ne PILOTE jamais seul : son rôle principal est la détection de
divergence sentiment/prix (gérée dans le detector).
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from app.sentiment.models import (
    NewsItem,
    PositioningInputs,
    SentimentLabel,
    SentimentScore,
)
from app.sentiment.positioning import PositioningAnalyzer
from app.sentiment.textual import TextualAnalyzer

W_POSITIONING = 0.65
W_TEXTUAL = 0.35


class SentimentEngine:
    def __init__(self, anthropic_key: Optional[str] = None, cost_guard=None):
        self.positioning = PositioningAnalyzer()
        self.textual = TextualAnalyzer(api_key=anthropic_key, cost_guard=cost_guard)

    async def evaluate(
        self,
        positioning: Optional[PositioningInputs] = None,
        news: Optional[list[NewsItem]] = None,
        now: Optional[datetime] = None,
    ) -> SentimentScore:
        pos_score: Optional[float] = None
        txt_score: Optional[float] = None
        extreme = False
        n_items = 0

        if positioning is not None:
            pos_score, extreme = self.positioning.analyze(positioning)

        if news:
            scored = await self.textual.analyze(news)
            txt_score = self.textual.aggregate(scored, now=now)
            n_items = len(scored)

        # combinaison avec re-normalisation des poids selon ce qui est dispo
        parts: list[tuple[float, float]] = []
        if pos_score is not None:
            parts.append((pos_score, W_POSITIONING))
        if txt_score is not None:
            parts.append((txt_score, W_TEXTUAL))

        if not parts:
            composite = 0.0
        else:
            wsum = sum(w for _, w in parts)
            composite = sum(s * w for s, w in parts) / wsum

        composite = max(-100.0, min(100.0, composite))

        note = ""
        if extreme:
            note = "Positionnement EXTRÊME — signal contrarian actif."

        return SentimentScore(
            composite=round(composite, 2),
            label=SentimentLabel.from_score(composite),
            positioning_score=round(pos_score, 2) if pos_score is not None else None,
            textual_score=round(txt_score, 2) if txt_score is not None else None,
            contrarian_flip=extreme,
            items_analyzed=n_items,
            note=note,
        )
