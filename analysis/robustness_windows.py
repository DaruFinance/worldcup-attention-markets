#!/usr/bin/env python3
"""Support the §6 robustness claims with actual estimates:
   (1) alternative event-window definitions (pre / first-half / second-half / post / entire match),
   (2) re-estimation at 5-min and 15-min aggregation.
Confirms the during-match null is not an artifact of the window or frequency choice."""
import os, warnings
warnings.simplefilter("ignore")
os.environ.setdefault("OPENBLAS_NUM_THREADS","1"); os.environ.setdefault("OMP_NUM_THREADS","1")
import numpy as np, pandas as pd
from pyfixest.estimation import feols

ROOT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"..")
PANEL=os.path.join(ROOT,"data","market","panel","all_panel.parquet")
OUT=os.path.join(ROOT,"analysis","out")

def alt_windows():
    d=pd.read_parquet(PANEL); d=d[d["tournament"].isin([2018,2022])].copy()
    rows=[]
    defs={"in_match (default)":"match",
          "pre -60..0":"any_pre_i","first half":"any_first_half_i",
          "second half":"any_second_half_i","post +60":"any_post_i"}
    for lab,var in defs.items():
        sub=d.dropna(subset=["lvol"])
        m=feols(f"lvol ~ {var} | instrument^wd_mod + date", data=sub, vcov={"CRV1":"date"})
        r=m.tidy().iloc[0]
        rows.append(dict(window=lab, coef=round(r["Estimate"],4), se=round(r["Std. Error"],4),
                         p=round(r["Pr(>|t|)"],4), pct=round(np.expm1(r["Estimate"])*100,2)))
    return pd.DataFrame(rows)

def by_frequency():
    d=pd.read_parquet(PANEL); d=d[d["tournament"].isin([2018,2022])].copy()
    d["ts"]=pd.to_datetime(d["ts"],utc=True)
    rows=[]
    for freq,fl in [("1min",1),("5min",5),("15min",15)]:
        if fl==1:
            g=d.copy()
        else:
            d["bin"]=d["ts"].dt.floor(f"{fl}min")
            agg=d.groupby(["instrument","bin"]).agg(
                vol=("lvol", lambda s: np.log(np.exp(s).sum())),  # sum levels then log
                match=("match","max")).reset_index()
            agg["ts"]=agg["bin"]; g=agg.rename(columns={"vol":"lvol"})
            g["weekday"]=g["ts"].dt.weekday; g["minute_of_day"]=g["ts"].dt.hour*60+g["ts"].dt.minute
            g["date"]=g["ts"].dt.strftime("%Y-%m-%d")
            g["wd_mod"]=g["weekday"].astype(str)+"_"+g["minute_of_day"].astype(str)
        sub=g.dropna(subset=["lvol"]); sub=sub[np.isfinite(sub["lvol"])]
        m=feols("lvol ~ match | instrument^wd_mod + date", data=sub, vcov={"CRV1":"date"})
        r=m.tidy().loc["match"]
        rows.append(dict(freq=freq, coef=round(r["Estimate"],4), se=round(r["Std. Error"],4),
                         p=round(r["Pr(>|t|)"],4), pct=round(np.expm1(r["Estimate"])*100,2), n=int(m._N)))
    return pd.DataFrame(rows)

if __name__=="__main__":
    aw=alt_windows(); aw.to_csv(os.path.join(OUT,"robustness_windows.csv"),index=False)
    bf=by_frequency(); bf.to_csv(os.path.join(OUT,"robustness_frequency.csv"),index=False)
    print("=== ALTERNATIVE EVENT WINDOWS (pooled, lvol) ===")
    print(aw.to_string(index=False))
    print("\n=== BY AGGREGATION FREQUENCY (pooled during-match, lvol) ===")
    print(bf.to_string(index=False))
