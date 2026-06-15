#!/usr/bin/env python3
"""
EXTENDED home-equity test, 1998-2022 (7 World Cups), using TradingView/ICE daily index series the user
supplied. Most index series carry no volume -> return (Edmans loser effect) + daily volatility channels
(matching the extended-FX arm). Each index keyed to its nation's own matches (Fjelstul results). Tests:
(1) pooled loser effect (next-session index return after own W/L/D and elimination), date-FE-absorbed
common world move, cluster by date, developed/emerging split + size interaction; (2) Brazil & Japan
standalones (world-return controlled); (3) match-day volatility; (4) match-day VOLUME distraction for the
few indices that do report volume. Out: analysis/out/eq_extended_{loser,standalone,vol}.csv
"""
import os, warnings
warnings.simplefilter("ignore")
os.environ.setdefault("OPENBLAS_NUM_THREADS","1"); os.environ.setdefault("OMP_NUM_THREADS","1")
import numpy as np, pandas as pd
from pyfixest.estimation import feols
ROOT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"..")
MDIR=os.path.join(ROOT,"data","matches"); OUT=os.path.join(ROOT,"analysis","out")
C=os.environ.get("WC_INDEX_DIR", os.path.join(ROOT,"data","market","indices_daily"))
# nation -> (file, class, end_cap)
IDX={"Australia":("ASX_DLY_XJO, 1D.csv","developed",None),
     "Brazil":("BMFBOVESPA_DLY_IBOV, 1D.csv","emerging",None),
     "Mexico":("BMV_DLY_ME, 1D.csv","emerging",None),
     "Poland":("GPW_DLY_WIG20, 1D.csv","emerging",None),
     "Belgium":("INDEX_BEL20, 1D.csv","developed",None),
     "Italy":("INDEX_FTSEMIB, 1D.csv","developed",None),
     "Portugal":("INDEX_PSI20, 1D.csv","developed",None),
     "South Africa":("JSE_DLY_J203, 1D.csv","emerging",None),
     "Denmark":("NASDAQ_DLY_OMXC25, 1D.csv","developed",None),
     "Sweden":("NASDAQ_DLY_OMXS30, 1D.csv","developed",None),
     "Russia":("RUS_MOEX, 1D.csv","emerging",2022),
     "United States":("SP_SPX, 1D.csv","developed",None),
     "Netherlands":("TVC_AEX, 1D.csv","developed",None),
     "France":("TVC_CAC40, 1D.csv","developed",None),
     "Germany":("TVC_DEU40, 1D.csv","developed",None),
     "Spain":("TVC_IBEX35, 1D.csv","developed",None),
     "South Korea":("TVC_KOSPI, 1D.csv","developed",None),
     "Japan":("TVC_NI225, 1D.csv","developed",None),
     "Switzerland":("TVC_SSMI, 1D.csv","developed",None),
     "England":("TVC_UKX, 1D.csv","developed",None)}
GATE=1998
USA_ALIAS={"United States":"United States"}  # Fjelstul uses "United States"

def load_idx(nation):
    fn,klass,cap=IDX[nation]; fp=os.path.join(C,fn)
    if not os.path.exists(fp): return None
    d=pd.read_csv(fp); d["date"]=pd.to_datetime(d["time"],unit="s",utc=True).dt.tz_localize(None).dt.normalize()
    d=d.sort_values("date")
    c=d["close"].astype(float)
    has_hl="high" in d and "low" in d
    d["park"]=np.log((d["high"].astype(float)/d["low"].astype(float)).where(d["low"]>0)) if has_hl else np.nan
    vcol=[x for x in d.columns if x.lower()=="volume"]
    d["lvol"]=np.log(d[vcol[0]].astype(float).where(d[vcol[0]]>0)) if vcol and (d[vcol[0]].fillna(0)!=0).mean()>0.5 else np.nan
    d["ret"]=np.log(c/c.shift(1))
    d=d[(d.date.dt.year>=GATE)]
    if cap: d=d[d.date.dt.year<=cap]
    d=d[d.ret.abs()<0.25]  # drop redenomination/data breaks
    d["nation"]=nation; d["ticker"]=fn.replace(", 1D.csv",""); d["klass"]=klass
    return d[["date","nation","ticker","klass","ret","park","lvol"]]

def fjelstul():
    d=pd.read_csv(os.path.join(MDIR,"fjelstul_all.csv"))
    d=d[d.tournament_name.str.contains("FIFA Men's World Cup",na=False)]
    d["year"]=d.tournament_name.str[:4].astype(int); d=d[d.year.between(GATE,2022)]
    d["date"]=pd.to_datetime(d.match_date).dt.normalize()
    rows=[]
    for _,r in d.iterrows():
        for team,gf,ga in [(r.home_team_name,r.home_team_score,r.away_team_score),
                           (r.away_team_name,r.away_team_score,r.home_team_score)]:
            res="W" if gf>ga else ("L" if gf<ga else "D")
            rows.append(dict(year=r.year,team=team,date=r.date,res=res))
    L=pd.DataFrame(rows)
    champ={}
    for y,g in d.groupby("year"):
        fin=g.sort_values("match_date").iloc[-1]
        champ[y]=fin.home_team_name if fin.home_team_score>fin.away_team_score else fin.away_team_name
    last=L.sort_values("date").groupby(["year","team"]).tail(1)
    elim=set((r.year,r.team,r.date) for r in last.itertuples() if r.team!=champ.get(r.year))
    L["elim"]=L.apply(lambda r:(r.year,r.team,r.date) in elim,axis=1)
    return L

def world():
    fp=os.path.join(ROOT,"data","controls","acwi_daily.parquet")  # cached, offline-reproducible
    if os.path.exists(fp):
        d=pd.read_parquet(fp); d["wret"]=np.log(d["close"]/d["close"].shift(1)); return d[["date","wret"]]
    return pd.DataFrame(columns=["date","wret"])

def attach(idx,L):
    # post = the SINGLE FIRST trading session strictly after each match (one treated obs/match)
    nat=idx.nation.iloc[0]; sub=L[L.team==nat]
    if not len(sub): return None
    mdays=sorted(sub.date); rb=sub.set_index("date")[["res","elim"]].to_dict("index")
    idx=idx.copy().sort_values("date").reset_index(drop=True)
    idx["own_play"]=idx.date.isin(set(mdays)).astype(int)
    dts=idx.date.values; pr=[None]*len(idx); pe=[0]*len(idx)
    for md in mdays:
        i=int(np.searchsorted(dts, np.datetime64(pd.Timestamp(md)), side="right"))
        if i<len(idx) and (idx.date.iloc[i]-md).days<=7 and pr[i] is None:
            pr[i]=rb[md]["res"]; pe[i]=int(rb[md]["elim"])
    idx["post_res"]=pr; idx["post_elim"]=pe
    return idx

def main():
    L=fjelstul()
    parts=[attach(load_idx(n),L) for n in IDX if load_idx(n) is not None]
    parts=[p for p in parts if p is not None]
    P=pd.concat(parts,ignore_index=True); P=P[np.isfinite(P.ret)]
    P["dstr"]=P.date.dt.strftime("%Y-%m-%d")
    P["postL"]=(P.post_res=="L").astype(int); P["postW"]=(P.post_res=="W").astype(int); P["postD"]=(P.post_res=="D").astype(int)
    P["postL_elim"]=P.postL*P.post_elim; P["emerg"]=(P.klass=="emerging").astype(int); P["postL_emerg"]=P.postL*P.emerg
    cov=P[P.own_play==1].groupby(["klass","nation"]).dstr.nunique().sort_values(ascending=False)
    print("own-match-day clusters per nation:"); print(cov.to_string()); print("total clusters:",P[P.own_play==1].dstr.nunique(),"| nations:",P.nation.nunique())

    rows=[]
    def lz(sub,spec,terms):
        m=feols("ret ~ postL + postW + postD | ticker + dstr", data=sub, vcov={"CRV1":"dstr"})
        for v in terms:
            r=m.tidy().loc[v]; rows.append(dict(spec=spec,term=v,bps=round(r["Estimate"]*1e4,1),se_bps=round(r["Std. Error"]*1e4,1),p=round(r["Pr(>|t|)"],4),clusters=int(sub[sub.own_play==1].dstr.nunique())))
    lz(P,"pooled all (20 idx)",["postL","postW","postD"])
    lz(P[P.emerg==1],"emerging only",["postL","postW","postD"])
    lz(P[P.emerg==0],"developed only",["postL","postW","postD"])
    me=feols("ret ~ postL + postL_elim + postW + postD | ticker + dstr", data=P, vcov={"CRV1":"dstr"})
    for v in ["postL","postL_elim"]:
        r=me.tidy().loc[v]; rows.append(dict(spec="elim-split",term=v,bps=round(r["Estimate"]*1e4,1),se_bps=round(r["Std. Error"]*1e4,1),p=round(r["Pr(>|t|)"],4),clusters=int(P[P.own_play==1].dstr.nunique())))
    ms=feols("ret ~ postL + postL_emerg + postW + postD | ticker + dstr", data=P, vcov={"CRV1":"dstr"})
    for v in ["postL","postL_emerg"]:
        r=ms.tidy().loc[v]; rows.append(dict(spec="size: postL x emerging",term=v,bps=round(r["Estimate"]*1e4,1),se_bps=round(r["Std. Error"]*1e4,1),p=round(r["Pr(>|t|)"],4),clusters=int(P[P.own_play==1].dstr.nunique())))
    pd.DataFrame(rows).to_csv(os.path.join(OUT,"eq_extended_loser.csv"),index=False)
    print("\n=== LOSER EFFECT (next-session index return, 1998-2022) ==="); print(pd.DataFrame(rows).to_string(index=False))

    w=world(); rs=[]
    for nat,lab in [("Brazil","IBOV"),("Japan","NI225"),("Germany","DAX"),("England","FTSE100")]:
        B=P[P.nation==nat].merge(w,on="date",how="left")
        f="ret ~ postL + postW + postD"+(" + wret" if B.wret.notna().any() else "")
        mb=feols(f, data=B, vcov="hetero"); bd=B[B.own_play==1].dstr.nunique()  # single series: HC1
        for v in ["postL","postW","postD"]:
            r=mb.tidy().loc[v]; rs.append(dict(nation=nat,index=lab,term=v,bps=round(r["Estimate"]*1e4,1),se_bps=round(r["Std. Error"]*1e4,1),p=round(r["Pr(>|t|)"],4),match_days=bd))
    pd.DataFrame(rs).to_csv(os.path.join(OUT,"eq_extended_standalone.csv"),index=False)
    print("\n=== STANDALONES (world-return controlled) ==="); print(pd.DataFrame(rs).to_string(index=False))

    s=P.dropna(subset=["park"]); s=s[np.isfinite(s.park)]
    mv=feols("park ~ own_play | ticker + dstr", data=s, vcov={"CRV1":"dstr"}); r=mv.tidy().loc["own_play"]
    vrows=[dict(outcome="match-day volatility (hi/lo)",pct=round(np.expm1(r["Estimate"])*100,2),se=round(r["Std. Error"],4),p=round(r["Pr(>|t|)"],4),n=int(mv._N))]
    sv=P.dropna(subset=["lvol"]); sv=sv[np.isfinite(sv.lvol)]
    if len(sv)>500:
        mvol=feols("lvol ~ own_play | ticker + dstr", data=sv, vcov={"CRV1":"dstr"}); r2=mvol.tidy().loc["own_play"]
        vrows.append(dict(outcome=f"match-day VOLUME ({sv.nation.nunique()} idx w/ vol)",pct=round(np.expm1(r2["Estimate"])*100,2),se=round(r2["Std. Error"],4),p=round(r2["Pr(>|t|)"],4),n=int(mvol._N)))
    pd.DataFrame(vrows).to_csv(os.path.join(OUT,"eq_extended_vol.csv"),index=False)
    print("\n=== MATCH-DAY VOLATILITY / VOLUME ==="); print(pd.DataFrame(vrows).to_string(index=False))
    print(f"\nPanel: {P.nation.nunique()} indices, {len(P):,} index-days, {P[P.own_play==1].dstr.nunique()} match-day clusters, 1998-2022.")
if __name__=="__main__":
    main()
