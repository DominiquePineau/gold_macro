"""Outils statistiques pour normaliser et comparer des séries hétérogènes."""
from __future__ import annotations

import math
from collections import deque
from typing import Iterable


def zscore(value: float, history: Iterable[float]) -> float:
    """Z-score de `value` par rapport à une distribution historique.

    Clippé à [-3, 3] pour éviter qu'un outlier domine tout le composite.
    """
    h = [x for x in history if x is not None and not math.isnan(x)]
    if len(h) < 2:
        return 0.0
    mean = sum(h) / len(h)
    var = sum((x - mean) ** 2 for x in h) / (len(h) - 1)
    std = math.sqrt(var)
    if std == 0:
        return 0.0
    z = (value - mean) / std
    return max(-3.0, min(3.0, z))


def slope(series: list[float], lookback: int | None = None) -> float:
    """Pente d'une régression linéaire simple (tendance).

    Retourne la pente normalisée par l'écart-type de la série,
    pour la rendre comparable entre instruments.
    """
    s = series if lookback is None else series[-lookback:]
    s = [x for x in s if x is not None and not math.isnan(x)]
    n = len(s)
    if n < 2:
        return 0.0
    xs = list(range(n))
    mx = sum(xs) / n
    my = sum(s) / n
    num = sum((xs[i] - mx) * (s[i] - my) for i in range(n))
    den = sum((xs[i] - mx) ** 2 for i in range(n))
    if den == 0:
        return 0.0
    raw_slope = num / den
    # normalisation par std pour comparabilité
    var = sum((v - my) ** 2 for v in s) / (n - 1) if n > 1 else 0
    std = math.sqrt(var)
    if std == 0:
        return 0.0
    return raw_slope / std


def pct_change(series: list[float], periods: int = 1) -> float:
    """Variation en pourcentage sur `periods`."""
    if len(series) <= periods or series[-periods - 1] == 0:
        return 0.0
    return (series[-1] - series[-periods - 1]) / abs(series[-periods - 1]) * 100


def sign_changed(prev: float, curr: float, threshold: float = 0.0) -> bool:
    """Détecte un croisement de seuil (par défaut : croisement de zéro)."""
    return (prev - threshold) * (curr - threshold) < 0


def diverging(slope_a: float, slope_b: float, min_strength: float = 0.1) -> bool:
    """Deux séries divergent si leurs pentes sont de signes opposés
    ET suffisamment marquées."""
    if abs(slope_a) < min_strength or abs(slope_b) < min_strength:
        return False
    return slope_a * slope_b < 0


class RollingWindow:
    """Fenêtre glissante pour stocker l'historique d'une série."""

    def __init__(self, maxlen: int = 252):
        self.data: deque[float] = deque(maxlen=maxlen)

    def push(self, value: float) -> None:
        if value is not None and not math.isnan(value):
            self.data.append(value)

    def values(self) -> list[float]:
        return list(self.data)

    @property
    def last(self) -> float | None:
        return self.data[-1] if self.data else None

    def __len__(self) -> int:
        return len(self.data)
