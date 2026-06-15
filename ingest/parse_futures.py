#!/usr/bin/env python3
"""
Parse raw AlgoSeek futures (per-contract daily csv.gz) into continuous front-contract
1-min series per root. Front = contract with max daily TotalQuantity (rolls automatically).

Out: data/market/futures/{ROOT}_1m.parquet  [ts, open, high, low, close, volume, count, buy, sell]
     volume = contracts (TotalQuantity), count = TotalTradeCount.
"""
import os, glob, gzip
from concurrent.futures import ProcessPoolExecutor
import numpy as np, pandas as pd

ROOT_DIR=os.path.join(os.path.dirname(os.path.abspath(__file__)),"..")
RAW=os.path.join(ROOT_DIR,"data","market","futures_raw")
OUT=os.path.join(ROOT_DIR,"data","market","futures")
os.makedirs(OUT, exist_ok=True)
ROOTS=["ES","NQ","GC","CL","6E","6B","6J"]
USE=["UTCDate","UTCTimeBarStart","OpenPrice","HighPrice","LowPrice","ClosePrice",
     "TotalQuantity","BuyQuantity","SellQuantity","TotalTradeCount"]

def log(m):
    from datetime import datetime, timezone
    print(f"[{datetime.now(timezone.utc):%H:%M:%S}] {m}", flush=True)

def parse_root(root):
    files=sorted(glob.glob(os.path.join(RAW,"*","*",root,"*.csv.gz")))
    if not files: return root,0
    daily={}   # date -> list of (contract, df)
    for f in files:
        date=os.path.basename(os.path.dirname(os.path.dirname(f)))
        try:
            df=pd.read_csv(f, usecols=USE)
        except Exception:
            continue
        if not len(df): continue
        df["contract"]=os.path.basename(f).split(".")[0]
        daily.setdefault(date,[]).append(df)
    frames=[]
    for date,dfs in daily.items():
        # pick front = contract with max total quantity that day
        best=max(dfs, key=lambda d: d["TotalQuantity"].sum())
        frames.append(best)
    if not frames: return root,0
    d=pd.concat(frames, ignore_index=True)
    # build UTC ts from UTCDate (YYYYMMDD) + UTCTimeBarStart (HH:MM)
    ts=pd.to_datetime(d["UTCDate"].astype(int).astype(str)+" "+d["UTCTimeBarStart"],
                      format="%Y%m%d %H:%M", utc=True)
    out=pd.DataFrame({
        "ts":ts, "open":d["OpenPrice"].astype(float), "high":d["HighPrice"].astype(float),
        "low":d["LowPrice"].astype(float), "close":d["ClosePrice"].astype(float),
        "volume":d["TotalQuantity"].astype(float), "count":d["TotalTradeCount"].astype(float),
        "buy":d["BuyQuantity"].astype(float), "sell":d["SellQuantity"].astype(float),
    }).dropna(subset=["ts","close"]).drop_duplicates("ts").sort_values("ts").reset_index(drop=True)
    out.to_parquet(os.path.join(OUT,f"{root}_1m.parquet"))
    return root, len(out)

def main():
    log(f"parsing {len(ROOTS)} roots")
    # modest parallelism (4) to respect shared box
    with ProcessPoolExecutor(max_workers=4) as ex:
        for root,n in ex.map(parse_root, ROOTS):
            log(f"  {root}: {n:,} minute-bars")
    log("done")

if __name__=="__main__":
    main()
