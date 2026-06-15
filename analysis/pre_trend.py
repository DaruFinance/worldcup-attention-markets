#!/usr/bin/env python3
"""
Formal parallel-trends / pre-trend test for the matched-control design (crypto, 2018+2022).
Tag each minute by event time relative to the nearest kickoff, bin into 15-min buckets over
[-120,+120], omit minutes not near any kickoff (the matched-control baseline absorbed by the
FE), and estimate event-time bin coefficients. If the design is clean, the PRE-kickoff bins
(-120..0) are jointly ~0 (no divergence before treatment).

Out: analysis/out/pre_trend.csv
"""
import os, warnings
warnings.simplefilter("ignore")
os.environ.setdefault("OPENBLAS_NUM_THREADS","1"); os.environ.setdefault("OMP_NUM_THREADS","1")
import numpy as np, pandas as pd
from pyfixest.estimation import feols

ROOT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"..")
PANEL=os.path.join(ROOT,"data","market","panel","crypto_panel.parquet")
MDIR=os.path.join(ROOT,"data","matches"); OUT=os.path.join(ROOT,"analysis","out")

def main():
    p=pd.read_parquet(PANEL); p=p[p["tournament"].isin([2018,2022])].copy()
    p["ts"]=pd.to_datetime(p["ts"],utc=True)
    m=pd.read_parquet(os.path.join(MDIR,"matches_all.parquet"))
    m=m[(m["tournament"].isin([2018,2022]))&(m["played"])]
    ko=np.sort(pd.to_datetime(m["kickoff_utc"],utc=True).values.astype("datetime64[m]"))
    tsm=p["ts"].values.astype("datetime64[m]")
    idx=np.clip(np.searchsorted(ko,tsm),1,len(ko)-1)
    dl=(tsm-ko[idx-1]).astype("timedelta64[m]").astype(int)
    dr=(tsm-ko[np.clip(idx,0,len(ko)-1)]).astype("timedelta64[m]").astype(int)
    rel=np.where(np.abs(dl)<=np.abs(dr),dl,dr)   # signed minutes to nearest kickoff
    near=np.abs(rel)<=120
    binv=(np.floor(rel/15)*15).astype(int)
    bins=list(range(-120,120,15))
    names={}
    for b in bins:
        nm=f"ev_{'m' if b<0 else 'p'}{abs(b)}"
        names[b]=nm
        p[nm]=((near)&(binv==b)).astype(int)   # control (not near any kickoff) = all zero
    sub=p.dropna(subset=["lvol"])
    rhs=" + ".join(names[b] for b in bins)
    mm=feols(f"lvol ~ {rhs} | instrument^wd_mod + date", data=sub, vcov={"CRV1":"date"})
    tt=mm.tidy()
    rows=[]
    for b in bins:
        if names[b] in tt.index:
            r=tt.loc[names[b]]; rows.append(dict(term=names[b], bin=b, Estimate=r["Estimate"],
                **{"Std. Error":r["Std. Error"],"Pr(>|t|)":r["Pr(>|t|)"]}))
    t=pd.DataFrame(rows).sort_values("bin")
    t["phase"]=np.where(t["bin"]<0,"pre","during/post")
    res=t[["bin","phase","Estimate","Std. Error","Pr(>|t|)"]].rename(
        columns={"Estimate":"coef","Std. Error":"se","Pr(>|t|)":"p"}).round(4)
    res.to_csv(os.path.join(OUT,"pre_trend.csv"),index=False)
    pre=res[res["phase"]=="pre"]
    print(res.to_string(index=False))
    print(f"\nPRE-kickoff bins (-120..0): {len(pre)} bins, "
          f"max|coef|={pre['coef'].abs().max():.4f}, min p={pre['p'].min():.3f}, "
          f"# with p<0.05: {(pre['p']<0.05).sum()}")
    print("=> parallel-trends holds" if (pre['p']>=0.05).all() else "=> PRE-TREND VIOLATION")
    return res

if __name__=="__main__":
    main()
