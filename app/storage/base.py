"""Contrat de la couche de persistance (repository pattern).

Append-only (event sourcing) : on n'UPDATE/DELETE jamais l'historique.
Le cœur reste découplé de l'implémentation (SQLite, Postgres, mémoire...).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Protocol, runtime_checkable


@dataclass
class StoredAlert:
    kind: str
    severity: str
    message: str
    timestamp: datetime


@dataclass
class StoredSnapshot:
    """Vue persistée d'un GoldSnapshot (composites + contexte + alertes)."""
    timestamp: datetime
    structural_composite: float
    tactical_composite: float
    aligned: bool
    sentiment_composite: Optional[float] = None
    xau_price: Optional[float] = None
    alerts: list[StoredAlert] = field(default_factory=list)
    # décomposition par facteur (audit) : {name, timeframe, zscore, weight, contribution}
    components: list[dict] = field(default_factory=list)
    id: Optional[int] = None  # rempli après écriture


@runtime_checkable
class SnapshotRepository(Protocol):
    """Persistance append-only des snapshots + requêtes d'historique."""

    def save(self, snapshot: StoredSnapshot) -> int:
        """Persiste un snapshot (et ses alertes/composantes). Retourne son id."""
        ...

    def history(self, *, since: Optional[datetime] = None,
                until: Optional[datetime] = None, limit: int = 1000) -> list[StoredSnapshot]:
        """Série temporelle des snapshots (filtrable par fenêtre)."""
        ...

    def alerts(self, *, kind: Optional[str] = None, severity: Optional[str] = None,
               limit: int = 1000) -> list[StoredAlert]:
        """Journal des alertes (filtrable par type/sévérité)."""
        ...
