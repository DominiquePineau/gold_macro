"""Tests du sentiment textuel NLP (app/sentiment/textual.py)."""
from __future__ import annotations

from datetime import timedelta

import pytest

from app.sentiment.models import NewsItem
from app.sentiment.textual import TextualAnalyzer


# --------------------------------------------------------------------------- #
# Repli lexique
# --------------------------------------------------------------------------- #
def test_lexicon_bullish_headline_positive():
    ta = TextualAnalyzer(api_key=None)
    items = ta._analyze_lexicon([NewsItem(text="Gold rallies on safe haven demand")])
    assert items[0].polarity > 0
    assert items[0].relevance > 0


def test_lexicon_bearish_headline_negative():
    ta = TextualAnalyzer(api_key=None)
    items = ta._analyze_lexicon([NewsItem(text="Gold tumbles as Fed turns hawkish, dollar strong")])
    assert items[0].polarity < 0


def test_lexicon_neutral_headline_zero():
    ta = TextualAnalyzer(api_key=None)
    items = ta._analyze_lexicon([NewsItem(text="Markets quiet ahead of the weekend")])
    assert items[0].polarity == 0.0
    assert items[0].rationale == "lexique: neutre"


async def test_analyze_without_key_uses_lexicon():
    ta = TextualAnalyzer(api_key=None)
    items = await ta.analyze([NewsItem(text="Gold surges on weak dollar")])
    assert items[0].polarity > 0


# --------------------------------------------------------------------------- #
# Agrégation : pertinence + fraîcheur
# --------------------------------------------------------------------------- #
def test_aggregate_empty_zero(now_utc):
    assert TextualAnalyzer.aggregate([], now=now_utc) == 0.0


def test_aggregate_relevance_weighting(now_utc):
    # item haussier pertinent (rel=1) vs item baissier non pertinent (rel=0.1)
    items = [
        NewsItem(text="a", polarity=1.0, relevance=1.0, published=now_utc),
        NewsItem(text="b", polarity=-1.0, relevance=0.1, published=now_utc),
    ]
    score = TextualAnalyzer.aggregate(items, now=now_utc)
    assert score > 0  # le pertinent domine


def test_aggregate_freshness_weighting(now_utc):
    # même pertinence, polarités opposées : le FRAIS doit l'emporter
    fresh = NewsItem(text="fresh", polarity=1.0, relevance=1.0, published=now_utc)
    old = NewsItem(text="old", polarity=-1.0, relevance=1.0,
                   published=now_utc - timedelta(hours=47))
    score = TextualAnalyzer.aggregate([fresh, old], now=now_utc)
    assert score > 0  # l'item récent pèse davantage


def test_aggregate_skips_unscored(now_utc):
    items = [NewsItem(text="x", polarity=None, relevance=None)]
    assert TextualAnalyzer.aggregate(items, now=now_utc) == 0.0


def test_aggregate_bounded(now_utc):
    items = [NewsItem(text="x", polarity=1.0, relevance=1.0, published=now_utc)]
    assert -100.0 <= TextualAnalyzer.aggregate(items, now=now_utc) <= 100.0


# --------------------------------------------------------------------------- #
# Appel Claude mocké (sans réseau)
# --------------------------------------------------------------------------- #
class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeAsyncClient:
    """Remplace httpx.AsyncClient : renvoie une réponse Claude canée."""
    payload = {
        "content": [{"type": "text",
                     "text": '{"items": [{"polarity": 0.8, "relevance": 0.9, "rationale": "haussier or"}]}'}]
    }

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, *a, **k):
        return _FakeResponse(self.payload)


async def test_analyze_claude_parses_response(monkeypatch):
    import app.sentiment.textual as txt
    monkeypatch.setattr(txt.httpx, "AsyncClient", _FakeAsyncClient)
    ta = TextualAnalyzer(api_key="fake-key")
    items = await ta.analyze([NewsItem(text="Gold up on Fed rate cut bets")])
    assert items[0].polarity == pytest.approx(0.8)
    assert items[0].relevance == pytest.approx(0.9)
    assert items[0].rationale == "haussier or"


async def test_analyze_claude_falls_back_on_error(monkeypatch):
    class _Boom(_FakeAsyncClient):
        async def post(self, *a, **k):
            raise RuntimeError("network down")

    import app.sentiment.textual as txt
    monkeypatch.setattr(txt.httpx, "AsyncClient", _Boom)
    ta = TextualAnalyzer(api_key="fake-key")
    # malgré la clé, l'échec réseau -> repli lexique (pas d'exception propagée)
    items = await ta.analyze([NewsItem(text="Gold surges on safe haven demand")])
    assert items[0].polarity > 0
    assert items[0].rationale == "lexique"
