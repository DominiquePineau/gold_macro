# Donchian × biais gold_macro — backtest (la combinaison « prometteuse »)

**Idée testée :** filtrer le Donchian par le biais macro de gold_macro pour éviter
les whipsaws de range. **Données :** XAU D1 2020-2026, composites rejoués par le
moteur réel (HistoricalReplay). Repro : `python scripts/backtest_combo.py`.

## Verdict honnête : la combinaison N'AMÉLIORE PAS le risque-ajusté
Aucune variante (confirmation ou veto) ne bat le **Donchian seul** (Sharpe 0.68)
sur la période complète. Le filtre macro coupe énormément l'exposition et le
drawdown, mais au prix du rendement — pas de free lunch.

## Période complète (Sharpe / max DD / % exposé)
| Stratégie | Sharpe | max DD | exposé |
|---|---:|---:|---:|
| Buy & Hold | **0.87** | −26.6% | 100% |
| **Donchian seul** | **0.68** | −15.9% | 45% |
| Donchian × struct>0 | 0.18 | −17.2% | 23% |
| Donchian × aligné (>15) | 0.56 | **−6.3%** | 5% |
| Donchian × struct>15 | 0.44 | −14.8% | 10% |
| Donchian veto struct<−15 | 0.51 | −19.7% | 37% |

## Ce que ça révèle (hors échantillon)
- **TRAIN 2020-2023 (range)** : le filtre AIDE — Donchian seul Sharpe 0.06 (whipsaw)
  → « × struct>15 » Sharpe **0.92** (DD −4.2%, exposé 6%). L'hypothèse marche EN RANGE.
- **TEST 2024-2026 (tendance)** : le filtre NUIT — Donchian seul Sharpe 1.29
  → « × struct>0 » Sharpe 0.55. Il sur-filtre et rate la tendance.

→ Le filtre macro est trop restrictif : les composites du moteur atteignent rarement
des niveaux forts (>15), donc on est en position 5-23% du temps seulement. Bon en
range, mauvais en tendance → ça s'annule, pas de gain net.

## Conclusion (la vérité, sans survente)
1. **Pas d'edge ajouté par la combinaison.** Le biais macro, en filtre dur de trade,
   sur-restreint.
2. **Pour trader la tendance de l'or mécaniquement** : Donchian seul (meilleur
   risque-ajusté simple, Sharpe 0.68, DD −16%) ou buy & hold (meilleur rendement).
3. **La valeur de gold_macro reste le CONTEXTE** : le dashboard et l'alerte
   ALIGNMENT (petit edge directionnel ~+5pp) comme « heads-up » de régime — pas
   comme filtre d'exécution dur.
4. **Bilan de toute la recherche XAU** : le simple bat le malin. Tenir l'or, ou un
   Donchian pour lisser le drawdown ; le SMC/ICT mécanique et les filtres macro
   durs n'ajoutent pas d'edge mesurable. Le seul edge robuste reste directionnel
   (momentum long), et il ne bat pas le buy & hold tellement l'or a monté.
