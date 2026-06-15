#!/usr/bin/env python3
"""
Collect three free match-event datasets for the completed World Cups (2010,2014,2018,2022):

  1. RED CARDS (sending-offs) per match, with minute + team, from the Fjelstul World Cup
     Database (jfjelstul/worldcup, public domain CDDL/MIT, no key). `bookings.csv` flags
     red_card / second_yellow_card / sending_off + minute_regulation/stoppage + team.
     "Red card" for an attention/event study = any *dismissal* (straight red OR second
     yellow), i.e. sending_off==1, since a player going off is the observable shock.

  2. KICKOFF VERIFICATION: reconstruct kickoff_utc from jfjelstul's *local* match_time +
     a venue->timezone map (multi-tz for 2014 Brazil / 2018 Russia, single-tz for
     2010 SA / 2022 Qatar), then diff against the spine's kickoff_utc and flag mismatches.
     (Halftime / actual-whistle are not free at scale; we only refine kickoff.)

  3. 2014 + 2010 GOAL TIMESTAMPS:
       - 2014: openfootball of2014.json HAS goals (171); built with build_goals.py logic.
       - 2010: openfootball has NO goals -> use jfjelstul goals.csv (145 goals, with minute).
     Goal-clock -> UTC instant via the same elapsed-minute model as build_goals.py.

Outputs (NEVER overwrites goals_all.parquet):
  data/matches/match_events_extra.parquet   (per-match red_cards + refined-kickoff diff)
  data/matches/goals_2014.parquet           (2014 goal-event timestamps)
  data/matches/goals_2010.parquet           (2010 goal-event timestamps, from jfjelstul)
  data/matches/goals_all_v2.parquet         (combined 2010+2014+2018+2022 goal events)

Source CSVs are cached under data/external/jfjelstul/{bookings,goals,matches}.csv.
"""
import os, json, re, sys
from datetime import timedelta
import pandas as pd

MDIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "matches")
EXT  = os.path.join(MDIR, "..", "external", "jfjelstul")
YEARS = (2010, 2014, 2018, 2022)

JFJ_RAW = "https://raw.githubusercontent.com/jfjelstul/worldcup/master/data-csv/{}.csv"

# --- team-name normalization (spine <-> openfootball <-> jfjelstul) ---
_ALIAS = {
    "south korea": "korearepublic", "korea republic": "korearepublic",
    "iran": "iran", "ir iran": "iran",
    "czech republic": "czechia",
    "turkey": "turkiye", "türkiye": "turkiye",
    "ivory coast": "cotedivoire", "côte d'ivoire": "cotedivoire", "côte d'ivoire": "cotedivoire",
    "usa": "unitedstates", "united states": "unitedstates",
    "china pr": "china",
    "republic of ireland": "ireland",
    "bosnia and herzegovina": "bosniaherzegovina", "bosnia-herzegovina": "bosniaherzegovina",
}
def norm(t):
    t = str(t).lower().strip()
    if t in _ALIAS:
        return _ALIAS[t]
    return re.sub(r"[^a-z]", "", t)

# --- venue timezone (UTC offset, hours) for multi-tz tournaments; June, no DST ---
TZ_2014 = {  # Brazil; default UTC-3, Amazon venues UTC-4
    "Cuiabá": -4, "Manaus": -4,
}
TZ_2018 = {  # Russia; default UTC+3
    "Kaliningrad": 2, "Samara": 4, "Yekaterinburg": 5,
}
def venue_offset(year, city):
    if year == 2010: return 2          # SAST, single tz
    if year == 2022: return 3          # AST Qatar, single tz
    if year == 2014: return TZ_2014.get(city, -3)
    if year == 2018: return TZ_2018.get(city, 3)
    return None


def download():
    os.makedirs(EXT, exist_ok=True)
    import urllib.request
    for t in ("bookings", "goals", "matches"):
        path = os.path.join(EXT, f"{t}.csv")
        if os.path.exists(path) and os.path.getsize(path) > 1000:
            continue
        url = JFJ_RAW.format(t)
        print(f"[download] {url}")
        urllib.request.urlretrieve(url, path)
    return {t: pd.read_csv(os.path.join(EXT, f"{t}.csv")) for t in ("bookings", "goals", "matches")}


def load_spine():
    """4-tournament spine: 2010/2014 from matches_hist, 2018/2022 from matches_all."""
    hist = pd.read_parquet(os.path.join(MDIR, "matches_hist.parquet"))
    allm = pd.read_parquet(os.path.join(MDIR, "matches_all.parquet"))
    allm = allm[allm.tournament.isin([2018, 2022])]
    cols = ["tournament", "kickoff_utc", "home", "away", "stage"]
    spine = pd.concat([hist[cols], allm[cols]], ignore_index=True)
    spine["ko"] = pd.to_datetime(spine["kickoff_utc"], utc=True)
    spine["d"] = spine["ko"].dt.strftime("%Y-%m-%d")
    return spine


def spine_lut(spine):
    """(year, date, frozenset{teams}) -> kickoff_utc, with +-1 day drift fallback keys."""
    lut = {}
    for _, r in spine.iterrows():
        teams = frozenset({norm(r["home"]), norm(r["away"])})
        lut[(int(r["tournament"]), r["d"], teams)] = r["ko"]
    return lut


def lookup_ko(lut, year, date, teams):
    ko = lut.get((year, date, teams))
    if ko is not None:
        return ko
    for dd in (-1, 1):
        d2 = (pd.Timestamp(date) + timedelta(days=dd)).strftime("%Y-%m-%d")
        ko = lut.get((year, d2, teams))
        if ko is not None:
            return ko
    return None


def elapsed_minutes(minute, offset):
    """match-clock minute (+ stoppage offset) -> minutes since kickoff (build_goals.py model)."""
    e = minute + (offset or 0)
    if minute > 45: e += 15      # halftime break
    if minute > 90: e += 5       # break before extra time
    return e


# ---------------------------------------------------------------- 1+2: per-match events
def build_match_events(book, matches, spine, lut):
    book = book.copy(); matches = matches.copy()
    for df in (book, matches):
        df["yr"] = df["tournament_name"].str.extract(r"(\d{4})").astype(int)
    book = book[book.yr.isin(YEARS)]
    matches = matches[matches.yr.isin(YEARS)]

    # per-match dismissal aggregates
    book["dismissal_min"] = book["minute_regulation"].fillna(0).astype(int)
    rows = []
    unmatched = 0
    for _, r in matches.iterrows():
        yr = int(r["yr"])
        teams = frozenset({norm(r["home_team_name"]), norm(r["away_team_name"])})
        ko = lookup_ko(lut, yr, r["match_date"], teams)
        if ko is None:
            unmatched += 1
        # bookings for this match (by jfjelstul match_id)
        mb = book[book.match_id == r["match_id"]]
        reds = mb[mb.sending_off == 1]
        # reconstruct kickoff_utc from local time + venue tz
        off = venue_offset(yr, r["city_name"])
        ko_recon = None
        if off is not None and isinstance(r["match_time"], str) and ":" in r["match_time"]:
            hh, mm = (int(x) for x in r["match_time"].split(":"))
            local = pd.Timestamp(f"{r['match_date']} {hh:02d}:{mm:02d}:00")
            ko_recon = (local - pd.Timedelta(hours=off)).tz_localize("UTC")
        ko_diff_min = None
        if ko is not None and ko_recon is not None:
            ko_diff_min = int(round((ko - ko_recon).total_seconds() / 60.0))
        rows.append(dict(
            tournament=yr,
            match_date=r["match_date"],
            home=r["home_team_name"], away=r["away_team_name"],
            city=r["city_name"], stadium=r["stadium_name"],
            kickoff_utc_spine=ko,
            kickoff_local=r["match_time"], venue_utc_offset=off,
            kickoff_utc_recon=ko_recon,
            kickoff_diff_min=ko_diff_min,
            red_cards=int(len(reds)),                  # all dismissals (red + 2nd yellow)
            straight_reds=int((mb.red_card == 1).sum()),
            second_yellows=int((mb.second_yellow_card == 1).sum()),
            red_minutes=";".join(str(int(m)) for m in sorted(reds["dismissal_min"])),
            red_teams=";".join(sorted(reds["team_name"].astype(str))),
            n_bookings=int(len(mb)),                   # yellows + reds (total cards)
        ))
    ev = pd.DataFrame(rows).sort_values(["tournament", "match_date"]).reset_index(drop=True)
    return ev, unmatched


# ---------------------------------------------------------------- 3a: 2014 goals (openfootball)
def build_goals_2014(lut):
    p = os.path.join(MDIR, "of2014.json")
    d = json.load(open(p))
    rows = []; unmatched = 0
    for mt in d["matches"]:
        teams = frozenset({norm(mt["team1"]), norm(mt["team2"])})
        ko = lookup_ko(lut, 2014, mt["date"], teams)
        if ko is None:
            unmatched += 1; continue
        for side, tk in (("goals1", "team1"), ("goals2", "team2")):
            for g in mt.get(side, []):
                minute = g.get("minute"); off = g.get("offset", 0)
                if minute is None: continue
                el = elapsed_minutes(minute, off)
                rows.append(dict(
                    tournament=2014, date=mt["date"], team1=mt["team1"], team2=mt["team2"],
                    kickoff_utc=ko, scoring_team=mt[tk],
                    minute=minute, offset=off, elapsed_min=el,
                    goal_utc=ko + timedelta(minutes=el),
                    ground=mt.get("ground"), source="openfootball"))
    df = pd.DataFrame(rows).sort_values("goal_utc").reset_index(drop=True)
    return df, unmatched


# ---------------------------------------------------------------- 3b: 2010 goals (jfjelstul)
def build_goals_2010(goals, matches, lut):
    g = goals.copy()
    g["yr"] = g["tournament_name"].str.extract(r"(\d{4})").astype(int)
    g = g[g.yr == 2010]
    # goals.csv home_team/away_team are 0/1 flags, not names -> join real names via match_id
    mn = matches.set_index("match_id")[["home_team_name", "away_team_name", "stadium_name"]]
    rows = []; unmatched = 0
    for _, r in g.iterrows():
        mm = mn.loc[r["match_id"]]
        teams = frozenset({norm(mm["home_team_name"]), norm(mm["away_team_name"])})
        ko = lookup_ko(lut, 2010, r["match_date"], teams)
        if ko is None:
            unmatched += 1; continue
        minute = int(r["minute_regulation"])
        off = int(r["minute_stoppage"]) if pd.notna(r["minute_stoppage"]) else 0
        el = elapsed_minutes(minute, off)
        rows.append(dict(
            tournament=2010, date=r["match_date"],
            team1=mm["home_team_name"], team2=mm["away_team_name"],
            kickoff_utc=ko, scoring_team=r["player_team_name"],
            minute=minute, offset=off, elapsed_min=el,
            goal_utc=ko + timedelta(minutes=el),
            ground=mm["stadium_name"], source="jfjelstul"))
    df = pd.DataFrame(rows).sort_values("goal_utc").reset_index(drop=True)
    return df, unmatched


def main():
    data = download()
    spine = load_spine()
    lut = spine_lut(spine)

    # 1+2 per-match events
    ev, ev_unm = build_match_events(data["bookings"], data["matches"], spine, lut)
    ev.to_parquet(os.path.join(MDIR, "match_events_extra.parquet"))
    print(f"\n[match_events_extra] {len(ev)} matches | unmatched-to-spine={ev_unm}")
    rc = ev.groupby("tournament")["red_cards"].sum().to_dict()
    print(f"  red cards (dismissals) per tournament: {rc}  total={int(ev.red_cards.sum())}")
    bk = ev.groupby("tournament")["n_bookings"].sum().to_dict()
    print(f"  total bookings (cards) per tournament: {bk}")
    diffs = ev.dropna(subset=["kickoff_diff_min"])
    big = diffs[diffs.kickoff_diff_min.abs() > 5]
    print(f"  kickoff recon vs spine: {len(diffs)} comparable; "
          f"|diff|<=5min for {int((diffs.kickoff_diff_min.abs() <= 5).sum())}; "
          f"flagged (>5min): {len(big)}")
    if len(big):
        print(big[["tournament", "match_date", "home", "away", "city",
                   "kickoff_utc_spine", "kickoff_utc_recon", "kickoff_diff_min"]].to_string(index=False))

    # 3a 2014 goals
    g14, u14 = build_goals_2014(lut)
    g14.to_parquet(os.path.join(MDIR, "goals_2014.parquet"))
    print(f"\n[goals_2014] {len(g14)} goals | unmatched matches={u14}")

    # 3b 2010 goals
    mm = data["matches"].copy(); mm["yr"] = mm["tournament_name"].str.extract(r"(\d{4})").astype(int)
    g10, u10 = build_goals_2010(data["goals"], mm[mm.yr == 2010], lut)
    g10.to_parquet(os.path.join(MDIR, "goals_2010.parquet"))
    print(f"[goals_2010] {len(g10)} goals | unmatched matches={u10}")

    # combined v2 (do NOT overwrite goals_all.parquet)
    base = pd.read_parquet(os.path.join(MDIR, "goals_all.parquet"))  # 2018+2022
    base = base.copy()
    if "source" not in base.columns:
        base["source"] = "openfootball"
    cols = ["tournament", "date", "team1", "team2", "kickoff_utc", "scoring_team",
            "minute", "offset", "elapsed_min", "goal_utc", "ground", "source"]
    combined = pd.concat([g10[cols], g14[cols], base.reindex(columns=cols)],
                         ignore_index=True).sort_values("goal_utc").reset_index(drop=True)
    combined.to_parquet(os.path.join(MDIR, "goals_all_v2.parquet"))
    gc = combined.groupby("tournament").size().to_dict()
    print(f"\n[goals_all_v2] {len(combined)} goals | per tournament: {gc}")


if __name__ == "__main__":
    main()
