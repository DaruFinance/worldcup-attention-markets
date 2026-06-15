import os, numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
from scipy.stats import norm
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__))) if False else os.path.join(os.path.dirname(os.path.abspath(__file__)),"..")
O=os.path.join(ROOT,"analysis","out"); F=os.path.join(ROOT,"analysis","figures"); os.makedirs(F,exist_ok=True)
# Fig 7  -  breadth forest
b=pd.read_csv(os.path.join(O,"breadth.csv"))
z=norm.ppf(1-b["p"].clip(1e-6,0.999)/2).clip(min=1e-6); b["se"]=b["coef"].abs().values/z
b=b.sort_values(["asset_class","instrument"]).reset_index(drop=True)
fig,ax=plt.subplots(figsize=(7,9)); y=np.arange(len(b))
cols={c:p for c,p in zip(sorted(b.asset_class.unique()), plt.cm.tab10.colors)}
ax.axvspan(-10,10,color="#eee"); ax.axvline(0,color="#c0392b",ls="--",lw=.9)
ax.errorbar(b.pct, y, xerr=1.96*np.expm1(b.se)*100, fmt="o", ms=4, lw=1,
            ecolor="#999", mfc="#1f4e79", mec="#1f4e79")
ax.set_yticks(y); ax.set_yticklabels([f"{r.instrument} ({r.asset_class})" for r in b.itertuples()], fontsize=8)
ax.set_xlabel("during-match volume effect (%)"); ax.set_xlim(-30,30)
ax.set_title("Figure 7. During-match volume effect by instrument\n29 instruments, 7 asset classes (2010-2022); grey band = ±10%")
fig.tight_layout(); fig.savefig(os.path.join(F,"fig7_breadth.png"),dpi=130); plt.close(fig); print("fig7")
# Fig 8  -  equivalence margins vs literature
e=pd.read_csv(os.path.join(O,"equivalence_tost.csv"))
e=e[~e.estimate.str.contains("spread|depth")==False] if False else e
e=e.sort_values("equiv_margin_pct")
fig,ax=plt.subplots(figsize=(8,5)); y=np.arange(len(e))
ax.barh(y, e.equiv_margin_pct, color="#1f4e79", alpha=.8)
ax.axvspan(30,50,color="#c0392b",alpha=.15); ax.axvline(30,color="#c0392b",ls="--",lw=1)
ax.text(40,len(e)-0.5,"national cash-equity\nliterature (30-50%)",color="#c0392b",fontsize=8,ha="center",va="top")
ax.set_yticks(y); ax.set_yticklabels(e.estimate, fontsize=8)
ax.set_xlabel("equivalence margin  -  largest effect ruled out at 5% (%)")
ax.set_title("Figure 8. Effects formally ruled out (TOST) vs the literature's reported declines")
fig.tight_layout(); fig.savefig(os.path.join(F,"fig8_equivalence.png"),dpi=130); plt.close(fig); print("fig8")
