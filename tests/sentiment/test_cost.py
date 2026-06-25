"""Tests du garde-fou de coût Claude (app/sentiment/cost.py)."""
from __future__ import annotations

import pytest

from app.sentiment.cost import CostGuard


def test_cost_eur_haiku_rates():
    # 1M tokens entrée = $1.00 ; 1M sortie = $5.00 ; à usd_per_eur=1.0 -> 6.00 €
    g = CostGuard(usd_per_eur=1.0)
    assert g.cost_eur(1_000_000, 1_000_000) == pytest.approx(6.0)
    assert g.cost_eur(0, 0) == 0.0


def test_report_every_euro():
    reports = []
    g = CostGuard(report_every_eur=1.0, hard_stop_eur=10.0, usd_per_eur=1.0,
                  on_report=lambda spent, d: reports.append(d))
    # 1 appel = ~3 € (500k out * $5/M = $2.5 ; +500k in *$1 = $0.5 -> $3 = 3€)
    g.record(500_000, 500_000)
    assert len(reports) == 3  # paliers 1€, 2€, 3€ franchis d'un coup
    assert [r["palier_eur"] for r in reports] == [1.0, 2.0, 3.0]
    assert all(r["kind"] == "REPORT" for r in reports)
    assert g.spent_eur == pytest.approx(3.0)


def test_hard_stop_blocks_calls():
    reports = []
    g = CostGuard(report_every_eur=1.0, hard_stop_eur=10.0, usd_per_eur=1.0,
                  on_report=lambda s, d: reports.append(d))
    assert g.allowed() is True
    g.record(2_000_000, 2_000_000)  # = 12 € > 10 € plafond
    assert g.allowed() is False     # bloqué
    stop = [r for r in reports if r["kind"] == "STOP"]
    assert len(stop) == 1           # alerte STOP émise une seule fois
    g.allowed()                      # rappel -> pas de doublon STOP
    assert len([r for r in reports if r["kind"] == "STOP"]) == 1


def test_accumulates_tokens_and_calls():
    g = CostGuard(usd_per_eur=1.0)
    g.record(1000, 2000)
    g.record(3000, 4000)
    assert g.calls == 2
    assert g._input_tokens == 4000
    assert g._output_tokens == 6000


def test_invalid_params_raise():
    with pytest.raises(ValueError):
        CostGuard(report_every_eur=0)
    with pytest.raises(ValueError):
        CostGuard(hard_stop_eur=-1)


async def test_textual_analyzer_stops_calling_claude_at_cap(monkeypatch):
    """Au-delà du plafond, l'analyzer n'appelle plus Claude -> repli lexique."""
    import app.sentiment.textual as txt
    from app.sentiment.models import NewsItem

    calls = {"n": 0}

    class _Resp:
        def raise_for_status(self): return None
        def json(self):
            return {"content": [{"type": "text",
                                 "text": '{"items": [{"polarity": 0.5, "relevance": 0.8}]}'}],
                    "usage": {"input_tokens": 2_000_000, "output_tokens": 2_000_000}}

    class _Client:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, *a, **k):
            calls["n"] += 1
            return _Resp()

    monkeypatch.setattr(txt.httpx, "AsyncClient", _Client)
    guard = CostGuard(hard_stop_eur=10.0, usd_per_eur=1.0)
    ta = txt.TextualAnalyzer(api_key="k", cost_guard=guard)

    await ta.analyze([NewsItem(text="Gold rallies on safe haven demand")])  # 1er appel = 12€
    assert calls["n"] == 1
    assert guard.allowed() is False
    # 2e analyse : plafond atteint -> pas d'appel Claude, repli lexique
    out = await ta.analyze([NewsItem(text="Gold surges on weak dollar")])
    assert calls["n"] == 1           # PAS de 2e appel réseau
    assert out[0].rationale == "lexique"
