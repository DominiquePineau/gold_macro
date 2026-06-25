# Plan d'implémentation — Gold Macro Engine

> Document de passation pour Claude Code. Objectif : amener le prototype
> `gold_macro` à un état production-ready, branché sur données réelles,
> testé, calibré et déployable sur l'infra DSC.

---

## 0. Contexte et philosophie du projet

### Ce que fait le système
Agrégateur macro multi-couches pour **XAU/USD** qui produit un **biais
directionnel** et des **alertes de retournement**. Trois couches de scoring
séparées, jamais fondues entre elles :

1. **Structurel** (HTF, daily/hebdo) : taux réels 10Y, DXY daily, COT → *où on est dans le cycle*
2. **Tactique** (LTF, intraday) : momentum prix, DXY intraday, momentum rendement → *quand agir*
3. **Sentiment** (mixte) : positionnement contrarian + NLP textuel → *confirmation / détection d'extrêmes*

### Principes de conception NON NÉGOCIABLES
Respecter ces invariants tout au long de l'implémentation :

- **Z-scores partout.** Aucune donnée brute n'entre dans un composite sans
  normalisation. C'est ce qui rend comparables des échelles hétérogènes.
- **Couches séparées.** Le sentiment ne contamine jamais le score macro. Il
  confirme ou alerte. Garder cette frontière.
- **Contrarian aux extrêmes uniquement.** Le positionnement de la foule n'a
  d'edge qu'aux extrêmes (z ≥ 1.5). En zone neutre → score proche de 0.
- **Le textuel ne pilote jamais seul.** Il est en retard sur le prix. Sa valeur
  est la divergence sentiment/prix, pas le niveau absolu.
- **Transparence.** Chaque score doit rester décomposable par facteur. Jamais
  de chiffre opaque. L'utilisateur (trader SMC/ICT) croise avec sa lecture de prix.
- **Outil de contexte, PAS signal d'entrée.** Le système informe la décision,
  il ne déclenche pas de trade automatiquement. Ne jamais ajouter d'exécution
  d'ordre sans demande explicite.

### Stack cible (cohérence avec l'infra existante)
- Python 3.12, FastAPI, async/await, httpx
- Pas de pandas dans le cœur (stats maison dans `app/core/stats.py`) — garder léger
- Déploiement Docker/Traefik, registre Verdaccio si packages JS
- DEV : `192.168.150.48` — PROD : `192.168.150.52` (NE JAMAIS toucher sans autorisation explicite, cf. PREF-008)

---

## 1. État actuel du code (point de départ)

### Arborescence livrée
```
gold_macro/
├── app/
│   ├── core/
│   │   ├── models.py        # Bias, SignalComponent, TimeframeScore, Alert, GoldSnapshot
│   │   ├── stats.py         # zscore, slope, pct_change, diverging, RollingWindow
│   │   ├── config.py        # FactorConfig : poids/directions — POINT DE CALIBRATION
│   │   ├── engine.py        # ScoringEngine : score_structural / score_tactical
│   │   ├── detector.py      # RegimeDetector : BIAS_FLIP, ALIGNMENT, DIVERGENCE, SENTIMENT_*
│   │   └── orchestrator.py  # GoldMacroOrchestrator : pipeline complet async
│   ├── sentiment/
│   │   ├── models.py        # NewsItem, PositioningInputs, SentimentScore, SentimentLabel
│   │   ├── positioning.py   # PositioningAnalyzer : contrarian aux extrêmes
│   │   ├── textual.py       # TextualAnalyzer : Claude Haiku + repli lexique
│   │   └── engine.py        # SentimentEngine : fusion 65/35
│   ├── sources/
│   │   ├── base.py          # DataProvider (ABC), MacroInputs (dataclass)
│   │   ├── mock.py          # MockProvider : trajectoire scénarisée déterministe
│   │   └── fred.py          # FredProvider : connecteur FRED (PARTIEL, à finir)
│   └── api/
│       └── main.py          # FastAPI : /health /evaluate /snapshot /score
├── demo.py                  # Démo CLI multi-cycles (fonctionne)
├── requirements.txt
└── README.md
```

### Ce qui fonctionne déjà
- Le pipeline complet tourne en mode mock (`python demo.py` passe)
- L'API REST répond sur les 4 endpoints
- Les trois couches de scoring sont opérationnelles
- Le sentiment textuel a un repli lexique fonctionnel sans clé API

### Dette technique connue (à corriger — voir Phase 1)
1. **`FredProvider.fetch()` viole l'interface `DataProvider.fetch()`** : il prend
   des arguments (`xau_price`, `cot_net_specs`, `next_event_hours`) alors que
   l'ABC impose `fetch(self) -> MacroInputs` sans argument. À refactorer.
2. **Aucun test automatisé.** Zéro fichier dans un dossier `tests/`.
3. **Pas de persistance.** Les snapshots ne sont pas stockés (event sourcing absent).
4. **Pas de scheduler.** Le système n'évalue que sur appel manuel de `/evaluate`.
5. **Sources réelles non branchées** : COT, prix XAU live, positionnement retail,
   put/call, fear & greed, flux news.
6. **Poids non calibrés** : les valeurs dans `config.py` sont des défauts
   raisonnables mais non validés.

---

## 2. Phases d'implémentation (séquencées)

> Exécuter dans l'ordre. Chaque phase a des critères de validation (DoD).
> Commit atomique par phase, message en français, préfixe conventionnel.

---

### PHASE 1 — Fondations : tests, contrats, CI

**Objectif** : verrouiller le comportement actuel avant d'ajouter quoi que ce soit.

#### 1.1 Mettre en place pytest + structure de tests
- Créer `tests/` avec `__init__.py`, `conftest.py`
- Ajouter `pytest`, `pytest-asyncio`, `pytest-cov` à un `requirements-dev.txt`
- Configurer `pyproject.toml` (ou `pytest.ini`) avec `asyncio_mode = "auto"`

#### 1.2 Tests unitaires du cœur statistique (`app/core/stats.py`)
Couvrir, avec valeurs connues calculées à la main :
- `zscore` : distribution vide → 0 ; un seul point → 0 ; clipping à ±3
- `slope` : série plate → 0 ; série croissante → positif ; normalisation
- `diverging` : signes opposés au-delà du seuil → True ; faible amplitude → False
- `sign_changed` : croisement de zéro et de seuils custom
- `RollingWindow` : maxlen respecté, rejet des NaN/None

#### 1.3 Tests du moteur de scoring (`app/core/engine.py`)
- Vérifier que `score_structural` / `score_tactical` restent dans [-100, 100]
- Vérifier la décomposition : somme des contributions cohérente avec le composite
- Vérifier l'inversion COT extrême (z ≥ 2.0 → `direction` inversé, note "EXTRÊME")
- Vérifier qu'un facteur absent du dict d'entrée est simplement ignoré

#### 1.4 Tests du détecteur (`app/core/detector.py`)
- BIAS_FLIP émis sur croisement de zéro structurel/tactique
- ALIGNMENT émis une seule fois à la bascule (pas à chaque cycle aligné)
- DIVERGENCE prix/taux réels sur même direction des pentes
- SENTIMENT_EXTREME et SENTIMENT_DIVERGENCE sur les bons seuils
- EVENT_PROXIMITY dans la fenêtre, pas en dehors

#### 1.5 Tests sentiment (`app/sentiment/`)
- `PositioningAnalyzer` : zone neutre → score faible ; extrême → contrarian fort
- `TextualAnalyzer.aggregate` : pondération fraîcheur (item ancien pèse moins)
- `TextualAnalyzer._analyze_lexicon` : headline haussière → polarity > 0
- Mock de l'appel Claude API (httpx) pour tester `_analyze_claude` sans réseau

#### 1.6 Corriger le contrat `FredProvider`
- Refactorer pour que `fetch(self) -> MacroInputs` respecte l'ABC
- Les dépendances externes (prix XAU, COT, event) doivent être injectées au
  `__init__` via des callables/providers, pas passées à `fetch()`
- Pattern suggéré : `FredProvider(price_feed=..., cot_feed=..., calendar=...)`

**DoD Phase 1** :
- `pytest --cov=app` passe à 100 %, couverture ≥ 85 % sur `app/core`
- `FredProvider` est substituable à `MockProvider` sans changer l'orchestrateur
- Un workflow GitHub Actions (ou GitLab CI selon le repo) lance les tests

---

### PHASE 2 — Sources de données réelles

> Une source à la fois. Chacune testée en isolation avant intégration.
> Discipline "une variable à la fois" (PREF).

#### 2.1 Connecteur COT (CFTC)
- Source : rapport CFTC "Disaggregated Futures-and-Options Combined", or = code `088691`
- Endpoint public CFTC ou fichier historique téléchargeable hebdo
- Extraire le **net positioning** des Managed Money (specs) : `long - short`
- Créer `app/sources/cot.py` avec une classe `CotProvider` ou une fonction-feed
- Gérer la fréquence hebdo : le COT ne change qu'une fois/semaine (publié vendredi,
  données du mardi). Mettre en cache, ne pas re-télécharger à chaque cycle.
- **Test** : parser un échantillon de fichier CFTC fixturé, vérifier l'extraction

#### 2.2 Flux prix XAU live
- Source primaire : OANDA (déjà dans le pipeline trading de l'utilisateur) ou IG
- Récupérer le dernier prix + historique court pour le momentum
- Créer `app/sources/price.py` avec interface `PriceFeed`
- Réutiliser le webhook FastAPI existant si le prix arrive déjà par là
- **Attention** : ne PAS dupliquer la connexion broker si elle existe déjà côté
  algo-trading. Vérifier le repo `algo-trading` et brancher dessus si possible.

#### 2.3 Finaliser FredProvider
- Compléter avec gestion d'erreur réseau (retry, timeout, cache si FRED down)
- Vérifier les séries : `DFII10` (taux réel 10Y), `DGS10` (nominal 10Y),
  `DTWEXBGS` (dollar index large)
- FRED publie en différé (J+1) : ne pas s'attendre à de l'intraday sur les taux

#### 2.4 Sources de sentiment de positionnement
- **Retail L/S** : OANDA expose un order book / position ratio ; IG a un
  "client sentiment". Récupérer le % de comptes longs sur l'or.
- **Put/Call GLD** : CBOE ou une API d'options (à identifier ; possiblement payant —
  documenter l'option choisie et le coût)
- **Fear & Greed** : pas d'indice or-spécifique standard ; utiliser un proxy
  (CNN Fear & Greed général, ou construire un mini-indice maison à partir de
  volatilité GLD + momentum). Documenter le choix.
- Créer `app/sources/positioning.py`

#### 2.5 Flux news pour le NLP
- Source : RSS financier (Reuters, Bloomberg via flux dispo, ForexLive, FXStreet)
  ou une API news (NewsAPI, Marketaux). Privilégier les titres récents (<48h).
- Filtrer sur pertinence or/macro avant d'envoyer à Claude (économie de tokens)
- Créer `app/sources/news.py` produisant des `NewsItem`
- **Brancher Claude Haiku réel** : vérifier que `ANTHROPIC_API_KEY` est lu,
  tester un vrai appel, valider le parsing JSON de la réponse

**DoD Phase 2** :
- Un `RealProvider` (ou composition de feeds) remplace `MockProvider` et produit
  un `MacroInputs` complet à partir de données live
- `demo.py` (ou une variante `demo_live.py`) tourne sur données réelles
- Chaque source a un test avec fixture + un mode dégradé si la source est down
- Le mock reste fonctionnel (ne pas le casser — il sert aux tests et à la démo)

---

### PHASE 3 — Persistance et event sourcing

> Cohérent avec le pattern event-sourcing SQLite déjà utilisé sur le DSC Portal.

#### 3.1 Schéma de stockage
- SQLite (cohérence avec l'existant) ou MySQL si intégration DSC Portal
- Table `snapshots` : timestamp, structural_composite, tactical_composite,
  sentiment_composite, xau_price, aligned (append-only)
- Table `alerts` : timestamp, kind, severity, message, snapshot_id (FK)
- Table `components` : snapshot_id, name, zscore, weight, contribution (pour audit)

#### 3.2 Couche de persistance
- Créer `app/storage/` avec un repository pattern (interface + impl SQLite)
- L'orchestrateur persiste chaque snapshot après évaluation
- Append-only, jamais d'UPDATE/DELETE sur l'historique (event sourcing)

#### 3.3 Endpoints d'historique
- `GET /history?since=...&until=...` : série temporelle des composites
- `GET /alerts?kind=...&severity=...` : journal des alertes filtrables

**DoD Phase 3** :
- Chaque cycle persiste un snapshot + ses alertes
- L'historique est requêtable via l'API
- Test d'intégration : N cycles → N snapshots en base, cohérents

---

### PHASE 4 — Scheduler et alerting

#### 4.1 Boucle d'évaluation périodique
- Scheduler async (APScheduler ou boucle asyncio maison)
- Cadence différenciée : structurel (horaire suffit), tactique (1-5 min),
  sentiment news (15-30 min pour limiter coût tokens)
- Découpler les fréquences : ne pas tout recalculer à chaque tick
- Configurable par variables d'environnement

#### 4.2 Webhook d'alertes (finaliser)
- Le squelette existe dans `app/api/main.py` (`_push_webhook`)
- Brancher la vraie destination : Telegram bot, Discord webhook, ou pipeline DSC
- Throttling : ne pas spammer si une alerte se répète (dédup sur kind+direction
  dans une fenêtre glissante)
- Niveaux : CRITICAL → push immédiat ; WARNING → digest ; INFO → log seulement

#### 4.3 Intégration TradingView (optionnel, si demandé)
- Le système peut consommer les alertes Pine de l'utilisateur en entrée
- OU exposer ses propres signaux que Pine peut afficher
- À clarifier avec l'utilisateur avant d'implémenter — NE PAS présumer

**DoD Phase 4** :
- Le système tourne en continu et évalue automatiquement
- Les alertes CRITICAL arrivent sur le canal configuré, sans doublon
- Arrêt/redémarrage propre (graceful shutdown)

---

### PHASE 5 — Backtest et calibration des poids

> LA phase qui transforme l'outil de "plausible" à "validé". Voir aussi le
> skill `systematic-debug` : mapper d'abord, changer une variable, mesurer.

#### 5.1 Harnais de backtest
- Créer `app/backtest/` : rejoue des données historiques à travers le pipeline
- Charger l'historique : prix XAU, TIPS, DXY, COT sur ≥ 2 ans (idéalement 5+)
- Rejouer cycle par cycle, collecter scores + alertes horodatés
- Pas de look-ahead bias : à chaque instant T, n'utiliser que les données ≤ T
  (les z-scores se calculent sur l'historique glissant, déjà le cas — vérifier)

#### 5.2 Métriques d'évaluation
- **Hit-rate des ALIGNMENT** : après une alerte d'alignement, le prix va-t-il
  dans la direction prédite sur N barres ? (mesurer pour N = 5, 10, 20)
- **Hit-rate des DIVERGENCE/SENTIMENT_DIVERGENCE** : un retournement suit-il ?
- **Lead/lag** : le BIAS_FLIP précède-t-il ou suit-il le mouvement de prix ?
- **Faux positifs** : taux d'alertes non suivies d'effet

#### 5.3 Optimisation des poids
- Les poids dans `config.py` (STRUCTURAL_FACTORS, TACTICAL_FACTORS, W_POSITIONING,
  W_TEXTUAL) sont les variables à optimiser
- Méthode : grid search ou optimisation bayésienne sur le hit-rate composite
- **GARDE-FOU anti-overfit** : split train/test temporel (ex : optimiser sur
  2020-2023, valider sur 2024-2025). Un poids qui ne tient que sur le train
  est rejeté. Documenter l'écart de performance train vs test.
- Ne PAS sur-optimiser : préférer des poids robustes à des poids parfaits sur
  l'historique. Le marché change de régime.

#### 5.4 Rapport de calibration
- Générer un rapport (markdown + graphes matplotlib) : poids retenus, hit-rates,
  courbe de performance, sensibilité aux paramètres
- Conclusion honnête : sur quels signaux le système a un edge mesurable, sur
  lesquels il n'en a pas. Ne pas survendre.

**DoD Phase 5** :
- Backtest reproductible sur ≥ 2 ans de données
- Poids calibrés avec validation out-of-sample documentée
- Rapport clair sur ce qui marche et ce qui ne marche pas
- `config.py` mis à jour avec les poids validés + commentaire sur la source

---

### PHASE 6 — Packaging, déploiement, doc

#### 6.1 Dockerisation
- `Dockerfile` multi-stage, image légère (python:3.12-slim)
- `docker-compose.yml` : service API + volume SQLite + variables d'env
- Intégration Traefik (labels) cohérente avec le stack DSC existant

#### 6.2 Configuration
- Toutes les clés/URLs en variables d'environnement, jamais en dur
- `.env.example` documenté (FRED_API_KEY, ANTHROPIC_API_KEY, ALERT_WEBHOOK_URL,
  OANDA creds, etc.)
- Validation au démarrage : échouer vite si une clé requise manque

#### 6.3 Documentation Confluence
- Utiliser le skill `confluence-doc` pour publier : architecture, runbook,
  guide de calibration, interprétation des scores et alertes
- Page d'exploitation : comment lire un snapshot, que faire sur chaque alerte

#### 6.4 Dashboard (préparer le terrain, livrable séparé)
- L'API expose déjà tout le nécessaire (/snapshot, /history, /alerts)
- Noter pour plus tard : front React + Sophia/UI-Kit (skills `sewan-ui-components`,
  `react-patterns`, `sophia-theme`). NE PAS implémenter ici sauf demande —
  c'était identifié comme livrable distinct.

**DoD Phase 6** :
- `docker compose up` lance le système complet
- Doc Confluence publiée
- `.env.example` complet, démarrage qui valide la config

---

## 3. Conventions et garde-fous transverses

### Style de code
- Type hints partout, dataclasses pour les structures, async pour l'I/O
- Docstrings en français (cohérence avec l'existant)
- Pas de pandas dans le cœur ; stats maison déjà en place
- Garder chaque module sous ~150 lignes ; découper si ça grossit

### Git
- Un commit par sous-tâche cohérente, message en français
- Préfixes : `feat:`, `test:`, `fix:`, `refactor:`, `docs:`, `chore:`
- Ne pas committer de clés API, de `.env`, de données téléchargées volumineuses

### Sécurité / prudence
- **Aucune exécution d'ordre de trading.** Ce système informe, il ne trade pas.
- Ne JAMAIS toucher PROD `192.168.150.52` sans autorisation explicite (PREF-008)
- Les clés API en env uniquement
- Si une source de données est payante, s'arrêter et demander avant de souscrire

### Quand demander à l'utilisateur (ne pas présumer)
- Choix d'une source de données payante (put/call, news API)
- Intégration TradingView (entrée ou sortie ?)
- Destination des alertes (Telegram ? Discord ? autre ?)
- Toute décision qui engage un coût ou touche l'infra de prod

### Rappels honnêteté intellectuelle
- Le système est un **outil d'aide à la décision**, pas un générateur de signaux
  d'entrée. Le garder ainsi dans le code, la doc, les messages d'alerte.
- Ne pas survendre les performances de backtest. Documenter les limites.
- Le sentiment textuel est en retard sur le prix : sa valeur est la divergence.

---

## 4. Ordre d'attaque recommandé

Si le temps est limité, prioriser dans cet ordre de valeur :

1. **Phase 1** (tests + fix contrat) — indispensable, débloque tout le reste
2. **Phase 5** (backtest) — c'est ce qui dit si l'outil vaut quelque chose ;
   peut se faire sur données historiques téléchargées sans brancher les feeds live
3. **Phase 2** (sources réelles) — pour l'usage live
4. **Phases 3, 4** (persistance, scheduler) — pour l'autonomie
5. **Phase 6** (déploiement) — pour la mise en service

> Note : Phase 5 avant Phase 2 est volontaire. Inutile de brancher des flux live
> coûteux si le backtest révèle que les poids n'ont pas d'edge. Valider la
> thèse d'abord, industrialiser ensuite.

---

## 5. Première action concrète pour Claude Code

```
1. Lire ce plan en entier.
2. Lire le README.md et parcourir toute l'arborescence app/.
3. Lancer `python demo.py` pour voir le système en action.
4. Confirmer la compréhension de l'architecture et signaler toute ambiguïté.
5. Démarrer Phase 1.1 : mise en place de pytest.
```

Ne pas tout faire d'un coup. Avancer phase par phase, valider chaque DoD,
committer, puis enchaîner.
