#!/usr/bin/env python3
"""
Master multiple-testing table. Collect EVERY during-match / own-team primary coefficient produced
across all channels (activity, liquidity, options, efficiency, comovement, intensity, sentiment,
domestic, attention) and apply one global Benjamini-Hochberg FDR. Answers definitively whether ANY
result survives once the full battery of tests is corrected together.
Out: analysis/out/master_fdr.csv
"""
import os
import numpy as np, pandas as pd
ROOT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"..")
O=os.path.join(ROOT,"analysis","out")

def bh(p):
    p=np.asarray(p,float); n=len(p); o=np.argsort(p); q=np.empty(n); c=1.0
    for i in range(n-1,-1,-1): c=min(c,p[o[i]]*n/(i+1)); q[o[i]]=c
    return q

def grab(fn, pcol, label, filt=None):
    fp=os.path.join(O,fn)
    if not os.path.exists(fp): return []
    d=pd.read_csv(fp)
    if filt: d=d[filt(d)]
    out=[]
    for _,r in d.iterrows():
        pv=r.get(pcol)
        if pd.isna(pv): continue
        desc=" / ".join(str(r[c]) for c in d.columns if c in ("group","outcome","test","term","spec","instrument","window") and pd.notna(r[c]))
        out.append((f"{label}: {desc}", float(pv)))
    return out

def main():
    tests=[]
    # primary during-match activity (cross-market)  -  exclude ALL aggregate to avoid double count
    tests+=grab("xm_main.csv","p","activity", lambda d:(d.group!="ALL")&(d.outcome.isin(["lvol","ltrades","absret","hlrange"])))
    tests+=grab("liquidity.csv","p","liquidity", lambda d:d.group!="ALL")
    tests+=grab("options.csv","p","options")
    tests+=grab("efficiency.csv","p","efficiency")
    tests+=grab("comovement.csv","p","comovement")
    tests+=grab("intensity.csv","p","intensity")
    tests+=grab("reg_goal.csv","p","goal-window")
    tests+=grab("sentiment.csv","p","sentiment", lambda d:d.spec=="win_loss")  # drop win_loss_upset (nested duplicate of win_loss)
    tests+=grab("attention_validation.csv","p","attention-scaling")
    tests+=grab("domestic_attention.csv","p","domestic-attention")
    tests+=grab("fx_spot.csv","p","fx-spot")
    tests+=grab("liquidity.csv","p","liquidity-extra", lambda d:d.group=="ALL")
    tests+=grab("stakes.csv","p","stakes")
    tests+=grab("pooled_domestic.csv","p","own-team", lambda d:(d.term=="own_match")&(~d.get("spec","").astype(str).str.contains("placebo")))
    tests+=grab("xm_domestic.csv","p","single-market domestic")

    # --- home-market / home-currency family (new) ---
    # per-currency during-match home-FX activity: SPOT pairs only (6B/6E/6J futures already counted above)
    def addrows(fn, pcol, label, keep):
        fp=os.path.join(O,fn)
        if not os.path.exists(fp): return []
        d=pd.read_csv(fp); out=[]
        for _,r in d.iterrows():
            if keep(r) and pd.notna(r.get(pcol)):
                key="/".join(str(r[c]) for c in d.columns if c in ("currency","home","outcome","kind","spec","term","nation","index") and pd.notna(r[c]))
                out.append((f"{label}: {key}", float(r[pcol])))
        return out
    spot={"USDBRL","USDMXN","USDJPY","AUDUSD","USDCAD","USDCHF","GBPUSD","EURUSD"}
    tests+=addrows("fx_home_country.csv","p","home-FX (per-ccy)", lambda r: r.get("currency") in spot and r.get("outcome")=="activity")
    tests+=addrows("home_equities_distraction.csv","p","home-equity distraction", lambda r: r.get("kind")=="equity")
    tests+=addrows("home_equities_loser.csv","p","home-equity loser", lambda r: r.get("spec")=="all matches" and r.get("term")=="postL")
    tests+=addrows("home_equities_size.csv","p","home-equity size", lambda r: r.get("term")=="own_emerg")
    tests+=addrows("fx_extended_loser.csv","p","home-FX loser (2002-22)", lambda r: r.get("spec") in ("pooled all (16 ccy)","size: postL x emerging") and r.get("term") in ("postL","postL_emerg"))
    tests+=addrows("eq_extended_loser.csv","p","home-equity loser (1998-22)", lambda r: r.get("spec") in ("pooled all (20 idx)","size: postL x emerging") and r.get("term") in ("postL","postL_emerg"))
    # NB: single-nation standalone loser-effect cells are NOT included  -  they rest on ~5-8 losses per
    # nation and are not validly estimable (degenerate SEs), the very point of the cluster-count argument.

    df=pd.DataFrame(tests, columns=["test","p"]).dropna()
    df["q_bh"]=bh(df["p"].values)
    df=df.sort_values("p").reset_index(drop=True)
    df.to_csv(os.path.join(O,"master_fdr.csv"),index=False)
    n=len(df); nom=int((df.p<0.05).sum()); surv=int((df.q_bh<0.05).sum())
    exp_false=0.05*n
    print(f"TOTAL during-match/own-team tests pooled: {n}")
    print(f"  nominally p<0.05: {nom}  (expected by chance at 5%: {exp_false:.1f})")
    print(f"  surviving global BH-FDR q<0.05: {surv}")
    print("\nsmallest 8 p-values:")
    print(df.head(8).to_string(index=False))
    return df

if __name__=="__main__":
    main()
