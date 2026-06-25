"""Tests de la configuration + validation fail-fast (app/config.py)."""
from __future__ import annotations

import pytest

from app.config import Config, ConfigError, load, summary, validate


def test_load_defaults_empty_env():
    cfg = load(env={})
    assert cfg.fred_api_key is None
    assert cfg.anthropic_api_key is None
    assert cfg.db_path == "gold_macro.db"
    assert cfg.tick_seconds == 300.0
    assert cfg.cost_hard_stop_eur == 10.0
    assert cfg.alert_destination == "log"
    assert cfg.claude_enabled is False


def test_load_from_env_dict():
    cfg = load(env={
        "FRED_API_KEY": "k", "ANTHROPIC_API_KEY": "a",
        "GOLD_MACRO_TICK_SECONDS": "60", "COST_HARD_STOP_EUR": "5",
        "TELEGRAM_BOT_TOKEN": "T", "TELEGRAM_CHAT_ID": "C",
    })
    assert cfg.fred_api_key == "k"
    assert cfg.claude_enabled is True
    assert cfg.tick_seconds == 60.0
    assert cfg.cost_hard_stop_eur == 5.0
    assert cfg.alert_destination == "telegram"


def test_alert_destination_priority():
    assert load(env={"ALERT_WEBHOOK_URL": "http://x"}).alert_destination == "webhook"
    assert load(env={"TELEGRAM_BOT_TOKEN": "T", "TELEGRAM_CHAT_ID": "C",
                     "ALERT_WEBHOOK_URL": "http://x"}).alert_destination == "telegram"


def test_validate_raises_when_required_missing():
    with pytest.raises(ConfigError) as exc:
        validate(load(env={}), required=("FRED_API_KEY",))
    assert "FRED_API_KEY" in str(exc.value)


def test_validate_passes_when_present():
    validate(load(env={"FRED_API_KEY": "k"}), required=("FRED_API_KEY",))  # ne lève pas


def test_validate_anthropic_required():
    with pytest.raises(ConfigError):
        validate(load(env={"FRED_API_KEY": "k"}), required=("ANTHROPIC_API_KEY",))


def test_bad_numeric_falls_back_to_default():
    cfg = load(env={"GOLD_MACRO_TICK_SECONDS": "pas_un_nombre"})
    assert cfg.tick_seconds == 300.0


def test_summary_has_no_secrets():
    cfg = load(env={"FRED_API_KEY": "supersecret", "ANTHROPIC_API_KEY": "sk-secret"})
    s = summary(cfg)
    assert "supersecret" not in s and "sk-secret" not in s
    assert "FRED=oui" in s and "Claude=oui" in s
