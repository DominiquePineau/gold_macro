"""Tests des sinks d'alerte (app/alerting/sinks.py)."""
from __future__ import annotations

from app.alerting.sinks import LogSink, TelegramSink, WebhookSink, build_sink


async def test_log_sink():
    s = LogSink()
    assert await s.send("hello") is True
    assert s.messages == ["hello"]


class _Resp:
    def raise_for_status(self): return None


def _client(capture, fail=False):
    class _C:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, **k):
            if fail:
                raise RuntimeError("network")
            capture.append((url, k.get("json")))
            return _Resp()
    return _C


async def test_webhook_sink_posts(monkeypatch):
    import app.alerting.sinks as sinks
    cap = []
    monkeypatch.setattr(sinks.httpx, "AsyncClient", _client(cap))
    assert await WebhookSink("http://hook").send("msg") is True
    assert cap[0][0] == "http://hook"
    assert cap[0][1] == {"text": "msg"}


async def test_webhook_sink_degraded(monkeypatch):
    import app.alerting.sinks as sinks
    monkeypatch.setattr(sinks.httpx, "AsyncClient", _client([], fail=True))
    assert await WebhookSink("http://hook").send("msg") is False  # pas d'exception


async def test_telegram_sink_posts(monkeypatch):
    import app.alerting.sinks as sinks
    cap = []
    monkeypatch.setattr(sinks.httpx, "AsyncClient", _client(cap))
    assert await TelegramSink("TOK", "123").send("hi") is True
    assert "botTOK/sendMessage" in cap[0][0]
    assert cap[0][1] == {"chat_id": "123", "text": "hi"}


def test_build_sink_priority(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.delenv("ALERT_WEBHOOK_URL", raising=False)
    assert isinstance(build_sink(), LogSink)  # rien configuré -> log

    monkeypatch.setenv("ALERT_WEBHOOK_URL", "http://hook")
    assert isinstance(build_sink(), WebhookSink)

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "T")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "C")
    assert isinstance(build_sink(), TelegramSink)  # Telegram prioritaire
