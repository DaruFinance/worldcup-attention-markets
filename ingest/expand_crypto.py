#!/usr/bin/env python3
"""
Expand the crypto data beyond Binance BTC/ETH USDT (spot+perp). All sources free, no key.

Three additions (see handoffs/crypto_expand.md for coverage + honest limitations):

  1. Coinbase BTC/USD & ETH/USD SPOT 1-min candles  -> data/market/crypto_coinbase/{SYM}USD_1m.parquet
     Adds the *USD* (not USDT) pairs AND a second exchange (spec wants >=2). Coinbase Exchange
     REST `/products/{P}/candles?granularity=60` returns <=300 candles/req -> page in 5h chunks,
     back off on 429. 2018 + 2022 tournament windows (+-14d).

  2. Binance perp MARK + INDEX price 1-min klines (these ARE archived, unlike OI/liq) ->
     data/market/crypto/perp_mark/{SYM}_mark_1m.parquet, {SYM}_index_1m.parquet
     2022 window (perp era). Reuses the data.binance.vision zip-parsing pattern.

  3. Bybit BTCUSDT/ETHUSDT PERP 1-min klines (second perp exchange) -> data/market/crypto_bybit/{SYM}_1m.parquet
     via the free v5 kline API (category=linear, <=1000 candles/req). 2022 window.

NOT available free for history (only our live-2026 capture has them): order-book DEPTH,
LIQUIDATIONS. No exchange archives those historically -> not chased here.

Resumable: caches Binance zips under data/market/_cache_binance/ (shared with backfill_crypto.py).
"""
import os, io, sys, time, json, zipfile
from datetime import date, datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
import urllib.request, urllib.error
import pandas as pd

ROOT  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
CACHE = os.path.join(ROOT, "data", "market", "_cache_binance")
BASE  = "https://data.binance.vision/data"

CB_OUT    = os.path.join(ROOT, "data", "market", "crypto_coinbase")
MARK_OUT  = os.path.join(ROOT, "data", "market", "crypto", "perp_mark")
BYBIT_OUT = os.path.join(ROOT, "data", "market", "crypto_bybit")
for d in (CACHE, CB_OUT, MARK_OUT, BYBIT_OUT):
    os.makedirs(d, exist_ok=True)

def log(m): print(f"[{datetime.now(timezone.utc):%H:%M:%S}] {m}", flush=True)

# ---- tournament windows +-14d (UTC) ----------------------------------------
# 2018: matches 2018-06-14 .. 2018-07-15 ; 2022: 2022-11-20 .. 2022-12-18
WINDOWS = {
    "2018": (date(2018, 5, 31), date(2018, 7, 29)),
    "2022": (date(2022, 11,  6), date(2023, 1,  1)),
}

# =============================================================================
# 1. COINBASE spot BTC-USD / ETH-USD 1m candles (REST, paginate 5h chunks)
# =============================================================================
CB_BASE = "https://api.exchange.coinbase.com"
CB_COLS = ["time", "low", "high", "open", "close", "volume"]  # coinbase candle order

def cb_get(product, start_dt, end_dt, tries=6):
    """One <=300-candle request. Returns list of candle rows. Backs off on 429/5xx."""
    url = (f"{CB_BASE}/products/{product}/candles?granularity=60"
           f"&start={start_dt.strftime('%Y-%m-%dT%H:%M:%S')}"
           f"&end={end_dt.strftime('%Y-%m-%dT%H:%M:%S')}")
    delay = 0.5
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "wc-bf/1.0"})
            with urllib.request.urlopen(req, timeout=45) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(delay); delay = min(delay * 2, 20); continue
            raise
        except Exception:
            time.sleep(delay); delay = min(delay * 2, 20)
    log(f"  coinbase {product} {start_dt} gave up after {tries} tries")
    return []

def build_coinbase():
    for asset in ("BTC", "ETH"):
        product = f"{asset}-USD"
        rows = []
        for tag, (d0, d1) in WINDOWS.items():
            t = datetime(d0.year, d0.month, d0.day, tzinfo=timezone.utc)
            end = datetime(d1.year, d1.month, d1.day, tzinfo=timezone.utc)
            n_chunks = 0
            while t < end:
                chunk_end = min(t + timedelta(hours=5), end)
                # coinbase end is exclusive-ish; subtract 1s to stay <=300 candles
                data = cb_get(product, t, chunk_end - timedelta(seconds=1))
                if data:
                    rows.extend(data)
                n_chunks += 1
                t = chunk_end
                time.sleep(0.18)  # ~5-6 req/s, stay under public rate limit
            log(f"  coinbase {product} {tag}: {n_chunks} chunks, running rows={len(rows):,}")
        if not rows:
            log(f"coinbase {product}: NO DATA"); continue
        df = pd.DataFrame(rows, columns=CB_COLS)
        for c in CB_COLS:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        df["ts"] = pd.to_datetime(df["time"], unit="s", utc=True)
        out = (df.dropna(subset=["ts", "close"]).drop_duplicates("ts").sort_values("ts")
                 [["ts", "open", "high", "low", "close", "volume"]].reset_index(drop=True))
        p = os.path.join(CB_OUT, f"{asset}USD_1m.parquet")
        out.to_parquet(p)
        log(f"coinbase {product}: {len(out):,} rows  {out['ts'].min()} .. {out['ts'].max()}  -> {p}")

# =============================================================================
# 2. BINANCE perp MARK + INDEX price klines (data.binance.vision, zip)
# =============================================================================
SYMS = ["BTCUSDT", "ETHUSDT"]
KCOLS = ["open_time", "open", "high", "low", "close", "volume", "close_time",
         "quote_volume", "count", "taker_buy_base", "taker_buy_quote", "ignore"]
PERP_MONTHS = [(2022, 11), (2022, 12), (2023, 1)]  # 2022 window months

def fetch(url):
    key = url.replace(BASE + "/", "").replace("/", "__")
    cp = os.path.join(CACHE, key)
    if os.path.exists(cp):
        with open(cp, "rb") as f: return f.read()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "wc-bf/1.0"})
        with urllib.request.urlopen(req, timeout=90) as r:
            b = r.read()
        with open(cp, "wb") as f: f.write(b)
        return b
    except urllib.error.HTTPError as e:
        if e.code == 404: return None
        raise

def read_zip_csv(b, cols):
    with zipfile.ZipFile(io.BytesIO(b)) as z:
        name = z.namelist()[0]
        df = pd.read_csv(z.open(name), header=None)
    if str(df.iloc[0, 0]).lower() in ("open_time", "calc_time"):
        df = df.iloc[1:].reset_index(drop=True)
    df = df.iloc[:, :len(cols)]
    df.columns = cols[:df.shape[1]]
    return df

def epoch_to_ms(series):
    s = pd.to_numeric(series, errors="coerce")
    s = s.mask(s > 1e17, s / 1e6)
    s = s.mask((s > 1e14) & (s <= 1e17), s / 1e3)
    return s

def mark_url(kind, sym, y, m):
    # kind in {"markPriceKlines","indexPriceKlines"}
    return f"{BASE}/futures/um/monthly/{kind}/{sym}/1m/{sym}-1m-{y:04d}-{m:02d}.zip"

def build_mark_index():
    for kind, suffix in (("markPriceKlines", "mark"), ("indexPriceKlines", "index")):
        for sym in SYMS:
            frames = []
            for (y, m) in PERP_MONTHS:
                b = fetch(mark_url(kind, sym, y, m))
                if b is None:
                    log(f"  {suffix} {sym} {y}-{m:02d}: 404"); continue
                frames.append(read_zip_csv(b, KCOLS))
            if not frames:
                log(f"{suffix} {sym}: no data"); continue
            df = pd.concat(frames, ignore_index=True)
            for c in ("open", "high", "low", "close"):
                df[c] = pd.to_numeric(df[c], errors="coerce")
            df["ts"] = pd.to_datetime(epoch_to_ms(df["open_time"]), unit="ms", utc=True)
            out = (df.dropna(subset=["ts", "close"]).drop_duplicates("ts").sort_values("ts")
                     [["ts", "open", "high", "low", "close"]].reset_index(drop=True))
            p = os.path.join(MARK_OUT, f"{sym}_{suffix}_1m.parquet")
            out.to_parquet(p)
            log(f"{suffix} {sym}: {len(out):,} rows  {out['ts'].min()} .. {out['ts'].max()}  -> {p}")

# =============================================================================
# 3. BYBIT perp BTCUSDT/ETHUSDT 1m klines (v5 API, category=linear)
# =============================================================================
BYBIT_BASE = "https://api.bybit.com"
BYBIT_COLS = ["start", "open", "high", "low", "close", "volume", "turnover"]

def bybit_get(symbol, start_ms, end_ms, tries=6):
    url = (f"{BYBIT_BASE}/v5/market/kline?category=linear&symbol={symbol}"
           f"&interval=1&start={start_ms}&end={end_ms}&limit=1000")
    delay = 0.5
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "wc-bf/1.0"})
            with urllib.request.urlopen(req, timeout=45) as r:
                d = json.loads(r.read())
            if d.get("retCode") == 0:
                return d["result"]["list"]
            time.sleep(delay); delay = min(delay * 2, 20)
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(delay); delay = min(delay * 2, 20); continue
            raise
        except Exception:
            time.sleep(delay); delay = min(delay * 2, 20)
    log(f"  bybit {symbol} {start_ms} gave up"); return []

def build_bybit():
    reachable = True
    for sym in SYMS:
        rows = []
        for tag, (d0, d1) in WINDOWS.items():
            if tag == "2018":
                continue  # bybit linear perp didn't exist in 2018
            t0 = int(datetime(d0.year, d0.month, d0.day, tzinfo=timezone.utc).timestamp() * 1000)
            t1 = int(datetime(d1.year, d1.month, d1.day, tzinfo=timezone.utc).timestamp() * 1000)
            step = 1000 * 60 * 1000  # 1000 minutes per request
            t = t0
            while t < t1:
                end = min(t + step, t1)
                lst = bybit_get(sym, t, end)
                if not lst and t == t0:
                    reachable = False
                rows.extend(lst)
                t = end
                time.sleep(0.12)
            log(f"  bybit {sym} {tag}: running rows={len(rows):,}")
        if not rows:
            log(f"bybit {sym}: NO DATA (source not reachable free?)"); continue
        df = pd.DataFrame(rows, columns=BYBIT_COLS)
        for c in BYBIT_COLS:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        df["ts"] = pd.to_datetime(df["start"], unit="ms", utc=True)
        out = (df.dropna(subset=["ts", "close"]).drop_duplicates("ts").sort_values("ts")
                 [["ts", "open", "high", "low", "close", "volume", "turnover"]].reset_index(drop=True))
        p = os.path.join(BYBIT_OUT, f"{sym}_1m.parquet")
        out.to_parquet(p)
        log(f"bybit {sym}: {len(out):,} rows  {out['ts'].min()} .. {out['ts'].max()}  -> {p}")
    return reachable

if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    log(f"crypto expand start  (target={which})")
    if which in ("all", "coinbase"):
        build_coinbase()
    if which in ("all", "mark"):
        build_mark_index()
    if which in ("all", "bybit"):
        build_bybit()
    log("crypto expand done")
