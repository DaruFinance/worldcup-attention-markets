#!/usr/bin/env python3
"""
EXTENDED home-currency FX test, 2002-2022 (six World Cups), using ICE/IDC daily series the user supplied.
No volume -> return (Edmans loser effect) + daily volatility channels only. Each series is gated at its
reliable float/redenomination date and normalized to the USD VALUE of the local currency, so a NEGATIVE
return = home currency depreciates (the loser-effect prediction). Results/dates/eliminations from the
Fjelstul World Cup DB (all tournaments). Tests: (1) pooled-EM loser effect (next-session return after the
nation's own W/L/D and after elimination), date-FE-absorbed common-USD move, cluster by date; (2) Brazil
STANDALONE (34 match-days, ~at the single-nation validity floor) with a DXY control; (3) match-day daily
volatility. Out: analysis/out/fx_extended_{loser,brazil,vol}.csv
"""
import os, warnings
warnings.simplefilter("ignore")
os.environ.setdefault("OPENBLAS_NUM_THREADS","1"); os.environ.setdefault("OMP_NUM_THREADS","1")
import numpy as np, pandas as pd
from pyfixest.estimation import feols
ROOT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"..")
MDIR=os.path.join(ROOT,"data","matches"); OUT=os.path.join(ROOT,"analysis","out")
C=os.environ.get("WC_INDEX_DIR", os.path.join(ROOT,"data","market","indices_daily"))
# nation -> (csv file, gate_year, invert?)  invert=True means file is USDxxx (xxx-per-USD) -> take 1/close for USD value
# nation -> (file, gate_year, invert?, class, end_cap_year)  invert=True for USDxxx files (xxx-per-USD)
FX={"Brazil":("FX_IDC_USDBRL, 1D.csv",2002,True,"emerging",None),
    "South Korea":("FX_IDC_USDKRW, 1D.csv",1998,True,"emerging",None),
    "Mexico":("FX_IDC_MXNUSD, 1D.csv",2003,False,"emerging",None),
    "Poland":("FX_IDC_PLNUSD, 1D.csv",2000,False,"emerging",None),
    "Colombia":("FX_IDC_COPUSD, 1D.csv",2007,False,"emerging",None),
    "South Africa":("FX_IDC_ZARUSD, 1D.csv",2006,False,"emerging",None),
    "Peru":("FX_IDC_USDPEN, 1D.csv",2002,True,"emerging",None),
    "Chile":("FX_IDC_USDCLP, 1D.csv",2000,True,"emerging",None),
    "Uruguay":("FX_IDC_USDUYU, 1D.csv",2003,True,"emerging",None),
    "Ghana":("FX_IDC_USDGHS, 1D.csv",2007,True,"emerging",None),
    "Russia":("FX_IDC_USDRUB, 1D.csv",2015,True,"emerging",2022),   # free float '14; cap before '22 sanctions halt
    "Japan":("FX_IDC_USDJPY, 1D.csv",1998,True,"developed",None),
    "Canada":("FX_IDC_USDCAD, 1D.csv",1998,True,"developed",None),
    "Australia":("FX_IDC_AUDUSD, 1D.csv",1998,False,"developed",None),
    "New Zealand":("FX_IDC_NZDUSD, 1D.csv",1998,False,"developed",None),
    "Sweden":("FX_IDC_USDSEK, 1D.csv",1998,True,"developed",None)}

def load_fx(nation):
    fn,gate,inv,klass,cap=FX[nation]; fp=os.path.join(C,fn)
    if not os.path.exists(fp): return None
    d=pd.read_csv(fp); d["date"]=pd.to_datetime(d["time"],unit="s",utc=True).dt.tz_localize(None).dt.normalize()
    d=d.sort_values("date")
    o,h,l,c=[d[x].astype(float) for x in ("open","high","low","close")]
    if inv:  # USDxxx -> USD value of local = 1/price ; high/low swap
        val=1.0/c; hi=1.0/l; lo=1.0/h
    else:
        val=c; hi=h; lo=l
    d["val"]=val; d["park"]=np.log((hi/lo).where(lo>0))
    d=d[d.date.dt.year>=gate]
    if cap: d=d[d.date.dt.year<=cap]
    d=d[d.val>0]; d["ret"]=np.log(d["val"]/d["val"].shift(1))
    d=d[~(d.ret.abs()>=0.25)]  # drop redenomination/data-break days (NaN first row kept)
    d["nation"]=nation; d["ticker"]=fn.replace(", 1D.csv","").replace("FX_IDC_","")
    d["klass"]=klass
    return d[["date","nation","ticker","klass","val","ret","park"]]

def fjelstul():
    d=pd.read_csv(os.path.join(MDIR,"fjelstul_all.csv"))
    d=d[d.tournament_name.str.contains("FIFA Men's World Cup",na=False)]
    d["year"]=d.tournament_name.str[:4].astype(int); d=d[d.year.between(1998,2022)]
    d["date"]=pd.to_datetime(d.match_date).dt.normalize()
    rows=[]
    for _,r in d.iterrows():
        for team,gf,ga in [(r.home_team_name,r.home_team_score,r.away_team_score),
                           (r.away_team_name,r.away_team_score,r.home_team_score)]:
            res="W" if gf>ga else ("L" if gf<ga else "D")
            rows.append(dict(year=r.year,team=team,date=r.date,res=res,ko=int(r.knockout_stage)))
    L=pd.DataFrame(rows)
    # champion per tournament = winner of last knockout match
    champ={}
    for y,g in d.groupby("year"):
        fin=g.sort_values("match_date").iloc[-1]
        champ[y]=fin.home_team_name if fin.home_team_score>fin.away_team_score else fin.away_team_name
    last=L.sort_values("date").groupby(["year","team"]).tail(1)
    elim=set((r.year,r.team,r.date) for r in last.itertuples() if r.team!=champ.get(r.year))
    L["elim"]=L.apply(lambda r:(r.year,r.team,r.date) in elim,axis=1)
    return L

def dxy():
    fp=os.path.join(ROOT,"data","controls","dxy_daily.parquet")  # cached, offline-reproducible
    if os.path.exists(fp):
        d=pd.read_parquet(fp); d["dxy_ret"]=np.log(d["close"]/d["close"].shift(1)); return d[["date","dxy_ret"]]
    return pd.DataFrame(columns=["date","dxy_ret"])

def attach(fx, L):
    # own_play = same calendar day; post = the SINGLE FIRST trading session strictly after each match
    # (one treated observation per match, no autocorrelated multi-day stacking)
    nat=fx.nation.iloc[0]; sub=L[L.team==nat]
    if not len(sub): return None
    mdays=sorted(sub.date); rb=sub.set_index("date")[["res","elim"]].to_dict("index")
    fx=fx.copy().sort_values("date").reset_index(drop=True)
    fx["own_play"]=fx.date.isin(set(mdays)).astype(int)
    dts=fx.date.values; pr=[None]*len(fx); pe=[0]*len(fx)
    for md in mdays:
        i=int(np.searchsorted(dts, np.datetime64(pd.Timestamp(md)), side="right"))
        if i<len(fx) and (fx.date.iloc[i]-md).days<=7 and pr[i] is None:
            pr[i]=rb[md]["res"]; pe[i]=int(rb[md]["elim"])
    fx["post_res"]=pr; fx["post_elim"]=pe
    return fx

def main():
    L=fjelstul()
    parts=[attach(load_fx(n),L) for n in FX if load_fx(n) is not None]
    parts=[p for p in parts if p is not None]
    P=pd.concat(parts,ignore_index=True); P=P.dropna(subset=["ret"]); P=P[np.isfinite(P.ret)]
    P["dstr"]=P.date.dt.strftime("%Y-%m-%d")
    P["postL"]=(P.post_res=="L").astype(int); P["postW"]=(P.post_res=="W").astype(int); P["postD"]=(P.post_res=="D").astype(int)
    P["postL_elim"]=P.postL*P.post_elim
    P["emerg"]=(P.klass=="emerging").astype(int); P["postL_emerg"]=P.postL*P.emerg
    # coverage
    cov=P[P.own_play==1].groupby(["klass","nation"]).dstr.nunique().sort_values(ascending=False)
    print("own-match-day clusters per nation (gated):"); print(cov.to_string()); print("total clusters:",P[P.own_play==1].dstr.nunique())

    # (1) loser effect, date FE absorbs common USD move; pooled-all / EM / developed + size interaction
    rows_l=[]
    def lz(sub,spec,terms):
        m=feols("ret ~ postL + postW + postD | ticker + dstr", data=sub, vcov={"CRV1":"dstr"})
        for v in terms:
            r=m.tidy().loc[v]; rows_l.append(dict(spec=spec,term=v,bps=round(r["Estimate"]*1e4,1),se_bps=round(r["Std. Error"]*1e4,1),p=round(r["Pr(>|t|)"],4),n=int(m._N),clusters=int(sub[sub.own_play==1].dstr.nunique())))
    lz(P,"pooled all (16 ccy)",["postL","postW","postD"])
    lz(P[P.emerg==1],"emerging only",["postL","postW","postD"])
    lz(P[P.emerg==0],"developed only",["postL","postW","postD"])
    m2=feols("ret ~ postL + postL_elim + postW + postD | ticker + dstr", data=P, vcov={"CRV1":"dstr"})
    for v in ["postL","postL_elim"]:
        r=m2.tidy().loc[v]; rows_l.append(dict(spec="elim-split (all)",term=v,bps=round(r["Estimate"]*1e4,1),se_bps=round(r["Std. Error"]*1e4,1),p=round(r["Pr(>|t|)"],4),n=int(m2._N),clusters=int(P[P.own_play==1].dstr.nunique())))
    m3=feols("ret ~ postL + postL_emerg + postW + postD | ticker + dstr", data=P, vcov={"CRV1":"dstr"})
    for v in ["postL","postL_emerg"]:
        r=m3.tidy().loc[v]; rows_l.append(dict(spec="size: postL x emerging",term=v,bps=round(r["Estimate"]*1e4,1),se_bps=round(r["Std. Error"]*1e4,1),p=round(r["Pr(>|t|)"],4),n=int(m3._N),clusters=int(P[P.own_play==1].dstr.nunique())))
    pd.DataFrame(rows_l).to_csv(os.path.join(OUT,"fx_extended_loser.csv"),index=False)
    print("\n=== LOSER EFFECT (next-session FX return) ==="); print(pd.DataFrame(rows_l).to_string(index=False))

    # (2) Standalones with DXY control (no date FE -> single cross-section): Brazil + Japan
    dx=dxy(); rb=[]
    for nat,lab in [("Brazil","USDBRL 2002-2022"),("Japan","USDJPY 1998-2022")]:
        B=P[P.nation==nat].merge(dx,on="date",how="left")
        f="ret ~ postL + postW + postD"+(" + dxy_ret" if B.dxy_ret.notna().any() else "")
        mb=feols(f, data=B.dropna(subset=["ret"]), vcov="hetero")  # single time series: HC1, not singleton-date clusters
        bd=B[B.own_play==1].dstr.nunique()
        for v in ["postL","postW","postD"]:
            r=mb.tidy().loc[v]; rb.append(dict(nation=nat,note=lab,term=v,bps=round(r["Estimate"]*1e4,1),se_bps=round(r["Std. Error"]*1e4,1),p=round(r["Pr(>|t|)"],4),match_days=bd))
    bdf=pd.DataFrame(rb); bdf.to_csv(os.path.join(OUT,"fx_extended_brazil.csv"),index=False)
    print("\n=== STANDALONES (DXY-controlled) ==="); print(bdf.to_string(index=False))

    # (3) match-day volatility, pooled
    s=P.dropna(subset=["park"]); s=s[np.isfinite(s.park)]
    mv=feols("park ~ own_play | ticker + dstr", data=s, vcov={"CRV1":"dstr"}); r=mv.tidy().loc["own_play"]
    vdf=pd.DataFrame([dict(outcome="daily hi/lo vol",pct=round(np.expm1(r["Estimate"])*100,2),se=round(r["Std. Error"],4),p=round(r["Pr(>|t|)"],4),n=int(mv._N))])
    vdf.to_csv(os.path.join(OUT,"fx_extended_vol.csv"),index=False)
    print("\n=== MATCH-DAY VOLATILITY (pooled EM) ==="); print(vdf.to_string(index=False))
    print(f"\nPanel: {P.ticker.nunique()} home currencies (5 developed gated 1998, rest 2002), {len(P):,} ccy-days, {P[P.own_play==1].dstr.nunique()} match-day clusters. No volume -> return+vol only.")
if __name__=="__main__":
    main()
