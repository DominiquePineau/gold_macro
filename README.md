# Gold Macro Engine

Agrégateur macro pour XAU/USD : compile taux réels, DXY, rendements, COT et
momentum prix en un **biais directionnel** multi-timeframe, avec **alertes de
retournement**.

## Principe

Trois couches séparées :

| Score | Horizon | Facteurs | Rôle |
|-------|---------|----------|------|
| **Structurel** | HTF (daily/hebdo) | Taux réels 10Y, DXY daily, COT | Où on est dans le cycle |
| **Tactique** | LTF (intraday) | Momentum prix, DXY intraday, momentum rendement | Quand agir |
| **Sentiment** | mixte | Positionnement (contrarian) + NLP textuel | Confirmation / extrêmes |

Chaque facteur est normalisé en **z-score**, pondéré, et orienté (+1/-1 selon
sa corrélation avec l'or). Le composite est rescalé sur **[-100, +100]**.

## Couche sentiment

Combine deux sous-scores (poids 65/35) :

- **Positionnement (contrarian)** : retail long %, put/call GLD, fear & greed.
  Logique à contre-courant **aux extrêmes uniquement** : foule saturée longue
  → signal baissier. Zone neutre = pas d'edge (score proche de 0).
- **Textuel (NLP)** : chaque headline notée par **Claude Haiku** pour son impact
  *sur l'or* (comprend le contexte inversé : "hausse des taux" = baissier).
  Repli sur lexique financier si pas de clé API. Agrégé par pertinence + fraîcheur.

Le textuel ne pilote jamais seul : il sert de **confirmation** et surtout de
**détection de divergence sentiment/prix** (sentiment euphorique + prix qui
cale = épuisement). Configurable dans `app/sentiment/engine.py`.

Clé requise pour le NLP : `export ANTHROPIC_API_KEY=...`

## Alertes

- **BIAS_FLIP** : un score croise zéro → bascule directionnelle
- **ALIGNMENT** : les deux timeframes convergent → conviction maximale
- **DIVERGENCE** : prix et taux réels bougent dans le même sens (anormal) → épuisement
- **SENTIMENT_DIVERGENCE** : sentiment extrême + prix qui ne suit pas → épuisement contrarian
- **SENTIMENT_EXTREME** : positionnement de la foule saturé → risque de retournement
- **EVENT_PROXIMITY** : événement macro imminent → prudence

## Anti-pièges intégrés

- **Z-scores clippés** à ±3 : un outlier ne domine pas le composite
- **COT extrême inversé** : au-delà de z=±2, un positionnement saturé inverse
  son signal (risque de squeeze) au lieu de le renforcer

## Lancer

```bash
pip install -r requirements.txt

# Démo autonome (provider mock, aucune clé requise)
python demo.py

# API
uvicorn app.api.main:app --reload
```

Endpoints : `GET /health`, `POST /evaluate`, `GET /snapshot`, `GET /score`.

## Données réelles (Phase 2 — implémenté)

`RealProvider` (`app/sources/real.py`) compose les sources live en un `MacroInputs` :

```python
from app.sources.real import RealProvider
from app.sources.price import TradeDBPriceFeed
from app.sources.positioning import ProxyPositioningFeed
from app.sources.news import NewsProvider

provider = RealProvider(
    price_feed=TradeDBPriceFeed(),          # prix XAU via le flux du système trade
    positioning_feed=ProxyPositioningFeed(),  # proxy Fear&Greed (dérivé du prix)
    news_feed=NewsProvider(),               # RSS gratuit (Google News + ForexLive)
)
```

| Source | Connecteur | Détail |
|--------|-----------|--------|
| Taux réels / nominal / dollar | `FredProvider` (FRED) | `FRED_API_KEY` ; retries + cache + mode dégradé |
| COT net specs | `CotProvider` (CFTC) | gratuit, cache hebdo, mode dégradé |
| Prix XAU | `TradeDBPriceFeed` | flux du système `trade` (candle_data), **aucune session broker** |
| Sentiment | `ProxyPositioningFeed` | proxy Fear&Greed maison (momentum/vol) |
| News (NLP) | `NewsProvider` | RSS gratuit → Claude Haiku si `ANTHROPIC_API_KEY`, sinon lexique |

Chaque source a un **mode dégradé** (renvoie `None`/vide sans casser le cycle) et
des **tests** (fixtures). Le `MockProvider` reste fonctionnel (démo + tests).

Démo live : `python demo_live.py` (nécessite `FRED_API_KEY`).
Alerte : `IGPriceFeed` existe aussi mais crée une session IG (risque de conflit
avec un bot de trading) — préférer `TradeDBPriceFeed`.

## Calibration

Les poids dans `app/core/config.py` sont le point d'ajustement principal.
À optimiser par backtest sur ton historique : mesurer le hit-rate des
ALIGNMENT et DIVERGENCE contre les retournements réels, et ajuster.

## Structure

```
app/
  core/
    models.py        # types : Bias, SignalComponent, Snapshot, Alert
    stats.py         # zscore, slope, divergence, rolling window
    config.py        # poids et directions des facteurs  ← calibration
    engine.py        # moteur de scoring
    detector.py      # détection bascules / divergences
    orchestrator.py  # pipeline complet
  sources/
    base.py          # interface DataProvider
    mock.py          # provider de démo
    fred.py          # connecteur FRED réel
  api/
    main.py          # FastAPI
demo.py
```
