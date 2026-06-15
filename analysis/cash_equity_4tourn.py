#!/usr/bin/env python3
"""
Cash-equity own-team test over FOUR tournaments (2010/2014/2018/2022)  -  the literature's actual
venue, with more power. Mirrors the PASSED cash_equity.py design exactly: RTH-only (ET 09:30-16:00),
matched control, correct same-clock +1-day calendar placebo. US broad ETFs (USA-playing) and the
9 country ETFs (own-country playing, pooled). Team names normalized across the two spine sources.
Out: analysis/out/cash_equity_4tourn.csv
"""
import os, sys, warnings
warnings.simplefilter("ignore")
os.environ.setdefault("OPENBLAS_NUM_THREADS","1"); os.environ.setdefault("OMP_NUM_THREADS","1")
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pyfixest.estimation import feols

ROOT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"..")
EQ=os.path.join(ROOT,"data","market","equity"); MDIR=os.path.join(ROOT,"data","matches")
OUT=os.path.join(ROOT,"analysis","out")
US=["SPY","QQQ","IWM"]
# ETF -> set of possible team-name strings across fixturedownload + openfootball
ETF_SETS={"EWZ":{"Brazil"},"EWW":{"Mexico"},"EWU":{"England","Scotland"},"EWG":{"Germany"},
          "EWQ":{"France"},"EWP":{"Spain"},"EWJ":{"Japan"},"ARGT":{"Argentina"},
          "EWY":{"Korea Republic","South Korea","Korea, South","Republic of Korea"}}
USA_NAMES={"USA","United States"}

def outcomes(d):
    d=d.sort_values("ts").reset_index(drop=True); c=d["close"].astype(float)
    v=d["volume"].astype(float); n=d["count"].astype(float)
    d["lvol"]=np.log(v.where(v>0)); d["ltrades"]=np.log(n.where(n>0)); return d

def combined_spine():
    a=pd.read_parquet(os.path.join(MDIR,"matches_all.parquet"))
    a=a[a["tournament"].isin([2018,2022])]
    h=pd.read_parquet(os.path.join(MDIR,"matches_hist.parquet"))
    c=["tournament","kickoff_utc","played","home","away"]
    m=pd.concat([a[c],h[c]],ignore_index=True); m["ko"]=pd.to_datetime(m["kickoff_utc"],utc=True)
    return m[m["played"]==True]

def team_minutes(m, teamset):
    s=set()
    for _,r in m.iterrows():
        if (r["home"] in teamset) or (r["away"] in teamset):
            s.update(pd.date_range(r["ko"], r["ko"]+pd.Timedelta(minutes=104), freq="1min"))
    return s

def match_minutes(m):
    s=set()
    for _,r in m.iterrows():
        s.update(pd.date_range(r["ko"], r["ko"]+pd.Timedelta(minutes=104), freq="1min"))
    return s

def windows(m):
    w={}
    for t,g in m.groupby("tournament"):
        w[t]=(g["ko"].min().normalize()-pd.Timedelta(days=21), g["ko"].max().normalize()+pd.Timedelta(days=22))
    return w

def load(tickers, wins, allm, own_set=None, usa_set=None):
    parts=[]
    for tk in tickers:
        p=os.path.join(EQ,f"{tk}_1m.parquet")
        if not os.path.exists(p): continue
        d=pd.read_parquet(p); d["ts"]=pd.to_datetime(d["ts"],utc=True).dt.floor("min"); d=outcomes(d)
        keep=pd.Series(False,index=d.index)
        for t,(a,b) in wins.items(): keep|=(d["ts"]>=a)&(d["ts"]<b)
        d=d[keep].copy()
        if not len(d): continue
        et=d["ts"].dt.tz_convert("America/New_York"); mod=et.dt.hour*60+et.dt.minute
        d=d[(mod>=570)&(mod<960)].copy()      # RTH only
        if not len(d): continue
        d["match"]=d["ts"].isin(allm).astype(int)
        if usa_set is not None:
            d["own"]=d["ts"].isin(usa_set).astype(int)
        else:
            d["own"]=d["ts"].isin(own_set[tk]).astype(int)
        d["own_match"]=d["match"]*d["own"]; d["foreign_match"]=d["match"]*(1-d["own"])
        d["weekday"]=d["ts"].dt.weekday; d["m"]=d["ts"].dt.hour*60+d["ts"].dt.minute
        d["wd_mod"]=d["weekday"].astype(str)+"_"+d["m"].astype(str)
        d["date"]=d["ts"].dt.strftime("%Y-%m-%d"); d["instrument"]=tk
        parts.append(d)
    return pd.concat(parts,ignore_index=True) if parts else pd.DataFrame()

def reg(df, rhs, y="lvol", fe="instrument^wd_mod + date"):
    if df["instrument"].nunique()<2: fe="wd_mod + date"
    sub=df.dropna(subset=[y]); sub=sub[np.isfinite(sub[y])]
    m=feols(f"{y} ~ {rhs} | {fe}", data=sub, vcov={"CRV1":"date"}); return m

def main():
    m=combined_spine(); allm=match_minutes(m); wins=windows(m)
    usa_min=team_minutes(m, USA_NAMES)
    own_sets={tk: team_minutes(m, s) for tk,s in ETF_SETS.items()}
    rows=[]
    # US cash: USA-playing (own) vs foreign, 4 tournaments, RTH
    usd=load(US, wins, allm, usa_set=usa_min)
    usa_days=usd.loc[usd.own_match==1,"date"].nunique()
    for y in ["lvol","ltrades"]:
        mm=reg(usd,"foreign_match + own_match",y)
        for v in ["foreign_match","own_match"]:
            r=mm.tidy().loc[v]; rows.append(dict(test=f"US cash 4T: {v}",outcome=y,coef=round(r["Estimate"],4),se=round(r["Std. Error"],4),p=round(r["Pr(>|t|)"],4),n=int(mm._N)))
    # placebo (same-clock +1 day) on US own_match
    usd2=usd.copy(); shifted=usd2["ts"]-pd.Timedelta(days=1)
    usd2["own_match"]=(shifted.isin(usa_min) & shifted.isin(allm)).astype(int)
    mm=reg(usd2,"own_match","ltrades"); r=mm.tidy().loc["own_match"]
    rows.append(dict(test="US cash 4T PLACEBO +1d",outcome="ltrades",coef=round(r["Estimate"],4),se=round(r["Std. Error"],4),p=round(r["Pr(>|t|)"],4),n=int(mm._N)))
    # country ETFs pooled, own-country, 4 tournaments
    etf=load(list(ETF_SETS), wins, allm, own_set=own_sets)
    own_days=etf.loc[etf.own_match==1,"date"].nunique()
    for y in ["lvol","ltrades"]:
        mm=reg(etf,"foreign_match + own_match",y)
        for v in ["foreign_match","own_match"]:
            r=mm.tidy().loc[v]; rows.append(dict(test=f"country ETF 4T: {v}",outcome=y,coef=round(r["Estimate"],4),se=round(r["Std. Error"],4),p=round(r["Pr(>|t|)"],4),n=int(mm._N)))
    res=pd.DataFrame(rows); res["usa_own_days"]=usa_days; res["etf_own_days"]=own_days
    res.to_csv(os.path.join(OUT,"cash_equity_4tourn.csv"),index=False)
    print(res.drop(columns=["usa_own_days","etf_own_days"]).to_string(index=False))
    print(f"\nUSA-playing RTH own-days (4T): {usa_days}  | country-ETF own-country RTH own-days (4T): {own_days}")
    return res

if __name__=="__main__":
    main()
