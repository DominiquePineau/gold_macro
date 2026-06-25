"""Tests de la calibration des poids (app/backtest/calibrate.py)."""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

from app.backtest.calibrate import (
    STRUCT_GRID,
    TACT_GRID,
    _reweight,
    _split,
    calibrate,
    robust_pick,
)
from app.core.config import STRUCTURAL_FACTORS


def _rows(n=300, start_year=2022):
    rows = []
    t0 = datetime(start_year, 1, 1, tzinfo=timezone.utc)
    xau, tips = 1800.0, 1.0
    for i in range(n):
        phase = math.sin(i / 7.0)
        tips += -phase * 0.02
        xau += phase * 6.0
        rows.append({
            "date": t0 + timedelta(days=i),
            "xau_close": xau, "real_rates_level": tips,
            "nominal_10y": 2.0 + phase * 0.1, "dxy": 100.0 - phase * 0.5,
            "cot_net_spec": phase * 50000,
        })
    return rows


def test_reweight_preserves_names_and_directions():
    rw = _reweight(STRUCTURAL_FACTORS, (0.5, 0.3, 0.2))
    assert [f.name for f in rw] == [f.name for f in STRUCTURAL_FACTORS]
    assert [f.direction for f in rw] == [f.direction for f in STRUCTURAL_FACTORS]
    assert [f.weight for f in rw] == [0.5, 0.3, 0.2]


def test_split_partitions_by_date():
    rows = _rows(100, start_year=2023)
    train, test = _split(rows, "2023-03-01")
    assert all(r["date"] < test[0]["date"] for r in train)
    assert len(train) + len(test) == len(rows)


def test_calibrate_returns_sorted_results():
    rows = _rows(400, start_year=2022)
    best, results = calibrate(rows, boundary="2023-01-01", horizon=10)
    assert len(results) == len(STRUCT_GRID) * len(TACT_GRID)
    # trié par train_edge décroissant
    edges = [r.train_edge for r in results]
    assert edges == sorted(edges, reverse=True)
    assert best is results[0]


def test_robust_pick_requires_positive_test_edge():
    rows = _rows(400, start_year=2022)
    _, results = calibrate(rows, boundary="2023-01-01", horizon=10)
    rb = robust_pick(results, min_test_edge=0.0)
    assert rb.test_edge >= 0.0


def test_robust_pick_falls_back_to_default_when_none_survive():
    rows = _rows(400, start_year=2022)
    _, results = calibrate(rows, boundary="2023-01-01", horizon=10)
    rb = robust_pick(results, min_test_edge=999.0)  # impossible -> fallback défaut
    assert rb.struct_weights == STRUCT_GRID[0]
    assert rb.tact_weights == TACT_GRID[0]
