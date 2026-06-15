#!/usr/bin/env python3
"""
Sharpest available proxy for the home-market distraction test. US-listed single-country ETFs measure
US trading of a country's exposure. We ask: does a country's ETF lose activity when ITS OWN team plays
(own_match), and  -  the mechanism check  -  does that effect scale with the COUNTRY'S OWN Google-Trends
attention on the day? Pooled across country ETFs, RTH only, 2010-2022, matched-control FE, clustered
by date. Distraction predicts own_match<0 and the own-attention interaction more negative.
Out: analysis/out/domestic_attention.csv
"""
import os, warnings
warnings.simplefilter("ignore")
os.environ.setdefault("OPENBLAS_NUM_THREADS","1"); os.environ.setdefault("OMP_NUM_THREADS","1")
import numpy as np, pandas as pd
from pyfixest.estimation import feols

ROOT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"..")
EQ=os.path.join(ROOT,"data","market","equity"); MDIR=os.path.join(ROOT,"data","matches")
OUT=os.path.join(ROOT,"analysis","out")
# ETF -> (team-name set, Trends geo)
ETF={"EWZ":({"Brazil"},"BR"),"EWW":({"Mexico"},"MX"),"EWU":({"England","Scotland"},"GB"),
     "EWG":({"Germany"},"DE"),"EWQ":({"France"},"FR"),"EWP":({"Spain"},"ES"),
     "EWJ":({"Japan"},"JP"),"ARGT":({"Argentina"},"AR"),"EWY":({"Korea Republic","South Korea"},None)}

def spine():
    a=pd.read_parquet(os.path.join(MDIR,"matches_all.parquet")); a=a[a.tournament.isin([2018,2022])]
    h=pd.read_parquet(os.path.join(MDIR,"matches_hist.parquet"))
    c=["tournament","kickoff_utc","played","home","away"]
    m=pd.concat([a[c],h[c]],ignore_index=True); m=m[m.played==True].copy()
    m["ko"]=pd.to_datetime(m["kickoff_utc"],utc=True); return m

def team_minutes(m, teams):
    s=set()
    for _,r in m.iterrows():
        if (r.home in teams) or (r.away in teams):
            s.update(pd.date_range(r.ko, r.ko+pd.Timedelta(minutes=104), freq="1min"))
    return s

def all_match_minutes(m):
    s=set()
    for _,r in m.iterrows(): s.update(pd.date_range(r.ko, r.ko+pd.Timedelta(minutes=104), freq="1min"))
    return s

def ctrends():
    t=pd.read_parquet(os.path.join(ROOT,"data","controls","google_trends.parquet"))
    c=t[t.geo!="WORLD"].groupby(["tournament","geo","date"],as_index=False).interest.mean()
    c["z"]=c.groupby(["tournament","geo"]).interest.transform(lambda s:(s-s.mean())/s.std(ddof=0))
    c["d"]=pd.to_datetime(c["date"]).dt.strftime("%Y-%m-%d")
    return {(r.geo,r.d):r.z for r in c.itertuples()}

def windows(m):
    w={}
    for t in (2010,2014,2018,2022):
        kt=m.loc[m.ko.dt.year==t,"ko"]
        if len(kt): w[t]=(kt.min().normalize()-pd.Timedelta(days=21), kt.max().normalize()+pd.Timedelta(days=22))
    return w

def main():
    m=spine(); allm=all_match_minutes(m); wins=windows(m); ct=ctrends()
    own_min={tk:team_minutes(m,teams) for tk,(teams,geo) in ETF.items()}
    parts=[]
    for tk,(teams,geo) in ETF.items():
        p=os.path.join(EQ,f"{tk}_1m.parquet")
        if not os.path.exists(p): continue
        d=pd.read_parquet(p); d["ts"]=pd.to_datetime(d["ts"],utc=True).dt.floor("min")
        v=d["volume"].astype(float); d["lvol"]=np.log(v.where(v>0))
        keep=pd.Series(False,index=d.index)
        for t,(a,b) in wins.items(): keep|=(d["ts"]>=a)&(d["ts"]<b)
        d=d[keep].copy()
        if not len(d): continue
        et=d["ts"].dt.tz_convert("America/New_York"); mod=et.dt.hour*60+et.dt.minute
        d=d[(mod>=570)&(mod<960)].copy()
        if not len(d): continue
        d["match"]=d["ts"].isin(allm).astype(int)
        d["own"]=d["ts"].isin(own_min[tk]).astype(int)
        d["own_match"]=d["own"]; d["foreign_match"]=((d["match"]==1)&(d["own"]==0)).astype(int)
        d["date"]=d["ts"].dt.strftime("%Y-%m-%d")
        d["otz"]=0.0
        if geo: d["otz"]=d["date"].map(lambda x: ct.get((geo,x),0.0))
        d["own_otz"]=d["own_match"]*d["otz"]
        d["weekday"]=d["ts"].dt.weekday; d["mm"]=mod
        d["wd_mod"]=d["weekday"].astype(str)+"_"+d["mm"].astype(str); d["instrument"]=tk
        parts.append(d[["ts","instrument","lvol","own_match","foreign_match","own_otz","date","wd_mod"]])
    panel=pd.concat(parts,ignore_index=True)
    own_days=panel.loc[panel.own_match==1,"date"].nunique()
    rows=[]
    # (1) own-team distraction (pooled country ETFs)
    m1=feols("lvol ~ foreign_match + own_match | instrument^wd_mod + date", data=panel.dropna(subset=["lvol"]), vcov={"CRV1":"date"})
    for v in ["foreign_match","own_match"]:
        r=m1.tidy().loc[v]; rows.append(dict(spec="own-team",term=v,coef=round(r["Estimate"],4),se=round(r["Std. Error"],4),p=round(r["Pr(>|t|)"],4)))
    # (2) own-team x own-country attention
    m2=feols("lvol ~ foreign_match + own_match + own_otz | instrument^wd_mod + date", data=panel.dropna(subset=["lvol"]), vcov={"CRV1":"date"})
    for v in ["own_match","own_otz"]:
        r=m2.tidy().loc[v]; rows.append(dict(spec="own-team x attention",term=v,coef=round(r["Estimate"],4),se=round(r["Std. Error"],4),p=round(r["Pr(>|t|)"],4)))
    res=pd.DataFrame(rows); res["own_match_days"]=own_days
    res.to_csv(os.path.join(OUT,"domestic_attention.csv"),index=False)
    print(res.to_string(index=False))
    print(f"\nown-country-ETF own-team RTH match-days: {own_days}")
    print("distraction => own_match<0 and own_otz (x own-country attention) more negative.")
    return res

if __name__=="__main__":
    main()
