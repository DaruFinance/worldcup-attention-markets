#!/usr/bin/env python3
"""
One-command refresh while the 2026 tournament is in progress. Re-pulls the latest crypto
klines, rebuilds the match spine and the unified panel, and re-runs the cross-market and
2026 out-of-sample estimates plus the tables and figures.

The futures 2026 backfill (AlgoSeek) is a separate metered pull: run
ingest/pull_futures_windows.py then ingest/parse_futures.py when you want the futures arm
refreshed for new 2026 dates.

Usage:  python3 update_2026.py
"""
import os, subprocess
HERE=os.path.dirname(os.path.abspath(__file__))
os.environ.setdefault("OPENBLAS_NUM_THREADS","1"); os.environ.setdefault("OMP_NUM_THREADS","1")

STEPS=[
    ("refresh match spine (all years)", ["python3","-c",
        "import sys;sys.path.insert(0,'ingest');import build_matches_all as b;b.main()"]),
    ("backfill crypto (latest months)", ["python3","ingest/backfill_crypto.py"]),
    ("build unified panel",             ["python3","analysis/build_panel.py"]),
    ("cross-market + 2026 OOS",         ["python3","analysis/regress_crossmarket.py"]),
    ("tables",                          ["python3","analysis/make_tables.py"]),
    ("figures",                         ["python3","analysis/make_figures.py"]),
]

def main():
    for name,cmd in STEPS:
        print(f"\n=== {name} ===", flush=True)
        r=subprocess.run(cmd, cwd=HERE)
        if r.returncode!=0:
            print(f"!! step failed: {name} (continuing)")
    print("\n2026 out-of-sample refreshed. See analysis/out/xm_2026_oos.csv")

if __name__=="__main__":
    main()
