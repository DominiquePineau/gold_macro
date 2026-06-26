"""Tests fonctionnels des endpoints API, dont /history et /alerts (Phase 3.3)."""
from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    # app fraîche sur une DB temporaire, sans warm-up (déterministe)
    monkeypatch.setenv("GOLD_MACRO_DB", str(tmp_path / "api.db"))
    monkeypatch.setenv("GOLD_MACRO_WARMUP", "0")
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    import app.api.main as main
    importlib.reload(main)
    with TestClient(main.app) as c:
        yield c


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_evaluate_then_history(client):
    for _ in range(5):
        assert client.post("/evaluate").status_code == 200
    h = client.get("/history")
    assert h.status_code == 200
    rows = h.json()
    assert len(rows) == 5
    assert all("structural_composite" in row and "xau_price" in row for row in rows)
    # ordre chronologique
    ts = [row["timestamp"] for row in rows]
    assert ts == sorted(ts)


def test_history_limit(client):
    for _ in range(6):
        client.post("/evaluate")
    rows = client.get("/history?limit=3").json()
    assert len(rows) == 3


def test_alerts_endpoint(client):
    for _ in range(15):
        client.post("/evaluate")
    a = client.get("/alerts")
    assert a.status_code == 200
    # filtrage par type : tous les éléments renvoyés ont le bon kind
    flips = client.get("/alerts?kind=BIAS_FLIP").json()
    assert all(x["kind"] == "BIAS_FLIP" for x in flips)


def test_snapshot_404_before_evaluate(client):
    assert client.get("/snapshot").status_code == 404


def test_dashboard_served(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "Gold Macro Engine" in r.text


def test_tradingview_webhook_and_signals(client):
    payload = {"symbol": "XAUUSD", "action": "BUY", "price": 4035.0,
               "strategy": "SMC", "message": "sweep long"}
    r = client.post("/tradingview/webhook", json=payload)
    assert r.status_code == 200
    assert r.json()["stored"]["action"] == "BUY"
    sigs = client.get("/tradingview/signals").json()
    assert len(sigs) >= 1
    assert sigs[0]["symbol"] == "XAUUSD"


def test_tradingview_secret_enforced(tmp_path, monkeypatch):
    import importlib
    monkeypatch.setenv("GOLD_MACRO_DB", str(tmp_path / "tv.db"))
    monkeypatch.setenv("GOLD_MACRO_WARMUP", "0")
    monkeypatch.setenv("TRADINGVIEW_WEBHOOK_SECRET", "s3cret")
    import app.api.main as main
    importlib.reload(main)
    from fastapi.testclient import TestClient
    with TestClient(main.app) as c:
        # mauvais secret -> 401
        assert c.post("/tradingview/webhook", json={"action": "BUY"}).status_code == 401
        # bon secret -> 200
        assert c.post("/tradingview/webhook",
                      json={"action": "BUY", "secret": "s3cret"}).status_code == 200
