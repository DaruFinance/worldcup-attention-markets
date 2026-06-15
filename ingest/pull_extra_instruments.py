#!/usr/bin/env python3
"""Pull extra AlgoSeek instruments for the WC windows into the SAME raw dirs the existing parsers read.
Equity: DIA. Futures: RTY,YM,SI,NG,HG,ZT,ZF,ZN,ZB,DX. Then re-parse. NEVER kills anything."""
import os, subprocess
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
ROOT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"..")
FOUT=os.path.join(ROOT,"data","market","futures_raw"); EOUT=os.path.join(ROOT,"data","market","equity_raw")
P545="algoseek_545933605308"; FROOTS=["RTY","YM","SI","NG","HG","ZT","ZF","ZN","ZB","DX"]; ETICK=["DIA"]; W=6
def wd():
    a=pd.read_parquet(ROOT+"/data/matches/matches_all.parquet"); a=a[a.tournament.isin([2018,2022])]
    h=pd.read_parquet(ROOT+"/data/matches/matches_hist.parquet")
    ko=pd.concat([pd.to_datetime(a.kickoff_utc,utc=True),pd.to_datetime(h.kickoff_utc,utc=True)])
    out=[]
    for t in (2010,2014,2018,2022):
        kt=ko[ko.dt.year==t]
        if not len(kt): continue
        d=kt.min().normalize()-pd.Timedelta(days=14); b=kt.max().normalize()+pd.Timedelta(days=14)
        while d<=b: out.append(d.strftime("%Y%m%d")); d+=timedelta(days=1)
    return sorted(set(out))
def fsync(t):
    date,root=t; yr=date[:4]; dst=os.path.join(FOUT,yr,date,root)
    if os.path.isdir(dst) and any(f.endswith(".csv.gz") for f in os.listdir(dst)): return "skip"
    os.makedirs(dst,exist_ok=True)
    subprocess.run(["aws","s3","cp",f"s3://us-futures-1min-trades-{yr}/{date}/{root}/",dst+"/","--recursive","--quiet","--profile",P545,"--request-payer","requester"],capture_output=True)
    return "ok" if any(f.endswith('.csv.gz') for f in os.listdir(dst)) else "empty"
def esync(t):
    date,tk=t; yr=date[:4]; dst=os.path.join(EOUT,yr,date); os.makedirs(dst,exist_ok=True); fn=os.path.join(dst,tk+".csv.gz")
    if os.path.exists(fn): return "skip"
    subprocess.run(["aws","s3","cp",f"s3://us-equity-1min-trades-{yr}/{date}/{tk[0]}/{tk}.csv.gz",fn,"--quiet","--profile",P545,"--request-payer","requester"],capture_output=True)
    return "ok" if os.path.exists(fn) else "miss"
if __name__=="__main__":
    dates=wd(); print(f"extra: {len(dates)} dates",flush=True)
    with ThreadPoolExecutor(max_workers=W) as ex:
        list(ex.map(fsync,[(d,r) for d in dates for r in FROOTS]))
        list(ex.map(esync,[(d,tk) for d in dates for tk in ETICK]))
    print("extra pull done",flush=True)
