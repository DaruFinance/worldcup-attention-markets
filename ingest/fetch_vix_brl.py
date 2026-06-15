#!/usr/bin/env python3
"""
Fetch two missing market controls over the World Cup tournament windows (2010,2014,2018,2022):

  VIX    : DAILY OHLC from Yahoo Finance chart API (symbol ^VIX).
           AlgoSeek's us-futures-1min-trades-{yr} bucket is CME-only; VIX futures
           (CFE/Cboe root 'VX') are NOT present there, so 1-min VIX is unavailable
           via the AlgoSeek entitlement. Daily is the correct granularity to label.
           Stooq (^vix) is gated behind a JS proof-of-work + "Access denied" to
           programmatic clients, so Yahoo is used instead. Day-level control.

  USDBRL : 1-MINUTE bars from AlgoSeek CME Brazilian Real futures (root '6L'),
           front-contract (max daily TotalQuantity), tournament-window dates only.
           6L quotes USD per BRL (e.g. 0.1853); we also emit usdbrl = 1/price
           (BRL per USD) for convenience. Same schema as ingest/parse_futures.py.

Out:
  data/market/controls/VIX_daily.parquet         [date, open, high, low, close]   (UTC date, ^VIX index level)
  data/market/controls/USDBRL_1m.parquet         [ts, open, high, low, close, volume, count, buy, sell, usdbrl]
  (also leaves raw 6L csv.gz under data/market/controls/brl_raw/ ; resumable)

Window = per tournament: [first_kickoff - 14d, last_kickoff + 14d].
Always set OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 before running.
"""
import os, io, json, gzip, glob, subprocess, urllib.request, urllib.parse
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np
import pandas as pd

ROOT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
MDIR = os.path.join(ROOT_DIR, "data", "matches")
OUT = os.path.join(ROOT_DIR, "data", "market", "controls")
RAW = os.path.join(OUT, "brl_raw")
P545 = "algoseek_545933605308"
BRL_ROOT = "6L"
WORKERS = 6
os.makedirs(OUT, exist_ok=True)
os.makedirs(RAW, exist_ok=True)

# Completed tournaments only (per _CONTEXT.md: do NOT use ongoing 2026).
TOURN_YEARS = {2010, 2014, 2018, 2022}


def log(m):
    print(f"[{datetime.now(timezone.utc):%H:%M:%S}] {m}", flush=True)


# ---------------------------------------------------------------- windows
def window_dates():
    """List of (year_int, 'YYYYMMDD') for every calendar day in each tournament window."""
    frames = []
    for sp in ("matches_all", "matches_hist"):
        m = pd.read_parquet(os.path.join(MDIR, f"{sp}.parquet"))
        frames.append(m[["tournament", "kickoff_utc"]])
    m = pd.concat(frames, ignore_index=True)
    m["ko"] = pd.to_datetime(m["kickoff_utc"], utc=True)
    m = m[m["tournament"].astype(int).isin(TOURN_YEARS)]
    dates = []
    for t, g in m.groupby("tournament"):
        a = g["ko"].min().normalize() - pd.Timedelta(days=14)
        b = g["ko"].max().normalize() + pd.Timedelta(days=14)
        d = a
        while d <= b:
            if d.weekday() < 5:  # skip weekends (no futures trading; saves probes)
                dates.append((int(str(t)[:4] if False else t), d.strftime("%Y%m%d")))
            d += timedelta(days=1)
    return dates


# ---------------------------------------------------------------- VIX (daily, Yahoo)
def fetch_vix():
    # span covering all four windows with margin
    p1 = int(datetime(2010, 1, 1, tzinfo=timezone.utc).timestamp())
    p2 = int(datetime(2023, 1, 31, tzinfo=timezone.utc).timestamp())
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/%5EVIX"
           f"?period1={p1}&period2={p2}&interval=1d")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    raw = urllib.request.urlopen(req, timeout=60).read()
    d = json.loads(raw)
    res = d["chart"]["result"][0]
    ts = res["timestamp"]
    q = res["indicators"]["quote"][0]
    df = pd.DataFrame({
        "date": pd.to_datetime(ts, unit="s", utc=True).normalize(),
        "open": q["open"], "high": q["high"], "low": q["low"], "close": q["close"],
    }).dropna(subset=["close"]).drop_duplicates("date").sort_values("date").reset_index(drop=True)
    df["date"] = df["date"].dt.tz_localize(None).dt.date.astype("datetime64[ns]")

    # keep only days inside (or adjacent to) the tournament windows, to stay small
    wd = pd.to_datetime([d for _, d in window_dates()], format="%Y%m%d")
    keep_dates = set(pd.to_datetime(wd).normalize())
    mask = df["date"].isin(keep_dates)
    full = df.copy()
    df = df[mask].reset_index(drop=True)
    df.to_parquet(os.path.join(OUT, "VIX_daily.parquet"))
    log(f"VIX daily: {len(df)} window trading-days (of {len(full)} fetched), "
        f"range {df['date'].min().date()}..{df['date'].max().date()}, "
        f"close {df['close'].min():.2f}-{df['close'].max():.2f}")
    return len(df)


# ---------------------------------------------------------------- USDBRL (1m, AlgoSeek 6L)
def sync_brl_day(date):
    yr = date[:4]
    bk = f"us-futures-1min-trades-{yr}"
    dst = os.path.join(RAW, yr, date)
    if os.path.isdir(dst) and any(f.endswith(".csv.gz") for f in os.listdir(dst)):
        return (date, "skip")
    os.makedirs(dst, exist_ok=True)
    cmd = ["aws", "s3", "sync", f"s3://{bk}/{date}/{BRL_ROOT}/", dst + "/",
           "--profile", P545, "--request-payer", "requester", "--only-show-errors"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        return (date, "ERR " + r.stderr.strip()[:60])
    n = len([f for f in os.listdir(dst) if f.endswith(".csv.gz")])
    return (date, f"ok({n})" if n else "empty")


USE = ["UTCDate", "UTCTimeBarStart", "OpenPrice", "HighPrice", "LowPrice", "ClosePrice",
       "TotalQuantity", "BuyQuantity", "SellQuantity", "TotalTradeCount"]


def parse_brl():
    files = sorted(glob.glob(os.path.join(RAW, "*", "*", "*.csv.gz")))
    if not files:
        return 0
    daily = {}  # date -> list of contract DataFrames
    for f in files:
        date = os.path.basename(os.path.dirname(f))
        try:
            df = pd.read_csv(f, usecols=USE)
        except Exception:
            continue
        if not len(df):
            continue
        daily.setdefault(date, []).append(df)
    frames = []
    for date, dfs in daily.items():
        best = max(dfs, key=lambda d: d["TotalQuantity"].sum())  # front contract
        frames.append(best)
    if not frames:
        return 0
    d = pd.concat(frames, ignore_index=True)
    ts = pd.to_datetime(d["UTCDate"].astype(int).astype(str) + " " + d["UTCTimeBarStart"],
                        format="%Y%m%d %H:%M", utc=True)
    out = pd.DataFrame({
        "ts": ts,
        "open": d["OpenPrice"].astype(float), "high": d["HighPrice"].astype(float),
        "low": d["LowPrice"].astype(float), "close": d["ClosePrice"].astype(float),
        "volume": d["TotalQuantity"].astype(float), "count": d["TotalTradeCount"].astype(float),
        "buy": d["BuyQuantity"].astype(float), "sell": d["SellQuantity"].astype(float),
    }).dropna(subset=["ts", "close"]).drop_duplicates("ts").sort_values("ts").reset_index(drop=True)
    # 6L price = USD per BRL; usdbrl (BRL per USD) is the conventional FX quote
    out["usdbrl"] = 1.0 / out["close"]
    out.to_parquet(os.path.join(OUT, "USDBRL_1m.parquet"))
    return out


def fetch_brl():
    dates = [d for _, d in window_dates()]
    log(f"BRL (6L) pull: {len(dates)} window weekdays")
    done = err = skip = empty = ok = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = [ex.submit(sync_brl_day, d) for d in dates]
        for fut in as_completed(futs):
            date, st = fut.result(); done += 1
            if st.startswith("ERR"):
                err += 1; log(f"  {date}: {st}")
            elif st == "skip":
                skip += 1
            elif st == "empty":
                empty += 1
            else:
                ok += 1
    log(f"  6L sync: ok={ok} skip={skip} empty={empty} err={err}")
    out = parse_brl()
    if isinstance(out, int):
        log("BRL: no rows parsed"); return 0
    by_yr = out.assign(y=out["ts"].dt.year).groupby("y").size()
    log(f"USDBRL 1m: {len(out):,} minute-bars; by year: {by_yr.to_dict()}; "
        f"6L close {out['close'].min():.5f}-{out['close'].max():.5f} "
        f"(usdbrl {out['usdbrl'].min():.3f}-{out['usdbrl'].max():.3f})")
    return len(out)


def main():
    log("=== VIX (daily, Yahoo ^VIX) ===")
    try:
        fetch_vix()
    except Exception as e:
        log(f"VIX FAILED: {e}")
    log("=== USDBRL (1m, AlgoSeek 6L) ===")
    try:
        fetch_brl()
    except Exception as e:
        log(f"BRL FAILED: {e}")
    log("done")


if __name__ == "__main__":
    main()
