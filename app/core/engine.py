"""Moteur de scoring : transforme les données brutes en biais directionnel.

Sépare deux horloges :
  - STRUCTURAL (HTF) : où on est dans le cycle macro
  - TACTICAL (LTF)   : quand le timing est favorable

Une alerte de conviction maximale = les deux alignés.
Une divergence entre les deux = signal d'épuisement potentiel.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from app.core import config
from app.core.models import (
    Bias,
    SignalComponent,
    Timeframe,
    TimeframeScore,
)
from app.core.stats import RollingWindow, zscore


class ScoringEngine:
    """Calcule les scores composites à partir des séries historiques."""

    def __init__(
        self,
        structural_factors: list[config.FactorConfig] | None = None,
        tactical_factors: list[config.FactorConfig] | None = None,
    ) -> None:
        # Facteurs (poids/directions) — surchargeables pour la calibration.
        # Par défaut : les valeurs de config.py.
        self.structural_factors = structural_factors or config.STRUCTURAL_FACTORS
        self.tactical_factors = tactical_factors or config.TACTICAL_FACTORS
        # Historiques glissants par facteur (pour les z-scores)
        self._history: dict[str, RollingWindow] = {}

    def _hist(self, key: str, maxlen: int = 252) -> RollingWindow:
        if key not in self._history:
            self._history[key] = RollingWindow(maxlen=maxlen)
        return self._history[key]

    def _build_component(
        self,
        factor: config.FactorConfig,
        raw_value: float,
    ) -> SignalComponent:
        """Construit une composante : normalise, applique direction et poids."""
        hist = self._hist(factor.name)
        z = zscore(raw_value, hist.values())
        hist.push(raw_value)  # on alimente APRÈS le calcul

        direction = factor.direction
        note = factor.note

        # Cas spécial COT : un positionnement saturé inverse le signal
        if factor.name == "cot_net_specs" and abs(z) >= config.COT_EXTREME_ZSCORE:
            direction = -direction
            note = f"{note} [EXTRÊME — signal inversé : risque de squeeze]"

        contribution = z * factor.weight * direction
        return SignalComponent(
            name=factor.name,
            raw_value=raw_value,
            zscore=round(z, 3),
            weight=factor.weight,
            contribution=round(contribution, 4),
            direction=direction,
            note=note,
        )

    def _score_timeframe(
        self,
        timeframe: Timeframe,
        factors: list[config.FactorConfig],
        raw_values: dict[str, float],
    ) -> TimeframeScore:
        components = []
        for f in factors:
            if f.name not in raw_values:
                continue
            components.append(self._build_component(f, raw_values[f.name]))

        # Composite = somme des contributions, rescalé sur [-100, 100].
        # Le facteur d'échelle 33 ≈ ramène un z-score de 3 pondéré à ~100.
        raw_composite = sum(c.contribution for c in components)
        composite = max(-100.0, min(100.0, raw_composite * 33.0))

        return TimeframeScore(
            timeframe=timeframe,
            composite=round(composite, 2),
            bias=Bias.from_score(composite),
            components=components,
        )

    def score_structural(self, raw_values: dict[str, float]) -> TimeframeScore:
        return self._score_timeframe(
            Timeframe.STRUCTURAL, self.structural_factors, raw_values
        )

    def score_tactical(self, raw_values: dict[str, float]) -> TimeframeScore:
        return self._score_timeframe(
            Timeframe.TACTICAL, self.tactical_factors, raw_values
        )
