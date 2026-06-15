#!/usr/bin/env python3
"""
Goal-event timestamps for 2018 & 2022 from openfootball (goal minute + stoppage offset).
Converts match clock to approximate UTC instant:
  elapsed = minute + offset + (15 if minute>45 else 0) + (5 if minute>90 else 0)
  goal_utc = kickoff_utc + elapsed   (±a few min; goal windows ±5/±15 absorb it)
kickoff_utc parsed from openfootball "HH:MM UTC±H".

Out: data/matches/goals_all.parquet  (one row per goal)
"""
import os, json, re
from datetime import datetime, timedelta, timezone
import pandas as pd

MDIR=os.path.join(os.path.dirname(os.path.abspath(__file__)),"..","data","matches")

def norm(t):
    t=t.lower().strip()
    alias={"south korea":"korea republic","iran":"ir iran","czech republic":"czechia",
           "turkey":"türkiye","ivory coast":"côte d'ivoire"}
    t=alias.get(t,t)
    return re.sub(r"[^a-z]","",t)

def kickoff_lookup():
    """(tournament, date, frozenset{team}) -> exact kickoff_utc from the spine."""
    m=pd.read_parquet(os.path.join(MDIR,"matches_all.parquet"))
    m["ko"]=pd.to_datetime(m["kickoff_utc"], utc=True)
    lut={}
    for _,r in m.iterrows():
        if not r["played"] and r["tournament"]!=2026: continue
        d=r["ko"].strftime("%Y-%m-%d")
        key=(int(r["tournament"]), d, frozenset({norm(r["home"]), norm(r["away"])}))
        lut[key]=r["ko"]
        # also index by date±1 to absorb local/UTC date drift
        for dd in (-1,1):
            d2=(r["ko"]+timedelta(days=dd)).strftime("%Y-%m-%d")
            lut.setdefault((int(r["tournament"]), d2, key[2]), r["ko"])
    return lut

def elapsed_minutes(minute, offset):
    e=minute+(offset or 0)
    if minute>45: e+=15      # halftime break
    if minute>90: e+=5       # break before extra time
    return e

def build():
    lut=kickoff_lookup()
    rows=[]; unmatched=0
    for year in (2018,2022):
        p=os.path.join(MDIR,f"of{year}.json")
        if not os.path.exists(p): continue
        d=json.load(open(p))
        for mt in d["matches"]:
            key=(year, mt["date"], frozenset({norm(mt["team1"]), norm(mt["team2"])}))
            ko=lut.get(key)
            if ko is None:
                unmatched+=1; continue
            for side,team_key in (("goals1","team1"),("goals2","team2")):
                for g in mt.get(side,[]):
                    minute=g.get("minute"); off=g.get("offset",0)
                    if minute is None: continue
                    el=elapsed_minutes(minute, off)
                    rows.append(dict(
                        tournament=year, date=mt["date"], team1=mt["team1"], team2=mt["team2"],
                        kickoff_utc=ko, scoring_team=mt[team_key],
                        minute=minute, offset=off, elapsed_min=el,
                        goal_utc=ko+timedelta(minutes=el),
                        ground=mt.get("ground")))
    df=pd.DataFrame(rows).sort_values("goal_utc").reset_index(drop=True)
    df.to_parquet(os.path.join(MDIR,"goals_all.parquet"))
    print(f"goals_all: {len(df)} goals | 2018={int((df.tournament==2018).sum())} "
          f"2022={int((df.tournament==2022).sum())} | unmatched matches={unmatched}")
    print(df.head(4)[["tournament","date","scoring_team","minute","goal_utc"]].to_string(index=False))
    return df

if __name__=="__main__":
    build()
