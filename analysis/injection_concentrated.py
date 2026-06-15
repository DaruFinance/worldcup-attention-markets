#!/usr/bin/env python3
"""
Positive-control, CONCENTRATED variant. The companion injection_power.py injects a HOMOGENEOUS
during-match decline (the same multiplicative shift on every match-minute) and so bounds the
design's power against a UNIFORM effect. But Ehrmann-Jansen's effect is largest "at the most
attentive moments" -- it is concentrated, not uniform. A real effect of the same average
magnitude but concentrated in a fraction of the in-play window leaves more within-cluster
residual variance, which inflates the date-clustered standard error and lowers the power of the
whole-window Match estimator even though its point estimate stays unbiased for the average.

This script quantifies that. For each well-powered cell we inject a known AVERAGE during-match
decline (-30% or -45%, the literature's range) but place it only on a fraction phi of each
match-day's in-play minutes, with per-minute magnitude delta/phi so the average over the window
is exactly delta. We then re-estimate beta with the same date-clustered inference and record the
mean recovered effect (should still equal delta -- unbiased for the average) and the power at the
5% level. phi=1.00 reproduces the uniform Table-5 figure; phi=0.25 and phi=0.10 concentrate the
same average into a quarter and a tenth of the window.

Out: analysis/out/injection_concentrated.csv
"""
import os, warnings, collections; warnings.simplefilter("ignore")
os.environ.setdefault("OPENBLAS_NUM_THREADS","1"); os.environ.setdefault("OMP_NUM_THREADS","1")
import numpy as np, pandas as pd
ROOT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"..")
PANEL=os.path.join(ROOT,"data","market","panel","all_panel.parquet")
OUT=os.path.join(ROOT,"analysis","out"); os.makedirs(OUT,exist_ok=True)
rng=np.random.default_rng(20260615)
OWN={"ES":"any_usa_i","NQ":"any_usa_i","6E":"any_euro_i","6B":"any_gbp_i","6J":"any_jpy_i"}
DELTAS=[np.log(0.70), np.log(0.55)]   # -30%, -45% average
DLAB={round(np.log(0.70),4):"-30%", round(np.log(0.55),4):"-45%"}
PHIS=[1.00, 0.25, 0.10]
B=2000

def demean(x,c1,c2,iters=60,tol=1e-10):
    x=np.asarray(x,float).copy()
    n1=np.bincount(c1); n2=np.bincount(c2)
    for _ in range(iters):
        x0=x.copy()
        x-=np.bincount(c1,x)[c1]/n1[c1]
        x-=np.bincount(c2,x)[c2]/n2[c2]
        if np.max(np.abs(x-x0))<tol: break
    return x

def prep(d, instruments, treat):
    s=d[d.instrument.isin(instruments)].dropna(subset=["lvol"]).copy()
    if treat=="own_match":
        s["own_flag"]=0
        for inst,flag in OWN.items():
            m=s.instrument==inst; s.loc[m,"own_flag"]=s.loc[m,flag].values
        s["t"]=s["match"]*s["own_flag"]; s["f"]=s["match"]*(1-s["own_flag"])
    else:
        s["t"]=s["match"].astype(float); s["f"]=0.0
    c1=pd.factorize((s.instrument.astype(str)+"_"+s.wd_mod.astype(str)).values)[0]
    c2,uniq=pd.factorize(s.date.values); G=len(uniq)
    fvec=demean(s["f"].values,c1,c2); ff=float(fvec@fvec)
    def resid(vec):
        v=demean(np.asarray(vec,float),c1,c2)
        if ff>1e-12: v=v-(fvec@v)/ff*fvec
        return v
    y=resid(s.lvol.values); t=resid(s["t"].values)
    treated=(s["t"].values>0)
    return y,t,c2,G,resid,treated

def select_indicator(treated, c2, phi):
    """Within each treated match-day cluster, mark the first ceil(phi*n) treated minutes."""
    sel=np.zeros(len(treated))
    by=collections.defaultdict(list)
    for i in np.where(treated)[0]: by[c2[i]].append(i)
    for cl,idxs in by.items():
        k=max(1,int(np.ceil(phi*len(idxs))))
        for i in idxs[:k]: sel[i]=1.0
    return sel

def run(y,t,c2,G,resid,treated,dl,phi):
    tt=float(t@t); e0=y-((t@y)/tt)*t
    g0=resid(select_indicator(treated,c2,phi))
    rej=0; bs=np.empty(B)
    for b in range(B):
        w=rng.choice([-1.0,1.0],size=G)[c2]
        ysim=(dl/phi)*g0 + w*e0
        bhat=float(t@ysim)/tt; e=ysim-bhat*t
        sm=np.bincount(c2,t*e,minlength=G); se=np.sqrt(sm@sm)/tt*np.sqrt(G/(G-1))
        bs[b]=bhat
        if se>0 and abs(bhat/se)>1.96: rej+=1
    return np.expm1(np.mean(bs))*100, rej/B

def main():
    d=pd.read_parquet(PANEL); d=d[d.tournament.isin([2018,2022])]
    cells=[("Crypto spot (Match)",["BTCUSDT_spot","ETHUSDT_spot"],"match"),
           ("Equity-index futures (Match)",["ES","NQ"],"match"),
           ("FX futures (Match)",["6E","6B","6J"],"match"),
           ("Own-team futures, pooled",list(OWN),"own_match")]
    out=[]
    for lab,instr,treat in cells:
        y,t,c2,G,resid,treated=prep(d,instr,treat)
        line={"cell":lab,"clusters":int(pd.Series(c2[treated]).nunique())}
        msg=[f"{lab:30s} clust={line['clusters']:3d}"]
        for dl in DELTAS:
            for phi in PHIS:
                rec,pw=run(y,t,c2,G,resid,treated,dl,phi)
                tag=DLAB[round(dl,4)]
                line[f"power_{tag}_phi{int(phi*100)}"]=round(pw,3)
                line[f"recover_{tag}_phi{int(phi*100)}"]=round(rec,1)
                msg.append(f"{tag}/phi{phi:.2f}:pw={pw:.2f}(rec{rec:+.0f}%)")
        out.append(line); print(" | ".join(msg))
    res=pd.DataFrame(out); res.to_csv(os.path.join(OUT,"injection_concentrated.csv"),index=False)
    print("\nSame AVERAGE effect, concentrated into fraction phi of the in-play window.")
    print("Wrote analysis/out/injection_concentrated.csv")
    return res

if __name__=="__main__":
    main()
