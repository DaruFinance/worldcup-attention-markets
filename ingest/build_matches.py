#!/usr/bin/env python3
"""
Build the World Cup match-event spine (2026 first; 2018/2022 loaders stubbed).

Source: fixturedownload.com live JSON feed (scheduled UTC kickoff, venue, group,
live-updating scores + resolved bracket). Re-run to refresh as matches complete and
knockout teams get filled in.

Emits:
  data/matches/matches_2026.parquet / .csv    -  one row per match, normalized
  data/matches/match_state_2026.parquet       -  1-min UTC expansion over each match's
                                               nominal window (pre60 .. post60)

NOTE on timestamps: the feed gives SCHEDULED kickoff only. Halftime / final-whistle /
goal timestamps require a second source (live football API) and are layered on later;
windows here are NOMINAL (KO, +45 HT, +60 2H, +105 FT) and flagged `windows_nominal=True`.
"""
import json, os, sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
MDIR = os.path.join(HERE, "..", "data", "matches")
FEED = os.path.join(MDIR, "wc2026_fixturedownload.json")

# ---- venue -> (host city, host country, IANA tz) --------------------------
VENUE = {
    "Mexico City Stadium":            ("Mexico City", "Mexico", "America/Mexico_City"),
    "Guadalajara Stadium":            ("Guadalajara", "Mexico", "America/Mexico_City"),
    "Monterrey Stadium":              ("Monterrey",   "Mexico", "America/Monterrey"),
    "Toronto Stadium":                ("Toronto",     "Canada", "America/Toronto"),
    "BC Place Vancouver":             ("Vancouver",   "Canada", "America/Vancouver"),
    "Atlanta Stadium":                ("Atlanta",     "USA",    "America/New_York"),
    "Boston Stadium":                 ("Boston",      "USA",    "America/New_York"),
    "Miami Stadium":                  ("Miami",       "USA",    "America/New_York"),
    "New York/New Jersey Stadium":    ("New York",    "USA",    "America/New_York"),
    "Philadelphia Stadium":           ("Philadelphia","USA",    "America/New_York"),
    "Dallas Stadium":                 ("Dallas",      "USA",    "America/Chicago"),
    "Houston Stadium":                ("Houston",     "USA",    "America/Chicago"),
    "Kansas City Stadium":            ("Kansas City", "USA",    "America/Chicago"),
    "Los Angeles Stadium":            ("Los Angeles", "USA",    "America/Los_Angeles"),
    "San Francisco Bay Area Stadium": ("San Francisco","USA",   "America/Los_Angeles"),
    "Seattle Stadium":                ("Seattle",     "USA",    "America/Los_Angeles"),
}

# ---- round number -> stage ------------------------------------------------
STAGE = {1: "group", 2: "group", 3: "group", 4: "R32",
         5: "R16", 6: "QF", 7: "SF", 8: "final_3rd"}
KNOCKOUT = {"R32", "R16", "QF", "SF", "final_3rd"}

EURO_AREA = {"Germany", "France", "Spain", "Netherlands", "Belgium",
             "Austria", "Portugal", "Croatia"}  # euro at 2026

# ---- team -> market relevance --------------------------------------------
# fx        : core FX pair in study universe (relevance for that pair's "domestic team")
# fxfut     : CME FX future root
# etf       : US-listed single-country ETF (expanded universe)
# index     : domestic equity index (expanded universe)
# Teams absent here are treated as foreign / control (no direct tradeable in universe).
TEAM = {
    "USA":          dict(iso="USA", fx=None,      fxfut="ES",  etf="SPY", index="SPX"),
    "Mexico":       dict(iso="MEX", fx="USDMXN",  fxfut="6M",  etf="EWW", index="IPC"),
    "Canada":       dict(iso="CAN", fx="USDCAD",  fxfut="6C",  etf="EWC", index="TSX"),
    "Brazil":       dict(iso="BRA", fx="USDBRL",  fxfut="6L",  etf="EWZ", index="IBOV"),
    "Argentina":    dict(iso="ARG", fx=None,      fxfut=None,  etf="ARGT",index=None),
    "England":      dict(iso="GBR", fx="GBPUSD",  fxfut="6B",  etf="EWU", index="UKX"),
    "Scotland":     dict(iso="GBR", fx="GBPUSD",  fxfut="6B",  etf="EWU", index="UKX"),
    "Germany":      dict(iso="DEU", fx="EURUSD",  fxfut="6E",  etf="EWG", index="DAX"),
    "France":       dict(iso="FRA", fx="EURUSD",  fxfut="6E",  etf="EWQ", index="CAC"),
    "Spain":        dict(iso="ESP", fx="EURUSD",  fxfut="6E",  etf="EWP", index="IBEX"),
    "Netherlands":  dict(iso="NLD", fx="EURUSD",  fxfut="6E",  etf="EWN", index="AEX"),
    "Belgium":      dict(iso="BEL", fx="EURUSD",  fxfut="6E",  etf=None,  index="BEL20"),
    "Austria":      dict(iso="AUT", fx="EURUSD",  fxfut="6E",  etf=None,  index="ATX"),
    "Portugal":     dict(iso="PRT", fx="EURUSD",  fxfut="6E",  etf=None,  index="PSI"),
    "Croatia":      dict(iso="HRV", fx="EURUSD",  fxfut="6E",  etf=None,  index=None),
    "Switzerland":  dict(iso="CHE", fx="USDCHF",  fxfut="6S",  etf="EWL", index="SMI"),
    "Japan":        dict(iso="JPN", fx="USDJPY",  fxfut="6J",  etf="EWJ", index="NKY"),
    "Korea Republic":dict(iso="KOR",fx=None,      fxfut=None,  etf="EWY", index="KOSPI"),
    "Australia":    dict(iso="AUS", fx="AUDUSD",  fxfut="6A",  etf="EWA", index="AS51"),
    "Sweden":       dict(iso="SWE", fx=None,      fxfut=None,  etf="EWD", index="OMX"),
    "Norway":       dict(iso="NOR", fx=None,      fxfut=None,  etf="NORW",index="OBX"),
    "Türkiye":      dict(iso="TUR", fx=None,      fxfut=None,  etf="TUR", index="XU100"),
    "South Africa": dict(iso="ZAF", fx="USDZAR",  fxfut=None,  etf="EZA", index="JALSH"),
    "Saudi Arabia": dict(iso="SAU", fx=None,      fxfut=None,  etf="KSA", index="SASEIDX"),
    "Qatar":        dict(iso="QAT", fx=None,      fxfut=None,  etf="QAT", index=None),
    "Egypt":        dict(iso="EGY", fx=None,      fxfut=None,  etf="EGPT",index=None),
    "Colombia":     dict(iso="COL", fx=None,      fxfut=None,  etf="GXG", index=None),
}

def relevance(team):
    return TEAM.get(team, dict(iso=None, fx=None, fxfut=None, etf=None, index=None))

def is_placeholder(t):
    if not t: return True
    tl = t.lower()
    return ("announce" in tl) or any(c.isdigit() for c in t)

def build_2026():
    feed = json.load(open(FEED))
    rows = []
    for m in feed:
        ko = datetime.strptime(m["DateUtc"], "%Y-%m-%d %H:%M:%SZ").replace(tzinfo=timezone.utc)
        rn = m["RoundNumber"]
        stage = STAGE.get(rn)
        city, host_country, tz = VENUE.get(m["Location"], (None, None, None))
        ko_local = ko.astimezone(ZoneInfo(tz)) if tz else None
        h, a = m["HomeTeam"], m["AwayTeam"]
        rh, ra = relevance(h), relevance(a)
        teams_known = not (is_placeholder(h) or is_placeholder(a))
        hs, as_ = m.get("HomeTeamScore"), m.get("AwayTeamScore")
        played = hs is not None and as_ is not None

        # market-relevance indicators (union over the two teams)
        def union(field):
            vals = [r[field] for r in (rh, ra) if r[field]]
            return ",".join(sorted(set(vals))) if vals else None
        rows.append(dict(
            tournament=2026, match_no=m["MatchNumber"], round_no=rn, stage=stage,
            knockout=stage in KNOCKOUT,
            group=m["Group"] if m["Group"] != "None" else None,
            venue=m["Location"], host_city=city, host_country=host_country, venue_tz=tz,
            kickoff_utc=ko, kickoff_local=ko_local.isoformat() if ko_local else None,
            home=h, away=a, teams_known=teams_known,
            home_iso=rh["iso"], away_iso=ra["iso"],
            home_score=hs, away_score=as_, played=played,
            winner=m.get("Winner"),
            total_goals=(hs + as_) if played else None,
            margin=(abs(hs - as_) if played else None),
            draw=(played and hs == as_),
            # market relevance
            rel_fx=union("fx"), rel_fxfut=union("fxfut"),
            rel_etf=union("etf"), rel_index=union("index"),
            usa_playing=("USA" in (h, a)),
            euro_playing=bool(EURO_AREA & {h, a}),
            gbp_playing=bool({"England", "Scotland"} & {h, a}),
            jpy_playing=("Japan" in (h, a)),
            host_team_playing=(rh["iso"] in ("USA", "MEX", "CAN")) or (ra["iso"] in ("USA", "MEX", "CAN")),
            # nominal windows (UTC)  -  refined later with actual event timestamps
            win_pre60_start=ko - timedelta(minutes=60),
            win_ko=ko,
            win_ht=ko + timedelta(minutes=45),
            win_2h=ko + timedelta(minutes=60),
            win_ft_nominal=ko + timedelta(minutes=105),
            win_post60_end=ko + timedelta(minutes=165),
            windows_nominal=True,
        ))
    df = pd.DataFrame(rows).sort_values("match_no").reset_index(drop=True)
    os.makedirs(MDIR, exist_ok=True)
    df.to_parquet(os.path.join(MDIR, "matches_2026.parquet"))
    df.to_csv(os.path.join(MDIR, "matches_2026.csv"), index=False)
    return df

def build_match_state_2026(df):
    """1-min UTC rows over each match nominal window; in-match flags + match-state stub."""
    recs = []
    for _, m in df.iterrows():
        start = m["win_pre60_start"]; end = m["win_post60_end"]
        t = start
        ko, ht, h2, ft = m["win_ko"], m["win_ht"], m["win_2h"], m["win_ft_nominal"]
        while t <= end:
            in_match = ko <= t < ft
            recs.append(dict(
                tournament=2026, match_no=m["match_no"], minute_utc=t,
                rel_to_ko_min=int((t - ko).total_seconds() // 60),
                pre_match=(start <= t < ko),
                first_half=(ko <= t < ht),
                halftime=(ht <= t < h2),
                second_half=(h2 <= t < ft),
                post_match=(ft <= t <= end),
                in_match=in_match,
                knockout=m["knockout"], stage=m["stage"],
                usa_playing=m["usa_playing"], euro_playing=m["euro_playing"],
                gbp_playing=m["gbp_playing"], jpy_playing=m["jpy_playing"],
            ))
            t += timedelta(minutes=1)
    ms = pd.DataFrame(recs)
    ms.to_parquet(os.path.join(MDIR, "match_state_2026.parquet"))
    return ms

if __name__ == "__main__":
    df = build_2026()
    ms = build_match_state_2026(df)
    print(f"matches_2026: {len(df)} rows | played={int(df['played'].sum())} | "
          f"knockout={int(df['knockout'].sum())} | teams_known={int(df['teams_known'].sum())}")
    print(f"match_state_2026: {len(ms)} minute-rows over {df['match_no'].nunique()} matches")
    print("\nrelevance coverage (matches with a core-universe domestic team):")
    print("  USA  :", int(df['usa_playing'].sum()),
          " EUR  :", int(df['euro_playing'].sum()),
          " GBP  :", int(df['gbp_playing'].sum()),
          " JPY  :", int(df['jpy_playing'].sum()))
    print("\nfirst 3 matches:")
    cols = ["match_no","stage","home","away","kickoff_utc","host_country","rel_fx","home_score","away_score"]
    print(df[cols].head(3).to_string(index=False))
