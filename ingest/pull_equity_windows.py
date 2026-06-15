#!/usr/bin/env python3
"""Targeted AlgoSeek US-equity 1-min puller (cash ETFs) for the tournament windows.
Adds the CASH-EQUITY structural leg (the original literature's venue). Exact-file cp:
s3://us-equity-1min-trades-{yr}/{YYYYMMDD}/{LETTER}/{TICKER}.csv.gz
Out: data/market/equity_raw/{yr}/{YYYYMMDD}/{TICKER}.csv.gz  (resumable)."""
import os, subprocess
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd

ROOT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"..")
OUT=os.path.join(ROOT,"data","market","equity_raw")
MDIR=os.path.join(ROOT,"data","matches")
P545="algoseek_545933605308"
# broad US cash + country ETFs (teams present 2018/2022)
TICKERS=["SPY","QQQ","IWM","EWZ","EWW","EWU","EWG","EWQ","EWP","EWJ","ARGT","EWY"]
WORKERS=6
os.makedirs(OUT, exist_ok=True)

def log(m):
    from datetime import datetime, timezone
    print(f"[{datetime.now(timezone.utc):%H:%M:%S}] {m}", flush=True)

def window_dates():
    spine=os.environ.get("WC_SPINE","matches_all")
    m=pd.read_parquet(os.path.join(MDIR,f"{spine}.parquet"))
    m["ko"]=pd.to_datetime(m["kickoff_utc"], utc=True)
    today=pd.Timestamp.utcnow().normalize()
    dates=[]
    for t,g in m.groupby("tournament"):
        a=g["ko"].min().normalize()-pd.Timedelta(days=14)
        b=min(g["ko"].max().normalize()+pd.Timedelta(days=14), today-pd.Timedelta(days=1))
        d=a
        while d<=b:
            if d.weekday()<5:  # equities: weekdays only
                dates.append(d.strftime("%Y%m%d"))
            d+=timedelta(days=1)
    return dates

def cp_one(task):
    date,tk=task; yr=date[:4]
    dst_dir=os.path.join(OUT,yr,date); dst=os.path.join(dst_dir,f"{tk}.csv.gz")
    if os.path.exists(dst): return (date,tk,"skip")
    os.makedirs(dst_dir, exist_ok=True)
    uri=f"s3://us-equity-1min-trades-{yr}/{date}/{tk[0]}/{tk}.csv.gz"
    r=subprocess.run(["aws","s3","cp",uri,dst,"--profile",P545,
                      "--request-payer","requester","--only-show-errors"],
                     capture_output=True, text=True)
    if r.returncode!=0:
        # missing ticker/day (holiday) is fine
        return (date,tk,"miss")
    return (date,tk,"ok")

def main():
    dates=window_dates()
    tasks=[(d,tk) for d in dates for tk in TICKERS]
    log(f"equity pull: {len(dates)} weekdays x {len(TICKERS)} tickers = {len(tasks)} files")
    ok=miss=skip=0
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs=[ex.submit(cp_one,t) for t in tasks]
        for i,f in enumerate(as_completed(futs),1):
            _,_,st=f.result()
            ok+=st=="ok"; miss+=st=="miss"; skip+=st=="skip"
            if i%200==0: log(f"  {i}/{len(tasks)} (ok={ok} miss={miss} skip={skip})")
    log(f"DONE: ok={ok} miss={miss} skip={skip}")

if __name__=="__main__":
    main()
