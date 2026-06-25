"""Tests des métriques de backtest (app/backtest/metrics.py)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.backtest.metrics import (
    base_rate_up,
    directional_hitrate,
    evaluate_alignment,
    forward_return,
)
from app.backtest.replay import BacktestPoint
from app.core.models import Alert


def _pt(i, price, struct=0.0, tac=0.0, kinds=()):
    return BacktestPoint(
        date=datetime(2021, 1, 1, tzinfo=timezone.utc) + timedelta(days=i),
        xau_price=price, structural=struct, tactical=tac, aligned=False,
        alerts=[Alert(kind=k, severity="INFO", message="") for k in kinds],
    )


def test_forward_return_basic():
    pts = [_pt(0, 100), _pt(1, 110)]
    assert forward_return(pts, 0, 1) == pytest_approx(0.10)


def test_forward_return_out_of_bounds_none():
    pts = [_pt(0, 100)]
    assert forward_return(pts, 0, 5) is None


def test_base_rate_up_all_rising():
    pts = [_pt(i, 100 + i) for i in range(10)]
    assert base_rate_up(pts, 1) == 100.0


def test_base_rate_up_all_falling():
    pts = [_pt(i, 100 - i) for i in range(10)]
    assert base_rate_up(pts, 1) == 0.0


def test_alignment_hit_when_price_follows_direction():
    # 5 points haussiers avec ALIGNMENT bull au 1er ; prix monte -> hit
    pts = [_pt(0, 100, struct=30, tac=30, kinds=("ALIGNMENT",))]
    pts += [_pt(i, 100 + i * 5) for i in range(1, 8)]
    evals = {e.horizon: e for e in evaluate_alignment(pts, horizons=(5,))}
    assert evals[5].n_signals == 1
    assert evals[5].hit_rate == 100.0


def test_alignment_miss_when_price_opposes():
    # ALIGNMENT bull mais prix baisse -> miss
    pts = [_pt(0, 100, struct=30, tac=30, kinds=("ALIGNMENT",))]
    pts += [_pt(i, 100 - i * 5) for i in range(1, 8)]
    e = evaluate_alignment(pts, horizons=(5,))[0]
    assert e.hit_rate == 0.0


def test_directional_hitrate_skips_zero_direction():
    pts = [_pt(0, 100, struct=0, tac=0, kinds=("ALIGNMENT",))]
    pts += [_pt(i, 100 + i) for i in range(1, 8)]
    e = directional_hitrate(pts, 5, kind="ALIGNMENT", direction_fn=lambda p: 0)
    assert e.n_signals == 0


def test_edge_is_hitrate_minus_base():
    pts = [_pt(0, 100, struct=30, tac=30, kinds=("ALIGNMENT",))]
    pts += [_pt(i, 100 + i * 5) for i in range(1, 8)]
    e = evaluate_alignment(pts, horizons=(5,))[0]
    assert e.edge == round(e.hit_rate - e.base_rate, 1)


# petit helper local pour éviter d'importer pytest.approx au niveau module
def pytest_approx(v, tol=1e-9):
    class _A:
        def __eq__(self, other):
            return abs(other - v) < tol
    return _A()
