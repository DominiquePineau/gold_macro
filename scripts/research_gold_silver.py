"""Recherche #3a : le ratio Or/Argent a-t-il un edge sur l'or ?

Or = xau-system D1 ; Argent = SI=F (Yahoo, gratuit). Teste :
  - ratio extrême (z-score) -> rendement forward de l'or (réversion ?)
  - momentum du ratio -> direction de l'or
  - l'argent mène-t-il l'or (lead/lag) ?
Honnête : on cherche un VRAI signal, pas à confirmer un biais.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
import httpx

XAU_M5 = "/home/ubuntu/xau-system/data/parquet/XAUUSD_M5.parquet"


def load_gold():
    df = pd.read_parquet(XAU_M5)
    g = df["close"].resample("1D").last().dropna()
    g.index = g.index.tz_convert("UTC").normalize()
    return g


def load_silver():
    r = httpx.get("https://query1.finance.yahoo.com/v8/finance/chart/SI=F",
                  params={"range": "7y", "interval": "1d"},
                  headers={"User-Agent": "Mozilla/5.0"}, timeout=30, follow_redirects=True)
    res = r.json()["chart"]["result"][0]
    ts = pd.to_datetime(res["timestamp"], unit="s", utc=True).normalize()
    cl = res["indicators"]["quote"][0]["close"]
    s = pd.Series(cl, index=ts).dropna()
    return s[~s.index.duplicated()]


def tstat(x):
    x = x[np.isfinite(x)]
    return float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))) if len(x) > 1 and x.std() > 0 else float("nan")


def main():
    g = load_gold(); s = load_silver()
    idx = g.index.intersection(s.index)
    g = g.loc[idx]; s = s.loc[idx]
    ratio = g / s
    print(f"jours alignés: {len(idx)}  {idx.min().date()} -> {idx.max().date()}")
    print(f"ratio or/argent: actuel {ratio.iloc[-1]:.1f}, moy {ratio.mean():.1f}, min {ratio.min():.1f}, max {ratio.max():.1f}")

    # z-score du ratio (252j)
    z = (ratio - ratio.rolling(252).mean()) / ratio.rolling(252).std()
    gret = lambda h: g.shift(-h) / g - 1.0   # rendement forward or

    print("\n=== Rendement forward de l'OR (20j) par bucket de ratio z-score ===")
    buckets = [(-9, -1.5, "ratio très bas (or cheap/argent)"),
               (-1.5, -0.5, "bas"), (-0.5, 0.5, "neutre"),
               (0.5, 1.5, "haut"), (1.5, 9, "très haut (or cher vs argent)")]
    f20 = gret(20)
    for lo, hi, lab in buckets:
        m = (z > lo) & (z <= hi)
        sub = f20[m].dropna().values
        if len(sub):
            print(f"  {lab:<34} n={len(sub):>4} moyFwd20={100*sub.mean():+.2f}% hit={100*np.mean(sub>0):.0f}% t={tstat(sub):.2f}")

    print("\n=== Momentum du ratio -> direction or (le ratio baisse = or surperforme ?) ===")
    rmom = ratio / ratio.shift(20) - 1.0
    for h in (10, 20):
        fwd = gret(h)
        # ratio en baisse (argent surperforme) -> signal ?
        down = fwd[(rmom < -0.03)].dropna().values
        up = fwd[(rmom > 0.03)].dropna().values
        print(f"  H={h}j | ratio↓ (>3%): or moyFwd={100*np.mean(down):+.2f}% (n={len(down)}) | "
              f"ratio↑: or moyFwd={100*np.mean(up):+.2f}% (n={len(up)})")

    print("\n=== L'ARGENT mène-t-il l'OR ? (corrélation rendement argent[t] -> or[t+k]) ===")
    sret = s.pct_change()
    gretd = g.pct_change()
    for k in (0, 1, 2, 3):
        c = np.corrcoef(sret.shift(k).dropna().align(gretd, join="inner")[0],
                        gretd.align(sret.shift(k).dropna(), join="inner")[0])[0, 1]
        print(f"  argent décalé de {k}j vs or : corr = {c:+.3f}")
    print("\n(corr ~même jour élevée = co-mouvement ; lag>0 significatif = l'argent mène)")


if __name__ == "__main__":
    main()
