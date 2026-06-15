#!/usr/bin/env python3
"""
2010 (South Africa) + 2014 (Brazil) match spine from openfootball, for the own-team POWER
extension of H6 (futures/cash equities go back to 2007; crypto does not, so this does not
touch the symmetric 2018/22 cross-market core). Same own-team flags as the core.
Out: data/matches/matches_hist.parquet
"""
import os, json, re
from datetime import datetime, timedelta, timezone
import pandas as pd

MDIR=os.path.join(os.path.dirname(os.path.abspath(__file__)),"..","data","matches")
HOST_OFFSET={2010:2, 2014:-3}      # SA=UTC+2 (no DST); Brazil mostly UTC-3
HOST_TEAMS={2010:{"South Africa"}, 2014:{"Brazil"}}
EURO={"Germany","France","Spain","Netherlands","Italy","Portugal","Greece","Belgium",
      "Austria","Ireland","Finland","Slovakia","Slovenia"}   # euro-area as of 2010/2014 (no Croatia)

def stage_of(rnd):
    r=rnd.lower()
    if "matchday" in r or "group" in r: return "group",False
    if "round of 16" in r: return "R16",True
    if "quarter" in r: return "QF",True
    if "semi" in r: return "SF",True
    if "final" in r or "third" in r: return "final_3rd",True
    return None,False

def parse_ko(date, timestr, year):
    m=re.match(r"(\d{1,2}):(\d{2})(?:\s*UTC([+-]\d{1,2}))?", timestr.strip())
    hh,mm=int(m.group(1)),int(m.group(2))
    off=int(m.group(3)) if m.group(3) else HOST_OFFSET[year]
    local=datetime.strptime(date,"%Y-%m-%d").replace(hour=hh,minute=mm,tzinfo=timezone.utc)
    return local - timedelta(hours=off)

def norm_usa(t): return t in ("USA","United States")

def build():
    rows=[]
    for year in (2010,2014):
        p=os.path.join(MDIR,f"of{year}.json")
        d=json.load(open(p))["matches"]
        for i,mt in enumerate(d,1):
            try: ko=parse_ko(mt["date"], mt["time"], year)
            except Exception: continue
            stage,kn=stage_of(mt.get("round",""))
            h,a=mt["team1"],mt["team2"]; ft=mt.get("score",{}).get("ft")
            played=isinstance(ft,list) and len(ft)==2
            rows.append(dict(
                tournament=year, match_no=i, stage=stage, knockout=kn,
                kickoff_utc=ko, home=h, away=a,
                home_score=ft[0] if played else None, away_score=ft[1] if played else None,
                played=played, teams_known=True,
                usa_playing=(norm_usa(h) or norm_usa(a)),
                euro_playing=bool(EURO & {h,a}),
                gbp_playing=bool({"England","Scotland"} & {h,a}),
                jpy_playing=("Japan" in (h,a)),
                host_team_playing=bool(HOST_TEAMS[year] & {h,a}),
                win_pre60_start=ko-timedelta(minutes=60), win_ko=ko,
                win_ht=ko+timedelta(minutes=45), win_2h=ko+timedelta(minutes=60),
                win_ft_nominal=ko+timedelta(minutes=105), win_post60_end=ko+timedelta(minutes=165),
            ))
    df=pd.DataFrame(rows)
    df.to_parquet(os.path.join(MDIR,"matches_hist.parquet"))
    print("matches_hist:", len(df), "| by tournament:", df.groupby("tournament").size().to_dict())
    print("own-team match counts:",
          {"usa":int(df.usa_playing.sum()),"euro":int(df.euro_playing.sum()),
           "gbp":int(df.gbp_playing.sum()),"jpy":int(df.jpy_playing.sum())})
    return df

if __name__=="__main__":
    build()
