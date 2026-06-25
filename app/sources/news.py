"""Flux news (RSS gratuit) pour le NLP — choix utilisateur : mix RSS + Claude réel.

Agrège plusieurs flux RSS GRATUITS (par défaut Google News filtré "or" + ForexLive
macro), filtre par pertinence or/macro AVANT d'envoyer au LLM (économie de tokens),
dédoublonne, garde les plus récents. Produit des `NewsItem` consommés par le
`TextualAnalyzer` (qui appelle Claude Haiku réel si ANTHROPIC_API_KEY est présent,
sinon repli lexique).

Mode dégradé : un flux qui échoue est ignoré (on garde les autres) ; si tout
échoue, on renvoie une liste vide (jamais d'exception qui casse le cycle).
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Optional

import httpx

from app.sentiment.models import NewsItem

# Flux RSS gratuits par défaut (mix : Google News "or" + ForexLive macro).
DEFAULT_FEEDS = [
    ("gnews", "https://news.google.com/rss/search?q=gold%20price%20XAU%20fed%20when:2d&hl=en-US&gl=US&ceid=US:en"),
    ("forexlive", "https://www.forexlive.com/feed/news"),
]

# Mots-clés de pertinence or/macro (filtre pré-LLM pour économiser des tokens).
RELEVANCE = (
    "gold", "xau", "bullion", "fed", "fomc", "powell", "rate", "rates", "yield",
    "treasury", "inflation", "cpi", "pce", "dollar", "dxy", "real rate", "tips",
    "safe haven", "geopolit", "war", "central bank", "recession", "dovish", "hawkish",
)


def _is_relevant(title: str) -> bool:
    low = title.lower()
    return any(k in low for k in RELEVANCE)


def _parse_pubdate(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    try:
        dt = parsedate_to_datetime(raw)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def parse_rss(xml_text: str, source: str) -> list[NewsItem]:
    """Parse un flux RSS en NewsItem (title + pubDate)."""
    items: list[NewsItem] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return items
    for it in root.findall(".//item"):
        title = (it.findtext("title") or "").strip()
        if not title:
            continue
        items.append(NewsItem(text=title, source=source,
                              published=_parse_pubdate(it.findtext("pubDate"))))
    return items


class NewsProvider:
    """Agrège des flux RSS, filtre la pertinence, garde les plus récents."""

    def __init__(self, feeds=DEFAULT_FEEDS, *, max_items: int = 8,
                 filter_relevance: bool = True, timeout: float = 15.0):
        self.feeds = feeds
        self.max_items = max_items
        self.filter_relevance = filter_relevance
        self.timeout = timeout

    async def _fetch(self, client: httpx.AsyncClient, source: str, url: str) -> list[NewsItem]:
        try:
            r = await client.get(url, follow_redirects=True,
                                 headers={"User-Agent": "Mozilla/5.0"})
            r.raise_for_status()
            return parse_rss(r.text, source)
        except Exception:
            return []  # flux en échec -> ignoré

    async def fetch_headlines(self) -> list[NewsItem]:
        """Récupère, filtre, dédoublonne et trie les titres récents."""
        collected: list[NewsItem] = []
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for source, url in self.feeds:
                collected.extend(await self._fetch(client, source, url))

        if self.filter_relevance:
            collected = [n for n in collected if _is_relevant(n.text)]

        # dédoublonnage par titre (insensible à la casse)
        seen: set[str] = set()
        unique: list[NewsItem] = []
        for n in collected:
            key = n.text.lower()
            if key not in seen:
                seen.add(key)
                unique.append(n)

        # tri par fraîcheur (les sans-date en dernier), cap max_items
        unique.sort(key=lambda n: n.published or datetime.min.replace(tzinfo=timezone.utc),
                    reverse=True)
        return unique[:self.max_items]

    async def __call__(self) -> list[NewsItem]:
        return await self.fetch_headlines()
