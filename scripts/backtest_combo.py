"""Donchian × biais gold_macro — le momentum filtré par le régime macro.

Hypothèse : le momentum (Donchian) souffre en range (whipsaws). Le biais macro
de gold_macro (structurel+tactique) identifie les régimes de tendance. En ne
restant long QUE quand la macro confirme, on devrait éviter les faux signaux de
range et améliorer le profil risque.

Réutilise le moteur réel (HistoricalReplay) pour les composites historiques,
les aligne avec un Donchian sur l'OHLC D1, et compare au Donchian seul + buy&hold.
"""
from __future__ import annotations
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, ".")
from app.backtest.replay import HistoricalReplay, load_rows
from scripts.backtest_momentum import load_d1, sig_donchian, equity, stats, ANN


def macro_series() -> pd.DataFrame:
    pts = HistoricalReplay(load_rows("data/backtest_daily.csv")).run()
    return pd.DataFrame({
        "date": [p.date for p in pts],
        "structural": [p.structural for p in pts],
        "tactical": [p.tactical for p in pts],
    }).set_index("date")


def bullish(macro: pd.DataFrame, mode: str) -> pd.Series:
    s, t = macro["structural"], macro["tactical"]
    if mode == "struct>0":
        return (s > 0).astype(float)
    if mode == "struct&tac>0":
        return ((s > 0) & (t > 0)).astype(float)
    if mode == "aligned":          # alignés haussiers (>15)
        return ((s > 15) & (t > 15)).astype(float)
    if mode == "struct>15":
        return (s > 15).astype(float)
    return pd.Series(1.0, index=macro.index)


def main():
    d1 = load_d1()
    macro = macro_series()
    # aligner sur dates communes (l'index macro est tz-aware UTC comme d1)
    common = d1.index.intersection(macro.index)
    d1 = d1.loc[common]; macro = macro.loc[common]
    print(f"jours alignés: {len(common)}  {common.min().date()} -> {common.max().date()}")

    donch = sig_donchian(d1).reindex(common).fillna(0.0)

    def report(d1sub, donchsub, macrosub, tag):
        rows = []
        # buy & hold
        net_bh, p_bh = equity(d1sub, pd.Series(1.0, index=d1sub.index))
        rows.append(stats(net_bh, p_bh, "Buy & Hold"))
        # donchian seul
        net_d, p_d = equity(d1sub, donchsub)
        rows.append(stats(net_d, p_d, "Donchian seul"))
        # combos "confirmation" (long si macro haussière)
        for mode in ("struct>0", "aligned", "struct>15"):
            filt = bullish(macrosub, mode)
            combo = pd.Series(donchsub.values * filt.values, index=d1sub.index)
            net_c, p_c = equity(d1sub, combo)
            rows.append(stats(net_c, p_c, f"Donchian × {mode}"))
        # combos "veto" (Donchian long SAUF si macro clairement baissière)
        for thr, lab in ((-15, "veto struct<-15"), (0, "veto struct<0")):
            veto = (macrosub["structural"] < thr).astype(float)
            combo = pd.Series(donchsub.values * (1 - veto.values), index=d1sub.index)
            net_v, p_v = equity(d1sub, combo)
            rows.append(stats(net_v, p_v, f"Donchian {lab}"))
        df = pd.DataFrame(rows)
        print(f"\n=== {tag} ===")
        print(df.to_string(index=False))

    report(d1, donch, macro, f"FULL ({len(common)} j)")
    m = "2024-01-01"
    report(d1.loc[:m], donch.loc[:m], macro.loc[:m], "TRAIN 2020-2023")
    report(d1.loc[m:], donch.loc[m:], macro.loc[m:], "TEST OOS 2024-2026")


if __name__ == "__main__":
    main()
