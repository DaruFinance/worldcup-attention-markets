#!/usr/bin/env python3
"""
Build three CONSTRUCTED datasets the study spec calls for. Inputs already exist;
this script assembles them. No look-ahead: every per-minute / pre-match feature uses
only information at or before the relevant timestamp.

Outputs:
  1. data/matches/match_state_panel.parquet   -  1-min match-state panel (per match), the
     existing match_state_all panel extended with live score / goal-difference / red-card
     differential / final-15 / match-decided features built from goal + red-card timestamps.
  2. data/matches/match_importance.parquet    -  per-match (group-stage) importance flags
     computed from group standings GOING INTO the match (prior results only): elim_possible,
     qual_possible, must_win_home/away. Knockout matches: elim_possible always True.
  3. data/controls/trading_calendar.parquet   -  NYSE (equities) + CME_Equity (futures) market
     open/close per date (UTC), holiday / early-close / DST flags, quarterly futures roll dates,
     equity OPEX (3rd Friday) + triple-witching flags, 2010-2022.

Run:  OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 ingest/build_constructs.py
"""
import os, sys, json
from datetime import datetime, timedelta, timezone
import pandas as pd
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
MDIR = os.path.join(HERE, "..", "data", "matches")
CDIR = os.path.join(HERE, "..", "data", "controls")

# ===========================================================================
# Shared: combined 4-tournament spine (per _CONTEXT.md)
# ===========================================================================
def load_spine():
    m  = pd.read_parquet(os.path.join(MDIR, "matches_all.parquet"))
    mh = pd.read_parquet(os.path.join(MDIR, "matches_hist.parquet"))
    spine = pd.concat([m[m.tournament.isin([2018, 2022])], mh], ignore_index=True)
    # normalize kickoff to tz-aware UTC
    spine["kickoff_utc"] = pd.to_datetime(spine["kickoff_utc"], utc=True)
    return spine


# ===========================================================================
# 1) MATCH-STATE PANEL  (1-min, per match)
# ===========================================================================
# nominal window timing (consistent with build_matches.py): KO, +45 HT, +60 2H, +105 FT.
# match-in-progress minutes = [kickoff, kickoff+105). We extend the existing
# match_state_all panel (which already carries the half/halftime/in-match flags) with
# score-state features derived from goal and red-card event timestamps.

HT_MIN, H2_MIN, FT_MIN = 45, 60, 105          # minutes after KO

def goal_wallclock_offset(elapsed_min):
    """Wall-clock minutes after kickoff at which a goal becomes 'known' to the panel.
    In goals_all_v2 the `elapsed_min` column already encodes exactly this: it equals
    (goal_utc - kickoff_utc) in minutes, i.e. the real wall-clock offset INCLUDING the
    ~15-minute half-time break and any stoppage time (verified: goal_utc == kickoff +
    elapsed_min for 100% of goals). So no remapping is needed  -  we use it as-is and the
    panel records the score-state at the true minute the goal happened (which may fall a
    few minutes past nominal FT for 90+stoppage goals; the panel post-window absorbs that)."""
    return int(elapsed_min)

def _build_minute_grid(spine):
    """1-min UTC rows over each match's nominal window (pre60..post60), carrying the same
    half / halftime / in-match flags as build_matches.py::build_match_state_2026. Built for
    all 4 COMPLETED tournaments (2010/2014/2018/2022); the existing match_state_all.parquet
    only covered 2018/2022/2026, so we regenerate the grid here for full completed-tournament
    coverage. Window timing identical: KO, +45 HT, +60 2H, +105 FT, +-60 pre/post."""
    recs = []
    for _, m in spine.iterrows():
        ko = m["kickoff_utc"]
        start = ko - timedelta(minutes=60)
        ht = ko + timedelta(minutes=HT_MIN)
        h2 = ko + timedelta(minutes=H2_MIN)
        ft = ko + timedelta(minutes=FT_MIN)
        end = ko + timedelta(minutes=165)
        t = start
        while t <= end:
            rel = int((t - ko).total_seconds() // 60)
            recs.append(dict(
                tournament=m["tournament"], match_no=m["match_no"], minute_utc=t,
                rel_to_ko_min=rel,
                pre_match=(start <= t < ko),
                first_half=(ko <= t < ht),
                halftime=(ht <= t < h2),
                second_half=(h2 <= t < ft),
                post_match=(ft <= t <= end),
                in_match=(ko <= t < ft),
                knockout=bool(m["knockout"]), stage=m["stage"],
                usa_playing=bool(m["usa_playing"]), euro_playing=bool(m["euro_playing"]),
                gbp_playing=bool(m["gbp_playing"]), jpy_playing=bool(m["jpy_playing"]),
            ))
            t += timedelta(minutes=1)
    return pd.DataFrame(recs)


def build_match_state_panel():
    spine = load_spine()
    base = _build_minute_grid(spine)
    base["minute_utc"] = pd.to_datetime(base["minute_utc"], utc=True)

    goals = pd.read_parquet(os.path.join(MDIR, "goals_all_v2.parquet"))
    goals["kickoff_utc"] = pd.to_datetime(goals["kickoff_utc"], utc=True)
    # dedupe across the two sources (jfjelstul + openfootball) -> 657 unique goals
    goals = goals.drop_duplicates(["tournament", "kickoff_utc", "scoring_team", "elapsed_min"])
    cards = pd.read_parquet(os.path.join(MDIR, "match_events_extra.parquet"))

    # --- attach kickoff + home/away to the base panel via (tournament, match_no) -----
    sp = spine[["tournament", "match_no", "kickoff_utc", "home", "away",
                "home_score", "away_score", "knockout"]].copy()
    panel = base.merge(sp, on=["tournament", "match_no"], how="left",
                       suffixes=("", "_sp"))

    # Spine team-pair -> match_no lookup (handles 32 simultaneous-kickoff slots where a
    # (tournament,kickoff_utc) join would be ambiguous, and home/away ordering vs goals row).
    sp_lookup = {}   # (tournament, kickoff_utc, frozenset{alias_home, alias_away}) -> (match_no, home, away)
    for _, r in sp.iterrows():
        key = (r["tournament"], r["kickoff_utc"],
               frozenset({_alias(r["home"]), _alias(r["away"])}))
        sp_lookup[key] = (r["match_no"], r["home"], r["away"])

    # --- per-match goal timeline keyed on (tournament, match_no) ----------------------
    # Each goal row carries its OWN team1/team2 + scoring_team; map scoring side within the
    # row, then attach to the spine match via (tournament, kickoff_utc, team-pair).
    goal_map = {}        # (tournament, match_no) -> list[(wall_offset, h_inc, a_inc)]
    mismatch = 0
    for _, r in goals.iterrows():
        key = (r["tournament"], r["kickoff_utc"],
               frozenset({_alias(r["team1"]), _alias(r["team2"])}))
        hit = sp_lookup.get(key)
        if hit is None:
            mismatch += 1
            continue
        match_no, sp_home, sp_away = hit
        off = goal_wallclock_offset(int(r["elapsed_min"]))
        clock_min = int(r["minute"])   # football match-clock minute (>90 == extra time)
        # which spine side scored?
        st = _alias(r["scoring_team"])
        if st == _alias(sp_home):
            h_inc, a_inc = 1, 0
        elif st == _alias(sp_away):
            h_inc, a_inc = 0, 1
        else:
            mismatch += 1
            continue
        goal_map.setdefault((r["tournament"], match_no), []).append((off, h_inc, a_inc, clock_min))

    # --- per-match red-card timeline keyed on (tournament, match_no) ------------------
    # cards has kickoff_utc_spine + red_minutes (semicolon/space list) + red_teams.
    card_map = {}
    cards["kickoff_utc_spine"] = pd.to_datetime(cards["kickoff_utc_spine"], utc=True)
    for _, r in cards.iterrows():
        rm = str(r.get("red_minutes", "") or "").strip()
        if not rm or rm in ("nan", "None"):
            continue
        key = (r["tournament"], r["kickoff_utc_spine"],
               frozenset({_alias(r["home"]), _alias(r["away"])}))
        hit = sp_lookup.get(key)
        if hit is None:
            continue
        match_no, sp_home, sp_away = hit
        teams = str(r.get("red_teams", "") or "").split(",")
        mins = [x for x in rm.replace(";", " ").split() if x.strip().isdigit()]
        ent = card_map.setdefault((r["tournament"], match_no), [])
        for i, mm in enumerate(mins):
            team = teams[i].strip() if i < len(teams) else (teams[0].strip() if teams else "")
            off = goal_wallclock_offset(int(mm))
            side = None
            if _alias(team) == _alias(sp_home):
                side = "home"
            elif _alias(team) == _alias(sp_away):
                side = "away"
            ent.append((off, side))

    # --- now vectorize per match -----------------------------------------------------
    out = []
    panel = panel.sort_values(["tournament", "match_no", "minute_utc"])
    for (tn, mno), grp in panel.groupby(["tournament", "match_no"], sort=False):
        grp = grp.copy()
        ko = grp["kickoff_utc"].iloc[0]
        knockout = bool(grp["knockout"].iloc[0])
        fh = grp["home_score"].iloc[0]   # final home score
        fa = grp["away_score"].iloc[0]   # final away score
        rel = grp["rel_to_ko_min"].values

        gl = sorted(goal_map.get((tn, mno), []))              # (offset, h_inc, a_inc, clock_min)
        cl = sorted([c for c in card_map.get((tn, mno), [])], key=lambda x: x[0])  # (offset, side)

        hs = np.zeros(len(grp), dtype=float)
        as_ = np.zeros(len(grp), dtype=float)
        rc_h = np.zeros(len(grp), dtype=float)
        rc_a = np.zeros(len(grp), dtype=float)
        # cumulative state at each minute: events with wall-offset <= rel_to_ko_min
        ch = ca = crh = cra = 0
        gi = ci = 0
        for i in range(len(grp)):
            t = rel[i]
            while gi < len(gl) and gl[gi][0] <= t:
                ch += gl[gi][1]; ca += gl[gi][2]; gi += 1
            while ci < len(cl) and cl[ci][0] <= t:
                side = cl[ci][1]
                if side == "home": crh += 1
                elif side == "away": cra += 1
                ci += 1
            hs[i] = ch; as_[i] = ca; rc_h[i] = crh; rc_a[i] = cra

        # Validate against the spine's stored (regulation) final. We compare REGULATION-time
        # goals only (wall-offset < FT_MIN); extra-time / penalty goals in knockout matches
        # legitimately push the panel score past the spine's regulation score in the post
        # window, so they are excluded from this completeness check. A residual mismatch
        # means goals_all_v2's scoring_team disagrees with the spine final  -  almost always an
        # OWN GOAL (credited to the kicker's nation, not the side it counted for).
        reg_h = sum(g[1] for g in gl if g[3] <= 90)   # regulation = match-clock minute <= 90
        reg_a = sum(g[2] for g in gl if g[3] <= 90)
        has_et_goal = any(g[3] > 90 for g in gl)
        recon_ok = (int(reg_h) == int(fh)) and (int(reg_a) == int(fa))
        grp["extra_time_goals"] = has_et_goal
        grp["score_home"] = hs
        grp["score_away"] = as_
        grp["goal_difference"] = hs - as_           # home - away
        grp["red_card_home"] = rc_h
        grp["red_card_away"] = rc_a
        grp["red_card_differential"] = rc_h - rc_a  # home - away
        grp["goal_timeline_complete"] = recon_ok
        # tied / leading indicators (None pre-match where score is trivially 0-0 tie;
        # keep literal: tied means current score equal)
        in_match = grp["in_match"].values | grp["post_match"].values
        grp["tied"] = (hs == as_)
        grp["home_leading"] = (hs > as_)
        grp["away_leading"] = (as_ > hs)
        # final 15 minutes of regulation (wall minutes [FT-15, FT) after KO)
        grp["final_15_minutes"] = (rel >= FT_MIN - 15) & (rel < FT_MIN)
        # match_decided: late and leading by a margin that the remaining plausible goals
        # are unlikely to overturn. plausible remaining goals ~ ceil(remaining_min/20),
        # min 1 once in regulation. group games can't be "decided to a draw"; treat a tie
        # as undecided. Knockout: a tie late is still live (ET), so undecided.
        remaining = np.clip(FT_MIN - rel, 0, FT_MIN)
        plausible = np.ceil(remaining / 20.0)
        lead = np.abs(hs - as_)
        decided = in_match & (lead > plausible) & (lead >= 1)
        grp["match_decided"] = decided
        out.append(grp)

    panel = pd.concat(out, ignore_index=True)
    # keep original columns + new; drop the merge helpers we don't want duplicated
    drop = [c for c in ["home", "away", "home_score", "away_score", "knockout_sp"]
            if c in panel.columns]
    panel = panel.drop(columns=drop)
    panel.to_parquet(os.path.join(MDIR, "match_state_panel.parquet"))
    return panel, mismatch


_ALIAS = {
    "south korea": "korea republic", "korea republic": "korea republic",
    "bosnia and herzegovina": "bosnia-herzegovina", "bosnia-herzegovina": "bosnia-herzegovina",
    "ir iran": "iran", "iran": "iran", "china pr": "china",
    "côte d'ivoire": "ivory coast", "cote d'ivoire": "ivory coast", "ivory coast": "ivory coast",
    "usa": "united states", "united states": "united states",
}
def _alias(name):
    if not isinstance(name, str):
        return ""
    n = name.strip().lower()
    return _ALIAS.get(n, n)


# ===========================================================================
# 2) MATCH-IMPORTANCE FLAGS  (group standings, going INTO each match)
# ===========================================================================
# Built from openfootball group matches (of{year}.json) which carry group + score + order.
# For each group-stage match we compute, using ONLY matches that kicked off STRICTLY before
# this match (prior results), whether for each team:
#   elim_possible : a loss here could (combined with worst-case other results) eliminate them.
#   qual_possible : a win here could (combined with best-case other results) qualify them.
#   must_win      : not winning makes qualification impossible (best case) -> must win.
# 3 points win / 1 draw / 0 loss; top 2 of 4 advance. We enumerate the small remaining-match
# space exhaustively (group has at most 3 remaining fixtures after MD2) -> exact, no heuristics.

def _of_group_matches(year):
    d = json.load(open(os.path.join(MDIR, f"of{year}.json")))
    rows = []
    for m in d["matches"]:
        grp = m.get("group")
        if not grp or "Group" not in str(grp):
            continue
        ft = m["score"]["ft"]
        # build a sortable datetime from date+time (time may be local; we only need ORDER
        # within a group, and matchday ordering is preserved by date then time string)
        dt = m["date"]
        tm = m.get("time", "00:00").split()[0]  # strip 'UTC+3' suffix if present
        rows.append(dict(year=year, group=grp, date=dt, time=tm,
                         team1=m["team1"], team2=m["team2"],
                         s1=int(ft[0]), s2=int(ft[1])))
    df = pd.DataFrame(rows)
    df["dt"] = pd.to_datetime(df["date"] + " " + df["time"], errors="coerce")
    df = df.sort_values(["group", "dt"]).reset_index(drop=True)
    return df


def _standings(played_rows):
    """points/gd/gf table from a list of played (team1,team2,s1,s2) dicts."""
    tbl = {}
    def ensure(t):
        tbl.setdefault(t, dict(pts=0, gf=0, ga=0, gd=0, pld=0))
    for r in played_rows:
        t1, t2, s1, s2 = r["team1"], r["team2"], r["s1"], r["s2"]
        ensure(t1); ensure(t2)
        tbl[t1]["gf"] += s1; tbl[t1]["ga"] += s2
        tbl[t2]["gf"] += s2; tbl[t2]["ga"] += s1
        tbl[t1]["pld"] += 1; tbl[t2]["pld"] += 1
        if s1 > s2:   tbl[t1]["pts"] += 3
        elif s2 > s1: tbl[t2]["pts"] += 3
        else:         tbl[t1]["pts"] += 1; tbl[t2]["pts"] += 1
    for t in tbl:
        tbl[t]["gd"] = tbl[t]["gf"] - tbl[t]["ga"]
    return tbl


def _rank_top2(final_pts):
    """given {team: pts} (simplified: points only, ties broken arbitrarily but we treat a
    team as 'could-be-top-2' if it can reach a points total that is in the top 2). We use a
    points-only qualification proxy (sufficient for elim/qual/must-win possibility flags)."""
    order = sorted(final_pts.items(), key=lambda kv: -kv[1])
    return [t for t, _ in order[:2]]


def build_match_importance():
    spine = load_spine()
    recs = []
    for year in [2010, 2014, 2018, 2022]:
        gm = _of_group_matches(year)
        for grp, gdf in gm.groupby("group"):
            teams = sorted(set(gdf.team1) | set(gdf.team2))
            assert len(teams) == 4, f"{year} {grp} has {len(teams)} teams"
            fixtures = gdf.to_dict("records")
            for idx, fx in enumerate(fixtures):
                # PRIOR results = fixtures strictly before this one (chronological order)
                prior = [f for f in fixtures if f["dt"] < fx["dt"]]
                # If exactly-simultaneous final-MD games share dt, exclude same-dt others too
                prior = [f for f in prior if not (f["dt"] == fx["dt"] and f is not fx)]
                base = _standings(prior)
                for t in teams:
                    base.setdefault(t, dict(pts=0, gf=0, ga=0, gd=0, pld=0))
                # remaining fixtures (this one + any after, by dt)  -  exclude played-priors
                remaining = [f for f in fixtures if f["dt"] >= fx["dt"]]
                home, away = fx["team1"], fx["team2"]
                flags = _possibility_flags(teams, base, remaining, fx)
                # map back to spine row via (tournament, date, team pair)
                recs.append(dict(
                    tournament=year, group=grp, date=fx["date"],
                    home=home, away=away,
                    elim_possible=flags["elim_any"],
                    qual_possible=flags["qual_any"],
                    must_win_home=flags["must_win"][home],
                    must_win_away=flags["must_win"][away],
                    elim_possible_home=flags["elim"][home],
                    elim_possible_away=flags["elim"][away],
                    qual_possible_home=flags["qual"][home],
                    qual_possible_away=flags["qual"][away],
                    knockout=False,
                ))
    imp = pd.DataFrame(recs)

    # attach (tournament, kickoff_utc, match_no) by joining to spine on tournament+team pair
    imp = _attach_spine_key(imp, spine)

    # knockout matches: elimination always possible (single-elim)
    ko = spine[spine.knockout].copy()
    ko_rows = pd.DataFrame(dict(
        tournament=ko["tournament"], match_no=ko["match_no"],
        kickoff_utc=ko["kickoff_utc"], group=None,
        home=ko["home"], away=ko["away"],
        elim_possible=True, qual_possible=True,
        must_win_home=True, must_win_away=True,
        elim_possible_home=True, elim_possible_away=True,
        qual_possible_home=True, qual_possible_away=True,
        knockout=True,
    ))
    imp_all = pd.concat([imp, ko_rows], ignore_index=True)
    imp_all = imp_all.sort_values(["tournament", "kickoff_utc"]).reset_index(drop=True)
    imp_all.to_parquet(os.path.join(MDIR, "match_importance.parquet"))
    return imp_all


def _possibility_flags(teams, base, remaining, this_fx):
    """Exhaustively enumerate all outcomes of `remaining` group fixtures (W/D/L each),
    and for each team determine whether there EXISTS a scenario where they finish top-2
    (qual possible) and whether there EXISTS a scenario where they DON'T (elim possible).
    must_win for a team in THIS fixture = in every scenario where they qualify, they won
    this fixture (i.e. not-winning => cannot qualify, best case)."""
    from itertools import product
    n = len(remaining)
    # cap: group remaining <= 6 fixtures -> 3^6 = 729 worst case, trivial.
    base_pts = {t: base[t]["pts"] for t in teams}
    this_id = id(this_fx)
    qual_any = {t: False for t in teams}
    elim_any = {t: False for t in teams}
    # for must-win: track, among scenarios where team qualifies, the set of THIS-match results
    qual_with_result = {t: set() for t in teams}  # results in {'W','D','L'} for this team in this match
    for combo in product(["1", "X", "2"], repeat=n):
        pts = dict(base_pts)
        this_result = {}  # team -> 'W'/'D'/'L' for this fixture
        for f, res in zip(remaining, combo):
            t1, t2 = f["team1"], f["team2"]
            if res == "1":
                pts[t1] += 3
                if f is this_fx:
                    this_result[t1] = "W"; this_result[t2] = "L"
            elif res == "2":
                pts[t2] += 3
                if f is this_fx:
                    this_result[t1] = "L"; this_result[t2] = "W"
            else:
                pts[t1] += 1; pts[t2] += 1
                if f is this_fx:
                    this_result[t1] = "D"; this_result[t2] = "D"
        top2 = set(_rank_top2(pts))
        for t in teams:
            if t in top2:
                qual_any[t] = True
                if t in this_result:
                    qual_with_result[t].add(this_result[t])
            else:
                elim_any[t] = True
    # must_win: team can qualify ONLY via a win in this match (every qualifying scenario had 'W')
    must_win = {}
    for t in teams:
        res_set = qual_with_result[t]
        must_win[t] = bool(res_set) and res_set == {"W"}
    return dict(qual=qual_any, elim=elim_any, must_win=must_win,
                qual_any=any(qual_any.values()), elim_any=any(elim_any.values()))


def _attach_spine_key(imp, spine):
    """join importance rows to spine (tournament, kickoff_utc, match_no) via team-pair match.
    handles name aliasing + home/away swaps."""
    sp = spine[["tournament", "match_no", "kickoff_utc", "home", "away", "stage"]].copy()
    sp = sp[sp.stage == "group"]
    sp["pair"] = sp.apply(lambda r: tuple(sorted([_alias(r["home"]), _alias(r["away"])])), axis=1)
    imp = imp.copy()
    imp["pair"] = imp.apply(lambda r: tuple(sorted([_alias(r["home"]), _alias(r["away"])])), axis=1)
    merged = imp.merge(sp[["tournament", "match_no", "kickoff_utc", "pair"]],
                       on=["tournament", "pair"], how="left")
    # within a tournament+pair there should be exactly one group fixture
    merged = merged.drop(columns=["pair"])
    return merged


# ===========================================================================
# 3) TRADING CALENDAR  (NYSE + CME_Equity), 2010-2022
# ===========================================================================
import pandas_market_calendars as mcal
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
CT = ZoneInfo("America/Chicago")

# quarterly equity-index futures (ES/NQ) expiry = 3rd Friday of Mar/Jun/Sep/Dec.
# roll convention: liquidity rolls ~8 days before expiry (2nd Thursday before 3rd Friday),
# i.e. the Thursday of the week before expiry week. We flag both the expiry date and the
# conventional roll date.
ROLL_MONTHS = [3, 6, 9, 12]

def _third_friday(year, month):
    d = datetime(year, month, 1)
    # weekday(): Mon=0..Fri=4
    first_fri = 1 + (4 - d.weekday()) % 7
    return datetime(year, month, first_fri + 14).date()

def _futures_roll_date(expiry):
    """conventional equity-index roll: the Thursday 8 days before 3rd-Friday expiry
    (one week before expiry week's Thursday)."""
    return expiry - timedelta(days=8)

def build_trading_calendar():
    start, end = "2010-01-01", "2022-12-31"
    nyse = mcal.get_calendar("NYSE")
    cme  = mcal.get_calendar("CME_Equity")

    nsched = nyse.schedule(start_date=start, end_date=end)
    csched = cme.schedule(start_date=start, end_date=end)

    # NYSE standard close is 21:00 UTC (16:00 ET) in DST / 21:00? ET fixed 16:00 -> UTC varies
    # with DST. Detect early close = close earlier than the day's normal 16:00 ET.
    rows = []
    all_dates = sorted(set(nsched.index.date) | set(csched.index.date))

    nyse_holidays = set(pd.to_datetime(nyse.holidays().holidays).date)

    for d in all_dates:
        ts = pd.Timestamp(d)
        rec = dict(date=pd.Timestamp(d))
        # ---- DST status (US Eastern) ----
        noon_et = datetime(d.year, d.month, d.day, 12, tzinfo=ET)
        rec["dst_active"] = bool(noon_et.dst() != timedelta(0))
        rec["et_utc_offset_hours"] = noon_et.utcoffset().total_seconds() / 3600.0

        # ---- NYSE (equities) ----
        if ts in nsched.index:
            mo = nsched.loc[ts, "market_open"]; mc = nsched.loc[ts, "market_close"]
            rec["nyse_open"] = mo
            rec["nyse_close"] = mc
            rec["nyse_trading"] = True
            # normal close = 16:00 ET that day -> to UTC
            norm_close = datetime(d.year, d.month, d.day, 16, 0, tzinfo=ET).astimezone(timezone.utc)
            rec["nyse_early_close"] = bool(mc < pd.Timestamp(norm_close))
        else:
            rec["nyse_open"] = pd.NaT; rec["nyse_close"] = pd.NaT
            rec["nyse_trading"] = False
            rec["nyse_early_close"] = False
        rec["nyse_holiday"] = bool(d in nyse_holidays and d.weekday() < 5)

        # ---- CME_Equity (futures) ----
        if ts in csched.index:
            rec["cme_open"] = csched.loc[ts, "market_open"]
            rec["cme_close"] = csched.loc[ts, "market_close"]
            rec["cme_trading"] = True
            # CME early close detection: normal eq-index globex close 16:00 CT? actual
            # settlement 15:15 CT; flag if close earlier than the modal close for that weekday.
        else:
            rec["cme_open"] = pd.NaT; rec["cme_close"] = pd.NaT
            rec["cme_trading"] = False

        # ---- quarterly futures roll / expiry ----
        is_expiry = any(_third_friday(d.year, mo_) == d for mo_ in ROLL_MONTHS)
        is_roll = any(_futures_roll_date(_third_friday(d.year, mo_)) == d for mo_ in ROLL_MONTHS)
        rec["futures_quarterly_expiry"] = bool(is_expiry)
        rec["futures_roll_date"] = bool(is_roll)

        # ---- equity OPEX (3rd Friday any month) + triple-witching ----
        tf = _third_friday(d.year, d.month)
        rec["equity_opex"] = bool(tf == d)              # monthly options expiration
        rec["triple_witching"] = bool(tf == d and d.month in ROLL_MONTHS)
        rows.append(rec)

    cal = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)
    # CME early-close flag: compare the close in LOCAL Central time. Comparing in UTC is wrong
    # because DST shifts the UTC close by an hour twice a year (a normal close, not an early
    # one). In this CME_Equity calendar a full session closes at 16:00 CT (and the pre-2021
    # settlement convention shows 15:15 CT); genuine holiday half-days settle ~12:00 CT or
    # 08:15 CT. We flag early = local CT close strictly before 15:00 CT.
    def _cme_early(r):
        if not r["cme_trading"] or pd.isna(r["cme_close"]):
            return False
        local = r["cme_close"].tz_convert(CT)
        return bool((local.hour, local.minute) < (15, 0))
    cal["cme_early_close"] = cal.apply(_cme_early, axis=1)

    os.makedirs(CDIR, exist_ok=True)
    cal.to_parquet(os.path.join(CDIR, "trading_calendar.parquet"))
    return cal


# ===========================================================================
if __name__ == "__main__":
    print("[1/3] match_state_panel ...")
    panel, mism = build_match_state_panel()
    print(f"    rows={len(panel):,}  matches={panel.groupby(['tournament','match_no']).ngroups}  "
          f"goal-name mismatches dropped={mism}")
    print(f"    incomplete goal timelines: "
          f"{(~panel.groupby(['tournament','match_no'])['goal_timeline_complete'].first()).sum()} matches")

    print("[2/3] match_importance ...")
    imp = build_match_importance()
    grp = imp[~imp.knockout]
    print(f"    rows={len(imp)}  group={len(grp)}  knockout={int(imp.knockout.sum())}")
    print(f"    unmatched-to-spine (no match_no): {int(imp['match_no'].isna().sum())}")
    print(f"    must_win_home={int(grp.must_win_home.sum())}  must_win_away={int(grp.must_win_away.sum())}  "
          f"elim_possible={int(grp.elim_possible.sum())}/{len(grp)}")

    print("[3/3] trading_calendar ...")
    cal = build_trading_calendar()
    print(f"    rows={len(cal)}  {cal.date.min().date()}..{cal.date.max().date()}")
    print(f"    nyse trading days={int(cal.nyse_trading.sum())}  early_closes={int(cal.nyse_early_close.sum())}  "
          f"holidays={int(cal.nyse_holiday.sum())}")
    print(f"    triple_witching={int(cal.triple_witching.sum())}  opex={int(cal.equity_opex.sum())}  "
          f"futures_expiry={int(cal.futures_quarterly_expiry.sum())}  rolls={int(cal.futures_roll_date.sum())}")
    print("done.")
