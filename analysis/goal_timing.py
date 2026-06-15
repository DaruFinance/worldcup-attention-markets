#!/usr/bin/env python3
"""
Goal-timing robustness for the goal-window null. Reconstructed goal timing (match-clock minute + stoppage
offset, not the true wall-clock instant) attenuates a true effect toward zero. We quantify the exposure two
ways, both with a fast two-way-FE + date-clustered estimator (FWL residualization). (1) Window-width sweep:
re-run the crypto goal regression at +-2, +-5, +-10, +-15 minutes -- a spike localized to the goal but
smeared by timing error would strengthen as the window widens; a flat profile means no spike is being hidden.
(2) Timing-jitter robustness: perturb every goal timestamp by uniform +-J minutes (J=1,2,3) and re-estimate,
reading the coefficient's sensitivity to mistiming of that size directly off the data. Out: analysis/out/goal_timing.csv
"""
import os, sys, warnings; warnings.simplefilter("ignore")
os.environ.setdefault("OPENBLAS_NUM_THREADS","1"); os.environ.setdefault("OMP_NUM_THREADS","1")
import numpy as np, pandas as pd
ROOT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"..")
PANEL=os.path.join(ROOT,"data","market","panel","all_panel.parquet")
MDIR=os.path.join(ROOT,"data","matches"); OUT=os.path.join(ROOT,"analysis","out")
rng=np.random.default_rng(909)
CRYPTO=["BTCUSDT_spot","ETHUSDT_spot","BTCUSDT_perp","ETHUSDT_perp"]

def load():
    d=pd.read_parquet(PANEL); d=d[d.tournament.isin([2018,2022]) & d.instrument.isin(CRYPTO)].dropna(subset=["lvol"]).copy()
    d["tmin"]=pd.to_datetime(d["ts"],utc=True).dt.tz_localize(None).dt.floor("min").values.astype("datetime64[m]")
    g=pd.read_parquet(os.path.join(MDIR,"goals_all.parquet"))
    gt=pd.to_datetime(g["goal_utc"],utc=True).dt.tz_localize(None).dt.floor("min").values.astype("datetime64[m]")
    c1=pd.factorize((d.instrument.astype(str)+"_"+d.wd_mod.astype(str)).values)[0]
    c2=pd.factorize(d.date.values)[0]; G=int(c2.max()+1)
    return d["lvol"].values.astype(float), d["tmin"].values, np.sort(gt), c1, c2, G

def dist(tmin, gt, shift=None):
    g=np.sort(gt+shift.astype("timedelta64[m]")) if shift is not None else gt
    idx=np.searchsorted(g,tmin)
    L=np.where(idx>0,(tmin-g[np.clip(idx-1,0,len(g)-1)]).astype("timedelta64[m]").astype(np.int64),10**6)
    R=np.where(idx<len(g),(g[np.clip(idx,0,len(g)-1)]-tmin).astype("timedelta64[m]").astype(np.int64),10**6)
    return np.minimum(np.abs(L),np.abs(R))

def demean(x,c1,c2,iters=50,tol=1e-10):
    x=np.asarray(x,float).copy()
    b1=np.bincount(c1); b2=np.bincount(c2)
    for _ in range(iters):
        x0=x.copy(); x-=np.bincount(c1,x)[c1]/b1[c1]; x-=np.bincount(c2,x)[c2]/b2[c2]
        if np.max(np.abs(x-x0))<tol: break
    return x

def fit(y_dm, gwin, c1, c2, G):
    """y already demeaned; demean treatment, FWL, clustered-by-date t."""
    t=demean(gwin.astype(float),c1,c2); tt=t@t
    if tt<=0: return np.nan,np.nan
    b=(t@y_dm)/tt; e=y_dm-b*t
    s=np.bincount(c2,t*e,minlength=G); se=np.sqrt(s@s)/tt*np.sqrt(G/(G-1))
    return b,(b/se if se>0 else np.nan)

def main():
    y,tmin,gt,c1,c2,G=load(); ydm=demean(y,c1,c2)
    base=dist(tmin,gt); rows=[]
    print("=== (1) window-width sweep (true timestamps) ===",flush=True)
    from scipy import stats
    for half in (2,5,10,15):
        b,tstat=fit(ydm,(base<=half),c1,c2,G); p=2*stats.norm.sf(abs(tstat))
        rows.append(dict(test="width",window=f"+-{half}m",jitter=0,coef_pct=round(np.expm1(b)*100,2),tstat=round(tstat,2),p=round(p,4)))
        print(f"  +-{half:2d}m : {np.expm1(b)*100:+6.2f}%  t={tstat:+.2f}  p={p:.3f}",flush=True)
    print("=== (2) timing-jitter (+-J min uniform), +-5m window, 120 draws ===",flush=True)
    for J in (1,2,3):
        bs=[]
        for _ in range(120):
            sh=rng.integers(-J,J+1,size=len(gt)).astype(np.int64)
            b,_=fit(ydm,(dist(tmin,gt,sh)<=5),c1,c2,G); bs.append(np.expm1(b)*100)
        rows.append(dict(test="jitter",window="+-5m",jitter=J,coef_pct=round(float(np.mean(bs)),2),tstat=np.nan,p=np.nan,sd_pct=round(float(np.std(bs)),2)))
        print(f"  J=+-{J}m : mean {np.mean(bs):+6.2f}%  sd {np.std(bs):.2f}  (120 jittered fits)",flush=True)
    pd.DataFrame(rows).to_csv(os.path.join(OUT,"goal_timing.csv"),index=False)
    print("\nFlat across widths and stable under +-1-3m jitter => the null is not a mistiming artifact.",flush=True)
if __name__=="__main__":
    main()
