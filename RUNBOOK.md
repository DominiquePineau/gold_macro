# Runbook — Gold Macro Engine

Doc d'exploitation locale (ce projet perso tourne sur ce serveur — pas d'infra
DSC/Sewan). Architecture, lancement, interprétation des scores et alertes,
calibration, dépannage.

---

## 1. Ce que fait le système

Agrégateur macro XAU/USD : compile taux réels, DXY, COT et momentum prix en un
**biais directionnel** multi-timeframe + **alertes de retournement**. C'est un
**outil de CONTEXTE, pas un signal d'entrée** — il informe la décision, il ne
trade jamais.

Trois couches séparées (jamais fondues) :
- **Structurel** (HTF) : taux réels 10Y, DXY, COT → *où on est dans le cycle*
- **Tactique** (LTF) : momentum prix, DXY intraday, momentum rendement → *quand*
- **Sentiment** : positionnement (proxy F&G) + NLP Claude Haiku → *confirmation / extrêmes*

## 2. Architecture

```
RealProvider (FRED + COT CFTC + prix flux trade + proxy F&G + news RSS)
      │ MacroInputs
      ▼
GoldMacroOrchestrator → ScoringEngine (structurel/tactique) + SentimentEngine
      │ GoldSnapshot (+ alertes)            (Claude Haiku, plafonné par CostGuard)
      ├──► SQLiteSnapshotRepository (append-only : snapshots/alerts/components)
      └──► AlertDispatcher → sink (Telegram / webhook / log)
Scheduler (asyncio) orchestre le tout à cadence configurable.
API FastAPI : couche de lecture (/history, /alerts, /snapshot, /score).
```

## 3. Lancer

### En local (venv)
```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # puis renseigner FRED_API_KEY (requis), etc.
set -a; . ./.env; set +a

python demo.py                 # démo autonome (mock, aucune clé)
python demo_live.py            # démo sur données réelles (FRED requis)
python -m app.scheduler        # boucle live (Ctrl-C = arrêt propre)
uvicorn app.api.main:app       # API de lecture sur :8000
```

### En Docker (recommandé pour le live continu)
```bash
cp .env.example .env           # renseigner les clés
docker compose up -d           # scheduler (écrit) + api (lit), DB partagée
docker compose logs -f scheduler
docker compose down            # arrêt propre
```
Le scheduler est le moteur live ; l'API sert l'historique. Ils partagent le
volume `gold_data` (SQLite). La base du système `trade` est montée en lecture
seule pour le prix XAU.

### Dashboard web (cockpit)
Une fois l'API lancée : ouvre **http://localhost:8000/** — cockpit React (scores
en direct, courbe d'historique structurel/tactique, journal d'alertes, dernière
alerte TradingView). Rafraîchi toutes les 10 s.

### Intégration TradingView (entrée)
Tes alertes Pine peuvent alimenter le moteur. Crée une alerte TradingView avec :
- **Webhook URL** : `http://<ton-hote>:8000/tradingview/webhook`
- **Message (JSON)** :
  ```json
  {"secret":"<TRADINGVIEW_WEBHOOK_SECRET>","symbol":"XAUUSD","action":"BUY","price":{{close}},"strategy":"SMC","message":"sweep long"}
  ```
Le moteur ingère le signal (souple sur les clés) et l'affiche sur le dashboard.
Si `TRADINGVIEW_WEBHOOK_SECRET` est défini, le `secret` du JSON doit correspondre.
NB : Pine ne peut PAS lire de données externes → pas d'affichage du biais SUR le
graphique TradingView (sens sortie non faisable sans Pine Seeds).

## 4. Interpréter les scores

Composites sur **[-100, +100]** (somme pondérée des z-scores × direction) :

| Score | Sens |
|---|---|
| ≥ +50 | STRONG_BULL | ≤ -50 | STRONG_BEAR |
| +15..+50 | BULL | -50..-15 | BEAR |
| -15..+15 | NEUTRAL (pas d'edge net) |

**Aligné** = structurel et tactique pointent dans le même sens (>15 ou <-15).
**Edge mesuré** (backtest, cf. `results/CALIBRATION_REPORT.md`) : l'ALIGNEMENT a
un edge réel (~+5pp au-dessus du hasard, validé hors échantillon) ; les bascules
isolées (BIAS_FLIP) sont bruitées ; la DIVERGENCE prix/taux n'a pas d'edge net.

## 5. Réagir aux alertes

| Alerte | Sévérité | Quoi en faire |
|---|---|---|
| ALIGNMENT | CRITICAL | Conviction max (les 2 TF convergent) — le signal le plus fiable |
| BIAS_FLIP | CRITICAL/WARNING | Bascule directionnelle — confirmer avec ta lecture de prix |
| DIVERGENCE | WARNING | Épuisement possible — surveiller, ne pas trader seul |
| SENTIMENT_EXTREME / _DIVERGENCE | WARNING | Positionnement saturé — risque de retournement contrarian |
| EVENT_PROXIMITY | INFO | Event macro imminent — prudence sur les nouvelles positions |

Politique de distribution : CRITICAL → push immédiat (dédoublonné) ; WARNING →
digest groupé ; INFO → log seulement.

## 6. Garde-fou de coût Claude

Le NLP (Claude Haiku) est plafonné : **rapport tous les `COST_REPORT_EVERY_EUR`
(défaut 1 €)**, **STOP dur à `COST_HARD_STOP_EUR` (défaut 10 €)** → repli lexique
automatique. Coût mesuré ≈ 0,0015 €/appel. Les rapports arrivent sur le canal
d'alerte. Sans `ANTHROPIC_API_KEY`, le système marche en repli lexique (gratuit).

## 7. Calibration des poids

Poids dans `app/core/config.py`, calibrés et **validés out-of-sample** (cf.
`results/CALIBRATION_REPORT.md`). Pour recalibrer :
```bash
python scripts/build_backtest_data.py     # (ré)assemble les données historiques
python scripts/run_backtest_report.py     # backtest + calibration + rapport
```

## 8. Dépannage

| Symptôme | Cause probable / action |
|---|---|
| Démarrage refusé « FRED_API_KEY manquante » | renseigner `.env` (validation fail-fast) |
| `xau_price` à None | base `trade` non montée / streamer arrêté → prix dégradé (cycle OK) |
| Sentiment textuel = lexique | pas de clé Claude, ou plafond 10 € atteint |
| Pas d'alertes reçues | destination non configurée (`alertes→log`) → poser TELEGRAM_* ou ALERT_WEBHOOK_URL |
| Composites ~0 au démarrage | normal : z-scores sans historique (warm-up de quelques cycles) |

## 9. Sécurité

- Clés en variables d'environnement uniquement ; `.env` gitignoré (jamais committé).
- Aucune exécution d'ordre de trading : le système informe, il ne trade pas.
- Sinks d'alerte en mode dégradé (une panne réseau ne casse jamais un cycle).
