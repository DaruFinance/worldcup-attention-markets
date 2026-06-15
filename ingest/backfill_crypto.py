#!/usr/bin/env python3
"""
Backfill Binance 1-min klines + funding from data.binance.vision (free, no key, no rate
cost). Spot BTC/ETH for all three tournaments; USDⓈ-M perp + funding where it exists
(perp launched 2019-09, so 2018 = spot only).

Klines already carry volume, quote_volume, TRADE COUNT, and taker-buy volume  -  so H1
(activity, avg trade size, order imbalance) and H3 (vol) need no separate aggTrades pull.

Output: data/market/crypto/{spot,perp}/{SYM}_1m.parquet  (concatenated, dedup, sorted)
        data/market/crypto/funding/{SYM}_funding.parquet
Resumable: caches raw zips under data/market/_cache_binance/.
"""
import os, io, sys, zipfile, calendar
from datetime import date, timedelta, datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
import urllib.request, urllib.error
import pandas as pd

ROOT  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
OUT   = os.path.join(ROOT, "data", "market", "crypto")
CACHE = os.path.join(ROOT, "data", "market", "_cache_binance")
BASE  = "https://data.binance.vision/data"
SYMS  = ["BTCUSDT", "ETHUSDT"]
WORKERS = 6

KCOLS = ["open_time","open","high","low","close","volume","close_time","quote_volume",
         "count","taker_buy_base","taker_buy_quote","ignore"]
FCOLS = ["calc_time","funding_interval_hours","last_funding_rate"]  # schema varies; handled

for d in (OUT, CACHE, os.path.join(OUT,"spot"), os.path.join(OUT,"perp"), os.path.join(OUT,"funding")):
    os.makedirs(d, exist_ok=True)

def log(m): print(f"[{datetime.now(timezone.utc):%H:%M:%S}] {m}", flush=True)

def months_between(y1,m1,y2,m2):
    out=[]; y,m=y1,m1
    while (y,m)<=(y2,m2):
        out.append((y,m)); m+=1
        if m>12: m=1; y+=1
    return out

# tournament windows (buffered ±~1 month for matched controls)
SPOT_MONTHS = months_between(2018,5,2018,8) + months_between(2022,10,2023,1) + months_between(2026,5,2026,6)
PERP_MONTHS = months_between(2022,10,2023,1) + months_between(2026,5,2026,6)

def fetch(url):
    """Return bytes or None (404)."""
    key = url.replace(BASE+"/","").replace("/","__")
    cp = os.path.join(CACHE, key)
    if os.path.exists(cp):
        with open(cp,"rb") as f: return f.read()
    try:
        req=urllib.request.Request(url, headers={"User-Agent":"wc-bf/1.0"})
        with urllib.request.urlopen(req, timeout=60) as r:
            b=r.read()
        with open(cp,"wb") as f: f.write(b)
        return b
    except urllib.error.HTTPError as e:
        if e.code==404: return None
        raise

def read_zip_csv(b, cols):
    with zipfile.ZipFile(io.BytesIO(b)) as z:
        name=z.namelist()[0]
        with z.open(name) as f:
            df=pd.read_csv(f, header=None)
    # binance recently added a header row in some files; detect
    if str(df.iloc[0,0]).lower() in ("open_time","calc_time"):
        df=df.iloc[1:].reset_index(drop=True)
    df=df.iloc[:, :len(cols)]
    df.columns=cols[:df.shape[1]]
    return df

def kline_url(market, sym, y, m, daily=None):
    seg = "spot" if market=="spot" else "futures/um"
    if daily:
        return f"{BASE}/{seg}/daily/klines/{sym}/1m/{sym}-1m-{daily}.zip"
    return f"{BASE}/{seg}/monthly/klines/{sym}/1m/{sym}-1m-{y:04d}-{m:02d}.zip"

def funding_url(sym, y, m):
    return f"{BASE}/futures/um/monthly/fundingRate/{sym}/{sym}-fundingRate-{y:04d}-{m:02d}.zip"

def get_klines(market, sym, y, m):
    """Monthly; if missing (incomplete current month), fall back to daily up to yesterday."""
    b=fetch(kline_url(market,sym,y,m))
    frames=[]
    if b is not None:
        frames.append(read_zip_csv(b, KCOLS))
    else:
        last_day = calendar.monthrange(y,m)[1]
        yest = (datetime.now(timezone.utc).date() - timedelta(days=1))
        d = date(y,m,1)
        while d.month==m and d<=yest:
            db=fetch(kline_url(market,sym,y,m,daily=d.isoformat()))
            if db is not None: frames.append(read_zip_csv(db, KCOLS))
            d+=timedelta(days=1)
    if not frames: return None
    df=pd.concat(frames, ignore_index=True)
    return df

def to_num(df, cols):
    for c in cols:
        if c in df: df[c]=pd.to_numeric(df[c], errors="coerce")
    return df

def epoch_to_ms(series):
    """Normalize a mixed epoch column (ms / us / ns) to milliseconds. For 2018-2026 the
    three units are cleanly 1000x apart with no overlap."""
    s=pd.to_numeric(series, errors="coerce")
    s=s.mask(s>1e17, s/1e6)            # ns  -> ms
    s=s.mask((s>1e14)&(s<=1e17), s/1e3)  # us -> ms
    return s

def build_market(market, months):
    for sym in SYMS:
        tasks=[]
        with ThreadPoolExecutor(max_workers=WORKERS) as ex:
            futs={ex.submit(get_klines, market, sym, y, m):(y,m) for (y,m) in months}
            for fu in as_completed(futs):
                ym=futs[fu]
                try:
                    df=fu.result()
                    if df is not None and len(df): tasks.append(df)
                except Exception as e:
                    log(f"  {market} {sym} {ym} err: {e}")
        if not tasks:
            log(f"{market} {sym}: no data"); continue
        df=pd.concat(tasks, ignore_index=True)
        df=to_num(df, ["open","high","low","close","volume","quote_volume","count",
                       "taker_buy_base","taker_buy_quote"])
        # open_time epoch (ms in older files, us in newer) -> normalize to ms
        df["ts"]=pd.to_datetime(epoch_to_ms(df["open_time"]), unit="ms", utc=True)
        df=df.dropna(subset=["ts","close"]).drop_duplicates("ts").sort_values("ts")
        keep=["ts","open","high","low","close","volume","quote_volume","count",
              "taker_buy_base","taker_buy_quote"]
        out=df[keep].reset_index(drop=True)
        p=os.path.join(OUT, market, f"{sym}_1m.parquet")
        out.to_parquet(p)
        log(f"{market} {sym}: {len(out):,} rows  {out['ts'].min()} .. {out['ts'].max()}  -> {p}")

def build_funding(months):
    for sym in SYMS:
        frames=[]
        for (y,m) in months:
            b=fetch(funding_url(sym,y,m))
            if b is None: continue
            df=read_zip_csv(b, ["calc_time","funding_interval_hours","last_funding_rate"])
            frames.append(df)
        if not frames:
            log(f"funding {sym}: none"); continue
        df=pd.concat(frames, ignore_index=True)
        df["ts"]=pd.to_datetime(epoch_to_ms(df["calc_time"]), unit="ms", utc=True)
        df["last_funding_rate"]=pd.to_numeric(df["last_funding_rate"], errors="coerce")
        out=df.dropna(subset=["ts"]).drop_duplicates("ts").sort_values("ts")[["ts","last_funding_rate","funding_interval_hours"]]
        p=os.path.join(OUT,"funding",f"{sym}_funding.parquet")
        out.to_parquet(p)
        log(f"funding {sym}: {len(out):,} rows -> {p}")

if __name__=="__main__":
    log(f"crypto backfill start  spot_months={len(SPOT_MONTHS)} perp_months={len(PERP_MONTHS)}")
    build_market("spot", SPOT_MONTHS)
    build_market("perp", PERP_MONTHS)
    build_funding(PERP_MONTHS)
    log("crypto backfill done")
