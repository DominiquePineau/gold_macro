"""Tests du dispatcher d'alertes (app/alerting/dispatcher.py)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.alerting.dispatcher import AlertDispatcher
from app.alerting.sinks import LogSink
from app.core.models import Alert


def _alert(kind, severity, message):
    return Alert(kind=kind, severity=severity, message=message)


async def test_critical_pushed():
    sink = LogSink()
    d = AlertDispatcher(sink)
    n = await d.dispatch([_alert("BIAS_FLIP", "CRITICAL", "Bascule → HAUSSIER")])
    assert n == 1
    assert len(sink.messages) == 1
    assert "CRITICAL" in sink.messages[0]


async def test_critical_deduplicated_within_window():
    sink = LogSink()
    d = AlertDispatcher(sink, dedup_window_seconds=3600)
    t0 = datetime(2026, 6, 25, 12, 0, tzinfo=timezone.utc)
    a = _alert("ALIGNMENT", "CRITICAL", "ALIGNEMENT HAUSSIER")
    await d.dispatch([a], now=t0)
    await d.dispatch([a], now=t0 + timedelta(minutes=10))  # même clé, fenêtre -> ignoré
    assert len(sink.messages) == 1


async def test_dedup_resets_after_window():
    sink = LogSink()
    d = AlertDispatcher(sink, dedup_window_seconds=600)
    t0 = datetime(2026, 6, 25, 12, 0, tzinfo=timezone.utc)
    a = _alert("ALIGNMENT", "CRITICAL", "ALIGNEMENT HAUSSIER")
    await d.dispatch([a], now=t0)
    await d.dispatch([a], now=t0 + timedelta(minutes=20))  # hors fenêtre -> re-poussé
    assert len(sink.messages) == 2


async def test_opposite_direction_not_deduped():
    sink = LogSink()
    d = AlertDispatcher(sink)
    t0 = datetime(2026, 6, 25, 12, 0, tzinfo=timezone.utc)
    await d.dispatch([_alert("BIAS_FLIP", "CRITICAL", "Bascule → HAUSSIER")], now=t0)
    await d.dispatch([_alert("BIAS_FLIP", "CRITICAL", "Bascule → BAISSIER")], now=t0)
    assert len(sink.messages) == 2  # directions différentes


async def test_warning_goes_to_digest_not_pushed():
    sink = LogSink()
    d = AlertDispatcher(sink)
    await d.dispatch([_alert("DIVERGENCE", "WARNING", "Épuisement possible")])
    assert sink.messages == []  # pas de push immédiat
    n = await d.flush_digest()
    assert n == 1
    assert len(sink.messages) == 1
    assert "DIGEST" in sink.messages[0]


async def test_digest_dedups():
    sink = LogSink()
    d = AlertDispatcher(sink)
    for _ in range(3):
        await d.dispatch([_alert("DIVERGENCE", "WARNING", "même message")])
    n = await d.flush_digest()
    assert n == 1  # 3 identiques -> 1 ligne


async def test_info_logged_only():
    sink = LogSink()
    d = AlertDispatcher(sink)
    await d.dispatch([_alert("EVENT_PROXIMITY", "INFO", "Event dans 2h")])
    assert sink.messages == []          # jamais poussé
    assert len(d.info_log) == 1         # mais journalisé


async def test_notify_direct():
    sink = LogSink()
    d = AlertDispatcher(sink)
    assert await d.notify("💸 palier 1€") is True
    assert sink.messages == ["💸 palier 1€"]


async def test_empty_digest_noop():
    sink = LogSink()
    d = AlertDispatcher(sink)
    assert await d.flush_digest() == 0
    assert sink.messages == []
