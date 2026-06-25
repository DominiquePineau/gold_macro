"""Tests du moteur de scoring (app/core/engine.py)."""
from __future__ import annotations

import pytest

from app.core import config
from app.core.engine import ScoringEngine
from app.core.models import Timeframe


def _feed_history(engine: ScoringEngine, factor: str, values: list[float]) -> None:
    """Alimente l'historique d'un facteur via des cycles successifs."""
    factors = {f.name: f for f in config.STRUCTURAL_FACTORS + config.TACTICAL_FACTORS}
    f = factors[factor]
    fn = engine.score_structural if f.timeframe == "structural" else engine.score_tactical
    for v in values:
        fn({factor: v})


# --------------------------------------------------------------------------- #
# Bornes et structure
# --------------------------------------------------------------------------- #
def test_composite_within_bounds_extreme_input():
    eng = ScoringEngine()
    _feed_history(eng, "real_rates_10y", [0, 1, 0, 1, 0, 1])
    score = eng.score_structural({"real_rates_10y": 1000.0})
    assert -100.0 <= score.composite <= 100.0


def test_empty_input_gives_zero_composite():
    eng = ScoringEngine()
    score = eng.score_structural({})
    assert score.composite == 0.0
    assert score.components == []


def test_missing_factor_is_ignored():
    eng = ScoringEngine()
    # un seul des trois facteurs structurels fourni -> 1 seule composante
    score = eng.score_structural({"real_rates_10y": 5.0})
    assert len(score.components) == 1
    assert score.components[0].name == "real_rates_10y"


def test_timeframe_label_correct():
    eng = ScoringEngine()
    s = eng.score_structural({"real_rates_10y": 1.0})
    t = eng.score_tactical({"price_momentum": 1.0})
    assert s.timeframe == Timeframe.STRUCTURAL
    assert t.timeframe == Timeframe.TACTICAL


# --------------------------------------------------------------------------- #
# Décomposition cohérente
# --------------------------------------------------------------------------- #
def test_composite_equals_sum_contributions_scaled():
    eng = ScoringEngine()
    _feed_history(eng, "real_rates_10y", [0, 2, 4, 6, 8])
    _feed_history(eng, "dxy_daily", [0, 1, 2, 3, 4])
    _feed_history(eng, "cot_net_specs", [0, 1, 0, 1, 0])
    score = eng.score_structural(
        {"real_rates_10y": 3.0, "dxy_daily": 2.0, "cot_net_specs": 0.5}
    )
    raw = sum(c.contribution for c in score.components)
    expected = max(-100.0, min(100.0, raw * 33.0))
    assert score.composite == pytest.approx(round(expected, 2))


def test_contribution_sign_follows_direction():
    # real_rates a direction -1 : une hausse (z>0) doit contribuer NÉGATIVEMENT
    eng = ScoringEngine()
    _feed_history(eng, "real_rates_10y", [0, 1, 2, 3, 4])
    score = eng.score_structural({"real_rates_10y": 10.0})
    comp = score.components[0]
    assert comp.zscore > 0
    assert comp.contribution < 0  # direction -1 inverse le signe


# --------------------------------------------------------------------------- #
# Inversion COT aux extrêmes
# --------------------------------------------------------------------------- #
def test_cot_extreme_inverts_direction_and_flags():
    eng = ScoringEngine()
    # historique resserré pour qu'un outlier donne |z| >= 2
    _feed_history(eng, "cot_net_specs", [0, 1, 0, 1, 0, 1])
    score = eng.score_structural({"cot_net_specs": 50.0})
    comp = next(c for c in score.components if c.name == "cot_net_specs")
    assert abs(comp.zscore) >= config.COT_EXTREME_ZSCORE
    # direction de base = +1 ; inversée -> -1
    assert comp.direction == -1
    assert "EXTRÊME" in comp.note


def test_cot_non_extreme_keeps_direction():
    eng = ScoringEngine()
    _feed_history(eng, "cot_net_specs", [0, 1, 2, 3, 4, 5])
    # valeur dans la continuité -> z modéré, pas d'inversion
    score = eng.score_structural({"cot_net_specs": 6.0})
    comp = next(c for c in score.components if c.name == "cot_net_specs")
    if abs(comp.zscore) < config.COT_EXTREME_ZSCORE:
        assert comp.direction == +1
        assert "EXTRÊME" not in comp.note


def test_tactical_scoring_runs():
    eng = ScoringEngine()
    _feed_history(eng, "price_momentum", [0, 1, 2, 3, 4])
    score = eng.score_tactical({"price_momentum": 5.0, "dxy_intraday": 1.0})
    assert score.timeframe == Timeframe.TACTICAL
    assert -100.0 <= score.composite <= 100.0
