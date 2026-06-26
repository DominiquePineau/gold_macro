"""Tests de l'ingestion TradingView (app/integrations/tradingview.py)."""
from __future__ import annotations

from app.integrations.tradingview import (
    TradingViewSignal,
    TradingViewStore,
    parse_tv_payload,
)


def test_parse_standard_payload():
    s = parse_tv_payload({"symbol": "xauusd", "action": "buy", "price": "4035.5",
                          "strategy": "SMC", "message": "Sweep + CISD long"})
    assert s.symbol == "XAUUSD"
    assert s.action == "BUY"
    assert s.price == 4035.5
    assert s.strategy == "SMC"
    assert s.message == "Sweep + CISD long"


def test_parse_variant_keys():
    # side/close/strategy_name/text au lieu de action/price/strategy/message
    s = parse_tv_payload({"ticker": "XAUUSD", "side": "sell", "close": 3980,
                          "strategy_name": "ORB", "text": "break low"})
    assert s.action == "SELL"
    assert s.price == 3980.0
    assert s.strategy == "ORB"
    assert s.message == "break low"


def test_parse_defaults_and_bad_price():
    s = parse_tv_payload({})
    assert s.symbol == "XAUUSD"  # défaut
    assert s.action == ""
    assert s.price is None
    s2 = parse_tv_payload({"price": "pas_un_nombre"})
    assert s2.price is None


def test_store_ring_buffer_and_latest():
    store = TradingViewStore(maxlen=3)
    for i in range(5):
        store.add(parse_tv_payload({"action": f"A{i}"}))
    assert len(store) == 3                       # maxlen respecté
    assert store.latest.action == "A4"           # le plus récent en tête
    assert [s.action for s in store.recent(2)] == ["A4", "A3"]


def test_store_empty_latest_none():
    assert TradingViewStore().latest is None


def test_to_dict_roundtrip():
    s = parse_tv_payload({"symbol": "XAUUSD", "action": "LONG", "price": 4000})
    d = s.to_dict()
    assert d["symbol"] == "XAUUSD" and d["action"] == "LONG" and d["price"] == 4000.0
    assert "received_at" in d
