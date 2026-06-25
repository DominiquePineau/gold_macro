"""Démo : simule une trajectoire de marché et affiche scores + alertes."""
import asyncio

from app.core.orchestrator import GoldMacroOrchestrator
from app.sources.mock import MockProvider


def bar(value: float, width: int = 20) -> str:
    """Mini jauge ASCII de -100 à +100."""
    filled = int((value + 100) / 200 * width)
    pos = "█" * filled + "░" * (width - filled)
    return f"[{pos}]"


async def main():
    orch = GoldMacroOrchestrator(provider=MockProvider(seed=7))

    # warm-up silencieux pour amorcer les z-scores
    for _ in range(15):
        await orch.run_cycle()
    print("=" * 92)
    print(" CYCLE | PRIX XAU |  STRUCTUREL   |  TACTIQUE     | SENTIMENT        | AL")
    print("=" * 92)

    for i in range(20):
        snap = await orch.run_cycle()
        s, t = snap.structural, snap.tactical
        sent = snap.sentiment
        align = "✓" if snap.aligned else " "
        sent_str = f"{sent.composite:>+5.0f} {sent.label.value[:10]:<10}" if sent else "n/a"
        print(f"  {i:>3}  | {snap.xau_price:>7.1f} | "
              f"{s.composite:>+5.0f} {bar(s.composite, 8)} | "
              f"{t.composite:>+5.0f} {bar(t.composite, 8)} | "
              f"{sent_str} | {align}")
        for a in snap.alerts:
            if a.kind == "EVENT_PROXIMITY":
                continue  # on masque le bruit événementiel pour lisibilité
            icon = {"CRITICAL": "🔴", "WARNING": "🟠", "INFO": "🔵"}.get(a.severity, "  ")
            print(f"       {icon} {a.kind}: {a.message}")

    print("=" * 92)
    print("\nDÉTAIL SENTIMENT (dernier cycle) :")
    sent = snap.sentiment
    print(f"  Composite      : {sent.composite:+.1f} ({sent.label.value})")
    print(f"  Positionnement : {sent.positioning_score}")
    print(f"  Textuel (NLP)  : {sent.textual_score}  ({sent.items_analyzed} headlines)")
    print(f"  Contrarian flip: {sent.contrarian_flip}")
    if sent.note:
        print(f"  Note           : {sent.note}")

    print("\nDÉCOMPOSITION DU DERNIER SCORE STRUCTUREL :")
    for c in snap.structural.components:
        print(f"  {c.name:<18} z={c.zscore:>+5.2f}  poids={c.weight:.2f}  "
              f"contrib={c.contribution:>+6.3f}")
        if "EXTRÊME" in c.note:
            print(f"       ⚠ {c.note}")


if __name__ == "__main__":
    asyncio.run(main())
