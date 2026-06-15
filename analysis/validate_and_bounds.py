#!/usr/bin/env python3
"""(1) Treatment validation via Wikipedia daily pageviews: tournament salience.
   (2) Equivalence / power bounds on the cross-market during-match null."""
import os
import numpy as np, pandas as pd
from scipy import stats

ROOT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"..")
OUT=os.path.join(ROOT,"analysis","out"); MDIR=os.path.join(ROOT,"data","matches")
CTRL=os.path.join(ROOT,"data","controls")

def wiki_validation():
    w=pd.read_parquet(os.path.join(CTRL,"wiki_daily.parquet"))
    w["date"]=pd.to_datetime(w["ts"],utc=True).dt.date
    m=pd.read_parquet(os.path.join(MDIR,"matches_all.parquet"))
    m["d"]=pd.to_datetime(m["kickoff_utc"],utc=True).dt.date
    out=[]
    for yr in (2018,2022):
        ww=w[w["tournament"]==yr].groupby("date")["views"].sum()
        md=m[m["tournament"]==yr]
        span=(md["d"].min(), md["d"].max())
        mday_counts=md.groupby("d").size()
        in_t=ww[(ww.index>=span[0])&(ww.index<=span[1])]
        buf=ww[(ww.index<span[0])|(ww.index>span[1])]
        # within tournament: views vs daily match count
        idx=in_t.index.intersection(mday_counts.index)
        corr=np.corrcoef(in_t.reindex(mday_counts.index).fillna(in_t.min()).values,
                         mday_counts.values)[0,1] if len(mday_counts)>3 else np.nan
        out.append(dict(tournament=yr, mean_views_tournament=int(in_t.mean()),
                        mean_views_buffer=int(buf.mean()) if len(buf) else None,
                        ratio=round(in_t.mean()/buf.mean(),1) if len(buf) and buf.mean()>0 else None,
                        corr_views_vs_matchcount=round(float(corr),3)))
    df=pd.DataFrame(out); df.to_csv(os.path.join(OUT,"wiki_validation.csv"),index=False)
    return df

def bounds():
    d=pd.read_csv(os.path.join(OUT,"xm_main.csv"))
    d=d[d["outcome"].isin(["lvol","ltrades"])].copy()
    # 95% CI on coef -> % effect bounds
    d["lo"]=d["coef"]-1.96*d["se"]; d["hi"]=d["coef"]+1.96*d["se"]
    d["pct_point"]=(np.expm1(d["coef"])*100)
    d["pct_lo"]=(np.expm1(d["lo"])*100); d["pct_hi"]=(np.expm1(d["hi"])*100)
    # one-sided: largest decline we can rule out at 95% = pct_lo (most negative bound)
    d["rule_out_decline_beyond_%"]=d["pct_lo"].round(1)
    keep=d[["group","outcome","pct_point","pct_lo","pct_hi"]].round(2)
    keep.to_csv(os.path.join(OUT,"equivalence_bounds.csv"),index=False)
    return keep

if __name__=="__main__":
    print("=== TREATMENT VALIDATION (Wikipedia daily pageviews) ===")
    print(wiki_validation().to_string(index=False))
    print("\n=== EQUIVALENCE / POWER BOUNDS on during-match % effect (2018+2022) ===")
    print(bounds().to_string(index=False))
    print("\n(pct_lo = most negative effect inside 95% CI; declines beyond it are ruled out)")
