"""Démo LIVE : RealProvider sur données réelles (toutes sources branchées).

Sources (choix utilisateur) :
  - macro      : FRED (FRED_API_KEY, gratuit)
  - COT        : CFTC (gratuit, sans clé)
  - prix XAU   : flux du système `trade` (candle_data SQLite, pas de session broker)
  - sentiment  : proxy Fear&Greed maison (dérivé du prix)
  - news (NLP) : RSS gratuit (Google News + ForexLive) -> Claude Haiku si
                 ANTHROPIC_API_KEY présent, sinon repli lexique

Aucun ordre n'est passé. Prérequis : FRED_API_KEY (et éventuellement TRADE_DB_PATH,
ANTHROPIC_API_KEY).

  python demo_live.py
"""
from __future__ import annotations

import asyncio
import os

from app.core.orchestrator import GoldMacroOrchestrator
from app.sources.news import NewsProvider
from app.sources.positioning import ProxyPositioningFeed
from app.sources.price import TradeDBPriceFeed
from app.sources.real import RealProvider


async def main() -> None:
    if not os.environ.get("FRED_API_KEY"):
        raise SystemExit("FRED_API_KEY manquante (source ton .env).")

    provider = RealProvider(
        price_feed=TradeDBPriceFeed(),          # 1a : flux du système trade
        positioning_feed=ProxyPositioningFeed(),  # 2 : proxy F&G
        news_feed=NewsProvider(max_items=6),    # 3 : RSS (+ Claude si clé)
    )
    orch = GoldMacroOrchestrator(provider=provider,
                                 anthropic_key=os.environ.get("ANTHROPIC_API_KEY"))

    print("=== Gold Macro Engine — DÉMO LIVE (toutes sources réelles) ===")
    inputs = await provider.fetch()
    print(f"\nDonnées brutes live :")
    print(f"  prix XAU (flux trade) : {inputs.xau_price}")
    print(f"  taux réel 10Y (niv.)  : {inputs.real_rates_level}")
    print(f"  Δ taux réel (bps)     : {inputs.real_rates_10y:+.1f}")
    print(f"  DXY daily (%)         : {inputs.dxy_daily:+.3f}")
    print(f"  COT net specs (CFTC)  : {inputs.cot_net_specs:+.0f}")
    print(f"  Fear&Greed (proxy)    : {inputs.fear_greed}")
    print(f"  news (NLP)            : {len(inputs.headlines or [])} titres")

    snap = await orch._evaluate(inputs)
    print(f"\nScores :")
    print(f"  STRUCTUREL : {snap.structural.composite:+.1f} ({snap.structural.bias.value})")
    print(f"  TACTIQUE   : {snap.tactical.composite:+.1f} ({snap.tactical.bias.value})")
    sent = snap.sentiment
    if sent is not None:
        print(f"  SENTIMENT  : {sent.composite:+.1f} ({sent.label.value}) "
              f"[{sent.items_analyzed} news, source {'Claude' if os.environ.get('ANTHROPIC_API_KEY') else 'lexique'}]")
    print(f"  Aligné     : {'OUI' if snap.aligned else 'non'}")
    if snap.alerts:
        print("  Alertes :")
        for a in snap.alerts:
            print(f"    [{a.severity}] {a.kind}: {a.message}")
    print("\nNB : 1er cycle = z-scores sans historique (composites ~0 attendus).")


if __name__ == "__main__":
    asyncio.run(main())
