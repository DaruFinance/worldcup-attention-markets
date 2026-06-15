#!/usr/bin/env python3
"""
H2  -  liquidity. Do quoted spreads widen and displayed depth fall during World Cup matches?
Uses the AlgoSeek TAQ liquidity series (relative quoted spread in bps, top-of-book depth,
aggressor imbalance). Matched-control design: Y ~ Match | instrument x (weekday x minute-of-day)
+ date, SE clustered by date. Completed tournaments (2010/2014/2018/2022). Equity = US RTH only.
Out: analysis/out/liquidity.csv
"""
import os, warnings
warnings.simplefilter("ignore")
os.environ.setdefault("OPENBLAS_NUM_THREADS","1"); os.environ.setdefault("OMP_NUM_THREADS","1")
import numpy as np, pandas as pd
from pyfixest.estimation import feols

ROOT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"..")
LIQ=os.path.join(ROOT,"data","market","liquidity"); MDIR=os.path.join(ROOT,"data","matches")
OUT=os.path.join(ROOT,"analysis","out")
GROUPS={"ES":"equity_fut","NQ":"equity_fut","GC":"commodity_fut","CL":"commodity_fut",
        "6E":"fx_fut","6B":"fx_fut","6J":"fx_fut",
        "SPY":"equity_cash","QQQ":"equity_cash","IWM":"equity_cash",
        "EWZ":"country_etf","EWW":"country_etf","EWU":"country_etf","EWG":"country_etf",
        "EWQ":"country_etf","EWP":"country_etf","EWJ":"country_etf","EWY":"country_etf"}
EQUITY={"SPY","QQQ","IWM","EWZ","EWW","EWU","EWG","EWQ","EWP","EWJ","EWY"}

def match_minutes():
    a=pd.read_parquet(os.path.join(MDIR,"matches_all.parquet")); a=a[a.tournament.isin([2018,2022])]
    h=pd.read_parquet(os.path.join(MDIR,"matches_hist.parquet"))
    ko=pd.concat([pd.to_datetime(a["kickoff_utc"],utc=True), pd.to_datetime(h["kickoff_utc"],utc=True)])
    s=set()
    for k in ko: s.update(pd.date_range(k, k+pd.Timedelta(minutes=104), freq="1min"))
    lo=min(ko)-pd.Timedelta(days=21); hi=max(ko)+pd.Timedelta(days=22)
    # window = union of ±21d around each tournament
    wins=[]
    for t in (2010,2014,2018,2022):
        kt=ko[(ko.dt.year>=t-1)&(ko.dt.year<=t)]
        kt=kt[(kt.dt.year==t)] if t!=2022 else ko[ko.dt.year.isin([2022])]
        if len(kt): wins.append((kt.min().normalize()-pd.Timedelta(days=21), kt.max().normalize()+pd.Timedelta(days=22)))
    return s, wins

def build():
    mins, wins = match_minutes()
    parts=[]
    for inst,grp in GROUPS.items():
        p=os.path.join(LIQ,f"{inst}_1m.parquet")
        if not os.path.exists(p): continue
        d=pd.read_parquet(p); d["ts"]=pd.to_datetime(d["ts"],utc=True).dt.floor("min")
        keep=pd.Series(False,index=d.index)
        for a,b in wins: keep|=(d["ts"]>=a)&(d["ts"]<b)
        d=d[keep].copy()
        if not len(d): continue
        if inst in EQUITY:
            et=d["ts"].dt.tz_convert("America/New_York"); mod=et.dt.hour*60+et.dt.minute
            d=d[(mod>=570)&(mod<960)].copy()
        if not len(d): continue
        d["match"]=d["ts"].isin(mins).astype(int)
        d["lspread"]=np.log(d["rel_spread_bps"].where(d["rel_spread_bps"]>0))
        d["ldepth"]=np.log(d["depth"].where(d["depth"]>0))
        d["weekday"]=d["ts"].dt.weekday; d["m"]=d["ts"].dt.hour*60+d["ts"].dt.minute
        d["wd_mod"]=d["weekday"].astype(str)+"_"+d["m"].astype(str)
        d["date"]=d["ts"].dt.strftime("%Y-%m-%d"); d["instrument"]=inst; d["market_group"]=grp
        parts.append(d[["ts","instrument","market_group","match","lspread","ldepth","imbalance","date","wd_mod"]])
    return pd.concat(parts,ignore_index=True)

def est(sub,y,fe="instrument^wd_mod + date"):
    if sub["instrument"].nunique()<2: fe="wd_mod + date"
    s=sub.dropna(subset=[y]); s=s[np.isfinite(s[y])]
    m=feols(f"{y} ~ match | {fe}", data=s, vcov={"CRV1":"date"}); r=m.tidy().loc["match"]
    return dict(coef=r["Estimate"], se=r["Std. Error"], p=r["Pr(>|t|)"], n=int(m._N))

def main():
    panel=build()
    print("panel:", len(panel), "rows |", panel.groupby("market_group").size().to_dict())
    rows=[]
    for grp in ["ALL"]+sorted(panel["market_group"].unique()):
        sub=panel if grp=="ALL" else panel[panel["market_group"]==grp]
        for y,lab in [("lspread","log rel-spread (bps)"),("ldepth","log depth")]:
            try: r=est(sub,y)
            except Exception as e: continue
            rows.append(dict(group=grp, outcome=lab, pct=round(np.expm1(r["coef"])*100,2),
                             coef=round(r["coef"],4), se=round(r["se"],4), p=round(r["p"],4), n=r["n"]))
    res=pd.DataFrame(rows); res.to_csv(os.path.join(OUT,"liquidity.csv"),index=False)
    print(res.to_string(index=False))
    print("\nH2: spread coef>0 => spreads WIDEN during matches; depth coef<0 => depth FALLS.")
    return res

if __name__=="__main__":
    main()
