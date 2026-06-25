"""Configuration du scoring : poids, directions, seuils.

Ces poids sont le point de calibration principal.

CALIBRATION 2026-06-25 (Phase 5, cf. results/CALIBRATION_REPORT.md) :
Poids structurels validés OUT-OF-SAMPLE (train 2020-2023 / test 2024-2026) :
real_rates 0.50 / dxy 0.30 / cot 0.20 — edge ALIGNMENT stable ~+5.5pp en test
(vs base rate). Choix ROBUSTE (pas le meilleur sur train, qui surapprenait :
7.3pp train → 2.0pp test). Le gain sur le défaut antérieur (0.40/0.30/0.30) est
marginal — les poids d'origine étaient déjà sains. Tactiques inchangés (déjà OK).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FactorConfig:
    name: str
    weight: float
    direction: int  # +1 si corrélé positivement à l'or, -1 si inversé
    timeframe: str  # "structural" ou "tactical"
    note: str = ""


# --- Facteurs STRUCTURELS (biais de fond, lents) ---
STRUCTURAL_FACTORS = [
    FactorConfig(
        name="real_rates_10y",
        weight=0.50,  # calibré 2026-06-25 (0.40 -> 0.50, validé OOS)
        direction=-1,  # taux réels montent → or baisse
        timeframe="structural",
        note="TIPS 10Y (FRED DFII10). Le moteur dominant.",
    ),
    FactorConfig(
        name="dxy_daily",
        weight=0.30,
        direction=-1,  # dollar fort → or baisse
        timeframe="structural",
        note="Dollar index, tendance daily.",
    ),
    FactorConfig(
        name="cot_net_specs",
        weight=0.20,  # calibré 2026-06-25 (0.30 -> 0.20, validé OOS)
        direction=+1,  # specs nets longs → soutien haussier (avec nuance d'extrêmes)
        timeframe="structural",
        note="Positionnement net spéculatif CFTC (hebdo).",
    ),
]

# --- Facteurs TACTIQUES (timing, rapides) ---
TACTICAL_FACTORS = [
    FactorConfig(
        name="price_momentum",
        weight=0.45,
        direction=+1,
        timeframe="tactical",
        note="Pente du prix XAU sur fenêtre courte.",
    ),
    FactorConfig(
        name="dxy_intraday",
        weight=0.35,
        direction=-1,
        timeframe="tactical",
        note="Mouvement DXY court terme.",
    ),
    FactorConfig(
        name="yield_momentum_10y",
        weight=0.20,
        direction=-1,
        timeframe="tactical",
        note="Momentum du rendement nominal US10Y.",
    ),
]

# Seuils de classification du biais
BIAS_THRESHOLDS = {
    "strong": 50.0,
    "moderate": 15.0,
}

# Seuil de proximité événement macro (en heures) qui déclenche une alerte
EVENT_PROXIMITY_HOURS = 4.0

# Pénalité d'extrême COT : au-delà de ce z-score, on inverse partiellement
# le signal (positionnement saturé = risque de retournement)
COT_EXTREME_ZSCORE = 2.0
