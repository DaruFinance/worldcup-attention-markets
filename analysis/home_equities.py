#!/usr/bin/env python3
"""
HOME-MARKET test, pooled across nations (the design the underpowered single pairs require). Daily home
equities (index + top caps, 26 nations) and exotic daily FX (24 pairs). Three questions:
  (1) DISTRACTION: is trading activity (log volume) / volatility (Parkinson log hi/lo) different on a
      calendar day the nation plays?  y ~ own_play | ticker + date, cluster by date.
  (2) LOSER EFFECT (Edmans-Garcia-Norli): is the home market's return on the FIRST trading day AFTER a
      match negative after a loss / elimination?  abret ~ post_loss+post_draw+post_win(+post_elim),
      market-adjusted by an MSCI-world (ACWI) return control, cluster by date.
  (3) SIZE HETEROGENEITY: own_play x emerging  -  is the effect larger in smaller / emerging markets
      (the hypothesis that the smallest nations show the biggest effect)?
Pooling stacks each nation's ~10-23 match-days into 200+ clusters => properly powered where single
pairs (<=22 days) never are. Daily is the finest free resolution for foreign venues; stated as a limit.
Out: analysis/out/home_equities_{distraction,loser,size}.csv
"""
import os, warnings
warnings.simplefilter("ignore")
os.environ.setdefault("OPENBLAS_NUM_THREADS","1"); os.environ.setdefault("OMP_NUM_THREADS","1")
import numpy as np, pandas as pd
from pyfixest.estimation import feols
ROOT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"..")
EQ=os.path.join(ROOT,"data","market","equities_intl"); FXX=os.path.join(ROOT,"data","market","fx_exotic_daily")
MDIR=os.path.join(ROOT,"data","matches"); OUT=os.path.join(ROOT,"analysis","out")

ALIAS={"Korea Republic":"South Korea","South Korea":"South Korea","USA":"USA","United States":"USA",
       "IR Iran":"Iran","Czech Republic":"Czechia"}
DEVELOPED={"Japan","England","Germany","France","Spain","Italy","Netherlands","Belgium","Portugal",
           "Switzerland","Australia","USA","Denmark","Sweden","South Korea"}

def nrm(t): return ALIAS.get(str(t).strip(),str(t).strip())

def matches():
    a=pd.read_parquet(os.path.join(MDIR,"matches_all.parquet")); a=a[a.tournament.isin([2018,2022])]
    h=pd.read_parquet(os.path.join(MDIR,"matches_hist.parquet"))
    c=["tournament","kickoff_utc","home","away","home_score","away_score"]
    m=pd.concat([a[c],h[c]],ignore_index=True).dropna(subset=["home_score","away_score"])
    m["ko"]=pd.to_datetime(m["kickoff_utc"],utc=True); m["date"]=m["ko"].dt.tz_convert("UTC").dt.normalize().dt.tz_localize(None)
    m["home"]=m["home"].map(nrm); m["away"]=m["away"].map(nrm)
    # long form: one row per (team, match) with result
    rows=[]
    for _,r in m.iterrows():
        for team,gf,ga in [(r.home,r.home_score,r.away_score),(r.away,r.away_score,r.home_score)]:
            res="W" if gf>ga else ("L" if gf<ga else "D")
            rows.append(dict(tournament=r.tournament,team=team,date=r.date,res=res,gf=gf,ga=ga))
    L=pd.DataFrame(rows)
    # elimination: a team's LAST match-day in a tournament (champions excluded -> they win the final)
    last=L.sort_values("date").groupby(["tournament","team"]).tail(1).copy()
    # champion = winner of the latest match in the tournament
    champ={}
    for t,g in m.groupby("tournament"):
        fin=g.sort_values("ko").iloc[-1]; champ[t]=fin.home if fin.home_score>fin.away_score else fin.away
    last["elim"]=last.apply(lambda r: r.team!=champ.get(r.tournament),axis=1)
    elim=set((r.tournament,r.team,r.date) for r in last[last.elim].itertuples())
    L["elim"]=L.apply(lambda r:(r.tournament,r.team,r.date) in elim,axis=1)
    return L

def windows(L):
    w={}
    for t,g in L.groupby("tournament"):
        w[t]=(g.date.min()-pd.Timedelta(days=21),g.date.max()+pd.Timedelta(days=22))
    return w

def world_ret():
    # cached ACWI (committed to data/controls) so the world-return adjustment reproduces offline/deterministically
    fp=os.path.join(ROOT,"data","controls","acwi_daily.parquet")
    if os.path.exists(fp):
        d=pd.read_parquet(fp); d["wret"]=np.log(d["close"]/d["close"].shift(1)); return d[["date","wret"]]
    return pd.DataFrame(columns=["date","wret"])

def load_panel(L, wins):
    man=pd.read_csv(os.path.join(EQ,"manifest.csv")); man=man[man.ok==True]
    fxm=pd.read_csv(os.path.join(FXX,"manifest.csv")); fxm=fxm[fxm.ok==True]
    # team match-day sets and per-team daily result map
    play_days={}; res_by_team={}
    for team,g in L.groupby("team"):
        play_days[team]=set(g.date); res_by_team[team]=g.set_index("date")[["res","elim"]].to_dict("index")
    parts=[]
    def add(fp, nation, klass, kind):
        nation=nrm(nation)
        if not os.path.exists(fp): return
        d=pd.read_parquet(fp); d["date"]=pd.to_datetime(d["date"]).dt.normalize()
        keep=pd.Series(False,index=d.index)
        for a,b in wins.values(): keep|=(d.date>=a)&(d.date<=b)
        d=d[keep].copy()
        if len(d)<20 or nation not in play_days: return
        d=d.sort_values("date")
        d["lvol"]=np.log(d["volume"].astype(float).where(d["volume"]>0)) if "volume" in d and d["volume"].fillna(0).sum()>0 else np.nan
        d["park"]=np.log((d["high"].astype(float)/d["low"].astype(float)).where(d["low"]>0))
        d["ret"]=np.log(d["close"].astype(float)/d["close"].astype(float).shift(1))
        pd_=play_days[nation]
        d=d.sort_values("date").reset_index(drop=True)
        d["own_play"]=d.date.isin(pd_).astype(int)
        # loser effect: the SINGLE FIRST trading session strictly after each match (one treated obs/match)
        rb=res_by_team[nation]; mdays=sorted(pd_)
        dts=d.date.values; pr=[None]*len(d); pe=[0]*len(d)
        for md in mdays:
            i=int(np.searchsorted(dts, np.datetime64(pd.Timestamp(md)), side="right"))
            if i<len(d) and (d.date.iloc[i]-md).days<=7 and pr[i] is None:
                pr[i]=rb[md]["res"]; pe[i]=1 if rb[md]["elim"] else 0
        d["post_res"]=pr; d["post_elim"]=pe
        d["ticker"]=os.path.basename(fp); d["nation"]=nation; d["klass"]=klass; d["kind"]=kind
        parts.append(d[["date","ticker","nation","klass","kind","lvol","park","ret","own_play","post_res","post_elim"]])
    for r in man.itertuples():
        klass="developed" if nrm(r.nation) in DEVELOPED else "emerging"
        add(r.path, r.nation, klass, "index" if r.role=="index" else "stock")
    for r in fxm.itertuples():
        klass="developed" if nrm(r.nation) in DEVELOPED else "emerging"
        add(r.path, r.nation, klass, "fx")
    return pd.concat(parts,ignore_index=True) if parts else pd.DataFrame()

def main():
    L=matches(); wins=windows(L); P=load_panel(L,wins)
    P["dstr"]=P.date.dt.strftime("%Y-%m-%d"); P["emerg"]=(P.klass=="emerging").astype(int)
    rows_d=[]; rows_l=[]; rows_s=[]

    # (1) DISTRACTION: equities volume + parkinson; fx parkinson (no daily volume)
    for kind,ycol,yname,sub in [("equity","lvol","log volume",P[P.kind.isin(["index","stock"])]),
                                 ("equity","park","volatility(hi/lo)",P[P.kind.isin(["index","stock"])]),
                                 ("fx","park","FX volatility(hi/lo)",P[P.kind=="fx"])]:
        s=sub.dropna(subset=[ycol]); s=s[np.isfinite(s[ycol])]
        if not len(s): continue
        m=feols(f"{ycol} ~ own_play | ticker + dstr", data=s, vcov={"CRV1":"dstr"}); r=m.tidy().loc["own_play"]
        rows_d.append(dict(kind=kind,outcome=yname,coef=round(r["Estimate"],4),pct=round(np.expm1(r["Estimate"])*100,2),
                           se=round(r["Std. Error"],4),p=round(r["Pr(>|t|)"],4),n=int(m._N),
                           play_days=int(s.loc[s.own_play==1,"dstr"].nunique())))

    # (2) LOSER EFFECT: next-session return after W/L/D and elimination, world-return adjusted
    wr=world_ret(); idx=P[P.kind=="index"].merge(wr,left_on="date",right_on="date",how="left")
    idx=idx.dropna(subset=["ret"]); idx=idx[np.isfinite(idx.ret)]
    idx["postL"]=(idx.post_res=="L").astype(int); idx["postW"]=(idx.post_res=="W").astype(int); idx["postD"]=(idx.post_res=="D").astype(int)
    base="ret ~ postL + postW + postD"
    f1=base+(" + wret" if idx.wret.notna().any() else "")
    m1=feols(f1+" | ticker", data=idx, vcov={"CRV1":"dstr"})
    for v in ["postL","postW","postD"]:
        r=m1.tidy().loc[v]; rows_l.append(dict(spec="all matches",term=v,bps=round(r["Estimate"]*1e4,1),
                            se_bps=round(r["Std. Error"]*1e4,1),p=round(r["Pr(>|t|)"],4),n=int(m1._N)))
    # elimination interaction (loss x elimination = knocked out)
    idx["postL_elim"]=idx.postL*idx.post_elim
    m2=feols("ret ~ postL + postL_elim + postW + postD"+(" + wret" if idx.wret.notna().any() else "")+" | ticker", data=idx, vcov={"CRV1":"dstr"})
    for v in ["postL","postL_elim"]:
        r=m2.tidy().loc[v]; rows_l.append(dict(spec="elim-split",term=v,bps=round(r["Estimate"]*1e4,1),
                            se_bps=round(r["Std. Error"]*1e4,1),p=round(r["Pr(>|t|)"],4),n=int(m2._N)))
    # emerging-only loser effect
    em=idx[idx.emerg==1]
    if len(em)>200 and em.postL.sum()>30:
        m3=feols("ret ~ postL + postW + postD"+(" + wret" if em.wret.notna().any() else "")+" | ticker", data=em, vcov={"CRV1":"dstr"})
        r=m3.tidy().loc["postL"]; rows_l.append(dict(spec="emerging only",term="postL",bps=round(r["Estimate"]*1e4,1),
                            se_bps=round(r["Std. Error"]*1e4,1),p=round(r["Pr(>|t|)"],4),n=int(m3._N)))

    # (3) SIZE HETEROGENEITY: own_play x emerging on equity volume
    s=P[P.kind.isin(["index","stock"])].dropna(subset=["lvol"]); s=s[np.isfinite(s.lvol)]
    s["own_emerg"]=s.own_play*s.emerg
    m=feols("lvol ~ own_play + own_emerg | ticker + dstr", data=s, vcov={"CRV1":"dstr"})
    for v in ["own_play","own_emerg"]:
        r=m.tidy().loc[v]; rows_s.append(dict(term=v,coef=round(r["Estimate"],4),pct=round(np.expm1(r["Estimate"])*100,2),
                            se=round(r["Std. Error"],4),p=round(r["Pr(>|t|)"],4)))

    for rows,fn,lab in [(rows_d,"home_equities_distraction.csv","DISTRACTION (match-day activity/vol)"),
                        (rows_l,"home_equities_loser.csv","LOSER EFFECT (next-session return)"),
                        (rows_s,"home_equities_size.csv","SIZE HETEROGENEITY (own_play x emerging)")]:
        df=pd.DataFrame(rows); df.to_csv(os.path.join(OUT,fn),index=False)
        print(f"\n=== {lab} ==="); print(df.to_string(index=False))
    print(f"\nPanel: {P.ticker.nunique()} tickers, {P.nation.nunique()} nations, {len(P):,} ticker-days; "
          f"{P[P.own_play==1].dstr.nunique()} distinct play-days (clusters). Daily resolution (finest free for foreign venues).")
    return P
if __name__=="__main__":
    main()
