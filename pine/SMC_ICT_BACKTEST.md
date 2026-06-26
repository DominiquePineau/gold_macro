# Backtest — SMC/ICT Ultimate (XAU/USD)

**Données :** XAUUSD M15, 2020-01 → 2026-06 (152 472 bougies).
**Modèle testé (port du Pine) :** sweep de liquidité → CHoCH/tendance → retour en
discount + OTE → confluence FVG/OB → entrée ; SL sous le sweep + buffer ATR ;
TP sur la liquidité opposée. Sortie barre par barre (SL prioritaire). Coûts déduits.
Repro : `python scripts/backtest_smc_ict.py`.

## Verdict en une phrase
**Le modèle SMC/ICT mécanisé n'a PAS d'edge sur XAU : espérance négative à tous les
niveaux de coûts, et déjà ≈ −0.15 R MÊME SANS FRAIS.** Cohérent avec nos résultats
antérieurs (Golden FVG falsifié, Sweep/CISD sans edge).

## Modèle complet — sensibilité aux coûts
| Coût A/R | n | win% | **espérance R** | PF | max DD% |
|---|---:|---:|---:|---:|---:|
| 0.00 $ (frictionless) | 75 | 33.3 | **−0.147** | 0.78 | −17.4 |
| 0.30 $ | 75 | 33.3 | −0.213 | 0.70 | −20.8 |
| 0.60 $ (réaliste) | 75 | 33.3 | −0.278 | 0.63 | −24.2 |
| 1.00 $ | 75 | 33.3 | −0.366 | 0.55 | −28.4 |

Win rate 33 % avec gain moyen ~1.5 R et perte ~−1 R ⇒ espérance négative. Le
problème n'est pas les coûts (négatif même à 0), c'est l'absence d'edge directionnel.

## Ablations (coût 0.60 $) — quelle brique sert à quoi ?
| Variante | n | espérance R | PF | win% | max DD% |
|---|---:|---:|---:|---:|---:|
| Complet | 75 | −0.278 | 0.63 | 33.3 | −24.2 |
| sans OTE | 173 | −0.139 | 0.78 | 43.4 | −27.4 |
| sans Discount | 75 | −0.278 | 0.63 | 33.3 | −24.2 |
| sans Kill Zone | 375 | −0.108 | 0.84 | 39.7 | −46.8 |
| sans FVG/OB | 1503 | −0.141 | 0.81 | 36.7 | **−94.4** |

**Lecture d'expert :**
- **FVG/OB + Kill Zones = les filtres qui comptent** : ils font passer de 1503 trades
  / DD −94 % à 75 trades / DD −24 %. Ils ne créent PAS d'edge, mais ils réduisent
  drastiquement le bruit et le drawdown → utiles en discrétionnaire.
- **OTE durcit trop** : il coupe les trades (173→75) sans améliorer l'espérance.
- **Discount** : neutre ici (le sweep+OTE le capturent déjà).
- Aucune combinaison ne franchit le zéro.

## Par année (frictionless) — dépendance de régime
2020 −0.33 · 2021 −0.36 · 2022 −0.40 · **2023 +0.44** · 2024 −0.41 · 2025 −0.29 ·
2026 +0.90 (n=5). Seuls 2023 et 2026-partiel sont positifs, sur de petits
échantillons → pas d'edge stable, juste du bruit de régime.

## Conclusion honnête
1. **À ne PAS trader en mécanique pure** — l'espérance est négative et instable.
2. **MAIS le script reste excellent en DISCRÉTIONNAIRE** : il dessine proprement
   structure (BOS/CHoCH), order blocks, FVG, sweeps, équilibre/OTE et kill zones,
   et envoie des alertes à gold_macro. C'est un outil de LECTURE, pas un automate.
3. Ce qui « marche » (réduit le risque) : la confluence FVG/OB + les kill zones.
   Ce qui est plus folklore mécaniquement : l'idée qu'empiler les notions ICT crée
   un edge directionnel — les chiffres disent non, sur XAU, sur 6  ans.
4. Piste honnête si tu veux un edge mesurable : c'est le **momentum/tendance** (TSMOM
   long, cf. xau-system) qui sort positif et robuste OOS, pas le SMC/ICT mécanique.
