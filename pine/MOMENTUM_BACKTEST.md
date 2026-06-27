# Momentum / Trend-following sur XAU — backtest honnête

**Données :** XAUUSD D1, 2020-2026. Coûts 2 bps/transition. Anti look-ahead
(position décalée d'1 jour). Validation OOS train 2020-2023 / test 2024-2026.
Repro : `python scripts/backtest_momentum.py`.

## Le résultat qui compte (et qui surprend)
**Sur l'or 2020-2026, AUCUNE stratégie de momentum ne bat le simple Buy & Hold —
ni en rendement, ni en Sharpe.** L'or a tellement tendance haussière que rester
long en permanence gagne. Le momentum sert au DRAWDOWN, pas à la surperformance.

## Période complète (2020-2026)
| Stratégie | CAGR | Sharpe | max DD | % en position | total |
|---|---:|---:|---:|---:|---:|
| **Buy & Hold** | 13.9% | **0.87** | −26.6% | 100% | +182% |
| TSMOM long-only | 9.4% | 0.72 | −20.1% | 65% | +104% |
| Trend MA 50/200 | 7.9% | 0.63 | −23.6% | 62% | +83% |
| **Donchian 55/20** | 7.9% | 0.68 | **−15.9%** | **45%** | +84% |

→ Buy & Hold gagne en rendement ET en Sharpe. Mais **Donchian divise le drawdown
par ~1.7 (−16% vs −27%) en n'étant en position que 45% du temps.**

## Hors échantillon
| | Buy & Hold | TSMOM | Trend MA | Donchian |
|---|---:|---:|---:|---:|
| **TRAIN 2020-2023** (Sharpe) | 0.50 | −0.06 | −0.33 | 0.06 |
| **TEST 2024-2026** (Sharpe) | 1.33 | 0.98 | 1.13 | **1.34** |

- **2020-2023 (marché chahuté)** : tous les momentum PERDENT de l'argent
  (whipsaws), Buy & Hold gagne. → le momentum souffre en range.
- **2024-2026 (forte tendance)** : Donchian ÉGALE le Sharpe du Buy & Hold (1.34)
  avec 59% d'exposition et un drawdown bien moindre. → le momentum brille en trend.

## Verdict d'expert (honnête)
1. **Pas de free lunch** : sur l'or, timer la tendance ne bat pas « acheter et
   tenir ». Le fameux edge TSMOM est un edge PAR TRADE (+0.06 R), pas un edge
   vs Buy & Hold — gold a trop monté.
2. **La vraie valeur du momentum = contrôle du risque.** Donchian 55/20 (style
   Turtle) est le plus robuste : meilleur drawdown (−16%), moitié moins exposé,
   Sharpe correct, et hors-échantillon il tient (1.34 en test). Idéal si tu veux
   participer à la tendance de l'or SANS subir les grosses corrections.
3. **Quand l'utiliser** : Donchian/trend = excellent en régime de tendance, à
   éviter en range (2020-2023 l'a puni). D'où l'intérêt de croiser avec le biais
   macro de gold_macro (rester long quand structurel+tactique sont alignés
   haussiers, se mettre flat sinon).
4. **Recommandation** : pour TradingView, je te livre la **Donchian/Turtle**
   (`momentum_xau.pine`) — simple, robuste, orientée drawdown. C'est le profil le
   plus sain pour trader la tendance de l'or mécaniquement.
