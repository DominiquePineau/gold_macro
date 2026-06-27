"""Entrypoint : `python -m app.scheduler` — boucle live avec arrêt propre.

Variables d'environnement :
  GOLD_MACRO_TICK_SECONDS   cadence d'évaluation (défaut 300 = 5 min)
  GOLD_MACRO_DIGEST_SECONDS cadence du digest WARNING (défaut 3600 = 1 h)
  GOLD_MACRO_DB             base SQLite (défaut gold_macro.db)
  COST_REPORT_EVERY_EUR     palier de rapport coût Claude (défaut 1.0)
  COST_HARD_STOP_EUR        plafond dur coût Claude (défaut 10.0)
  FRED_API_KEY / ANTHROPIC_API_KEY / TELEGRAM_BOT_TOKEN+TELEGRAM_CHAT_ID
  (ou ALERT_WEBHOOK_URL)    sources & destination des alertes

Destination des alertes : Telegram si TELEGRAM_* présents, sinon webhook si
ALERT_WEBHOOK_URL, sinon journal seulement (aucune fuite).
"""
from __future__ import annotations

import asyncio
import os
import signal

from app import config as cfg_mod
from app.alerting.dispatcher import AlertDispatcher
from app.alerting.sinks import build_sink
from app.core.orchestrator import GoldMacroOrchestrator
from app.scheduler.runner import Scheduler
from app.sentiment.cost import CostGuard
from app.sources.news import NewsProvider
from app.sources.positioning import ProxyPositioningFeed
from app.sources.price import TradeDBPriceFeed
from app.sources.calendar import EconomicCalendar
from app.sources.real import RealProvider
from app.storage.sqlite import SQLiteSnapshotRepository


def _f(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


async def main() -> None:
    # fail-fast : FRED requise pour le socle macro live (cf. .env.example)
    cfg = cfg_mod.load()
    cfg_mod.validate(cfg, required=("FRED_API_KEY",))
    print("Config:", cfg_mod.summary(cfg), flush=True)

    fomc = [d.strip() for d in os.environ.get("GOLD_MACRO_FOMC_DATES", "").split(",") if d.strip()] or None
    econ = EconomicCalendar(cfg.fred_api_key, fomc_dates=fomc) if cfg.fred_api_key else None
    provider = RealProvider(
        price_feed=TradeDBPriceFeed(),
        calendar=econ.hours_to_next if econ else None,
        calendar_name_feed=econ.next_event_name if econ else None,
        positioning_feed=ProxyPositioningFeed(),
        news_feed=NewsProvider(cache_ttl_seconds=_f("GOLD_MACRO_NEWS_TTL", 1800.0)),
    )
    cost_guard = CostGuard(report_every_eur=_f("COST_REPORT_EVERY_EUR", 1.0),
                           hard_stop_eur=_f("COST_HARD_STOP_EUR", 10.0))
    repository = SQLiteSnapshotRepository(db_path=os.environ.get("GOLD_MACRO_DB", "gold_macro.db"))
    orchestrator = GoldMacroOrchestrator(
        provider=provider,
        anthropic_key=os.environ.get("ANTHROPIC_API_KEY"),
        cost_guard=cost_guard,
        repository=repository,
    )
    dispatcher = AlertDispatcher(build_sink())
    scheduler = Scheduler(orchestrator, dispatcher, cost_guard=cost_guard,
                          tick_seconds=_f("GOLD_MACRO_TICK_SECONDS", 300.0),
                          digest_seconds=_f("GOLD_MACRO_DIGEST_SECONDS", 3600.0))

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, scheduler.stop)
        except NotImplementedError:
            pass  # plateformes sans add_signal_handler

    print(f"Gold Macro Engine — scheduler démarré (tick={scheduler.tick}s). Ctrl-C pour arrêter.")
    await scheduler.run()
    print(f"Arrêt propre après {scheduler.cycles} cycles.")


if __name__ == "__main__":
    asyncio.run(main())
