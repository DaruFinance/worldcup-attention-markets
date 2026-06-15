#!/usr/bin/env python3
"""Breadth robustness: the during-match log-volume effect, instrument by instrument, across the full
universe now assembled  -  including rates (ZT/ZF/ZN/ZB), more commodities (SI/NG/HG), DIA, and the
country ETFs. If the null is real it should hold across ~29 instruments and 5+ asset classes.
Out: analysis/out/breadth.csv"""
import os, glob, warnings
warnings.simplefilter("ignore")
os.environ.setdefault("OPENBLAS_NUM_THREADS","1"); os.environ.setdefault("OMP_NUM_THREADS","1")
import numpy as np, pandas as pd
from pyfixest.estimation import feols
ROOT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"..")
FUT=os.path.join(ROOT,"data","market","futures"); EQ=os.path.join(ROOT,"data","market","equity")
MDIR=os.path.join(ROOT,"data","matches"); OUT=os.path.join(ROOT,"analysis","out")

def mset_win():
    a=pd.read_parquet(os.path.join(MDIR,"matches_all.parquet")); a=a[a.tournament.isin([2018,2022])]
    h=pd.read_parquet(os.path.join(MDIR,"matches_hist.parquet"))
    ko=pd.concat([pd.to_datetime(a.kickoff_utc,utc=True),pd.to_datetime(h.kickoff_utc,utc=True)])
    s=set()
    for k in ko: s.update(pd.date_range(k,k+pd.Timedelta(minutes=104),freq="1min"))
    w={}
    for t in (2010,2014,2018,2022):
        kt=ko[ko.dt.year==t]
        if len(kt): w[t]=(kt.min().normalize()-pd.Timedelta(days=21),kt.max().normalize()+pd.Timedelta(days=22))
    return s,w

def run(p, mins, wins, vol_col, rth):
    d=pd.read_parquet(p); d["ts"]=pd.to_datetime(d["ts"],utc=True).dt.floor("min")
    v=d[vol_col].astype(float); d["lvol"]=np.log(v.where(v>0))
    keep=pd.Series(False,index=d.index)
    for a,b in wins.values(): keep|=(d["ts"]>=a)&(d["ts"]<b)
    d=d[keep].copy()
    if rth:
        et=d["ts"].dt.tz_convert("America/New_York"); mod=et.dt.hour*60+et.dt.minute
        d=d[(mod>=570)&(mod<960)].copy()
    if len(d)<5000: return None
    d["match"]=d["ts"].isin(mins).astype(int)
    d["weekday"]=d["ts"].dt.weekday; d["mod"]=d["ts"].dt.hour*60+d["ts"].dt.minute
    d["wd_mod"]=d["weekday"].astype(str)+"_"+d["mod"].astype(str); d["date"]=d["ts"].dt.strftime("%Y-%m-%d")
    sub=d.dropna(subset=["lvol"]); sub=sub[np.isfinite(sub.lvol)]
    if sub.match.sum()<200: return None
    m=feols("lvol ~ match | wd_mod + date", data=sub, vcov={"CRV1":"date"}); r=m.tidy().loc["match"]
    return dict(coef=round(r["Estimate"],4),pct=round(np.expm1(r["Estimate"])*100,1),p=round(r["Pr(>|t|)"],3),n=int(m._N))

def main():
    mins,wins=mset_win()
    FUTI={"ES":"equity-idx","NQ":"equity-idx","YM":"equity-idx","RTY":"equity-idx",
          "GC":"metals","SI":"metals","HG":"metals","CL":"energy","NG":"energy",
          "6E":"FX","6B":"FX","6J":"FX","ZT":"rates","ZF":"rates","ZN":"rates","ZB":"rates"}
    EQI={"SPY":"US-cash","QQQ":"US-cash","IWM":"US-cash","DIA":"US-cash",
         "EWZ":"ctry-ETF","EWW":"ctry-ETF","EWU":"ctry-ETF","EWG":"ctry-ETF","EWQ":"ctry-ETF",
         "EWP":"ctry-ETF","EWJ":"ctry-ETF","EWY":"ctry-ETF","ARGT":"ctry-ETF"}
    rows=[]
    for inst,cls in FUTI.items():
        p=os.path.join(FUT,f"{inst}_1m.parquet")
        if os.path.exists(p):
            r=run(p,mins,wins,"volume",False)
            if r: rows.append(dict(instrument=inst,asset_class=cls,**r))
    for inst,cls in EQI.items():
        p=os.path.join(EQ,f"{inst}_1m.parquet")
        if os.path.exists(p):
            r=run(p,mins,wins,"volume",True)
            if r: rows.append(dict(instrument=inst,asset_class=cls,**r))
    res=pd.DataFrame(rows); res.to_csv(os.path.join(OUT,"breadth.csv"),index=False)
    print(res.to_string(index=False))
    n=len(res); sig=int((res.p<0.05).sum())
    print(f"\n{n} instruments across {res.asset_class.nunique()} asset classes. "
          f"nominally p<0.05: {sig} (expect {0.05*n:.1f}). median |effect|={res.pct.abs().median():.1f}%.")
    return res

if __name__=="__main__":
    main()
