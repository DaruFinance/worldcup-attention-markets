#!/usr/bin/env python3
"""
Build the crypto minute panel for the event study.

For each instrument (BTC/ETH x spot/perp): 1-min outcomes computed on the FULL series
(returns have no window-boundary leakage), then restricted to tournament-window dates
(first match -21d .. last match +21d). Match features come from the unified match-state
collapsed to per-UTC-minute (concurrent-match intensity, half/pre/post, knockout, domestic
flags). Control minutes = same instrument, same weekday & minute-of-day, NON-match periods
inside the same window  -  the comparison the weekday×minute-of-day FE makes.

Out: data/market/panel/crypto_panel.parquet  (long: one row per instrument-minute)
"""
import os
import numpy as np, pandas as pd

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
CRY  = os.path.join(ROOT, "data", "market", "crypto")
MDIR = os.path.join(ROOT, "data", "matches")
OUT  = os.path.join(ROOT, "data", "market", "panel")
os.makedirs(OUT, exist_ok=True)

INSTRUMENTS = [("BTCUSDT","spot"),("ETHUSDT","spot"),("BTCUSDT","perp"),("ETHUSDT","perp")]

def log(m):
    from datetime import datetime, timezone
    print(f"[{datetime.now(timezone.utc):%H:%M:%S}] {m}", flush=True)

def tournament_windows(matches):
    w={}
    for t,g in matches.groupby("tournament"):
        ko=pd.to_datetime(g["kickoff_utc"], utc=True)
        w[t]=(ko.min().normalize()-pd.Timedelta(days=21),
              ko.max().normalize()+pd.Timedelta(days=22))
    return w

def collapse_match_state(ms):
    """Per-UTC-minute match features (across concurrent matches)."""
    ms=ms.copy(); ms["minute_utc"]=pd.to_datetime(ms["minute_utc"], utc=True)
    inm=ms[ms["in_match"]]
    g=ms.groupby("minute_utc")
    gi=inm.groupby("minute_utc")
    feat=pd.DataFrame(index=ms["minute_utc"].drop_duplicates().sort_values())
    feat["n_in_match"]   = gi.size().reindex(feat.index).fillna(0).astype(int)
    feat["any_match"]    = (feat["n_in_match"]>0)
    feat["any_pre"]      = g["pre_match"].max().reindex(feat.index).fillna(False)
    feat["any_post"]     = g["post_match"].max().reindex(feat.index).fillna(False)
    feat["any_first_half"]=g["first_half"].max().reindex(feat.index).fillna(False)
    feat["any_halftime"] = g["halftime"].max().reindex(feat.index).fillna(False)
    feat["any_second_half"]=g["second_half"].max().reindex(feat.index).fillna(False)
    feat["any_knockout"] = gi["knockout"].max().reindex(feat.index).fillna(False)
    feat["any_usa"]      = gi["usa_playing"].max().reindex(feat.index).fillna(False)
    feat["any_euro"]     = gi["euro_playing"].max().reindex(feat.index).fillna(False)
    feat["any_gbp"]      = gi["gbp_playing"].max().reindex(feat.index).fillna(False)
    feat["any_jpy"]      = gi["jpy_playing"].max().reindex(feat.index).fillna(False)
    feat["tournament"]   = g["tournament"].max().reindex(feat.index)
    return feat.reset_index().rename(columns={"index":"minute_utc"})

def outcomes(df):
    df=df.sort_values("ts").reset_index(drop=True)
    c=df["close"].astype(float); qv=df["quote_volume"].astype(float)
    df["ret"]=np.log(c/c.shift(1))
    df["absret"]=df["ret"].abs()
    df["sqret"]=df["ret"]**2
    df["lvol"]=np.log(qv.where(qv>0))
    df["ltrades"]=np.log(df["count"].astype(float).where(df["count"]>0))
    df["avg_trade"]=qv/df["count"].replace(0,np.nan)
    df["lavg_trade"]=np.log(df["avg_trade"].where(df["avg_trade"]>0))
    hl=np.log(df["high"].astype(float)/df["low"].astype(float))
    df["hlrange"]=hl.where(hl>=0)
    df["amihud"]=(df["absret"]/qv.where(qv>0))*1e9
    tbq=df["taker_buy_quote"].astype(float)
    df["buy_frac"]=tbq/qv.where(qv>0)
    df["signed_imb"]=2*df["buy_frac"]-1
    return df

def build():
    matches=pd.read_parquet(os.path.join(MDIR,"matches_all.parquet"))
    ms=pd.read_parquet(os.path.join(MDIR,"match_state_all.parquet"))
    feat=collapse_match_state(ms)
    wins=tournament_windows(matches)
    log(f"windows: { {int(k):(str(v[0].date()),str(v[1].date())) for k,v in wins.items()} }")

    parts=[]
    for sym,mkt in INSTRUMENTS:
        p=os.path.join(CRY,mkt,f"{sym}_1m.parquet")
        if not os.path.exists(p):
            log(f"skip {sym} {mkt} (no file)"); continue
        d=pd.read_parquet(p); d["ts"]=pd.to_datetime(d["ts"], utc=True)
        d=outcomes(d)
        # restrict to union of tournament windows; tag tournament
        keep=pd.Series(False, index=d.index); d["tournament"]=pd.NA
        for t,(a,b) in wins.items():
            mft=(d["ts"]>=a)&(d["ts"]<b)
            d.loc[mft,"tournament"]=t; keep|=mft
        d=d[keep].copy()
        if not len(d):
            log(f"{sym} {mkt}: no rows in windows"); continue
        # join per-minute match features
        d=d.merge(feat.drop(columns=["tournament"]), left_on="ts", right_on="minute_utc", how="left")
        for col in ["any_match","any_pre","any_post","any_first_half","any_halftime",
                    "any_second_half","any_knockout","any_usa","any_euro","any_gbp","any_jpy"]:
            d[col]=d[col].fillna(False).astype(bool)
        d["n_in_match"]=d["n_in_match"].fillna(0).astype(int)
        # time FE keys
        d["weekday"]=d["ts"].dt.weekday
        d["minute_of_day"]=d["ts"].dt.hour*60+d["ts"].dt.minute
        d["date"]=d["ts"].dt.strftime("%Y-%m-%d")
        d["wd_mod"]=d["weekday"].astype(str)+"_"+d["minute_of_day"].astype(str)
        d["instrument"]=f"{sym}_{mkt}"
        d["sym"]=sym; d["mkt"]=mkt
        parts.append(d)
        log(f"{sym} {mkt}: {len(d):,} rows | match-minutes={int(d['any_match'].sum()):,} "
            f"| max concurrent={int(d['n_in_match'].max())}")
    panel=pd.concat(parts, ignore_index=True)
    cols=["ts","instrument","sym","mkt","tournament","date","weekday","minute_of_day","wd_mod",
          "ret","absret","sqret","lvol","ltrades","avg_trade","lavg_trade","hlrange","amihud",
          "buy_frac","signed_imb","close","quote_volume","count",
          "any_match","n_in_match","any_pre","any_post","any_first_half","any_halftime",
          "any_second_half","any_knockout","any_usa","any_euro","any_gbp","any_jpy"]
    panel=panel[cols]
    outp=os.path.join(OUT,"crypto_panel.parquet")
    panel.to_parquet(outp)
    log(f"PANEL -> {outp}  rows={len(panel):,}  instruments={panel['instrument'].nunique()}")
    print(panel.groupby(["tournament","instrument"]).agg(
        rows=("ret","size"), match_min=("any_match","sum")).to_string())
    return panel

if __name__=="__main__":
    build()
