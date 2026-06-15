#!/usr/bin/env python3
"""
Unified match spine across 2018 (Russia, 64m), 2022 (Qatar, 64m), 2026 (NA, 104m).
Reuses the team->market relevance map from build_matches.py; adds year-aware euro-area
membership (Netherlands absent 2018; Croatia & Austria pre-euro until 2023) so the
EUR/USD domestic-team flag is correct per tournament.

Emits data/matches/matches_all.parquet (+ matches_{year}.parquet) and match_state_all.parquet.
"""
import json, os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import pandas as pd
import build_matches as bm  # same dir on sys.path via runner

MDIR = bm.MDIR

STAGE64 = {1:"group",2:"group",3:"group",4:"R16",5:"QF",6:"SF",7:"final_3rd"}
KNOCK   = {"R32","R16","QF","SF","final_3rd"}

# euro-area teams actually participating, by tournament (names == feed names)
EURO_BY_YEAR = {
    2018: {"Germany","France","Spain","Belgium","Portugal"},
    2022: {"Germany","France","Spain","Belgium","Portugal","Netherlands"},
    2026: {"Germany","France","Spain","Netherlands","Belgium","Austria","Portugal","Croatia"},
}
HOST = {2018:"Russia", 2022:"Qatar", 2026:None}   # 2026 host derived per-venue
HOST_TEAMS = {2018:{"Russia"}, 2022:{"Qatar"}, 2026:{"USA","Mexico","Canada"}}

# venue tz: 2026 from bm.VENUE; 2018 Russia (multi-tz best-effort); 2022 all Qatar
TZ2018 = {
    "Luzhniki Stadium, Moscow":"Europe/Moscow","Spartak Stadium, Moscow":"Europe/Moscow",
    "Saint Petersburg Stadium":"Europe/Moscow","Fisht Stadium, Sochi":"Europe/Moscow",
    "Kaliningrad Stadium":"Europe/Kaliningrad","Kazan Arena":"Europe/Moscow",
    "Nizhny Novgorod Stadium":"Europe/Moscow","Samara Arena":"Europe/Samara",
    "Volgograd Arena":"Europe/Volgograd","Rostov Arena":"Europe/Moscow",
    "Mordovia Arena, Saransk":"Europe/Moscow","Ekaterinburg Stadium":"Asia/Yekaterinburg",
}

def cfg(year):
    feed = os.path.join(MDIR, f"wc{year}_fixturedownload.json")
    n = len(json.load(open(feed)))
    is104 = (n > 64)
    return dict(year=year, feed=feed, stage=bm.STAGE if is104 else STAGE64)

def venue_tz(year, loc):
    if year==2026: return bm.VENUE.get(loc,(None,None,None))[2]
    if year==2022: return "Asia/Qatar"
    if year==2018: return TZ2018.get(loc,"Europe/Moscow")
    return None

def host_country(year, loc):
    if year==2026: return bm.VENUE.get(loc,(None,None,None))[1]
    return HOST[year]

def build_year(year):
    c=cfg(year); feed=json.load(open(c["feed"])); euro=EURO_BY_YEAR.get(year,set())
    rows=[]
    for m in feed:
        ko=datetime.strptime(m["DateUtc"],"%Y-%m-%d %H:%M:%SZ").replace(tzinfo=timezone.utc)
        stage=c["stage"].get(m["RoundNumber"])
        tz=venue_tz(year,m["Location"]); hc=host_country(year,m["Location"])
        h,a=m["HomeTeam"],m["AwayTeam"]; rh,ra=bm.relevance(h),bm.relevance(a)
        teams_known=not(bm.is_placeholder(h) or bm.is_placeholder(a))
        hs,as_=m.get("HomeTeamScore"),m.get("AwayTeamScore"); played=hs is not None and as_ is not None
        def union(f):
            v=[r[f] for r in (rh,ra) if r[f]]; return ",".join(sorted(set(v))) if v else None
        rows.append(dict(
            tournament=year, match_no=m["MatchNumber"], round_no=m["RoundNumber"], stage=stage,
            knockout=stage in KNOCK, group=m["Group"] if m["Group"]!="None" else None,
            venue=m["Location"], host_country=hc, venue_tz=tz,
            kickoff_utc=ko, home=h, away=a, teams_known=teams_known,
            home_iso=rh["iso"], away_iso=ra["iso"], home_score=hs, away_score=as_,
            played=played, winner=m.get("Winner"),
            total_goals=(hs+as_) if played else None, margin=(abs(hs-as_) if played else None),
            draw=(played and hs==as_),
            rel_fx=union("fx"), rel_fxfut=union("fxfut"), rel_etf=union("etf"), rel_index=union("index"),
            usa_playing=("USA" in (h,a)),
            euro_playing=bool(euro & {h,a}),
            gbp_playing=bool({"England","Scotland"} & {h,a}),
            jpy_playing=("Japan" in (h,a)),
            host_team_playing=bool(HOST_TEAMS.get(year,set()) & {h,a}),
            win_pre60_start=ko-timedelta(minutes=60), win_ko=ko,
            win_ht=ko+timedelta(minutes=45), win_2h=ko+timedelta(minutes=60),
            win_ft_nominal=ko+timedelta(minutes=105), win_post60_end=ko+timedelta(minutes=165),
            windows_nominal=True,
        ))
    return pd.DataFrame(rows)

def build_state(df):
    recs=[]
    for _,m in df.iterrows():
        ko,ht,h2,ft=m["win_ko"],m["win_ht"],m["win_2h"],m["win_ft_nominal"]
        t=m["win_pre60_start"]; end=m["win_post60_end"]
        while t<=end:
            recs.append(dict(tournament=m["tournament"], match_no=m["match_no"], minute_utc=t,
                rel_to_ko_min=int((t-ko).total_seconds()//60),
                pre_match=(m["win_pre60_start"]<=t<ko), first_half=(ko<=t<ht),
                halftime=(ht<=t<h2), second_half=(h2<=t<ft), post_match=(ft<=t<=end),
                in_match=(ko<=t<ft), knockout=m["knockout"], stage=m["stage"],
                usa_playing=m["usa_playing"], euro_playing=m["euro_playing"],
                gbp_playing=m["gbp_playing"], jpy_playing=m["jpy_playing"]))
            t+=timedelta(minutes=1)
    return pd.DataFrame(recs)

def main():
    parts=[]
    for y in (2018,2022,2026):
        f=os.path.join(MDIR,f"wc{y}_fixturedownload.json")
        if not os.path.exists(f): continue
        dfy=build_year(y); dfy.to_parquet(os.path.join(MDIR,f"matches_{y}.parquet")); parts.append(dfy)
    allm=pd.concat(parts, ignore_index=True)
    allm.to_parquet(os.path.join(MDIR,"matches_all.parquet"))
    allm.to_csv(os.path.join(MDIR,"matches_all.csv"), index=False)
    st=build_state(allm); st.to_parquet(os.path.join(MDIR,"match_state_all.parquet"))
    print("matches_all:", len(allm), "| by tournament:",
          allm.groupby("tournament").size().to_dict())
    print("played:", allm.groupby("tournament")["played"].sum().to_dict())
    print("euro_playing:", allm.groupby("tournament")["euro_playing"].sum().to_dict(),
          "| usa:", allm.groupby("tournament")["usa_playing"].sum().to_dict(),
          "| gbp:", allm.groupby("tournament")["gbp_playing"].sum().to_dict())
    print("match_state_all:", len(st), "minute-rows")
    return allm

if __name__=="__main__":
    main()
