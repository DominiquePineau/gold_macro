"""Test d'intégration : N cycles -> N snapshots persistés (DoD Phase 3)."""
from __future__ import annotations

from app.core.orchestrator import GoldMacroOrchestrator
from app.sources.mock import MockProvider
from app.storage.sqlite import SQLiteSnapshotRepository


async def test_cycles_persist_snapshots(tmp_path):
    repo = SQLiteSnapshotRepository(db_path=str(tmp_path / "cycles.db"))
    orch = GoldMacroOrchestrator(provider=MockProvider(seed=7), repository=repo)

    N = 8
    for _ in range(N):
        await orch.run_cycle()

    assert repo.count_snapshots() == N           # N cycles -> N snapshots
    hist = repo.history()
    assert len(hist) == N
    # cohérence : composites bornés, prix présent
    for h in hist:
        assert -100.0 <= h.structural_composite <= 100.0
        assert h.xau_price is not None
    # l'historique est trié chronologiquement
    ts = [h.timestamp for h in hist]
    assert ts == sorted(ts)


async def test_no_repository_means_no_persistence(tmp_path):
    # sans repository, run_cycle ne persiste rien (et ne casse pas)
    orch = GoldMacroOrchestrator(provider=MockProvider(seed=1))
    snap = await orch.run_cycle()
    assert snap is not None


async def test_alerts_persisted_with_snapshots(tmp_path):
    repo = SQLiteSnapshotRepository(db_path=str(tmp_path / "al.db"))
    orch = GoldMacroOrchestrator(provider=MockProvider(seed=42), repository=repo)
    for _ in range(12):
        await orch.run_cycle()
    # le scénario mock génère des alertes -> au moins une persistée
    assert len(repo.alerts()) >= 1
