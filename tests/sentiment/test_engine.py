"""Tests de la fusion sentiment (app/sentiment/engine.py)."""
from __future__ import annotations

from app.sentiment.engine import SentimentEngine, W_POSITIONING, W_TEXTUAL
from app.sentiment.models import NewsItem, PositioningInputs, SentimentLabel


async def test_empty_evaluate_is_neutral():
    eng = SentimentEngine(anthropic_key=None)
    s = await eng.evaluate(positioning=None, news=None)
    assert s.composite == 0.0
    assert s.label == SentimentLabel.NEUTRAL
    assert s.contrarian_flip is False


async def test_positioning_only_uses_full_weight(now_utc):
    eng = SentimentEngine(anthropic_key=None)
    s = await eng.evaluate(positioning=PositioningInputs(retail_long_pct=50.0), now=now_utc)
    # un seul sous-score dispo -> composite == positioning_score (renormalisé)
    assert s.positioning_score is not None
    assert s.textual_score is None
    assert s.composite == s.positioning_score


async def test_fusion_weights_normalized(now_utc, bullish_headline):
    eng = SentimentEngine(anthropic_key=None)  # textuel via lexique
    s = await eng.evaluate(
        positioning=PositioningInputs(retail_long_pct=50.0),
        news=[bullish_headline],
        now=now_utc,
    )
    assert s.positioning_score is not None and s.textual_score is not None
    expected = (s.positioning_score * W_POSITIONING + s.textual_score * W_TEXTUAL) / (
        W_POSITIONING + W_TEXTUAL
    )
    assert s.composite == round(max(-100.0, min(100.0, expected)), 2)
    assert s.items_analyzed == 1


async def test_extreme_positioning_sets_contrarian_flip(now_utc):
    eng = SentimentEngine(anthropic_key=None)
    # construire un historique puis un extrême
    for v in [40, 45, 50, 45, 40, 50]:
        await eng.evaluate(positioning=PositioningInputs(retail_long_pct=v), now=now_utc)
    s = await eng.evaluate(positioning=PositioningInputs(retail_long_pct=99.0), now=now_utc)
    assert s.contrarian_flip is True
    assert "EXTRÊME" in s.note


async def test_composite_bounded(now_utc, bullish_headline):
    eng = SentimentEngine(anthropic_key=None)
    s = await eng.evaluate(
        positioning=PositioningInputs(retail_long_pct=50.0),
        news=[bullish_headline], now=now_utc)
    assert -100.0 <= s.composite <= 100.0
