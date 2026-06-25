"""Tests du cœur statistique (app/core/stats.py) — valeurs calculées à la main."""
from __future__ import annotations

import math

import pytest

from app.core.stats import (
    RollingWindow,
    diverging,
    pct_change,
    sign_changed,
    slope,
    zscore,
)


# --------------------------------------------------------------------------- #
# zscore
# --------------------------------------------------------------------------- #
def test_zscore_empty_history_returns_zero():
    assert zscore(5.0, []) == 0.0


def test_zscore_single_point_returns_zero():
    # < 2 points -> indéfini -> 0
    assert zscore(5.0, [3.0]) == 0.0


def test_zscore_constant_history_returns_zero():
    # std == 0 -> 0 (pas de division par zéro)
    assert zscore(5.0, [4.0, 4.0, 4.0]) == 0.0


def test_zscore_known_value():
    # history [0,2,4,6,8] : mean=4, var (ddof=1)=(16+4+0+4+16)/4=10, std=sqrt(10)
    # z(14) = (14-4)/sqrt(10) = 10/3.1623 = 3.162 -> clippé à 3.0
    assert zscore(14.0, [0, 2, 4, 6, 8]) == 3.0


def test_zscore_clipped_to_plus_minus_three():
    assert zscore(1000.0, [0, 1, 2, 3, 4]) == 3.0
    assert zscore(-1000.0, [0, 1, 2, 3, 4]) == -3.0


def test_zscore_ignores_nan_and_none():
    z_clean = zscore(6.0, [0, 2, 4])
    z_dirty = zscore(6.0, [0, 2, 4, float("nan"), None])  # type: ignore[list-item]
    assert z_dirty == pytest.approx(z_clean)


def test_zscore_midpoint_is_zero():
    # value == mean -> z == 0
    assert zscore(4.0, [0, 2, 4, 6, 8]) == 0.0


# --------------------------------------------------------------------------- #
# slope
# --------------------------------------------------------------------------- #
def test_slope_flat_series_zero():
    assert slope([5.0, 5.0, 5.0, 5.0]) == 0.0


def test_slope_increasing_positive():
    assert slope([1, 2, 3, 4, 5]) > 0


def test_slope_decreasing_negative():
    assert slope([5, 4, 3, 2, 1]) < 0


def test_slope_single_point_zero():
    assert slope([3.0]) == 0.0


def test_slope_lookback_truncates():
    # uniquement les 3 derniers (croissants) -> pente positive même si début plat
    assert slope([5, 5, 5, 1, 2, 3], lookback=3) > 0


def test_slope_symmetric_normalized():
    # croissante et décroissante symétriques -> pentes opposées de même magnitude
    up = slope([1, 2, 3, 4, 5])
    down = slope([5, 4, 3, 2, 1])
    assert up == pytest.approx(-down)


# --------------------------------------------------------------------------- #
# pct_change
# --------------------------------------------------------------------------- #
def test_pct_change_basic():
    # de 100 à 110 sur 1 période = +10 %
    assert pct_change([100, 110], 1) == pytest.approx(10.0)


def test_pct_change_negative():
    assert pct_change([100, 90], 1) == pytest.approx(-10.0)


def test_pct_change_insufficient_history_zero():
    assert pct_change([100], 1) == 0.0


def test_pct_change_zero_base_returns_zero():
    assert pct_change([0, 50], 1) == 0.0


def test_pct_change_multi_period():
    assert pct_change([100, 999, 120], 2) == pytest.approx(20.0)


# --------------------------------------------------------------------------- #
# sign_changed
# --------------------------------------------------------------------------- #
def test_sign_changed_zero_crossing():
    assert sign_changed(-1.0, 1.0) is True
    assert sign_changed(1.0, -1.0) is True


def test_sign_changed_no_crossing():
    assert sign_changed(1.0, 2.0) is False
    assert sign_changed(-1.0, -2.0) is False


def test_sign_changed_custom_threshold():
    # croisement du seuil 15 (et pas de zéro)
    assert sign_changed(10.0, 20.0, threshold=15.0) is True
    assert sign_changed(10.0, 14.0, threshold=15.0) is False


def test_sign_changed_touching_threshold_is_false():
    # produit nul (== 0) n'est pas < 0
    assert sign_changed(0.0, 5.0) is False


# --------------------------------------------------------------------------- #
# diverging
# --------------------------------------------------------------------------- #
def test_diverging_opposite_signs_strong():
    assert diverging(0.5, -0.5) is True


def test_diverging_same_sign_false():
    assert diverging(0.5, 0.5) is False


def test_diverging_below_strength_false():
    # signes opposés mais trop faibles -> pas de divergence
    assert diverging(0.05, -0.5, min_strength=0.1) is False
    assert diverging(0.5, -0.05, min_strength=0.1) is False


# --------------------------------------------------------------------------- #
# RollingWindow
# --------------------------------------------------------------------------- #
def test_rolling_window_maxlen_respected():
    w = RollingWindow(maxlen=3)
    for v in [1, 2, 3, 4, 5]:
        w.push(v)
    assert w.values() == [3, 4, 5]
    assert len(w) == 3


def test_rolling_window_rejects_nan_none():
    w = RollingWindow(maxlen=5)
    w.push(1.0)
    w.push(float("nan"))
    w.push(None)  # type: ignore[arg-type]
    w.push(2.0)
    assert w.values() == [1.0, 2.0]


def test_rolling_window_last_and_empty():
    w = RollingWindow(maxlen=5)
    assert w.last is None
    w.push(7.0)
    assert w.last == 7.0
    assert len(w) == 1
