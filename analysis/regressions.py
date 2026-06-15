#!/usr/bin/env python3
"""
Core event-study regressions for the crypto arm.

Identification: Y_it = beta*Match_t + FE(instrument x weekday x minute-of-day) + FE(date) + e.
The instrument-specific weekday×minute-of-day FE is the matched-control: it compares a
match-minute to the SAME minute-of-week for the SAME instrument on non-match days inside
the tournament window (kills the "matches happen in low-volume US evenings" / lunch-hour
confound). Date FE absorbs day-level vol regime / macro. SE clustered by date.

Estimation sample = 2018 + 2022 (complete). 2026 = live OOS, reported separately.
Multiple testing: BH-FDR across the primary outcome family.

Out: analysis/out/reg_main.csv, reg_hetero.csv, reg_bymarket.csv, reg_placebo.csv,
     reg_2026_oos.csv  (+ printed summary)
"""
import os, warnings
warnings.simplefilter("ignore")
os.environ.setdefault("OPENBLAS_NUM_THREADS","1"); os.environ.setdefault("OMP_NUM_THREADS","1")
import numpy as np, pandas as pd
from pyfixest.estimation import feols
from scipy import stats

ROOT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"..")
PANEL=os.path.join(ROOT,"data","market","panel","crypto_panel.parquet")
OUT=os.path.join(ROOT,"analysis","out"); os.makedirs(OUT,exist_ok=True)

PRIMARY=["lvol","ltrades","absret","hlrange"]          # pre-registered primary outcomes
SECOND =["lavg_trade","sqret","amihud","signed_imb"]   # exploratory
ALLOUT = PRIMARY+SECOND

def load():
    d=pd.read_parquet(PANEL)
    for c in ["any_match","any_pre","any_post","any_first_half","any_halftime",
              "any_second_half","any_knockout","any_usa","any_euro","any_gbp","any_jpy"]:
        d[c+"_i"]=d[c].astype(int)
    d["match"]=d["any_match_i"]
    return d

def bh_fdr(pvals):
    p=np.asarray(pvals,float); n=len(p); order=np.argsort(p)
    ranked=np.empty(n); c=1.0
    for i in range(n-1,-1,-1):
        idx=order[i]; c=min(c, p[idx]*n/(i+1)); ranked[idx]=c
    return ranked

def run(formula, data, cluster="date"):
    m=feols(formula, data=data, vcov={"CRV1":cluster})
    return m

def coef_row(m, var, label, extra=None):
    t=m.tidy()
    if var not in t.index: return None
    r=t.loc[var]
    row=dict(term=label, coef=r["Estimate"], se=r["Std. Error"],
             t=r["t value"], p=r["Pr(>|t|)"], n=int(m._N))
    if extra: row.update(extra)
    return row

# ---------------------------------------------------------------- main effects
def main_effects(d):
    est=d[d["tournament"].isin([2018,2022])].copy()
    rows=[]
    for y in ALLOUT:
        sub=est.dropna(subset=[y])
        m=run(f"{y} ~ match | instrument^wd_mod + date", sub)
        r=coef_row(m,"match",y,extra=dict(outcome=y,primary=y in PRIMARY,
                   match_mean=sub.loc[sub.match==1,y].mean(),
                   ctrl_mean=sub.loc[sub.match==0,y].mean()))
        rows.append(r)
    df=pd.DataFrame(rows)
    df["q_bh_primary"]=np.nan
    pm=df["primary"]; df.loc[pm,"q_bh_primary"]=bh_fdr(df.loc[pm,"p"].values)
    df.to_csv(os.path.join(OUT,"reg_main.csv"),index=False)
    return df

# ---------------------------------------------------------------- heterogeneity
def hetero(d):
    est=d[d["tournament"].isin([2018,2022])].copy()
    rows=[]
    for y in PRIMARY:
        sub=est.dropna(subset=[y])
        # intensity (concurrent matches)
        m=run(f"{y} ~ n_in_match | instrument^wd_mod + date", sub)
        rows.append(coef_row(m,"n_in_match",f"{y}: per concurrent match",extra=dict(outcome=y,spec="intensity")))
        # knockout interaction
        m=run(f"{y} ~ match + match:any_knockout_i | instrument^wd_mod + date", sub)
        rows.append(coef_row(m,"match",f"{y}: match (group)",extra=dict(outcome=y,spec="knockout")))
        rows.append(coef_row(m,"match:any_knockout_i",f"{y}: knockout extra",extra=dict(outcome=y,spec="knockout")))
        # phase decomposition (baseline = non-match)
        m=run(f"{y} ~ any_pre_i + any_first_half_i + any_halftime_i + any_second_half_i + any_post_i "
              f"| instrument^wd_mod + date", sub)
        for v,lab in [("any_pre_i","pre -60..0"),("any_first_half_i","first half"),
                      ("any_halftime_i","halftime"),("any_second_half_i","second half"),
                      ("any_post_i","post +60")]:
            rows.append(coef_row(m,v,f"{y}: {lab}",extra=dict(outcome=y,spec="phase")))
        # US-team attention (crypto is global; US-hours team a natural attention peak)
        m=run(f"{y} ~ match + match:any_usa_i | instrument^wd_mod + date", sub)
        rows.append(coef_row(m,"match:any_usa_i",f"{y}: USA-playing extra",extra=dict(outcome=y,spec="domestic")))
    df=pd.DataFrame([r for r in rows if r]); df.to_csv(os.path.join(OUT,"reg_hetero.csv"),index=False)
    return df

# ---------------------------------------------------------------- by market structure
def by_market(d):
    est=d[d["tournament"].isin([2018,2022])].copy()
    rows=[]
    for y in PRIMARY:
        for key,flt in [("BTC",est["sym"]=="BTCUSDT"),("ETH",est["sym"]=="ETHUSDT"),
                        ("spot",est["mkt"]=="spot"),("perp",est["mkt"]=="perp")]:
            sub=est[flt].dropna(subset=[y])
            if sub["match"].sum()<50 or sub["instrument"].nunique()<1: continue
            fe="instrument^wd_mod + date" if sub["instrument"].nunique()>1 else "wd_mod + date"
            m=run(f"{y} ~ match | {fe}", sub)
            rows.append(coef_row(m,"match",f"{y}/{key}",extra=dict(outcome=y,group=key)))
    df=pd.DataFrame([r for r in rows if r]); df.to_csv(os.path.join(OUT,"reg_bymarket.csv"),index=False)
    return df

# ---------------------------------------------------------------- placebo
def placebo(d):
    """Shift the match-minute set by +1 day and +3h; re-estimate. Effect should vanish."""
    est=d[d["tournament"].isin([2018,2022])].copy().sort_values(["instrument","ts"])
    rows=[]
    for shift_label, periods in [("+1day",1440),("+3h",180),("-1day",-1440)]:
        g=est.copy()
        # placebo match flag = real match shifted within instrument by `periods` minutes
        g["match_pbo"]=g.groupby("instrument")["match"].shift(periods).fillna(0).astype(int)
        for y in PRIMARY:
            sub=g.dropna(subset=[y])
            m=run(f"{y} ~ match_pbo | instrument^wd_mod + date", sub)
            rows.append(coef_row(m,"match_pbo",f"{y} {shift_label}",extra=dict(outcome=y,shift=shift_label)))
    df=pd.DataFrame([r for r in rows if r]); df.to_csv(os.path.join(OUT,"reg_placebo.csv"),index=False)
    return df

# ---------------------------------------------------------------- 2026 OOS
def oos_2026(d):
    s=d[d["tournament"]==2026].copy()
    rows=[]
    if s["any_match"].sum()>30:
        for y in PRIMARY:
            sub=s.dropna(subset=[y])
            m=run(f"{y} ~ match | instrument^wd_mod + date", sub)
            rows.append(coef_row(m,"match",y,extra=dict(outcome=y)))
    df=pd.DataFrame([r for r in rows if r])
    if len(df): df.to_csv(os.path.join(OUT,"reg_2026_oos.csv"),index=False)
    return df

def fmt(df, cols=("term","coef","se","p")):
    if df is None or not len(df): return "(none)"
    show=df.copy()
    for c in ["coef","se","p","q_bh_primary","t","match_mean","ctrl_mean"]:
        if c in show: show[c]=show[c].astype(float).round(4)
    keep=[c for c in ["term","coef","se","p","q_bh_primary"] if c in show]
    return show[keep].to_string(index=False)

if __name__=="__main__":
    d=load()
    print("=== estimation sample (2018+2022) rows:",
          int(d["tournament"].isin([2018,2022]).sum()),"===\n")
    print("### MAIN EFFECTS (during-match vs matched control)\n", fmt(main_effects(d)),"\n")
    print("### HETEROGENEITY\n", fmt(hetero(d)),"\n")
    print("### BY MARKET STRUCTURE\n", fmt(by_market(d)),"\n")
    print("### PLACEBO (should be ~0)\n", fmt(placebo(d)),"\n")
    print("### 2026 LIVE OOS (only", int((d['tournament']==2026).sum()),"min,",
          int(d[d.tournament==2026]['any_match'].sum()),"match-min so far)\n", fmt(oos_2026(d)))
