#!/usr/bin/env python3
"""
pull_options.py  -  Pull SPY options data from AlgoSeek (OPRA) for the World Cup
attention study's options section. Completed tournaments only: 2014, 2018, 2022.

Two products (both us-east-1, REQUESTER-PAYS):
  1min-taq     us-options-1min-taq-YYYY      profile algoseek_545933605308
               per-minute per-contract Volume/OHLC + underlying mid.
               -> intraday SPY option volume + put/call volume ratio.
  daily-greeks us-options-daily-greeks-YYYY  profile algoseek_787889850840
               EOD MidImpliedVol + greeks per contract.
               -> ATM-IV + 25-delta skew at day resolution.

KEY LAYOUT FACT (corrected vs options_probe.py): under
  s3://<bucket>/<TRADE_YYYYMMDD>/S/SPY/
there is ONE FILE PER EXPIRATION, named SPY.<EXP_YYYYMMDD>.csv.gz, each holding all
minute bars for that trade date for contracts of that expiry. To get total option
volume for a trade date you sum across expiry files. We restrict to expiries within
DTE_CAP (45) calendar days of the trade date: that is the liquid front of the SPY
term structure where essentially all option volume sits, and bounds egress.
  daily-greeks is ONE file per trade date: s3://<bucket>/<YYYYMMDD>/S/SPY.csv.gz.

Coverage constraints (verified live, 2026-06-13):
  - 1min-taq covers 2014, 2018, 2022 (full daily coverage each).
  - daily-greeks only exists from 2017 -> so 2014 has NO greeks bucket. The day-level
    IV/skew test therefore uses 2018 + 2022 only; the intraday volume test uses all three.

Day set per tournament window [first match -21d, last match +22d]:
  - all match-days (any WC match with a kickoff that day, ET date), AND
  - non-match control weekdays in the window, on the SAME weekdays that host matches
    (so the weekday x minute-of-day FE has within-cell control mass). Capped to keep
    the pull bounded (CONTROL_CAP per tournament, evenly spaced across the window).

Run:
  python3 ingest/pull_options.py plan    # print the trade-date / file plan, no download
  python3 ingest/pull_options.py taq      # download 1min-taq (the big pull)
  python3 ingest/pull_options.py greeks    # download daily-greeks (tiny)
  python3 ingest/pull_options.py all       # greeks + taq
"""
import os, sys, subprocess
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MDIR = os.path.join(ROOT, "data", "matches")
OUTD = os.path.join(ROOT, "data", "market", "options", "raw")

PROF_TAQ = "algoseek_545933605308"
PROF_GREEKS = "algoseek_787889850840"

TOURNAMENTS = [2014, 2018, 2022]
DTE_CAP = 45          # pull expiries within 45 calendar days of trade date (liquid front)
CONTROL_CAP = 24      # max non-match control weekdays per tournament


def _aws(args, profile, timeout=600):
    cmd = ["aws"] + args + ["--profile", profile, "--request-payer", "requester"]
    env = dict(os.environ, AWS_PAGER="")
    return subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=timeout)


def _windows():
    sys.path.insert(0, os.path.join(ROOT, "analysis"))
    from build_panel_crypto import tournament_windows
    ma = pd.read_parquet(os.path.join(MDIR, "matches_all.parquet"))
    mh = pd.read_parquet(os.path.join(MDIR, "matches_hist.parquet"))
    return {**tournament_windows(mh), **tournament_windows(ma)}


def _matches():
    """Combined played matches for 2014/2018/2022 with ET trade-date + weekday."""
    ma = pd.read_parquet(os.path.join(MDIR, "matches_all.parquet"))
    mh = pd.read_parquet(os.path.join(MDIR, "matches_hist.parquet"))
    a = ma[ma["tournament"].isin([2018, 2022])][["tournament", "kickoff_utc"]].copy()
    h = mh[mh["tournament"] == 2014][["tournament", "kickoff_utc"]].copy()
    m = pd.concat([h, a], ignore_index=True)
    m["ko"] = pd.to_datetime(m["kickoff_utc"], utc=True)
    et = m["ko"].dt.tz_convert("America/New_York")
    m["date_et"] = et.dt.strftime("%Y-%m-%d")
    m["wd"] = et.dt.weekday
    return m


def trade_dates():
    """Return {tournament: {'match': [dates], 'control': [dates]}} as ET YYYY-MM-DD."""
    wins = _windows()
    m = _matches()
    out = {}
    for t in TOURNAMENTS:
        g = m[m["tournament"] == t]
        match_days = sorted(set(g["date_et"]))
        match_wds = set(g["wd"])
        lo, hi = wins[t]
        days = pd.date_range(lo.tz_convert("America/New_York").normalize(),
                             hi.tz_convert("America/New_York").normalize(), freq="D")
        # candidate controls: weekdays (Mon-Fri) in window, on match-hosting weekdays,
        # not themselves match-days (US markets shut weekends anyway).
        cand = [d.strftime("%Y-%m-%d") for d in days
                if d.weekday() < 5 and d.weekday() in match_wds
                and d.strftime("%Y-%m-%d") not in set(match_days)]
        # evenly subsample to CONTROL_CAP
        if len(cand) > CONTROL_CAP:
            idx = [round(i * (len(cand) - 1) / (CONTROL_CAP - 1)) for i in range(CONTROL_CAP)]
            cand = sorted({cand[i] for i in idx})
        out[t] = {"match": match_days, "control": cand}
    return out


def _list_expiries(bucket, ymd):
    """List expiry files under a trade-date dir; return [(exp_ymd, key, size)]."""
    uri = f"s3://{bucket}/{ymd}/S/SPY/"
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
            res.append((exp, uri + name, int(parts[2]) if len(parts) >= 3 and parts[2].isdigit() else 0))
    return res


def plan():
    td = trade_dates()
    total_days = 0
    for t in TOURNAMENTS:
        md, cd = td[t]["match"], td[t]["control"]
        total_days += len(md) + len(cd)
        print(f"[{t}] match-days={len(md)} control-days={len(cd)}  "
              f"({md[0]}..{md[-1]})")
    print(f"TOTAL trade-dates (taq) = {total_days}; greeks years = [2018, 2022] (no 2014 greeks bucket)")
    print(f"DTE_CAP={DTE_CAP} -> ~12-16 expiry files/day; rough taq files ~ {total_days*14}")


def pull_taq():
    os.makedirs(OUTD, exist_ok=True)
    td = trade_dates()
    manifest = []
    for t in TOURNAMENTS:
        bucket = f"us-options-1min-taq-{t}"
        for kind in ("match", "control"):
            for ds in td[t][kind]:
                ymd = ds.replace("-", "")
                exps = _list_expiries(bucket, ymd)
                tdate = pd.Timestamp(ds)
                # keep expiries within DTE_CAP calendar days (and not already expired before trade date)
                keep = [(e, key, sz) for (e, key, sz) in exps
                        if 0 <= (pd.Timestamp(e[:4] + "-" + e[4:6] + "-" + e[6:8]) - tdate).days <= DTE_CAP]
                ddir = os.path.join(OUTD, "taq", str(t), ymd)
                os.makedirs(ddir, exist_ok=True)
                got = 0
                for (e, key, sz) in keep:
                    dst = os.path.join(ddir, f"SPY.{e}.csv.gz")
                    if os.path.exists(dst) and os.path.getsize(dst) > 0:
                        got += 1
                        continue
                    r = _aws(["s3", "cp", key, dst, "--quiet"], PROF_TAQ)
                    if r.returncode == 0 and os.path.exists(dst):
                        got += 1
                    else:
                        print(f"  FAIL {key}: {r.stderr.strip()[:120]}")
                manifest.append(dict(tournament=t, trade_date=ds, kind=kind, n_expiry_files=got))
                print(f"[taq {t} {ds} {kind}] expiries kept={len(keep)} downloaded={got}", flush=True)
    pd.DataFrame(manifest).to_csv(os.path.join(OUTD, "taq_manifest.csv"), index=False)
    print(f"taq manifest -> {os.path.join(OUTD, 'taq_manifest.csv')}")


def pull_greeks():
    os.makedirs(OUTD, exist_ok=True)
    td = trade_dates()
    rows = []
    for t in [2018, 2022]:           # no daily-greeks bucket before 2017
        bucket = f"us-options-daily-greeks-{t}"
        ddir = os.path.join(OUTD, "greeks", str(t))
        os.makedirs(ddir, exist_ok=True)
        for kind in ("match", "control"):
            for ds in td[t][kind]:
                ymd = ds.replace("-", "")
                key = f"s3://{bucket}/{ymd}/S/SPY.csv.gz"
                dst = os.path.join(ddir, f"SPY.{ymd}.csv.gz")
                if os.path.exists(dst) and os.path.getsize(dst) > 0:
                    rows.append(dict(tournament=t, trade_date=ds, kind=kind, ok=1)); continue
                r = _aws(["s3", "cp", key, dst, "--quiet"], PROF_GREEKS)
                ok = int(r.returncode == 0 and os.path.exists(dst))
                if not ok:
                    print(f"  greeks miss {ds}: {r.stderr.strip()[:100]}")
                rows.append(dict(tournament=t, trade_date=ds, kind=kind, ok=ok))
        print(f"[greeks {t}] done", flush=True)
    pd.DataFrame(rows).to_csv(os.path.join(OUTD, "greeks_manifest.csv"), index=False)
    print(f"greeks manifest -> {os.path.join(OUTD, 'greeks_manifest.csv')}")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "plan"
    {"plan": plan, "taq": pull_taq, "greeks": pull_greeks,
     "all": lambda: (pull_greeks(), pull_taq())}[mode]()
