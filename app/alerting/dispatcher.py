"""Distribution des alertes par sévérité, avec dédup glissante et digest (Phase 4.2).

Politique (plan §4.2) :
  CRITICAL -> push immédiat (dédoublonné sur kind+direction, fenêtre glissante)
  WARNING  -> mis en digest (envoyé groupé via flush_digest, ex. horaire)
  INFO     -> journalisé seulement (jamais poussé sur le canal d'alerte)

Le `kind+direction` sert de clé de dédup : une même bascule répétée n'est pas
re-poussée tant qu'on est dans la fenêtre.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.alerting.sinks import AlertSink, LogSink
from app.core.models import Alert


def _direction(message: str) -> str:
    if "HAUSSIER" in message:
        return "HAUSSIER"
    if "BAISSIER" in message:
        return "BAISSIER"
    return ""


def _key(alert: Alert) -> str:
    return f"{alert.kind}:{_direction(alert.message)}"


_SEVERITY_EMOJI = {"CRITICAL": "🔴", "WARNING": "🟠", "INFO": "🔵"}

# Conseil d'action par type d'alerte (cf. RUNBOOK §5). Outil de CONTEXTE.
_HINTS = {
    "ALIGNMENT": "Conviction max : structurel et tactique convergent — le signal le plus fiable. Croise avec ta lecture de prix.",
    "BIAS_FLIP": "Bascule directionnelle. À confirmer avec ta lecture de prix avant d'agir.",
    "DIVERGENCE": "Épuisement possible de la tendance. Surveiller un retournement, ne pas trader seul.",
    "SENTIMENT_EXTREME": "Positionnement saturé : risque de retournement à contre-courant de la foule.",
    "SENTIMENT_DIVERGENCE": "Sentiment et prix divergent : signal contrarian d'épuisement.",
    "EVENT_PROXIMITY": "Événement macro imminent — prudence sur les nouvelles positions.",
}


def _fmt(alert: Alert) -> str:
    """Message d'alerte CLAIR et DÉTAILLÉ (sévérité, type, contexte, conseil, heure)."""
    emoji = _SEVERITY_EMOJI.get(alert.severity, "•")
    ts = alert.timestamp.strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"{emoji} {alert.severity} · {alert.kind}",
        alert.message,
    ]
    hint = _HINTS.get(alert.kind)
    if hint:
        lines.append(f"👉 {hint}")
    lines.append(f"🕒 {ts} · outil de contexte (n'exécute aucun ordre)")
    return "\n".join(lines)


class AlertDispatcher:
    """Route les alertes vers un sink selon leur sévérité, avec dédup + digest."""

    def __init__(self, sink: AlertSink | None = None, *,
                 dedup_window_seconds: float = 3600.0):
        self.sink = sink or LogSink()
        self.dedup_window = dedup_window_seconds
        self._last_sent: dict[str, datetime] = {}
        self._digest: list[Alert] = []
        self.info_log: list[str] = []

    def _is_duplicate(self, alert: Alert, now: datetime) -> bool:
        last = self._last_sent.get(_key(alert))
        return last is not None and (now - last).total_seconds() < self.dedup_window

    async def dispatch(self, alerts: list[Alert], *, now: datetime | None = None) -> int:
        """Traite une volée d'alertes. Retourne le nombre de pushes CRITICAL effectués."""
        now = now or datetime.now(timezone.utc)
        pushed = 0
        for a in alerts:
            if a.severity == "CRITICAL":
                if self._is_duplicate(a, now):
                    continue  # déjà poussée récemment -> on évite le spam
                if await self.sink.send(_fmt(a)):
                    pushed += 1
                self._last_sent[_key(a)] = now
            elif a.severity == "WARNING":
                self._digest.append(a)  # groupé pour flush_digest
            else:  # INFO
                self.info_log.append(_fmt(a))
        return pushed

    async def flush_digest(self) -> int:
        """Envoie les WARNING accumulés en un seul message groupé (dédoublonné)."""
        if not self._digest:
            return 0
        seen: set[str] = set()
        lines: list[str] = []
        for a in self._digest:
            k = _key(a)
            if k in seen:
                continue
            seen.add(k)
            lines.append(_fmt(a))
        self._digest.clear()
        await self.sink.send("📋 DIGEST WARNINGS\n" + "\n".join(lines))
        return len(lines)

    async def notify(self, text: str) -> bool:
        """Envoi direct d'un message hors-alerte (ex. rapport de coût Claude)."""
        return await self.sink.send(text)
