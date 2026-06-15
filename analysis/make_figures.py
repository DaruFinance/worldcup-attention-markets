#!/usr/bin/env python3
"""Figure 2 (cross-market coefficient plot) + Figure 4 (knockout) from regression CSVs."""
import os
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"..")
OUT=os.path.join(ROOT,"analysis","out"); FIG=os.path.join(ROOT,"analysis","figures")
os.makedirs(FIG,exist_ok=True)
GLAB={"crypto_spot":"Crypto spot","crypto_perp":"Crypto perp","equity_fut":"Equity futures",
      "commodity_fut":"Commodity futures","fx_fut":"FX futures"}

def fig2():
    p=os.path.join(OUT,"xm_main.csv")
    if not os.path.exists(p): return
    d=pd.read_csv(p); d=d[d["group"]!="ALL"]
    outs=["lvol","ltrades","absret","hlrange"]; titles=["log $ volume","log trade count","|return|","high-low range"]
    fig,axes=plt.subplots(1,4,figsize=(16,4.2),sharey=True)
    order=[g for g in GLAB if g in d["group"].unique()]
    for ax,y,tt in zip(axes,outs,titles):
        sub=d[d["outcome"]==y].set_index("group").reindex(order)
        yv=np.arange(len(order))
        ax.errorbar(sub["coef"],yv,xerr=1.96*sub["se"],fmt="o",color="#1f4e79",capsize=3)
        ax.axvline(0,color="#c0392b",ls="--",lw=.9)
        ax.set_yticks(yv); ax.set_yticklabels([GLAB[g] for g in order]); ax.set_title(tt)
        ax.set_xlabel("Match coef (log pts)")
    fig.suptitle("Figure 2. During-match effect by market structure (2018+2022, 95% CI, date-clustered)")
    fig.tight_layout(); fig.savefig(os.path.join(FIG,"fig2_bymarket.png"),dpi=130); plt.close(fig)
    print("wrote fig2")

def fig4():
    p=os.path.join(OUT,"xm_knockout.csv")
    if not os.path.exists(p): return
    d=pd.read_csv(p)
    if not len(d): return
    sub=d[d["outcome"]=="lvol"]
    if not len(sub): return
    fig,ax=plt.subplots(figsize=(7,4))
    grp=sub.pivot_table(index="group",columns="term",values="coef",aggfunc="first")
    grp.plot(kind="barh",ax=ax)
    ax.axvline(0,color="#333",lw=.8); ax.set_xlabel("log $ volume coef")
    ax.set_title("Figure 4. Match vs knockout-extra effect on volume by market")
    fig.tight_layout(); fig.savefig(os.path.join(FIG,"fig4_knockout.png"),dpi=130); plt.close(fig)
    print("wrote fig4")

if __name__=="__main__":
    fig2(); fig4()
