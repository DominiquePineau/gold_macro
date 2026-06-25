"""API FastAPI : expose le moteur de scoring XAU/USD.

Endpoints :
  GET  /health          : ping
  GET  /snapshot        : dernier snapshot calculé
  POST /evaluate        : déclenche un cycle et retourne le snapshot
  GET  /score           : version compacte (juste les biais)

Webhook sortant : à chaque alerte CRITICAL, push vers WEBHOOK_URL
(Telegram, Discord, ou ton pipeline existant).
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import datetime
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.core.models import Alert, GoldSnapshot
from app.core.orchestrator import GoldMacroOrchestrator
from app.sources.mock import MockProvider

WEBHOOK_URL = os.environ.get("ALERT_WEBHOOK_URL")


def _select_provider():
    """Choisit le provider selon l'environnement."""
    if os.environ.get("FRED_API_KEY"):
        # En prod, on brancherait FredProvider (+ flux prix XAU).
        # Gardé en mock par défaut pour démo autonome.
        pass
    return MockProvider()


orchestrator = GoldMacroOrchestrator(provider=_select_provider())


def _serialize_snapshot(s: GoldSnapshot) -> dict:
    sent = s.sentiment
    return {
        "timestamp": s.timestamp.isoformat(),
        "xau_price": s.xau_price,
        "aligned": s.aligned,
        "sentiment": ({
            "composite": sent.composite,
            "label": sent.label.value,
            "positioning_score": sent.positioning_score,
            "textual_score": sent.textual_score,
            "contrarian_flip": sent.contrarian_flip,
            "items_analyzed": sent.items_analyzed,
            "note": sent.note,
        } if sent else None),
        "structural": {
            "composite": s.structural.composite,
            "bias": s.structural.bias.value,
            "top_driver": (s.structural.top_driver().name
                           if s.structural.top_driver() else None),
            "components": [asdict(c) for c in s.structural.components],
        },
        "tactical": {
            "composite": s.tactical.composite,
            "bias": s.tactical.bias.value,
            "top_driver": (s.tactical.top_driver().name
                           if s.tactical.top_driver() else None),
            "components": [asdict(c) for c in s.tactical.components],
        },
        "alerts": [
            {"kind": a.kind, "severity": a.severity, "message": a.message,
             "timestamp": a.timestamp.isoformat()}
            for a in s.alerts
        ],
    }


async def _push_webhook(alerts: list[Alert]) -> None:
    if not WEBHOOK_URL:
        return
    critical = [a for a in alerts if a.severity == "CRITICAL"]
    if not critical:
        return
    text = "🟡 GOLD MACRO\n" + "\n".join(f"[{a.kind}] {a.message}" for a in critical)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(WEBHOOK_URL, json={"text": text})
    except Exception:
        pass  # ne jamais casser le cycle pour un webhook


@asynccontextmanager
async def lifespan(app: FastAPI):
    # warm-up : quelques cycles pour amorcer les z-scores
    for _ in range(20):
        await orchestrator.run_cycle()
    yield


app = FastAPI(title="Gold Macro Engine", version="0.1.0", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok", "time": datetime.utcnow().isoformat()}


@app.post("/evaluate")
async def evaluate():
    snap = await orchestrator.run_cycle()
    await _push_webhook(snap.alerts)
    return _serialize_snapshot(snap)


@app.get("/snapshot")
async def snapshot():
    if orchestrator.last_snapshot is None:
        raise HTTPException(404, "Aucun snapshot. Appeler /evaluate d'abord.")
    return _serialize_snapshot(orchestrator.last_snapshot)


@app.get("/score")
async def score():
    s = orchestrator.last_snapshot
    if s is None:
        raise HTTPException(404, "Aucun snapshot.")
    return {
        "structural": {"composite": s.structural.composite, "bias": s.structural.bias.value},
        "tactical": {"composite": s.tactical.composite, "bias": s.tactical.bias.value},
        "aligned": s.aligned,
        "xau_price": s.xau_price,
    }
