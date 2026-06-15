#!/usr/bin/env python3
"""
Cash-equity arm  -  the original literature's venue (national stock markets), self-contained
so it does not disturb the passed core panel. US broad ETFs (SPY/QQQ/IWM) and single-country
ETFs (EWZ/EWW/EWU/EWG/EWQ/EWP/EWJ/ARGT/EWY). Same matched-control design: instrument x
weekday x minute-of-day + date FE, clustered by date, 2018+2022.

Caveat (stated in the paper): US-listed country ETFs trade in US hours and measure US trading
of country exposure, not the home exchange. So this bounds the US-investor channel, not the
home-market channel.

Tests: (a) US cash during any match and during USA matches; (b) country ETFs pooled, own-country
team playing (own_match) vs foreign match.
Out: analysis/out/cash_equity.csv
"""
import os, sys, warnings
warnings.simplefilter("ignore")
os.environ.setdefault("OPENBLAS_NUM_THREADS","1"); os.environ.setdefault("OMP_NUM_THREADS","1")
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_panel_crypto import collapse_match_state, tournament_windows
from pyfixest.estimation import feols

ROOT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"..")
EQ=os.path.join(ROOT,"data","market","equity"); MDIR=os.path.join(ROOT,"data","matches")
OUT=os.path.join(ROOT,"analysis","out")
US=["SPY","QQQ","IWM"]
ETF_TEAMS={"EWZ":["Brazil"],"EWW":["Mexico"],"EWU":["England","Scotland"],"EWG":["Germany"],
           "EWQ":["France"],"EWP":["Spain"],"EWJ":["Japan"],"ARGT":["Argentina"],"EWY":["Korea Republic"]}

def outcomes(d):
    d=d.sort_values("ts").reset_index(drop=True); c=d["close"].astype(float)
    v=d["volume"].astype(float); n=d["count"].astype(float)
    d["ret"]=np.log(c/c.shift(1)); d["absret"]=d["ret"].abs()
    d["lvol"]=np.log(v.where(v>0)); d["ltrades"]=np.log(n.where(n>0))
    hl=np.log(d["high"].astype(float)/d["low"].astype(float)); d["hlrange"]=hl.where(hl>=0)
    return d

def team_inmatch_minutes():
    """team -> set of in-match UTC minutes (Timestamp), from played 2018/2022 matches."""
    m=pd.read_parquet(os.path.join(MDIR,"matches_all.parquet"))
    m=m[(m["tournament"].isin([2018,2022]))&(m["played"])].copy()
    m["ko"]=pd.to_datetime(m["kickoff_utc"],utc=True)
    d={}
    for _,r in m.iterrows():
        mins=pd.date_range(r["ko"], r["ko"]+pd.Timedelta(minutes=104), freq="1min")
        for t in (r["home"],r["away"]):
            d.setdefault(t,set()).update(mins)
    return d

def load(tickers, feat, wins, tmins=None, own_teams=None, rth_only=True):
    parts=[]
    for tk in tickers:
        p=os.path.join(EQ,f"{tk}_1m.parquet")
        if not os.path.exists(p): continue
        d=pd.read_parquet(p); d["ts"]=pd.to_datetime(d["ts"],utc=True); d=outcomes(d)
        keep=pd.Series(False,index=d.index)
        for t,(a,b) in wins.items():
            keep|=(d["ts"]>=a)&(d["ts"]<b)
        d["tournament"]=pd.NA
        for t,(a,b) in wins.items():
            d.loc[(d["ts"]>=a)&(d["ts"]<b),"tournament"]=t
        d=d[keep].copy()
        if not len(d): continue
        if rth_only:   # regular US trading hours only (ET 09:30-16:00)  -  extended hours are
            et=d["ts"].dt.tz_convert("America/New_York")   # ultra-thin and drive composition artifacts
            mod=et.dt.hour*60+et.dt.minute
            d=d[(mod>=570)&(mod<960)].copy()
        if not len(d): continue
        d=d.merge(feat.drop(columns=["tournament"]),left_on="ts",right_on="minute_utc",how="left")
        d["any_match"]=d["any_match"].fillna(False).astype(bool); d["match"]=d["any_match"].astype(int)
        d["any_usa_i"]=d["any_usa"].fillna(False).astype(int)
        if own_teams is not None:
            teams=ETF_TEAMS[tk]; om=set().union(*[tmins.get(t,set()) for t in teams])
            d["own"]=d["ts"].isin(om).astype(int)
            d["own_match"]=d["match"]*d["own"]; d["foreign_match"]=d["match"]*(1-d["own"])
        d["instrument"]=tk
        d["weekday"]=d["ts"].dt.weekday; d["minute_of_day"]=d["ts"].dt.hour*60+d["ts"].dt.minute
        d["date"]=d["ts"].dt.strftime("%Y-%m-%d")
        d["wd_mod"]=d["weekday"].astype(str)+"_"+d["minute_of_day"].astype(str)
        parts.append(d)
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()

def reg(df, rhs, y="lvol", fe="instrument^wd_mod + date"):
    sub=df.dropna(subset=[y]); sub=sub[np.isfinite(sub[y])]
    m=feols(f"{y} ~ {rhs} | {fe}", data=sub, vcov={"CRV1":"date"})
    return m

def calendar_placebo(df, feat, days=1):
    """True same-clock +N-day placebo: a minute is placebo-treated if the SAME clock minute
    N calendar days earlier was a real match minute (not a row-shift on irregular bars)."""
    match_set=set(pd.to_datetime(feat.loc[feat["any_match"],"minute_utc"],utc=True))
    shifted=df["ts"]-pd.Timedelta(days=days)
    return shifted.isin(match_set).astype(int)

def main():
    ms=pd.read_parquet(os.path.join(MDIR,"match_state_all.parquet")); feat=collapse_match_state(ms)
    feat["minute_utc"]=pd.to_datetime(feat["minute_utc"],utc=True)
    m=pd.read_parquet(os.path.join(MDIR,"matches_all.parquet")); wins=tournament_windows(m)
    rows=[]
    # ---- US cash, REGULAR TRADING HOURS only (extended hours are ultra-thin) ----
    usd=load(US, feat, wins, rth_only=True)
    for y in ["lvol","ltrades","absret"]:
        mm=reg(usd,"match",y); r=mm.tidy().loc["match"]
        rows.append(dict(test="US cash RTH: any match", outcome=y, coef=r["Estimate"],se=r["Std. Error"],p=r["Pr(>|t|)"],n=int(mm._N)))
    # within tournament (fragility check)
    for t in (2018,2022):
        sub=usd[usd["tournament"]==t]
        mm=reg(sub,"match","ltrades"); r=mm.tidy().loc["match"]
        rows.append(dict(test=f"US cash RTH ltrades {t}-only", outcome="ltrades", coef=r["Estimate"],se=r["Std. Error"],p=r["Pr(>|t|)"],n=int(mm._N)))
    # CORRECT +1-day same-clock placebo (should be ~0 if the effect is real)
    usd["match_pbo"]=calendar_placebo(usd, feat, days=1)
    for y in ["ltrades","lvol"]:
        mm=reg(usd,"match_pbo",y); r=mm.tidy().loc["match_pbo"]
        rows.append(dict(test="US cash RTH PLACEBO +1d (same clock)", outcome=y, coef=r["Estimate"],se=r["Std. Error"],p=r["Pr(>|t|)"],n=int(mm._N)))
    # the extended-hours artifact, documented: all-session vs RTH-only ltrades
    usd_all=load(US, feat, wins, rth_only=False)
    mm=reg(usd_all,"match","ltrades"); r=mm.tidy().loc["match"]
    rows.append(dict(test="US cash ALL-SESSION ltrades (artifact)", outcome="ltrades", coef=r["Estimate"],se=r["Std. Error"],p=r["Pr(>|t|)"],n=int(mm._N)))
    usa_days=usd.loc[(usd.match==1)&(usd.any_usa_i==1),"date"].nunique()
    # ---- country ETFs pooled, RTH ----
    tmins=team_inmatch_minutes()
    etf=load(list(ETF_TEAMS), feat, wins, tmins=tmins, own_teams=True, rth_only=True)
    own_days=etf.loc[etf.get("own_match",0)==1,"date"].nunique() if len(etf) else 0
    if len(etf):
        for y in ["lvol","ltrades"]:
            mm=reg(etf,"foreign_match + own_match",y)
            for v in ["foreign_match","own_match"]:
                r=mm.tidy().loc[v]; rows.append(dict(test=f"country ETF RTH: {v}",outcome=y,coef=r["Estimate"],se=r["Std. Error"],p=r["Pr(>|t|)"],n=int(mm._N)))
    res=pd.DataFrame(rows).round(4)
    res["us_rth_match_days"]=usd.loc[usd.match==1,"date"].nunique()
    res["usa_match_days"]=usa_days; res["own_country_days"]=own_days
    res.to_csv(os.path.join(OUT,"cash_equity.csv"),index=False)
    print(res.drop(columns=["us_rth_match_days","usa_match_days","own_country_days"]).to_string(index=False))
    print(f"\nclusters: US-cash RTH match-days={usd.loc[usd.match==1,'date'].nunique()}, "
          f"USA-match-days={usa_days}, own-country-days(ETF)={own_days}")
    return res

if __name__=="__main__":
    main()
