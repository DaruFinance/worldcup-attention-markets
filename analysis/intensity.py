#!/usr/bin/env python3
"""
H8  -  match intensity. Does a closer match (by pre-match Elo) or a dramatic one (extra time /
penalties) amplify the during-match effect? Uses the new Elo-closeness + ET/penalty enrichment
(data/matches/elo_importance.parquet). Pooled index/FX/commodity futures, 4 completed tournaments
(2010/2014/2018/2022). Same matched-control FE; SE clustered by date.
Out: analysis/out/intensity.csv
"""
import os, warnings
warnings.simplefilter("ignore")
os.environ.setdefault("OPENBLAS_NUM_THREADS","1"); os.environ.setdefault("OMP_NUM_THREADS","1")
import numpy as np, pandas as pd
from pyfixest.estimation import feols

ROOT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"..")
FUT=os.path.join(ROOT,"data","market","futures"); MDIR=os.path.join(ROOT,"data","matches")
OUT=os.path.join(ROOT,"analysis","out")
INSTR=["ES","NQ","GC","CL","6E","6B","6J"]

def norm(t):
    a={"south korea":"korea republic","united states":"usa","ivory coast":"côte d'ivoire",
       "bosnia-herzegovina":"bosnia and herzegovina"}
    t=str(t).strip().lower(); return a.get(t,t)

def spine_with_elo():
    a=pd.read_parquet(os.path.join(MDIR,"matches_all.parquet")); a=a[a.tournament.isin([2018,2022])]
    h=pd.read_parquet(os.path.join(MDIR,"matches_hist.parquet"))
    c=["tournament","kickoff_utc","played","home","away"]
    m=pd.concat([a[c],h[c]],ignore_index=True); m=m[m.played==True].copy()
    m["ko"]=pd.to_datetime(m["kickoff_utc"],utc=True)
    m["k"]=m.apply(lambda r: (int(r.tournament), frozenset({norm(r.home),norm(r.away)})),axis=1)
    elo=pd.read_parquet(os.path.join(MDIR,"elo_importance.parquet"))
    elo["k"]=elo.apply(lambda r: (int(r.tournament), frozenset({norm(r.home),norm(r.away)})),axis=1)
    elo=elo.drop_duplicates("k")[["k","closeness","extra_time","penalties"]]
    m=m.merge(elo,on="k",how="left")
    # closeness = -strength_diff; z-score so higher = closer match
    m["closeness_z"]=(m["closeness"]-m["closeness"].mean())/m["closeness"].std()
    m["etpen"]=((m["extra_time"]==True)|(m["penalties"]==True)).astype(int)
    return m

def minute_features(m):
    rows=[]
    for _,r in m.iterrows():
        if pd.isna(r["closeness_z"]): continue
        mins=pd.date_range(r["ko"], r["ko"]+pd.Timedelta(minutes=104), freq="1min")
        for t in mins:
            rows.append((t, r["closeness_z"], r["etpen"]))
    f=pd.DataFrame(rows, columns=["ts","cz","etpen"])
    # collapse concurrent matches: closeness = max (closest in-progress), etpen = any
    g=f.groupby("ts").agg(cz=("cz","max"), etpen=("etpen","max")).reset_index()
    g["match"]=1
    return g

def windows(m):
    w={}
    for t,gg in m.groupby("tournament"):
        w[t]=(gg["ko"].min().normalize()-pd.Timedelta(days=21), gg["ko"].max().normalize()+pd.Timedelta(days=22))
    return w

def main():
    m=spine_with_elo(); feat=minute_features(m); wins=windows(m)
    parts=[]
    for inst in INSTR:
        p=os.path.join(FUT,f"{inst}_1m.parquet")
        if not os.path.exists(p): continue
        d=pd.read_parquet(p); d["ts"]=pd.to_datetime(d["ts"],utc=True).dt.floor("min")
        c=d["close"].astype(float); v=d["volume"].astype(float); n=d["count"].astype(float)
        d["lvol"]=np.log(v.where(v>0)); d["ltrades"]=np.log(n.where(n>0))
        d["ret"]=np.log(c/c.shift(1)); d["absret"]=d["ret"].abs()
        keep=pd.Series(False,index=d.index)
        for t,(a,b) in wins.items(): keep|=(d["ts"]>=a)&(d["ts"]<b)
        d=d[keep].copy()
        if not len(d): continue
        d=d.merge(feat,on="ts",how="left")
        d["match"]=d["match"].fillna(0).astype(int)
        d["cz"]=d["cz"].fillna(0.0); d["etpen"]=d["etpen"].fillna(0).astype(int)
        d["m_cz"]=d["match"]*d["cz"]; d["m_etpen"]=d["match"]*d["etpen"]
        d["weekday"]=d["ts"].dt.weekday; d["mod"]=d["ts"].dt.hour*60+d["ts"].dt.minute
        d["wd_mod"]=d["weekday"].astype(str)+"_"+d["mod"].astype(str)
        d["date"]=d["ts"].dt.strftime("%Y-%m-%d"); d["instrument"]=inst
        parts.append(d[["ts","instrument","lvol","ltrades","absret","match","m_cz","m_etpen","cz","etpen","wd_mod","date"]])
    panel=pd.concat(parts,ignore_index=True)
    close_days=panel.loc[panel.m_cz!=0,"date"].nunique(); etpen_days=panel.loc[panel.m_etpen==1,"date"].nunique()
    rows=[]
    for y in ["lvol","ltrades","absret"]:
        sub=panel.dropna(subset=[y]); sub=sub[np.isfinite(sub[y])]
        mm=feols(f"{y} ~ match + m_cz + m_etpen | instrument^wd_mod + date", data=sub, vcov={"CRV1":"date"})
        t=mm.tidy()
        for v,lab in [("match","match"),("m_cz","x closeness(+1SD)"),("m_etpen","x extra-time/penalties")]:
            if v in t.index:
                r=t.loc[v]; rows.append(dict(outcome=y,term=lab,coef=round(r["Estimate"],4),
                    se=round(r["Std. Error"],4),p=round(r["Pr(>|t|)"],4),n=int(mm._N)))
    res=pd.DataFrame(rows); res["close_match_days"]=close_days; res["etpen_days"]=etpen_days
    res.to_csv(os.path.join(OUT,"intensity.csv"),index=False)
    print(res.to_string(index=False))
    print(f"\nmatch-days with closeness data: {close_days} | ET/penalty match-days (futures-window): {etpen_days}")
    return res

if __name__=="__main__":
    main()
