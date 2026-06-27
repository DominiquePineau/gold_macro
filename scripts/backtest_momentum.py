"""Backtest de stratégies momentum / trend-following sur XAU (D1) — le vrai edge.

Compare plusieurs approches simples et robustes au buy & hold, net de coûts,
avec validation out-of-sample (train 2020-2023 / test 2024-2026). Métriques
risque-ajustées (Sharpe, max DD, % temps en position) — le momentum se juge
surtout au DRAWDOWN évité, pas au rendement brut.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

XAU_M5 = "/home/ubuntu/xau-system/data/parquet/XAUUSD_M5.parquet"
COST_BPS = 2.0        # coût par transition (entrée ou sortie), en points de base
ANN = 252


def load_d1():
    df = pd.read_parquet(XAU_M5)
    df = df[~df.index.duplicated()].sort_index()
    df = df.loc[df.index >= "2020-01-02"]
    d1 = df.resample("1D").agg({"open": "first", "high": "max", "low": "min",
                                "close": "last"}).dropna()
    return d1


# ---------------------------------------------------------------- signaux (0/1)
def sig_tsmom(d1, horizons=(60, 120, 250)):
    c = d1["close"]
    signs = sum(np.sign(c / c.shift(h) - 1.0) for h in horizons)
    return (signs > 0).astype(float)  # long si momentum net positif


def sig_ma(d1, fast=50, slow=200):
    c = d1["close"]
    return ((c > c.rolling(slow).mean()) & (c.ewm(span=fast).mean() > c.ewm(span=slow).mean())).astype(float)


def sig_donchian(d1, entry=55, exit=20):
    h, l, c = d1["high"], d1["low"], d1["close"]
    hi = h.rolling(entry).max().shift(1)
    lo = l.rolling(exit).min().shift(1)
    pos = np.zeros(len(c)); state = 0.0
    cv = c.values; hiv = hi.values; lov = lo.values
    for i in range(len(c)):
        if state == 0.0 and not np.isnan(hiv[i]) and cv[i] > hiv[i]:
            state = 1.0
        elif state == 1.0 and not np.isnan(lov[i]) and cv[i] < lov[i]:
            state = 0.0
        pos[i] = state
    return pd.Series(pos, index=c.index)


# ---------------------------------------------------------------- moteur
def equity(d1, pos):
    """Position (0/1) décalée d'1 jour (anti look-ahead). Renvoie rendements nets."""
    ret = d1["close"].pct_change().fillna(0.0).values
    p = pos.shift(1).fillna(0.0).values           # on agit le lendemain du signal
    gross = p * ret
    trades = np.abs(np.diff(np.concatenate([[0.0], p])))
    cost = trades * (COST_BPS / 1e4)
    net = gross - cost
    return pd.Series(net, index=d1.index), p


def stats(net, p, label):
    if len(net) == 0:
        return {"strat": label, "n": 0}
    eq = np.cumprod(1 + net.values)
    yrs = len(net) / ANN
    cagr = eq[-1] ** (1 / yrs) - 1 if yrs > 0 else 0
    vol = net.std() * np.sqrt(ANN)
    sharpe = (net.mean() * ANN) / vol if vol > 0 else 0
    peak = np.maximum.accumulate(eq); dd = (eq / peak - 1).min()
    expo = float(np.mean(p > 0))
    return {"strat": label, "CAGR%": round(100 * cagr, 1), "vol%": round(100 * vol, 1),
            "Sharpe": round(sharpe, 2), "maxDD%": round(100 * dd, 1),
            "expo%": round(100 * expo, 0), "tot%": round(100 * (eq[-1] - 1), 0)}


def run_all(d1, tag=""):
    rows = []
    bh = d1["close"].pct_change().fillna(0.0)
    eq = np.cumprod(1 + bh.values); peak = np.maximum.accumulate(eq)
    rows.append({"strat": "Buy & Hold", "CAGR%": round(100*(eq[-1]**(ANN/len(eq))-1),1),
                 "vol%": round(100*bh.std()*np.sqrt(ANN),1),
                 "Sharpe": round((bh.mean()*ANN)/(bh.std()*np.sqrt(ANN)),2),
                 "maxDD%": round(100*(eq/peak-1).min(),1), "expo%": 100,
                 "tot%": round(100*(eq[-1]-1),0)})
    for name, sig in (("TSMOM long-only", sig_tsmom(d1)),
                      ("Trend MA (50/200)", sig_ma(d1)),
                      ("Donchian 55/20", sig_donchian(d1))):
        net, p = equity(d1, sig)
        rows.append(stats(net, p, name))
    df = pd.DataFrame(rows)
    print(f"\n=== {tag} ({d1.index.min().date()} -> {d1.index.max().date()}, {len(d1)} j) ===")
    print(df.to_string(index=False))
    return df


if __name__ == "__main__":
    d1 = load_d1()
    run_all(d1, "FULL 2020-2026")
    run_all(d1.loc[:"2023-12-31"], "TRAIN 2020-2023")
    run_all(d1.loc["2024-01-01":], "TEST OOS 2024-2026")
