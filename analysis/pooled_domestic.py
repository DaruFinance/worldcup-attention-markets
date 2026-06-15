#!/usr/bin/env python3
"""
Properly-powered test of H6 (domestic-team effect). Per-instrument domestic tests are
under-powered (6B=6 match-days, NQ/ES=2). Pool the mapped instruments so the own-team
effect is identified from the union of domestic match-days across markets.

own_match = Match x (own national team playing). Spec:
  Y ~ foreign_match + own_match | instrument^wd_mod + date,  cluster date.
foreign_match = a match in progress with NO own-team; own_match = own team playing.
Reports treated (own) date-cluster counts, runs FX-only subset, a +1-day placebo on the
own flag, and leave-2018-out.
"""
import os, warnings
warnings.simplefilter("ignore")
os.environ.setdefault("OPENBLAS_NUM_THREADS","1"); os.environ.setdefault("OMP_NUM_THREADS","1")
import numpy as np, pandas as pd
from pyfixest.estimation import feols

ROOT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"..")
PANEL=os.path.join(ROOT,"data","market","panel","all_panel.parquet")
OUT=os.path.join(ROOT,"analysis","out"); os.makedirs(OUT,exist_ok=True)
OWN={"ES":"any_usa_i","NQ":"any_usa_i","6E":"any_euro_i","6B":"any_gbp_i","6J":"any_jpy_i"}
OUTS=["lvol","ltrades","absret"]

def prep(d):
    d=d[d["instrument"].isin(OWN)].copy()
    d["own_flag"]=0
    for inst,flag in OWN.items():
        m=d["instrument"]==inst; d.loc[m,"own_flag"]=d.loc[m,flag].values
    d["own_match"]=d["match"]*d["own_flag"]
    d["foreign_match"]=d["match"]*(1-d["own_flag"])
    return d

def run(d, tag, fe="instrument^wd_mod + date"):
    rows=[]
    for y in OUTS:
        sub=d.dropna(subset=[y])
        m=feols(f"{y} ~ foreign_match + own_match | {fe}", data=sub, vcov={"CRV1":"date"})
        t=m.tidy()
        for v in ["foreign_match","own_match"]:
            r=t.loc[v]
            rows.append(dict(spec=tag,outcome=y,term=v,coef=r["Estimate"],se=r["Std. Error"],
                             p=r["Pr(>|t|)"],n=int(m._N)))
    return rows

def main():
    d=pd.read_parquet(PANEL)
    est=prep(d[d["tournament"].isin([2018,2022])])
    own_days=est.loc[est["own_match"]==1,"date"].nunique()
    fx=est[est["instrument"].isin(["6E","6B","6J"])]
    fx_days=fx.loc[fx["own_match"]==1,"date"].nunique()
    print(f"own-team treated date-clusters: ALL-mapped={own_days}, FX-only={fx_days}")

    rows=[]
    rows+=run(est,"all_mapped")
    rows+=run(fx,"fx_only")
    # leave-2018-out (2022 only)
    rows+=run(est[est["tournament"]==2022],"2022_only")
    # placebo: own flag shifted +1 day within instrument
    pb=est.sort_values(["instrument","ts"]).copy()
    pb["own_match"]=pb.groupby("instrument")["own_match"].shift(1440).fillna(0).astype(int)
    pb["foreign_match"]=(pb["match"]-pb["own_match"]).clip(lower=0)
    rows+=run(pb,"placebo_+1d")

    res=pd.DataFrame(rows); res.to_csv(os.path.join(OUT,"pooled_domestic.csv"),index=False)
    pv=res.pivot_table(index=["outcome","term"],columns="spec",values="coef",aggfunc="first")
    pp=res.pivot_table(index=["outcome","term"],columns="spec",values="p",aggfunc="first")
    print("\n=== COEF ===\n", pv.round(4).to_string())
    print("\n=== P ===\n", pp.round(4).to_string())
    print(f"\n(own-team treated clusters: all={own_days}, fx={fx_days}  -  interpret accordingly)")
    return res

if __name__=="__main__":
    main()
