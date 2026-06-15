#!/usr/bin/env python3
"""
Unified cross-market minute panel: crypto (spot+perp) + futures (equity/commodity/FX).
Reuses match-state collapse + tournament windows from build_panel_crypto. Per-instrument
outcomes in log points so the Match coefficient is a comparable % change across instruments
regardless of native volume units. Restricted to tournament windows (±21d).

Out: data/market/panel/all_panel.parquet
"""
import os, sys, warnings
warnings.simplefilter("ignore")
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_panel_crypto import collapse_match_state, tournament_windows

ROOT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"..")
CRY=os.path.join(ROOT,"data","market","crypto")
FUT=os.path.join(ROOT,"data","market","futures")
MDIR=os.path.join(ROOT,"data","matches")
OUT=os.path.join(ROOT,"data","market","panel"); os.makedirs(OUT,exist_ok=True)

# registry: (instrument_id, path, market_group, kind)
def registry():
    reg=[]
    for sym in ["BTCUSDT","ETHUSDT"]:
        reg.append((f"{sym}_spot", os.path.join(CRY,"spot",f"{sym}_1m.parquet"),"crypto_spot","crypto"))
        reg.append((f"{sym}_perp", os.path.join(CRY,"perp",f"{sym}_1m.parquet"),"crypto_perp","crypto"))
    grp={"ES":"equity_fut","NQ":"equity_fut","GC":"commodity_fut","CL":"commodity_fut",
         "6E":"fx_fut","6B":"fx_fut","6J":"fx_fut"}
    for r,g in grp.items():
        reg.append((r, os.path.join(FUT,f"{r}_1m.parquet"), g, "futures"))
    return [x for x in reg if os.path.exists(x[1])]

def outcomes(df, kind):
    df=df.sort_values("ts").reset_index(drop=True)
    c=df["close"].astype(float)
    if kind=="crypto":
        vol=df["quote_volume"].astype(float); cnt=df["count"].astype(float)
        buy=df["taker_buy_quote"].astype(float); sell=vol-buy
    else:
        vol=df["volume"].astype(float); cnt=df["count"].astype(float)
        buy=df["buy"].astype(float); sell=df["sell"].astype(float)
    df["ret"]=np.log(c/c.shift(1)); df["absret"]=df["ret"].abs(); df["sqret"]=df["ret"]**2
    df["lvol"]=np.log(vol.where(vol>0)); df["ltrades"]=np.log(cnt.where(cnt>0))
    at=vol/cnt.replace(0,np.nan); df["lavg_trade"]=np.log(at.where(at>0))
    hl=np.log(df["high"].astype(float)/df["low"].astype(float)); df["hlrange"]=hl.where(hl>=0)
    df["amihud"]=(df["absret"]/vol.where(vol>0))*1e9
    tot=(buy+sell).replace(0,np.nan); df["signed_imb"]=(buy-sell)/tot
    return df

def build():
    matches=pd.read_parquet(os.path.join(MDIR,"matches_all.parquet"))
    ms=pd.read_parquet(os.path.join(MDIR,"match_state_all.parquet"))
    feat=collapse_match_state(ms); wins=tournament_windows(matches)
    parts=[]
    for inst,path,grp,kind in registry():
        d=pd.read_parquet(path); d["ts"]=pd.to_datetime(d["ts"],utc=True)
        d=outcomes(d,kind)
        keep=pd.Series(False,index=d.index); d["tournament"]=pd.NA
        for t,(a,b) in wins.items():
            mft=(d["ts"]>=a)&(d["ts"]<b); d.loc[mft,"tournament"]=t; keep|=mft
        d=d[keep].copy()
        if not len(d): continue
        d=d.merge(feat.drop(columns=["tournament"]),left_on="ts",right_on="minute_utc",how="left")
        for col in ["any_match","any_pre","any_post","any_first_half","any_halftime",
                    "any_second_half","any_knockout","any_usa","any_euro","any_gbp","any_jpy"]:
            d[col]=d[col].fillna(False).astype(bool)
        d["n_in_match"]=d["n_in_match"].fillna(0).astype(int)
        d["match"]=d["any_match"].astype(int)
        d["weekday"]=d["ts"].dt.weekday; d["minute_of_day"]=d["ts"].dt.hour*60+d["ts"].dt.minute
        d["date"]=d["ts"].dt.strftime("%Y-%m-%d")
        d["wd_mod"]=d["weekday"].astype(str)+"_"+d["minute_of_day"].astype(str)
        d["instrument"]=inst; d["market_group"]=grp; d["kind"]=kind
        for c in ["any_knockout","any_usa","any_euro","any_gbp","any_jpy","any_pre",
                  "any_first_half","any_halftime","any_second_half","any_post"]:
            d[c+"_i"]=d[c].astype(int)
        parts.append(d)
        print(f"  {inst:14s} {grp:13s} rows={len(d):>7,} match-min={int(d['any_match'].sum()):>6,} "
              f"tourns={sorted(d['tournament'].dropna().unique().tolist())}")
    cols=["ts","instrument","market_group","kind","tournament","date","weekday","minute_of_day",
          "wd_mod","match","n_in_match","ret","absret","sqret","lvol","ltrades","lavg_trade",
          "hlrange","amihud","signed_imb",
          "any_knockout_i","any_usa_i","any_euro_i","any_gbp_i","any_jpy_i",
          "any_pre_i","any_first_half_i","any_halftime_i","any_second_half_i","any_post_i"]
    panel=pd.concat(parts,ignore_index=True)[cols]
    panel.to_parquet(os.path.join(OUT,"all_panel.parquet"))
    print(f"ALL PANEL rows={len(panel):,} instruments={panel['instrument'].nunique()} "
          f"groups={sorted(panel['market_group'].unique())}")
    return panel

if __name__=="__main__":
    build()
