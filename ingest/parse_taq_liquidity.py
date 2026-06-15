#!/usr/bin/env python3
"""
Parse AlgoSeek TAQ (quote-bearing) 1-min files into per-instrument LIQUIDITY series  -  the H2
data (quoted spread, depth, order-flow). Futures: front contract per day (max volume; back
contracts have absurd spreads). Equity: ET->UTC, time-weighted top-of-book spread.

Out: data/market/liquidity/{INSTRUMENT}_1m.parquet
     [ts, mid, spread, rel_spread_bps, depth, imbalance, vol]
"""
import os, glob, warnings
warnings.simplefilter("ignore")
from concurrent.futures import ProcessPoolExecutor
import numpy as np, pandas as pd

ROOT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"..")
FRAW=os.path.join(ROOT,"data","market","taq_raw","futures")
ERAW=os.path.join(ROOT,"data","market","taq_raw","equity")
OUT=os.path.join(ROOT,"data","market","liquidity"); os.makedirs(OUT, exist_ok=True)
FUT_ROOTS=["ES","NQ","GC","CL","6E","6B","6J"]
EQ_TICK=["SPY","QQQ","IWM","EWZ","EWW","EWU","EWG","EWQ","EWP","EWJ","EWY"]

def log(m):
    from datetime import datetime, timezone
    print(f"[{datetime.now(timezone.utc):%H:%M:%S}] {m}", flush=True)

FUT_COLS=["UTCDate","UTCTimeBarStart","CloseBidPrice","CloseBidSize","CloseAskPrice","CloseAskSize",
          "MinSpread","MaxSpread","BuyAggressorQuantity","SellAggressorQuantity","Volume"]

def parse_futures_root(root):
    files=sorted(glob.glob(os.path.join(FRAW,"*","*",root,"*.csv.gz")))
    if not files: return root,0
    daily={}
    for f in files:
        date=os.path.basename(os.path.dirname(os.path.dirname(f)))
        try: d=pd.read_csv(f, usecols=lambda c: c in FUT_COLS)
        except Exception: continue
        if not len(d): continue
        d["__c"]=os.path.basename(f).split(".")[0]
        daily.setdefault(date,[]).append(d)
    frames=[]
    for date,dfs in daily.items():
        best=max(dfs, key=lambda x: pd.to_numeric(x.get("Volume",0),errors="coerce").fillna(0).sum())
        frames.append(best)
    if not frames: return root,0
    d=pd.concat(frames, ignore_index=True)
    for c in ["CloseBidPrice","CloseAskPrice","CloseBidSize","CloseAskSize","MinSpread","MaxSpread",
              "BuyAggressorQuantity","SellAggressorQuantity","Volume"]:
        d[c]=pd.to_numeric(d.get(c),errors="coerce")
    ts=pd.to_datetime(d["UTCDate"].astype(int).astype(str)+" "+d["UTCTimeBarStart"],
                      format="%Y%m%d %H:%M", utc=True, errors="coerce")
    mid=(d["CloseBidPrice"]+d["CloseAskPrice"])/2
    spread=(d["CloseAskPrice"]-d["CloseBidPrice"])
    # guard: drop crazy spreads (back-contract artefacts that slipped through) > 2% of mid
    bad=(spread/mid)>0.02
    out=pd.DataFrame({
        "ts":ts, "mid":mid, "spread":spread.where(~bad),
        "rel_spread_bps":(spread/mid*1e4).where(~bad),
        "depth":(d["CloseBidSize"]+d["CloseAskSize"]),
        "imbalance":(d["BuyAggressorQuantity"]-d["SellAggressorQuantity"])/
                    (d["BuyAggressorQuantity"]+d["SellAggressorQuantity"]).replace(0,np.nan),
        "vol":d["Volume"],
    }).dropna(subset=["ts","mid"]).drop_duplicates("ts").sort_values("ts").reset_index(drop=True)
    out=out[out["spread"]>0]
    out.to_parquet(os.path.join(OUT,f"{root}_1m.parquet"))
    return root,len(out)

EQ_COLS=["Date","TimeBarStart","CloseBidPrice","CloseBidSize","CloseAskPrice","CloseAskSize",
         "MinSpread","TimeWeightBid","TimeWeightAsk","TradeAtBid","TradeAtAsk","Volume"]

def parse_equity_ticker(tk):
    files=sorted(glob.glob(os.path.join(ERAW,"*","*",f"{tk}.csv.gz")))
    if not files: return tk,0
    frames=[]
    for f in files:
        try: d=pd.read_csv(f, usecols=lambda c: c in EQ_COLS)
        except Exception: continue
        if len(d): frames.append(d)
    if not frames: return tk,0
    d=pd.concat(frames, ignore_index=True)
    for c in ["CloseBidPrice","CloseAskPrice","CloseBidSize","CloseAskSize","TimeWeightBid",
              "TimeWeightAsk","TradeAtBid","TradeAtAsk","Volume"]:
        d[c]=pd.to_numeric(d.get(c),errors="coerce")
    naive=pd.to_datetime(d["Date"].astype(int).astype(str)+" "+d["TimeBarStart"], format="%Y%m%d %H:%M", errors="coerce")
    ts=naive.dt.tz_localize("America/New_York", ambiguous="NaT", nonexistent="NaT").dt.tz_convert("UTC")
    twb=d["TimeWeightBid"]; twa=d["TimeWeightAsk"]
    mid=(twb+twa)/2; spread=(twa-twb)
    bad=(spread/mid)>0.02
    out=pd.DataFrame({
        "ts":ts, "mid":mid, "spread":spread.where(~bad),
        "rel_spread_bps":(spread/mid*1e4).where(~bad),
        "depth":(d["CloseBidSize"]+d["CloseAskSize"]),
        "imbalance":(d["TradeAtAsk"]-d["TradeAtBid"])/(d["TradeAtAsk"]+d["TradeAtBid"]).replace(0,np.nan),
        "vol":d["Volume"],
    }).dropna(subset=["ts","mid"]).drop_duplicates("ts").sort_values("ts").reset_index(drop=True)
    out=out[out["spread"]>0]
    out.to_parquet(os.path.join(OUT,f"{tk}_1m.parquet"))
    return tk,len(out)

def main():
    log("parsing futures TAQ liquidity")
    with ProcessPoolExecutor(max_workers=4) as ex:
        for r,n in ex.map(parse_futures_root, FUT_ROOTS): log(f"  {r}: {n:,} min-bars")
    log("parsing equity TAQ liquidity")
    with ProcessPoolExecutor(max_workers=4) as ex:
        for tk,n in ex.map(parse_equity_ticker, EQ_TICK): log(f"  {tk}: {n:,} min-bars")
    log("done")

if __name__=="__main__":
    main()
