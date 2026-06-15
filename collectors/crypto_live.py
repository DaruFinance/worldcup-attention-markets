#!/usr/bin/env python3
"""
Perishable crypto live collector  -  World Cup attention-shock study.

Captures the crypto-market data that is UNRECOVERABLE after the fact (Binance does
not archive these): order-book depth, best bid/ask + sizes, open interest, funding /
mark / index, and forced liquidations. Everything else (1m klines, aggTrades, funding
history) is archived on data.binance.vision and is backfilled separately.

Design goals: run unattended for the full tournament (2026-06-11 .. 2026-07-19 + buffer)
on a SHARED box with negligible CPU. Single process, two daemon threads, every loop
wrapped so it can never die. Daily-rotated JSONL, UTC. Heartbeat file for hang detection.

Streams
  REST poller (every POLL_SEC):  per {perp,spot} x {BTCUSDT,ETHUSDT}
      depth(limit=50), bookTicker; perp also openInterest + premiumIndex(funding/mark/index)
  WS listener: wss !forceOrder@arr (all-market liquidations) -> filter BTC/ETH

Usage:  python3 crypto_live.py            # runs forever
        POLL_SEC=30 python3 crypto_live.py
"""
import os, sys, json, time, threading, traceback
from datetime import datetime, timezone
import urllib.request

OUT      = os.environ.get("WC_OUT", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "crypto_live"))
POLL_SEC = int(os.environ.get("POLL_SEC", "60"))
HEARTBEAT = os.path.join(OUT, "_heartbeat.json")
SYMBOLS  = ["BTCUSDT", "ETHUSDT"]
DEPTH_LIMIT = 50

FAPI = "https://fapi.binance.com"      # USDⓈ-M perpetual futures
SAPI = "https://api.binance.com"       # spot
WS   = "wss://fstream.binance.com/stream?streams=!forceOrder@arr"

os.makedirs(OUT, exist_ok=True)
_locks = {}
def _lock(stream):
    return _locks.setdefault(stream, threading.Lock())

def utcnow_ms():
    return int(time.time() * 1000)

def daystr():
    return datetime.now(timezone.utc).strftime("%Y%m%d")

def write(stream, obj):
    """Append one JSON row to the daily-rotated file for `stream`."""
    path = os.path.join(OUT, f"{stream}_{daystr()}.jsonl")
    line = json.dumps(obj, separators=(",", ":"))
    with _lock(stream):
        with open(path, "a") as f:
            f.write(line + "\n")

def get(url, timeout=8):
    req = urllib.request.Request(url, headers={"User-Agent": "wc-collector/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())

def log(msg):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    sys.stdout.write(f"[{ts}] {msg}\n"); sys.stdout.flush()

# ---------------------------------------------------------------- REST poller
def poll_once():
    ts = utcnow_ms()
    for sym in SYMBOLS:
        # ---- perp ----
        try:
            d = get(f"{FAPI}/fapi/v1/depth?symbol={sym}&limit={DEPTH_LIMIT}")
            write("depth", {"ts": ts, "sym": sym, "mkt": "perp",
                            "E": d.get("E"), "b": d["bids"], "a": d["asks"]})
        except Exception as e:
            log(f"perp depth {sym}: {e}")
        try:
            bt = get(f"{FAPI}/fapi/v1/ticker/bookTicker?symbol={sym}")
            write("book", {"ts": ts, "sym": sym, "mkt": "perp",
                           "bp": bt["bidPrice"], "bq": bt["bidQty"],
                           "ap": bt["askPrice"], "aq": bt["askQty"]})
        except Exception as e:
            log(f"perp book {sym}: {e}")
        try:
            oi = get(f"{FAPI}/fapi/v1/openInterest?symbol={sym}")
            write("oi", {"ts": ts, "sym": sym, "oi": oi["openInterest"]})
        except Exception as e:
            log(f"oi {sym}: {e}")
        try:
            pi = get(f"{FAPI}/fapi/v1/premiumIndex?symbol={sym}")
            write("funding", {"ts": ts, "sym": sym, "mark": pi["markPrice"],
                              "index": pi["indexPrice"], "fr": pi["lastFundingRate"],
                              "nextFundingTime": pi["nextFundingTime"]})
        except Exception as e:
            log(f"funding {sym}: {e}")
        # ---- spot ----
        try:
            d = get(f"{SAPI}/api/v3/depth?symbol={sym}&limit={DEPTH_LIMIT}")
            write("depth", {"ts": ts, "sym": sym, "mkt": "spot",
                            "b": d["bids"], "a": d["asks"]})
        except Exception as e:
            log(f"spot depth {sym}: {e}")
        try:
            bt = get(f"{SAPI}/api/v3/ticker/bookTicker?symbol={sym}")
            write("book", {"ts": ts, "sym": sym, "mkt": "spot",
                           "bp": bt["bidPrice"], "bq": bt["bidQty"],
                           "ap": bt["askPrice"], "aq": bt["askQty"]})
        except Exception as e:
            log(f"spot book {sym}: {e}")

def poller():
    while True:
        t0 = time.time()
        try:
            poll_once()
            with open(HEARTBEAT, "w") as f:
                json.dump({"ts": utcnow_ms(),
                           "iso": datetime.now(timezone.utc).isoformat(),
                           "poll_sec": POLL_SEC}, f)
        except Exception:
            log("poller cycle error:\n" + traceback.format_exc())
        time.sleep(max(1, POLL_SEC - (time.time() - t0)))

# ---------------------------------------------------------------- WS liquidations
def ws_listener():
    import websocket  # websocket-client
    keep = {s for s in SYMBOLS}
    def on_message(_, raw):
        try:
            msg = json.loads(raw)
            o = msg.get("data", {}).get("o", {})
            if o.get("s") in keep:
                write("liquidations", {"ts": o.get("T"), "sym": o["s"], "side": o["S"],
                                       "price": o["p"], "qty": o["q"], "avgPrice": o.get("ap"),
                                       "orderType": o.get("o"), "status": o.get("X")})
        except Exception:
            pass
    def on_error(_, e):
        log(f"ws error: {e}")
    def on_close(_, code, msg):
        log(f"ws closed code={code} msg={msg}")
    while True:
        try:
            ws = websocket.WebSocketApp(WS, on_message=on_message,
                                        on_error=on_error, on_close=on_close)
            ws.run_forever(ping_interval=180, ping_timeout=10)
        except Exception:
            log("ws crashed:\n" + traceback.format_exc())
        time.sleep(5)  # reconnect backoff

# ---------------------------------------------------------------- main
if __name__ == "__main__":
    log(f"crypto_live start  OUT={OUT}  POLL_SEC={POLL_SEC}  symbols={SYMBOLS}")
    threading.Thread(target=ws_listener, daemon=True).start()
    poller()  # main loop (blocks)
