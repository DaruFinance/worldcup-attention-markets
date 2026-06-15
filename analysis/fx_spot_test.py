#!/usr/bin/env python3
"""
FX-SPOT arm. Decentralized retail spot FX (Dukascopy) vs the centralized CME FX futures (6E/6B/6J)
already tested. Outcome = log(tick_count) = quote/price-update activity (NOT true traded volume  -  retail
FX has no consolidated tape; we label it tick-volume per the spec's warning). Matched-control design,
completed tournaments 2010-2022, SE clustered by date. Also a domestic cut (EUR pairs × euro-area team,
GBP × England/Scotland, JPY × Japan).
Out: analysis/out/fx_spot.csv
"""
import os, warnings
warnings.simplefilter("ignore")
os.environ.setdefault("OPENBLAS_NUM_THREADS","1"); os.environ.setdefault("OMP_NUM_THREADS","1")
import numpy as np, pandas as pd
from pyfixest.estimation import feols
ROOT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"..")
FX=os.path.join(ROOT,"data","market","fx_spot"); MDIR=os.path.join(ROOT,"data","matches"); OUT=os.path.join(ROOT,"analysis","out")
PAIRS=["EURUSD","GBPUSD","USDJPY","USDCHF","USDCAD","AUDUSD","USDMXN"]  # BRL excluded (sparse)
# pair -> domestic team set
DOM={"EURUSD":{"Germany","France","Spain","Netherlands","Belgium","Portugal","Italy","Croatia","Austria"},
     "GBPUSD":{"England","Scotland"}, "USDJPY":{"Japan"}, "USDMXN":{"Mexico"}, "USDCAD":{"Canada"}}

def spine():
    a=pd.read_parquet(os.path.join(MDIR,"matches_all.parquet")); a=a[a.tournament.isin([2018,2022])]
    h=pd.read_parquet(os.path.join(MDIR,"matches_hist.parquet"))
    c=["tournament","kickoff_utc","played","home","away"]
    m=pd.concat([a[c],h[c]],ignore_index=True); m=m[m.played==True].copy()
    m["ko"]=pd.to_datetime(m["kickoff_utc"],utc=True); return m

def all_min(m):
    s=set()
    for k in m["ko"]: s.update(pd.date_range(k,k+pd.Timedelta(minutes=104),freq="1min"))
    return s
def team_min(m,teams):
    s=set()
    for _,r in m.iterrows():
        if (r.home in teams) or (r.away in teams): s.update(pd.date_range(r.ko,r.ko+pd.Timedelta(minutes=104),freq="1min"))
    return s
def windows(m):
    w={}
    for t in (2010,2014,2018,2022):
        kt=m.loc[m.ko.dt.year==t,"ko"]
        if len(kt): w[t]=(kt.min().normalize()-pd.Timedelta(days=21),kt.max().normalize()+pd.Timedelta(days=22))
    return w

def main():
    m=spine(); allm=all_min(m); wins=windows(m)
    dom_min={p:team_min(m,DOM[p]) for p in PAIRS if p in DOM}
    parts=[]
    for p in PAIRS:
        fp=os.path.join(FX,f"{p}_1m.parquet")
        if not os.path.exists(fp): continue
        d=pd.read_parquet(fp); d["ts"]=pd.to_datetime(d["ts"],utc=True).dt.floor("min")
        if "tick_count" not in d: continue
        d["ltick"]=np.log(d["tick_count"].astype(float).where(d["tick_count"]>0))
        keep=pd.Series(False,index=d.index)
        for a,b in wins.values(): keep|=(d["ts"]>=a)&(d["ts"]<b)
        d=d[keep].copy()
        if not len(d): continue
        d["match"]=d["ts"].isin(allm).astype(int)
        d["own"]=d["ts"].isin(dom_min[p]).astype(int) if p in dom_min else 0
        d["own_match"]=d["match"]*d["own"]; d["foreign_match"]=d["match"]*(1-d["own"])
        d["weekday"]=d["ts"].dt.weekday; d["mod"]=d["ts"].dt.hour*60+d["ts"].dt.minute
        d["wd_mod"]=d["weekday"].astype(str)+"_"+d["mod"].astype(str); d["date"]=d["ts"].dt.strftime("%Y-%m-%d"); d["instrument"]=p
        parts.append(d[["ts","instrument","ltick","match","own_match","foreign_match","wd_mod","date"]])
    panel=pd.concat(parts,ignore_index=True); s=panel.dropna(subset=["ltick"]); s=s[np.isfinite(s.ltick)]
    rows=[]
    m1=feols("ltick ~ match | instrument^wd_mod + date", data=s, vcov={"CRV1":"date"}); r=m1.tidy().loc["match"]
    rows.append(dict(test="FX spot: during-match (tick activity)",coef=round(r["Estimate"],4),pct=round(np.expm1(r["Estimate"])*100,2),se=round(r["Std. Error"],4),p=round(r["Pr(>|t|)"],4),n=int(m1._N)))
    m2=feols("ltick ~ foreign_match + own_match | instrument^wd_mod + date", data=s, vcov={"CRV1":"date"})
    for v in ["foreign_match","own_match"]:
        rr=m2.tidy().loc[v]; rows.append(dict(test=f"FX spot: {v}",coef=round(rr["Estimate"],4),pct=round(np.expm1(rr["Estimate"])*100,2),se=round(rr["Std. Error"],4),p=round(rr["Pr(>|t|)"],4),n=int(m2._N)))
    own_days=s.loc[s.own_match==1,"date"].nunique()
    res=pd.DataFrame(rows); res["own_match_days"]=own_days
    res.to_csv(os.path.join(OUT,"fx_spot.csv"),index=False)
    print(res.to_string(index=False)); print(f"\nFX-spot own-team match-days: {own_days}. tick_count = quote activity, NOT true traded volume.")
    return res
if __name__=="__main__":
    main()
