#!/usr/bin/env python3
"""
pull_options_spill2023.py  -  fill the cross-year gap in pull_options.py.

The 2022 World Cup window [first match -21d, last match +22d] spills into Jan 2023,
so a handful of *control* trade-days land in January 2023. AlgoSeek buckets are
year-partitioned (`us-options-{daily-greeks,1min-taq}-YYYY`), and pull_options.py
hardcodes the tournament year (2022), so it queries the wrong bucket for those days
and reports them missing. Those Jan-2023 dates live in the 2023 buckets.

This script pulls ONLY the Jan-2023 control trade-days for SPY, writing into the same
on-disk tree under the 2022 tournament directory so the analysis script picks them up:
  greeks -> data/market/options/raw/greeks/2022/SPY.YYYYMMDD.csv.gz
  taq    -> data/market/options/raw/taq/2022/YYYYMMDD/SPY.<EXP>.csv.gz
Same DTE_CAP / expiry-front logic as the main script. Idempotent.
"""
import os, sys, subprocess
import importlib.util
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUTD = os.path.join(ROOT, "data", "market", "options", "raw")

spec = importlib.util.spec_from_file_location("po", os.path.join(ROOT, "ingest", "pull_options.py"))
po = importlib.util.module_from_spec(spec); spec.loader.exec_module(po)

DTE_CAP = po.DTE_CAP
PROF_TAQ = po.PROF_TAQ
PROF_GREEKS = po.PROF_GREEKS


def _aws(args, profile, timeout=600):
    cmd = ["aws"] + args + ["--profile", profile, "--request-payer", "requester"]
    env = dict(os.environ, AWS_PAGER="")
    return subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=timeout)


def _spill_days():
    """2022-tournament control trade-days that fall in calendar year 2023."""
    td = po.trade_dates()
    days = sorted(set(td[2022]["match"] + td[2022]["control"]))
    return [d for d in days if d[:4] == "2023"]


def _list_expiries_2023(ymd):
    uri = f"s3://us-options-1min-taq-2023/{ymd}/S/SPY/"
    r = _aws(["s3", "ls", uri], PROF_TAQ, timeout=120)
    res = []
    for line in r.stdout.splitlines():
        parts = line.split()
        if not parts:
            continue
        name = parts[-1]
        if not name.startswith("SPY.") or not name.endswith(".csv.gz"):
            continue
        exp = name[len("SPY."):-len(".csv.gz")]
        if len(exp) == 8 and exp.isdigit():
            res.append((exp, uri + name))
    return res


def main():
    days = _spill_days()
    print(f"spill (Jan-2023) trade-days: {days}")
    # greeks
    gdir = os.path.join(OUTD, "greeks", "2022")
    os.makedirs(gdir, exist_ok=True)
    for ds in days:
        ymd = ds.replace("-", "")
        key = f"s3://us-options-daily-greeks-2023/{ymd}/S/SPY.csv.gz"
        dst = os.path.join(gdir, f"SPY.{ymd}.csv.gz")
        if os.path.exists(dst) and os.path.getsize(dst) > 0:
            print(f"[greeks spill {ds}] have"); continue
        r = _aws(["s3", "cp", key, dst, "--quiet"], PROF_GREEKS)
        ok = r.returncode == 0 and os.path.exists(dst)
        print(f"[greeks spill {ds}] {'ok' if ok else 'MISS '+r.stderr.strip()[:80]}")
    # taq
    for ds in days:
        ymd = ds.replace("-", "")
        exps = _list_expiries_2023(ymd)
        tdate = pd.Timestamp(ds)
        keep = [(e, key) for (e, key) in exps
                if 0 <= (pd.Timestamp(e[:4] + "-" + e[4:6] + "-" + e[6:8]) - tdate).days <= DTE_CAP]
        ddir = os.path.join(OUTD, "taq", "2022", ymd)
        os.makedirs(ddir, exist_ok=True)
        got = 0
        for (e, key) in keep:
            dst = os.path.join(ddir, f"SPY.{e}.csv.gz")
            if os.path.exists(dst) and os.path.getsize(dst) > 0:
                got += 1; continue
            r = _aws(["s3", "cp", key, dst, "--quiet"], PROF_TAQ)
            if r.returncode == 0 and os.path.exists(dst):
                got += 1
            else:
                print(f"  FAIL {key}: {r.stderr.strip()[:100]}")
        print(f"[taq spill {ds}] kept={len(keep)} got={got}", flush=True)


if __name__ == "__main__":
    main()
