#!/usr/bin/env python3
"""Publication figures, vector PDF, Times-matching style. Reads analysis/out CSVs. Out: figures/*.pdf"""
import os, warnings; warnings.simplefilter("ignore")
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import rcParams
rcParams.update({"font.family":"serif","font.serif":["Nimbus Roman","Times New Roman","DejaVu Serif"],
                 "font.size":9,"axes.linewidth":0.6,"axes.edgecolor":"#222","figure.dpi":150,
                 "axes.grid":False,"legend.frameon":False})
R=os.path.join(os.path.dirname(os.path.abspath(__file__)),"..")
O=os.path.join(R,"analysis","out"); F=os.path.join(R,"figures"); os.makedirs(F,exist_ok=True)
def csv(n): return pd.read_csv(os.path.join(O,n))
NAVY="#1f3b73"; RED="#b22222"; GREY="#888"

# ---- Fig 1: during-match volume by market, vs the literature's 30-50% decline band ----
eb=csv("equivalence_bounds.csv"); eb=eb[eb.outcome=="lvol"]
lab={"ALL":"All markets (pooled)","crypto_spot":"Crypto spot","crypto_perp":"Crypto perp",
     "equity_fut":"Equity-index futures","commodity_fut":"Commodity futures","fx_fut":"FX futures"}
eb=eb[eb.group.isin(lab)].copy(); eb["lab"]=eb.group.map(lab)
order=["All markets (pooled)","Crypto spot","Crypto perp","Equity-index futures","Commodity futures","FX futures"]
eb=eb.set_index("lab").loc[order].reset_index()
fig,ax=plt.subplots(figsize=(6.4,3.2)); y=np.arange(len(eb))[::-1]
ax.axvspan(-50,-30,color=RED,alpha=0.12,lw=0); ax.text(-40,len(eb)-0.3,"prior literature\n(−30 to −50%)",color=RED,ha="center",va="top",fontsize=7.5)
ax.axvline(0,color="#444",lw=0.8,zorder=1)
ax.errorbar(eb.pct_point,y,xerr=[eb.pct_point-eb.pct_lo,eb.pct_hi-eb.pct_point],fmt="o",color=NAVY,
            ecolor=NAVY,elinewidth=1.1,capsize=2.5,ms=4,zorder=3)
ax.set_yticks(y); ax.set_yticklabels(eb.lab,fontsize=8.5); ax.set_xlim(-55,20)
ax.set_xlabel("during-match change in trading volume (%), 95% CI"); ax.set_ylabel("")
for sp in ("top","right"): ax.spines[sp].set_visible(False)
fig.tight_layout(); fig.savefig(os.path.join(F,"fig_bymarket.pdf")); plt.close(fig)

# ---- Fig 2: event study around kickoff (nothing happens) ----
k=csv("kickoff_curve.csv"); k=k[(k.rel>=-90)&(k.rel<=150)]
fig,ax=plt.subplots(figsize=(6.4,2.8))
ax.axvspan(0,105,color=NAVY,alpha=0.07,lw=0); ax.text(52,0.0,"match in progress",color=NAVY,ha="center",fontsize=7.5)
ax.axhline(0,color="#444",lw=0.7)
m=100*(np.exp(k.lvol_mean)-1); s=100*k.lvol_se
ax.plot(k.rel,m,color=NAVY,lw=1.1); ax.fill_between(k.rel,m-1.96*s,m+1.96*s,color=NAVY,alpha=0.15,lw=0)
ax.axvline(0,color=GREY,lw=0.6,ls="--"); ax.set_xlabel("minutes relative to kickoff")
ax.set_ylabel("volume vs.\nsame-minute baseline (%)"); ax.set_xlim(-90,150)
for sp in ("top","right"): ax.spines[sp].set_visible(False)
fig.tight_layout(); fig.savefig(os.path.join(F,"fig_kickoff.pdf")); plt.close(fig)

# ---- Fig 3: attention is real, markets are not ----
w=csv("wiki_validation.csv")
fig,(a1,a2)=plt.subplots(1,2,figsize=(6.4,2.7),gridspec_kw={"width_ratios":[1,1]})
a1.bar([0,1],w.ratio,color=NAVY,width=0.6); a1.axhline(1,color=GREY,lw=0.7,ls="--")
a1.set_xticks([0,1]); a1.set_xticklabels(["2018","2022"]); a1.set_ylabel("Wikipedia views,\n×off-tournament baseline")
for i,r in enumerate(w.ratio): a1.text(i,r+0.15,f"{r:.1f}×",ha="center",fontsize=8.5)
a1.set_title("Attention spikes",fontsize=9); a1.set_ylim(0,9.2)
for sp in ("top","right"): a1.spines[sp].set_visible(False)
bm=csv("equivalence_bounds.csv"); bm=bm[(bm.outcome=="lvol")&(bm.group.isin(["crypto_spot","equity_fut","commodity_fut","fx_fut"]))]
names=["Crypto","Equity\nfut.","Commod.\nfut.","FX\nfut."]
a2.axhline(0,color="#444",lw=0.7)
a2.bar(range(len(bm)),bm.pct_point,yerr=[bm.pct_point-bm.pct_lo,bm.pct_hi-bm.pct_point],
       color="#9aa7bd",ecolor=NAVY,capsize=2.5,width=0.6)
a2.set_xticks(range(len(bm))); a2.set_xticklabels(names,fontsize=8); a2.set_ylabel("during-match volume (%)")
a2.set_title("Markets do not",fontsize=9); a2.set_ylim(-20,20)
for sp in ("top","right"): a2.spines[sp].set_visible(False)
fig.tight_layout(); fig.savefig(os.path.join(F,"fig_attention.pdf")); plt.close(fig)

# ---- Fig 4: comovement composition artifact + Monte Carlo ----
cm=csv("comovement.csv"); mc=csv("artifact_mc.csv")
fig,(a1,a2)=plt.subplots(1,2,figsize=(6.4,2.8))
specs={"all_avail (raw - composition-confounded)":"Naive\n(raw)","all_avail +ninst control":"Composition-\ncontrolled","crypto_only (composition-free)":"Constant-\ninstrument set"}
cc=cm[cm.spec.isin(specs)].copy(); cc["lab"]=cc.spec.map(specs); cc=cc.set_index("lab").loc[list(specs.values())].reset_index()
cols=[RED if p<0.05 else NAVY for p in cc.p]
a1.axhline(0,color="#444",lw=0.7)
a1.bar(range(len(cc)),cc.coef,yerr=1.96*cc.se,color=cols,ecolor="#444",capsize=2.5,width=0.6)
a1.set_xticks(range(len(cc))); a1.set_xticklabels(cc.lab,fontsize=7.8); a1.set_ylabel("match−control comovement")
for i,(c,p) in enumerate(zip(cc.coef,cc.p)): a1.text(i,c+(0.004 if c>=0 else -0.012),("p=%.3f"%p),ha="center",fontsize=7,color=cols[i])
a1.set_title("The 'comovement decline' is composition",fontsize=8.6)
for sp in ("top","right"): a1.spines[sp].set_visible(False)
a2.bar([0,1],mc.pct_sig_5,color=[RED,NAVY],width=0.6); a2.axhline(5,color=GREY,lw=0.7,ls="--")
a2.set_xlim(-0.6,2.05)
a2.text(1.42,5,"5% nominal",color=GREY,fontsize=7,ha="left",va="center")
a2.set_xticks([0,1]); a2.set_xticklabels(["naive\nmeasure","with\ncontrol"],fontsize=8)
a2.set_ylabel("false-positive rate (%)\n400 no-effect simulations"); a2.set_ylim(0,108)
for i,v in enumerate(mc.pct_sig_5): a2.text(i,v+2,f"{v:.0f}%",ha="center",fontsize=8.5)
a2.set_title("Monte Carlo: zero true effect",fontsize=8.6)
for sp in ("top","right"): a2.spines[sp].set_visible(False)
fig.tight_layout(); fig.savefig(os.path.join(F,"fig_comovement.pdf")); plt.close(fig)

# ---- Fig 5: home-market forest plot ----
rows=[]
hd=csv("home_equities_distraction.csv"); r=hd[(hd.kind=="equity")&(hd.outcome=="log volume")].iloc[0]
rows.append(("Home-equity volume (26 nations)",r.pct,r.pct-1.96*r.se*100,r.pct+1.96*r.se*100,"%"))
el=csv("eq_extended_loser.csv"); r=el[(el.spec=="pooled all (20 idx)")&(el.term=="postL")].iloc[0]
rows.append(("Loser effect, 20 stock indices",r.bps,r.bps-1.96*r.se_bps,r.bps+1.96*r.se_bps,"bp"))
fl=csv("fx_extended_loser.csv"); r=fl[(fl.spec=="pooled all (16 ccy)")&(fl.term=="postL")].iloc[0]
rows.append(("Loser effect, 16 currencies",r.bps,r.bps-1.96*r.se_bps,r.bps+1.96*r.se_bps,"bp"))
sz=csv("home_equities_size.csv"); r=sz[sz.term=="own_emerg"].iloc[0]
rows.append(("Small-country tilt (volume)",r.pct,r.pct-1.96*r.se*100,r.pct+1.96*r.se*100,"%"))
fig,ax=plt.subplots(figsize=(6.4,2.6)); y=np.arange(len(rows))[::-1]
ax.axvline(0,color="#444",lw=0.8)
for i,(lab,pt,lo,hi,unit) in enumerate(rows):
    yy=y[i]; ax.errorbar(pt,yy,xerr=[[pt-lo],[hi-pt]],fmt="o",color=NAVY,ecolor=NAVY,capsize=2.5,ms=4)
    ax.text(hi+ (1 if unit=="%" else 4),yy,f"{pt:.1f}{'%' if unit=='%' else ' bp'}",va="center",fontsize=7.5,color="#333")
ax.set_yticks(y); ax.set_yticklabels([r[0] for r in rows],fontsize=8.5)
ax.set_xlabel("home-market effect (volume in %, loser effect in bp), 95% CI")
for sp in ("top","right"): ax.spines[sp].set_visible(False)
fig.tight_layout(); fig.savefig(os.path.join(F,"fig_homemarket.pdf")); plt.close(fig)

# ---- Fig 6: positive control — the design recovers a real effect ----
ip=csv("injection_power.csv")
xeff=[0,-10,-30,-45]
def prow(r): return [r["power_0% (size)"],r["power_-10%"],r["power_-30%"],r["power_-45%"]]
fig,ax=plt.subplots(figsize=(6.4,3.1))
ax.axvspan(-50,-30,color=RED,alpha=0.08,lw=0)
ax.text(-40,0.40,"prior literature\n(−30 to −50%)",color=RED,ha="center",fontsize=7)
ax.axhline(0.8,color=GREY,lw=0.7,ls=":"); ax.text(-1.5,0.825,"80% power",color=GREY,fontsize=7,ha="right")
ax.axhline(0.05,color=GREY,lw=0.7,ls="--"); ax.text(-1.5,0.085,"5% size",color=GREY,fontsize=7,ha="right")
sel=[("Crypto spot (Match)","Crypto spot",NAVY),
     ("Equity-index futures (Match)","Equity-index futures","#2e7d4f"),
     ("FX futures (Match)","FX futures","#b8860b"),
     ("Own-team futures, pooled","Own-team futures, pooled","#6a4c93")]
for name,lg,col in sel:
    r=ip[ip.cell==name].iloc[0]; ax.plot(xeff,prow(r),"-o",color=col,ms=4,lw=1.3,label=lg)
r=ip[ip.cell=="Sterling 6B, England own"].iloc[0]
ax.plot(xeff,prow(r),"--s",color=RED,ms=4,lw=1.1,label="Sterling, England (6 clusters)")
ax.set_xlabel("injected during-match volume effect (%)"); ax.set_ylabel("rejection rate")
ax.set_xticks(xeff); ax.set_ylim(-0.02,1.06); ax.set_xlim(-49,2.5)
ax.legend(fontsize=6.8,loc="center right")
for sp in ("top","right"): ax.spines[sp].set_visible(False)
fig.tight_layout(); fig.savefig(os.path.join(F,"fig_power.pdf")); plt.close(fig)

# ---- Fig 7: attention is real at the hour of play (per-match kickoff-hour spike) ----
from matplotlib.patches import Patch
am=csv("attention_hourly_matches.csv").copy()
am["short"]=am["match"].str.extract(r"\((.*?)\)")[0]
x=np.arange(len(am)); cols=[NAVY if "2018" in m else RED for m in am.match]
fig,ax=plt.subplots(figsize=(6.4,3.0))
ax.axhline(1,color=GREY,lw=0.7,ls="--"); ax.text(len(am)-0.5,1.12,"no change",color=GREY,fontsize=7,ha="right")
ax.bar(x,am.team_mean_spike,color=cols,width=0.62)
for i,v in enumerate(am.team_mean_spike): ax.text(i,v+0.08,f"{v:.1f}×",ha="center",fontsize=7.2)
ax.set_xticks(x); ax.set_xticklabels(am.short,rotation=40,ha="right",fontsize=7)
ax.set_ylabel("team-article pageviews,\nkickoff hour ÷ 3 h earlier"); ax.set_ylim(0,6.4)
ax.legend(handles=[Patch(color=NAVY,label="2018"),Patch(color=RED,label="2022")],fontsize=7.5,loc="upper left")
for sp in ("top","right"): ax.spines[sp].set_visible(False)
fig.tight_layout(); fig.savefig(os.path.join(F,"fig_attention_intraday.pdf")); plt.close(fig)

print("wrote:", sorted(os.listdir(F)))
