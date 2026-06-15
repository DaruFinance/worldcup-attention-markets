#!/usr/bin/env python3
"""
Vendor-agnostic puller for intraday HOME-EXCHANGE data (the H_local pull). Maps nation -> exchange ->
index-constituent tickers, fetches 1-min bars inside each tournament's +/-21d window in the exchange's
local timezone, and writes data/market/home_intraday/<EXCH>_1m.parquet (cols: ts_utc, ticker, trades,
volume). Two back ends: EODHD (set EODHD_API_KEY) and a generic local-CSV importer for archive/TRTH dumps.
Only the Americas+Europe exchanges that carry in-session own-team matches are listed (see
analysis/hlocal_feasibility.py); JPX/KRX/ASX/NGX are omitted -- zero overlap, not worth pulling.
"""
import os, sys, time
import pandas as pd
R=os.path.join(os.path.dirname(os.path.abspath(__file__)),"..")
OUT=os.path.join(R,"data","market","home_intraday"); os.makedirs(OUT,exist_ok=True)
TOURN_WINDOWS={2010:("2010-05-20","2010-07-31"),2014:("2014-05-22","2014-07-31"),
               2018:("2018-05-24","2018-07-31"),2022:("2022-10-29","2023-01-07")}
# exchange -> (EODHD suffix, IANA tz, [constituent tickers, top liquidity])  -- trim/extend as licensed
EXCH={
 "B3":        (".SA","America/Sao_Paulo",["PETR4","VALE3","ITUB4","BBDC4","ABEV3","B3SA3","WEGE3","PETR3"]),
 "BMV":       (".MX","America/Mexico_City",["AMXL","GFNORTEO","WALMEX","FEMSAUBD","CEMEXCPO","GMEXICOB"]),
 "BYMA":      (".BA","America/Argentina/Buenos_Aires",["GGAL","YPFD","PAMP","BMA","TXAR"]),
 "Euronext-PA":(".PA","Europe/Paris",["MC","OR","TTE","SAN","AIR","BNP"]),
 "Euronext-AS":(".AS","Europe/Amsterdam",["ASML","INGA","HEIA","ADYEN","PHIA"]),
 "Euronext-LS":(".LS","Europe/Lisbon",["EDP","GALP","JMT","BCP"]),
 "Euronext-BR":(".BR","Europe/Brussels",["ABI","KBC","UCB","SOLB"]),
 "Xetra":     (".XETRA","Europe/Berlin",["SAP","SIE","ALV","BMW","BAS","DTE"]),
 "SIX":       (".SW","Europe/Zurich",["NESN","ROG","NOVN","UBSG","ZURN"]),
 "BME":       (".MC","Europe/Madrid",["SAN","IBE","ITX","BBVA","TEF"]),
 "LSE":       (".LSE","Europe/London",["HSBA","BP","SHEL","AZN","ULVR","RIO"]),
 "BorsaItaliana":(".MI","Europe/Rome",["ENI","ISP","ENEL","UCG","STLAM"]),
 "JSE":       (".JSE","Africa/Johannesburg",["NPN","MTN","SOL","FSR","SBK"]),
 "GPW":       (".WAR","Europe/Warsaw",["PKO","PKN","PZU","PEO","DNP"]),
}

def fetch_eodhd(ticker, frm, to, key):
    import requests
    url=f"https://eodhd.com/api/intraday/{ticker}"
    params=dict(api_token=key,interval="1m",fmt="json",
                **{"from":int(pd.Timestamp(frm,tz='UTC').timestamp()),
                   "to":int(pd.Timestamp(to,tz='UTC').timestamp())})
    r=requests.get(url,params=params,timeout=60); r.raise_for_status(); j=r.json()
    if not j: return None
    d=pd.DataFrame(j)
    d["ts_utc"]=pd.to_datetime(d["timestamp"],unit="s",utc=True)
    # EODHD intraday carries volume; trade count is approximated by tick-bar count where absent
    d["trades"]=d.get("count",d.get("volume")); d["volume"]=d.get("volume")
    return d[["ts_utc","trades","volume"]]

def import_csv(path):
    """Generic importer for an archive/TRTH dump: expects columns ts_utc|datetime, ticker, trades|count, volume."""
    d=pd.read_csv(path)
    tc=[c for c in d.columns if c.lower() in ("ts_utc","datetime","timestamp","time")][0]
    d["ts_utc"]=pd.to_datetime(d[tc],utc=True)
    for a,b in [("trades","count"),("volume","vol")]:
        if a not in d.columns and b in d.columns: d[a]=d[b]
    return d[["ts_utc","ticker","trades","volume"]]

def main():
    key=os.environ.get("EODHD_API_KEY")
    csv_dir=os.environ.get("HOME_INTRADAY_CSV_DIR")  # point at a folder of archive dumps instead
    if not key and not csv_dir:
        print("No data source configured. Set EODHD_API_KEY for the pilot pull, or HOME_INTRADAY_CSV_DIR")
        print("to import archive/TRTH dumps. Target exchanges (Americas+Europe, in-session > 0):")
        for e in EXCH: print("  -",e)
        print("\nPer analysis/hlocal_feasibility.py this yields ~83 in-session clusters (full 2010-2022) or")
        print("~23 from a 2022-only EODHD pilot. JPX/KRX/ASX/NGX omitted (zero overlap).")
        return
    for exch,(suf,tz,tickers) in EXCH.items():
        parts=[]
        for tk in tickers:
            for y,(frm,to) in TOURN_WINDOWS.items():
                try:
                    if key:
                        d=fetch_eodhd(tk+suf,frm,to,key)
                        if d is not None and len(d): d["ticker"]=tk; parts.append(d)
                        time.sleep(0.3)
                except Exception as e:
                    print(f"  skip {tk}{suf} {y}: {type(e).__name__}")
        if csv_dir:
            p=os.path.join(csv_dir,f"{exch}.csv")
            if os.path.exists(p): parts.append(import_csv(p))
        if parts:
            df=pd.concat(parts,ignore_index=True)
            df.to_parquet(os.path.join(OUT,f"{exch}_1m.parquet"),index=False)
            print(f"OK {exch}: {len(df):,} bar-rows, {df.ticker.nunique()} tickers")
        else:
            print(f"-- {exch}: no data returned")
if __name__=="__main__":
    main()
