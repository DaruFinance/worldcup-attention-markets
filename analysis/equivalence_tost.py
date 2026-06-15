#!/usr/bin/env python3
"""
Formal equivalence (TOST) on the during-match nulls. For each headline coefficient (coef, se on the
log scale) the smallest symmetric margin within which we can declare statistical equivalence at the
5% level is Δ* = |coef| + 1.645·se (both one-sided tests reject). We report Δ* in % and whether we
formally reject an effect as large as the literature's national-cash-equity declines (30%).
Reads existing coefficient tables; writes analysis/out/equivalence_tost.csv.
"""
import os
import math
import numpy as np, pandas as pd
ROOT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"..")
OUT=os.path.join(ROOT,"analysis","out")
Z=1.645  # one-sided 5%
LIT=np.log(1.30)  # 30% literature effect on log scale

def tost_row(label, coef, se):
    dstar=abs(coef)+Z*se
    return dict(estimate=label, coef=round(coef,4), se=round(se,4),
                equiv_margin_pct=round(np.expm1(dstar)*100,1),
                rejects_30pct=("yes" if dstar<LIT else "no"),
                tost_p_vs_30=round(1-0.5*(1+math.erf((LIT-abs(coef))/se/np.sqrt(2))),4) if se>0 else np.nan)

def main():
    rows=[]
    xm=pd.read_csv(os.path.join(OUT,"xm_main.csv"))
    for _,r in xm[xm.outcome=="lvol"].iterrows():
        rows.append(tost_row(f"during-match volume / {r['group']}", r["coef"], r["se"]))
    pd_=pd.read_csv(os.path.join(OUT,"pooled_domestic.csv"))
    om=pd_[(pd_.term=="own_match")&(pd_.outcome=="lvol")&(pd_.spec=="all_mapped")]
    if len(om): rows.append(tost_row("pooled own-team volume (2 tournaments)", om.iloc[0]["coef"], om.iloc[0]["se"]))
    ot=pd.read_csv(os.path.join(OUT,"own_team_4tourn.csv"))
    om4=ot[(ot.term=="own_match")&(ot.outcome=="lvol")]
    if len(om4): rows.append(tost_row("pooled own-team volume (4 tournaments)", om4.iloc[0]["coef"], om4.iloc[0]["se"]))
    lq=pd.read_csv(os.path.join(OUT,"liquidity.csv"))
    for _,r in lq[lq.group=="ALL"].iterrows():
        rows.append(tost_row(f"liquidity / {r['outcome']}", r["coef"], r["se"]))
    res=pd.DataFrame(rows); res.to_csv(os.path.join(OUT,"equivalence_tost.csv"),index=False)
    pd.set_option("display.width",160)
    print(res.to_string(index=False))
    n=len(res); rej=(res.rejects_30pct=="yes").sum()
    print(f"\n{rej}/{n} estimates formally reject (TOST, 5%) an effect as large as the literature's 30%.")
    return res

if __name__=="__main__":
    main()
