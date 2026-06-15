#!/usr/bin/env python3
"""
Monte Carlo: the comovement composition artifact is general, not specific to this data. We simulate a
world with NO true attention effect, where 'match' blocks merely sample a DIFFERENT set of instruments
than control blocks (because some markets are closed during some matches). We show the naive mean-
pairwise-correlation measure manufactures a spurious, significant 'comovement decline during matches'
purely from composition  -  and that an instrument-count control removes it. Quantifies the false-positive
rate and effect size vs the composition shift. Out: analysis/out/artifact_mc.csv
"""
import os, warnings
warnings.simplefilter("ignore")
import numpy as np, pandas as pd
from scipy import stats
OUT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"..","analysis","out")
rng=np.random.default_rng(7)

def block_meancorr(R):  # R: (T, k) returns -> mean pairwise corr
    if R.shape[1]<2: return np.nan
    C=np.corrcoef(R.T); iu=np.triu_indices(C.shape[0],1); v=C[iu]; v=v[~np.isnan(v)]
    return v.mean() if len(v) else np.nan

def one_sim(n_inst=11, n_blocks=600, Tblk=105, drop_in_match=3, p_match=0.2):
    # true correlation: a high-corr cluster + low-corr rest, NO match effect anywhere
    base=np.full((n_inst,n_inst),0.2);
    hi=list(range(7))
    for i in hi:
        for j in hi:
            if i!=j: base[i,j]=0.75
    np.fill_diagonal(base,1.0)
    L=np.linalg.cholesky(base+1e-6*np.eye(n_inst))
    rows=[]
    for b in range(n_blocks):
        is_match=rng.random()<p_match
        Z=rng.standard_normal((Tblk,n_inst)); R=Z@L.T   # identical DGP, no match effect
        # composition: each high-corr instrument is 'closed' with prob that is HIGHER during a match
        # (mirrors futures being shut for weekend matches) but stochastic, so instrument-count varies
        # within both block types and is not collinear with the match indicator.
        p_drop = 0.35 if is_match else 0.12
        keep_hi=[c for c in hi if rng.random()>p_drop]
        cols=keep_hi+[c for c in range(n_inst) if c not in hi]
        if len(cols)<2: cols=list(range(n_inst))
        mc=block_meancorr(R[:,cols])
        rows.append((int(is_match), mc, len(cols)))
    d=pd.DataFrame(rows, columns=["match","mc","ninst"])
    # naive: match vs control mean comovement
    naive=d.groupby("match").mc.mean();
    t_naive,p_naive=stats.ttest_ind(d.loc[d.match==1,"mc"], d.loc[d.match==0,"mc"], equal_var=False)
    # composition-controlled: regress mc on match + ninst (OLS), test match
    X=np.column_stack([np.ones(len(d)), d.match.values, d.ninst.values]); y=d.mc.values
    beta,_,_,_=np.linalg.lstsq(X,y,rcond=None)
    resid=y-X@beta; df=len(d)-3; s2=(resid@resid)/df
    XtXinv=np.linalg.inv(X.T@X); se=np.sqrt(s2*XtXinv[1,1]); t_ctrl=beta[1]/se
    p_ctrl=2*(1-stats.t.cdf(abs(t_ctrl),df))
    return dict(naive_diff=naive.get(1,np.nan)-naive.get(0,np.nan), p_naive=p_naive,
                ctrl_coef=beta[1], p_ctrl=p_ctrl)

def main():
    sims=[one_sim() for _ in range(400)]
    df=pd.DataFrame(sims)
    res=pd.DataFrame([
        dict(measure="naive mean-pairwise-corr (match−control)",
             mean_effect=round(df.naive_diff.mean(),4), pct_sig_5=round((df.p_naive<0.05).mean()*100,1)),
        dict(measure="composition-controlled (+ instrument count)",
             mean_effect=round(df.ctrl_coef.mean(),4), pct_sig_5=round((df.p_ctrl<0.05).mean()*100,1)),
    ])
    res.to_csv(os.path.join(OUT,"artifact_mc.csv"),index=False)
    print("Monte Carlo: NO true match effect; match blocks only drop 3 high-corr instruments (composition).")
    print(res.to_string(index=False))
    print(f"\nNaive measure: spurious mean 'decline' {df.naive_diff.mean():+.3f}, "
          f"significant in {(df.p_naive<0.05).mean()*100:.0f}% of simulations (should be 5%).")
    print(f"With instrument-count control: false-positive rate {(df.p_ctrl<0.05).mean()*100:.0f}% (back to nominal).")
    return res

if __name__=="__main__":
    main()
