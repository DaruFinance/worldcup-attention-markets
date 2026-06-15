#!/usr/bin/env python3
"""
Few-cluster wild-cluster bootstrap applied symmetrically to the pooled own-team cells. wild_bootstrap.py covers the
single-market own-team cells; the pooled own-team cell (28 date-clusters, 2 tournaments) is also below the
~50-cluster regime where asymptotic cluster-robust p-values are trustworthy and its p is interpreted in the
text, so it must get the same treatment rather than only the cells we dismiss. We bootstrap the pooled
all-mapped and FX-only own-team volume cells (2- and 4-tournament), restricted-null wild-cluster, Rademacher
weights over match-days, B=4999, beside the asymptotic clustered p. Out: analysis/out/pooled_bootstrap.csv
"""
import os, warnings; warnings.simplefilter("ignore")
os.environ.setdefault("OPENBLAS_NUM_THREADS","1"); os.environ.setdefault("OMP_NUM_THREADS","1")
import numpy as np, pandas as pd
from pyfixest.estimation import feols
ROOT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"..")
PANEL=os.path.join(ROOT,"data","market","panel","all_panel.parquet")
P4=os.path.join(ROOT,"data","market","panel")   # 4-tourn panel if present
OUT=os.path.join(ROOT,"analysis","out")
rng=np.random.default_rng(77)
OWN={"ES":"any_usa_i","NQ":"any_usa_i","6E":"any_euro_i","6B":"any_gbp_i","6J":"any_jpy_i"}

def demean(x,c1,c2,iters=60,tol=1e-10):
    x=np.asarray(x,float).copy()
    for _ in range(iters):
        x0=x.copy()
        x-=np.bincount(c1,x)[c1]/np.bincount(c1)[c1]
        x-=np.bincount(c2,x)[c2]/np.bincount(c2)[c2]
        if np.max(np.abs(x-x0))<tol: break
    return x

def prep(d, instruments):
    s=d[d.instrument.isin(instruments)].dropna(subset=["lvol"]).copy()
    s["own_flag"]=0
    for inst,flag in OWN.items():
        m=s.instrument==inst; s.loc[m,"own_flag"]=s.loc[m,flag].values
    s["own_match"]=s["match"]*s["own_flag"]; s["foreign_match"]=s["match"]*(1-s["own_flag"])
    s["iwd"]=s.instrument.astype(str)+"_"+s.wd_mod.astype(str)
    return s

def wcr(s, B=4999):
    c1=pd.factorize(s.iwd.values)[0]; c2,uniq=pd.factorize(s.date.values); G=len(uniq)
    y=demean(s.lvol.values,c1,c2); t=demean(s.own_match.values,c1,c2); f=demean(s.foreign_match.values,c1,c2)
    ff=f@f
    if ff>0: y=y-(f@y)/ff*f; t=t-(f@t)/ff*f
    tt=t@t; bhat=(t@y)/tt
    def tstat(u):
        b=(t@u)/tt; e=u-b*t; sc=np.bincount(c2,t*e,minlength=G); se=np.sqrt(sc@sc)/tt*np.sqrt(G/(G-1))
        return (b/se if se>0 else np.nan), b
    t_obs,_=tstat(y); u0=y.copy(); cnt=0
    for _ in range(B):
        w=rng.choice([-1.0,1.0],size=G)[c2]
        tb,_=tstat(w*u0)
        if abs(tb)>=abs(t_obs): cnt+=1
    return bhat,t_obs,(cnt+1)/(B+1),G

def asy_p(s):
    m=feols("lvol ~ foreign_match + own_match | iwd + date", data=s, vcov={"CRV1":"date"})
    r=m.tidy().loc["own_match"]; return float(r["Pr(>|t|)"])

def main():
    d=pd.read_parquet(PANEL); d2=d[d.tournament.isin([2018,2022])]
    rows=[]
    specs=[("Own-team pooled, all-mapped (2 tourn.)",list(OWN),d2),
           ("Own-team pooled, FX-only (2 tourn.)",["6E","6B","6J"],d2)]
    # 4-tournament panel if a combined file exists (futures predate crypto)
    p4=os.path.join(P4,"all_panel_4tourn.parquet")
    if os.path.exists(p4):
        d4=pd.read_parquet(p4); specs.append(("Own-team pooled, FX-only (4 tourn.)",["6E","6B","6J"],d4))
    for lab,instr,src in specs:
        s=prep(src,instr)
        pasy=asy_p(s); bhat,t_obs,pwb,G=wcr(s)
        days=int(s.loc[s.own_match==1,"date"].nunique())
        rows.append(dict(cell=lab,match_days=days,effect_pct=round(np.expm1(bhat)*100,1),
                         t=round(t_obs,2),p_asymptotic=round(pasy,4),p_wildboot=round(pwb,4)))
        print(f"{lab:42s} days={days:3d} eff={np.expm1(bhat)*100:+5.1f}% p_asy={pasy:.4f} p_wb={pwb:.4f}")
    pd.DataFrame(rows).to_csv(os.path.join(OUT,"pooled_bootstrap.csv"),index=False)
    print("Wrote analysis/out/pooled_bootstrap.csv")
if __name__=="__main__":
    main()
