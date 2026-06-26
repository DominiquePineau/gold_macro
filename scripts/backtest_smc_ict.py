"""Backtest honnête du modèle SMC/ICT (port du smc_ict_ultimate.pine) sur XAU.

Données : XAUUSD M5 (xau-system) -> M15. Réplay causal du modèle ICT :
  sweep de liquidité -> CHoCH/tendance -> discount + OTE -> confluence FVG/OB
  -> entrée ; SL sous le sweep ; TP sur la liquidité opposée (ou RR).
Sortie simulée barre par barre (SL prioritaire). Coûts spread+slippage déduits.
Métriques en R nettes de coûts. Objectif : dire la VÉRITÉ sur l'edge mécanique.
"""
from __future__ import annotations
import sys
import numpy as np
import pandas as pd

XAU_M5 = "/home/ubuntu/xau-system/data/parquet/XAUUSD_M5.parquet"


def load_m15():
    df = pd.read_parquet(XAU_M5)
    df = df[~df.index.duplicated()].sort_index()
    df = df.loc[df.index >= "2020-01-02"]
    m15 = df.resample("15min").agg({"open": "first", "high": "max", "low": "min",
                                    "close": "last"}).dropna()
    return m15


def atr(df, n=14):
    h, l, c = df["high"], df["low"], df["close"]
    pc = c.shift(1)
    tr = pd.concat([(h - l), (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()


def run(m15, *, piv=5, liq=20, fvg_atr=0.25, max_bars=15, rr=2.0, sl_buf=0.5,
        cost_rt=0.60, use_disc=True, use_ote=True, use_kz=True, use_ob=True):
    o = m15["open"].values; h = m15["high"].values; l = m15["low"].values; c = m15["close"].values
    a = atr(m15, 14).values
    idx = m15.index
    paris = idx.tz_convert("Europe/Paris")
    hod = paris.hour + paris.minute / 60.0
    inkz = ((hod >= 8) & (hod < 11)) | ((hod >= 14) & (hod < 17)) if use_kz else np.ones(len(c), bool)
    n = len(c)

    # pivots confirmés (causal, lag = piv)
    isph = np.zeros(n, bool); ispl = np.zeros(n, bool)
    for i in range(piv, n - piv):
        if h[i] == h[i - piv:i + piv + 1].max():
            isph[i + piv] = True   # connu à i+piv
        if l[i] == l[i - piv:i + piv + 1].min():
            ispl[i + piv] = True
    ph_val = np.where(isph, np.roll(h, piv), np.nan)
    pl_val = np.where(ispl, np.roll(l, piv), np.nan)

    trades = []
    lastPH = lastPL = np.nan
    trend = 0
    bss = 10**9  # bars since sweep sell
    bsb = 10**9
    sweepLow = sweepHigh = np.nan

    for i in range(piv + 1, n - 1):
        if isph[i]:
            lastPH = ph_val[i]
        if ispl[i]:
            lastPL = pl_val[i]
        if np.isnan(a[i]):
            continue
        # structure
        bosUp = (not np.isnan(lastPH)) and c[i] > lastPH
        bosDown = (not np.isnan(lastPL)) and c[i] < lastPL
        chochUp = trend == -1 and bosUp
        chochDown = trend == 1 and bosDown
        if bosUp:
            trend = 1
        if bosDown:
            trend = -1
        # liquidité
        priorLow = l[i - liq:i].min() if i >= liq else l[:i].min()
        priorHigh = h[i - liq:i].max() if i >= liq else h[:i].max()
        sweepSell = l[i] < priorLow and c[i] > priorLow
        sweepBuy = h[i] > priorHigh and c[i] < priorHigh
        bss = 0 if sweepSell else bss + 1
        bsb = 0 if sweepBuy else bsb + 1
        if sweepSell:
            sweepLow = l[i]
        if sweepBuy:
            sweepHigh = h[i]
        # dealing range / discount / OTE
        rngHi = max(lastPH if not np.isnan(lastPH) else h[i], h[i])
        rngLo = min(lastPL if not np.isnan(lastPL) else l[i], l[i])
        eq = (rngHi + rngLo) / 2.0
        disc = c[i] < eq; prem = c[i] > eq
        oteLhi = rngHi - 0.62 * (rngHi - rngLo); oteLlo = rngHi - 0.79 * (rngHi - rngLo)
        oteShi = rngLo + 0.79 * (rngHi - rngLo); oteSlo = rngLo + 0.62 * (rngHi - rngLo)
        inOTEl = (not use_ote) or (oteLlo <= c[i] <= oteLhi)
        inOTEs = (not use_ote) or (oteSlo <= c[i] <= oteShi)
        # FVG / OB
        bullFVG = l[i] > h[i - 2] and (l[i] - h[i - 2]) >= fvg_atr * a[i]
        bearFVG = h[i] < l[i - 2] and (l[i - 2] - h[i]) >= fvg_atr * a[i]
        bullOB = c[i - 1] < o[i - 1] and c[i] > h[i - 1]
        bearOB = c[i - 1] > o[i - 1] and c[i] < l[i - 1]
        confL = (not use_ob) or bullFVG or bullOB
        confS = (not use_ob) or bearFVG or bearOB

        longSetup = inkz[i] and bss <= max_bars and (chochUp or trend == 1) and \
            ((not use_disc) or disc) and inOTEl and confL
        shortSetup = inkz[i] and bsb <= max_bars and (chochDown or trend == -1) and \
            ((not use_disc) or prem) and inOTEs and confS

        for side, setup in (("L", longSetup), ("S", shortSetup)):
            if not setup:
                continue
            entry = c[i]
            if side == "L":
                sl = (l[i] if np.isnan(sweepLow) else min(sweepLow, l[i])) - sl_buf * a[i]
                risk = entry - sl
                tp = rngHi
            else:
                sl = (h[i] if np.isnan(sweepHigh) else max(sweepHigh, h[i])) + sl_buf * a[i]
                risk = sl - entry
                tp = rngLo
            if risk <= 0 or (side == "L" and tp <= entry) or (side == "S" and tp >= entry):
                continue
            # simulation forward (SL prioritaire)
            outcome = None; xpx = c[min(i + 96, n - 1)]
            for k in range(i + 1, min(i + 96, n)):  # max ~1 jour
                if side == "L":
                    if l[k] <= sl: outcome, xpx = "sl", sl; break
                    if h[k] >= tp: outcome, xpx = "tp", tp; break
                else:
                    if h[k] >= sl: outcome, xpx = "sl", sl; break
                    if l[k] <= tp: outcome, xpx = "tp", tp; break
            d = 1 if side == "L" else -1
            pnl = d * (xpx - entry) - cost_rt
            trades.append({"R": pnl / risk, "side": side, "outcome": outcome or "timeout",
                           "year": idx[i].year})
            break  # une position à la fois (pas de pyramiding)
    return pd.DataFrame(trades)


def metrics(tr):
    if len(tr) == 0:
        return {"n": 0}
    R = tr["R"].values
    R = R[np.isfinite(R)]
    wins = R[R > 0]; loss = R[R <= 0]
    eq = np.cumprod(1 + 0.01 * R); peak = np.maximum.accumulate(eq)
    return {"n": len(R), "win%": round(100 * len(wins) / len(R), 1),
            "exp_R": round(float(R.mean()), 3),
            "PF": round(wins.sum() / -loss.sum(), 2) if loss.sum() < 0 else float("inf"),
            "maxDD%": round(100 * (eq / peak - 1).min(), 1),
            "avgWin": round(float(wins.mean()), 2) if len(wins) else 0,
            "avgLoss": round(float(loss.mean()), 2) if len(loss) else 0}


if __name__ == "__main__":
    m15 = load_m15()
    print(f"M15={len(m15)}  {m15.index.min().date()} -> {m15.index.max().date()}")
    print("\n=== Modèle complet (sweep+CHoCH+discount+OTE+FVG/OB+KZ) ===")
    for cost in (0.0, 0.30, 0.60, 1.00):
        m = metrics(run(m15, cost_rt=cost))
        print(f"  coût {cost:.2f}$ : {m}")
    print("\n=== Ablations (coût 0.60$, on retire une brique) ===")
    base = dict(cost_rt=0.60)
    variants = {
        "complet": {},
        "sans OTE": {"use_ote": False},
        "sans Discount": {"use_disc": False},
        "sans KillZone": {"use_kz": False},
        "sans FVG/OB": {"use_ob": False},
        "RR 3": {"rr": 3.0, "use_liqTP": False} if False else {"rr": 3.0},
    }
    for name, kw in variants.items():
        m = metrics(run(m15, **{**base, **kw}))
        print(f"  {name:<16}: n={m.get('n',0):>5} exp={m.get('exp_R','-')} "
              f"PF={m.get('PF','-')} win={m.get('win%','-')}% DD={m.get('maxDD%','-')}")
    print("\n=== Frictionless, par année (détecte la dépendance de régime) ===")
    tr = run(m15, cost_rt=0.0)
    for y in range(2020, 2027):
        sub = tr[tr["year"] == y]
        if len(sub):
            print(f"  {y}: n={len(sub):>4} exp={sub['R'].mean():+.3f}R win={100*(sub['R']>0).mean():.0f}%")
