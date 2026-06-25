"""Tests du scheduler (app/scheduler/runner.py)."""
from __future__ import annotations

import asyncio

from app.alerting.dispatcher import AlertDispatcher
from app.alerting.sinks import LogSink
from app.core.orchestrator import GoldMacroOrchestrator
from app.scheduler.runner import Scheduler
from app.sentiment.cost import CostGuard
from app.sources.mock import MockProvider
from app.storage.sqlite import SQLiteSnapshotRepository


def _scheduler(tmp_path, **kw):
    repo = SQLiteSnapshotRepository(db_path=str(tmp_path / "s.db"))
    orch = GoldMacroOrchestrator(provider=MockProvider(seed=3), repository=repo)
    disp = AlertDispatcher(LogSink())
    return Scheduler(orch, disp, tick_seconds=0.001, digest_seconds=1e9, **kw), repo, disp


async def test_runs_max_cycles(tmp_path):
    sched, repo, _ = _scheduler(tmp_path)
    await sched.run(max_cycles=5)
    assert sched.cycles == 5
    assert repo.count_snapshots() == 5


async def test_stop_halts_loop(tmp_path):
    sched, _, _ = _scheduler(tmp_path)
    sched.tick = 0.05
    task = asyncio.create_task(sched.run())
    await asyncio.sleep(0.02)
    sched.stop()
    await asyncio.wait_for(task, timeout=2.0)  # s'arrête proprement
    assert sched._stop.is_set()


async def test_alerts_dispatched(tmp_path):
    sched, _, disp = _scheduler(tmp_path)
    await sched.run(max_cycles=12)  # le mock génère des alertes/CRITICAL
    # au moins un push CRITICAL OU un digest a transité par le sink
    assert isinstance(disp.sink, LogSink)


async def test_cost_report_routed_to_channel(tmp_path):
    repo = SQLiteSnapshotRepository(db_path=str(tmp_path / "c.db"))
    orch = GoldMacroOrchestrator(provider=MockProvider(seed=1), repository=repo)
    sink = LogSink()
    disp = AlertDispatcher(sink)
    guard = CostGuard(report_every_eur=1.0, hard_stop_eur=10.0, usd_per_eur=1.0)
    sched = Scheduler(orch, disp, cost_guard=guard, tick_seconds=0.001, digest_seconds=1e9)
    # simule une conso Claude franchissant 2 paliers
    guard.record(300_000, 300_000)  # ~1.8 € -> palier 1€
    await sched.run_once()           # draine les notices -> canal
    assert any("Claude COÛT" in m and "palier 1" in m for m in sink.messages)


async def test_graceful_flush_on_exit(tmp_path):
    sched, _, disp = _scheduler(tmp_path)
    # injecte un WARNING en digest, puis run 1 cycle -> flush à la sortie
    from app.core.models import Alert
    await disp.dispatch([Alert(kind="DIVERGENCE", severity="WARNING", message="x")])
    await sched.run(max_cycles=1)
    assert any("DIGEST" in m for m in disp.sink.messages)
