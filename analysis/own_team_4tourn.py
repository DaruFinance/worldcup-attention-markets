#!/usr/bin/env python3
"""
Power extension of H6 (own-team effect) to FOUR tournaments (2010, 2014, 2018, 2022) using
the index/FX futures that exist back to 2007  -  the same pooled-DiD spec as pooled_domestic.py,
now with ~2x the treated own-team match-days. Crypto cannot extend (didn't exist), so this is
reported as a power-enhanced robustness for H6, not a change to the symmetric cross-market core.

Instruments & own-team mapping (same as core): ES,NQ -> USA; 6E -> euro-area; 6B -> GB; 6J -> Japan.
Out: analysis/out/own_team_4tourn.csv
"""
import os, warnings
warnings.simplefilter("ignore")
os.environ.setdefault("OPENBLAS_NUM_THREADS","1"); os.environ.setdefault("OMP_NUM_THREADS","1")
import numpy as np, pandas as pd
from pyfixest.estimation import feols

ROOT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"..")
FUT=os.path.join(ROOT,"data","market","futures"); MDIR=os.path.join(ROOT,"data","matches")
OUT=os.path.join(ROOT,"analysis","out")
OWN={"ES":"usa","NQ":"usa","6E":"euro","6B":"gbp","6J":"jpy"}

def combined_spine():
    a=pd.read_parquet(os.path.join(MDIR,"matches_all.parquet"))
    a=a[a["tournament"].isin([2018,2022])]
    h=pd.read_parquet(os.path.join(MDIR,"matches_hist.parquet"))
    cols=["tournament","kickoff_utc","played","usa_playing","euro_playing","gbp_playing","jpy_playing"]
    m=pd.concat([a[cols],h[cols]],ignore_index=True)
    m["ko"]=pd.to_datetime(m["kickoff_utc"],utc=True)
    return m[m["played"]==True]

def minute_sets(m):
    """match-in-progress minute set + per-flag minute sets, all 4 tournaments."""
    dur=104
    allm=set(); flags={f:set() for f in ["usa","euro","gbp","jpy"]}
    fmap={"usa":"usa_playing","euro":"euro_playing","gbp":"gbp_playing","jpy":"jpy_playing"}
    for _,r in m.iterrows():
        mins=pd.date_range(r["ko"], r["ko"]+pd.Timedelta(minutes=dur), freq="1min")
        allm.update(mins)
        for f,col in fmap.items():
            if r[col]: flags[f].update(mins)
    return allm, flags

def windows(m):
    w={}
    for t,g in m.groupby("tournament"):
        w[t]=(g["ko"].min().normalize()-pd.Timedelta(days=21), g["ko"].max().normalize()+pd.Timedelta(days=22))
    return w

def main():
    m=combined_spine(); allm,flags=minute_sets(m); wins=windows(m)
    parts=[]
    for inst,flag in OWN.items():
        p=os.path.join(FUT,f"{inst}_1m.parquet")
        if not os.path.exists(p): print("missing",inst); continue
        d=pd.read_parquet(p); d["ts"]=pd.to_datetime(d["ts"],utc=True).dt.floor("min")
        c=d["close"].astype(float); v=d["volume"].astype(float); n=d["count"].astype(float)
        d["lvol"]=np.log(v.where(v>0)); d["ltrades"]=np.log(n.where(n>0))
        keep=pd.Series(False,index=d.index); d["tournament"]=pd.NA
        for t,(a,b) in wins.items():
            mt=(d["ts"]>=a)&(d["ts"]<b); d.loc[mt,"tournament"]=t; keep|=mt
        d=d[keep].copy()
        if not len(d): continue
        d["match"]=d["ts"].isin(allm).astype(int)
        d["own_flagmin"]=d["ts"].isin(flags[flag]).astype(int)
        d["own_match"]=(d["match"]*d["own_flagmin"]).astype(int)
        d["foreign_match"]=(d["match"]*(1-d["own_flagmin"])).astype(int)
        d["weekday"]=d["ts"].dt.weekday; d["mod"]=d["ts"].dt.hour*60+d["ts"].dt.minute
        d["wd_mod"]=d["weekday"].astype(str)+"_"+d["mod"].astype(str)
        d["date"]=d["ts"].dt.strftime("%Y-%m-%d"); d["instrument"]=inst
        parts.append(d[["ts","instrument","tournament","lvol","ltrades","match","own_match","foreign_match","wd_mod","date"]])
    panel=pd.concat(parts,ignore_index=True)
    own_days=panel.loc[panel.own_match==1,"date"].nunique()
    rows=[]
    for y in ["lvol","ltrades"]:
        sub=panel.dropna(subset=[y]); sub=sub[np.isfinite(sub[y])]
        mm=feols(f"{y} ~ foreign_match + own_match | instrument^wd_mod + date", data=sub, vcov={"CRV1":"date"})
        t=mm.tidy()
        for v in ["foreign_match","own_match"]:
            r=t.loc[v]; rows.append(dict(outcome=y,term=v,coef=round(r["Estimate"],4),
                se=round(r["Std. Error"],4),p=round(r["Pr(>|t|)"],4),
                pct=round(np.expm1(r["Estimate"])*100,2),n=int(mm._N)))
    res=pd.DataFrame(rows); res["own_treated_dates"]=own_days
    res.to_csv(os.path.join(OUT,"own_team_4tourn.csv"),index=False)
    se=res.loc[(res.outcome=="lvol")&(res.term=="own_match"),"se"].values[0]
    mde=np.expm1(2.8*se)*100
    print(res.to_string(index=False))
    print(f"\nown-team treated date-clusters (4 tournaments): {own_days}  (was 28 in 2018+2022)")
    print(f"own_match lvol MDE (2.8*SE, exp) = {mde:.1f}%  (was ~23%)")
    return res

if __name__=="__main__":
    main()
