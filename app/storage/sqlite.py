"""Implémentation SQLite append-only de SnapshotRepository (Phase 3).

3 tables (event sourcing, jamais d'UPDATE/DELETE) :
  snapshots  : timestamp, structural/tactical/sentiment composites, xau_price, aligned
  alerts     : snapshot_id (FK), timestamp, kind, severity, message
  components : snapshot_id (FK), name, timeframe, zscore, weight, contribution

Pur stdlib (sqlite3) — pas de pandas. Thread-safe via connexion par appel.
"""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from app.storage.base import StoredAlert, StoredSnapshot

_SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    structural_composite REAL NOT NULL,
    tactical_composite REAL NOT NULL,
    sentiment_composite REAL,
    xau_price REAL,
    aligned INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id INTEGER NOT NULL REFERENCES snapshots(id),
    timestamp TEXT NOT NULL,
    kind TEXT NOT NULL,
    severity TEXT NOT NULL,
    message TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS components (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id INTEGER NOT NULL REFERENCES snapshots(id),
    name TEXT NOT NULL,
    timeframe TEXT,
    zscore REAL,
    weight REAL,
    contribution REAL
);
CREATE INDEX IF NOT EXISTS idx_snap_ts ON snapshots(timestamp);
CREATE INDEX IF NOT EXISTS idx_alert_kind ON alerts(kind);
CREATE INDEX IF NOT EXISTS idx_alert_sev ON alerts(severity);
"""


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _parse(ts: str) -> datetime:
    dt = datetime.fromisoformat(ts)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


class SQLiteSnapshotRepository:
    """Repository SQLite append-only."""

    def __init__(self, db_path: str = "gold_macro.db"):
        self.db_path = db_path
        with self._conn() as con:
            con.executescript(_SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.db_path, timeout=10)
        con.execute("PRAGMA foreign_keys = ON")
        return con

    # ------------------------------------------------------------------ write
    def save(self, snapshot: StoredSnapshot) -> int:
        with self._conn() as con:
            cur = con.execute(
                "INSERT INTO snapshots (timestamp, structural_composite, "
                "tactical_composite, sentiment_composite, xau_price, aligned) "
                "VALUES (?,?,?,?,?,?)",
                (_iso(snapshot.timestamp), snapshot.structural_composite,
                 snapshot.tactical_composite, snapshot.sentiment_composite,
                 snapshot.xau_price, int(snapshot.aligned)),
            )
            sid = int(cur.lastrowid)
            for a in snapshot.alerts:
                con.execute(
                    "INSERT INTO alerts (snapshot_id, timestamp, kind, severity, message) "
                    "VALUES (?,?,?,?,?)",
                    (sid, _iso(a.timestamp), a.kind, a.severity, a.message),
                )
            for c in snapshot.components:
                con.execute(
                    "INSERT INTO components (snapshot_id, name, timeframe, zscore, "
                    "weight, contribution) VALUES (?,?,?,?,?,?)",
                    (sid, c.get("name"), c.get("timeframe"), c.get("zscore"),
                     c.get("weight"), c.get("contribution")),
                )
            con.commit()
        snapshot.id = sid
        return sid

    # ------------------------------------------------------------------ read
    def history(self, *, since: Optional[datetime] = None,
                until: Optional[datetime] = None, limit: int = 1000) -> list[StoredSnapshot]:
        clauses, params = [], []
        if since is not None:
            clauses.append("timestamp >= ?"); params.append(_iso(since))
        if until is not None:
            clauses.append("timestamp <= ?"); params.append(_iso(until))
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        with self._conn() as con:
            rows = con.execute(
                f"SELECT id, timestamp, structural_composite, tactical_composite, "
                f"sentiment_composite, xau_price, aligned FROM snapshots{where} "
                f"ORDER BY timestamp ASC LIMIT ?", (*params, limit),
            ).fetchall()
        return [
            StoredSnapshot(
                id=r[0], timestamp=_parse(r[1]), structural_composite=r[2],
                tactical_composite=r[3], sentiment_composite=r[4], xau_price=r[5],
                aligned=bool(r[6]),
            )
            for r in rows
        ]

    def alerts(self, *, kind: Optional[str] = None, severity: Optional[str] = None,
               limit: int = 1000) -> list[StoredAlert]:
        clauses, params = [], []
        if kind is not None:
            clauses.append("kind = ?"); params.append(kind)
        if severity is not None:
            clauses.append("severity = ?"); params.append(severity)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        with self._conn() as con:
            rows = con.execute(
                f"SELECT timestamp, kind, severity, message FROM alerts{where} "
                f"ORDER BY timestamp DESC LIMIT ?", (*params, limit),
            ).fetchall()
        return [StoredAlert(timestamp=_parse(r[0]), kind=r[1], severity=r[2], message=r[3])
                for r in rows]

    def count_snapshots(self) -> int:
        with self._conn() as con:
            return int(con.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0])
