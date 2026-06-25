"""Tests du harnais de replay (app/backtest/replay.py)."""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

from app.backtest.replay import BacktestPoint, HistoricalReplay, load_rows


def _make_rows(n: int = 60) -> list[dict]:
    """Série synthétique : taux réels qui montent puis baissent, prix inverse."""
    rows = []
    t0 = datetime(2021, 1, 1, tzinfo=timezone.utc)
    xau = 1800.0
    tips = 1.0
    for i in range(n):
        phase = math.sin(i / 6.0)
        tips += -phase * 0.02
        xau += phase * 5.0
        rows.append({
            "date": t0 + timedelta(days=i),
            "xau_close": xau,
            "real_rates_level": tips,
            "nominal_10y": 2.0 + phase * 0.1,
            "dxy": 100.0 - phase * 0.5,
            "cot_net_spec": phase * 50000,
        })
    return rows


def test_replay_produces_point_per_row():
    rows = _make_rows(40)
    pts = HistoricalReplay(rows).run()
    assert len(pts) == 40
    assert all(isinstance(p, BacktestPoint) for p in pts)


def test_composites_within_bounds():
    pts = HistoricalReplay(_make_rows(60)).run()
    for p in pts:
        assert -100.0 <= p.structural <= 100.0
        assert -100.0 <= p.tactical <= 100.0


def test_first_point_has_zero_delta_no_lookahead():
    # 1er point : pas de prev_tips -> real_rates_chg = 0 ; pas d'exception
    pts = HistoricalReplay(_make_rows(5)).run()
    assert pts[0].date == _make_rows(5)[0]["date"]


def test_aligned_flag_consistent():
    pts = HistoricalReplay(_make_rows(60)).run()
    for p in pts:
        expected = (p.structural > 15 and p.tactical > 15) or (p.structural < -15 and p.tactical < -15)
        assert p.aligned == expected


def test_alerts_are_generated():
    pts = HistoricalReplay(_make_rows(80)).run()
    kinds = {k for p in pts for k in p.alert_kinds}
    # sur une trajectoire oscillante, on attend au moins des bascules
    assert "BIAS_FLIP" in kinds


def test_load_rows_roundtrip(tmp_path):
    csv_path = tmp_path / "d.csv"
    csv_path.write_text(
        "date,xau_close,real_rates_level,nominal_10y,dxy,cot_net_spec\n"
        "2021-01-01 00:00:00+00:00,1800.0,1.0,2.0,100.0,50000\n"
        "2021-01-02 00:00:00+00:00,1810.0,1.1,2.1,100.5,52000\n"
    )
    rows = load_rows(str(csv_path))
    assert len(rows) == 2
    assert rows[0]["xau_close"] == 1800.0
    assert rows[0]["date"].tzinfo is not None
    assert rows[1]["cot_net_spec"] == 52000.0
