#!/usr/bin/env python3
"""
Exotic / small-nation FX, DAILY (yfinance USDxxx=X). The smallest WC nations are where the attention
effect could be largest, but their currencies have no free intraday history and individually too few
own-match-days for a valid single-pair test (<~22 even pulling 2010-2022). Collected here to be POOLED
into one small-nation panel (shared own_match coef + country-size interaction) and for the day-of /
next-day loser-effect window. Floating/managed EM only  -  hard pegs (XOF/XAF, Gulf), dollarized (Ecuador),
and sanctioned no-free-market (Iran) are excluded as untestable, not faked.
Out: data/market/fx_exotic_daily/<PAIR>.parquet + manifest.
"""
import os, time, warnings
warnings.simplefilter("ignore")
import pandas as pd, yfinance as yf
ROOT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"..")
OUT=os.path.join(ROOT,"data","market","fx_exotic_daily"); os.makedirs(OUT,exist_ok=True)
# pair -> home nation (for the own-match keying downstream)
PAIRS={"USDBRL=X":"Brazil","USDMXN=X":"Mexico","USDZAR=X":"South Africa","USDTRY=X":"Turkey",
       "USDPLN=X":"Poland","USDRUB=X":"Russia","USDCOP=X":"Colombia","USDCLP=X":"Chile",
       "USDPEN=X":"Peru","USDNGN=X":"Nigeria","USDEGP=X":"Egypt","USDMAD=X":"Morocco",
       "USDARS=X":"Argentina","USDUYU=X":"Uruguay","USDKRW=X":"South Korea","USDGHS=X":"Ghana",
       "USDTND=X":"Tunisia","USDDZD=X":"Algeria","USDHUF=X":"Hungary","USDCZK=X":"Czechia",
       "USDSEK=X":"Sweden","USDDKK=X":"Denmark","USDHRK=X":"Croatia","USDRSD=X":"Serbia"}

def fetch(tk):
    try:
        df=yf.Ticker(tk).history(start="2009-06-01",end="2023-06-01",auto_adjust=False)
        if df is not None and len(df)>50:
            df=df.reset_index()[["Date","Open","High","Low","Close"]]
            df.columns=["date","open","high","low","close"]
            df["date"]=pd.to_datetime(df["date"]).dt.tz_localize(None).dt.normalize()
            return df
    except Exception:
        pass
    return None

def main():
    man=[]
    for tk,nation in PAIRS.items():
        df=fetch(tk); time.sleep(0.25)
        if df is None:
            man.append(dict(pair=tk,nation=nation,rows=0,y0=None,y1=None,ok=False)); print(f"MISS {tk:10s} {nation}"); continue
        fp=os.path.join(OUT,f"{tk.replace('=X','').replace('USD','USD_')}.parquet"); df.to_parquet(fp,index=False)
        y0,y1=int(df.date.dt.year.min()),int(df.date.dt.year.max())
        man.append(dict(pair=tk,nation=nation,rows=len(df),y0=y0,y1=y1,ok=True,path=fp))
        print(f"OK   {tk:10s} {nation:13s} rows={len(df):5d} {y0}..{y1}")
    m=pd.DataFrame(man); m.to_csv(os.path.join(OUT,"manifest.csv"),index=False)
    print(f"\n{m.ok.sum()}/{len(m)} exotic pairs pulled.")
    miss=m[~m.ok]
    if len(miss): print("gaps:", ", ".join(f"{r.pair}({r.nation})" for r in miss.itertuples()))
    return m
if __name__=="__main__":
    main()
