"""Tests du proxy de positionnement Fear&Greed (app/sources/positioning.py)."""
from __future__ import annotations

import sqlite3

import pytest

from app.sentiment.models import PositioningInputs
from app.sources.positioning import ProxyPositioningFeed, fear_greed_proxy


def test_proxy_neutral_when_insufficient_history():
    assert fear_greed_proxy([100, 101, 102]) == 50.0


def test_proxy_greed_on_strong_uptrend():
    closes = [100 + i for i in range(40)]  # hausse régulière, faible vol
    fg = fear_greed_proxy(closes)
    assert fg > 60  # greed


def test_proxy_fear_on_downtrend():
    closes = [140 - i for i in range(40)]  # baisse régulière
    fg = fear_greed_proxy(closes)
    assert fg < 40  # fear


def test_proxy_bounded():
    closes = [100 * (1.05 ** i) for i in range(40)]  # explosif
    fg = fear_greed_proxy(closes)
    assert 0.0 <= fg <= 100.0


def _db(tmp_path, closes):
    db = tmp_path / "t.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE candle_data (timestamp TEXT, instrument TEXT, "
                "timeframe TEXT, open REAL, high REAL, low REAL, close REAL)")
    for i, c in enumerate(closes):
        con.execute("INSERT INTO candle_data VALUES (?,?,?,?,?,?,?)",
                    (f"2026-06-01 00:{i:02d}:00", "XAUUSD", "1h", c, c, c, c))
    con.commit()
    con.close()
    return str(db)


async def test_feed_returns_positioning(tmp_path):
    db = _db(tmp_path, [2000 + i for i in range(40)])
    feed = ProxyPositioningFeed(db_path=db, n=60)
    pos = await feed.positioning()
    assert isinstance(pos, PositioningInputs)
    assert pos.fear_greed is not None and pos.fear_greed > 50  # uptrend -> greed
    assert pos.retail_long_pct is None  # non dispo (proxy)


async def test_feed_none_when_no_data(tmp_path):
    db = _db(tmp_path, [2000, 2001])  # trop court
    feed = ProxyPositioningFeed(db_path=db)
    assert await feed.positioning() is None
