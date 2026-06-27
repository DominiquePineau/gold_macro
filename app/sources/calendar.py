"""Calendrier économique (événements à fort impact sur l'or).

Récupère les dates de publication à venir via l'API FRED (releases) pour les
événements US qui bougent l'or — CPI, Emploi/NFP, PCE, PIB, ventes au détail —
et calcule les heures avant le prochain. Alimente l'alerte EVENT_PROXIMITY.

Les FOMC ne sont pas des « releases » FRED → liste configurable (à ajuster).
Heures standard : releases de données à 08:30 ET, FOMC à 14:00 ET.

Mode dégradé : si FRED est injoignable, on garde le dernier calendrier connu.
"""
from __future__ import annotations

import time as _time
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

import httpx

FRED_REL = "https://api.stlouisfed.org/fred/release/dates"
ET = ZoneInfo("America/New_York")

# release_id FRED -> (nom, impact, heure ET de publication)
RELEASES = {
    10: ("CPI (inflation US)", "high", time(8, 30)),
    50: ("Emploi / NFP", "high", time(8, 30)),
    54: ("PCE / Revenus", "high", time(8, 30)),
    53: ("PIB US", "medium", time(8, 30)),
    17: ("Ventes au détail", "medium", time(8, 30)),
}

# FOMC : pas une release FRED. Dates de DÉCISION 2026 (2e jour) — À VÉRIFIER/AJUSTER.
DEFAULT_FOMC = ["2026-07-29", "2026-09-16", "2026-10-28", "2026-12-16"]
FOMC_TIME_ET = time(14, 0)


@dataclass
class EconEvent:
    when: datetime          # UTC, tz-aware
    name: str
    impact: str             # "high" | "medium"

    def hours_from(self, now: datetime) -> float:
        return (self.when - now).total_seconds() / 3600.0


def _to_utc(date_str: str, t_et: time) -> datetime:
    d = datetime.fromisoformat(date_str).date()
    return datetime.combine(d, t_et, tzinfo=ET).astimezone(timezone.utc)


class EconomicCalendar:
    """Calendrier macro US (FRED releases + FOMC configurable), avec cache."""

    def __init__(self, api_key: str, *, lookahead_days: int = 21,
                 cache_ttl_seconds: float = 6 * 3600.0, timeout: float = 20.0,
                 fomc_dates: Optional[list[str]] = None):
        self.api_key = api_key
        self.lookahead = lookahead_days
        self.cache_ttl = cache_ttl_seconds
        self.timeout = timeout
        self.fomc_dates = DEFAULT_FOMC if fomc_dates is None else fomc_dates
        self._cache: list[EconEvent] = []
        self._fetched_at: float = -1e18

    async def _fetch_release(self, client: httpx.AsyncClient, rid: int) -> list[str]:
        today = datetime.now(timezone.utc).date().isoformat()
        r = await client.get(FRED_REL, params={
            "release_id": rid, "api_key": self.api_key, "file_type": "json",
            "include_release_dates_with_no_data": "true",
            "realtime_start": today, "sort_order": "asc", "limit": 6})
        r.raise_for_status()
        return [x["date"] for x in r.json().get("release_dates", []) if x["date"] >= today]

    async def upcoming(self) -> list[EconEvent]:
        """Liste triée des événements à venir (cache + mode dégradé)."""
        if self._cache and (_time.monotonic() - self._fetched_at) < self.cache_ttl:
            return self._cache
        now = datetime.now(timezone.utc)
        horizon = now + timedelta(days=self.lookahead)
        events: list[EconEvent] = []
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                for rid, (name, impact, t_et) in RELEASES.items():
                    for ds in await self._fetch_release(client, rid):
                        ev = EconEvent(_to_utc(ds, t_et), name, impact)
                        if now <= ev.when <= horizon:
                            events.append(ev)
            for ds in self.fomc_dates:
                ev = EconEvent(_to_utc(ds, FOMC_TIME_ET), "FOMC (décision Fed)", "high")
                if now <= ev.when <= horizon:
                    events.append(ev)
            events.sort(key=lambda e: e.when)
            self._cache = events
            self._fetched_at = _time.monotonic()
            return events
        except Exception:
            return self._cache  # dégradé : dernier calendrier connu

    async def next_event(self) -> Optional[EconEvent]:
        now = datetime.now(timezone.utc)
        for e in await self.upcoming():
            if e.when > now:
                return e
        return None

    async def hours_to_next(self) -> Optional[float]:
        """Feed `calendar` : heures avant le prochain événement (ou None)."""
        e = await self.next_event()
        return e.hours_from(datetime.now(timezone.utc)) if e else None

    async def next_event_name(self) -> Optional[str]:
        e = await self.next_event()
        return e.name if e else None
