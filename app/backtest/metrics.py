"""Métriques d'évaluation des signaux du backtest (hit-rate, lead/lag, base rate).

Honnêteté : tout hit-rate directionnel est comparé au **base rate** inconditionnel
(probabilité que l'or monte sur N jours, indépendamment de tout signal). Sur
2020-2026 l'or a fortement monté → un signal "haussier" paraît bon par défaut.
L'edge réel = hit-rate AU-DESSUS du base rate.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.backtest.replay import BacktestPoint


def _sign(x: float) -> int:
    return 1 if x > 0 else (-1 if x < 0 else 0)


def forward_return(points: list[BacktestPoint], i: int, n: int) -> float | None:
    """Rendement de l'or de l'indice i à i+n (None si hors borne)."""
    if i + n >= len(points):
        return None
    p0, p1 = points[i].xau_price, points[i + n].xau_price
    if p0 == 0:
        return None
    return p1 / p0 - 1.0


@dataclass
class SignalEval:
    kind: str
    horizon: int
    n_signals: int
    hit_rate: float          # % où le mouvement va dans la direction prédite
    base_rate: float         # % où l'or monte inconditionnellement (réf. directionnelle)
    edge: float              # hit_rate - base_rate_directionnel (pp)
    avg_forward: float       # rendement moyen forward dans la direction (signé)


def base_rate_up(points: list[BacktestPoint], n: int) -> float:
    """Probabilité inconditionnelle que l'or monte sur n jours."""
    rs = [forward_return(points, i, n) for i in range(len(points))]
    rs = [r for r in rs if r is not None]
    return 100.0 * sum(1 for r in rs if r > 0) / len(rs) if rs else 0.0


def directional_hitrate(points: list[BacktestPoint], n: int, *, kind: str,
                        direction_fn) -> SignalEval:
    """Hit-rate d'un type d'alerte : le prix va-t-il dans la direction prédite ?

    `direction_fn(point) -> int (+1/-1/0)` donne la direction prédite au signal.
    Le base rate est orienté selon la direction majoritaire des signaux pour une
    comparaison juste (un signal haussier se compare au % de hausse, etc.).
    """
    hits = 0
    total = 0
    fwds: list[float] = []
    dirs: list[int] = []
    for i, p in enumerate(points):
        if kind not in p.alert_kinds:
            continue
        d = direction_fn(p)
        if d == 0:
            continue
        fr = forward_return(points, i, n)
        if fr is None:
            continue
        total += 1
        dirs.append(d)
        fwds.append(fr * d)  # rendement orienté dans le sens prédit
        if _sign(fr) == d:
            hits += 1
    hit_rate = 100.0 * hits / total if total else 0.0
    # base rate orienté : moyenne pondérée selon le mix long/short des signaux
    up = base_rate_up(points, n)
    n_long = sum(1 for d in dirs if d > 0)
    n_short = sum(1 for d in dirs if d < 0)
    base_dir = ((up * n_long) + ((100.0 - up) * n_short)) / total if total else 0.0
    avg_fwd = 100.0 * sum(fwds) / len(fwds) if fwds else 0.0
    return SignalEval(kind=kind, horizon=n, n_signals=total,
                      hit_rate=round(hit_rate, 1), base_rate=round(base_dir, 1),
                      edge=round(hit_rate - base_dir, 1), avg_forward=round(avg_fwd, 2))


def evaluate_alignment(points: list[BacktestPoint], horizons=(5, 10, 20)) -> list[SignalEval]:
    return [directional_hitrate(points, n, kind="ALIGNMENT",
                                direction_fn=lambda p: _sign(p.structural)) for n in horizons]


def evaluate_bias_flip(points: list[BacktestPoint], horizons=(5, 10, 20)) -> list[SignalEval]:
    return [directional_hitrate(points, n, kind="BIAS_FLIP",
                                direction_fn=lambda p: _sign(p.structural)) for n in horizons]


def evaluate_divergence(points: list[BacktestPoint], horizons=(5, 10, 20),
                        trend_lookback: int = 10) -> list[SignalEval]:
    """DIVERGENCE = épuisement attendu -> on PRÉDIT un retournement de la tendance.

    Direction prédite = opposée à la tendance prix récente au moment du signal.
    """
    def reversal_dir(idx_point):
        i, p = idx_point
        lo = max(0, i - trend_lookback)
        prices = [points[j].xau_price for j in range(lo, i + 1)]
        from app.core.stats import slope as _slope
        return -_sign(_slope(prices))

    # on a besoin de l'indice -> wrapper manuel
    hits = {n: [0, 0, []] for n in horizons}
    for i, p in enumerate(points):
        if "DIVERGENCE" not in p.alert_kinds:
            continue
        d = reversal_dir((i, p))
        if d == 0:
            continue
        for n in horizons:
            fr = forward_return(points, i, n)
            if fr is None:
                continue
            hits[n][1] += 1
            hits[n][2].append(fr * d)
            if _sign(fr) == d:
                hits[n][0] += 1
    out = []
    for n in horizons:
        h, tot, fwds = hits[n]
        hr = 100.0 * h / tot if tot else 0.0
        up = base_rate_up(points, n)
        # un retournement prédit est ~50/50 a priori ; base = 50 (pas de drift directionnel net)
        out.append(SignalEval(kind="DIVERGENCE", horizon=n, n_signals=tot,
                              hit_rate=round(hr, 1), base_rate=50.0,
                              edge=round(hr - 50.0, 1),
                              avg_forward=round(100.0 * sum(fwds) / len(fwds), 2) if fwds else 0.0))
    return out


def alert_counts(points: list[BacktestPoint]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for p in points:
        for k in p.alert_kinds:
            counts[k] = counts.get(k, 0) + 1
    return counts
