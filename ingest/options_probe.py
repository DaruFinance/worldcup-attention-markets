#!/usr/bin/env python3
"""
options_probe.py  -  Probe & sample AlgoSeek US Equity Options (OPRA) for the
World Cup attention study's options section.

Goal: determine whether intraday SPY options data (for ATM-IV, 25-delta skew,
put/call volume measures) is obtainable, and pull a compact verification slice.

Findings (see handoffs/options.md for the full report):
  - AlgoSeek HAS a full US Equity Options (OPRA) product, history ~2012->present.
  - Both World Cup years 2018 and 2022 are covered.
  - Relevant datasets & buckets (all us-east-1, REQUESTER-PAYS):
      daily-greeks   us-options-daily-greeks-YYYY   profile algoseek_787889850840
                     -> EOD MidImpliedVol + Mid{Delta,Gamma,Theta,Vega,Rho} per
                        contract; gives ATM-IV and 25-delta skew (DAILY, not intraday).
      1min-taq       us-options-1min-taq-YYYY       profile algoseek_545933605308
                     -> per-minute per-contract bid/ask/trade OHLC + Volume +
                        TotalTrades + underlying mid; gives INTRADAY put/call volume.
  - Path layout: s3://<bucket>/YYYYMMDD/<FirstLetter>/...  (partitioned by ticker
    initial). SPY:
        greeks:  .../YYYYMMDD/S/SPY.csv.gz                (one file/day, ~190-310 KB)
        1min:    .../YYYYMMDD/S/SPY/SPY.YYYYMMDD.csv.gz   (one file/day, ~4-8 MB gz)

Run modes:
  python3 ingest/options_probe.py probe   # list buckets / confirm SPY paths exist
  python3 ingest/options_probe.py pull     # download the 4-file verification slice
  python3 ingest/options_probe.py inspect  # print schema + computed measures from slice
"""
import sys, gzip, csv, subprocess, os

OUT = os.path.join(os.path.dirname(__file__), "..", "data", "options_probe")
OUT = os.path.abspath(OUT)

# Two sample match days, one per completed World Cup in scope.
# 2018-06-15 (Fri, WC2018 group stage); 2022-11-21 (Mon, WC2022 group stage).
PROF_GREEKS = "algoseek_787889850840"
PROF_TAQ = "algoseek_545933605308"

JOBS = [
    # (label, profile, s3_uri, local_name)
    ("greeks_2018", PROF_GREEKS,
     "s3://us-options-daily-greeks-2018/20180615/S/SPY.csv.gz",
     "greeks_SPY_20180615.csv.gz"),
    ("greeks_2022", PROF_GREEKS,
     "s3://us-options-daily-greeks-2022/20221121/S/SPY.csv.gz",
     "greeks_SPY_20221121.csv.gz"),
    ("taq1min_2018", PROF_TAQ,
     "s3://us-options-1min-taq-2018/20180615/S/SPY/SPY.20180615.csv.gz",
     "taq1min_SPY_20180615.csv.gz"),
    ("taq1min_2022", PROF_TAQ,
     "s3://us-options-1min-taq-2022/20221121/S/SPY/SPY.20221121.csv.gz",
     "taq1min_SPY_20221121.csv.gz"),
]


def _aws(args, profile):
    cmd = ["aws"] + args + ["--profile", profile, "--request-payer", "requester"]
    env = dict(os.environ, AWS_PAGER="")
    return subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=300)


def probe():
    """Confirm the option buckets exist and SPY day-files are present."""
    for label, prof, uri, _ in JOBS:
        r = _aws(["s3", "ls", uri], prof)
        ok = "SPY" in r.stdout
        print(f"[{label}] {uri}\n   -> {'OK ' + r.stdout.strip() if ok else 'MISSING: ' + (r.stderr.strip() or r.stdout.strip())}")


def pull():
    os.makedirs(OUT, exist_ok=True)
    for label, prof, uri, name in JOBS:
        dst = os.path.join(OUT, name)
        r = _aws(["s3", "cp", uri, dst], prof)
        if r.returncode == 0:
            print(f"[{label}] downloaded -> {dst} ({os.path.getsize(dst)} bytes)")
        else:
            print(f"[{label}] FAILED: {r.stderr.strip()}")


def _interp_iv_at_delta(rows, callput, target_delta):
    """Linear-interp IV at a target delta among converged contracts of one expiry."""
    pts = sorted((float(r["MidDelta"]), float(r["MidImpliedVol"])) for r in rows
                 if r["CallPut"] == callput and r["ImpliedVolConvergence"] == "Converged")
    if len(pts) < 2:
        return None
    for (d0, v0), (d1, v1) in zip(pts, pts[1:]):
        lo, hi = min(d0, d1), max(d0, d1)
        if lo <= target_delta <= hi and d1 != d0:
            return v0 + (v1 - v0) * (target_delta - d0) / (d1 - d0)
    return None


def inspect():
    # ---- daily greeks: ATM IV + 25-delta skew ----
    for name, day in [("greeks_SPY_20180615.csv.gz", "20180615"),
                      ("greeks_SPY_20221121.csv.gz", "20221121")]:
        p = os.path.join(OUT, name)
        with gzip.open(p, "rt") as fh:
            rows = list(csv.DictReader(fh))
        # choose the front monthly-ish expiry with most converged contracts and >=20 DTE
        from collections import defaultdict
        byexp = defaultdict(list)
        for r in rows:
            byexp[r["Expiration"]].append(r)
        cand = [(e, rs) for e, rs in byexp.items()
                if rs and int(rs[0]["DaysToMaturity"]) >= 20]
        cand.sort(key=lambda kv: -sum(1 for r in kv[1] if r["ImpliedVolConvergence"] == "Converged"))
        exp, ers = cand[0]
        atm_c = _interp_iv_at_delta(ers, "C", 0.50)
        d25c = _interp_iv_at_delta(ers, "C", 0.25)
        d25p = _interp_iv_at_delta(ers, "P", -0.25)
        skew = (d25p - d25c) if (d25p and d25c) else None
        print(f"[greeks {day}] expiry {exp} (DTE {ers[0]['DaysToMaturity']}): "
              f"ATM_IV={atm_c:.4f}  25dCall_IV={d25c:.4f}  25dPut_IV={d25p:.4f}  "
              f"skew(put-call)={skew:.4f}" if skew else f"[greeks {day}] insufficient")

    # ---- 1min taq: intraday put/call volume ----
    for name, day in [("taq1min_SPY_20180615.csv.gz", "20180615"),
                      ("taq1min_SPY_20221121.csv.gz", "20221121")]:
        p = os.path.join(OUT, name)
        cvol = pvol = 0
        mins = set()
        with gzip.open(p, "rt") as fh:
            for r in csv.DictReader(fh):
                mins.add(r["TimeBarStart"])
                v = r["Volume"]
                v = int(v) if v else 0
                if r["CallPut"] == "C":
                    cvol += v
                elif r["CallPut"] == "P":
                    pvol += v
        pcr = pvol / cvol if cvol else float("nan")
        print(f"[1min {day}] minutes={len(mins)} callvol={cvol} putvol={pvol} "
              f"day_PCR={pcr:.3f} (minute-level P/C ratio computable per row)")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "probe"
    {"probe": probe, "pull": pull, "inspect": inspect}[mode]()
