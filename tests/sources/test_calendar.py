"""Tests du calendrier économique (app/sources/calendar.py)."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.sources.calendar import EconomicCalendar, _to_utc


def test_to_utc_et_0830_summer():
    # 08:30 ET en été (EDT = UTC-4) -> 12:30 UTC
    dt = _to_utc("2026-07-14", __import__("datetime").time(8, 30))
    assert dt.tzinfo is not None
    assert dt.hour == 12 and dt.minute == 30
    assert dt.date().isoformat() == "2026-07-14"


class _Resp:
    def __init__(self, dates):
        self._d = dates

    def raise_for_status(self):
        return None

    def json(self):
        return {"release_dates": [{"date": d} for d in self._d]}


def _client(date_map):
    """date_map : release_id -> liste de dates renvoyées."""
    class _C:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, params=None, **k):
            rid = int(params["release_id"])
            return _Resp(date_map.get(rid, []))
    return _C


def _future(days):
    from datetime import timedelta
    return (datetime.now(timezone.utc) + timedelta(days=days)).date().isoformat()


async def test_upcoming_builds_and_sorts(monkeypatch):
    import app.sources.calendar as cal
    dmap = {10: [_future(5)], 50: [_future(2)], 54: [], 53: [], 17: [_future(1)]}
    monkeypatch.setattr(cal.httpx, "AsyncClient", _client(dmap))
    c = EconomicCalendar("k", fomc_dates=[_future(3)])
    ev = await c.upcoming()
    # 4 événements (CPI, NFP, ventes, FOMC), triés par date croissante
    assert len(ev) == 4
    whens = [e.when for e in ev]
    assert whens == sorted(whens)
    assert any("FOMC" in e.name for e in ev)
    assert any("CPI" in e.name for e in ev)


async def test_next_event_and_hours(monkeypatch):
    import app.sources.calendar as cal
    monkeypatch.setattr(cal.httpx, "AsyncClient", _client({50: [_future(2)]}))
    c = EconomicCalendar("k", fomc_dates=[])
    assert "Emploi" in (await c.next_event_name())
    h = await c.hours_to_next()
    assert 24 < h < 24 * 3   # ~2 jours


async def test_cache_avoids_refetch(monkeypatch):
    import app.sources.calendar as cal
    calls = {"n": 0}

    class _C(_client({50: [_future(2)]})):
        async def get(self, url, params=None, **k):
            calls["n"] += 1
            return _Resp([_future(2)])

    monkeypatch.setattr(cal.httpx, "AsyncClient", _C)
    c = EconomicCalendar("k", fomc_dates=[], cache_ttl_seconds=3600)
    await c.upcoming()
    await c.upcoming()
    assert calls["n"] == len(__import__("app.sources.calendar", fromlist=["RELEASES"]).RELEASES)  # 1 passe, pas 2


async def test_degraded_on_fred_down(monkeypatch):
    import app.sources.calendar as cal

    class _Boom:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, *a, **k): raise RuntimeError("FRED down")

    monkeypatch.setattr(cal.httpx, "AsyncClient", _Boom)
    c = EconomicCalendar("k", fomc_dates=[])
    assert await c.upcoming() == []          # dégradé, pas d'exception
    assert await c.hours_to_next() is None
