"""Sentiment textuel (NLP).

Moteur principal : Claude API (Haiku) — note chaque headline pour son impact
SUR L'OR spécifiquement, en comprenant le contexte macro inversé
(ex: "hausse des taux" = baissier or).

Fallback : lexique financier simple si pas de clé API, pour que le système
reste fonctionnel en démo.

IMPORTANT : ce score est de la CONFIRMATION, pas un driver. Le sentiment
textuel est souvent en retard sur le prix. Sa vraie valeur est la DÉTECTION
DE DIVERGENCE (sentiment euphorique + prix qui cale = épuisement).
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Optional

import httpx

from app.sentiment.models import NewsItem

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"

# Lexique de secours : termes orientés POUR L'OR (contexte déjà résolu).
# Valeurs positives = haussier or, négatives = baissier or.
_FALLBACK_LEXICON = {
    "safe haven": 0.7, "valeur refuge": 0.7, "haven demand": 0.6,
    "rate cut": 0.6, "baisse des taux": 0.6, "dovish": 0.5,
    "inflation": 0.4, "geopolitical": 0.5, "war": 0.4, "crisis": 0.4,
    "weak dollar": 0.6, "dollar faible": 0.6, "recession": 0.4,
    "record high": 0.5, "rally": 0.4, "surge": 0.4,
    "rate hike": -0.6, "hausse des taux": -0.6, "hawkish": -0.5,
    "strong dollar": -0.6, "dollar fort": -0.6, "yields rise": -0.5,
    "selloff": -0.5, "plunge": -0.5, "tumble": -0.4, "risk-on": -0.3,
}

_SYSTEM_PROMPT = """Tu es un analyste spécialisé sur le marché de l'or (XAU/USD).
Pour chaque headline, évalue son impact DIRECTIONNEL SUR LE PRIX DE L'OR.

Règles de contexte macro (cruciales) :
- Hausse des taux réels / dollar fort / Fed hawkish → BAISSIER pour l'or (négatif)
- Baisse des taux / dollar faible / risque géopolitique / inflation → HAUSSIER (positif)
- Demande valeur refuge, achats banques centrales → HAUSSIER

Réponds UNIQUEMENT en JSON valide, sans markdown, format :
{"items": [{"polarity": <float -1..1>, "relevance": <float 0..1>, "rationale": "<8 mots max>"}]}
polarity : -1 très baissier or, +1 très haussier or.
relevance : 0 si hors-sujet, 1 si impact direct majeur sur l'or.
Garde le même ordre que les headlines fournies."""


class TextualAnalyzer:
    """Note des headlines via Claude, avec repli lexique."""

    def __init__(self, api_key: Optional[str] = None, model: str = "claude-haiku-4-5-20251001"):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.model = model

    # --- moteur principal : Claude ---
    async def _analyze_claude(self, items: list[NewsItem]) -> list[NewsItem]:
        headlines = [f"{i+1}. {it.text}" for i, it in enumerate(items)]
        user_msg = "Headlines à analyser :\n" + "\n".join(headlines)

        payload = {
            "model": self.model,
            "max_tokens": 1024,
            "system": _SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": user_msg}],
        }
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(ANTHROPIC_URL, headers=headers, json=payload)
            r.raise_for_status()
            data = r.json()

        text = "".join(b.get("text", "") for b in data.get("content", [])
                       if b.get("type") == "text")
        text = text.replace("```json", "").replace("```", "").strip()
        parsed = json.loads(text)

        for it, scored in zip(items, parsed.get("items", [])):
            it.polarity = float(scored.get("polarity", 0.0))
            it.relevance = float(scored.get("relevance", 0.0))
            it.rationale = scored.get("rationale", "")
        return items

    # --- repli : lexique ---
    def _analyze_lexicon(self, items: list[NewsItem]) -> list[NewsItem]:
        for it in items:
            low = it.text.lower()
            hits = [v for k, v in _FALLBACK_LEXICON.items() if k in low]
            if hits:
                it.polarity = max(-1.0, min(1.0, sum(hits) / len(hits)))
                it.relevance = min(1.0, 0.3 + 0.2 * len(hits))
                it.rationale = "lexique"
            else:
                it.polarity = 0.0
                it.relevance = 0.1
                it.rationale = "lexique: neutre"
        return items

    async def analyze(self, items: list[NewsItem]) -> list[NewsItem]:
        if not items:
            return []
        if self.api_key:
            try:
                return await self._analyze_claude(items)
            except Exception:
                return self._analyze_lexicon(items)
        return self._analyze_lexicon(items)

    @staticmethod
    def aggregate(items: list[NewsItem], now: Optional[datetime] = None) -> float:
        """Agrège les items notés en un score [-100, +100].

        Pondéré par pertinence ET fraîcheur (décroissance sur 48h).
        """
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        num = 0.0
        den = 0.0
        for it in items:
            if it.polarity is None or it.relevance is None:
                continue
            w = it.relevance
            if it.published is not None:
                pub = it.published
                if pub.tzinfo is None:
                    pub = pub.replace(tzinfo=timezone.utc)
                age_h = max(0.0, (now - pub).total_seconds() / 3600)
                w *= max(0.2, 1.0 - age_h / 48.0)  # demi-vie ~48h
            num += it.polarity * w
            den += w
        if den == 0:
            return 0.0
        return max(-100.0, min(100.0, (num / den) * 100))
