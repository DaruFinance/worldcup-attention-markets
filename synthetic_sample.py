#!/usr/bin/env python3
"""
Synthetic sample generator — no real data, no inferential content.

This repository does not distribute market data (see DATA.md). To let the headline
cross-market scripts run end to end as a smoke test, this builds a small SYNTHETIC
estimation panel with the same schema as the real ``all_panel.parquet`` and writes it to
``data/market/panel/all_panel.parquet`` (gitignored). The during-match effect is zero by
construction, so any number produced by running the analysis on this file is meaningless;
it only proves the pipeline executes. Build the real panel from the sources documented in
DATA.md to reproduce the paper.

    python synthetic_sample.py
    python analysis/regress_crossmarket.py     # runs on the synthetic panel

Drives the panel-based scripts (regress_crossmarket, equivalence_tost, comovement,
event_study). The daily-arm scripts (home_equities, sentiment, fx_exotic_extended) read the
public daily sources in DATA.md, not this panel.
"""
import os
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.abspath(__file__))
OUTDIR = os.path.join(ROOT, "data", "market", "panel")
GROUPS = {
    "crypto_spot": ["BTC", "ETH"],
    "crypto_perp": ["BTCPERP", "ETHPERP"],
    "equity_fut": ["ES", "NQ"],
    "commodity_fut": ["GC", "CL"],
    "fx_fut": ["6E", "6B", "6J"],
}
INST_GROUP = {i: g for g, insts in GROUPS.items() for i in insts}
INST_IDX = {i: k for k, i in enumerate(INST_GROUP)}          # deterministic per-instrument offset
N_DAYS, N_MIN = 40, 120                                       # per tournament; synthetic minutes per day
DOM_TEAMS = ["USA", "EURO", "GBP", "JPY", "NONE"]


def build():
    rng = np.random.default_rng(0)
    starts = {2018: "2018-06-14", 2022: "2022-11-20", 2026: "2026-06-11"}
    rows = []
    for tour, start in starts.items():
        for dt in pd.date_range(start, periods=N_DAYS, freq="D"):
            has_match = rng.random() < 0.6                    # ~60% of days carry a match window
            ko = int(rng.integers(0, N_MIN - 105)) if has_match else -1
            knockout = bool(has_match and rng.random() < 0.3)
            dom = rng.choice(DOM_TEAMS) if has_match else "NONE"
            wd = dt.weekday()
            for inst, grp in INST_GROUP.items():
                off = INST_IDX[inst] * 0.1                    # deterministic instrument effect
                for m in range(N_MIN):
                    match = 1 if (has_match and ko <= m < ko + 105) else 0
                    lvol = 10.0 + off + rng.normal(0, 0.3)    # zero match effect by construction
                    ltrades = 8.0 + off + rng.normal(0, 0.3)
                    rows.append((
                        tour, inst, grp, match, f"{wd}_{m}", dt.strftime("%Y-%m-%d"),
                        lvol, ltrades, abs(rng.normal(0, 1e-3)), abs(rng.normal(0, 1e-3)),
                        lvol - ltrades, rng.normal(0, 0.1), abs(rng.normal(0, 1e-6)),
                        int(match and dom == "USA"), int(match and dom == "EURO"),
                        int(match and dom == "GBP"), int(match and dom == "JPY"),
                        int(match and knockout),
                    ))
    cols = ["tournament", "instrument", "market_group", "match", "wd_mod", "date",
            "lvol", "ltrades", "absret", "hlrange", "lavg_trade", "signed_imb", "amihud",
            "any_usa_i", "any_euro_i", "any_gbp_i", "any_jpy_i", "any_knockout_i"]
    df = pd.DataFrame(rows, columns=cols)
    os.makedirs(OUTDIR, exist_ok=True)
    path = os.path.join(OUTDIR, "all_panel.parquet")
    df.to_parquet(path)
    print(f"wrote {path}")
    print(f"  {len(df):,} rows | {df['match'].sum():,} match-minutes | "
          f"{df['date'].nunique()} dates | instruments {sorted(df['instrument'].unique())}")
    print("  SYNTHETIC: during-match effect is zero by construction; results carry no meaning.")


if __name__ == "__main__":
    build()
