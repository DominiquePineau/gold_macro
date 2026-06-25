"""Scheduler asyncio : évalue périodiquement et distribue les alertes (Phase 4.1).

- Cadence d'évaluation configurable (``tick_seconds``).
- Digest des WARNING vidé sur une cadence plus lente (``digest_seconds``).
- Rapports de coût Claude (CostGuard.on_report) routés vers le canal d'alerte.
- Arrêt PROPRE : ``stop()`` (ou SIGTERM/SIGINT via l'entrypoint) termine le cycle
  courant puis sort ; pas de sleep bloquant non interruptible.

Découplage des fréquences : les sources lentes (COT hebdo, FRED quotidien, news)
sont mises en cache au niveau des connecteurs, donc un tick rapide ne re-télécharge
pas tout — seul le scoring est recalculé à chaque tick.
"""
from __future__ import annotations

import asyncio
import time
from typing import Optional

from app.alerting.dispatcher import AlertDispatcher
from app.core.orchestrator import GoldMacroOrchestrator


class Scheduler:
    def __init__(self, orchestrator: GoldMacroOrchestrator, dispatcher: AlertDispatcher,
                 *, tick_seconds: float = 300.0, digest_seconds: float = 3600.0,
                 cost_guard=None):
        self.orchestrator = orchestrator
        self.dispatcher = dispatcher
        self.tick = tick_seconds
        self.digest_every = digest_seconds
        self._stop = asyncio.Event()
        self._pending_notices: list[str] = []
        self.cycles = 0
        self._last_digest = 0.0
        if cost_guard is not None:
            # le rapport "tous les 1€" / l'alerte STOP sont mis en file ici (sync),
            # puis drainés vers le canal à chaque cycle.
            cost_guard.on_report = self._on_cost_report

    def _on_cost_report(self, spent_eur: float, detail: dict) -> None:
        if detail.get("kind") == "STOP":
            self._pending_notices.append(
                f"🛑 Claude COÛT — plafond {detail['cap_eur']}€ atteint "
                f"({spent_eur:.2f}€). Appels suspendus → repli lexique.")
        else:
            self._pending_notices.append(
                f"💸 Claude COÛT — palier {detail['palier_eur']}€ franchi "
                f"({spent_eur:.2f}€, {detail['calls']} appels, "
                f"plafond {detail['cap_eur']}€).")

    async def _drain_notices(self) -> None:
        while self._pending_notices:
            await self.dispatcher.notify(self._pending_notices.pop(0))

    async def run_once(self):
        """Un cycle : évalue, distribue alertes, draine les notices de coût."""
        snap = await self.orchestrator.run_cycle()
        await self.dispatcher.dispatch(snap.alerts)
        await self._drain_notices()
        self.cycles += 1
        return snap

    def stop(self) -> None:
        self._stop.set()

    async def run(self, *, max_cycles: Optional[int] = None) -> None:
        """Boucle principale. S'arrête sur ``stop()`` ou après ``max_cycles``."""
        self._last_digest = time.monotonic()
        while not self._stop.is_set():
            await self.run_once()

            # digest périodique des WARNING
            if time.monotonic() - self._last_digest >= self.digest_every:
                await self.dispatcher.flush_digest()
                self._last_digest = time.monotonic()

            if max_cycles is not None and self.cycles >= max_cycles:
                break

            # sleep INTERRUPTIBLE : se réveille immédiatement si stop() est appelé
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.tick)
            except asyncio.TimeoutError:
                pass  # tick écoulé -> prochain cycle

        # arrêt propre : on vide le digest restant
        await self.dispatcher.flush_digest()
        await self._drain_notices()
