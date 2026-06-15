#!/usr/bin/env python3
"""
Positive-control power check. A null is only informative if the estimator could have caught a real
effect at the realized cluster counts. We never observe the distraction effect where it is known to
exist (no free foreign intraday data), so we inject one into our OWN real panels and check recovery.

For each headline cell we residualize the real outcome on the design's fixed effects and foreign control
(Frisch-Waugh), take the real residuals, and generate B synthetic panels of the form
    y_sim = delta * treat + (Rademacher cluster sign) * residual,
i.e. the true coefficient is exactly `delta` and the noise is the panel's own clustered residual. We then
re-estimate beta with the same date-clustered inference and record (i) the mean recovered effect, which
should equal delta if the estimator is unbiased, and (ii) the rejection rate at the 5% level, which is the
empirical POWER against an effect of that size at this cell's real cluster count. delta=0 returns the
empirical SIZE (should sit near 5%).

delta is in log points: a -30% effect is log(0.70)=-0.357, a -45% effect is log(0.55)=-0.598 -- the
Ehrmann-Jansen 45-55% range. If the well-powered cells recover -30%/-45% with high power, their during-match
nulls are real nulls and not a dead estimator; cells that cannot are flagged as underpowered, not as evidence.
Out: analysis/out/injection_power.csv
"""
import os, warnings; warnings.simplefilter("ignore")
os.environ.setdefault("OPENBLAS_NUM_THREADS","1"); os.environ.setdefault("OMP_NUM_THREADS","1")
import numpy as np, pandas as pd
ROOT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"..")
PANEL=os.path.join(ROOT,"data","market","panel","all_panel.parquet")
OUT=os.path.join(ROOT,"analysis","out"); os.makedirs(OUT,exist_ok=True)
rng=np.random.default_rng(20260615)
OWN={"ES":"any_usa_i","NQ":"any_usa_i","6E":"any_euro_i","6B":"any_gbp_i","6J":"any_jpy_i"}
DELTAS=[0.0, np.log(0.90), np.log(0.70), np.log(0.55)]   # 0, -10%, -30%, -45%
DLAB ={0.0:"0% (size)", round(np.log(0.90),3):"-10%", round(np.log(0.70),3):"-30%", round(np.log(0.55),3):"-45%"}
B=2000

def demean(x,c1,c2,iters=60,tol=1e-10):
    x=np.asarray(x,float).copy()
    for _ in range(iters):
        x0=x.copy()
        x-=np.bincount(c1,x)[c1]/np.bincount(c1)[c1]
        x-=np.bincount(c2,x)[c2]/np.bincount(c2)[c2]
        if np.max(np.abs(x-x0))<tol: break
    return x

def prep_cell(d, instruments, treat):
    """Return residualized (y, t, cluster-index, G) after partialling foreign_match + (instrument^wd_mod, date)."""
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
    y=demean(s.lvol.values,c1,c2); t=demean(s["t"].values,c1,c2); f=demean(s["f"].values,c1,c2)
    if np.dot(f,f)>1e-12:
        ff=f@f; y=y-(f@y)/ff*f; t=t-(f@t)/ff*f
    treated_clusters=int(s.loc[s["t"]>0,"date"].nunique())
    return y,t,c2,G,treated_clusters

def power_curve(y,t,c2,G):
    tt=t@t
    e0=y-((t@y)/tt)*t                 # real residual (real beta ~ 0 for these nulls)
    def cl_se(tv,ev):
        s=np.bincount(c2, tv*ev, minlength=G); return np.sqrt(s@s)/tt*np.sqrt(G/(G-1))
    rows={}
    for dl in DELTAS:
        rej=0; bs=np.empty(B)
        for b in range(B):
            w=rng.choice([-1.0,1.0],size=G)[c2]
            ysim=dl*t + w*e0
            bhat=(t@ysim)/tt; e=ysim-bhat*t; se=cl_se(t,e)
            bs[b]=bhat
            if se>0 and abs(bhat/se)>1.96: rej+=1
        rows[dl]=(np.expm1(np.mean(bs))*100, rej/B)
    return rows

def main():
    d=pd.read_parquet(PANEL); d=d[d.tournament.isin([2018,2022])]
    cells=[("Crypto spot (Match)",["BTCUSDT_spot","ETHUSDT_spot"],"match"),
           ("Crypto perp (Match)",["BTCUSDT_perp","ETHUSDT_perp"],"match"),
           ("Equity-index futures (Match)",["ES","NQ"],"match"),
           ("FX futures (Match)",["6E","6B","6J"],"match"),
           ("Own-team futures, pooled",list(OWN),"own_match"),
           ("Own-team FX-only, pooled",["6E","6B","6J"],"own_match"),
           ("Sterling 6B, England own",["6B"],"own_match")]
    out=[]
    for lab,instr,treat in cells:
        y,t,c2,G,tc=prep_cell(d,instr,treat)
        pc=power_curve(y,t,c2,G)
        line={"cell":lab,"treated_clusters":tc}
        for dl in DELTAS:
            rec,pw=pc[dl]; tag=DLAB[round(dl,3)]
            line[f"recover_{tag}"]=round(rec,1); line[f"power_{tag}"]=round(pw,3)
        out.append(line)
        print(f"{lab:32s} clusters={tc:3d} | "
              +" ".join(f"{DLAB[round(dl,3)]}:pw={pc[dl][1]:.2f}(rec{pc[dl][0]:+.0f}%)" for dl in DELTAS))
    res=pd.DataFrame(out); res.to_csv(os.path.join(OUT,"injection_power.csv"),index=False)
    print("\nPower against the injected effect at each cell's real cluster count. delta=0 column is empirical size.")
    print("Wrote analysis/out/injection_power.csv")
    return res
if __name__=="__main__":
    main()
