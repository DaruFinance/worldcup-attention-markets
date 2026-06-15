#!/usr/bin/env python3
"""
Pull AlgoSeek TAQ (quote-bearing) 1-min bars for the H2 liquidity hypothesis  -  the historical
bid/ask, spread and order-flow that the trades-only products lack. Completed tournaments only
(2010/2014/2018/2022). Same windowed pattern as pull_futures_windows / pull_equity_windows.

  Futures: s3://us-futures-1min-taq-{yr}/{YYYYMMDD}/{ROOT}/{CONTRACT}.csv.gz   [profile 545]
  Equity : s3://us-equity-1min-taq-{yr}/{YYYYMMDD}/{LETTER}/{TICKER}.csv.gz    [profile 545]

NEVER kills anything; pure aws s3 cp. Resumable (skips existing). Out under data/market/taq_raw/.
"""
import os, subprocess
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd

ROOT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"..")
OUT=os.path.join(ROOT,"data","market","taq_raw"); MDIR=os.path.join(ROOT,"data","matches")
P545="algoseek_545933605308"
FUT_ROOTS=["ES","NQ","GC","CL","6E","6B","6J"]
EQ_TICK=["SPY","QQQ","IWM","EWZ","EWW","EWU","EWG","EWQ","EWP","EWJ","EWY"]
WORKERS=6
os.makedirs(OUT, exist_ok=True)

def log(m):
    from datetime import datetime, timezone
    print(f"[{datetime.now(timezone.utc):%H:%M:%S}] {m}", flush=True)

def window_dates():
    a=pd.read_parquet(os.path.join(MDIR,"matches_all.parquet")); a=a[a.tournament.isin([2018,2022])]
    h=pd.read_parquet(os.path.join(MDIR,"matches_hist.parquet"))
    ko=pd.concat([pd.to_datetime(a["kickoff_utc"],utc=True), pd.to_datetime(h["kickoff_utc"],utc=True)])
    df=pd.DataFrame({"ko":ko}); df["t"]=df["ko"].dt.year
    out=[]
    for _,g in df.groupby(df["ko"].dt.to_period("Y")):
        a0=g["ko"].min().normalize()-pd.Timedelta(days=14); b0=g["ko"].max().normalize()+pd.Timedelta(days=14)
        d=a0
        while d<=b0:
            out.append(d.strftime("%Y%m%d")); d+=timedelta(days=1)
    return sorted(set(out))

def cp_dir(uri, dst):
    if os.path.isdir(dst) and any(f.endswith(".csv.gz") for f in os.listdir(dst)): return "skip"
    os.makedirs(dst, exist_ok=True)
    r=subprocess.run(["aws","s3","cp",uri,dst+"/","--recursive","--quiet",
                      "--profile",P545,"--request-payer","requester"], capture_output=True, text=True)
    n=len([f for f in os.listdir(dst) if f.endswith(".csv.gz")])
    return f"ok({n})" if n else ("err" if r.returncode else "empty")

def cp_file(uri, dst):
    if os.path.exists(dst): return "skip"
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    r=subprocess.run(["aws","s3","cp",uri,dst,"--quiet","--profile",P545,"--request-payer","requester"],
                     capture_output=True, text=True)
    return "ok" if (r.returncode==0 and os.path.exists(dst)) else "miss"

def fut_task(t):
    date,root=t; yr=date[:4]
    return cp_dir(f"s3://us-futures-1min-taq-{yr}/{date}/{root}/", os.path.join(OUT,"futures",yr,date,root))

def eq_task(t):
    date,tk=t; yr=date[:4]
    return cp_file(f"s3://us-equity-1min-taq-{yr}/{date}/{tk[0]}/{tk}.csv.gz",
                   os.path.join(OUT,"equity",yr,date,f"{tk}.csv.gz"))

def run(name, tasks, fn):
    log(f"{name}: {len(tasks)} tasks"); ok=skip=other=0
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs=[ex.submit(fn,t) for t in tasks]
        for i,f in enumerate(as_completed(futs),1):
            st=f.result(); ok+=st.startswith("ok"); skip+=st=="skip"; other+=st in("empty","miss","err")
            if i%150==0: log(f"  {name} {i}/{len(tasks)} (ok={ok} skip={skip} empty/miss={other})")
    log(f"{name} DONE: ok={ok} skip={skip} empty/miss={other}")

if __name__=="__main__":
    dates=window_dates()
    log(f"TAQ liquidity pull: {len(dates)} window-dates (2010/2014/2018/2022)")
    run("futures-taq", [(d,r) for d in dates for r in FUT_ROOTS], fut_task)
    run("equity-taq",  [(d,tk) for d in dates for tk in EQ_TICK], eq_task)
    log("ALL TAQ LIQUIDITY DONE")
