#!/usr/bin/env python3
"""Do high-stakes (elimination / must-win) matches move markets more? Uses the constructed
match_importance flags (elim_possible, must_win). Pooled futures (2010-2022) + crypto (2018/22),
matched-control FE, clustered by date. Distraction would predict a larger effect when a match is
do-or-die. Out: analysis/out/stakes.csv"""
import os, warnings
warnings.simplefilter("ignore")
os.environ.setdefault("OPENBLAS_NUM_THREADS","1"); os.environ.setdefault("OMP_NUM_THREADS","1")
import numpy as np, pandas as pd
from pyfixest.estimation import feols
ROOT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"..")
FUT=os.path.join(ROOT,"data","market","futures"); CRY=os.path.join(ROOT,"data","market","crypto")
MDIR=os.path.join(ROOT,"data","matches"); OUT=os.path.join(ROOT,"analysis","out")

def spine_imp():
    a=pd.read_parquet(os.path.join(MDIR,"matches_all.parquet")); a=a[a.tournament.isin([2018,2022])]
    h=pd.read_parquet(os.path.join(MDIR,"matches_hist.parquet"))
    c=["tournament","kickoff_utc","played","home","away","knockout"]
    m=pd.concat([a[c],h[c]],ignore_index=True); m=m[m.played==True].copy()
    m["ko"]=pd.to_datetime(m["kickoff_utc"],utc=True)
    imp=pd.read_parquet(os.path.join(MDIR,"match_importance.parquet")) if os.path.exists(os.path.join(MDIR,"match_importance.parquet")) else None
    m["stakes"]=m["knockout"].astype(int)  # knockout = do-or-die baseline
    if imp is not None and {"must_win_home","must_win_away","elim_possible"}.issubset(imp.columns):
        # join by tournament + teams
        def norm(t):
            import re; al={"south korea":"korea republic","united states":"usa"}; t=str(t).lower().strip(); return al.get(t,re.sub(r"[^a-z]","",t))
        imp["k"]=imp.apply(lambda r:(int(r.get("tournament",0)),frozenset({norm(r.get("home","")),norm(r.get("away",""))})),axis=1)
        ik={r.k:(bool(getattr(r,"must_win_home",False)) or bool(getattr(r,"must_win_away",False))) for r in imp.itertuples()}
        m["k"]=m.apply(lambda r:(int(r.tournament),frozenset({norm(r.home),norm(r.away)})),axis=1)
        m["stakes"]=m.apply(lambda r: int(r.knockout or ik.get(r.k,False)),axis=1)
    return m

def minute_feats(m):
    rows=[]
    for _,r in m.iterrows():
        for t in pd.date_range(r.ko,r.ko+pd.Timedelta(minutes=104),freq="1min"):
            rows.append((t,r.stakes))
    f=pd.DataFrame(rows,columns=["ts","stk"]).groupby("ts").stk.max().reset_index()
    f["match"]=1; return f

def windows(m):
    w={}
    for t in (2010,2014,2018,2022):
        kt=m.loc[m.ko.dt.year==t,"ko"]
        if len(kt): w[t]=(kt.min().normalize()-pd.Timedelta(days=21),kt.max().normalize()+pd.Timedelta(days=22))
    return w

def load(p, wins, feat, vol, rth=False):
    d=pd.read_parquet(p); d["ts"]=pd.to_datetime(d["ts"],utc=True).dt.floor("min")
    v=d[vol].astype(float); d["lvol"]=np.log(v.where(v>0))
    keep=pd.Series(False,index=d.index)
    for a,b in wins.values(): keep|=(d["ts"]>=a)&(d["ts"]<b)
    d=d[keep].copy()
    if rth:
        et=d["ts"].dt.tz_convert("America/New_York"); mod=et.dt.hour*60+et.dt.minute; d=d[(mod>=570)&(mod<960)].copy()
    if not len(d): return None
    d=d.merge(feat,on="ts",how="left"); d["match"]=d["match"].fillna(0).astype(int); d["stk"]=d["stk"].fillna(0).astype(int)
    d["m_stakes"]=d["match"]*d["stk"]
    d["weekday"]=d["ts"].dt.weekday; d["mod"]=d["ts"].dt.hour*60+d["ts"].dt.minute
    d["wd_mod"]=d["weekday"].astype(str)+"_"+d["mod"].astype(str); d["date"]=d["ts"].dt.strftime("%Y-%m-%d")
    return d

def main():
    m=spine_imp(); feat=minute_feats(m); wins=windows(m)
    rows=[]
    for grp,insts,sub_w,vol,rth in [
        ("futures",["ES","NQ","GC","CL","6E","6B","6J"],wins,"volume",False),
        ("crypto",["BTCUSDT_spot","ETHUSDT_spot","BTCUSDT_perp","ETHUSDT_perp"],{t:wins[t] for t in (2018,2022) if t in wins},"quote_volume",False)]:
        parts=[]
        for inst in insts:
            p=(os.path.join(FUT,f"{inst}_1m.parquet") if grp=="futures"
               else os.path.join(CRY,inst.split("_")[1],f"{inst.split('_')[0]}_1m.parquet"))
            if not os.path.exists(p): continue
            d=load(p,sub_w,feat,vol,rth)
            if d is not None: d["instrument"]=inst; parts.append(d[["ts","instrument","lvol","match","m_stakes","wd_mod","date"]])
        if not parts: continue
        panel=pd.concat(parts,ignore_index=True); s=panel.dropna(subset=["lvol"]); s=s[np.isfinite(s.lvol)]
        mm=feols("lvol ~ match + m_stakes | instrument^wd_mod + date", data=s, vcov={"CRV1":"date"})
        for v,lab in [("match",f"{grp}: match"),("m_stakes",f"{grp}: x do-or-die")]:
            r=mm.tidy().loc[v]; rows.append(dict(term=lab,coef=round(r["Estimate"],4),pct=round(np.expm1(r["Estimate"])*100,1),se=round(r["Std. Error"],4),p=round(r["Pr(>|t|)"],4)))
    res=pd.DataFrame(rows); res.to_csv(os.path.join(OUT,"stakes.csv"),index=False)
    print(res.to_string(index=False)); print("\ndo-or-die interaction ~0 => high-stakes matches don't move markets more.")
    return res
if __name__=="__main__":
    main()
