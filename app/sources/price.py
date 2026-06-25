"""Flux prix XAU live (interface PriceFeed + implémentation IG, read-only).

`PriceFeed` = callable async sans argument renvoyant le dernier prix XAU (mid),
ou None si indisponible (mode dégradé). Injectable comme `price_feed` de
FredProvider/RealProvider.

`IGPriceFeed` interroge l'API IG Markets en LECTURE SEULE (snapshot de marché ;
aucun ordre n'est jamais passé). Réutilise une session IG en cache (re-auth sur
expiration). Credentials via variables d'environnement — jamais en dur.

NB : IG est le broker de l'utilisateur. OANDA est une alternative possible
(même interface PriceFeed) si on préfère ne pas dépendre du compte de trading.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Optional

import httpx

DEFAULT_GOLD_EPIC = "CS.D.CFEGOLD.CEF.IP"  # Spot Gold ($1) côté IG


class StaticPriceFeed:
    """Feed trivial (valeur fixe) — pour tests/injection."""

    def __init__(self, value: Optional[float]):
        self.value = value

    async def __call__(self) -> Optional[float]:
        return self.value


class IGPriceFeed:
    """Prix XAU mid via IG (READ-ONLY). Session IG mise en cache."""

    def __init__(self, *, api_key: Optional[str] = None, username: Optional[str] = None,
                 password: Optional[str] = None, api_url: Optional[str] = None,
                 epic: str = DEFAULT_GOLD_EPIC, session_ttl_seconds: float = 5 * 3600.0,
                 timeout: float = 20.0):
        self.api_key = api_key or os.environ.get("IG_API_KEY")
        self.username = username or os.environ.get("IG_USERNAME")
        self.password = password or os.environ.get("IG_PASSWORD")
        self.api_url = (api_url or os.environ.get("IG_API_URL")
                        or "https://api.ig.com/gateway/deal").rstrip("/")
        self.epic = epic
        self.session_ttl = session_ttl_seconds
        self.timeout = timeout
        self._tokens: Optional[dict] = None
        self._auth_at: Optional[datetime] = None

    def _have_creds(self) -> bool:
        return bool(self.api_key and self.username and self.password)

    def _session_fresh(self) -> bool:
        if self._tokens is None or self._auth_at is None:
            return False
        return (datetime.now(timezone.utc) - self._auth_at).total_seconds() < self.session_ttl

    async def _authenticate(self, client: httpx.AsyncClient) -> dict:
        r = await client.post(
            f"{self.api_url}/session",
            headers={"X-IG-API-KEY": self.api_key, "Version": "2",
                     "Content-Type": "application/json",
                     "Accept": "application/json; charset=UTF-8"},
            json={"identifier": self.username, "password": self.password},
        )
        r.raise_for_status()
        tokens = {"CST": r.headers.get("CST"),
                  "X-SECURITY-TOKEN": r.headers.get("X-SECURITY-TOKEN")}
        self._tokens = tokens
        self._auth_at = datetime.now(timezone.utc)
        return tokens

    async def price(self) -> Optional[float]:
        """Dernier prix mid XAU (read-only). None si indispo (mode dégradé)."""
        if not self._have_creds():
            return None
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                if not self._session_fresh():
                    await self._authenticate(client)
                headers = {"X-IG-API-KEY": self.api_key, "Version": "3",
                           "Accept": "application/json; charset=UTF-8", **self._tokens}
                r = await client.get(f"{self.api_url}/markets/{self.epic}", headers=headers)
                r.raise_for_status()
                snap = r.json().get("snapshot", {})
                bid, offer = snap.get("bid"), snap.get("offer")
                if bid is None or offer is None:
                    return None
                return (float(bid) + float(offer)) / 2.0
        except Exception:
            return None  # mode dégradé : pas de prix ce cycle

    async def __call__(self) -> Optional[float]:
        return await self.price()
