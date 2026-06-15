#!/usr/bin/env python3
"""
Headline cross-market regressions. Estimation = 2018+2022 (2026 = live OOS).
Spec: Y ~ Match | instrument^(weekday x minute-of-day) + date, SE clustered by date.
The Match coefficient is a log-point (≈%) change vs the matched control, comparable across
market groups. BH-FDR across the primary outcome x group family.

Tables out (analysis/out/): xm_main.csv (Table 3/5), xm_domestic.csv (Table 4),
xm_knockout.csv, xm_2026_oos.csv.
"""
import os, warnings
warnings.simplefilter("ignore")
os.environ.setdefault("OPENBLAS_NUM_THREADS","1"); os.environ.setdefault("OMP_NUM_THREADS","1")
import numpy as np, pandas as pd
from pyfixest.estimation import feols

ROOT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"..")
PANEL=os.path.join(ROOT,"data","market","panel","all_panel.parquet")
OUT=os.path.join(ROOT,"analysis","out"); os.makedirs(OUT,exist_ok=True)
PRIMARY=["lvol","ltrades","absret","hlrange"]
GROUPS=["crypto_spot","crypto_perp","equity_fut","commodity_fut","fx_fut"]

def bh(p):
    p=np.asarray(p,float); n=len(p); o=np.argsort(p); out=np.empty(n); c=1.0
    for i in range(n-1,-1,-1): c=min(c,p[o[i]]*n/(i+1)); out[o[i]]=c
    return out

def est(sub, y, rhs="match", fe="instrument^wd_mod + date"):
    if sub["instrument"].nunique()<2: fe="wd_mod + date"
    m=feols(f"{y} ~ {rhs} | {fe}", data=sub.dropna(subset=[y]), vcov={"CRV1":"date"})
    return m

def get(m, var):
    t=m.tidy()
    if var not in t.index: return None
    r=t.loc[var]; return dict(coef=r["Estimate"], se=r["Std. Error"], p=r["Pr(>|t|)"], n=int(m._N))

def main():
    d=pd.read_parquet(PANEL)
    est_s=d[d["tournament"].isin([2018,2022])].copy()

    # ---- Table 3/5: main effect, per group + ALL ----
    rows=[]
    for grp in ["ALL"]+GROUPS:
        sub=est_s if grp=="ALL" else est_s[est_s["market_group"]==grp]
        if not len(sub): continue
        for y in PRIMARY+["lavg_trade","signed_imb","amihud"]:
            try: m=est(sub,y)
            except Exception as e: continue
            r=get(m,"match")
            if r: rows.append(dict(group=grp,outcome=y,primary=y in PRIMARY,
                    pct=(np.expm1(r["coef"])*100 if y in ("lvol","ltrades","lavg_trade") else np.nan),
                    **r))
    main_df=pd.DataFrame(rows)
    fam=main_df[(main_df["group"]!="ALL")&(main_df["primary"])]
    main_df["q_bh"]=np.nan; main_df.loc[fam.index,"q_bh"]=bh(fam["p"].values)
    main_df.to_csv(os.path.join(OUT,"xm_main.csv"),index=False)

    # ---- Table 4: domestic-team & knockout heterogeneity ----
    DOM={"equity_fut":"any_usa_i","fx_fut":None}  # fx handled per-pair below
    drows=[]
    # ES/NQ: USA; 6E: euro; 6B: gbp; 6J: jpy  (per-instrument domestic flag)
    dom_by_inst={"ES":"any_usa_i","NQ":"any_usa_i","6E":"any_euro_i","6B":"any_gbp_i","6J":"any_jpy_i"}
    for inst,flag in dom_by_inst.items():
        sub=est_s[est_s["instrument"]==inst]
        if not len(sub): continue
        for y in ["lvol","ltrades","absret"]:
            try:
                m=est(sub,y,rhs=f"match + match:{flag}",fe="wd_mod + date")
            except Exception: continue
            for v,lab in [("match",f"{inst} match"),(f"match:{flag}",f"{inst} x domestic")]:
                r=get(m,v)
                if r: drows.append(dict(instrument=inst,term=lab,outcome=y,**r))
    pd.DataFrame(drows).to_csv(os.path.join(OUT,"xm_domestic.csv"),index=False)

    # ---- knockout per group ----
    krows=[]
    for grp in GROUPS:
        sub=est_s[est_s["market_group"]==grp]
        if not len(sub) or sub["any_knockout_i"].sum()<30: continue
        for y in ["lvol","ltrades","absret"]:
            try: m=est(sub,y,rhs="match + match:any_knockout_i")
            except Exception: continue
            for v,lab in [("match","match(group)"),("match:any_knockout_i","knockout extra")]:
                r=get(m,v)
                if r: krows.append(dict(group=grp,term=lab,outcome=y,**r))
    pd.DataFrame(krows).to_csv(os.path.join(OUT,"xm_knockout.csv"),index=False)

    # ---- 2026 OOS ----
    o=d[d["tournament"]==2026]; orows=[]
    for grp in GROUPS:
        sub=o[o["market_group"]==grp]
        if sub["match"].sum()<30: continue
        for y in PRIMARY:
            try: m=est(sub,y)
            except Exception: continue
            r=get(m,"match")
            if r: orows.append(dict(group=grp,outcome=y,**r))
    pd.DataFrame(orows).to_csv(os.path.join(OUT,"xm_2026_oos.csv"),index=False)

    # ---- print headline ----
    pd.set_option("display.width",160)
    show=main_df[main_df["outcome"].isin(PRIMARY)][["group","outcome","coef","se","p","q_bh","pct","n"]].round(4)
    print("=== CROSS-MARKET MAIN EFFECT (during-match, 2018+2022) ===")
    print(show.to_string(index=False))
    print("\n=== DOMESTIC-TEAM (per instrument) ===")
    dd=pd.read_csv(os.path.join(OUT,"xm_domestic.csv"))
    if len(dd): print(dd.round(4).to_string(index=False))
    return main_df

if __name__=="__main__":
    main()
