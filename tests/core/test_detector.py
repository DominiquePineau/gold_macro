"""Tests du détecteur de régime / alertes (app/core/detector.py)."""
from __future__ import annotations

from app.core.detector import RegimeDetector
from app.core.models import Bias, Timeframe, TimeframeScore


def _ts(composite: float, tf: Timeframe = Timeframe.STRUCTURAL) -> TimeframeScore:
    return TimeframeScore(timeframe=tf, composite=composite,
                          bias=Bias.from_score(composite), components=[])


def _kinds(alerts) -> list[str]:
    return [a.kind for a in alerts]


# --------------------------------------------------------------------------- #
# BIAS_FLIP
# --------------------------------------------------------------------------- #
def test_bias_flip_structural_on_zero_cross():
    d = RegimeDetector()
    d.evaluate(_ts(20.0), _ts(0.0))            # amorce l'historique
    alerts = d.evaluate(_ts(-20.0), _ts(0.0))  # croisement de zéro structurel
    flips = [a for a in alerts if a.kind == "BIAS_FLIP" and "STRUCTUREL" in a.message]
    assert len(flips) == 1
    assert flips[0].severity == "CRITICAL"


def test_bias_flip_tactical_on_zero_cross():
    d = RegimeDetector()
    d.evaluate(_ts(0.0), _ts(10.0, Timeframe.TACTICAL))
    alerts = d.evaluate(_ts(0.0), _ts(-10.0, Timeframe.TACTICAL))
    flips = [a for a in alerts if a.kind == "BIAS_FLIP" and "TACTIQUE" in a.message]
    assert len(flips) == 1
    assert flips[0].severity == "WARNING"


def test_no_flip_without_crossing():
    d = RegimeDetector()
    d.evaluate(_ts(10.0), _ts(10.0, Timeframe.TACTICAL))
    alerts = d.evaluate(_ts(20.0), _ts(20.0, Timeframe.TACTICAL))
    assert "BIAS_FLIP" not in _kinds(alerts)


# --------------------------------------------------------------------------- #
# ALIGNMENT (une seule fois à la bascule)
# --------------------------------------------------------------------------- #
def test_alignment_emitted_once():
    d = RegimeDetector()
    a1 = d.evaluate(_ts(30.0), _ts(30.0, Timeframe.TACTICAL))
    a2 = d.evaluate(_ts(35.0), _ts(40.0, Timeframe.TACTICAL))  # toujours aligné
    assert "ALIGNMENT" in _kinds(a1)
    assert "ALIGNMENT" not in _kinds(a2)  # pas ré-émise tant qu'aligné


def test_alignment_reemitted_after_break():
    d = RegimeDetector()
    d.evaluate(_ts(30.0), _ts(30.0, Timeframe.TACTICAL))     # aligné haussier
    d.evaluate(_ts(-30.0), _ts(5.0, Timeframe.TACTICAL))     # cassé
    a3 = d.evaluate(_ts(-30.0), _ts(-30.0, Timeframe.TACTICAL))  # ré-aligné baissier
    assert "ALIGNMENT" in _kinds(a3)


def test_no_alignment_when_mixed():
    d = RegimeDetector()
    alerts = d.evaluate(_ts(30.0), _ts(-30.0, Timeframe.TACTICAL))
    assert "ALIGNMENT" not in _kinds(alerts)


# --------------------------------------------------------------------------- #
# DIVERGENCE prix / taux réels (anomalie : même sens)
# --------------------------------------------------------------------------- #
def test_divergence_price_rates_same_direction():
    d = RegimeDetector()
    # prix ET taux réels montent ensemble (anormal) sur >=5 points
    alerts = []
    for i in range(6):
        alerts = d.evaluate(_ts(5.0), _ts(5.0, Timeframe.TACTICAL),
                            xau_price=2400 + i * 10, real_rates_value=2.0 + i * 0.1)
    assert "DIVERGENCE" in _kinds(alerts)


def test_no_divergence_when_normally_inverse():
    d = RegimeDetector()
    alerts = []
    for i in range(6):
        # prix monte, taux réels baissent -> corrélation normale -> pas d'alerte
        alerts = d.evaluate(_ts(5.0), _ts(5.0, Timeframe.TACTICAL),
                            xau_price=2400 + i * 10, real_rates_value=2.0 - i * 0.1)
    assert "DIVERGENCE" not in _kinds(alerts)


# --------------------------------------------------------------------------- #
# SENTIMENT
# --------------------------------------------------------------------------- #
def test_sentiment_extreme_alert():
    d = RegimeDetector()
    alerts = d.evaluate(_ts(0.0), _ts(0.0, Timeframe.TACTICAL),
                        sentiment_score=55.0, sentiment_contrarian=True)
    assert "SENTIMENT_EXTREME" in _kinds(alerts)


def test_no_sentiment_extreme_when_not_contrarian():
    d = RegimeDetector()
    alerts = d.evaluate(_ts(0.0), _ts(0.0, Timeframe.TACTICAL),
                        sentiment_score=55.0, sentiment_contrarian=False)
    assert "SENTIMENT_EXTREME" not in _kinds(alerts)


def test_sentiment_divergence_alert():
    d = RegimeDetector()
    alerts = []
    # sentiment euphorique qui grimpe, prix qui baisse -> divergence d'épuisement
    for i in range(6):
        alerts = d.evaluate(
            _ts(0.0), _ts(0.0, Timeframe.TACTICAL),
            xau_price=2500 - i * 10,           # prix baisse
            sentiment_score=50.0 + i * 2,      # sentiment monte et reste >= 50
        )
    assert "SENTIMENT_DIVERGENCE" in _kinds(alerts)


# --------------------------------------------------------------------------- #
# EVENT_PROXIMITY
# --------------------------------------------------------------------------- #
def test_event_proximity_within_window():
    d = RegimeDetector()
    alerts = d.evaluate(_ts(0.0), _ts(0.0, Timeframe.TACTICAL), next_event_hours=2.0)
    assert "EVENT_PROXIMITY" in _kinds(alerts)


def test_event_proximity_outside_window():
    d = RegimeDetector()
    alerts = d.evaluate(_ts(0.0), _ts(0.0, Timeframe.TACTICAL), next_event_hours=12.0)
    assert "EVENT_PROXIMITY" not in _kinds(alerts)


def test_event_proximity_boundary_inclusive():
    d = RegimeDetector()
    alerts = d.evaluate(_ts(0.0), _ts(0.0, Timeframe.TACTICAL),
                        next_event_hours=4.0, event_proximity_threshold=4.0)
    assert "EVENT_PROXIMITY" in _kinds(alerts)
