"""Orchestrateur : pipeline complet données → scores → alertes → snapshot."""
from __future__ import annotations

from datetime import datetime

from app.core.detector import RegimeDetector
from app.core.engine import ScoringEngine
from app.core.models import GoldSnapshot
from app.sentiment.engine import SentimentEngine
from app.sentiment.models import PositioningInputs
from app.sources.base import DataProvider, MacroInputs


class GoldMacroOrchestrator:
    """Pilote un cycle complet d'évaluation."""

    def __init__(self, provider: DataProvider, anthropic_key: str | None = None,
                 cost_guard=None, repository=None):
        self.provider = provider
        self.engine = ScoringEngine()
        self.detector = RegimeDetector()
        self.sentiment = SentimentEngine(anthropic_key=anthropic_key, cost_guard=cost_guard)
        self.repository = repository  # SnapshotRepository | None (persistance optionnelle)
        self.last_snapshot: GoldSnapshot | None = None

    def _persist(self, snapshot: GoldSnapshot) -> None:
        """Convertit le GoldSnapshot en StoredSnapshot et le persiste (append-only)."""
        from app.storage.base import StoredAlert, StoredSnapshot

        components = []
        for tf in (snapshot.structural, snapshot.tactical):
            for c in tf.components:
                components.append({
                    "name": c.name, "timeframe": tf.timeframe.value,
                    "zscore": c.zscore, "weight": c.weight, "contribution": c.contribution,
                })
        sent = snapshot.sentiment
        stored = StoredSnapshot(
            timestamp=snapshot.timestamp,
            structural_composite=snapshot.structural.composite,
            tactical_composite=snapshot.tactical.composite,
            sentiment_composite=getattr(sent, "composite", None),
            xau_price=snapshot.xau_price,
            aligned=snapshot.aligned,
            alerts=[StoredAlert(kind=a.kind, severity=a.severity, message=a.message,
                                timestamp=a.timestamp) for a in snapshot.alerts],
            components=components,
        )
        self.repository.save(stored)

    async def _evaluate(self, inputs: MacroInputs) -> GoldSnapshot:
        structural = self.engine.score_structural(inputs.structural_dict())
        tactical = self.engine.score_tactical(inputs.tactical_dict())

        # --- couche sentiment ---
        pos = None
        if any(v is not None for v in
               (inputs.retail_long_pct, inputs.put_call_gld, inputs.fear_greed)):
            pos = PositioningInputs(
                retail_long_pct=inputs.retail_long_pct,
                put_call_gld=inputs.put_call_gld,
                fear_greed=inputs.fear_greed,
            )
        sent = await self.sentiment.evaluate(
            positioning=pos,
            news=inputs.headlines,
            now=inputs.timestamp,
        )

        alerts = self.detector.evaluate(
            structural=structural,
            tactical=tactical,
            xau_price=inputs.xau_price,
            real_rates_value=inputs.real_rates_level,
            next_event_hours=inputs.next_event_hours,
            next_event_name=inputs.next_event_name,
            sentiment_score=sent.composite,
            sentiment_contrarian=sent.contrarian_flip,
        )

        snapshot = GoldSnapshot(
            timestamp=inputs.timestamp,
            structural=structural,
            tactical=tactical,
            alerts=alerts,
            xau_price=inputs.xau_price,
            sentiment=sent,
        )
        self.last_snapshot = snapshot
        if self.repository is not None:
            self._persist(snapshot)
        return snapshot

    async def run_cycle(self) -> GoldSnapshot:
        inputs = await self.provider.fetch()
        return await self._evaluate(inputs)
