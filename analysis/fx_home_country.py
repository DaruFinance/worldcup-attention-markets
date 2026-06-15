#!/usr/bin/env python3
"""
HOME-COUNTRY FX test. The pooled 'FX' effect is meaningless: a currency only has a reason to react when
ITS OWN nation is playing. So test each currency ONLY against its home nation's match-minutes, never
pooled across all matches. Two outcomes per currency: activity (log tick_count for retail spot / log
volume for CME futures) and volatility (log high/low range). Decompose into own_match (home nation on
the pitch) vs foreign_match (some other match in progress) so the home effect is isolated above any
generic tournament effect. Single-instrument matched-control FE: y ~ foreign_match + own_match |
wd_mod + date, SE clustered by date. Completed tournaments only (2010-2022); BRL is 2010-only and
flagged underpowered, but it is INCLUDED, not dropped. Out: analysis/out/fx_home_country.csv
"""
import os, warnings
warnings.simplefilter("ignore")
os.environ.setdefault("OPENBLAS_NUM_THREADS","1"); os.environ.setdefault("OMP_NUM_THREADS","1")
import numpy as np, pandas as pd
from pyfixest.estimation import feols
ROOT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"..")
FX=os.path.join(ROOT,"data","market","fx_spot"); FUT=os.path.join(ROOT,"data","market","futures")
MDIR=os.path.join(ROOT,"data","matches"); OUT=os.path.join(ROOT,"analysis","out")

EURO={"Germany","France","Spain","Netherlands","Belgium","Portugal","Italy","Croatia","Austria",
      "Ireland","Greece","Slovakia","Slovenia"}
# (currency, source, file, vol_col, home-nation set, label)
SPECS=[
  ("USDBRL","spot","USDBRL_1m.parquet","tick_count",{"Brazil"},                  "Brazil"),
  ("USDMXN","spot","USDMXN_1m.parquet","tick_count",{"Mexico"},                  "Mexico"),
  ("USDJPY","spot","USDJPY_1m.parquet","tick_count",{"Japan"},                   "Japan"),
  ("AUDUSD","spot","AUDUSD_1m.parquet","tick_count",{"Australia"},               "Australia"),
  ("USDCAD","spot","USDCAD_1m.parquet","tick_count",{"Canada"},                  "Canada"),
  ("USDCHF","spot","USDCHF_1m.parquet","tick_count",{"Switzerland"},             "Switzerland"),
  ("GBPUSD","spot","GBPUSD_1m.parquet","tick_count",{"England"},                 "England"),
  ("EURUSD","spot","EURUSD_1m.parquet","tick_count",EURO,                        "euro-area"),
  ("6J","fut","6J_1m.parquet","volume",{"Japan"},                               "Japan (CME fut)"),
  ("6B","fut","6B_1m.parquet","volume",{"England"},                             "England (CME fut)"),
  ("6E","fut","6E_1m.parquet","volume",EURO,                                    "euro-area (CME fut)"),
]

def spine():
    a=pd.read_parquet(os.path.join(MDIR,"matches_all.parquet")); a=a[a.tournament.isin([2018,2022])]
    h=pd.read_parquet(os.path.join(MDIR,"matches_hist.parquet"))
    c=["tournament","kickoff_utc","played","home","away"]
    m=pd.concat([a[c],h[c]],ignore_index=True); m=m[m.played==True].copy()
    m["ko"]=pd.to_datetime(m["kickoff_utc"],utc=True); return m

def minutes(m, mask):
    s=set()
    for _,r in m[mask].iterrows(): s.update(pd.date_range(r.ko,r.ko+pd.Timedelta(minutes=104),freq="1min"))
    return s

def windows(m):
    w={}
    for t in (2010,2014,2018,2022):
        kt=m.loc[m.ko.dt.year==t,"ko"]
        if len(kt): w[t]=(kt.min().normalize()-pd.Timedelta(days=21),kt.max().normalize()+pd.Timedelta(days=22))
    return w

def main():
    m=spine(); wins=windows(m)
    allmin=minutes(m, pd.Series(True,index=m.index))
    rows=[]
    for cur,src,fn,vcol,home,lab in SPECS:
        fp=os.path.join(FX if src=="spot" else FUT, fn)
        if not os.path.exists(fp): continue
        d=pd.read_parquet(fp); d["ts"]=pd.to_datetime(d["ts"],utc=True).dt.floor("min")
        keep=pd.Series(False,index=d.index)
        for a,b in wins.values(): keep|=(d["ts"]>=a)&(d["ts"]<b)
        d=d[keep].copy()
        if not len(d): continue
        v=d[vcol].astype(float)
        d["act"]=np.log(v.where(v>0))
        d["vol"]=np.log((d["high"].astype(float)/d["low"].astype(float)).where(d["low"]>0))  # log hi/lo range
        home_min=minutes(m, m.apply(lambda r:(r.home in home) or (r.away in home),axis=1))
        d["own"]=d["ts"].isin(home_min).astype(int)
        d["anym"]=d["ts"].isin(allmin).astype(int)
        d["own_match"]=d["own"]*d["anym"]; d["foreign_match"]=(1-d["own"])*d["anym"]
        d["weekday"]=d["ts"].dt.weekday; d["mod"]=d["ts"].dt.hour*60+d["ts"].dt.minute
        d["wd_mod"]=d["weekday"].astype(str)+"_"+d["mod"].astype(str); d["date"]=d["ts"].dt.strftime("%Y-%m-%d")
        own_days=d.loc[d.own_match==1,"date"].nunique()
        own_minutes=int((d.own_match==1).sum())
        for ycol,yname in [("act","activity"),("vol","volatility(hi/lo)")]:
            s=d.dropna(subset=[ycol]); s=s[np.isfinite(s[ycol])]
            if s.own_match.sum()<30 or s.foreign_match.sum()<30:
                rows.append(dict(currency=cur,home=lab,outcome=yname,coef=np.nan,pct=np.nan,se=np.nan,
                                 p=np.nan,own_match_days=own_days,own_minutes=own_minutes,note="too few own-match obs"))
                continue
            try:
                mm=feols(f"{ycol} ~ foreign_match + own_match | wd_mod + date", data=s, vcov={"CRV1":"date"})
                r=mm.tidy().loc["own_match"]
                rows.append(dict(currency=cur,home=lab,outcome=yname,coef=round(r["Estimate"],4),
                                 pct=round(np.expm1(r["Estimate"])*100,2),se=round(r["Std. Error"],4),
                                 p=round(r["Pr(>|t|)"],4),own_match_days=own_days,own_minutes=own_minutes,
                                 note=("UNDERPOWERED" if own_days<8 else "")))
            except Exception as e:
                rows.append(dict(currency=cur,home=lab,outcome=yname,coef=np.nan,pct=np.nan,se=np.nan,
                                 p=np.nan,own_match_days=own_days,own_minutes=own_minutes,note=f"err:{type(e).__name__}"))
    res=pd.DataFrame(rows)
    res.to_csv(os.path.join(OUT,"fx_home_country.csv"),index=False)
    pd.set_option("display.width",200,"display.max_columns",20)
    print(res.to_string(index=False))
    sig=res.dropna(subset=["p"]); sig=sig[sig.p<0.05]
    print(f"\nrows={len(res)}  home-nation cells with p<0.05: {len(sig)}")
    if len(sig): print(sig[['currency','home','outcome','pct','p','own_match_days']].to_string(index=False))
    print("\nEach currency tested ONLY on its own nation's matches. own_match = home team on the pitch.")
    return res
if __name__=="__main__":
    main()
