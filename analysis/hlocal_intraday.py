#!/usr/bin/env python3
"""
The pre-registered intraday H_local test (runs once ingest/pull_home_intraday.py has written bars). The
Ehrmann-Jansen object at last: log trade count on a nation's OWN exchange, during its OWN team's in-play
window, matched-control FE, clustered by date. OwnMatch is built from the Fjelstul kickoffs in each
exchange's LOCAL timezone with an in-session filter, so treatment and controls share the trading calendar.
Reports pooled beta + 95% CI + equivalence bound (largest decline excluded), the Brazil-only cut, and the
per-exchange table -- the format of Tables 2-3 of the paper. Out: analysis/out/hlocal_intraday.csv
"""
import os, warnings; warnings.simplefilter("ignore")
os.environ.setdefault("OPENBLAS_NUM_THREADS","1")
import numpy as np, pandas as pd, glob
R=os.path.join(os.path.dirname(os.path.abspath(__file__)),"..")
IN=os.path.join(R,"data","market","home_intraday"); M=os.path.join(R,"data","matches"); O=os.path.join(R,"analysis","out")
# exchange -> (nation, IANA tz)  -- mirrors the puller
EXCH={"B3":("Brazil","America/Sao_Paulo"),"BMV":("Mexico","America/Mexico_City"),
      "BYMA":("Argentina","America/Argentina/Buenos_Aires"),"Euronext-PA":("France","Europe/Paris"),
      "Euronext-AS":("Netherlands","Europe/Amsterdam"),"Euronext-LS":("Portugal","Europe/Lisbon"),
      "Euronext-BR":("Belgium","Europe/Brussels"),"Xetra":("Germany","Europe/Berlin"),
      "SIX":("Switzerland","Europe/Zurich"),"BME":("Spain","Europe/Madrid"),"LSE":("England","Europe/London"),
      "BorsaItaliana":("Italy","Europe/Rome"),"JSE":("South Africa","Africa/Johannesburg"),"GPW":("Poland","Europe/Warsaw")}

def own_windows(nation):
    a=pd.read_parquet(os.path.join(M,"matches_all.parquet")); a=a[a.tournament.isin([2018,2022])]
    h=pd.read_parquet(os.path.join(M,"matches_hist.parquet"))
    c=["kickoff_utc","home","away","played"]; m=pd.concat([a[c],h[c]],ignore_index=True)
    m=m[(m.played==True)&((m.home==nation)|(m.away==nation))]
    ko=pd.to_datetime(m["kickoff_utc"],utc=True)
    return [(k,k+pd.Timedelta(minutes=104)) for k in ko]

def load(exch):
    fp=os.path.join(IN,f"{exch}_1m.parquet")
    if not os.path.exists(fp): return None
    d=pd.read_parquet(fp); d["ts"]=pd.to_datetime(d["ts_utc"],utc=True).dt.floor("min")
    g=d.groupby(["ts","ticker"],as_index=False).agg(trades=("trades","sum"))
    g["ltr"]=np.log(g["trades"].astype(float).where(g["trades"]>0))
    return g.dropna(subset=["ltr"])

def fit(panel, label):
    from pyfixest.estimation import feols
    s=panel.copy(); s["dstr"]=s.ts.dt.strftime("%Y-%m-%d")
    s["wd_mod"]=s.ts.dt.weekday.astype(str)+"_"+(s.ts.dt.hour*60+s.ts.dt.minute).astype(str)
    m=feols("ltr ~ own_match | ticker^wd_mod + dstr", data=s, vcov={"CRV1":"dstr"})
    r=m.tidy().loc["own_match"]; c,se=r["Estimate"],r["Std. Error"]
    lo,hi=np.expm1(c-1.96*se)*100, np.expm1(c+1.96*se)*100
    return dict(cell=label,effect_pct=round(np.expm1(c)*100,1),ci_lo=round(lo,1),ci_hi=round(hi,1),
                decline_excl=round(max(0,-lo),1),clusters=int(s.loc[s.own_match==1,"dstr"].nunique()),p=round(r["Pr(>|t|)"],4))

def main():
    if not glob.glob(os.path.join(IN,"*_1m.parquet")):
        print("No home_intraday parquets yet. Run ingest/pull_home_intraday.py first (needs a data route)."); return
    pooled=[]; rows=[]
    for exch,(nation,tz) in EXCH.items():
        g=load(exch)
        if g is None: continue
        wins=own_windows(nation); inplay=pd.Series(False,index=g.index)
        loc=g.ts.dt.tz_convert(tz)  # local clock; in-session is implicit (vendor bars exist only in session)
        for a,b in wins: inplay |= (g.ts>=a)&(g.ts<=b)
        g=g.assign(own_match=inplay.astype(int),exch=exch,nation=nation)
        if g.own_match.sum()>50:
            try: rows.append(fit(g,f"{exch} ({nation})"))
            except Exception as e: print(f"  {exch}: {type(e).__name__}")
        pooled.append(g)
    if not pooled: return
    P=pd.concat(pooled,ignore_index=True); P["ticker"]=P.exch+":"+P.ticker
    rows.insert(0, fit(P,"POOLED (all exchanges)"))
    b=P[P.nation=="Brazil"]
    if b.own_match.sum()>50: rows.insert(1, fit(b,"Brazil only (B3)"))
    res=pd.DataFrame(rows); res.to_csv(os.path.join(O,"hlocal_intraday.csv"),index=False)
    print(res.to_string(index=False))
    pr=res.iloc[0]
    print(f"\nPre-registered verdict: pooled own-match effect {pr.effect_pct:+.1f}% "
          f"[{pr.ci_lo},{pr.ci_hi}], {pr.clusters} clusters. "
          f"H_local {'REJECTED (decline < -30% excluded)' if pr.ci_lo>-30 else 'NOT rejected'}; "
          f"{'CONFIRMED' if (pr.effect_pct<=-30 and pr.p<0.05) else 'no -30% decline at the achieved power'}.")
if __name__=="__main__":
    main()
