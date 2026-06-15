#!/usr/bin/env python3
"""
build_elo.py  -  Match-strength / importance / intensity enrichment for the WC spine.

Outputs one row per World Cup match (2010, 2014, 2018, 2022) with:
  - home_strength / away_strength : pre-match World Football Elo (computed from full
    international match history 1872->match date, standard eloratings.net formula).
  - strength_diff = |home_strength - away_strength|
  - favourite     = team (home/away) with higher pre-match Elo
  - closeness     = -strength_diff  (larger == closer, i.e. more uncertain match)
  - red_cards     : NOT AVAILABLE in any on-disk source (openfootball carries no cards) -> NaN
  - extra_time    : bool, match went to extra time (openfootball score.et present)
  - penalties     : bool, match decided on penalty shootout (openfootball score.p present)

Sources (all free, no key):
  - Elo input: martj42/international_results results.csv (raw GitHub) -> data/raw_elo/results.csv
  - ET/pen   : data/matches/of{2010,2014,2018,2022}.json (openfootball, already on disk)
  - spine    : matches_all.parquet (2018,2022) + matches_hist.parquet (2010,2014)

Elo is COMPUTED, not looked up, so the rating used for a WC match is strictly the
state BEFORE that match (no look-ahead): the World Football Elo recursion is replayed
chronologically over every international fixture, and we snapshot each team's rating at
the instant its WC match is about to be played.
"""
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
MDIR = ROOT / "data" / "matches"
RAW = ROOT / "data" / "raw_elo" / "results.csv"
OUT = MDIR / "elo_importance.parquet"

# ----------------------------------------------------------------------------
# Team-name aliases: map every source's spelling -> the spine's canonical name.
# ----------------------------------------------------------------------------
# martj42 results.csv spelling  ->  spine spelling
ELO_ALIAS = {
    "United States": "USA",
    "South Korea": "Korea Republic",
    "Ivory Coast": "Côte d'Ivoire",
    "Bosnia and Herzegovina": "Bosnia-Herzegovina",
}


def canon_elo(name: str) -> str:
    return ELO_ALIAS.get(name, name)


# Spine / openfootball spellings -> canonical (matches the _CONTEXT.md convention,
# which uses "Korea Republic"). matches_hist (2010/2014) writes "South Korea" while
# matches_all (2018/2022) writes "Korea Republic"; openfootball writes "South Korea".
# Normalise everything to one canonical name so the undirected-pair join is exact.
SPINE_ALIAS = {
    "South Korea": "Korea Republic",
}


def canon_team(name: str) -> str:
    return SPINE_ALIAS.get(name, name)


# ----------------------------------------------------------------------------
# World Football Elo (eloratings.net) recursion.
#   R'_A = R_A + K * G * (W - W_e)
#   W_e  = 1 / (10^(-dr/400) + 1),  dr = R_A - R_B + 100*home_advantage
#   K    : tournament weight (60 World Cup; smaller for lesser comps)
#   G    : goal-difference multiplier (1; 1.5 for +2; (11+gd)/8 for +3 and up)
# ----------------------------------------------------------------------------
TOURN_K = {
    "FIFA World Cup": 60,
    "FIFA World Cup qualification": 40,
    "Confederations Cup": 40,
    "UEFA Euro": 50,
    "Copa América": 50,
    "African Cup of Nations": 50,
    "AFC Asian Cup": 50,
    "Gold Cup": 50,
    "UEFA Nations League": 40,
    "Friendly": 20,
}
DEFAULT_K = 30  # other continental / qualification competitions
HOME_ADV = 100  # Elo points for playing at home (0 when neutral)
INIT_RATING = 1500.0


def goal_multiplier(gd: int) -> float:
    gd = abs(gd)
    if gd <= 1:
        return 1.0
    if gd == 2:
        return 1.5
    return (11 + gd) / 8.0


def k_for(tournament: str) -> float:
    return TOURN_K.get(tournament, DEFAULT_K)


def compute_elo_snapshots(results: pd.DataFrame) -> pd.DataFrame:
    """Replay the Elo recursion chronologically. Return, for every FIFA World Cup
    row in `results`, the PRE-match rating of both teams (canonical names)."""
    results = results.sort_values("date", kind="stable").reset_index(drop=True)
    ratings: dict[str, float] = {}
    snaps = []
    for row in results.itertuples(index=False):
        h, a = row.home_team, row.away_team
        rh = ratings.get(h, INIT_RATING)
        ra = ratings.get(a, INIT_RATING)
        neutral = bool(row.neutral)
        # snapshot WC matches BEFORE updating
        if row.tournament == "FIFA World Cup":
            snaps.append(
                {
                    "date": row.date,
                    "home_raw": h,
                    "away_raw": a,
                    "home_elo": rh,
                    "away_elo": ra,
                }
            )
        # skip rows with missing scores for the update
        if pd.isna(row.home_score) or pd.isna(row.away_score):
            continue
        hs, as_ = int(row.home_score), int(row.away_score)
        ha = 0 if neutral else HOME_ADV
        dr = (rh + ha) - ra
        we_h = 1.0 / (10 ** (-dr / 400.0) + 1.0)
        if hs > as_:
            w_h = 1.0
        elif hs < as_:
            w_h = 0.0
        else:
            w_h = 0.5
        k = k_for(row.tournament)
        g = goal_multiplier(hs - as_)
        delta = k * g * (w_h - we_h)
        ratings[h] = rh + delta
        ratings[a] = ra - delta
    snap = pd.DataFrame(snaps)
    # canon_elo: CSV spelling -> spine spelling; canon_team: -> final canonical
    snap["home"] = snap["home_raw"].map(canon_elo).map(canon_team)
    snap["away"] = snap["away_raw"].map(canon_elo).map(canon_team)
    snap["date"] = pd.to_datetime(snap["date"]).dt.date
    return snap


# ----------------------------------------------------------------------------
# Extra-time / penalty flags from openfootball.
# ----------------------------------------------------------------------------
def load_of_flags() -> pd.DataFrame:
    rows = []
    for y in (2010, 2014, 2018, 2022):
        d = json.load(open(MDIR / f"of{y}.json"))
        for m in d["matches"]:
            sc = m.get("score", {}) or {}
            rows.append(
                {
                    "tournament": y,
                    "of_date": pd.to_datetime(m["date"]).date(),
                    "t1": canon_team(m["team1"]),
                    "t2": canon_team(m["team2"]),
                    "extra_time": "et" in sc,
                    "penalties": "p" in sc,
                }
            )
    of = pd.DataFrame(rows)
    of["pair"] = of.apply(lambda r: frozenset((r.t1, r.t2)), axis=1)
    return of


# ----------------------------------------------------------------------------
# Build the spine and join.
# ----------------------------------------------------------------------------
def build_spine() -> pd.DataFrame:
    ma = pd.read_parquet(MDIR / "matches_all.parquet")
    mh = pd.read_parquet(MDIR / "matches_hist.parquet")
    cols = ["tournament", "kickoff_utc", "home", "away", "stage", "knockout"]
    spine = pd.concat([ma[ma.tournament.isin([2018, 2022])][cols], mh[cols]], ignore_index=True)
    spine["tournament"] = spine["tournament"].astype(int)
    spine["home"] = spine["home"].map(canon_team)
    spine["away"] = spine["away"].map(canon_team)
    spine["date"] = pd.to_datetime(spine["kickoff_utc"]).dt.tz_convert("UTC").dt.date
    spine["pair"] = spine.apply(lambda r: frozenset((r.home, r.away)), axis=1)
    return spine


def join_elo(spine: pd.DataFrame, snap: pd.DataFrame) -> pd.DataFrame:
    """Attach pre-match Elo by tournament-year + undirected team pair.
    A WC undirected pair can recur within one tournament (e.g. group + 3rd place),
    so we match the pair and, when ambiguous, pick the snapshot with the nearest date.
    """
    snap = snap.copy()
    snap["pair"] = snap.apply(lambda r: frozenset((r.home, r.away)), axis=1)
    snap["year"] = pd.to_datetime(snap["date"]).map(lambda d: d.year)

    home_elo = np.full(len(spine), np.nan)
    away_elo = np.full(len(spine), np.nan)
    for i, sr in enumerate(spine.itertuples(index=False)):
        cand = snap[(snap.year == sr.tournament) & (snap.pair == sr.pair)]
        if cand.empty:
            continue
        if len(cand) > 1:
            # nearest by date
            dd = pd.Series([abs((c - sr.date).days) for c in cand.date], index=cand.index)
            cand = cand.loc[[dd.idxmin()]]
        c = cand.iloc[0]
        # orient: snapshot stores home_elo for c.home, away_elo for c.away
        if c.home == sr.home:
            home_elo[i] = c.home_elo
            away_elo[i] = c.away_elo
        else:
            home_elo[i] = c.away_elo
            away_elo[i] = c.home_elo
    spine = spine.copy()
    spine["home_strength"] = home_elo
    spine["away_strength"] = away_elo
    return spine


def main() -> None:
    print(f"[build_elo] reading Elo input {RAW}")
    res = pd.read_csv(RAW)
    # canonicalise tournament-history team names is NOT needed for the recursion
    # (ratings keyed by raw name; only the WC snapshots get canonicalised).
    snap = compute_elo_snapshots(res)
    print(f"[build_elo] WC pre-match Elo snapshots: {len(snap)}")

    spine = build_spine()
    print(f"[build_elo] spine matches: {len(spine)} "
          f"({spine.groupby('tournament').size().to_dict()})")

    df = join_elo(spine, snap)
    of = load_of_flags()

    # join ET/pen by tournament + pair (+ date tiebreak on recurring pairs)
    et = np.zeros(len(df), dtype=bool)
    pen = np.zeros(len(df), dtype=bool)
    of_hit = np.zeros(len(df), dtype=bool)
    for i, sr in enumerate(df.itertuples(index=False)):
        cand = of[(of.tournament == sr.tournament) & (of.pair == sr.pair)]
        if cand.empty:
            continue
        if len(cand) > 1:
            dd = pd.Series([abs((c - sr.date).days) for c in cand.of_date], index=cand.index)
            cand = cand.loc[[dd.idxmin()]]
        c = cand.iloc[0]
        et[i] = bool(c.extra_time)
        pen[i] = bool(c.penalties)
        of_hit[i] = True
    df["extra_time"] = et
    df["penalties"] = pen

    # derived strength metrics
    df["strength_diff"] = (df["home_strength"] - df["away_strength"]).abs()
    df["closeness"] = -df["strength_diff"]  # larger == closer / more uncertain
    df["favourite"] = np.where(
        df["home_strength"].isna(),
        np.nan,
        np.where(df["home_strength"] >= df["away_strength"], df["home"], df["away"]),
    )
    df["red_cards"] = np.nan  # not available in any on-disk source

    out = df[
        [
            "tournament",
            "date",
            "home",
            "away",
            "stage",
            "knockout",
            "home_strength",
            "away_strength",
            "strength_diff",
            "closeness",
            "favourite",
            "red_cards",
            "extra_time",
            "penalties",
        ]
    ].copy()
    out["date"] = pd.to_datetime(out["date"])
    out.to_parquet(OUT, index=False)

    # coverage report
    n = len(out)
    elo_cov = out["home_strength"].notna().sum()
    of_cov = int(of_hit.sum())
    print(f"[build_elo] wrote {OUT}  rows={n}")
    print(f"[build_elo] Elo coverage: {elo_cov}/{n}  "
          f"missing pairs: "
          f"{out[out.home_strength.isna()][['tournament','home','away']].values.tolist()}")
    print(f"[build_elo] ET/pen coverage (openfootball matched): {of_cov}/{n}")
    print(f"[build_elo] extra_time matches: {int(out.extra_time.sum())}  "
          f"penalty matches: {int(out.penalties.sum())}")
    print(out.groupby("tournament")[["extra_time", "penalties"]].sum())


if __name__ == "__main__":
    main()
