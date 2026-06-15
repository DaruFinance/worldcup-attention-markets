#!/usr/bin/env python3
"""
Per-country HOME-EQUITY data. For every World Cup nation with an investable, free-data exchange, pull
the main index + a few top-cap names (daily, 2009-2023, yfinance). Daily is the finest free resolution
for foreign exchanges; it supports (a) match-day distraction tests (volume/volatility when a match
overlaps the local session) and (b) the Edmans-Garcia-Norli loser-effect (home market return the day
after the national team plays / loses). Small markets with no free history (most African, Gulf, smaller
South-American) are logged as gaps, not faked. Out: data/market/equities_intl/<TICKER>.parquet + manifest.
"""
import os, time, warnings
warnings.simplefilter("ignore")
import pandas as pd, yfinance as yf
ROOT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"..")
OUT=os.path.join(ROOT,"data","market","equities_intl"); os.makedirs(OUT,exist_ok=True)

# nation -> (index_ticker, [top company tickers])
MAP={
 "Brazil":      ("^BVSP",   ["PETR4.SA","VALE3.SA","ITUB4.SA","BBDC4.SA","ABEV3.SA"]),
 "Mexico":      ("^MXX",    ["AMXL.MX","GFNORTEO.MX","WALMEX.MX","CEMEXCPO.MX"]),
 "Japan":       ("^N225",   ["7203.T","6758.T","9984.T","8306.T"]),
 "England":     ("^FTSE",   ["HSBA.L","BP.L","SHEL.L","AZN.L"]),
 "Germany":     ("^GDAXI",  ["SAP.DE","SIE.DE","ALV.DE","BMW.DE"]),
 "France":      ("^FCHI",   ["MC.PA","OR.PA","TTE.PA","SAN.PA"]),
 "Spain":       ("^IBEX",   ["SAN.MC","IBE.MC","ITX.MC","BBVA.MC"]),
 "Italy":       ("FTSEMIB.MI",["ENI.MI","ISP.MI","ENEL.MI","UCG.MI"]),
 "Netherlands": ("^AEX",    ["ASML.AS","INGA.AS","HEIA.AS"]),
 "Belgium":     ("^BFX",    ["ABI.BR","KBC.BR"]),
 "Portugal":    ("PSI20.LS",["EDP.LS","GALP.LS","JMT.LS"]),
 "Switzerland": ("^SSMI",   ["NESN.SW","ROG.SW","NOVN.SW","UBSG.SW"]),
 "Argentina":   ("^MERV",   ["GGAL.BA","YPFD.BA","PAMP.BA"]),
 "South Korea": ("^KS11",   ["005930.KS","000660.KS","005380.KS"]),
 "Australia":   ("^AXJO",   ["BHP.AX","CBA.AX","CSL.AX"]),
 "Poland":      ("WIG20.WA",["PKO.WA","PKN.WA","PZU.WA"]),
 "Denmark":     ("^OMXC25", ["NOVO-B.CO","MAERSK-B.CO","DSV.CO"]),
 "Sweden":      ("^OMX",    ["VOLV-B.ST","ERIC-B.ST","INVE-B.ST"]),
 "Russia":      ("IMOEX.ME",["SBER.ME","GAZP.ME","LKOH.ME"]),
 "Turkey":      ("XU100.IS",["THYAO.IS","GARAN.IS","AKBNK.IS"]),
 "Greece":      ("^ATG",    ["ETE.AT","OPAP.AT"]),
 "South Africa":("^JN0U.JO",["NPN.JO","MTN.JO","SOL.JO"]),
 "Saudi Arabia":("^TASI.SR",["2222.SR","1120.SR","2010.SR"]),
 "USA":         ("^GSPC",   ["AAPL","MSFT"]),
 "Croatia":     ("^CRBEX",  []),
 "Nigeria":     ("^NGSEINDX",[]),
 "Qatar":       ("^QSI",    []),
}
ALIASES={"^OMXC25":["^OMXC25","^OMXC20"],"^OMX":["^OMX","^OMXS30","^OMXSPI"],"PSI20.LS":["PSI20.LS","^PSI20"],
         "^JN0U.JO":["^JN0U.JO","^J203.JO","^JTOPI"],"^ATG":["^ATG","GD.AT"],"^TASI.SR":["^TASI.SR","^TASI"],
         "^MERV":["^MERV"],"XU100.IS":["XU100.IS","^XU100"]}

def fetch(tk):
    for cand in ALIASES.get(tk,[tk]):
        try:
            df=yf.Ticker(cand).history(start="2009-06-01",end="2023-06-01",auto_adjust=False)
            if df is not None and len(df)>50:
                df=df.reset_index()[["Date","Open","High","Low","Close","Volume"]]
                df.columns=["date","open","high","low","close","volume"]
                df["date"]=pd.to_datetime(df["date"]).dt.tz_localize(None).dt.normalize()
                return cand,df
        except Exception:
            pass
        time.sleep(0.3)
    return None,None

def main():
    man=[]
    for nation,(idx,cos) in MAP.items():
        for role,tk in [("index",idx)]+[("stock",c) for c in cos]:
            used,df=fetch(tk)
            if df is None:
                man.append(dict(nation=nation,role=role,req=tk,used=None,rows=0,y0=None,y1=None,ok=False))
                print(f"MISS {nation:13s} {role:5s} {tk}")
                continue
            fp=os.path.join(OUT,f"{used.replace('^','_').replace('.','_')}.parquet")
            df.to_parquet(fp,index=False)
            y0,y1=df.date.dt.year.min(),df.date.dt.year.max()
            man.append(dict(nation=nation,role=role,req=tk,used=used,rows=len(df),y0=int(y0),y1=int(y1),ok=True,path=fp))
            print(f"OK   {nation:13s} {role:5s} {used:12s} rows={len(df):5d} {y0}..{y1}")
            time.sleep(0.2)
    m=pd.DataFrame(man); m.to_csv(os.path.join(OUT,"manifest.csv"),index=False)
    ok=m[m.ok]; print(f"\n{ok.ok.sum()}/{len(m)} tickers pulled across {ok.nation.nunique()} nations.")
    miss=m[~m.ok];
    if len(miss): print("gaps:", ", ".join(f"{r.nation}/{r.req}" for r in miss.itertuples()))
    return m
if __name__=="__main__":
    main()
