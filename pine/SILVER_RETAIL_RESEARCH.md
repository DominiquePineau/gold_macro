# Piste #3 — Or/Argent + sentiment retail (recherche honnête)

Repro : `python scripts/research_gold_silver.py`. Or = xau-system D1, Argent = SI=F
(Yahoo, gratuit), 1623 jours alignés 2020-2026.

## 3a. Ratio Or/Argent — pas d'edge directionnel propre sur l'or
| Test | Résultat | Verdict |
|---|---|---|
| L'argent MÈNE l'or ? (lag corr) | même-jour 0.68, lag 1-3j ≈ 0 (−0.02/+0.01/+0.04) | ❌ l'argent NE mène PAS l'or (co-mouvement, pas de lead) |
| Ratio extrême → rendement forward or | ratio bas (or cheap/argent) → +3.0% (t=3.9) ; ratio haut → +0.7% | ⚠️ signal relative-value MAIS entaché par la tendance (tous buckets positifs) |
| Momentum du ratio → direction or | ratio↑ → or +1.35% / ratio↓ → +0.92% (20j) | ⚠️ faible, co-mouvement |

**Lecture :** Or et argent bougent ensemble le même jour (corr 0.68) mais l'argent
ne donne AUCUNE avance prédictive — le folklore « l'argent mène l'or » n'est pas
vérifié ici. Le ratio aux extrêmes a une légère valeur relative-value (or pas cher
vs argent → meilleur forward), mais entaché par la tendance haussière → pas un edge
directionnel propre sur l'or. Utile au mieux en CONTEXTE (ratio actuel 61.5 vs
moyenne 81.7 = or relativement cher en argent… historiquement bas en fait).

## 3b. Sentiment retail (IG) — non backtestable
- IG expose le **client sentiment** (% comptes longs/courts) en TEMPS RÉEL, mais
  **sans historique** → impossible à backtester. On ne peut pas valider l'edge
  contrarian sur le passé.
- Utilisable seulement comme **signal CONTEXTE live** : si le retail est extrême
  (ex. >80% long), drapeau contrarian. Mais ça tape l'API IG (compte live) → même
  risque WAF/conflit avec ton bot de trading qu'on a vu. À activer seulement si tu
  le veux explicitement, avec prudence.

## Verdict #3
- **Or/argent** : pas d'edge tradeable sur l'or ; l'argent ne mène pas l'or ;
  valeur contextuelle modeste (ratio extrême).
- **Retail IG** : pas backtestable ; possible en contexte live contrarian (option,
  avec caveat WAF). Non câblé par défaut.

→ Cohérent avec tout le reste : sur l'or, peu de signaux croisés tiennent la route.
Le contexte macro (gold_macro) + un Donchian pour le risque restent le plus solide.
