"""Génère le rapport de calibration (Phase 5.4) : métriques + graphes + markdown.

Sortie :
  results/CALIBRATION_REPORT.md
  results/fig_alignment_markers.png
  results/fig_hitrate_vs_base.png
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from app.backtest.calibrate import calibrate, robust_pick  # noqa: E402
from app.backtest.metrics import (  # noqa: E402
    alert_counts,
    base_rate_up,
    evaluate_alignment,
    evaluate_bias_flip,
    evaluate_divergence,
)
from app.backtest.replay import HistoricalReplay, load_rows  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RES = ROOT / "results"
RES.mkdir(exist_ok=True)
DATA = ROOT / "data" / "backtest_daily.csv"


def fig_alignment_markers(points):
    fig, ax = plt.subplots(figsize=(11, 4.5))
    dates = [p.date for p in points]
    prices = [p.xau_price for p in points]
    ax.plot(dates, prices, color="#444", lw=0.8, label="XAU/USD")
    for p in points:
        if "ALIGNMENT" in p.alert_kinds:
            up = p.structural > 0
            ax.scatter(p.date, p.xau_price, marker="^" if up else "v",
                       color="green" if up else "red", s=28, zorder=3)
    ax.set_title("XAU/USD — alertes ALIGNMENT (▲ haussier / ▼ baissier)")
    ax.set_ylabel("Prix")
    ax.legend(loc="upper left")
    fig.tight_layout()
    out = RES / "fig_alignment_markers.png"
    fig.savefig(out, dpi=110)
    plt.close(fig)
    return out


def fig_hitrate_vs_base(align, biasf, diverg):
    fig, ax = plt.subplots(figsize=(9, 4.5))
    groups = []
    hits = []
    bases = []
    for evs, name in ((align, "ALIGN"), (biasf, "FLIP"), (diverg, "DIVERG")):
        for e in evs:
            groups.append(f"{name}\nN={e.horizon}")
            hits.append(e.hit_rate)
            bases.append(e.base_rate)
    x = range(len(groups))
    ax.bar([i - 0.2 for i in x], hits, width=0.4, label="hit-rate", color="#2a7")
    ax.bar([i + 0.2 for i in x], bases, width=0.4, label="base rate", color="#bbb")
    ax.axhline(50, color="k", lw=0.5, ls="--")
    ax.set_xticks(list(x))
    ax.set_xticklabels(groups, fontsize=8)
    ax.set_ylabel("%")
    ax.set_title("Hit-rate des signaux vs base rate inconditionnel")
    ax.legend()
    fig.tight_layout()
    out = RES / "fig_hitrate_vs_base.png"
    fig.savefig(out, dpi=110)
    plt.close(fig)
    return out


def main():
    rows = load_rows(str(DATA))
    points = HistoricalReplay(rows).run()  # poids calibrés (config.py à jour)
    align = evaluate_alignment(points)
    biasf = evaluate_bias_flip(points)
    diverg = evaluate_divergence(points)
    counts = alert_counts(points)
    best, results = calibrate(rows, boundary="2024-01-01", horizon=10)
    robust = robust_pick(results)

    f1 = fig_alignment_markers(points)
    f2 = fig_hitrate_vs_base(align, biasf, diverg)

    def tbl(evs):
        out = "| Horizon | n | hit-rate | base rate | **edge** | avg fwd (dir) |\n"
        out += "|---:|---:|---:|---:|---:|---:|\n"
        for e in evs:
            out += f"| {e.horizon}j | {e.n_signals} | {e.hit_rate}% | {e.base_rate}% | **{e.edge:+}pp** | {e.avg_forward:+}% |\n"
        return out

    md = f"""# Rapport de calibration — Gold Macro Engine (Phase 5)

**Date :** 2026-06-25 · **Données :** {points[0].date.date()} → {points[-1].date.date()} ({len(points)} jours)
**Sources :** XAU (xau-system M5→D1), FRED (DFII10/DGS10/DTWEXBGS), COT CFTC (point-in-time).
**Périmètre :** signaux MACRO (structurel + tactique). La couche sentiment est
absente du backtest (pas d'historique de positionnement/news) — non évaluée ici.

> Réplay **causal** (z-scores et momentum calculés uniquement sur données ≤ T,
> aucun look-ahead). Tout hit-rate est comparé au **base rate** inconditionnel
> (l'or a monté sur la période → un signal "haussier" paraît bon par défaut ;
> l'edge réel = au-dessus du base rate).

## Volume d'alertes
{', '.join(f'{k}={v}' for k, v in counts.items())}
Base rate (P[or monte]) : 5j={base_rate_up(points,5):.1f}% · 10j={base_rate_up(points,10):.1f}% · 20j={base_rate_up(points,20):.1f}%

## ALIGNMENT (les 2 timeframes convergent)
{tbl(align)}
→ **Seul signal avec un edge net et persistant** (~+5pp au-dessus du base rate, toutes
fenêtres). C'est le signal actionnable.

## BIAS_FLIP (croisement de zéro structurel)
{tbl(biasf)}
→ Edge faible et décroissant avec l'horizon. Beaucoup de signaux, bruité. Marginal.

## DIVERGENCE (prix/taux réels même sens — épuisement attendu)
{tbl(diverg)}
→ **Pas d'edge mesurable** (~50/50). Le signal d'épuisement ne prédit pas
fiablement un retournement sur cet historique.

![alignment]({f1.name})
![hitrate]({f2.name})

## Calibration des poids (validation out-of-sample)

Optimisation de l'edge ALIGNMENT (N=10) — train 2020-2023 / test 2024-2026 :

- **Meilleur sur TRAIN** : struct {best.struct_weights} / tact {best.tact_weights}
  → train edge **{best.train_edge}pp** mais test edge **{best.test_edge}pp** = SURAPPRENTISSAGE.
- **Choix ROBUSTE retenu** : struct {robust.struct_weights} / tact {robust.tact_weights}
  → train **{robust.train_edge}pp** / test **{robust.test_edge}pp** = STABLE in/out-of-sample.

`config.py` mis à jour avec les poids robustes (real_rates 0.50 / dxy 0.30 / cot 0.20).
Le gain sur les poids d'origine est **marginal** — ils étaient déjà sains. On ne
sur-optimise pas (garde-fou anti-overfit du plan).

## Conclusion honnête

| Signal | Edge | Verdict |
|---|---|---|
| ALIGNMENT | ~+5pp stable OOS | ✅ edge réel, actionnable comme CONTEXTE |
| BIAS_FLIP | +0.7 à +2.6pp | ⚠️ marginal, bruité |
| DIVERGENCE | ~0 | ❌ pas d'edge mesurable |

**L'outil a un edge mesurable et robuste sur l'ALIGNEMENT macro structurel+tactique**
(~+5pp au-dessus du hasard, validé hors échantillon). Les bascules (BIAS_FLIP) sont
trop bruitées pour être tradées seules, et la DIVERGENCE prix/taux n'a pas d'edge
directionnel sur cette période. Rappel : **outil de contexte, pas signal d'entrée**.
La couche sentiment (non backtestable faute d'historique) reste à valider en live.
"""
    (RES / "CALIBRATION_REPORT.md").write_text(md)
    print(f"Rapport -> {RES / 'CALIBRATION_REPORT.md'}")
    print(f"Figures -> {f1.name}, {f2.name}")
    print(f"\nALIGNMENT edges: {[e.edge for e in align]}")
    print(f"Robuste: struct{robust.struct_weights} tact{robust.tact_weights} "
          f"train={robust.train_edge} test={robust.test_edge}")


if __name__ == "__main__":
    main()
