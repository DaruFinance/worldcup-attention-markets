#!/usr/bin/env python3
"""
PRICE-EFFICIENCY measures during World Cup match windows vs matched controls.

Block design (mirrors analysis/comovement.py): each PLAYED match -> a block
[kickoff, +105min]. Controls = same-(weekday x clock) blocks on NON-MATCH days inside
the same tournament window, that do not overlap any match. Match (treated) vs control
blocks are compared with a block-level regression  Y ~ match | wd_clk , SE clustered by
date (date FE is collinear with `match` here because controls live on different days, so
identification is within weekday x clock slot, clustered by date -- same as comovement.py).

Completed tournaments only:
  - variance ratio / abnormal returns / equity-arm basis & lead-lag: 2010, 2014, 2018, 2022
    (SPY/ES cover all four).
  - crypto spot-perp basis & crypto lead-lag: perp data starts 2022-10 -> 2022 ONLY.
    spot covers 2018+2022 but a basis needs both legs, so crypto basis is 2022-only.
  - crypto variance-ratio / abnormal: 2018 + 2022 (spot+perp both, but 2018 perp absent ->
    crypto VR/abret uses spot legs for 2018, both for 2022; we tag the universe per row).

NO LOOK-AHEAD: 1-min log returns are computed on the FULL per-instrument series first, then
restricted to blocks. Variance ratio / cross-correlation / basis use only data inside the
block (a block is self-contained; nothing peeks past +105min).

Measures
  1. Variance ratio (Lo-MacKinlay) VR(q)=Var(q-min ret)/(q*Var(1-min ret)), q=5, per
     instrument per block; VR!=1 => autocorrelation => inefficiency. Test match vs control.
  2. Spot-futures basis: SPY (cash) vs ES (futures) return-spread on common RTH minutes;
     test whether basis dispersion (sd of per-minute return diff in a block) changes during
     matches. Crypto spot-perp basis = log(perp/spot): test block-mean LEVEL and block-SD.
  3. Lead-lag: cross-correlation of 1-min returns between futures(ES)&spot(SPY) and crypto
     perp&spot at leads/lags +-5min; lead-lag ratio = max corr at futures-leads vs spot-leads.
     Does discovery shift toward futures during matches?
  4. Abnormal/cumulative returns: market-adjusted return = inst ret - cross-inst mean ret that
     minute; cumulate over the block; |CAR| compared match vs control.

Out: analysis/out/efficiency.csv   (+ handoffs/efficiency.md paragraph)
"""
import os, sys, warnings
warnings.simplefilter("ignore")
os.environ.setdefault("OPENBLAS_NUM_THREADS","1"); os.environ.setdefault("OMP_NUM_THREADS","1")
import numpy as np, pandas as pd
from pyfixest.estimation import feols

ROOT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"..")
FUT=os.path.join(ROOT,"data","market","futures")
EQ=os.path.join(ROOT,"data","market","equity")
CSP=os.path.join(ROOT,"data","market","crypto","spot")
CPP=os.path.join(ROOT,"data","market","crypto","perp")
MDIR=os.path.join(ROOT,"data","matches")
OUT=os.path.join(ROOT,"analysis","out"); os.makedirs(OUT,exist_ok=True)
DUR=pd.Timedelta(minutes=105)
Q=5                              # variance-ratio horizon
LAG=5                            # lead-lag window (minutes)

# ---------- matches / windows -------------------------------------------------
def load_matches():
    ma=pd.read_parquet(os.path.join(MDIR,"matches_all.parquet"))
    ma=ma[ma["tournament"].isin([2018,2022])]
    mh=pd.read_parquet(os.path.join(MDIR,"matches_hist.parquet"))      # 2010, 2014
    cols=["tournament","kickoff_utc","played"]
    m=pd.concat([ma[cols],mh[cols]],ignore_index=True)
    m=m[m["played"]].copy()
    m["ko"]=pd.to_datetime(m["kickoff_utc"],utc=True)
    return m

def tournament_windows(m):
    w={}
    for t,g in m.groupby("tournament"):
        ko=g["ko"]
        w[t]=(ko.min().normalize()-pd.Timedelta(days=21), ko.max().normalize()+pd.Timedelta(days=22))
    return w

# ---------- instrument series (returns on FULL series, then restrict) ---------
def log_ret_series(path, win_lo, win_hi):
    d=pd.read_parquet(path, columns=["ts","close"])
    d["ts"]=pd.to_datetime(d["ts"],utc=True)
    d=d.sort_values("ts").drop_duplicates("ts")
    d["ret"]=np.log(d["close"].astype(float)/d["close"].astype(float).shift(1))   # FULL series first
    d=d[(d["ts"]>=win_lo)&(d["ts"]<win_hi)]
    return d.set_index("ts")

def level_series(path, win_lo, win_hi):
    d=pd.read_parquet(path, columns=["ts","close"])
    d["ts"]=pd.to_datetime(d["ts"],utc=True); d=d.sort_values("ts").drop_duplicates("ts")
    d=d[(d["ts"]>=win_lo)&(d["ts"]<win_hi)]
    return d.set_index("ts")["close"].astype(float)

# ---------- block-list construction (treated + matched controls) -------------
def block_list(m, tourns):
    """Return list of (tournament, start_ts, is_match, weekday, clock, date) blocks."""
    blocks=[]
    wins=tournament_windows(m)
    for t in tourns:
        mt=m[m["tournament"]==t]
        if not len(mt): continue
        kos=mt["ko"].tolist()
        match_dates={k.strftime("%Y-%m-%d") for k in kos}
        slots=sorted({(k.weekday(),k.hour*60+k.minute) for k in kos})
        def overlaps(s,e): return any((s<k+DUR) and (e>k) for k in kos)
        # treated
        for k in kos:
            blocks.append((t,k,1,k.weekday(),k.hour*60+k.minute,k.strftime("%Y-%m-%d")))
        # controls
        lo,hi=wins[t]; d=lo
        while d<=hi:
            ds=d.strftime("%Y-%m-%d")
            if ds not in match_dates:
                for (wd,clk) in slots:
                    if d.weekday()!=wd: continue
                    s=d+pd.Timedelta(minutes=int(clk)); e=s+DUR
                    if overlaps(s,e): continue
                    blocks.append((t,s,0,wd,int(clk),ds))
            d+=pd.Timedelta(days=1)
    return blocks

# ---------- regression helper -------------------------------------------------
def fit_match(df, y):
    """Y ~ match | wd_clk, cluster date. Returns (coef, se, p, n)."""
    df=df.dropna(subset=[y,"match","wd_clk","date"])
    if df["match"].nunique()<2 or len(df)<10:
        return (np.nan,np.nan,np.nan,len(df))
    try:
        mod=feols(f"{y} ~ match | wd_clk", data=df, vcov={"CRV1":"date"})
        r=mod.tidy().loc["match"]
        return (r["Estimate"],r["Std. Error"],r["Pr(>|t|)"],len(df))
    except Exception as e:
        return (np.nan,np.nan,np.nan,len(df))

def summ(df, y, label, units=""):
    c,s,p,n=fit_match(df,y)
    mt=df.loc[df.match==1,y]; ct=df.loc[df.match==0,y]
    ci_lo=c-1.96*s if np.isfinite(s) else np.nan; ci_hi=c+1.96*s if np.isfinite(s) else np.nan
    return dict(measure=label, units=units,
                match_blocks=int((df.match==1).sum()), ctrl_blocks=int((df.match==0).sum()),
                mean_match=round(mt.mean(),6) if len(mt) else np.nan,
                mean_ctrl=round(ct.mean(),6) if len(ct) else np.nan,
                coef=round(c,6), se=round(s,6),
                ci_lo=round(ci_lo,6), ci_hi=round(ci_hi,6),
                p=round(p,4), n_blocks=n)

# ---------- per-measure block computations -----------------------------------
def variance_ratio(ret, q=Q):
    r=ret.dropna().values
    if len(r)<2*q+5: return np.nan
    v1=np.var(r,ddof=1)
    if v1<=0: return np.nan
    rq=np.add.reduceat(r, np.arange(0,len(r)-len(r)%q,q)) if False else None
    # non-overlapping q-sums:
    nq=(len(r)//q)*q
    rq=r[:nq].reshape(-1,q).sum(axis=1)
    if len(rq)<3: return np.nan
    vq=np.var(rq,ddof=1)
    return vq/(q*v1)

def block_window(idx_series, s, e):
    return idx_series.loc[(idx_series.index>=s)&(idx_series.index<e)]

def lead_lag_ratio(rfut, rspot, maxlag=LAG):
    """+ => price discovery in FUTURES leads (fut return predicts future spot return).
       ratio = mean|corr(fut leads)| - mean|corr(spot leads)| ; also peak-lag (argmax abs)."""
    a=pd.concat([rfut.rename("f"),rspot.rename("s")],axis=1).dropna()
    if len(a)<30: return np.nan,np.nan
    f=a["f"].values; sp=a["s"].values
    f=(f-f.mean()); sp=(sp-sp.mean())
    sf=f.std(); ss=sp.std()
    if sf<=0 or ss<=0: return np.nan,np.nan
    f/=sf; sp/=ss; n=len(f)
    cc={}
    for L in range(-maxlag,maxlag+1):
        if L>=0: x=f[:n-L]; y=sp[L:]            # fut leads spot by L
        else:    x=f[-L:];  y=sp[:n+L]
        if len(x)<10: cc[L]=np.nan; continue
        cc[L]=np.corrcoef(x,y)[0,1]
    fut_leads=np.nanmean([abs(cc[L]) for L in range(1,maxlag+1) if np.isfinite(cc[L])])
    spot_leads=np.nanmean([abs(cc[L]) for L in range(-maxlag,0) if np.isfinite(cc[L])])
    ratio=fut_leads-spot_leads
    peak=max((L for L in cc if np.isfinite(cc[L])), key=lambda L: abs(cc[L]), default=np.nan)
    return ratio, peak

# =============================================================================
def main():
    m=load_matches()
    rows=[]

    # ---- universes / windows -------------------------------------------------
    EQ_TOURNS=[2010,2014,2018,2022]
    CR_TOURNS_VR=[2018,2022]      # crypto VR / abret (spot legs always; perp 2022 only)
    CR_TOURNS_BASIS=[2022]        # perp exists 2022-10 onward

    # global load window = union of tournament windows
    wins_all=tournament_windows(m)
    glo=min(w[0] for w in wins_all.values()); ghi=max(w[1] for w in wins_all.values())

    # equity/futures level+return series across full eq span
    spy_r=log_ret_series(os.path.join(EQ,"SPY_1m.parquet"),glo,ghi)["ret"]
    es_r =log_ret_series(os.path.join(FUT,"ES_1m.parquet"),glo,ghi)["ret"]
    spy_l=level_series(os.path.join(EQ,"SPY_1m.parquet"),glo,ghi)
    es_l =level_series(os.path.join(FUT,"ES_1m.parquet"),glo,ghi)

    # crypto series (2018/2022 windows only)
    cw_lo=min(wins_all[t][0] for t in [2018,2022]); cw_hi=max(wins_all[t][1] for t in [2018,2022])
    bsp_r=log_ret_series(os.path.join(CSP,"BTCUSDT_1m.parquet"),cw_lo,cw_hi)["ret"]
    esp_r=log_ret_series(os.path.join(CSP,"ETHUSDT_1m.parquet"),cw_lo,cw_hi)["ret"]
    bpp_r=log_ret_series(os.path.join(CPP,"BTCUSDT_1m.parquet"),cw_lo,cw_hi)["ret"]
    epp_r=log_ret_series(os.path.join(CPP,"ETHUSDT_1m.parquet"),cw_lo,cw_hi)["ret"]
    bsp_l=level_series(os.path.join(CSP,"BTCUSDT_1m.parquet"),cw_lo,cw_hi)
    esp_l=level_series(os.path.join(CSP,"ETHUSDT_1m.parquet"),cw_lo,cw_hi)
    bpp_l=level_series(os.path.join(CPP,"BTCUSDT_1m.parquet"),cw_lo,cw_hi)
    epp_l=level_series(os.path.join(CPP,"ETHUSDT_1m.parquet"),cw_lo,cw_hi)

    # ===================== 1. VARIANCE RATIO =================================
    # equity/futures arm: SPY, ES, QQQ?, keep SPY+ES (the two with basis interest) + NQ/GC for breadth
    vr_eq_inst={"SPY":spy_r,"ES":es_r}
    blocks_eq=block_list(m, EQ_TOURNS)
    vr_rows=[]
    for inst,ser in vr_eq_inst.items():
        for (t,s,mm,wd,clk,ds) in blocks_eq:
            seg=block_window(ser,s,s+DUR)
            vr=variance_ratio(seg)
            if np.isnan(vr): continue
            vr_rows.append(dict(inst=inst,vr=vr,absdev=abs(vr-1.0),match=mm,
                                wd_clk=f"{wd}_{clk}",date=ds,tournament=t))
    vr_df=pd.DataFrame(vr_rows)
    if len(vr_df):
        rows.append(summ(vr_df,"vr","VR(5) equity+futures pooled (level)","VR"))
        rows.append(summ(vr_df,"absdev","VR(5) equity+futures |VR-1| (inefficiency)","|VR-1|"))

    # crypto VR (spot legs 2018+2022, perp legs where present)
    vr_cr_inst={"BTC_spot":bsp_r,"ETH_spot":esp_r,"BTC_perp":bpp_r,"ETH_perp":epp_r}
    blocks_cr=block_list(m, CR_TOURNS_VR)
    crv=[]
    for inst,ser in vr_cr_inst.items():
        for (t,s,mm,wd,clk,ds) in blocks_cr:
            seg=block_window(ser,s,s+DUR); vr=variance_ratio(seg)
            if np.isnan(vr): continue
            crv.append(dict(inst=inst,vr=vr,absdev=abs(vr-1.0),match=mm,wd_clk=f"{wd}_{clk}",date=ds,tournament=t))
    crv_df=pd.DataFrame(crv)
    if len(crv_df):
        rows.append(summ(crv_df,"vr","VR(5) crypto pooled (level)","VR"))
        rows.append(summ(crv_df,"absdev","VR(5) crypto |VR-1| (inefficiency)","|VR-1|"))

    # ===================== 2. BASIS =========================================
    # SPY vs ES: return-spread (scale-free). per block: sd of (es_ret - spy_ret) on common RTH min,
    # and mean abs return-spread (dispersion).
    sf_rows=[]
    common=pd.concat([es_r.rename("es"),spy_r.rename("spy")],axis=1)
    for (t,s,mm,wd,clk,ds) in blocks_eq:
        seg=common.loc[(common.index>=s)&(common.index<s+DUR)].dropna()
        if len(seg)<20: continue
        sp=(seg["es"]-seg["spy"])
        sf_rows.append(dict(basis_sd=sp.std(), basis_absmean=sp.abs().mean(), match=mm,
                            wd_clk=f"{wd}_{clk}",date=ds,tournament=t))
    sf_df=pd.DataFrame(sf_rows)
    if len(sf_df):
        rows.append(summ(sf_df,"basis_sd","SPY-ES return-spread SD per block","sd(log ret diff)"))
        rows.append(summ(sf_df,"basis_absmean","SPY-ES |return-spread| mean per block","mean|ret diff|"))

    # crypto spot-perp basis = log(perp/spot), level & vol, per coin, 2022 only
    def crypto_basis_blocks(spot_l, perp_l, coin):
        b=np.log(perp_l/spot_l.reindex(perp_l.index))   # log(perp/spot), aligned on perp index
        b=b.dropna()
        out=[]
        for (t,s,mm,wd,clk,ds) in block_list(m, CR_TOURNS_BASIS):
            seg=b.loc[(b.index>=s)&(b.index<s+DUR)]
            if len(seg)<20: continue
            out.append(dict(coin=coin, basis_level=seg.mean()*1e4, basis_vol=seg.std()*1e4,
                            match=mm,wd_clk=f"{wd}_{clk}",date=ds,tournament=t))
        return out
    cb=crypto_basis_blocks(bsp_l,bpp_l,"BTC")+crypto_basis_blocks(esp_l,epp_l,"ETH")
    cb_df=pd.DataFrame(cb)
    if len(cb_df):
        rows.append(summ(cb_df,"basis_level","crypto spot-perp basis LEVEL (bps), 2022","bps log(perp/spot)"))
        rows.append(summ(cb_df,"basis_vol","crypto spot-perp basis VOL (bps), 2022","bps sd"))

    # ===================== 3. LEAD-LAG ======================================
    # ES (fut) vs SPY (spot): ratio>0 => futures leads. per block.
    ll_rows=[]
    for (t,s,mm,wd,clk,ds) in blocks_eq:
        rf=block_window(es_r,s,s+DUR); rs=block_window(spy_r,s,s+DUR)
        ratio,peak=lead_lag_ratio(rf,rs)
        if np.isnan(ratio): continue
        ll_rows.append(dict(ll_ratio=ratio, peak_lag=peak, match=mm,wd_clk=f"{wd}_{clk}",date=ds,tournament=t))
    ll_df=pd.DataFrame(ll_rows)
    if len(ll_df):
        rows.append(summ(ll_df,"ll_ratio","lead-lag ES->SPY (fut leads if >0)","corr diff"))

    # crypto perp vs spot lead-lag, 2022 only (perp leads if >0)
    cll=[]
    for (t,s,mm,wd,clk,ds) in block_list(m, CR_TOURNS_BASIS):
        for (perp,spot) in [(bpp_r,bsp_r),(epp_r,esp_r)]:
            rf=block_window(perp,s,s+DUR); rs=block_window(spot,s,s+DUR)
            ratio,peak=lead_lag_ratio(rf,rs)
            if np.isnan(ratio): continue
            cll.append(dict(ll_ratio=ratio,peak_lag=peak,match=mm,wd_clk=f"{wd}_{clk}",date=ds,tournament=t))
    cll_df=pd.DataFrame(cll)
    if len(cll_df):
        rows.append(summ(cll_df,"ll_ratio","lead-lag crypto perp->spot (perp leads if >0), 2022","corr diff"))

    # ===================== 4. ABNORMAL / CUMULATIVE RETURNS ==================
    # market-adjusted ret = inst ret - cross-inst mean ret that minute; cumulate over block.
    # Equity/futures market = {SPY,QQQ,IWM,ES,NQ}? Use the broad-liquid set available across 2010-22:
    # SPY, QQQ, IWM (cash) + ES, NQ (fut). Build a wide minute x inst return frame.
    abr_inst={}
    for tk,sub in [("SPY",EQ),("QQQ",EQ),("IWM",EQ),("ES",FUT),("NQ",FUT)]:
        p=os.path.join(sub,f"{tk}_1m.parquet")
        if os.path.exists(p): abr_inst[tk]=log_ret_series(p,glo,ghi)["ret"]
    wide=pd.concat({k:v for k,v in abr_inst.items()},axis=1)
    mkt=wide.mean(axis=1)
    adj=wide.sub(mkt,axis=0)        # market-adjusted returns
    abr_rows=[]
    for inst in adj.columns:
        ser=adj[inst]
        for (t,s,mm,wd,clk,ds) in blocks_eq:
            seg=ser.loc[(ser.index>=s)&(ser.index<s+DUR)].dropna()
            if len(seg)<20: continue
            car=seg.sum()        # cumulative abnormal return over block
            abr_rows.append(dict(inst=inst, car=car, abscar=abs(car), match=mm,
                                 wd_clk=f"{wd}_{clk}",date=ds,tournament=t))
    abr_df=pd.DataFrame(abr_rows)
    if len(abr_df):
        rows.append(summ(abr_df,"abscar","|CAR| equity+fut (market-adjusted, abs)","|cum abn ret|"))
        rows.append(summ(abr_df,"car","CAR equity+fut (signed, ~0 by constr.)","cum abn ret"))

    # crypto abnormal: market = mean of the 4 crypto legs that minute
    cwide=pd.concat({"BTC_spot":bsp_r,"ETH_spot":esp_r,"BTC_perp":bpp_r,"ETH_perp":epp_r},axis=1)
    cmkt=cwide.mean(axis=1); cadj=cwide.sub(cmkt,axis=0)
    car_rows=[]
    for inst in cadj.columns:
        ser=cadj[inst]
        for (t,s,mm,wd,clk,ds) in blocks_cr:
            seg=ser.loc[(ser.index>=s)&(ser.index<s+DUR)].dropna()
            if len(seg)<20: continue
            car_rows.append(dict(inst=inst,car=ser.loc[(ser.index>=s)&(ser.index<s+DUR)].sum(),
                                 abscar=abs(seg.sum()),match=mm,wd_clk=f"{wd}_{clk}",date=ds,tournament=t))
    car_df=pd.DataFrame(car_rows)
    if len(car_df):
        rows.append(summ(car_df,"abscar","|CAR| crypto (market-adjusted, abs)","|cum abn ret|"))

    out=pd.DataFrame(rows)
    out.to_csv(os.path.join(OUT,"efficiency.csv"),index=False)
    pd.set_option("display.width",240); pd.set_option("display.max_columns",30)
    print(out.to_string(index=False))
    return out

if __name__=="__main__":
    main()
