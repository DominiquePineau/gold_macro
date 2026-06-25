"""Tests du sentiment de positionnement contrarian (app/sentiment/positioning.py)."""
from __future__ import annotations

from app.sentiment.positioning import EXTREME_Z, PositioningAnalyzer
from app.sentiment.models import PositioningInputs


def test_neutral_zone_low_score():
    """En zone neutre (z faible), le score contrarian reste faible."""
    pa = PositioningAnalyzer()
    # historique stable autour de 50 -> un point proche de la moyenne = z~0
    for v in [49, 50, 51, 50, 49, 51]:
        pa.analyze(PositioningInputs(retail_long_pct=v))
    score, extreme = pa.analyze(PositioningInputs(retail_long_pct=50.0))
    assert abs(score) < 40.0      # pas d'amplification hors extrême
    assert extreme is False


def test_extreme_long_gives_bearish_contrarian():
    """Foule massivement longue (z élevé) -> score contrarian NÉGATIF (baissier)."""
    pa = PositioningAnalyzer()
    for v in [40, 45, 50, 45, 40, 50]:
        pa.analyze(PositioningInputs(retail_long_pct=v))
    score, extreme = pa.analyze(PositioningInputs(retail_long_pct=99.0))
    assert score < 0          # contrarian : foule longue -> baissier
    assert extreme is True


def test_extreme_short_gives_bullish_contrarian():
    pa = PositioningAnalyzer()
    for v in [60, 55, 50, 55, 60, 50]:
        pa.analyze(PositioningInputs(retail_long_pct=v))
    score, extreme = pa.analyze(PositioningInputs(retail_long_pct=1.0))
    assert score > 0          # foule trop courte -> haussier contrarian
    assert extreme is True


def test_no_inputs_returns_zero():
    pa = PositioningAnalyzer()
    score, extreme = pa.analyze(PositioningInputs())
    assert score == 0.0
    assert extreme is False


def test_score_clipped_to_range():
    pa = PositioningAnalyzer()
    for v in [50, 50, 50, 50, 50]:
        pa.analyze(PositioningInputs(retail_long_pct=v))
    score, _ = pa.analyze(PositioningInputs(retail_long_pct=10_000.0))
    assert -100.0 <= score <= 100.0


def test_put_call_extreme_fear_is_bullish():
    """Put/call élevé (peur) aux extrêmes -> contrarian haussier (score > 0)."""
    pa = PositioningAnalyzer()
    for v in [1.0, 1.1, 0.9, 1.0, 1.1, 0.9]:
        pa.analyze(PositioningInputs(put_call_gld=v))
    score, extreme = pa.analyze(PositioningInputs(put_call_gld=5.0))  # peur extrême
    assert score > 0
    assert extreme is True


def test_fear_greed_extreme_greed_is_bearish():
    """Fear&Greed extrême (greed) -> contrarian baissier (score < 0)."""
    pa = PositioningAnalyzer()
    for v in [50, 52, 48, 50, 52, 48]:
        pa.analyze(PositioningInputs(fear_greed=v))
    score, extreme = pa.analyze(PositioningInputs(fear_greed=99.0))
    assert score < 0
    assert extreme is True


def test_combined_inputs_averaged():
    """Plusieurs inputs -> score = moyenne des sous-signaux (borné)."""
    pa = PositioningAnalyzer()
    score, _ = pa.analyze(PositioningInputs(retail_long_pct=50.0,
                                            put_call_gld=1.0, fear_greed=50.0))
    assert -100.0 <= score <= 100.0


def test_contrarian_curve_monotonic_in_extreme():
    """Plus l'extrême est marqué, plus la magnitude contrarian est forte."""
    c1 = PositioningAnalyzer._contrarian_curve(EXTREME_Z + 0.1)
    c2 = PositioningAnalyzer._contrarian_curve(EXTREME_Z + 2.0)
    assert abs(c2) > abs(c1)
    assert c1 < 0 and c2 < 0  # z positif -> contrarian négatif
