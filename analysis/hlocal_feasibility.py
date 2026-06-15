#!/usr/bin/env python3
"""
Pre-purchase POWER calculation for the intraday H_local test: how many own-team World Cup match in-play
windows overlap the nation's home exchange regular session (weekday only), 2010-2022. This is the binding
constraint -- most kickoffs are outside home trading hours -- and it decides which exchanges are worth
buying. Out: analysis/out/hlocal_feasibility.csv
"""
import os, numpy as np, pandas as pd
R=os.path.join(os.path.dirname(os.path.abspath(__file__)),"..")
M=os.path.join(R,"data","matches"); O=os.path.join(R,"analysis","out")
# nation -> (exchange, UTC open, UTC close)  approx regular session, DST-agnostic (scaffold; the live
# pull resolves DST per date in the exchange's own tz)
EX={"Brazil":("B3",13,20),"Mexico":("BMV",14.5,21),"Argentina":("BYMA",14,20),
    "Japan":("JPX",0,6),"South Korea":("KRX",0,6.5),"Australia":("ASX",0,6),
    "England":("LSE",8,16.5),"Germany":("Xetra",8,16.5),"France":("Euronext-PA",8,16.5),
    "Spain":("BME",8,16.5),"Italy":("BorsaItaliana",8,16.5),"Netherlands":("Euronext-AS",8,16.5),
    "Switzerland":("SIX",8,16.5),"Belgium":("Euronext-BR",8,16.5),"Portugal":("Euronext-LS",8,16.5),
    "South Africa":("JSE",7,15),"Poland":("GPW",8,15),"Nigeria":("NGX",9,13)}

def spine():
    a=pd.read_parquet(os.path.join(M,"matches_all.parquet")); a=a[a.tournament.isin([2018,2022])]
    h=pd.read_parquet(os.path.join(M,"matches_hist.parquet"))
    c=["tournament","kickoff_utc","home","away","played"]
    m=pd.concat([a[c],h[c]],ignore_index=True); m=m[m.played==True].copy()
    m["ko"]=pd.to_datetime(m["kickoff_utc"],utc=True); m["end"]=m["ko"]+pd.Timedelta(minutes=105)
    return m

def overlaps(ko,end,o,cl):
    if ko.weekday()>=5: return False
    h0=ko.hour+ko.minute/60; h1=(end.hour+end.minute/60) if end.date()==ko.date() else 24
    return (h0<cl) and (h1>o)

def main():
    m=spine(); rows=[]
    for nation,(ex,o,cl) in EX.items():
        sub=m[(m.home==nation)|(m.away==nation)]
        flags=[overlaps(r.ko,r.end,o,cl) for r in sub.itertuples()]
        byt={t:int(sum(f for f,tt in zip(flags,sub.tournament) if tt==t)) for t in (2010,2014,2018,2022)}
        rows.append(dict(nation=nation,exchange=ex,own_matches=len(sub),in_session=int(sum(flags)),**{f"y{t}":byt[t] for t in (2010,2014,2018,2022)}))
    d=pd.DataFrame(rows).sort_values("in_session",ascending=False)
    d.to_csv(os.path.join(O,"hlocal_feasibility.csv"),index=False)
    print(d.to_string(index=False))
    print(f"\nPooled in-session own-match clusters: {d.in_session.sum()} | exchanges with >=6: {(d.in_session>=6).sum()} | zero-overlap (do not buy): {list(d[d.in_session==0].exchange)}")
    return d
if __name__=="__main__":
    main()
