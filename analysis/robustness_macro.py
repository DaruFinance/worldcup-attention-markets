#!/usr/bin/env python3
"""Robustness: re-estimate the during-match effect after DROPPING minutes within ±90 min
of a high-impact US/euro-area macro release. If the date FE already handled it, estimates
are unchanged; either way we report the actual re-estimation rather than assert it."""
import os, warnings
warnings.simplefilter("ignore")
os.environ.setdefault("OPENBLAS_NUM_THREADS","1"); os.environ.setdefault("OMP_NUM_THREADS","1")
import numpy as np, pandas as pd
from pyfixest.estimation import feols

ROOT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"..")
PANEL=os.path.join(ROOT,"data","market","panel","all_panel.parquet")
MAC=os.path.join(ROOT,"data","controls","macro_events.parquet")
OUT=os.path.join(ROOT,"analysis","out")
GROUPS=["crypto_spot","crypto_perp","equity_fut","commodity_fut","fx_fut"]

def main():
    d=pd.read_parquet(PANEL); d=d[d["tournament"].isin([2018,2022])].copy()
    d["ts"]=pd.to_datetime(d["ts"],utc=True)
    ev=pd.read_parquet(MAC); ev["event_utc"]=pd.to_datetime(ev["event_utc"],utc=True)
    et=np.sort(ev["event_utc"].values.astype("datetime64[m]"))
    tsm=d["ts"].values.astype("datetime64[m]")
    idx=np.searchsorted(et,tsm); idx=np.clip(idx,1,len(et)-1)
    left=np.abs((tsm-et[idx-1]).astype("timedelta64[m]").astype(int))
    right=np.abs((et[np.clip(idx,0,len(et)-1)]-tsm).astype("timedelta64[m]").astype(int))
    d["macro_near"]=(np.minimum(left,right)<=90)
    # how many match-minutes are contaminated?
    contam=int((d["match"]*d["macro_near"]).sum()); tot=int(d["match"].sum())
    rows=[]
    for grp in GROUPS:
        for samp,flt in [("baseline", d["market_group"]==grp),
                         ("ex_macro", (d["market_group"]==grp)&(~d["macro_near"]))]:
            sub=d[flt].dropna(subset=["lvol"])
            m=feols("lvol ~ match | instrument^wd_mod + date", data=sub, vcov={"CRV1":"date"})
            r=m.tidy().loc["match"]
            rows.append(dict(group=grp,sample=samp,coef=r["Estimate"],se=r["Std. Error"],
                             p=r["Pr(>|t|)"],n=int(m._N)))
    res=pd.DataFrame(rows); res.to_csv(os.path.join(OUT,"robustness_macro.csv"),index=False)
    print(f"match-minutes within +/-90min of a macro release: {contam}/{tot} "
          f"({100*contam/tot:.1f}%)")
    piv=res.pivot_table(index="group",columns="sample",values="coef")
    piv["delta"]=piv["ex_macro"]-piv["baseline"]
    print(piv.round(4).to_string())
    return res

if __name__=="__main__":
    main()
