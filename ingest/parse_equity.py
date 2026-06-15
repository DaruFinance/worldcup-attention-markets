#!/usr/bin/env python3
"""Parse AlgoSeek US-equity 1-min (cash ETFs) -> per-ticker UTC parquet.
TimeBarStart is local Eastern; convert ET->UTC with DST via zoneinfo.
Schema: Date,Ticker,TimeBarStart,First,High,Low,Last,VWP,Volume,TotalTrades.
Out: data/market/equity/{TICKER}_1m.parquet [ts,open,high,low,close,volume,count]"""
import os, glob
from concurrent.futures import ProcessPoolExecutor
import numpy as np, pandas as pd

ROOT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"..")
RAW=os.path.join(ROOT,"data","market","equity_raw")
OUT=os.path.join(ROOT,"data","market","equity"); os.makedirs(OUT, exist_ok=True)
TICKERS=["SPY","QQQ","IWM","EWZ","EWW","EWU","EWG","EWQ","EWP","EWJ","ARGT","EWY"]
USE=["Date","TimeBarStart","FirstTradePrice","HighTradePrice","LowTradePrice",
     "LastTradePrice","Volume","TotalTrades"]

def log(m):
    from datetime import datetime, timezone
    print(f"[{datetime.now(timezone.utc):%H:%M:%S}] {m}", flush=True)

def parse_ticker(tk):
    files=sorted(glob.glob(os.path.join(RAW,"*","*",f"{tk}.csv.gz")))
    if not files: return tk,0
    frames=[]
    for f in files:
        try: d=pd.read_csv(f, usecols=USE)
        except Exception: continue
        if len(d): frames.append(d)
    if not frames: return tk,0
    d=pd.concat(frames, ignore_index=True)
    # ET local -> UTC
    naive=pd.to_datetime(d["Date"].astype(int).astype(str)+" "+d["TimeBarStart"],
                         format="%Y%m%d %H:%M")
    ts=naive.dt.tz_localize("America/New_York", ambiguous="NaT", nonexistent="NaT").dt.tz_convert("UTC")
    out=pd.DataFrame({
        "ts":ts, "open":d["FirstTradePrice"].astype(float), "high":d["HighTradePrice"].astype(float),
        "low":d["LowTradePrice"].astype(float), "close":d["LastTradePrice"].astype(float),
        "volume":d["Volume"].astype(float), "count":d["TotalTrades"].astype(float),
    }).dropna(subset=["ts","close"]).drop_duplicates("ts").sort_values("ts").reset_index(drop=True)
    out.to_parquet(os.path.join(OUT,f"{tk}_1m.parquet"))
    return tk, len(out)

def main():
    log(f"parsing {len(TICKERS)} equity tickers")
    with ProcessPoolExecutor(max_workers=4) as ex:
        for tk,n in ex.map(parse_ticker, TICKERS):
            log(f"  {tk}: {n:,} minute-bars")
    log("done")

if __name__=="__main__":
    main()
