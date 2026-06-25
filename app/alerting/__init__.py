"""Distribution des alertes : routage par sévérité, dédup, digest, sinks (Phase 4)."""
from app.alerting.dispatcher import AlertDispatcher
from app.alerting.sinks import LogSink, TelegramSink, WebhookSink, build_sink

__all__ = ["AlertDispatcher", "LogSink", "WebhookSink", "TelegramSink", "build_sink"]
