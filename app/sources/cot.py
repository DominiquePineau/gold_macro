"""Connecteur COT (CFTC) — positionnement net des Managed Money sur l'or.

Source : rapport CFTC "Disaggregated Futures-and-Options Combined"
(Socrata `kh3c-gbw2`), or = code contrat 088691.
Net = `m_money_positions_long_all` − `m_money_positions_short_all`.

Le COT ne change qu'une fois/semaine (publié vendredi, données du mardi). On met
donc en cache : pas de re-téléchargement à chaque cycle. Mode dégradé : si la CFTC
est injoignable, on renvoie la dernière valeur connue (ou None au premier appel).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import httpx

CFTC_URL = "https://publicreporting.cftc.gov/resource/kh3c-gbw2.json"
GOLD_CONTRACT_CODE = "088691"


@dataclass
class CotSnapshot:
    report_date: str
    long_all: float
    short_all: float

    @property
    def net(self) -> float:
        return self.long_all - self.short_all


def parse_cot_row(row: dict) -> CotSnapshot:
    """Extrait le net Managed Money d'une ligne CFTC (Socrata)."""
    return CotSnapshot(
        report_date=str(row.get("report_date_as_yyyy_mm_dd", "")),
        long_all=float(row["m_money_positions_long_all"]),
        short_all=float(row["m_money_positions_short_all"]),
    )


class CotProvider:
    """Fournit le net specs COT or, avec cache hebdo et repli dégradé."""

    def __init__(self, *, contract_code: str = GOLD_CONTRACT_CODE,
                 cache_ttl_seconds: float = 6 * 3600.0, timeout: float = 30.0):
        self.contract_code = contract_code
        self.cache_ttl = cache_ttl_seconds
        self.timeout = timeout
        self._cached: Optional[CotSnapshot] = None
        self._fetched_at: Optional[datetime] = None

    def _cache_fresh(self) -> bool:
        if self._cached is None or self._fetched_at is None:
            return False
        age = (datetime.now(timezone.utc) - self._fetched_at).total_seconds()
        return age < self.cache_ttl

    async def fetch_latest(self) -> CotSnapshot:
        """Récupère le dernier rapport COT or (sans cache)."""
        params = {
            "cftc_contract_market_code": self.contract_code,
            "$order": "report_date_as_yyyy_mm_dd DESC",
            "$limit": 1,
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.get(CFTC_URL, params=params)
            r.raise_for_status()
            data = r.json()
        if not data:
            raise ValueError("CFTC : aucune donnée pour le contrat or")
        return parse_cot_row(data[0])

    async def snapshot(self) -> Optional[CotSnapshot]:
        """Snapshot COT avec cache + mode dégradé (dernier connu si CFTC down)."""
        if self._cache_fresh():
            return self._cached
        try:
            snap = await self.fetch_latest()
            self._cached = snap
            self._fetched_at = datetime.now(timezone.utc)
            return snap
        except Exception:
            # Mode dégradé : on conserve la dernière valeur connue (ou None).
            return self._cached

    async def net_specs(self) -> Optional[float]:
        """Feed : net Managed Money (utilisable comme `cot_feed` de FredProvider)."""
        snap = await self.snapshot()
        return snap.net if snap is not None else None
