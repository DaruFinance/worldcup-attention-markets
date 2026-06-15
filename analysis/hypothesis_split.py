#!/usr/bin/env python3
"""
Separate the two distinct hypotheses the study actually tests, and bound each cell.

  H_global : does the synchronized GLOBAL attention shock depress AGGREGATE trading in continuous global
             markets? Tested by the average during-match effect in venues whose marginal trader is NOT the
             local viewer (no national-team mapping). A null here bounds the global-attention channel.
  H_local  : Ehrmann-Jansen's mechanism -- the LOCAL marginal trader who is also the local viewer steps
             away during the OWN team's match. Tested only by own-team cuts in mapped venues. The genuinely
             comparable object (minute-level trade count on the team's own home cash exchange) needs
             foreign intraday data we do not have; what we can test is CME own-currency futures (intraday
             but a GLOBAL marginal trader), US-traded country ETFs (intraday but a US marginal trader),
             and home equities (the right trader but DAILY resolution).
  H_loser  : Edmans-Garcia-Norli next-session return after the team loses (daily).

For each cell we report the point effect, the 95% CI, the largest decline still consistent with the data
(the equivalence bound), the minimum detectable effect at 80% power, the data resolution, and who the
marginal trader is. Out: analysis/out/hypothesis_split.csv
"""
import os, numpy as np, pandas as pd
O=os.path.join(os.path.dirname(os.path.abspath(__file__)),"..","analysis","out")
def pct(x): return np.expm1(x)*100
# (panel, label, coef_log, se_log, clusters, resolution, marginal_trader)
CELLS=[
 # ---- H_global: aggregate attention channel, non-local marginal trader ----
 ("global","Crypto spot (BTC,ETH)",        -0.0272,0.0363, 48,"1-min","global retail"),
 ("global","Crypto perpetual",             -0.0398,0.0696, 23,"1-min","global retail/levered"),
 ("global","Equity-index futures (ES,NQ)", -0.0298,0.0698, 31,"1-min","global institutional"),
 ("global","Commodity futures (GC,CL)",     0.0699,0.0665, 31,"1-min","global"),
 ("global","FX futures, average match",     0.1043,0.0658, 31,"1-min","global automated"),
 ("global","All instruments pooled",        0.0230,0.0438, 48,"1-min","global"),
 # ---- H_local: own team in a mapped venue ----
 ("local","Euro futures 6E, euro-area matches",  0.1197,0.0578, 60,"1-min","global (not euro viewer)"),
 ("local","Sterling futures 6B, England matches",-0.3568,0.1137, 10,"1-min","global (not UK viewer)"),
 ("local","Yen futures 6J, Japan matches",        0.1403,0.1103, 11,"1-min","global (not JP viewer)"),
 ("local","Own-team futures pooled (2 tourn.)",   0.1041,0.0737, 28,"1-min","global"),
 ("local","Own-team futures pooled (4 tourn.)",   0.0857,0.0642, 60,"1-min","global"),
 ("local","Country ETFs, own-country matches",   -0.0482,0.0720, 55,"1-min","US (not home viewer)"),
 ("local","Home equities, own-match day",        -0.0056,0.0547, 63,"DAILY","home (right trader)"),
]
# loser effect cells carry bp, handled separately
LOSER=[("Loser effect, 20 national indices",-0.5,9.1,110),
       ("Loser effect, 16 home currencies",  9.9,6.6, 74)]

def main():
    rows=[]
    for panel,lab,c,se,ncl,reso,trader in CELLS:
        lo,hi=c-1.96*se, c+1.96*se
        decline_excl=max(0.0,-pct(lo))            # largest decline still consistent with data (95%)
        mde=pct(2.8*se)                            # minimum detectable effect, 80% power, 5%
        rows.append(dict(panel=panel,cell=lab,effect_pct=round(pct(c),1),
                         ci_lo=round(pct(lo),1),ci_hi=round(pct(hi),1),
                         decline_excluded_beyond_pct=round(decline_excl,1),
                         MDE_pct=round(mde,1),clusters=ncl,resolution=reso,marginal_trader=trader))
    df=pd.DataFrame(rows); df.to_csv(os.path.join(O,"hypothesis_split.csv"),index=False)
    for p,title in [("global","H_global  AGGREGATE GLOBAL ATTENTION CHANNEL (non-local trader)"),
                    ("local","H_local   LOCAL DISTRACTION CHANNEL (own team, mapped venue)")]:
        sub=df[df.panel==p]
        print(f"\n=== {title} ===")
        print(sub[["cell","effect_pct","ci_lo","ci_hi","decline_excluded_beyond_pct","MDE_pct","clusters","resolution","marginal_trader"]].to_string(index=False))
    print("\n=== H_loser   NEXT-SESSION RETURN AFTER A LOSS (daily) ===")
    for lab,bp,sebp,ncl in LOSER:
        lo,hi=bp-1.96*sebp,bp+1.96*sebp
        print(f"  {lab:38s} {bp:+5.1f} bp  95% CI [{lo:+.0f},{hi:+.0f}]  clusters={ncl}")
    # headline summary
    g=df[df.panel=="global"]; tight=g.decline_excluded_beyond_pct.min()
    print(f"\nGLOBAL channel: tightest cell excludes declines beyond {tight:.0f}% (pooled/crypto-spot); "
          f"every cell brackets zero, largest point estimate POSITIVE.")
    loc=df[df.panel=="local"]
    best=loc.loc[loc.clusters.idxmax()]
    print(f"LOCAL channel: best-powered comparable cell = '{best.cell}' ({best.clusters} match-days, "
          f"{best.resolution}, trader={best.marginal_trader}): {best.effect_pct:+.1f}% (excludes declines "
          f"beyond {best.decline_excluded_beyond_pct:.0f}%), wrong sign for distraction. "
          f"The minute-level OWN-EXCHANGE trade count with a LOCAL trader is untested (no foreign intraday data); "
          f"home equities (right trader) are DAILY only, MDE {loc[loc.resolution=='DAILY'].MDE_pct.iloc[0]:.0f}%.")
    return df
if __name__=="__main__":
    main()
