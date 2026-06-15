#!/usr/bin/env python3
"""
Triple-difference: does the own-team effect strengthen in high-importance (knockout) matches?

Pool the mapped index/FX futures (ES,NQ -> USA; 6E -> euro-area; 6B -> GB; 6J -> Japan) over the
four completed tournaments (2010,2014,2018,2022), built from the combined 4-tournament spine
(concat(matches_all[2018,2022], matches_hist[2010,2014])).

Per instrument-minute indicators:
  match  = any match in progress       (minute in [kickoff, kickoff+105min) of ANY played match)
  own    = own national team playing   (minute in an own-team match's match-in-progress window)
  knock  = a knockout match in progress

Spec (DDD):
  lvol ~ match + match:own + match:knock + match:own:knock | instrument^wd_mod + date
  SE clustered by date.

The match:own:knock term is the triple-difference: the extra own-team volume response that
appears specifically in knockout matches. It is likely UNDERPOWERED (few own-team knockout
match-days); we report the cluster count of own-team-knockout treated date-clusters so the
reader can weight it accordingly.

Out: analysis/out/triple_diff.csv
"""
import os, warnings
warnings.simplefilter("ignore")
os.environ.setdefault("OPENBLAS_NUM_THREADS","1"); os.environ.setdefault("OMP_NUM_THREADS","1")
import numpy as np, pandas as pd
from pyfixest.estimation import feols

ROOT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"..")
FUT=os.path.join(ROOT,"data","market","futures"); MDIR=os.path.join(ROOT,"data","matches")
OUT=os.path.join(ROOT,"analysis","out"); os.makedirs(OUT,exist_ok=True)
OWN={"ES":"usa","NQ":"usa","6E":"euro","6B":"gbp","6J":"jpy"}

def combined_spine():
    a=pd.read_parquet(os.path.join(MDIR,"matches_all.parquet"))
    a=a[a["tournament"].isin([2018,2022])]
    h=pd.read_parquet(os.path.join(MDIR,"matches_hist.parquet"))
    cols=["tournament","kickoff_utc","played","knockout",
          "usa_playing","euro_playing","gbp_playing","jpy_playing"]
    m=pd.concat([a[cols],h[cols]],ignore_index=True)
    m["ko"]=pd.to_datetime(m["kickoff_utc"],utc=True)
    return m[m["played"]==True].copy()

def minute_sets(m):
    """match-in-progress minute set, per-own-flag minute sets, and knockout minute set."""
    dur=104  # [kickoff, kickoff+105min) -> 105 one-minute bins inclusive of kickoff+104
    allm=set(); knock=set(); flags={f:set() for f in ["usa","euro","gbp","jpy"]}
    fmap={"usa":"usa_playing","euro":"euro_playing","gbp":"gbp_playing","jpy":"jpy_playing"}
    for _,r in m.iterrows():
        mins=pd.date_range(r["ko"], r["ko"]+pd.Timedelta(minutes=dur), freq="1min")
        allm.update(mins)
        if bool(r["knockout"]): knock.update(mins)
        for f,col in fmap.items():
            if r[col]: flags[f].update(mins)
    return allm, flags, knock

def windows(m):
    w={}
    for t,g in m.groupby("tournament"):
        w[t]=(g["ko"].min().normalize()-pd.Timedelta(days=21), g["ko"].max().normalize()+pd.Timedelta(days=22))
    return w

def main():
    m=combined_spine(); allm,flags,knock=minute_sets(m); wins=windows(m)
    parts=[]
    for inst,flag in OWN.items():
        p=os.path.join(FUT,f"{inst}_1m.parquet")
        if not os.path.exists(p): print("missing",inst); continue
        d=pd.read_parquet(p); d["ts"]=pd.to_datetime(d["ts"],utc=True).dt.floor("min")
        v=d["volume"].astype(float)
        d["lvol"]=np.log(v.where(v>0))
        keep=pd.Series(False,index=d.index); d["tournament"]=pd.NA
        for t,(a,b) in wins.items():
            mt=(d["ts"]>=a)&(d["ts"]<b); d.loc[mt,"tournament"]=t; keep|=mt
        d=d[keep].copy()
        if not len(d): continue
        d["match"]=d["ts"].isin(allm).astype(int)
        own_min=d["ts"].isin(flags[flag]).astype(int)
        knock_min=d["ts"].isin(knock).astype(int)
        # DDD components are interactions of match with own and knock minute flags
        d["m_own"]=(d["match"]*own_min).astype(int)
        d["m_knock"]=(d["match"]*knock_min).astype(int)
        d["m_own_knock"]=(d["match"]*own_min*knock_min).astype(int)
        d["weekday"]=d["ts"].dt.weekday; d["mod"]=d["ts"].dt.hour*60+d["ts"].dt.minute
        d["wd_mod"]=d["weekday"].astype(str)+"_"+d["mod"].astype(str)
        d["date"]=d["ts"].dt.strftime("%Y-%m-%d"); d["instrument"]=inst
        parts.append(d[["ts","instrument","tournament","lvol","match",
                        "m_own","m_knock","m_own_knock","wd_mod","date"]])
    panel=pd.concat(parts,ignore_index=True)

    # power diagnostics: treated date-clusters at each level
    own_knock_days=panel.loc[panel.m_own_knock==1,"date"].nunique()
    own_days=panel.loc[panel.m_own==1,"date"].nunique()
    knock_days=panel.loc[panel.m_knock==1,"date"].nunique()
    own_knock_min=int(panel["m_own_knock"].sum())

    rows=[]
    for y in ["lvol"]:
        sub=panel.dropna(subset=[y]); sub=sub[np.isfinite(sub[y])]
        mm=feols(f"{y} ~ match + m_own + m_knock + m_own_knock | instrument^wd_mod + date",
                 data=sub, vcov={"CRV1":"date"})
        t=mm.tidy()
        label={"match":"match (base)","m_own":"match:own",
               "m_knock":"match:knock","m_own_knock":"match:own:knock (DDD)"}
        for v in ["match","m_own","m_knock","m_own_knock"]:
            r=t.loc[v]
            rows.append(dict(outcome=y,term=v,label=label[v],
                coef=round(r["Estimate"],4),se=round(r["Std. Error"],4),
                t=round(r["t value"],3),p=round(r["Pr(>|t|)"],4),
                pct=round(np.expm1(r["Estimate"])*100,2),n=int(mm._N)))
    res=pd.DataFrame(rows)
    res["own_knock_treated_dates"]=own_knock_days
    res["own_treated_dates"]=own_days
    res["knock_treated_dates"]=knock_days
    res["own_knock_treated_minutes"]=own_knock_min
    res.to_csv(os.path.join(OUT,"triple_diff.csv"),index=False)

    ddd=res.loc[res.term=="m_own_knock"].iloc[0]
    print(res.to_string(index=False))
    print(f"\ntreated date-clusters: own={own_days}, knockout={knock_days}, own-AND-knockout={own_knock_days}")
    print(f"own-knockout treated minutes={own_knock_min:,}")
    print(f"DDD (match:own:knock) lvol coef={ddd['coef']} ({ddd['pct']}%), p={ddd['p']}")
    if own_knock_days < 8:
        print(f"WARNING: only {own_knock_days} own-team knockout treated date-clusters -> DDD is underpowered.")
    return res

if __name__=="__main__":
    main()
