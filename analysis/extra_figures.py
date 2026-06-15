#!/usr/bin/env python3
"""
Two replacement figures (matplotlib Agg, NEW filenames, do not overwrite fig1/2/4/5):

  fig3_domestic.png   coefficient plot: foreign-team-match vs own-team-match volume effect
                      (lvol) by market grouping, with 95% CIs. Numbers read from
                      analysis/out/pooled_domestic.csv (all_mapped, fx_only) and
                      analysis/out/own_team_4tourn.csv (4-tournament all-mapped).
  fig6_by_tournament.png  the own-team-match (own_match) lvol effect estimated SEPARATELY by
                      tournament (2010, 2014, 2018, 2022) on the mapped index/FX futures, to
                      show stability across tournaments. (Replaces the dropped 2026 figure;
                      the 2026 World Cup is ongoing and excluded.) Estimated here from scratch.

Out: analysis/figures/fig3_domestic.png, analysis/figures/fig6_by_tournament.png
"""
import os, warnings
warnings.simplefilter("ignore")
os.environ.setdefault("OPENBLAS_NUM_THREADS","1"); os.environ.setdefault("OMP_NUM_THREADS","1")
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pyfixest.estimation import feols

ROOT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"..")
FUT=os.path.join(ROOT,"data","market","futures"); MDIR=os.path.join(ROOT,"data","matches")
OUT=os.path.join(ROOT,"analysis","out")
FIG=os.path.join(ROOT,"analysis","figures"); os.makedirs(FIG,exist_ok=True)
OWN={"ES":"usa","NQ":"usa","6E":"euro","6B":"gbp","6J":"jpy"}

# --------------------------------------------------------------------------------------
# FIG 3 : foreign_match vs own_match, lvol, by grouping (read from existing CSVs, in %)
# --------------------------------------------------------------------------------------
def fig3():
    pd_csv=pd.read_csv(os.path.join(OUT,"pooled_domestic.csv"))
    ot=pd.read_csv(os.path.join(OUT,"own_team_4tourn.csv"))
    rows=[]
    # 4-tournament all-mapped (2010-2022)
    for term in ["foreign_match","own_match"]:
        r=ot[(ot.outcome=="lvol")&(ot.term==term)].iloc[0]
        rows.append(("4-tournament\n(2010-2022)",term,r["coef"],r["se"]))
    # 2-tournament all-mapped (2018+2022)
    for term in ["foreign_match","own_match"]:
        r=pd_csv[(pd_csv.spec=="all_mapped")&(pd_csv.outcome=="lvol")&(pd_csv.term==term)].iloc[0]
        rows.append(("2-tournament\nall-mapped\n(2018+2022)",term,r["coef"],r["se"]))
    # FX-only (2018+2022)
    for term in ["foreign_match","own_match"]:
        r=pd_csv[(pd_csv.spec=="fx_only")&(pd_csv.outcome=="lvol")&(pd_csv.term==term)].iloc[0]
        rows.append(("FX-only\n(2018+2022)",term,r["coef"],r["se"]))
    df=pd.DataFrame(rows,columns=["group","term","coef","se"])
    # convert log-point coef + CI to %: expm1(coef +/- 1.96 se)*100
    df["pct"]=np.expm1(df["coef"])*100
    df["lo"]=np.expm1(df["coef"]-1.96*df["se"])*100
    df["hi"]=np.expm1(df["coef"]+1.96*df["se"])*100

    groups=df["group"].drop_duplicates().tolist()
    fig,ax=plt.subplots(figsize=(8.0,4.6))
    color={"foreign_match":"#888888","own_match":"#1f6fb2"}
    lbl={"foreign_match":"Foreign-team match","own_match":"Own-team match"}
    yticks=[]; ylabels=[]
    y=0; gap=1.0; off=0.18
    for g in groups:
        for k,term in enumerate(["foreign_match","own_match"]):
            r=df[(df.group==g)&(df.term==term)].iloc[0]
            yy=y+(off if term=="own_match" else -off)
            ax.errorbar(r["pct"],yy,xerr=[[r["pct"]-r["lo"]],[r["hi"]-r["pct"]]],
                        fmt="o",ms=6,capsize=3,color=color[term],
                        label=lbl[term] if g==groups[0] else None)
        yticks.append(y); ylabels.append(g); y+=gap
    ax.axvline(0,color="k",lw=0.8,ls="--",alpha=0.6)
    ax.set_yticks(yticks); ax.set_yticklabels(ylabels)
    ax.set_ylim(-0.6,y-0.4); ax.invert_yaxis()
    ax.set_xlabel("Match effect on log-volume (% change vs. matched control), 95% CI")
    ax.set_title("Fig 3. Own-team vs foreign-team match effect on volume, by grouping")
    ax.legend(loc="lower right",frameon=False,fontsize=9)
    ax.grid(axis="x",alpha=0.25)
    fig.tight_layout()
    fig.savefig(os.path.join(FIG,"fig3_domestic.png"),dpi=150)
    plt.close(fig)
    print("wrote fig3_domestic.png")
    print(df[["group","term","pct","lo","hi"]].to_string(index=False))

# --------------------------------------------------------------------------------------
# FIG 6 : own_match (and match) lvol effect estimated PER TOURNAMENT (2010/2014/2018/2022)
# --------------------------------------------------------------------------------------
def combined_spine():
    a=pd.read_parquet(os.path.join(MDIR,"matches_all.parquet"))
    a=a[a["tournament"].isin([2018,2022])]
    h=pd.read_parquet(os.path.join(MDIR,"matches_hist.parquet"))
    cols=["tournament","kickoff_utc","played","usa_playing","euro_playing","gbp_playing","jpy_playing"]
    m=pd.concat([a[cols],h[cols]],ignore_index=True)
    m["ko"]=pd.to_datetime(m["kickoff_utc"],utc=True)
    return m[m["played"]==True].copy()

def build_panel():
    m=combined_spine()
    dur=104
    allm=set(); flags={f:set() for f in ["usa","euro","gbp","jpy"]}
    fmap={"usa":"usa_playing","euro":"euro_playing","gbp":"gbp_playing","jpy":"jpy_playing"}
    for _,r in m.iterrows():
        mins=pd.date_range(r["ko"], r["ko"]+pd.Timedelta(minutes=dur), freq="1min")
        allm.update(mins)
        for f,col in fmap.items():
            if r[col]: flags[f].update(mins)
    wins={}
    for t,g in m.groupby("tournament"):
        wins[t]=(g["ko"].min().normalize()-pd.Timedelta(days=21), g["ko"].max().normalize()+pd.Timedelta(days=22))
    parts=[]
    for inst,flag in OWN.items():
        p=os.path.join(FUT,f"{inst}_1m.parquet")
        if not os.path.exists(p): continue
        d=pd.read_parquet(p); d["ts"]=pd.to_datetime(d["ts"],utc=True).dt.floor("min")
        v=d["volume"].astype(float); d["lvol"]=np.log(v.where(v>0))
        keep=pd.Series(False,index=d.index); d["tournament"]=pd.NA
        for t,(a,b) in wins.items():
            mt=(d["ts"]>=a)&(d["ts"]<b); d.loc[mt,"tournament"]=t; keep|=mt
        d=d[keep].copy()
        if not len(d): continue
        d["match"]=d["ts"].isin(allm).astype(int)
        own_min=d["ts"].isin(flags[flag]).astype(int)
        d["own_match"]=(d["match"]*own_min).astype(int)
        d["foreign_match"]=(d["match"]*(1-own_min)).astype(int)
        d["weekday"]=d["ts"].dt.weekday; d["mod"]=d["ts"].dt.hour*60+d["ts"].dt.minute
        d["wd_mod"]=d["weekday"].astype(str)+"_"+d["mod"].astype(str)
        d["date"]=d["ts"].dt.strftime("%Y-%m-%d"); d["instrument"]=inst
        parts.append(d[["ts","instrument","tournament","lvol","match","own_match","foreign_match","wd_mod","date"]])
    return pd.concat(parts,ignore_index=True)

def fig6():
    panel=build_panel()
    res=[]
    for t in [2010,2014,2018,2022]:
        sub=panel[panel.tournament==t].dropna(subset=["lvol"])
        sub=sub[np.isfinite(sub["lvol"])]
        own_days=sub.loc[sub.own_match==1,"date"].nunique()
        try:
            mm=feols("lvol ~ foreign_match + own_match | instrument^wd_mod + date",
                     data=sub, vcov={"CRV1":"date"})
            tt=mm.tidy(); r=tt.loc["own_match"]
            res.append((t,r["Estimate"],r["Std. Error"],r["Pr(>|t|)"],own_days))
        except Exception as e:
            print(f"{t}: failed ({e})"); res.append((t,np.nan,np.nan,np.nan,own_days))
    df=pd.DataFrame(res,columns=["tournament","coef","se","p","own_days"])
    df["pct"]=np.expm1(df["coef"])*100
    df["lo"]=np.expm1(df["coef"]-1.96*df["se"])*100
    df["hi"]=np.expm1(df["coef"]+1.96*df["se"])*100
    # pooled reference (4-tournament) from own_team_4tourn.csv
    ot=pd.read_csv(os.path.join(OUT,"own_team_4tourn.csv"))
    pooled=ot[(ot.outcome=="lvol")&(ot.term=="own_match")].iloc[0]
    pooled_pct=np.expm1(pooled["coef"])*100

    fig,ax=plt.subplots(figsize=(7.6,4.4))
    x=np.arange(len(df))
    ax.axhline(0,color="k",lw=0.8,ls="--",alpha=0.6)
    ax.axhline(pooled_pct,color="#1f6fb2",lw=1.0,ls=":",alpha=0.8,
               label=f"4-tournament pooled ({pooled_pct:.1f}%)")
    ax.errorbar(x,df["pct"],yerr=[df["pct"]-df["lo"],df["hi"]-df["pct"]],
                fmt="o",ms=7,capsize=4,color="#1f6fb2")
    for i,r in df.iterrows():
        ax.annotate(f"n={int(r['own_days'])}d", (x[i],r["pct"]),
                    textcoords="offset points",xytext=(0,10),ha="center",fontsize=8,color="#555")
    ax.set_xticks(x); ax.set_xticklabels([str(t) for t in df["tournament"]])
    ax.set_xlabel("World Cup (own-team treated date-clusters annotated)")
    ax.set_ylabel("Own-team match effect on log-volume (%), 95% CI")
    ax.set_title("Fig 6. Own-team match effect on volume, by tournament\n(index/FX futures; 2026 ongoing, excluded)")
    ax.legend(loc="best",frameon=False,fontsize=9)
    ax.grid(axis="y",alpha=0.25)
    fig.tight_layout()
    fig.savefig(os.path.join(FIG,"fig6_by_tournament.png"),dpi=150)
    plt.close(fig)
    print("\nwrote fig6_by_tournament.png")
    print(df[["tournament","coef","se","p","pct","lo","hi","own_days"]].round(4).to_string(index=False))

if __name__=="__main__":
    fig3(); fig6()
