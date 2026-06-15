#!/usr/bin/env python3
"""
Targeted AlgoSeek futures puller: only the tournament-window dates (span ±14d) for a
small root set  -  keeps it cheap/fast vs full-history. Files are ~30KB/contract/day.
Layout: s3://us-futures-1min-trades-{yr}/{YYYYMMDD}/{ROOT}/{CONTRACT}.csv.gz
Gentle on the origin (6 workers; memory: ~5-6 RPS ceiling, concurrency crashes it).

Out: data/market/futures_raw/{yr}/{YYYYMMDD}/{ROOT}/*.csv.gz   (resumable; skips existing)
"""
import os, subprocess, sys
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd

ROOT_DIR=os.path.join(os.path.dirname(os.path.abspath(__file__)),"..")
OUT=os.path.join(ROOT_DIR,"data","market","futures_raw")
MDIR=os.path.join(ROOT_DIR,"data","matches")
P545="algoseek_545933605308"
ROOTS=["ES","NQ","GC","CL","6E","6B","6J"]
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
            dates.append((int(t), d.strftime("%Y%m%d"))); d+=timedelta(days=1)
    return dates

def sync_one(task):
    yr_int, date, root = task
    yr=date[:4]
    bk=f"us-futures-1min-trades-{yr}"
    dst=os.path.join(OUT, yr, date, root)
    # resume: skip if dir already has files
    if os.path.isdir(dst) and any(f.endswith(".csv.gz") for f in os.listdir(dst)):
        return (date, root, "skip")
    os.makedirs(dst, exist_ok=True)
    cmd=["aws","s3","sync",f"s3://{bk}/{date}/{root}/", dst+"/",
         "--profile",P545,"--request-payer","requester","--only-show-errors"]
    r=subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode!=0:
        return (date, root, "ERR "+r.stderr.strip()[:60])
    n=len([f for f in os.listdir(dst) if f.endswith(".csv.gz")])
    return (date, root, f"ok({n})" if n else "empty")

def main():
    dates=window_dates()
    tasks=[(yr,d,r) for (yr,d) in dates for r in ROOTS]
    log(f"futures pull: {len(dates)} dates x {len(ROOTS)} roots = {len(tasks)} day-root syncs")
    done=err=skip=empty=0
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs=[ex.submit(sync_one,t) for t in tasks]
        for f in as_completed(futs):
            date,root,st=f.result(); done+=1
            if st.startswith("ERR"): err+=1; log(f"  {date} {root}: {st}")
            elif st=="skip": skip+=1
            elif st=="empty": empty+=1
            if done%100==0: log(f"  {done}/{len(tasks)} (err={err} skip={skip} empty={empty})")
    log(f"DONE: {done} syncs, err={err}, skip={skip}, empty={empty}")

if __name__=="__main__":
    main()
