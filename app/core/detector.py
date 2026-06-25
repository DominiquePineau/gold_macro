"""Détection de changements de direction et de divergences.

Trois familles d'alertes :
  1. BIAS_FLIP    : un score composite croise zéro → bascule directionnelle
  2. ALIGNMENT    : les deux timeframes s'alignent → conviction maximale
  3. DIVERGENCE   : prix vs macro incohérents → épuisement potentiel
  + EVENT_PROXIMITY : événement macro imminent → prudence
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from app.core.models import Alert, GoldSnapshot, TimeframeScore
from app.core.stats import RollingWindow, diverging, sign_changed, slope


class RegimeDetector:
    """Maintient l'historique des scores et émet des alertes sur transitions."""

    def __init__(self, history_len: int = 50):
        self.structural_hist = RollingWindow(maxlen=history_len)
        self.tactical_hist = RollingWindow(maxlen=history_len)
        self.xau_hist = RollingWindow(maxlen=history_len)
        self.real_rates_hist = RollingWindow(maxlen=history_len)
        self.sentiment_hist = RollingWindow(maxlen=history_len)
        self._prev_aligned: bool = False

    def evaluate(
        self,
        structural: TimeframeScore,
        tactical: TimeframeScore,
        xau_price: Optional[float] = None,
        real_rates_value: Optional[float] = None,
        next_event_hours: Optional[float] = None,
        sentiment_score: Optional[float] = None,
        sentiment_contrarian: bool = False,
        event_proximity_threshold: float = 4.0,
    ) -> list[Alert]:
        alerts: list[Alert] = []

        prev_struct = self.structural_hist.last
        prev_tac = self.tactical_hist.last

        # --- 1. BIAS FLIP (croisement de zéro) ---
        if prev_struct is not None and sign_changed(prev_struct, structural.composite):
            direction = "HAUSSIER" if structural.composite > 0 else "BAISSIER"
            alerts.append(Alert(
                kind="BIAS_FLIP",
                severity="CRITICAL",
                message=(
                    f"Bascule STRUCTURELLE → {direction} "
                    f"({prev_struct:+.0f} → {structural.composite:+.0f}). "
                    f"Driver: {self._driver_name(structural)}."
                ),
            ))

        if prev_tac is not None and sign_changed(prev_tac, tactical.composite):
            direction = "HAUSSIER" if tactical.composite > 0 else "BAISSIER"
            alerts.append(Alert(
                kind="BIAS_FLIP",
                severity="WARNING",
                message=(
                    f"Bascule TACTIQUE → {direction} "
                    f"({prev_tac:+.0f} → {tactical.composite:+.0f})."
                ),
            ))

        # --- 2. ALIGNMENT (les deux pointent pareil) ---
        s, t = structural.composite, tactical.composite
        aligned = (s > 15 and t > 15) or (s < -15 and t < -15)
        if aligned and not self._prev_aligned:
            direction = "HAUSSIER" if s > 0 else "BAISSIER"
            alerts.append(Alert(
                kind="ALIGNMENT",
                severity="CRITICAL",
                message=(
                    f"ALIGNEMENT {direction} : structurel ({s:+.0f}) "
                    f"et tactique ({t:+.0f}) convergent. Conviction maximale."
                ),
            ))
        self._prev_aligned = aligned

        # --- 3. DIVERGENCE prix vs taux réels ---
        if xau_price is not None:
            self.xau_hist.push(xau_price)
        if real_rates_value is not None:
            self.real_rates_hist.push(real_rates_value)

        if len(self.xau_hist) >= 5 and len(self.real_rates_hist) >= 5:
            xau_slope = slope(self.xau_hist.values(), lookback=10)
            rates_slope = slope(self.real_rates_hist.values(), lookback=10)
            # Normalement : prix et taux réels divergent (corrélation négative).
            # L'ANOMALIE = ils montent ensemble (ou baissent ensemble).
            if not diverging(xau_slope, rates_slope) and abs(xau_slope) > 0.1:
                alerts.append(Alert(
                    kind="DIVERGENCE",
                    severity="WARNING",
                    message=(
                        "DIVERGENCE prix/taux réels : le prix et les taux réels "
                        "bougent dans le même sens (anormal). Épuisement possible "
                        "de la tendance — surveiller un retournement."
                    ),
                ))

        # --- 3b. DIVERGENCE sentiment vs prix (épuisement) ---
        if sentiment_score is not None:
            self.sentiment_hist.push(sentiment_score)
            if len(self.sentiment_hist) >= 5 and len(self.xau_hist) >= 5:
                sent_slope = slope(self.sentiment_hist.values(), lookback=8)
                xau_slope = slope(self.xau_hist.values(), lookback=8)
                # Sentiment euphorique (greed) qui grimpe MAIS prix qui cale/baisse
                # → épuisement haussier. Et inversement.
                if abs(sentiment_score) >= 50 and diverging(sent_slope, xau_slope):
                    mood = "euphorique (greed)" if sentiment_score > 0 else "paniqué (fear)"
                    alerts.append(Alert(
                        kind="SENTIMENT_DIVERGENCE",
                        severity="WARNING",
                        message=(
                            f"DIVERGENCE sentiment/prix : sentiment {mood} "
                            f"({sentiment_score:+.0f}) mais le prix ne suit pas. "
                            f"Signal contrarian d'épuisement."
                        ),
                    ))
            # Extrême de positionnement = alerte contrarian directe
            if sentiment_contrarian and abs(sentiment_score) >= 40:
                side = "SURACHAT (foule longue)" if sentiment_score < 0 else "SURVENTE (foule courte)"
                alerts.append(Alert(
                    kind="SENTIMENT_EXTREME",
                    severity="WARNING",
                    message=(
                        f"Positionnement EXTRÊME → {side}. "
                        f"Score contrarian {sentiment_score:+.0f}. "
                        f"Risque de retournement à contre-courant de la foule."
                    ),
                ))

        # --- 4. EVENT PROXIMITY ---
        if next_event_hours is not None and 0 <= next_event_hours <= event_proximity_threshold:
            alerts.append(Alert(
                kind="EVENT_PROXIMITY",
                severity="INFO",
                message=(
                    f"Événement macro majeur dans {next_event_hours:.1f}h. "
                    f"Volatilité attendue — prudence sur les nouvelles positions."
                ),
            ))

        # archivage
        self.structural_hist.push(structural.composite)
        self.tactical_hist.push(tactical.composite)

        return alerts

    @staticmethod
    def _driver_name(score: TimeframeScore) -> str:
        top = score.top_driver()
        return top.name if top else "n/a"
