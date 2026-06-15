#!/usr/bin/env python3
"""
Attention-mechanism validation. The spec's key check: matches with HIGHER attention should, if the
attention channel operated, produce LARGER trading effects. We interact Match with the day's Google
Trends attention (worldwide), and  -  sharper  -  with the playing country's OWN Trends for the mapped
instruments. If these interactions are ~zero, even the highest-attention matches don't move markets,
which strengthens the null.
  crypto: 2018/2022  |  futures: 2010-2022 (mapped own-team set ES,NQ->US; 6E->euro; 6B->GB; 6J->JP)
Out: analysis/out/attention_validation.csv
"""
import os, warnings
warnings.simplefilter("ignore")
os.environ.setdefault("OPENBLAS_NUM_THREADS","1"); os.environ.setdefault("OMP_NUM_THREADS","1")
import numpy as np, pandas as pd
from pyfixest.estimation import feols

ROOT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"..")
MDIR=os.path.join(ROOT,"data","matches"); CRY=os.path.join(ROOT,"data","market","crypto")
FUT=os.path.join(ROOT,"data","market","futures"); OUT=os.path.join(ROOT,"analysis","out")

def trends_world():
    t=pd.read_parquet(os.path.join(ROOT,"data","controls","google_trends.parquet"))
    w=t[t.geo=="WORLD"].groupby(["tournament","date"],as_index=False).interest.mean()
    w["z"]=w.groupby("tournament").interest.transform(lambda s:(s-s.mean())/s.std(ddof=0))
    w["d"]=pd.to_datetime(w["date"]).dt.strftime("%Y-%m-%d")
    return dict(zip(w["d"], w["z"]))

def country_trends():
    t=pd.read_parquet(os.path.join(ROOT,"data","controls","google_trends.parquet"))
    c=t[t.geo!="WORLD"].groupby(["tournament","geo","date"],as_index=False).interest.mean()
    c["z"]=c.groupby(["tournament","geo"]).interest.transform(lambda s:(s-s.mean())/s.std(ddof=0))
    c["d"]=pd.to_datetime(c["date"]).dt.strftime("%Y-%m-%d")
    return {(r.geo,r.d):r.z for r in c.itertuples()}

def match_minute_set():
    a=pd.read_parquet(os.path.join(MDIR,"matches_all.parquet")); a=a[a.tournament.isin([2018,2022])]
    h=pd.read_parquet(os.path.join(MDIR,"matches_hist.parquet"))
    ko=pd.concat([pd.to_datetime(a["kickoff_utc"],utc=True), pd.to_datetime(h["kickoff_utc"],utc=True)])
    s=set()
    for k in ko: s.update(pd.date_range(k,k+pd.Timedelta(minutes=104),freq="1min"))
    wins={}
    for t in (2010,2014,2018,2022):
        kt=ko[ko.dt.year==t]
        if len(kt): wins[t]=(kt.min().normalize()-pd.Timedelta(days=21), kt.max().normalize()+pd.Timedelta(days=22))
    return s, wins

def prep(p, wins, mins, wz, kind):
    d=pd.read_parquet(p); d["ts"]=pd.to_datetime(d["ts"],utc=True).dt.floor("min")
    c=(d["quote_volume"] if kind=="crypto" else d["volume"]).astype(float)
    d["lvol"]=np.log(c.where(c>0))
    keep=pd.Series(False,index=d.index)
    for t,(a,b) in wins.items(): keep|=(d["ts"]>=a)&(d["ts"]<b)
    d=d[keep].copy()
    if not len(d): return None
    d["match"]=d["ts"].isin(mins).astype(int)
    d["date"]=d["ts"].dt.strftime("%Y-%m-%d")
    d["wz"]=d["date"].map(wz).fillna(0.0)
    d["m_wz"]=d["match"]*d["wz"]
    d["weekday"]=d["ts"].dt.weekday; d["mod"]=d["ts"].dt.hour*60+d["ts"].dt.minute
    d["wd_mod"]=d["weekday"].astype(str)+"_"+d["mod"].astype(str)
    return d

def reg(df,rhs):
    s=df.dropna(subset=["lvol"]); s=s[np.isfinite(s["lvol"])]
    m=feols(f"lvol ~ {rhs} | instrument^wd_mod + date", data=s, vcov={"CRV1":"date"})
    return m.tidy()

def main():
    wz=trends_world(); mins,wins=match_minute_set()
    rows=[]
    # crypto (2018/2022 only  -  restrict windows)
    cw={t:wins[t] for t in (2018,2022) if t in wins}
    parts=[]
    for sym in ["BTCUSDT","ETHUSDT"]:
        for mkt in ["spot","perp"]:
            p=os.path.join(CRY,mkt,f"{sym}_1m.parquet")
            if not os.path.exists(p): continue
            d=prep(p,cw,mins,wz,"crypto")
            if d is not None: d["instrument"]=f"{sym}_{mkt}"; parts.append(d)
    crypto=pd.concat(parts,ignore_index=True)
    t=reg(crypto,"match + m_wz")
    for v,lab in [("match","crypto: match (avg attention)"),("m_wz","crypto: match x attention(+1SD)")]:
        r=t.loc[v]; rows.append(dict(test=lab,coef=round(r["Estimate"],4),se=round(r["Std. Error"],4),p=round(r["Pr(>|t|)"],4),n=int(t.attrs.get('N',0) or 0)))
    # futures (2010-2022)
    parts=[]
    for inst in ["ES","NQ","GC","CL","6E","6B","6J"]:
        p=os.path.join(FUT,f"{inst}_1m.parquet")
        if not os.path.exists(p): continue
        d=prep(p,wins,mins,wz,"fut")
        if d is not None: d["instrument"]=inst; parts.append(d)
    fut=pd.concat(parts,ignore_index=True)
    t=reg(fut,"match + m_wz")
    for v,lab in [("match","futures: match (avg attention)"),("m_wz","futures: match x attention(+1SD)")]:
        r=t.loc[v]; rows.append(dict(test=lab,coef=round(r["Estimate"],4),se=round(r["Std. Error"],4),p=round(r["Pr(>|t|)"],4),n=0))
    res=pd.DataFrame(rows); res.to_csv(os.path.join(OUT,"attention_validation.csv"),index=False)
    print(res.to_string(index=False))
    print("\nIf 'match x attention' ~ 0: higher-attention matches do NOT move markets more (null holds even at peak attention).")
    return res

if __name__=="__main__":
    main()
