#!/usr/bin/env python3
"""
Matched-control event studies (crypto, 2018+2022).

Baseline per instrument x (weekday x minute-of-day) computed from NON-match minutes inside
the tournament windows = the matched control. Deviation = value - baseline. We trace:
  (1) kickoff-centered curve [-120,+150]  -> Figure 1
  (2) goal-centered curve   [-30,+30]     -> Figure 5
and run the goal-window regression (g5 = |t-goal|<=5, g15 = 6..15) with instrument x
weekday x minute-of-day + date FE, clustered by date.

Out: analysis/out/kickoff_curve.csv, goal_curve.csv, reg_goal.csv
     analysis/figures/fig1_kickoff_*.png, fig5_goal_*.png
"""
import os, warnings
warnings.simplefilter("ignore")
os.environ.setdefault("OPENBLAS_NUM_THREADS","1"); os.environ.setdefault("OMP_NUM_THREADS","1")
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pyfixest.estimation import feols

ROOT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"..")
PANEL=os.path.join(ROOT,"data","market","panel","crypto_panel.parquet")
MDIR=os.path.join(ROOT,"data","matches")
OUT=os.path.join(ROOT,"analysis","out"); FIG=os.path.join(ROOT,"analysis","figures")
os.makedirs(OUT,exist_ok=True); os.makedirs(FIG,exist_ok=True)
OUTCOMES=["lvol","ltrades","absret","signed_imb"]
LABEL={"lvol":"log dollar volume","ltrades":"log trade count",
       "absret":"|1-min return|","signed_imb":"signed taker imbalance"}

def load():
    p=pd.read_parquet(PANEL)
    p=p[p["tournament"].isin([2018,2022])].copy()
    p["ts"]=pd.to_datetime(p["ts"], utc=True)
    return p

def baselines(p):
    """mean of each outcome over NON-match minutes, per (instrument, wd_mod)."""
    nm=p[~p["any_match"]]
    b={}
    for y in OUTCOMES:
        b[y]=nm.groupby(["instrument","wd_mod"])[y].mean()
    return b

def add_dev(df, b):
    for y in OUTCOMES:
        base=b[y].reindex(pd.MultiIndex.from_arrays([df["instrument"],df["wd_mod"]])).values
        df[y+"_dev"]=df[y].values - base
    return df

def event_curve(p, centers, lo, hi, label):
    """centers: DataFrame with columns [id, ts0]. Returns rel-min aggregated deviations."""
    # build event-minute frame (ts, ev_id, rel) then merge to panel on ts
    rel=np.arange(lo,hi+1)
    ev=centers.loc[centers.index.repeat(len(rel))].copy()
    ev["rel"]=np.tile(rel, len(centers))
    ev["ts0"]=pd.to_datetime(ev["ts0"], utc=True)
    ev["ts"]=ev["ts0"]+pd.to_timedelta(ev["rel"],unit="m")
    m=ev.merge(p[["ts","instrument","date"]+[y+"_dev" for y in OUTCOMES]], on="ts", how="inner")
    rows=[]
    for r,g in m.groupby("rel"):
        row=dict(rel=int(r), n=len(g))
        for y in OUTCOMES:
            v=g[y+"_dev"].dropna()
            # cluster-ish SE by date
            row[y+"_mean"]=v.mean()
            row[y+"_se"]=v.std()/np.sqrt(max(1,g["date"].nunique()))
        rows.append(row)
    return pd.DataFrame(rows).sort_values("rel")

def plot_curve(curve, fname, title, xlabel, vlines):
    fig,axes=plt.subplots(1,3,figsize=(15,4.2))
    for ax,y in zip(axes,["lvol","ltrades","absret"]):
        mu=curve[y+"_mean"].values; se=curve[y+"_se"].values; x=curve["rel"].values
        ax.axhline(0,color="#999",lw=.8);
        for vx,vl in vlines: ax.axvline(vx,color="#c0392b",ls="--",lw=.8,alpha=.7)
        ax.plot(x,mu,color="#1f4e79",lw=1.5)
        ax.fill_between(x,mu-1.96*se,mu+1.96*se,color="#1f4e79",alpha=.18)
        ax.set_title(LABEL[y]); ax.set_xlabel(xlabel)
    axes[0].set_ylabel("deviation from matched control")
    fig.suptitle(title,fontsize=12)
    fig.tight_layout(); fig.savefig(os.path.join(FIG,fname),dpi=130); plt.close(fig)

def goal_regression(p):
    goals=pd.read_parquet(os.path.join(MDIR,"goals_all.parquet"))
    gt=pd.to_datetime(goals["goal_utc"],utc=True).values.astype("datetime64[m]")
    # nearest-goal distance per panel minute (vectorized searchsorted)
    gt=np.sort(gt)
    tsm=p["ts"].values.astype("datetime64[m]")
    idx=np.searchsorted(gt,tsm)
    idx=np.clip(idx,1,len(gt)-1)
    left=(tsm-gt[idx-1]).astype("timedelta64[m]").astype(int)
    right=(gt[np.clip(idx,0,len(gt)-1)]-tsm).astype("timedelta64[m]").astype(int)
    dist=np.minimum(np.abs(left),np.abs(right))
    p=p.copy()
    p["g5"]=((dist<=5)).astype(int)
    p["g15"]=((dist>5)&(dist<=15)).astype(int)
    rows=[]
    for y in OUTCOMES:
        sub=p.dropna(subset=[y])
        m=feols(f"{y} ~ g5 + g15 | instrument^wd_mod + date", data=sub, vcov={"CRV1":"date"})
        t=m.tidy()
        for v in ["g5","g15"]:
            r=t.loc[v]
            rows.append(dict(outcome=y, window=v, coef=r["Estimate"], se=r["Std. Error"],
                             p=r["Pr(>|t|)"], n=int(m._N)))
    df=pd.DataFrame(rows); df.to_csv(os.path.join(OUT,"reg_goal.csv"),index=False)
    return df

def main():
    p=load(); b=baselines(p); p=add_dev(p,b)
    # kickoff centers (played matches in estimation sample)
    m=pd.read_parquet(os.path.join(MDIR,"matches_all.parquet"))
    m=m[(m["tournament"].isin([2018,2022]))&(m["played"])].copy()
    kc=pd.DataFrame({"id":m["match_no"].values,
                     "ts0":pd.to_datetime(m["kickoff_utc"],utc=True).dt.floor("min").values})
    kcurve=event_curve(p,kc,-120,150,"kickoff"); kcurve.to_csv(os.path.join(OUT,"kickoff_curve.csv"),index=False)
    plot_curve(kcurve,"fig1_kickoff.png",
               "Figure 1. Crypto activity & volatility around World Cup kickoff (2018+2022, matched control)",
               "minutes from kickoff",[(0,"KO"),(45,"HT"),(60,"2H"),(105,"~FT")])
    # goal centers
    goals=pd.read_parquet(os.path.join(MDIR,"goals_all.parquet"))
    gc=pd.DataFrame({"id":range(len(goals)),
                     "ts0":pd.to_datetime(goals["goal_utc"],utc=True).dt.floor("min").values})
    gcurve=event_curve(p,gc,-30,30,"goal"); gcurve.to_csv(os.path.join(OUT,"goal_curve.csv"),index=False)
    plot_curve(gcurve,"fig5_goal.png",
               "Figure 5. Crypto response around goal events (2018+2022, matched control)",
               "minutes from goal",[(0,"goal")])
    greg=goal_regression(p)
    print("=== GOAL-WINDOW REGRESSION (within tournament windows, FE+date, cluster date) ===")
    print(greg.round(4).to_string(index=False))
    print("\nkickoff curve peak |lvol_dev| at rel(min):",
          int(kcurve.loc[kcurve['lvol_mean'].abs().idxmax(),'rel']),
          "value", round(kcurve['lvol_mean'].abs().max(),4))
    print("goal curve lvol_dev at rel 0..+5:",
          kcurve is not None and gcurve[(gcurve.rel>=0)&(gcurve.rel<=5)]['lvol_mean'].mean().round(4))
    print("figures ->", FIG)

if __name__=="__main__":
    main()
