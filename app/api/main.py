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
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from pathlib import Path

from app.core.models import Alert, GoldSnapshot
from app.core.orchestrator import GoldMacroOrchestrator
from app.integrations.tradingview import TradingViewStore, parse_tv_payload
from app.sources.mock import MockProvider
from app.storage.sqlite import SQLiteSnapshotRepository

WEBHOOK_URL = os.environ.get("ALERT_WEBHOOK_URL")
DB_PATH = os.environ.get("GOLD_MACRO_DB", "gold_macro.db")
WARMUP_CYCLES = int(os.environ.get("GOLD_MACRO_WARMUP", "20"))
TV_SECRET = os.environ.get("TRADINGVIEW_WEBHOOK_SECRET")
_DASHBOARD = Path(__file__).resolve().parent.parent / "web" / "dashboard.html"
tv_store = TradingViewStore()


def _select_provider():
    """Choisit le provider selon l'environnement."""
    if os.environ.get("FRED_API_KEY"):
        # En prod, on brancherait FredProvider (+ flux prix XAU).
        # Gardé en mock par défaut pour démo autonome.
        pass
    return MockProvider()


repository = SQLiteSnapshotRepository(db_path=DB_PATH)
orchestrator = GoldMacroOrchestrator(provider=_select_provider(), repository=repository)


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
    # warm-up : quelques cycles pour amorcer les z-scores (configurable)
    for _ in range(WARMUP_CYCLES):
        await orchestrator.run_cycle()
    yield


app = FastAPI(title="Gold Macro Engine", version="0.1.0", lifespan=lifespan)


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """Cockpit web (React) — scores, historique, alertes, dernière alerte TV."""
    if _DASHBOARD.exists():
        return HTMLResponse(_DASHBOARD.read_text(encoding="utf-8"))
    raise HTTPException(404, "dashboard introuvable")


@app.get("/health")
async def health():
    return {"status": "ok", "time": datetime.utcnow().isoformat()}


@app.post("/tradingview/webhook")
async def tradingview_webhook(request: Request):
    """Reçoit une alerte TradingView (Pine) et l'ingère (entrée)."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "corps JSON invalide")
    if TV_SECRET and str(body.get("secret", "")) != TV_SECRET:
        raise HTTPException(401, "secret TradingView invalide")
    signal = parse_tv_payload(body)
    tv_store.add(signal)
    return {"status": "ok", "stored": signal.to_dict()}


@app.get("/tradingview/signals")
async def tradingview_signals(limit: int = 20):
    return [s.to_dict() for s in tv_store.recent(limit)]


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


@app.get("/history")
async def history(since: Optional[str] = None, until: Optional[str] = None,
                  limit: int = 1000):
    """Série temporelle des composites persistés (filtrable par fenêtre ISO 8601)."""
    s = datetime.fromisoformat(since) if since else None
    u = datetime.fromisoformat(until) if until else None
    rows = repository.history(since=s, until=u, limit=limit)
    return [
        {
            "timestamp": r.timestamp.isoformat(),
            "structural_composite": r.structural_composite,
            "tactical_composite": r.tactical_composite,
            "sentiment_composite": r.sentiment_composite,
            "xau_price": r.xau_price,
            "aligned": r.aligned,
        }
        for r in rows
    ]


@app.get("/alerts")
async def alerts(kind: Optional[str] = None, severity: Optional[str] = None,
                 limit: int = 1000):
    """Journal des alertes persistées (filtrable par type / sévérité)."""
    rows = repository.alerts(kind=kind, severity=severity, limit=limit)
    return [
        {"timestamp": a.timestamp.isoformat(), "kind": a.kind,
         "severity": a.severity, "message": a.message}
        for a in rows
    ]


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
