#!/usr/bin/env python3
"""
Intraday (hourly) attention validation from the free Wikimedia hourly pageview dumps. For a sample of
matches, pull national-team article views in event time around kickoff (kickoff-2h .. kickoff+2h) and show
the during-match spike, validating that attention surges AT the match hour, not just on the match day.
Streams each ~50MB hourly .gz, greps the relevant articles, deletes it (disk-bounded).
Out: analysis/out/attention_hourly.csv + figures/fig_attention_hourly.pdf
"""
import os, gzip, io, urllib.request, warnings; warnings.simplefilter("ignore")
import numpy as np, pandas as pd
R=os.path.join(os.path.dirname(os.path.abspath(__file__)),"..")
M=os.path.join(R,"data","matches"); O=os.path.join(R,"analysis","out"); FIG=os.path.join(R,"figures")
ART={"Brazil":"Brazil","Argentina":"Argentina","France":"France","England":"England","Germany":"Germany",
 "Spain":"Spain","Portugal":"Portugal","Netherlands":"Netherlands","Belgium":"Belgium","Croatia":"Croatia",
 "Italy":"Italy","Mexico":"Mexico","Uruguay":"Uruguay","Switzerland":"Switzerland","Poland":"Poland",
 "Japan":"Japan","Morocco":"Morocco","Senegal":"Senegal","Denmark":"Denmark","Sweden":"Sweden",
 "Colombia":"Colombia","Russia":"Russia"}
def art(team): return f"{ART[team].replace(' ','_')}_national_football_team"
WC={2018:"2018_FIFA_World_Cup",2022:"2022_FIFA_World_Cup"}

def spine():
    a=pd.read_parquet(os.path.join(M,"matches_all.parquet")); a=a[a.tournament.isin([2018,2022])]
    a=a[a.played==True].copy(); a["ko"]=pd.to_datetime(a["kickoff_utc"],utc=True)
    a=a[a.home.isin(ART)&a.away.isin(ART)]
    # sample ~6 per tournament spread across the window
    out=[]
    for t in (2018,2022):
        s=a[a.tournament==t].sort_values("ko")
        idx=np.linspace(0,len(s)-1,6).astype(int)
        out.append(s.iloc[idx])
    return pd.concat(out)

def hour_views(dt, titles):
    """download the hourly dump for UTC datetime dt, return {title: views} for requested en titles."""
    url=f"https://dumps.wikimedia.org/other/pageviews/{dt:%Y}/{dt:%Y-%m}/pageviews-{dt:%Y%m%d}-{dt:%H}0000.gz"
    want=set(titles); got={t:0 for t in titles}
    try:
        req=urllib.request.Request(url,headers={"User-Agent":"wc-research/1.0"})
        with urllib.request.urlopen(req,timeout=120) as resp:
            with gzip.GzipFile(fileobj=io.BytesIO(resp.read())) as gz:
                for line in io.TextIOWrapper(gz,encoding="utf-8",errors="ignore"):
                    p=line.split(" ")
                    if len(p)>=3 and p[0]=="en" and p[1] in want:
                        got[p[1]]=int(p[2])
    except Exception as e:
        print(f"  miss {url.split('/')[-1]}: {type(e).__name__}")
        return None
    return got

def main():
    m=spine(); rows=[]
    print(f"sampling {len(m)} matches, kickoff-2h..+2h hourly...")
    for _,r in m.iterrows():
        ko=r.ko.floor("h"); titles=[art(r.home),art(r.away),WC[r.tournament]]
        for off in (-2,-1,0,1,2):
            dt=ko+pd.Timedelta(hours=int(off)); g=hour_views(dt,titles)
            if g is None: continue
            team_views=g[art(r.home)]+g[art(r.away)]
            rows.append(dict(match=f"{r.home}-{r.away}",tournament=r.tournament,offset=off,
                             team_views=team_views,wc_views=g[WC[r.tournament]]))
        print(f"  done {r.home}-{r.away}")
    d=pd.DataFrame(rows); d.to_csv(os.path.join(O,"attention_hourly.csv"),index=False)
    # event-time profile: normalize each match's team_views to its own kickoff-2h baseline
    base=d[d.offset==-2].set_index("match").team_views
    d["norm"]=d.apply(lambda x: x.team_views/base.get(x.match,np.nan),axis=1)
    prof=d.groupby("offset").norm.agg(["mean","sem"])
    print("\nEvent-time team-article views (x kickoff-2h baseline):")
    print(prof.to_string())
    spike=prof.loc[0,"mean"]; print(f"\nKICKOFF-HOUR SPIKE: {spike:.1f}x the 2h-pre baseline (pooled, {d.match.nunique()} matches)")
    # figure
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    from matplotlib import rcParams; rcParams.update({"font.family":"serif","font.size":9})
    fig,ax=plt.subplots(figsize=(6.4,2.8)); x=prof.index
    ax.axvspan(0,1.75,color="#1f3b73",alpha=0.08,lw=0); ax.text(0.85,prof["mean"].max()*0.95,"match in progress",color="#1f3b73",ha="center",fontsize=7.5)
    ax.errorbar(x,prof["mean"],yerr=prof["sem"],fmt="o-",color="#1f3b73",capsize=2.5,lw=1.2,ms=4)
    ax.axhline(1,color="#888",lw=0.7,ls="--"); ax.set_xlabel("hours relative to kickoff")
    ax.set_ylabel("national-team article views\n(× kickoff−2h baseline)"); ax.set_xticks([-2,-1,0,1,2])
    for sp in ("top","right"): ax.spines[sp].set_visible(False)
    fig.tight_layout(); fig.savefig(os.path.join(FIG,"fig_attention_hourly.pdf")); plt.close(fig)
    print("wrote fig_attention_hourly.pdf")
if __name__=="__main__":
    main()
