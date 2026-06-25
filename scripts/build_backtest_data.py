"""Assemble le dataset historique quotidien pour le backtest (offline, pandas).

Sortie : data/backtest_daily.csv avec colonnes
  date, xau_close, real_rates_level, nominal_10y, dxy, cot_net_spec

Sources :
  - FRED  : DFII10 (taux réel 10Y), DGS10 (nominal 10Y), DTWEXBGS (dollar large)
  - XAU   : xau-system M5 -> resample D1 close
  - COT   : xau-system cot_gold.parquet (net_spec hebdo, point-in-time via available_at)

NB : ce script est un outil OFFLINE (pandas autorisé). Le harnais de backtest
(`app/backtest/`) lit le CSV produit avec la stdlib (cœur sans pandas).
Données non committées (cf .gitignore) : relancer pour régénérer.
"""
from __future__ import annotations

import sys
from pathlib import Path

import httpx
import pandas as pd

FRED = "https://api.stlouisfed.org/fred/series/observations"
XAU_M5 = "/home/ubuntu/xau-system/data/parquet/XAUUSD_M5.parquet"
COT = "/home/ubuntu/xau-system/data/external/cot_gold.parquet"
START = "2020-01-01"


def _fred_key() -> str:
    for l in Path("/home/ubuntu/trade/.env").read_text().splitlines():
        if l.startswith("FRED_API_KEY="):
            return l.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("FRED_API_KEY introuvable")


def fred_series(sid: str, key: str) -> pd.Series:
    r = httpx.get(FRED, params={"series_id": sid, "api_key": key, "file_type": "json",
                                "observation_start": START, "sort_order": "asc"}, timeout=30)
    r.raise_for_status()
    rows = [(o["date"], o["value"]) for o in r.json()["observations"] if o["value"] not in (".", "", None)]
    s = pd.Series({pd.Timestamp(d, tz="UTC"): float(v) for d, v in rows}).sort_index()
    return s


def main() -> None:
    key = _fred_key()
    print("FRED...", flush=True)
    tips = fred_series("DFII10", key)
    nominal = fred_series("DGS10", key)
    dxy = fred_series("DTWEXBGS", key)

    print("XAU resample D1...", flush=True)
    m5 = pd.read_parquet(XAU_M5)
    xau = m5["close"].resample("1D").last().dropna()

    print("COT point-in-time...", flush=True)
    cot = pd.read_parquet(COT)
    cot["available_at"] = pd.to_datetime(cot["available_at"], utc=True)
    cot = cot.sort_values("available_at").set_index("available_at")["net_spec"]

    # index quotidien commun = jours où XAU existe, depuis START
    idx = xau.index[xau.index >= pd.Timestamp(START, tz="UTC")]
    df = pd.DataFrame(index=idx)
    df["xau_close"] = xau.reindex(idx)
    # FRED/COT : forward-fill point-in-time (dernière valeur connue <= date)
    df["real_rates_level"] = tips.reindex(idx, method="ffill")
    df["nominal_10y"] = nominal.reindex(idx, method="ffill")
    df["dxy"] = dxy.reindex(idx, method="ffill")
    df["cot_net_spec"] = cot.reindex(idx, method="ffill")
    df = df.dropna()

    out = Path(__file__).resolve().parent.parent / "data" / "backtest_daily.csv"
    out.parent.mkdir(exist_ok=True)
    df.index.name = "date"
    df.to_csv(out)
    print(f"OK -> {out}  ({len(df)} jours, {df.index.min().date()} -> {df.index.max().date()})")
    print(df.head(2).to_string())
    print(df.tail(2).to_string())


if __name__ == "__main__":
    sys.exit(main())
