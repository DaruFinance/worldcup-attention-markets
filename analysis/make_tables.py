#!/usr/bin/env python3
"""Assemble formatted markdown tables for the paper from analysis/out/*.csv + spine."""
import os
import numpy as np, pandas as pd

ROOT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"..")
OUT=os.path.join(ROOT,"analysis","out"); MDIR=os.path.join(ROOT,"data","matches")
PAPER=os.path.join(ROOT,"analysis","out"); os.makedirs(PAPER,exist_ok=True)
def rd(f):
    p=os.path.join(OUT,f); return pd.read_csv(p) if os.path.exists(p) else None
def stars(p):
    return "***" if p<.01 else "**" if p<.05 else "*" if p<.10 else ""

def t1_sample():
    m=pd.read_parquet(os.path.join(MDIR,"matches_all.parquet"))
    g=pd.read_parquet(os.path.join(MDIR,"goals_all.parquet")) if os.path.exists(os.path.join(MDIR,"goals_all.parquet")) else None
    rows=[]
    for t,gg in m.groupby("tournament"):
        rows.append(dict(tournament=int(t), matches=len(gg), played=int(gg["played"].sum()),
            knockout=int(gg["knockout"].sum()), usa=int(gg["usa_playing"].sum()),
            euro=int(gg["euro_playing"].sum()), gbp=int(gg["gbp_playing"].sum()),
            jpy=int(gg["jpy_playing"].sum()),
            goals=(int((g.tournament==t).sum()) if g is not None else None)))
    return pd.DataFrame(rows)

def fmt(df, val="coef", se="se", p="p", idx=None, cols=None):
    if df is None or not len(df): return "_(pending)_\n"
    return df.round(4).to_markdown(index=False)

def main():
    lines=["# Tables  -  When the World Watches Football\n"]
    lines.append("## Table 1. Sample description\n")
    lines.append(t1_sample().to_markdown(index=False)+"\n")

    xm=rd("xm_main.csv")
    if xm is not None:
        lines.append("\n## Table 3/5. Cross-market during-match effect (2018+2022)\n")
        prim=xm[xm["outcome"].isin(["lvol","ltrades","absret","hlrange"])].copy()
        prim["effect"]=prim.apply(lambda r:f"{r['coef']:+.4f}{stars(r['p'])}",axis=1)
        piv=prim.pivot_table(index="group",columns="outcome",values="effect",aggfunc="first")
        piv=piv.reindex([g for g in ["ALL","crypto_spot","crypto_perp","equity_fut","commodity_fut","fx_fut"] if g in piv.index])
        lines.append(piv.to_markdown()+"\n")
        lines.append("\n_log-point coef on Match; ***/**/* = p<.01/.05/.10; SE clustered by date; "
                     "instrument×weekday×minute-of-day + date FE._\n")

    dd=rd("xm_domestic.csv")
    if dd is not None and len(dd):
        lines.append("\n## Table 4. Domestic-team heterogeneity\n")
        dd=dd.copy(); dd["effect"]=dd.apply(lambda r:f"{r['coef']:+.4f}{stars(r['p'])}",axis=1)
        lines.append(dd.pivot_table(index=["instrument","term"],columns="outcome",values="effect",aggfunc="first").to_markdown()+"\n")

    kk=rd("xm_knockout.csv")
    if kk is not None and len(kk):
        lines.append("\n## Table 4b. Knockout heterogeneity\n")
        kk=kk.copy(); kk["effect"]=kk.apply(lambda r:f"{r['coef']:+.4f}{stars(r['p'])}",axis=1)
        lines.append(kk.pivot_table(index=["group","term"],columns="outcome",values="effect",aggfunc="first").to_markdown()+"\n")

    pb=rd("reg_placebo.csv")
    if pb is not None:
        lines.append("\n## Table 7. Placebo (crypto; shifted match windows  -  should be ~0)\n")
        lines.append(pb[["term","coef","se","p"]].round(4).to_markdown(index=False)+"\n")

    gl=rd("reg_goal.csv")
    if gl is not None:
        lines.append("\n## Goal-window effects (crypto)\n")
        lines.append(gl[["outcome","window","coef","se","p"]].round(4).to_markdown(index=False)+"\n")

    oo=rd("xm_2026_oos.csv")
    if oo is not None and len(oo):
        lines.append("\n## 2026 live out-of-sample (partial)\n")
        lines.append(oo[["group","outcome","coef","se","p"]].round(4).to_markdown(index=False)+"\n")

    open(os.path.join(PAPER,"tables.md"),"w").write("\n".join(lines))
    print("wrote", os.path.join(PAPER,"tables.md"))

if __name__=="__main__":
    main()
