"""Sentiment de positionnement (quantitatif, contrarian).

Logique : le positionnement de la foule est un signal à contre-courant
AUX EXTRÊMES. Retail massivement long → signal baissier. Put/call élevé
(peur) → signal haussier contrarian.

Aux niveaux modérés, le positionnement n'est pas exploitable : on retourne
un score proche de zéro pour éviter le sur-signal.
"""
from __future__ import annotations

from app.core.stats import RollingWindow, zscore
from app.sentiment.models import PositioningInputs

# Au-delà de ce z-score, on considère le positionnement comme "extrême"
# et le signal contrarian s'active pleinement.
EXTREME_Z = 1.5


class PositioningAnalyzer:
    """Transforme le positionnement de la foule en score contrarian."""

    def __init__(self) -> None:
        self._retail = RollingWindow(252)
        self._putcall = RollingWindow(252)
        self._feargreed = RollingWindow(252)

    @staticmethod
    def _contrarian_curve(z: float) -> float:
        """Mappe un z-score de positionnement vers un score contrarian.

        - près de 0 (positionnement neutre) → ~0 (pas d'edge)
        - extrême positif (foule trop longue) → négatif (baissier)
        - extrême négatif (foule trop courte/peureuse) → positif (haussier)

        On amplifie seulement la zone extrême (au-delà de EXTREME_Z).
        """
        if abs(z) < EXTREME_Z:
            # zone morte atténuée : peu de signal
            return -z * 8.0
        # zone extrême : signal contrarian fort, clippé
        sign = -1 if z > 0 else 1
        magnitude = min(100.0, 40.0 + (abs(z) - EXTREME_Z) * 30.0)
        return sign * magnitude

    def analyze(self, inp: PositioningInputs) -> tuple[float, bool]:
        """Retourne (score_contrarian [-100,100], extrême_détecté)."""
        signals: list[float] = []
        extreme = False

        if inp.retail_long_pct is not None:
            self._retail.push(inp.retail_long_pct)
            z = zscore(inp.retail_long_pct, self._retail.values())
            signals.append(self._contrarian_curve(z))
            extreme = extreme or abs(z) >= EXTREME_Z

        if inp.put_call_gld is not None:
            self._putcall.push(inp.put_call_gld)
            z = zscore(inp.put_call_gld, self._putcall.values())
            # put/call élevé = peur = contrarian haussier → on inverse le signe
            # d'entrée puis on applique la courbe (qui ré-inverse aux extrêmes)
            signals.append(self._contrarian_curve(-z))
            extreme = extreme or abs(z) >= EXTREME_Z

        if inp.fear_greed is not None:
            self._feargreed.push(inp.fear_greed)
            z = zscore(inp.fear_greed, self._feargreed.values())
            signals.append(self._contrarian_curve(z))
            extreme = extreme or abs(z) >= EXTREME_Z

        if not signals:
            return 0.0, False
        score = sum(signals) / len(signals)
        return max(-100.0, min(100.0, score)), extreme
