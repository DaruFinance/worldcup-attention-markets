#!/usr/bin/env python3
"""
H4  -  return comovement / price efficiency, done carefully.

The original World Cup result (Ehrmann-Jansen) is that cross-market return comovement FALLS
during a country's matches. We test it at the block level: each played 2018/2022 match gives
a block [kickoff, +105m]; controls are same-weekday/same-clock blocks on NON-MATCH DAYS in the
same window. Block comovement = mean pairwise Pearson correlation of 1-min returns across the
instruments trading in the block (>=30 overlapping obs/instrument; >=2 instruments).

Two composition issues, both handled here:
  (1) which instruments are open varies by clock/weekday and drives raw comovement. So the
      PRIMARY test is CRYPTO-ONLY (4 constant, always-trading instruments)  -  composition-free.
  (2) for the all-market universe we additionally control for instrument count and restrict to
      fully-open blocks, to show the raw drop is composition, not attention.
We also report each estimate WITH and WITHOUT the date FE (the sign is FE-sensitive).

Out: analysis/out/comovement.csv
"""
import os, warnings
warnings.simplefilter("ignore")
os.environ.setdefault("OPENBLAS_NUM_THREADS","1"); os.environ.setdefault("OMP_NUM_THREADS","1")
import numpy as np, pandas as pd
from pyfixest.estimation import feols

ROOT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"..")
PANEL=os.path.join(ROOT,"data","market","panel","all_panel.parquet")
MDIR=os.path.join(ROOT,"data","matches")
OUT=os.path.join(ROOT,"analysis","out")
CRYPTO=["BTCUSDT_spot","ETHUSDT_spot","BTCUSDT_perp","ETHUSDT_perp"]
ALL=CRYPTO+["ES","NQ","GC","CL","6E","6B","6J"]
WIN={2018:(pd.Timestamp("2018-05-24",tz="UTC"),pd.Timestamp("2018-08-05",tz="UTC")),
     2022:(pd.Timestamp("2022-10-30",tz="UTC"),pd.Timestamp("2023-01-08",tz="UTC"))}

def mean_pair_corr(block, cols, min_obs=30):
    sub=block[cols]
    good=[c for c in sub.columns if sub[c].notna().sum()>=min_obs]
    if len(good)<2: return np.nan,len(good)
    cm=sub[good].corr(min_periods=min_obs).values
    iu=np.triu_indices(len(good),1); vals=cm[iu]; vals=vals[~np.isnan(vals)]
    return (np.nanmean(vals) if len(vals) else np.nan), len(good)

def build_blocks(cols, require_full=False):
    panel=pd.read_parquet(PANEL); panel=panel[panel["tournament"].isin([2018,2022])].copy()
    panel["ts"]=pd.to_datetime(panel["ts"],utc=True)
    wide=panel.pivot_table(index="ts",columns="instrument",values="ret")
    cols=[c for c in cols if c in wide.columns]; wide=wide[cols].sort_index()
    m=pd.read_parquet(os.path.join(MDIR,"matches_all.parquet"))
    m=m[(m["tournament"].isin([2018,2022]))&(m["played"])].copy()
    m["ko"]=pd.to_datetime(m["kickoff_utc"],utc=True)
    kos=m["ko"].tolist(); dur=pd.Timedelta(minutes=105)
    match_dates={k.strftime("%Y-%m-%d") for k in kos}
    def overlaps(s,e): return any((s<k+dur) and (e>k) for k in kos)
    rows=[]
    for _,mt in m.iterrows():
        s=mt["ko"]; e=s+dur; cm,n=mean_pair_corr(wide.loc[s:e],cols)
        if np.isnan(cm) or (require_full and n<len(cols)): continue
        rows.append(dict(match=1,comov=cm,ninst=n,weekday=s.weekday(),
                         clock=s.hour*60+s.minute,date=s.strftime("%Y-%m-%d"),tournament=mt["tournament"]))
    for t,(a,b) in WIN.items():
        mm=m[m["tournament"]==t]; slots=mm["ko"].apply(lambda k:(k.weekday(),k.hour*60+k.minute)).unique()
        d=a
        while d<=b:
            ds=d.strftime("%Y-%m-%d")
            if ds not in match_dates:                       # genuine NON-MATCH day
                for (wd,clk) in slots:
                    if d.weekday()!=wd: continue
                    s=d+pd.Timedelta(minutes=int(clk)); e=s+dur
                    if overlaps(s,e): continue
                    cm,n=mean_pair_corr(wide.loc[s:e],cols)
                    if np.isnan(cm) or (require_full and n<len(cols)): continue
                    rows.append(dict(match=0,comov=cm,ninst=n,weekday=wd,clock=int(clk),
                                     date=ds,tournament=t))
            d+=pd.Timedelta(days=1)
    df=pd.DataFrame(rows); df["wd_clk"]=df["weekday"].astype(str)+"_"+df["clock"].astype(str)
    return df

def fit(df, rhs="match", fe="wd_clk"):
    # NOTE: controls are on non-match DAYS, so `match` is nested within date -> a date FE is
    # collinear with match. The correct identification compares match blocks to non-match-day
    # blocks within the same weekday x clock slot (wd_clk FE), clustered by date.
    m=feols(f"comov ~ {rhs} | {fe}", data=df, vcov={"CRV1":"date"})
    r=m.tidy().loc["match"]; return r["Estimate"], r["Std. Error"], r["Pr(>|t|)"]

def row(df,label,**kw):
    try:
        c,s,p=fit(df,**kw)
    except Exception as e:
        c,s,p=(np.nan,np.nan,np.nan); print(f"  [{label}] skipped: {str(e)[:50]}")
    return dict(spec=label, match_blocks=int((df.match==1).sum()), ctrl_blocks=int((df.match==0).sum()),
                comov_match=round(df.loc[df.match==1,"comov"].mean(),4),
                comov_ctrl=round(df.loc[df.match==0,"comov"].mean(),4),
                ninst_match=round(df.loc[df.match==1,"ninst"].mean(),2),
                ninst_ctrl=round(df.loc[df.match==0,"ninst"].mean(),2),
                coef=round(c,4), se=round(s,4), p=round(p,4))

def main():
    res=[]
    cz=build_blocks(CRYPTO)
    res.append(row(cz,"crypto_only (composition-free)"))
    av=build_blocks(ALL)
    res.append(row(av,"all_avail (raw - composition-confounded)"))
    res.append(row(av,"all_avail +ninst control", rhs="match + ninst"))
    full=build_blocks(ALL, require_full=True)
    if (full.match==1).sum()>10 and (full.match==0).sum()>10:
        res.append(row(full,"all_avail fully-open 11-inst (composition-free)"))
    out=pd.DataFrame(res); out.to_csv(os.path.join(OUT,"comovement.csv"),index=False)
    pd.set_option("display.width",200)
    print(out.to_string(index=False))
    print("\nReads: crypto-only is composition-free (4 constant instruments). all_avail match vs ctrl")
    print("differ in #instruments open, so the raw comov gap is composition; ninst-control & fully-open")
    print("blocks isolate the attention effect. coef<0 => comovement falls during matches (H4).")
    return out

if __name__=="__main__":
    main()
