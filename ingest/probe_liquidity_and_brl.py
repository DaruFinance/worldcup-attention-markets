#!/usr/bin/env python3
"""
Two jobs (World Cup study gap-closer):

TASK 1  -  AlgoSeek QUOTE/LIQUIDITY product probe (documentation + live AWS).
    Confirms which AlgoSeek products carry bid/ask, spread, depth, and open
    interest historically (the data our trades-only 1min products lack), for the
    completed-tournament years 2010/2014/2018/2022. Run with `--probe` to re-probe
    AWS live; findings written to handoffs/liquidity_brl.md by hand from this run.
    (The probe is read-only `aws s3 ls`/`cp` with --request-payer requester.)

TASK 2  -  Parse the already-pulled AlgoSeek CME BRL futures (root 6L, 1min-trades
    bars) under data/market/controls/brl_raw/{year}/{YYYYMMDD}/{contract}.csv.gz
    into a continuous front-contract 1-minute USDBRL series. Front = the 6L
    contract with the max daily TotalQuantity (auto-roll), matching the convention
    in ingest/parse_futures.py.

    NOTE: the handoff brief said brl_raw held Dukascopy .bi5 files; it does not.
    It holds AlgoSeek 6L .csv.gz (1min-trades) bars, so we parse those directly
    (real exchange data, no synthetic fallback, no fabrication).

    Out: data/market/controls/USDBRL_1m.parquet
         [ts, open, high, low, close, volume, count, buy, sell]
         price = CME 6L futures price (USD per BRL); volume = TotalQuantity
         (contracts); count = TotalTradeCount.
"""
import os, sys, glob, subprocess
import pandas as pd

ROOT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
BRL_RAW  = os.path.join(ROOT_DIR, "data", "market", "controls", "brl_raw")
OUT_PARQ = os.path.join(ROOT_DIR, "data", "market", "controls", "USDBRL_1m.parquet")

# AlgoSeek 1min-trades bar columns we keep (same family as parse_futures.py).
USE = ["UTCDate", "UTCTimeBarStart", "OpenPrice", "HighPrice", "LowPrice",
       "ClosePrice", "TotalQuantity", "BuyQuantity", "SellQuantity",
       "TotalTradeCount"]


def log(m):
    from datetime import datetime, timezone
    print(f"[{datetime.now(timezone.utc):%H:%M:%S}] {m}", flush=True)


# ---------------------------------------------------------------------------
# TASK 2  -  parse BRL
# ---------------------------------------------------------------------------
def parse_brl():
    # layout: brl_raw/{year}/{YYYYMMDD}/{contract}.csv.gz  (flat, no root subdir)
    files = sorted(glob.glob(os.path.join(BRL_RAW, "*", "*", "*.csv.gz")))
    if not files:
        log("BRL: no raw files under brl_raw/  -  nothing to parse")
        return 0
    log(f"BRL: {len(files)} raw contract-day files")

    daily = {}  # date(YYYYMMDD) -> list of per-contract DataFrames
    for f in files:
        date = os.path.basename(os.path.dirname(f))
        try:
            df = pd.read_csv(f, usecols=USE)
        except Exception as e:
            log(f"  skip {f}: {e}")
            continue
        if not len(df):
            continue
        df["contract"] = os.path.basename(f).split(".")[0]
        daily.setdefault(date, []).append(df)

    frames = []
    rollchoice = []  # audit: which contract was front each day
    for date, dfs in sorted(daily.items()):
        best = max(dfs, key=lambda d: d["TotalQuantity"].sum())
        rollchoice.append((date, best["contract"].iloc[0],
                           int(best["TotalQuantity"].sum())))
        frames.append(best)
    if not frames:
        log("BRL: nothing parseable")
        return 0

    d = pd.concat(frames, ignore_index=True)
    ts = pd.to_datetime(d["UTCDate"].astype(int).astype(str) + " " +
                        d["UTCTimeBarStart"], format="%Y%m%d %H:%M", utc=True)
    out = pd.DataFrame({
        "ts": ts,
        "open":  d["OpenPrice"].astype(float),
        "high":  d["HighPrice"].astype(float),
        "low":   d["LowPrice"].astype(float),
        "close": d["ClosePrice"].astype(float),
        "volume": d["TotalQuantity"].astype(float),
        "count":  d["TotalTradeCount"].astype(float),
        "buy":    pd.to_numeric(d["BuyQuantity"], errors="coerce"),
        "sell":   pd.to_numeric(d["SellQuantity"], errors="coerce"),
    }).dropna(subset=["ts", "close"]).drop_duplicates("ts") \
      .sort_values("ts").reset_index(drop=True)

    os.makedirs(os.path.dirname(OUT_PARQ), exist_ok=True)
    out.to_parquet(OUT_PARQ)

    # coverage summary
    yr = out["ts"].dt.year
    log(f"BRL: wrote {len(out):,} minute-bars -> {OUT_PARQ}")
    for y in sorted(yr.unique()):
        sub = out[yr == y]
        log(f"  {y}: {len(sub):,} bars  "
            f"{sub['ts'].min():%Y-%m-%d}..{sub['ts'].max():%Y-%m-%d}  "
            f"price {sub['close'].min():.5f}..{sub['close'].max():.5f}")
    return len(out)


# ---------------------------------------------------------------------------
# TASK 1  -  liquidity-product probe (read-only)
# ---------------------------------------------------------------------------
PROFILE = "algoseek_545933605308"  # equities + futures core (TAQ + depth + tick)


def _ls(bucket, prefix=""):
    cmd = ["aws", "s3", "ls", "--profile", PROFILE,
           f"s3://{bucket}/{prefix}", "--request-payer", "requester"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        return r.stdout.strip()
    except Exception as e:
        return f"ERR {e}"


def probe():
    log("PROBE: AlgoSeek quote/liquidity buckets for 2010/2014/2018/2022")
    for yr in (2010, 2014, 2018, 2022):
        for b in (f"us-equity-1min-taq-{yr}",
                  f"us-futures-1min-taq-{yr}",
                  f"us-futures-taq-{yr}",
                  f"us-futures-multiple-depth-{yr}"):
            head = _ls(b)
            ok = "OK" if head and "PRE" in head else ("EMPTY" if head == "" else "?")
            first = head.splitlines()[1] if len(head.splitlines()) > 1 else head
            log(f"  {b:34s} {ok:5s} {first[:60]}")


def main():
    if "--probe" in sys.argv:
        probe()
    if "--brl" in sys.argv or "--probe" not in sys.argv:
        parse_brl()


if __name__ == "__main__":
    main()
