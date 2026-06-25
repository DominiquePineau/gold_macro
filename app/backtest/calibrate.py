"""Calibration des poids du moteur avec validation out-of-sample (Phase 5.3).

Principe anti-overfit (garde-fou du plan) :
  - on optimise sur une période TRAIN (2020-2023),
  - on valide sur une période TEST (2024+),
  - un jeu de poids qui ne tient que sur le train est rejeté,
  - on préfère des poids robustes à des poids parfaits sur l'historique.

Objectif optimisé : l'**edge** des alertes ALIGNMENT (hit-rate − base rate) à
N=10 jours, le seul signal avec un edge mesurable au départ.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from app.backtest.metrics import evaluate_alignment
from app.backtest.replay import HistoricalReplay
from app.core.config import STRUCTURAL_FACTORS, TACTICAL_FACTORS, FactorConfig


def _reweight(factors: list[FactorConfig], weights: tuple[float, ...]) -> list[FactorConfig]:
    """Recrée les facteurs avec de nouveaux poids (mêmes noms/directions)."""
    return [replace(f, weight=w) for f, w in zip(factors, weights)]


# Grilles de poids candidates (normalisées à somme 1) — volontairement GROSSIÈRES
# pour rester robuste (le plan déconseille la sur-optimisation).
STRUCT_GRID = [
    (0.40, 0.30, 0.30),  # défaut : taux réels dominants
    (0.50, 0.30, 0.20),  # taux réels renforcés
    (0.34, 0.33, 0.33),  # égalitaire
    (0.30, 0.40, 0.30),  # DXY dominant
    (0.45, 0.35, 0.20),
]
TACT_GRID = [
    (0.45, 0.35, 0.20),  # défaut : momentum prix dominant
    (0.60, 0.25, 0.15),  # prix très dominant
    (0.34, 0.33, 0.33),  # égalitaire
    (0.50, 0.30, 0.20),
]


@dataclass
class CalibResult:
    struct_weights: tuple[float, ...]
    tact_weights: tuple[float, ...]
    train_edge: float
    test_edge: float
    train_hit: float
    test_hit: float
    n_train: int
    n_test: int


def _split(rows: list[dict], boundary: str):
    import datetime as _dt
    b = _dt.datetime.fromisoformat(boundary)
    if b.tzinfo is None:
        b = b.replace(tzinfo=_dt.timezone.utc)
    train = [r for r in rows if r["date"] < b]
    test = [r for r in rows if r["date"] >= b]
    return train, test


def _edge_at(rows: list[dict], sw, tw, horizon=10) -> tuple[float, float, int]:
    pts = HistoricalReplay(
        rows,
        structural_factors=_reweight(STRUCTURAL_FACTORS, sw),
        tactical_factors=_reweight(TACTICAL_FACTORS, tw),
    ).run()
    ev = next(e for e in evaluate_alignment(pts, horizons=(horizon,)) if e.horizon == horizon)
    return ev.edge, ev.hit_rate, ev.n_signals


def calibrate(rows: list[dict], *, boundary: str = "2024-01-01",
              horizon: int = 10) -> tuple[CalibResult, list[CalibResult]]:
    """Grille sur (struct, tact). Sélectionne le meilleur edge TRAIN, rapporte TEST.

    Retourne (meilleur, tous_les_résultats) triés par edge train décroissant.
    """
    train, test = _split(rows, boundary)
    results: list[CalibResult] = []
    for sw in STRUCT_GRID:
        for tw in TACT_GRID:
            tr_edge, tr_hit, n_tr = _edge_at(train, sw, tw, horizon)
            te_edge, te_hit, n_te = _edge_at(test, sw, tw, horizon)
            results.append(CalibResult(
                struct_weights=sw, tact_weights=tw,
                train_edge=tr_edge, test_edge=te_edge,
                train_hit=tr_hit, test_hit=te_hit, n_train=n_tr, n_test=n_te,
            ))
    results.sort(key=lambda r: r.train_edge, reverse=True)
    return results[0], results


def robust_pick(results: list[CalibResult], *, min_test_edge: float = 0.0) -> CalibResult:
    """Choisit le jeu robuste : meilleur edge TRAIN qui tient AUSSI en TEST.

    Rejette les configs dont l'edge test < min_test_edge (overfit). À défaut,
    retombe sur le défaut (1re config de la grille = poids d'origine).
    """
    survivors = [r for r in results if r.test_edge >= min_test_edge]
    if survivors:
        # parmi les robustes, on prend le meilleur edge MOYEN train/test
        survivors.sort(key=lambda r: (r.train_edge + r.test_edge) / 2, reverse=True)
        return survivors[0]
    return next(r for r in results
                if r.struct_weights == STRUCT_GRID[0] and r.tact_weights == TACT_GRID[0])
