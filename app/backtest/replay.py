"""Rejoue l'historique quotidien à travers le moteur réel (causal, sans look-ahead).

À chaque jour T, on ne calcule les entrées brutes (deltas, momentum) qu'à partir
de données <= T (mêmes formules que `FredProvider`), puis on alimente
`ScoringEngine` + `RegimeDetector`. Les z-scores et historiques internes sont
causaux par construction (push APRÈS calcul). La couche sentiment est absente du
backtest (pas d'historique de positionnement/news) — on évalue les signaux macro.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.core.detector import RegimeDetector
from app.core.engine import ScoringEngine
from app.core.models import Alert
from app.core.stats import RollingWindow, pct_change, slope

_NUMERIC = ("xau_close", "real_rates_level", "nominal_10y", "dxy", "cot_net_spec")


def load_rows(path: str) -> list[dict]:
    """Charge le CSV de backtest (stdlib, pas de pandas) en liste de dicts typés."""
    out: list[dict] = []
    with open(path, newline="") as fh:
        for row in csv.DictReader(fh):
            rec: dict = {"date": datetime.fromisoformat(row["date"])}
            if rec["date"].tzinfo is None:
                rec["date"] = rec["date"].replace(tzinfo=timezone.utc)
            for k in _NUMERIC:
                rec[k] = float(row[k])
            out.append(rec)
    out.sort(key=lambda r: r["date"])
    return out


@dataclass
class BacktestPoint:
    """Résultat d'un cycle de backtest à une date."""
    date: datetime
    xau_price: float
    structural: float          # composite structurel [-100, 100]
    tactical: float            # composite tactique [-100, 100]
    aligned: bool
    alerts: list[Alert] = field(default_factory=list)

    @property
    def alert_kinds(self) -> list[str]:
        return [a.kind for a in self.alerts]


class HistoricalReplay:
    """Rejoue une série de lignes quotidiennes et produit des BacktestPoint."""

    def __init__(self, rows: list[dict], *, price_lookback: int = 10,
                 yield_lookback: int = 5, structural_factors=None,
                 tactical_factors=None):
        self.rows = rows
        self.price_lookback = price_lookback
        self.yield_lookback = yield_lookback
        self.structural_factors = structural_factors
        self.tactical_factors = tactical_factors

    def run(self) -> list[BacktestPoint]:
        engine = ScoringEngine(self.structural_factors, self.tactical_factors)
        detector = RegimeDetector()
        xau_w = RollingWindow(252)
        nominal_w = RollingWindow(252)
        dxy_w = RollingWindow(252)

        points: list[BacktestPoint] = []
        prev_tips: float | None = None

        for r in self.rows:
            xau_w.push(r["xau_close"])
            nominal_w.push(r["nominal_10y"])
            dxy_w.push(r["dxy"])

            # --- entrées brutes (mêmes formules que FredProvider, causales) ---
            tips_level = r["real_rates_level"]
            real_rates_chg = (tips_level - prev_tips) * 100 if prev_tips is not None else 0.0
            dxy_vals = dxy_w.values()
            dxy_daily = pct_change(dxy_vals, 1) if len(dxy_vals) >= 2 else 0.0
            price_mom = slope(xau_w.values(), lookback=self.price_lookback) if len(xau_w) >= 3 else 0.0
            yield_mom = slope(nominal_w.values(), lookback=self.yield_lookback) if len(nominal_w) >= 3 else 0.0

            structural_raw = {
                "real_rates_10y": real_rates_chg,
                "dxy_daily": dxy_daily,
                "cot_net_specs": r["cot_net_spec"],
            }
            tactical_raw = {
                "price_momentum": price_mom,
                "dxy_intraday": dxy_daily,  # proxy daily (comme FredProvider)
                "yield_momentum_10y": yield_mom,
            }

            structural = engine.score_structural(structural_raw)
            tactical = engine.score_tactical(tactical_raw)
            alerts = detector.evaluate(
                structural=structural,
                tactical=tactical,
                xau_price=r["xau_close"],
                real_rates_value=tips_level,
                next_event_hours=None,
                sentiment_score=None,
            )

            points.append(BacktestPoint(
                date=r["date"], xau_price=r["xau_close"],
                structural=structural.composite, tactical=tactical.composite,
                aligned=(structural.composite > 15 and tactical.composite > 15)
                        or (structural.composite < -15 and tactical.composite < -15),
                alerts=alerts,
            ))
            prev_tips = tips_level

        return points
