"""Tests de la persistance SQLite append-only (app/storage/sqlite.py)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.storage.base import SnapshotRepository, StoredAlert, StoredSnapshot
from app.storage.sqlite import SQLiteSnapshotRepository


def _snap(i, ts, *, struct=10.0, tac=20.0, sent=5.0, price=2400.0, kinds=()):
    return StoredSnapshot(
        timestamp=ts, structural_composite=struct, tactical_composite=tac,
        sentiment_composite=sent, xau_price=price, aligned=(struct > 15 and tac > 15),
        alerts=[StoredAlert(kind=k, severity="INFO", message=f"m{i}", timestamp=ts) for k in kinds],
        components=[{"name": "real_rates_10y", "timeframe": "structural",
                     "zscore": 1.2, "weight": 0.5, "contribution": -0.6}],
    )


@pytest.fixture
def repo(tmp_path):
    return SQLiteSnapshotRepository(db_path=str(tmp_path / "t.db"))


def test_implements_protocol(repo):
    assert isinstance(repo, SnapshotRepository)


def test_save_returns_id_and_counts(repo):
    t0 = datetime(2026, 6, 25, 12, 0, tzinfo=timezone.utc)
    sid = repo.save(_snap(1, t0))
    assert isinstance(sid, int) and sid > 0
    assert repo.count_snapshots() == 1


def test_history_ordered_and_windowed(repo):
    base = datetime(2026, 6, 25, tzinfo=timezone.utc)
    for i in range(5):
        repo.save(_snap(i, base + timedelta(hours=i), struct=float(i)))
    allh = repo.history()
    assert len(allh) == 5
    assert [h.structural_composite for h in allh] == [0, 1, 2, 3, 4]  # ordre chrono
    # fenêtre
    win = repo.history(since=base + timedelta(hours=1), until=base + timedelta(hours=3))
    assert [h.structural_composite for h in win] == [1, 2, 3]


def test_history_roundtrip_fields(repo):
    t0 = datetime(2026, 6, 25, 9, 0, tzinfo=timezone.utc)
    repo.save(_snap(1, t0, struct=30, tac=40, sent=12.5, price=4035.0))
    h = repo.history()[0]
    assert h.structural_composite == 30
    assert h.tactical_composite == 40
    assert h.sentiment_composite == 12.5
    assert h.xau_price == 4035.0
    assert h.aligned is True
    assert h.timestamp == t0


def test_alerts_filtered(repo):
    t0 = datetime(2026, 6, 25, tzinfo=timezone.utc)
    repo.save(_snap(1, t0, kinds=("ALIGNMENT", "BIAS_FLIP")))
    repo.save(_snap(2, t0 + timedelta(hours=1), kinds=("BIAS_FLIP",)))
    assert len(repo.alerts()) == 3
    assert len(repo.alerts(kind="BIAS_FLIP")) == 2
    assert len(repo.alerts(kind="ALIGNMENT")) == 1
    assert all(a.kind == "BIAS_FLIP" for a in repo.alerts(kind="BIAS_FLIP"))


def test_append_only_persists_components(repo, tmp_path):
    t0 = datetime(2026, 6, 25, tzinfo=timezone.utc)
    sid = repo.save(_snap(1, t0))
    # vérifie la table components via une connexion directe
    import sqlite3
    con = sqlite3.connect(str(tmp_path / "t.db"))
    n = con.execute("SELECT COUNT(*) FROM components WHERE snapshot_id=?", (sid,)).fetchone()[0]
    con.close()
    assert n == 1


def test_persistence_survives_reopen(tmp_path):
    db = str(tmp_path / "persist.db")
    t0 = datetime(2026, 6, 25, tzinfo=timezone.utc)
    SQLiteSnapshotRepository(db_path=db).save(_snap(1, t0))
    # ré-ouverture : la donnée est toujours là (append-only persistant)
    repo2 = SQLiteSnapshotRepository(db_path=db)
    assert repo2.count_snapshots() == 1
