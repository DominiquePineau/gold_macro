"""Démo LIVE : RealProvider sur données réelles (FRED + COT CFTC + prix IG).

Prérequis (variables d'environnement) :
  FRED_API_KEY                              (FRED, gratuit)
  IG_API_KEY / IG_USERNAME / IG_PASSWORD    (prix XAU IG, lecture seule)
  IG_API_URL                                (déf. https://api.ig.com/gateway/deal)

Aucun ordre n'est passé : prix IG en LECTURE SEULE. La couche sentiment
(positionnement/news) n'est pas branchée ici (décisions de source en attente).

  python demo_live.py
"""
from __future__ import annotations

import asyncio
import os

from app.core.orchestrator import GoldMacroOrchestrator
from app.sources.price import IGPriceFeed
from app.sources.real import RealProvider


async def main() -> None:
    if not os.environ.get("FRED_API_KEY"):
        raise SystemExit("FRED_API_KEY manquante (source ton .env).")

    provider = RealProvider(price_feed=IGPriceFeed())  # FRED+COT+IG (creds via env)
    orch = GoldMacroOrchestrator(provider=provider)

    print("=== Gold Macro Engine — DÉMO LIVE (FRED + COT + prix IG) ===")
    inputs = await provider.fetch()
    print(f"\nDonnées brutes live :")
    print(f"  prix XAU (IG)        : {inputs.xau_price}")
    print(f"  taux réel 10Y (niv.) : {inputs.real_rates_level}")
    print(f"  Δ taux réel (bps)    : {inputs.real_rates_10y:+.1f}")
    print(f"  DXY daily (%)        : {inputs.dxy_daily:+.3f}")
    print(f"  COT net specs (CFTC) : {inputs.cot_net_specs:+.0f}")
    print(f"  yield momentum 10Y   : {inputs.yield_momentum_10y:+.3f}")

    snap = await orch._evaluate(inputs)
    print(f"\nScores :")
    print(f"  STRUCTUREL : {snap.structural.composite:+.1f} ({snap.structural.bias.value})")
    print(f"  TACTIQUE   : {snap.tactical.composite:+.1f} ({snap.tactical.bias.value})")
    print(f"  Aligné     : {'OUI' if snap.aligned else 'non'}")
    if snap.alerts:
        print("  Alertes :")
        for a in snap.alerts:
            print(f"    [{a.severity}] {a.kind}: {a.message}")
    print("\nNB : 1er cycle = z-scores sans historique (composites ~0 attendus).")


if __name__ == "__main__":
    asyncio.run(main())
