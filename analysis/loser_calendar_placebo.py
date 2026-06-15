#!/usr/bin/env python3
"""
Placebo test of the tournament-season calendar-drift interpretation of the loser-effect panel. The loser-effect
panel shows the first session after a nation's own match is mildly negative after BOTH a loss (-15bp) and a
win (-10bp), and the paper reads the common negative as a calendar drift over the tournament season rather
than a response to the result. That is testable: if it is a calendar effect, the SAME nations' index-days
that fall inside the tournament window but are NOT post-match sessions should carry the same negative drift.

We build a placebo dummy `season_nonpost` = an own-nation index-day inside [first match, last match + 7d] of
a tournament the nation played, excluding actual post-match sessions, and regress next-day return on it with
the identical ticker + date FE and date-clustering. Prediction the paper's reading implies: season_nonpost is
also ~ -10 to -15bp and indistinguishable from postW/postL. If instead it were ~0, the post-match negative
would be a genuine result reaction and the calendar story would fail. Out: analysis/out/loser_calendar_placebo.csv
"""
import os, warnings; warnings.simplefilter("ignore")
os.environ.setdefault("OPENBLAS_NUM_THREADS","1"); os.environ.setdefault("OMP_NUM_THREADS","1")
import numpy as np, pandas as pd
from pyfixest.estimation import feols
import importlib.util
HERE=os.path.dirname(os.path.abspath(__file__)); ROOT=os.path.join(HERE,"..")
OUT=os.path.join(ROOT,"analysis","out")
# reuse the exact loaders from equities_extended.py so the panel is identical
spec=importlib.util.spec_from_file_location("eqx", os.path.join(HERE,"equities_extended.py"))
eqx=importlib.util.module_from_spec(spec); spec.loader.exec_module(eqx)

def main():
    L=eqx.fjelstul()
    parts=[eqx.attach(eqx.load_idx(n),L) for n in eqx.IDX if eqx.load_idx(n) is not None]
    parts=[p for p in parts if p is not None]
    P=pd.concat(parts,ignore_index=True); P=P[np.isfinite(P.ret)].copy()
    P["dstr"]=P.date.dt.strftime("%Y-%m-%d")
    P["postL"]=(P.post_res=="L").astype(int); P["postW"]=(P.post_res=="W").astype(int); P["postD"]=(P.post_res=="D").astype(int)
    P["is_post"]=(P.postL|P.postW|P.postD).astype(int)
    P["emerg"]=(P.klass=="emerging").astype(int)

    # tournament-season windows [first match, last match + 7d] per year, and the set of years each nation played
    L["year"]=L.year.astype(int)
    twin={y:(g.date.min(), g.date.max()+pd.Timedelta(days=7)) for y,g in L.groupby("year")}
    played={(r.year,r.team) for r in L.itertuples()}

    def in_season(row):
        for y,(a,b) in twin.items():
            if a<=row.date<=b and (y,row.nation) in played:
                return 1
        return 0
    P["in_season"]=P.apply(in_season,axis=1)
    # placebo = own-nation, inside its own tournament season, but NOT an actual post-match session
    P["season_nonpost"]=((P.in_season==1)&(P.is_post==0)).astype(int)

    rows=[]
    def reg(sub,spec,formula,terms):
        m=feols(formula, data=sub, vcov={"CRV1":"dstr"})
        for v in terms:
            r=m.tidy().loc[v]
            rows.append(dict(spec=spec,term=v,bps=round(r["Estimate"]*1e4,1),se_bps=round(r["Std. Error"]*1e4,1),
                             p=round(r["Pr(>|t|)"],4),n=int(m._N)))
    # (1) the placebo beside the result dummies, all nations
    reg(P,"pooled all (20 idx)","ret ~ postL + postW + postD + season_nonpost | ticker + dstr",
        ["postL","postW","postD","season_nonpost"])
    # (2) developed subset (the cell the paper cites for the -15/-10bp drift)
    reg(P[P.emerg==0],"developed only","ret ~ postL + postW + postD + season_nonpost | ticker + dstr",
        ["postL","postW","postD","season_nonpost"])
    # (3) placebo alone (cleanest read of the seasonal drift)
    reg(P,"placebo alone","ret ~ season_nonpost | ticker + dstr",["season_nonpost"])

    res=pd.DataFrame(rows); res.to_csv(os.path.join(OUT,"loser_calendar_placebo.csv"),index=False)
    print(res.to_string(index=False))
    npost=int(P.season_nonpost.sum()); ndays=int(P.loc[P.season_nonpost==1,"dstr"].nunique())
    print(f"\nplacebo obs (season non-post own-nation index-days): {npost:,} across {ndays} date-clusters")
    print("If season_nonpost ~ postW ~ postL (all mildly negative, not distinguishable), the common drift is calendar.")
if __name__=="__main__":
    main()
