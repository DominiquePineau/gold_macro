"""Configuration centralisée + validation au démarrage (Phase 6.2).

Toutes les clés/URLs viennent de l'environnement — jamais en dur. `validate()`
échoue VITE et clairement si une clé requise manque (fail-fast), pour ne pas
démarrer un service à moitié configuré.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


class ConfigError(RuntimeError):
    """Configuration invalide / incomplète au démarrage."""


@dataclass(frozen=True)
class Config:
    # sources
    fred_api_key: str | None
    anthropic_api_key: str | None
    trade_db_path: str
    # persistance
    db_path: str
    # scheduler
    tick_seconds: float
    digest_seconds: float
    news_ttl_seconds: float
    # coût Claude
    cost_report_every_eur: float
    cost_hard_stop_eur: float
    # alertes
    telegram_bot_token: str | None
    telegram_chat_id: str | None
    alert_webhook_url: str | None

    @property
    def alert_destination(self) -> str:
        if self.telegram_bot_token and self.telegram_chat_id:
            return "telegram"
        if self.alert_webhook_url:
            return "webhook"
        return "log"

    @property
    def claude_enabled(self) -> bool:
        return bool(self.anthropic_api_key)


def load(env: dict | None = None) -> Config:
    """Charge la configuration depuis l'environnement (ou un dict fourni)."""
    e = env if env is not None else os.environ

    def s(name: str) -> str | None:
        return e.get(name) or None

    def f(name: str, default: float) -> float:
        try:
            return float(e.get(name, default))
        except (TypeError, ValueError):
            return default

    return Config(
        fred_api_key=s("FRED_API_KEY"),
        anthropic_api_key=s("ANTHROPIC_API_KEY"),
        trade_db_path=e.get("TRADE_DB_PATH") or "/home/ubuntu/trade/trading.db",
        db_path=e.get("GOLD_MACRO_DB") or "gold_macro.db",
        tick_seconds=f("GOLD_MACRO_TICK_SECONDS", 300.0),
        digest_seconds=f("GOLD_MACRO_DIGEST_SECONDS", 3600.0),
        news_ttl_seconds=f("GOLD_MACRO_NEWS_TTL", 1800.0),
        cost_report_every_eur=f("COST_REPORT_EVERY_EUR", 1.0),
        cost_hard_stop_eur=f("COST_HARD_STOP_EUR", 10.0),
        telegram_bot_token=s("TELEGRAM_BOT_TOKEN"),
        telegram_chat_id=s("TELEGRAM_CHAT_ID"),
        alert_webhook_url=s("ALERT_WEBHOOK_URL"),
    )


def validate(cfg: Config, *, required: tuple[str, ...] = ("FRED_API_KEY",)) -> None:
    """Échoue vite si une clé requise manque (fail-fast)."""
    missing = []
    mapping = {
        "FRED_API_KEY": cfg.fred_api_key,
        "ANTHROPIC_API_KEY": cfg.anthropic_api_key,
    }
    for key in required:
        if not mapping.get(key):
            missing.append(key)
    if missing:
        raise ConfigError(
            "Configuration incomplète : " + ", ".join(missing) +
            " manquante(s). Renseigne ces variables d'environnement (cf. .env.example).")


def summary(cfg: Config) -> str:
    """Résumé lisible (sans secrets) de la configuration active."""
    return (
        f"FRED={'oui' if cfg.fred_api_key else 'NON'} | "
        f"Claude={'oui' if cfg.claude_enabled else 'non (repli lexique)'} | "
        f"prix_trade_db={cfg.trade_db_path} | "
        f"db={cfg.db_path} | tick={cfg.tick_seconds:.0f}s | "
        f"alertes→{cfg.alert_destination} | "
        f"coût: rapport/{cfg.cost_report_every_eur}€ stop@{cfg.cost_hard_stop_eur}€"
    )
