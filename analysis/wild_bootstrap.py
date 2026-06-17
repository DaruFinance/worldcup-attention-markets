#!/usr/bin/env python3
"""
Wild-cluster restricted bootstrap (Cameron-Gelbach-Miller) for the own-team cells, to replace the asserted
"few-cluster cells over-reject" with an exact small-sample p-value. For each cell we residualize the
outcome and the own-team indicator on the fixed effects and the foreign-match control (Frisch-Waugh), then
impose the null and resample cluster-wise Rademacher signs over match-days (B=4999). The prediction: the
few-cluster mirages (sterling on ~6-10 days, Nasdaq on ~2) get an inflated bootstrap p and are no longer
significant, while the well-powered euro cell (60 days) is unchanged. Out: analysis/out/wild_bootstrap.csv
"""
import os, warnings; warnings.simplefilter("ignore")
os.environ.setdefault("OPENBLAS_NUM_THREADS","1")
import numpy as np, pandas as pd
from pyfixest.estimation import feols
R=os.path.join(os.path.dirname(os.path.abspath(__file__)),"..")
FUT=os.path.join(R,"data","market","futures"); MD=os.path.join(R,"data","matches"); O=os.path.join(R,"analysis","out")
rng=np.random.default_rng(12345)
EURO={"Germany","France","Spain","Netherlands","Belgium","Portugal","Italy","Croatia","Austria"}

def spine():
    a=pd.read_parquet(os.path.join(MD,"matches_all.parquet")); a=a[a.tournament.isin([2018,2022])]
    h=pd.read_parquet(os.path.join(MD,"matches_hist.parquet"))
    c=["tournament","kickoff_utc","home","away","played"]; m=pd.concat([a[c],h[c]],ignore_index=True)
    m=m[m.played==True].copy(); m["ko"]=pd.to_datetime(m["kickoff_utc"],utc=True); return m

def windows(m):
    w={}
    for t in (2010,2014,2018,2022):
        k=m.loc[m.ko.dt.year==t,"ko"]
        if len(k): w[t]=(k.min().normalize()-pd.Timedelta(days=21),k.max().normalize()+pd.Timedelta(days=22))
    return w

def minset(m, teams):
    s=set()
    for _,r in m.iterrows():
        if (r.home in teams) or (r.away in teams):
            s.update(pd.date_range(r.ko,r.ko+pd.Timedelta(minutes=104),freq="1min"))
    return s

def build(inst, teams, m, wins):
    fp=os.path.join(FUT,f"{inst}_1m.parquet")
    if not os.path.exists(fp): return None
    d=pd.read_parquet(fp); d["ts"]=pd.to_datetime(d["ts"],utc=True).dt.floor("min")
    v=d["volume"].astype(float); d["lvol"]=np.log(v.where(v>0))
    keep=pd.Series(False,index=d.index)
    for a,b in wins.values(): keep|=(d.ts>=a)&(d.ts<b)
    d=d[keep].dropna(subset=["lvol"]).copy()
    own=minset(m,teams); allm=minset(m, set(m.home)|set(m.away))
    d["own"]=d.ts.isin(own).astype(int); d["anym"]=d.ts.isin(allm).astype(int)
    d["own_match"]=d.own*d.anym; d["foreign_match"]=(1-d.own)*d.anym
    d["wd_mod"]=d.ts.dt.weekday.astype(str)+"_"+(d.ts.dt.hour*60+d.ts.dt.minute).astype(str)
    d["date"]=d.ts.dt.strftime("%Y-%m-%d")
    return d

def demean(x, c1, c2, iters=50, tol=1e-9):
    """two-way fixed-effect residualization by alternating group-mean removal (fully length-aligned)."""
    x=np.asarray(x,float).copy()
    for _ in range(iters):
        x0=x.copy()
        x-=np.bincount(c1,x)[c1]/np.bincount(c1)[c1]
        x-=np.bincount(c2,x)[c2]/np.bincount(c2)[c2]
        if np.max(np.abs(x-x0))<tol: break
    return x

def wcr_boot(df, B=4999):
    """FWL on own_match controlling foreign_match + two-way FE, wild-cluster restricted bootstrap by date."""
    c1=pd.factorize(df["wd_mod"].values)[0]; c2,uniq=pd.factorize(df["date"].values)
    G=len(uniq)
    y=demean(df["lvol"].values,c1,c2); t=demean(df["own_match"].values,c1,c2); f=demean(df["foreign_match"].values,c1,c2)
    # partial foreign_match out of both y and t
    ff=f@f
    if ff>0: y=y-(f@y)/ff*f; t=t-(f@t)/ff*f
    tt=t@t; bhat=(t@y)/tt
    def tstat(u):
        b=(t@u)/tt; e=u-b*t; s=np.bincount(c2,t*e,minlength=G)
        se=np.sqrt((s@s))/tt*np.sqrt(G/(G-1)); return b/se if se>0 else np.nan, b
    t_obs,_=tstat(y)
    u0=y.copy(); cnt=0
    for _ in range(B):
        w=rng.choice([-1.0,1.0],size=G)[c2]
        tb,_=tstat(w*u0)
        if abs(tb)>=abs(t_obs): cnt+=1
    return bhat, t_obs, (cnt+1)/(B+1), G

def main():
    m=spine(); wins=windows(m)
    cells=[("6B","England (sterling)",{"England","Scotland","Wales"}),
           ("6E","euro-area (euro)",EURO),
           ("NQ","USA (Nasdaq)",{"United States","USA"}),
           ("ES","USA (S&P)",{"United States","USA"})]
    rows=[]
    for inst,lab,teams in cells:
        d=build(inst,teams,m,wins)
        if d is None or d.own_match.sum()<30: print(f"skip {lab}"); continue
        # asymptotic clustered p from pyfixest for reference
        mm=feols("lvol ~ foreign_match + own_match | wd_mod + date", data=d, vcov={"CRV1":"date"})
        r=mm.tidy().loc["own_match"]; p_asy=r["Pr(>|t|)"]
        bhat,t_obs,p_boot,G=wcr_boot(d)
        rows.append(dict(cell=lab,instrument=inst,own_match_days=int(d.loc[d.own_match==1,"date"].nunique()),
                         effect_pct=round(np.expm1(bhat)*100,1),t=round(t_obs,2),
                         p_asymptotic=round(float(p_asy),4),p_wildboot=round(p_boot,4)))
        print(f"{lab:22s} days={int(d.loc[d.own_match==1,'date'].nunique()):3d}  eff={np.expm1(bhat)*100:+6.1f}%  p_asy={float(p_asy):.4f}  p_wildboot={p_boot:.4f}")
    res=pd.DataFrame(rows); res.to_csv(os.path.join(O,"wild_bootstrap.csv"),index=False)
    print("\nReading: cells where p_asymptotic is significant but p_wildboot is not are the few-cluster mirages.")
    return res
if __name__=="__main__":
    main()
