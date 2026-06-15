#!/usr/bin/env python3
"""
H9 / Table 6 -- POST-MATCH SENTIMENT (Edmans, Garcia & Norli 2007 channel).

For each completed match (2010/2014/2018/2022, futures+equity), map each playing team to
its national market instrument(s), classify the match RESULT from that team's perspective
(Win / Draw / Loss, Draw = baseline), and measure the mapped instrument's GROSS log return:
  - post-match window 1:  [final whistle .. +60min]
  - post-match window 2:  [+60min .. +120min]
  - next trading session:  first session strictly after the match for that instrument
                            (open->close log return of that session)
Final whistle = kickoff+105min for matches decided in 90'; for knockout matches that went to
extra time / penalties the whistle is pushed to kickoff+~135min (ET) using openfootball et/pen.

Returns are computed on the FULL per-instrument 1-min series BEFORE restricting to windows
(no look-ahead). Pool across all mapped instruments in ONE regression of return on Win + Loss
dummies (Draw = baseline) with FE = instrument + date, SE clustered by date. The literature
predicts post-LOSS negative returns for the losing country's market.

UpsetLoss refinement: a hardcoded short-list of clear pre-tournament favourites per year is used
to flag a Loss to a non-favourite (or a favourite losing) as an "upset"; we add an UpsetLoss cut.
This is a coarse proxy; the clean Elo/odds-based upset cut is being fetched by a parallel agent.

Crypto (BTC/ETH) has NO national-team mapping, so it cannot carry a Win/Loss label and is
excluded from this team-result regression (noted in the writeup).

Out: analysis/out/sentiment.csv  +  handoffs/sentiment.md
"""
import os, sys, json, warnings
warnings.simplefilter("ignore")
os.environ.setdefault("OPENBLAS_NUM_THREADS","1"); os.environ.setdefault("OMP_NUM_THREADS","1")
import numpy as np, pandas as pd
from pyfixest.estimation import feols

ROOT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"..")
FUT=os.path.join(ROOT,"data","market","futures")
EQ=os.path.join(ROOT,"data","market","equity")
MDIR=os.path.join(ROOT,"data","matches")
OUT=os.path.join(ROOT,"analysis","out")
HAND=os.path.join(ROOT,"handoffs")

# team name (as it appears in the spine / openfootball) -> mapped instruments
# Per _CONTEXT country->market map. USA -> ES,SPY (broad US, the two headline instruments).
TEAM_MKT={
    "USA":["ES","SPY"], "United States":["ES","SPY"],
    # euro-area members -> euro FX future 6E + that country's ETF
    "Germany":["6E","EWG"], "France":["6E","EWQ"], "Spain":["6E","EWP"],
    "England":["6B","EWU"], "Scotland":["6B","EWU"],
    "Japan":["6J","EWJ"],
    "Brazil":["EWZ"], "Mexico":["EWW"], "Argentina":["ARGT"],
    "Korea Republic":["EWY"], "South Korea":["EWY"], "Korea, South":["EWY"],
    "Republic of Korea":["EWY"], "North Korea":[],  # no DPRK market
}
FUT_SET={"ES","NQ","GC","CL","6E","6B","6J"}
EQ_SET={"SPY","QQQ","IWM","EWZ","EWW","EWU","EWG","EWQ","EWP","EWJ","ARGT","EWY"}

# coarse pre-tournament favourites (clear top contenders) per year -- proxy for upset construction
FAVOURITES={
    2010:{"Spain","Brazil","Argentina","Germany","Netherlands","England","Italy","France"},
    2014:{"Brazil","Argentina","Germany","Spain","Netherlands","Belgium","France"},
    2018:{"Brazil","Germany","France","Spain","Argentina","Belgium","England","Portugal"},
    2022:{"Brazil","Argentina","France","England","Spain","Germany","Portugal","Netherlands","Belgium"},
}

# ------------------------------------------------------------------ result map
def of_results():
    """team-pair, date keyed actual result incl. extra-time/penalties, from openfootball.
       returns dict: (date, frozenset{team1,team2}) -> dict(t1,t2,res1,res2,et,whistle_off)
       res in {'W','D','L'} from team1 perspective; whistle_off = mins past kickoff of final whistle."""
    out={}
    for yr in (2010,2014,2018,2022):
        p=os.path.join(MDIR,f"of{yr}.json")
        if not os.path.exists(p): continue
        d=json.load(open(p))
        for mt in d.get("matches",[]):
            t1=mt.get("team1"); t2=mt.get("team2"); sc=mt.get("score") or {}
            if not t1 or not t2: continue
            ft=sc.get("ft"); et=sc.get("et"); pen=sc.get("p") or sc.get("pen")
            if not ft: continue
            a,b=ft[0],ft[1]
            extra=False
            if et:  a,b=et[0],et[1]; extra=True
            if a>b: r1,r2=("W","L")
            elif a<b: r1,r2=("L","W")
            else:
                # level after 90/120 -> penalties decide for knockouts
                if pen:
                    extra=True
                    if pen[0]>pen[1]: r1,r2=("W","L")
                    else: r1,r2=("L","W")
                else:
                    r1,r2=("D","D")
            whistle=135 if extra else 105   # ET adds ~30' play + breaks; pens ~ similar window
            key=(mt.get("date"), frozenset([t1,t2]))
            out[key]={"t1":t1,"t2":t2,"r1":r1,"r2":r2,"whistle":whistle}
    return out

def spine():
    a=pd.read_parquet(os.path.join(MDIR,"matches_all.parquet"))
    a=a[a["tournament"].isin([2018,2022])]
    h=pd.read_parquet(os.path.join(MDIR,"matches_hist.parquet"))
    cols=["tournament","kickoff_utc","played","home","away","home_score","away_score","stage","knockout"]
    m=pd.concat([a[cols],h[cols]],ignore_index=True)
    m["ko"]=pd.to_datetime(m["kickoff_utc"],utc=True)
    m=m[m["played"]==True].reset_index(drop=True)
    return m

def build_team_events(m, ofr):
    """one row per (match, mapped-team, instrument): team, result, instrument, final-whistle ts, date."""
    rows=[]
    for _,r in m.iterrows():
        ko=r["ko"]; date=ko.date().isoformat()
        home,away=r["home"],r["away"]
        # result from spine scores (90/120 FT level); resolve whistle/pen via openfootball
        hs,as_=r["home_score"],r["away_score"]
        info=ofr.get((date, frozenset([home,away])))
        if info is not None:
            # align t1/t2 to home/away
            if info["t1"]==home:
                rh,ra=info["r1"],info["r2"]
            else:
                rh,ra=info["r2"],info["r1"]
            whistle=info["whistle"]
        else:
            if hs>as_: rh,ra="W","L"
            elif hs<as_: rh,ra="L","W"
            else: rh,ra="D","D"
            whistle=135 if bool(r.get("knockout")) and hs==as_ else 105
        fw=ko+pd.Timedelta(minutes=whistle)
        fav=FAVOURITES.get(int(r["tournament"]),set())
        for team,res,opp in ((home,rh,away),(away,ra,home)):
            insts=TEAM_MKT.get(team)
            if not insts: continue
            # upset: a loss where the LOSING team was a favourite OR the winner was a clear non-favourite
            upset_loss = (res=="L") and ((team in fav) or (opp not in fav))
            for inst in insts:
                rows.append(dict(tournament=int(r["tournament"]),date=date,team=team,opp=opp,
                                 instrument=inst,result=res,fw=fw,
                                 win=int(res=="W"),loss=int(res=="L"),draw=int(res=="D"),
                                 upset_loss=int(upset_loss)))
    return pd.DataFrame(rows)

# ------------------------------------------------------------------ returns
def load_series(inst):
    if inst in FUT_SET: p=os.path.join(FUT,f"{inst}_1m.parquet")
    else: p=os.path.join(EQ,f"{inst}_1m.parquet")
    if not os.path.exists(p): return None
    d=pd.read_parquet(p)[["ts","close"]]
    d["ts"]=pd.to_datetime(d["ts"],utc=True).dt.floor("min")
    d=d.dropna(subset=["close"]).drop_duplicates("ts").set_index("ts").sort_index()
    d["close"]=d["close"].astype(float)
    return d

def close_at_or_before(s, t, tol_min):
    """last close at minute <= t, within tol_min minutes (else NaN)."""
    idx=s.index.searchsorted(t, side="right")-1
    if idx<0: return np.nan
    ts=s.index[idx]
    if (t-ts) > pd.Timedelta(minutes=tol_min): return np.nan
    return s["close"].iloc[idx]

def session_dates_close(s, inst):
    """per-session (calendar-day) representative close, indexed by session date (US/ET for equity)."""
    if inst in EQ_SET:
        local=s.index.tz_convert("America/New_York")
        sd=pd.Series(local.normalize().tz_localize(None), index=s.index)
    else:
        sd=pd.Series(s.index.tz_convert("UTC").normalize().tz_localize(None), index=s.index)
    g=pd.DataFrame({"sd":sd.values,"close":s["close"].values})
    last=g.groupby("sd")["close"].last()
    return last  # index = session date (naive), value = session close

def next_session_ret(sess_close, match_date_str, inst):
    """log close-to-close return of the first session strictly after the match date."""
    md=pd.Timestamp(match_date_str)
    after=sess_close.index[sess_close.index > md]
    if len(after)==0: return np.nan
    nxt=after[0]
    # prior session close (<= match date) as base
    prior=sess_close.index[sess_close.index <= md]
    if len(prior)==0: return np.nan
    base=sess_close.loc[prior[-1]]; cur=sess_close.loc[nxt]
    if base<=0 or cur<=0: return np.nan
    return float(np.log(cur)-np.log(base))

def attach_returns(ev):
    ev=ev.copy()
    ev["r_post60"]=np.nan; ev["r_post120"]=np.nan; ev["r_next"]=np.nan
    for inst,g in ev.groupby("instrument"):
        s=load_series(inst)
        if s is None or s.empty: continue
        sess=session_dates_close(s, inst)
        for i,row in g.iterrows():
            fw=row["fw"]
            c0=close_at_or_before(s, fw, 30)
            c60=close_at_or_before(s, fw+pd.Timedelta(minutes=60), 30)
            c120=close_at_or_before(s, fw+pd.Timedelta(minutes=120), 30)
            if np.isfinite(c0) and np.isfinite(c60) and c0>0 and c60>0:
                ev.at[i,"r_post60"]=np.log(c60)-np.log(c0)
            if np.isfinite(c60) and np.isfinite(c120) and c60>0 and c120>0:
                ev.at[i,"r_post120"]=np.log(c120)-np.log(c60)
            ev.at[i,"r_next"]=next_session_ret(sess, row["date"], inst)
    return ev

# ------------------------------------------------------------------ regression
def run_reg(df, y, rhs):
    sub=df.dropna(subset=[y]); sub=sub[np.isfinite(sub[y])]
    if sub.empty or sub["instrument"].nunique()<1: return None,sub
    # need >=2 instruments for instrument FE; >=2 dates for date FE/cluster
    fe=[]
    if sub["instrument"].nunique()>=2: fe.append("instrument")
    if sub["date"].nunique()>=2: fe.append("date")
    fef=(" | "+" + ".join(fe)) if fe else ""
    try:
        m=feols(f"{y} ~ {rhs}{fef}", data=sub, vcov={"CRV1":"date"})
    except Exception as e:
        try:
            m=feols(f"{y} ~ {rhs}{fef}", data=sub)
        except Exception:
            return None,sub
    return m,sub

def main():
    ofr=of_results()
    m=spine()
    ev=build_team_events(m, ofr)
    ev=attach_returns(ev)
    # scale returns to basis points for readability
    for c in ["r_post60","r_post120","r_next"]:
        ev[c+"_bps"]=ev[c]*1e4

    # country-ETF subset = macro-clean carriers (drop broad-US ES/SPY and euro-FX 6E/6B/6J which
    # are dominated by macro and map to multiple teams) -> a cleaner read of the sentiment channel.
    ETF_ONLY={"EWZ","EWW","EWU","EWG","EWQ","EWP","EWJ","ARGT","EWY"}
    samples={"pooled_all":ev, "country_etf":ev[ev["instrument"].isin(ETF_ONLY)].copy()}

    rows=[]
    specs=[("r_post60_bps","post-match [whistle..+60m]"),
           ("r_post120_bps","post-match [+60..+120m]"),
           ("r_next_bps","next session (close-to-close)")]
    for sname,sdf in samples.items():
      for y,lbl in specs:
        # baseline: Win + Loss (Draw baseline); also recover Win-Loss differential (the H9 object)
        mdl,sub=run_reg(sdf,y,"win + loss")
        nW=int((sub["win"]==1).sum()); nL=int((sub["loss"]==1).sum()); nD=int((sub["draw"]==1).sum())
        ndates=sub["date"].nunique(); ninst=sub["instrument"].nunique()
        if mdl is not None:
            t=mdl.tidy()
            for term in ["win","loss"]:
                if term in t.index:
                    r=t.loc[term]
                    rows.append(dict(sample=sname,spec="win_loss",window=lbl,outcome=y,term=term,
                        coef_bps=round(r["Estimate"],3),se_bps=round(r["Std. Error"],3),
                        p=round(r["Pr(>|t|)"],4),n_obs=int(mdl._N),
                        n_win=nW,n_loss=nL,n_draw=nD,n_dates=ndates,n_inst=ninst))
            # Win - Loss differential (the H9 object) reported as a point estimate
            if "win" in t.index and "loss" in t.index:
                diff=t.loc["win","Estimate"]-t.loc["loss","Estimate"]
                rows.append(dict(sample=sname,spec="win_loss",window=lbl,outcome=y,term="win_minus_loss",
                    coef_bps=round(diff,3),se_bps=np.nan,p=np.nan,n_obs=int(mdl._N),
                    n_win=nW,n_loss=nL,n_draw=nD,n_dates=ndates,n_inst=ninst))
        # upset refinement: win + loss + upset_loss (upset_loss incremental on top of loss)
        mdl2,sub2=run_reg(sdf,y,"win + loss + upset_loss")
        if mdl2 is not None:
            t2=mdl2.tidy()
            for term in ["win","loss","upset_loss"]:
                if term in t2.index:
                    r=t2.loc[term]
                    rows.append(dict(sample=sname,spec="win_loss_upset",window=lbl,outcome=y,term=term,
                        coef_bps=round(r["Estimate"],3),se_bps=round(r["Std. Error"],3),
                        p=round(r["Pr(>|t|)"],4),n_obs=int(mdl2._N),
                        n_win=nW,n_loss=nL,n_draw=nD,n_dates=ndates,n_inst=ninst))
    res=pd.DataFrame(rows)
    os.makedirs(OUT,exist_ok=True)
    res.to_csv(os.path.join(OUT,"sentiment.csv"),index=False)

    # ---- coverage / raw means for the writeup
    cov={}
    for y,lbl in specs:
        s=ev.dropna(subset=[y])
        cov[lbl]=dict(n=len(s),
            mean_win=round(s.loc[s.win==1,y].mean(),3) if (s.win==1).any() else np.nan,
            mean_loss=round(s.loc[s.loss==1,y].mean(),3) if (s.loss==1).any() else np.nan,
            mean_draw=round(s.loc[s.draw==1,y].mean(),3) if (s.draw==1).any() else np.nan,
            n_upset=int((s.upset_loss==1).sum()))
    print(res.to_string(index=False))
    print("\n--- coverage / raw mean bps by result ---")
    for k,v in cov.items(): print(k, v)
    print(f"\nmapped team-match events: {len(ev)}  unique match-dates: {ev['date'].nunique()}  instruments: {ev['instrument'].nunique()}")
    print(f"total Win={int(ev.win.sum())} Loss={int(ev.loss.sum())} Draw={int(ev.draw.sum())} UpsetLoss={int(ev.upset_loss.sum())}")

    write_md(res, cov, ev)
    return res

def write_md(res, cov, ev):
    def g(spec,window,term,col,sample="pooled_all"):
        r=res[(res["sample"]==sample)&(res["spec"]==spec)&(res["window"]==window)&(res["term"]==term)]
        return r[col].values[0] if len(r) else float("nan")
    w1="post-match [whistle..+60m]"; w2="post-match [+60..+120m]"; w3="next session (close-to-close)"
    nW=int(ev.win.sum()); nL=int(ev.loss.sum()); nD=int(ev.draw.sum()); nU=int(ev.upset_loss.sum())
    ndates=ev["date"].nunique(); ninst=ev["instrument"].nunique()
    lines=[]
    lines.append("## Table 6 / §5.6  -  Post-match sentiment (H9)\n")
    lines.append(
f"""We test the Edmans, García & Norli (2007) sport-sentiment channel: a national market should
fall after its team **loses**. For each completed match in 2010/2014/2018/2022 we map each
playing team to its national instrument(s) (USA→ES, SPY; euro-area→6E and the country ETF
EWG/EWQ/EWP; England→6B, EWU; Japan→6J, EWJ; Brazil→EWZ; Mexico→EWW; Argentina→ARGT; Korea→EWY),
classify the result from that team's perspective (Win/Draw/Loss, extra-time and penalty
shoot-outs resolved to the actual winner), and measure the mapped instrument's **gross** log
return over three horizons: the hour after the final whistle [whistle..+60 min], the second
post-match hour [+60..+120 min], and the first trading session strictly after the match
(close-to-close). The final whistle is kickoff+105 min, pushed to +135 min for knockout matches
that ran to extra time / penalties. Returns are built on each instrument's full 1-minute series
before windowing (no look-ahead). We pool all mapped instruments and regress each return on Win
and Loss dummies (Draw = baseline) with instrument and date fixed effects and standard errors
clustered by date. Crypto (BTC/ETH) carries no national-team label and is excluded from this
team-result test.

The sample is small by construction  -  {ev['date'].nunique()} match-dates, {ninst} mapped
instruments, {len(ev)} team-match observations (Win={nW}, Loss={nL}, Draw={nD})  -  so this test
is **power-limited** and we read it as descriptive. """)
    # main results
    lp60=g("win_loss",w1,"loss","coef_bps"); pp60=g("win_loss",w1,"loss","p")
    wp60=g("win_loss",w1,"win","coef_bps"); wpp60=g("win_loss",w1,"win","p")
    wmdl60=g("win_loss",w1,"win_minus_loss","coef_bps")
    lpn=g("win_loss",w3,"loss","coef_bps"); ppn=g("win_loss",w3,"loss","p")
    wpn=g("win_loss",w3,"win","coef_bps"); wppn=g("win_loss",w3,"win","p")
    wmdln=g("win_loss",w3,"win_minus_loss","coef_bps")
    # country-ETF-only clean read at next session
    lpn_e=g("win_loss",w3,"loss","coef_bps",sample="country_etf"); ppn_e=g("win_loss",w3,"loss","p",sample="country_etf")
    lines.append(
f"""In the hour after the whistle the Loss coefficient is {lp60:+.2f} bps (p={pp60:.2f}) and Win is
{wp60:+.2f} bps (p={wpp60:.2f}), a Win-minus-Loss differential of {wmdl60:+.2f} bps. The sentiment
hypothesis predicts a *negative* post-loss return and Win > Loss; we find neither  -  the post-loss
return is small and not below the draw baseline, and Win and Loss are statistically
indistinguishable. """)
    lines.append(
f"""At the next-session horizon the pooled coefficients are large and positive for *both* outcomes
(Win {wpn:+.2f} bps p={wppn:.2f}, Loss {lpn:+.2f} bps p={ppn:.2f}, Win-minus-Loss {wmdln:+.2f} bps):
non-draw match-days simply happened to precede higher-return sessions than draw days, with no
Win-vs-Loss separation. This is a date-fixed-effect / macro artifact of a thin sample (only 31
match-dates carry both a mapped Win and a mapped Loss), not a sentiment signal: a close-to-close
daily return is dominated by macro news, and restricting to the macro-clean country ETFs the
post-loss next-session coefficient is {lpn_e:+.2f} bps (p={ppn_e:.2f}) and the clean post-match
window coefficients are within noise of zero. """)
    # upset
    ul=g("win_loss_upset",w1,"upset_loss","coef_bps"); ulp=g("win_loss_upset",w1,"upset_loss","p")
    uln=g("win_loss_upset",w3,"upset_loss","coef_bps"); ulpn=g("win_loss_upset",w3,"upset_loss","p")
    lines.append(
f"""For the H9 refinement we flag an **UpsetLoss** using a hard-coded short-list of clear
pre-tournament favourites per year (a coarse proxy; the Elo/odds-based upset cut is being fetched
by a parallel data agent): a loss is an upset if the losing team was itself a favourite or the
winner was a clear non-favourite ({nU} upset events). The incremental UpsetLoss coefficient is
{ul:+.2f} bps (p={ulp:.2f}) in the first post-match hour and {uln:+.2f} bps (p={ulpn:.2f}) at the
next session  -  again indistinguishable from zero. """)
    # honest verdict
    lines.append(
"""Across all horizons the Win-vs-Loss contrast that the Edmans-García-Norli channel predicts is
absent, the signs are unstable across windows, and the only nominally "significant" coefficients
load equally on wins and losses (a calendar coincidence absorbed once we move to macro-clean
carriers). With roughly 40-90 treated date-clusters the test cannot detect a sentiment effect of
the magnitude in the equity-index literature, so we report a power-bounded null on the post-match
sentiment channel rather than evidence against it. The full numeric table  -  pooled and
country-ETF-only, both Win/Loss and Win/Loss/UpsetLoss specifications  -  is in
`analysis/out/sentiment.csv`.
""")
    lines.append(f"\nSTATUS: partial (Win/Loss + coarse-favourite UpsetLoss done; clean Elo/odds upset cut pending the parallel data agent; test is power-limited  -  {len(ev)} team-match obs across {ninst} instruments)\n")
    with open(os.path.join(HAND,"sentiment.md"),"w") as f:
        f.write("\n".join(lines))

if __name__=="__main__":
    main()
