#!/usr/bin/env python3
"""
Dukascopy FX SPOT 1-minute bar puller for the World Cup study.

The study currently uses CME FX FUTURES (6E/6B/6J). This adds the matching SPOT
pairs from Dukascopy's free tick archive, so spot vs futures can be compared.

Source layout (month is 0-INDEXED):
  https://datafeed.dukascopy.com/datafeed/{PAIR}/{YYYY}/{MM-1:02d}/{DD:02d}/{HH:02d}h_ticks.bi5
Each .bi5 = LZMA-compressed stream of 20-byte big-endian records:
  struct '>IIIff' = (time_ms_offset_within_hour, ask_int, bid_int, ask_vol, bid_vol)
Price = int / scale, scale per pair (5-digit -> 1e5, JPY 3-digit -> 1e3). Verified
by sanity-checking the level (EURUSD~1.17, USDJPY~110, USDMXN~20.5).

Volume here is TICK count (number of quotes), NOT traded volume -- labelled tick_count.

Windows: the four completed-tournament spans +/-14 days (2010, 2014, 2018, 2022),
derived from data/matches/matches_all.parquet (2018/2022) + matches_hist.parquet (2010/2014).
FX trades ~Sun 22:00 - Fri 22:00 UTC; we request every hour of every window date and
simply keep whatever ticks exist (weekend hours come back empty and are skipped).

Output: data/market/fx_spot/{PAIR}_1m.parquet  cols [ts, open, high, low, close, mid, tick_count]
  ts = minute-start UTC; open/high/low/close = bar mid-price OHLC; mid = close (kept for
  symmetry / explicitness); tick_count = #ticks in that minute.

Gentle: 6-worker thread pool, small per-file retries with backoff. Resumable via an
on-disk hour cache so a re-run does not re-download. Does NOT spawn daemons; the pull
itself may be backgrounded by the caller.
"""
import os, sys, time, lzma, struct, urllib.request, urllib.error
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
import numpy as np

ROOT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
OUT_DIR  = os.path.join(ROOT_DIR, "data", "market", "fx_spot")
CACHE    = os.path.join(ROOT_DIR, "data", "market", "_cache_dukascopy")
MDIR     = os.path.join(ROOT_DIR, "data", "matches")
LOGDIR   = os.path.join(ROOT_DIR, "logs")
os.makedirs(OUT_DIR, exist_ok=True)
os.makedirs(CACHE, exist_ok=True)
os.makedirs(LOGDIR, exist_ok=True)

BASE = "https://datafeed.dukascopy.com/datafeed"
UA   = {"User-Agent": "Mozilla/5.0 (research; 1m FX spot bars)"}

# pair -> price scale (int / scale = price). JPY crosses are 3-digit.
PAIRS = {
    "EURUSD": 1e5, "GBPUSD": 1e5, "USDJPY": 1e3, "USDCHF": 1e5,
    "USDCAD": 1e5, "AUDUSD": 1e5, "USDBRL": 1e5, "USDMXN": 1e5,
}
WORKERS = 6
RETRIES = 4

def log(m):
    line = f"[{datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S}Z] {m}"
    print(line, flush=True)
    with open(os.path.join(LOGDIR, "fx_spot_pull.log"), "a") as f:
        f.write(line + "\n")

# ---- window dates ----------------------------------------------------------
def tournament_windows():
    a = pd.read_parquet(os.path.join(MDIR, "matches_all.parquet"), columns=["tournament", "kickoff_utc"])
    h = pd.read_parquet(os.path.join(MDIR, "matches_hist.parquet"), columns=["tournament", "kickoff_utc"])
    df = pd.concat([a[a.tournament.isin([2018, 2022])], h], ignore_index=True)
    df["ko"] = pd.to_datetime(df["kickoff_utc"], utc=True)
    wins = {}
    for t, g in df.groupby("tournament"):
        lo = g.ko.min().normalize() - pd.Timedelta(days=14)
        hi = g.ko.max().normalize() + pd.Timedelta(days=14)
        wins[int(t)] = (lo, hi)
    return wins

def window_days(wins):
    days = []
    for t, (lo, hi) in sorted(wins.items()):
        d = lo
        while d <= hi:
            days.append((t, d.year, d.month, d.day))
            d += timedelta(days=1)
    return days

# ---- one .bi5 hour ---------------------------------------------------------
def fetch_hour(pair, y, mo, dd, hh):
    """Return decompressed bytes ('' if no ticks / weekend) or None on hard failure.
    Uses a tiny disk cache keyed by url so re-runs are cheap."""
    ck = os.path.join(CACHE, pair, f"{y}{mo:02d}{dd:02d}{hh:02d}.bin")
    if os.path.exists(ck):
        with open(ck, "rb") as f:
            return f.read()
    url = f"{BASE}/{pair}/{y}/{mo-1:02d}/{dd:02d}/{hh:02d}h_ticks.bi5"
    raw = None
    for k in range(RETRIES):
        try:
            req = urllib.request.Request(url, headers=UA)
            raw = urllib.request.urlopen(req, timeout=40).read()
            break
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raw = b""  # genuinely absent -> treat as empty
                break
            if k == RETRIES - 1:
                return None
            time.sleep(1.0 * (k + 1))
        except Exception:
            if k == RETRIES - 1:
                return None
            time.sleep(1.0 * (k + 1))
    if raw is None:
        return None
    data = b""
    if raw:
        try:
            data = lzma.decompress(raw)
        except lzma.LZMAError:
            data = b""
    os.makedirs(os.path.dirname(ck), exist_ok=True)
    with open(ck, "wb") as f:
        f.write(data)
    return data

def parse_hour(data, scale, hour_start_ms):
    """data -> list of (epoch_ms, mid). hour_start_ms = ms epoch at top of the hour."""
    out = []
    n = len(data) // 20
    if n == 0:
        return out
    for i in range(0, n * 20, 20):
        t, ask, bid, _av, _bv = struct.unpack(">IIIff", data[i:i+20])
        mid = (ask + bid) / 2.0 / scale
        out.append((hour_start_ms + t, mid))
    return out

# ---- per-pair pull + aggregate --------------------------------------------
def pull_pair(pair, days):
    scale = PAIRS[pair]
    tasks = []  # (y, mo, dd, hh, hour_start_ms)
    for (_t, y, mo, dd) in days:
        base_dt = datetime(y, mo, dd, tzinfo=timezone.utc)
        for hh in range(24):
            hsms = int((base_dt + timedelta(hours=hh)).timestamp() * 1000)
            tasks.append((y, mo, dd, hh, hsms))

    ticks = []  # (epoch_ms, mid)
    fail = empty = withdata = 0
    t0 = time.time()

    def work(task):
        y, mo, dd, hh, hsms = task
        data = fetch_hour(pair, y, mo, dd, hh)
        if data is None:
            return ("fail", None)
        if not data:
            return ("empty", None)
        return ("ok", parse_hour(data, scale, hsms))

    done = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = [ex.submit(work, t) for t in tasks]
        for f in as_completed(futs):
            st, recs = f.result()
            done += 1
            if st == "fail":
                fail += 1
            elif st == "empty":
                empty += 1
            else:
                withdata += 1
                ticks.extend(recs)
            if done % 300 == 0:
                log(f"  {pair}: {done}/{len(tasks)} hours (data={withdata} empty={empty} fail={fail}) ticks={len(ticks):,}")

    log(f"  {pair}: fetched {len(tasks)} hours in {time.time()-t0:.0f}s "
        f"(data={withdata} empty={empty} fail={fail}); aggregating {len(ticks):,} ticks")

    if not ticks:
        log(f"  {pair}: NO TICKS at all -> no parquet written")
        return {"pair": pair, "ticks": 0, "bars": 0, "fail": fail}

    df = pd.DataFrame(ticks, columns=["epoch_ms", "mid"])
    df["ts"] = pd.to_datetime(df["epoch_ms"], unit="ms", utc=True)
    df = df.sort_values("ts")
    df["minute"] = df["ts"].dt.floor("min")
    g = df.groupby("minute")
    bars = pd.DataFrame({
        "open":  g["mid"].first(),
        "high":  g["mid"].max(),
        "low":   g["mid"].min(),
        "close": g["mid"].last(),
        "tick_count": g["mid"].size().astype("int64"),
    }).reset_index().rename(columns={"minute": "ts"})
    bars["mid"] = bars["close"]
    bars = bars[["ts", "open", "high", "low", "close", "mid", "tick_count"]]
    bars = bars.sort_values("ts").reset_index(drop=True)

    outp = os.path.join(OUT_DIR, f"{pair}_1m.parquet")
    bars.to_parquet(outp, index=False)
    log(f"  {pair}: wrote {len(bars):,} 1m bars -> {outp} "
        f"(ts {bars.ts.min()} .. {bars.ts.max()})")
    return {"pair": pair, "ticks": len(df), "bars": len(bars), "fail": fail,
            "ts_min": bars.ts.min(), "ts_max": bars.ts.max()}

def main():
    only = sys.argv[1:] if len(sys.argv) > 1 else list(PAIRS.keys())
    wins = tournament_windows()
    log("tournament windows (+/-14d): " + "; ".join(
        f"{t}:{lo.date()}->{hi.date()}" for t, (lo, hi) in sorted(wins.items())))
    days = window_days(wins)
    log(f"total window days = {len(days)} ; pairs = {only}")
    results = []
    for pair in only:
        if pair not in PAIRS:
            log(f"  skip unknown pair {pair}")
            continue
        log(f"=== PULLING {pair} ===")
        results.append(pull_pair(pair, days))
    log("ALL DONE")
    for r in results:
        log(f"  result {r}")

if __name__ == "__main__":
    main()
