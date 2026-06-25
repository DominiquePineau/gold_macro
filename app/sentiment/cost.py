"""Garde-fou de coût pour les appels Claude Haiku (NLP textuel).

Demandé par l'utilisateur : **rapport d'utilisation tous les 1 €, STOP dur à 10 €.**

Estime le coût des appels à partir des tokens consommés (champ `usage` de la
réponse Messages API) × tarif Haiku 4.5 ($1.00 / MTok entrée, $5.00 / MTok sortie),
converti en EUR. Émet un rapport à chaque palier de 1 € franchi, et bloque tout
nouvel appel Claude une fois le plafond (10 €) atteint — le TextualAnalyzer
retombe alors proprement sur le lexique.
"""
from __future__ import annotations

from typing import Callable, Optional

# Tarif Claude Haiku 4.5 (USD par million de tokens).
HAIKU_INPUT_USD_PER_MTOK = 1.00
HAIKU_OUTPUT_USD_PER_MTOK = 5.00


class CostGuard:
    """Suit la dépense Claude en EUR, rapporte par palier, plafonne dur."""

    def __init__(self, *, report_every_eur: float = 1.0, hard_stop_eur: float = 10.0,
                 usd_per_eur: float = 1.08,
                 input_usd_per_mtok: float = HAIKU_INPUT_USD_PER_MTOK,
                 output_usd_per_mtok: float = HAIKU_OUTPUT_USD_PER_MTOK,
                 on_report: Optional[Callable[[float, dict], None]] = None):
        if report_every_eur <= 0 or hard_stop_eur <= 0 or usd_per_eur <= 0:
            raise ValueError("report_every_eur, hard_stop_eur, usd_per_eur doivent être > 0")
        self.report_every = report_every_eur
        self.hard_stop = hard_stop_eur
        self.usd_per_eur = usd_per_eur
        self.in_rate = input_usd_per_mtok
        self.out_rate = output_usd_per_mtok
        self.on_report = on_report
        self._spent_eur = 0.0
        self._next_threshold = report_every_eur
        self._input_tokens = 0
        self._output_tokens = 0
        self._calls = 0
        self._stopped_reported = False

    @property
    def spent_eur(self) -> float:
        return round(self._spent_eur, 4)

    @property
    def calls(self) -> int:
        return self._calls

    def cost_eur(self, input_tokens: int, output_tokens: int) -> float:
        """Coût EUR d'un appel donné (sans l'enregistrer)."""
        usd = (input_tokens / 1e6) * self.in_rate + (output_tokens / 1e6) * self.out_rate
        return usd / self.usd_per_eur

    def allowed(self) -> bool:
        """Faux une fois le plafond dur atteint -> on bloque les appels Claude."""
        if self._spent_eur >= self.hard_stop:
            if not self._stopped_reported:
                self._stopped_reported = True
                self._emit("STOP", {"spent_eur": self.spent_eur, "cap_eur": self.hard_stop})
            return False
        return True

    def record(self, input_tokens: int, output_tokens: int) -> None:
        """Enregistre la consommation d'un appel et émet un rapport par palier."""
        self._calls += 1
        self._input_tokens += int(input_tokens)
        self._output_tokens += int(output_tokens)
        self._spent_eur += self.cost_eur(input_tokens, output_tokens)
        # rapport à chaque palier de 1 € franchi (gère plusieurs paliers d'un coup)
        while self._spent_eur >= self._next_threshold:
            crossed = self._next_threshold
            self._next_threshold += self.report_every
            self._emit("REPORT", {
                "palier_eur": round(crossed, 2),
                "spent_eur": self.spent_eur,
                "calls": self._calls,
                "input_tokens": self._input_tokens,
                "output_tokens": self._output_tokens,
                "cap_eur": self.hard_stop,
            })

    def _emit(self, kind: str, detail: dict) -> None:
        if self.on_report is not None:
            self.on_report(self._spent_eur, {"kind": kind, **detail})
