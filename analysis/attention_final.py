#!/usr/bin/env python3
"""
The §5 intraday-attention reconstruction (2022 final), emitted by one script over the free Wikimedia
hourly pageview dumps. Pulls the kickoff hour (15:00 UTC, 2022-12-18) and a 3h-earlier baseline (12:00
UTC), extracts the two finalists' national-team articles, the tournament article, and the Lionel Messi
article, and reports the kickoff-hour spike. Out: analysis/out/attention_hourly_final.csv
"""
import os, gzip, io, urllib.request
import pandas as pd
O=os.path.join(os.path.dirname(os.path.abspath(__file__)),"..","analysis","out")
ARTS={"2022_FIFA_World_Cup":"2022 FIFA World Cup","Argentina_national_football_team":"Argentina national team",
      "France_national_football_team":"France national team","Lionel_Messi":"Lionel Messi"}

def hour(dt):
    url=f"https://dumps.wikimedia.org/other/pageviews/{dt:%Y}/{dt:%Y-%m}/pageviews-{dt:%Y%m%d}-{dt:%H}0000.gz"
    got={k:0 for k in ARTS}
    req=urllib.request.Request(url,headers={"User-Agent":"wc-research/1.0"})
    with urllib.request.urlopen(req,timeout=180) as resp:
        with gzip.GzipFile(fileobj=io.BytesIO(resp.read())) as gz:
            for line in io.TextIOWrapper(gz,encoding="utf-8",errors="ignore"):
                p=line.split(" ")
                if len(p)>=3 and p[0]=="en" and p[1] in got: got[p[1]]=int(p[2])
    return got

def main():
    ko=pd.Timestamp("2022-12-18 15:00",tz="UTC"); base=ko-pd.Timedelta(hours=3)
    pre=hour(base); kick=hour(ko)
    rows=[dict(article=ARTS[k],pre_kickoff=pre[k],kickoff=kick[k],ratio=round(kick[k]/pre[k],1)) for k in ARTS]
    d=pd.DataFrame(rows); d.to_csv(os.path.join(O,"attention_hourly_final.csv"),index=False)
    print(d.to_string(index=False)); print("mean kickoff-hour spike vs -3h baseline:",round(d.ratio.mean(),1),"x")
if __name__=="__main__":
    main()
