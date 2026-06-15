#!/usr/bin/env python3
"""
Treatment validation: hourly English-Wikipedia pageviews for the World Cup tournament
articles over the 2018 & 2022 windows. If match hours show large view spikes, the
attention shock is real, so a market null means markets ignore a demonstrable shock
(not that no shock occurred).

Wikimedia REST: /metrics/pageviews/per-article/en.wikipedia/all-access/all-agents/{art}/hourly/{s}/{e}
Out: data/controls/wiki_daily.parquet  [ts, article, views]
"""
import os, json, urllib.request, urllib.parse, time
from datetime import datetime, timezone
import pandas as pd

OUT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"..","data","controls")
os.makedirs(OUT, exist_ok=True)
BASE="https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/all-agents"
ARTICLES={2018:["2018_FIFA_World_Cup"], 2022:["2022_FIFA_World_Cup"]}
WIN={2018:("2018052000","2018081500"), 2022:("2022103000","2023011000")}

def fetch(article, s, e):
    url=f"{BASE}/{urllib.parse.quote(article,safe='')}/daily/{s}/{e}"
    req=urllib.request.Request(url, headers={"User-Agent":"wc-study/1.0 (research)"})
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.loads(r.read())["items"]

def main():
    rows=[]
    for yr,arts in ARTICLES.items():
        s,e=WIN[yr]
        for a in arts:
            try: items=fetch(a,s,e)
            except Exception as ex:
                print(f"{a}: {ex}"); continue
            for it in items:
                ts=datetime.strptime(it["timestamp"],"%Y%m%d%H").replace(tzinfo=timezone.utc)
                rows.append(dict(ts=ts, article=a, views=it["views"], tournament=yr))
            print(f"{a}: {len(items)} daily points")
            time.sleep(0.3)
    df=pd.DataFrame(rows)
    if len(df):
        df["ts"]=pd.to_datetime(df["ts"],utc=True)
        df.to_parquet(os.path.join(OUT,"wiki_daily.parquet"))
        print(f"wiki_daily: {len(df)} rows -> saved")
    return df

if __name__=="__main__":
    import urllib.parse
    main()
