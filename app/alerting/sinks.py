"""Destinations d'alertes (sinks). Configurable par environnement.

- LogSink      : journalise seulement (défaut sûr, aucune fuite externe)
- WebhookSink  : POST {"text": ...} vers ALERT_WEBHOOK_URL (Discord/pipeline)
- TelegramSink : sendMessage via l'API bot Telegram (TELEGRAM_BOT_TOKEN + CHAT_ID)

`build_sink()` choisit selon l'env. Tous les sinks sont en mode DÉGRADÉ : une
erreur d'envoi ne casse jamais le cycle (l'alerte est juste perdue côté canal).
"""
from __future__ import annotations

import os
from typing import Optional, Protocol, runtime_checkable

import httpx


@runtime_checkable
class AlertSink(Protocol):
    async def send(self, text: str) -> bool:
        """Envoie un message. Retourne True si livré, False si dégradé."""
        ...


class LogSink:
    """Sink par défaut : journalise (liste interne pour inspection/tests)."""

    def __init__(self) -> None:
        self.messages: list[str] = []

    async def send(self, text: str) -> bool:
        self.messages.append(text)
        print(f"[ALERT] {text}", flush=True)
        return True


class WebhookSink:
    """POST générique {"text": ...} (Discord, n8n, pipeline DSC...)."""

    def __init__(self, url: str, *, timeout: float = 10.0):
        self.url = url
        self.timeout = timeout

    async def send(self, text: str) -> bool:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.post(self.url, json={"text": text})
                r.raise_for_status()
            return True
        except Exception:
            return False


class TelegramSink:
    """Bot Telegram : sendMessage vers un chat_id."""

    def __init__(self, token: str, chat_id: str, *, timeout: float = 10.0):
        self.token = token
        self.chat_id = chat_id
        self.timeout = timeout

    async def send(self, text: str) -> bool:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.post(
                    f"https://api.telegram.org/bot{self.token}/sendMessage",
                    json={"chat_id": self.chat_id, "text": text},
                )
                r.raise_for_status()
            return True
        except Exception:
            return False


def build_sink() -> AlertSink:
    """Construit le sink selon l'environnement (priorité Telegram > webhook > log)."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if token and chat_id:
        return TelegramSink(token, chat_id)
    url: Optional[str] = os.environ.get("ALERT_WEBHOOK_URL")
    if url:
        return WebhookSink(url)
    return LogSink()  # défaut sûr : pas de destination configurée -> log seulement
