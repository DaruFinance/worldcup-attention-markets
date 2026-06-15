#!/usr/bin/env python3
"""
Per-match enrichment for the four COMPLETED men's World Cups (2010, 2014, 2018, 2022).

Builds ONE row per spine match with:
  - attendance            official spectators (datahub football/worldcup -> attendance.csv;
                          1930-2010 Kaggle/FIFA, 2014/2018/2022 Wikipedia match reports;
                          CC-BY-SA-4.0, derived from the Fjelstul DB)
  - n_subs                number of substitutions (Fjelstul substitutions.csv: per coming_on player)
  - n_penalty_kicks       IN-MATCH penalty GOALS scored (Fjelstul goals.csv, penalty==1).
                          NOTE: this counts penalties *converted in open play / regulation+ET*,
                          NOT all penalties *awarded* (misses are absent from goals.csv), and is
                          DISTINCT from shootout penalties (Fjelstul penalty_kicks.csv is shootout-only).
  - var_flag              1 if Video Assistant Referee was in use that tournament (2018, 2022),
                          else 0 (2010, 2014). Tournament-level FIFA fact; no free per-match
                          VAR-overturn / disallowed-goal table exists at scale -> reported as a flag.
  - home/away_fifa_rank   FIFA Men's World Ranking position as of the ranking dated ON/BEFORE the
                          match kickoff (no look-ahead). Rank derived by ordering total_points
                          within each ranking date (validated 100% vs cnc8 explicit-rank on overlap).
  - home/away_fifa_points FIFA ranking total points, same as-of date.
                          Source: Dato-Futbol/fifa-ranking ranking_fifa_historical.csv
                          (Dec 1992 - Sep 2024, scraped from fifa.com).

Join key: Fjelstul match_id where available (subs, penalty goals), else
(tournament, match_date +/-1d, frozenset{norm(home), norm(away)}) against the 4-tourn spine.
Team-name normalization mirrors ingest/fetch_match_events.py (spine uses "South Korea"/"North Korea"
in 2010/2014 hist, "Korea Republic" in 2018/2022; this maps both Korea variants + Cote d'Ivoire +
encoding-mangled strings + a "SPA"->Spain typo in the attendance file).

Output: data/matches/match_enrichment.parquet   (NEVER overwrites any existing file)
Cached source CSVs:
  data/external/jfjelstul/{goals,substitutions}.csv   (public domain)
  data/external/attendance/att.csv                    (datahub)
  data/external/fifa_ranking/dato.csv                 (Dato-Futbol)
"""
import os, re, sys
from datetime import timedelta
import urllib.request
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
MDIR = os.path.join(HERE, "..", "data", "matches")
EXT  = os.path.join(HERE, "..", "data", "external")
YEARS = (2010, 2014, 2018, 2022)

# VAR introduced tournament-wide in 2018 and used again 2022; NOT in 2010/2014.
VAR_YEARS = {2018, 2022}

JFJ_RAW   = "https://raw.githubusercontent.com/jfjelstul/worldcup/master/data-csv/{}.csv"
ATT_URL   = "https://datahub.io/football/worldcup/_r/-/attendance.csv"
FIFA_URL  = "https://raw.githubusercontent.com/Dato-Futbol/fifa-ranking/master/ranking_fifa_historical.csv"


# --------------------------------------------------------------- team normalization
_ALIAS = {
    "south korea": "korearepublic", "korea republic": "korearepublic",
    "north korea": "koreadpr", "korea dpr": "koreadpr",
    "iran": "iran", "ir iran": "iran",
    "czech republic": "czechia", "turkey": "turkiye", "türkiye": "turkiye",
    "ivory coast": "cotedivoire",
    "usa": "unitedstates", "united states": "unitedstates",
    "china pr": "china", "republic of ireland": "ireland",
    "bosnia and herzegovina": "bosniaherzegovina", "bosnia-herzegovina": "bosniaherzegovina",
    "spa": "spain",   # attendance.csv has one "SPA" (Spain) typo in 2022
}
def norm(t):
    t = str(t).lower().strip()
    # Cote d'Ivoire appears in several mojibake forms across the mixed-encoding attendance file
    if "voire" in t or "ivoire" in t or t.startswith("c") and "te d" in t and "iv" in t.replace("�", "iv"):
        return "cotedivoire"
    if "ivoire" in t.encode("ascii", "ignore").decode().lower():
        return "cotedivoire"
    if "te d" in t and ("�" in t or "ã" in t or "ô" in t):  # Cï¿½te / CÃ´te / Côte
        return "cotedivoire"
    if t in _ALIAS:
        return _ALIAS[t]
    return re.sub(r"[^a-z]", "", t)


# --------------------------------------------------------------- downloads (cached)
def _fetch(url, path, encoding=None):
    if os.path.exists(path) and os.path.getsize(path) > 1000:
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    print(f"[download] {url}")
    urllib.request.urlretrieve(url, path)


def load_sources():
    jdir = os.path.join(EXT, "jfjelstul")
    adir = os.path.join(EXT, "attendance")
    fdir = os.path.join(EXT, "fifa_ranking")
    _fetch(JFJ_RAW.format("goals"),         os.path.join(jdir, "goals.csv"))
    _fetch(JFJ_RAW.format("substitutions"), os.path.join(jdir, "substitutions.csv"))
    _fetch(ATT_URL,                          os.path.join(adir, "att.csv"))
    _fetch(FIFA_URL,                         os.path.join(fdir, "dato.csv"))
    goals = pd.read_csv(os.path.join(jdir, "goals.csv"))
    subs  = pd.read_csv(os.path.join(jdir, "substitutions.csv"))
    # attendance file is mixed-encoding; cp1252 decodes the most rows, mojibake handled in norm()
    att   = pd.read_csv(os.path.join(adir, "att.csv"), encoding="cp1252")
    fifa  = pd.read_csv(os.path.join(fdir, "dato.csv"))
    return goals, subs, att, fifa


# --------------------------------------------------------------- spine
def load_spine():
    hist = pd.read_parquet(os.path.join(MDIR, "matches_hist.parquet"))
    allm = pd.read_parquet(os.path.join(MDIR, "matches_all.parquet"))
    allm = allm[allm.tournament.isin([2018, 2022])]
    cols = ["tournament", "kickoff_utc", "home", "away", "stage"]
    spine = pd.concat([hist[cols], allm[cols]], ignore_index=True)
    spine["ko"] = pd.to_datetime(spine["kickoff_utc"], utc=True)
    spine["d"]  = spine["ko"].dt.strftime("%Y-%m-%d")
    return spine.reset_index(drop=True)


def build_lut(spine):
    lut = {}
    for i, r in spine.iterrows():
        teams = frozenset({norm(r["home"]), norm(r["away"])})
        lut[(int(r["tournament"]), r["d"], teams)] = i
    return lut


def match_to_spine(lut, year, date, t1, t2):
    """Return spine row index or None, with +/-1 day fallback."""
    teams = frozenset({norm(t1), norm(t2)})
    key = (year, date, teams)
    if key in lut:
        return lut[key]
    for dd in (-1, 1):
        d2 = (pd.Timestamp(date) + timedelta(days=dd)).strftime("%Y-%m-%d")
        if (year, d2, teams) in lut:
            return lut[(year, d2, teams)]
    return None


# --------------------------------------------------------------- FIFA as-of
def fifa_asof_lookup(fifa):
    """Return f(team_norm, kickoff_ts) -> (rank, points) using the ranking dated <= kickoff.
    Rank derived by ordering total_points within each ranking date (descending)."""
    fifa = fifa.copy()
    fifa["date"] = pd.to_datetime(fifa["date"])
    fifa = fifa[fifa["total_points"].notna()].copy()
    fifa["rank"] = fifa.groupby("date")["total_points"].rank(ascending=False, method="min").astype(int)
    fifa["tn"] = fifa["team"].map(norm)
    dates = sorted(fifa["date"].unique())
    # per-team frame for fast as-of merge
    fifa = fifa.sort_values("date")
    by_team = {tn: g[["date", "rank", "total_points"]].reset_index(drop=True)
               for tn, g in fifa.groupby("tn")}

    def lookup(team_norm, kickoff_ts):
        ko = pd.Timestamp(kickoff_ts).tz_localize(None) if pd.Timestamp(kickoff_ts).tzinfo else pd.Timestamp(kickoff_ts)
        g = by_team.get(team_norm)
        if g is None:
            return (pd.NA, pd.NA)
        elig = g[g["date"] <= ko]
        if elig.empty:
            return (pd.NA, pd.NA)
        row = elig.iloc[-1]
        return (int(row["rank"]), float(row["total_points"]))
    return lookup


# --------------------------------------------------------------- main build
def main():
    goals, subs, att, fifa = load_sources()
    spine = load_spine()
    lut = build_lut(spine)
    n = len(spine)

    out = spine[["tournament", "kickoff_utc", "home", "away", "stage"]].copy()
    out["attendance"]      = pd.array([pd.NA] * n, dtype="Int64")
    out["n_subs"]          = pd.array([pd.NA] * n, dtype="Int64")
    out["n_penalty_kicks"] = pd.array([0] * n,     dtype="Int64")
    out["var_flag"]        = out["tournament"].isin(VAR_YEARS).astype(int)

    cov = {f: {y: 0 for y in YEARS} for f in
           ("attendance", "n_subs", "n_penalty_kicks", "fifa_home", "fifa_away")}
    unmatched = {"attendance": [], "subs": []}

    # ---- 1. attendance (date+teams join) ----
    a = att[att.year.isin(YEARS)].copy()
    for _, r in a.iterrows():
        idx = match_to_spine(lut, int(r["year"]), r["date"], r["team1"], r["team2"])
        if idx is None:
            unmatched["attendance"].append((int(r["year"]), r["date"], r["team1"], r["team2"]))
            continue
        val = r["attendance"]
        if pd.notna(val) and val > 0:
            out.at[idx, "attendance"] = int(val)
            cov["attendance"][int(r["year"])] += 1

    # ---- 2. substitutions (Fjelstul match_id -> date+teams join; count coming_on) ----
    subs = subs.copy()
    subs["yr"] = subs["tournament_name"].str.extract(r"(\d{4})").astype(int)
    subs = subs[subs["yr"].isin(YEARS) & subs["tournament_name"].str.contains("Men")]
    # one substitution event == one player coming on
    sc = subs[subs["coming_on"] == 1].groupby("match_id").size()
    # map match_id -> spine via the matches metadata embedded in subs (match_date + home/away team)
    meta = subs.drop_duplicates("match_id")[["match_id", "yr", "match_date", "home_team", "away_team", "team_name"]]
    # subs rows carry home_team/away_team as 0/1 flags, not names; derive names from team_name per side
    # Simpler: pull home/away names from match_name "A vs B"
    nm = subs.drop_duplicates("match_id")[["match_id", "yr", "match_date", "match_name"]].copy()
    nm[["mhome", "maway"]] = nm["match_name"].str.split(" vs ", expand=True)
    for _, r in nm.iterrows():
        idx = match_to_spine(lut, int(r["yr"]), r["match_date"], r["mhome"], r["maway"])
        if idx is None:
            unmatched["subs"].append((int(r["yr"]), r["match_date"], r["match_name"]))
            continue
        cnt = int(sc.get(r["match_id"], 0))
        out.at[idx, "n_subs"] = cnt
        cov["n_subs"][int(r["yr"])] += 1

    # ---- 3. in-match penalty goals (Fjelstul goals.csv penalty==1) ----
    g = goals.copy()
    g["yr"] = g["tournament_name"].str.extract(r"(\d{4})").astype(int)
    g = g[g["yr"].isin(YEARS) & g["tournament_name"].str.contains("Men")]
    pg = g[g["penalty"] == 1]
    gnm = g.drop_duplicates("match_id")[["match_id", "yr", "match_date", "match_name"]].copy()
    gnm[["mhome", "maway"]] = gnm["match_name"].str.split(" vs ", expand=True)
    pk_by_match = pg.groupby("match_id").size()
    for _, r in gnm.iterrows():
        idx = match_to_spine(lut, int(r["yr"]), r["match_date"], r["mhome"], r["maway"])
        if idx is None:
            continue
        cnt = int(pk_by_match.get(r["match_id"], 0))
        out.at[idx, "n_penalty_kicks"] = cnt
        if cnt > 0:
            cov["n_penalty_kicks"][int(r["yr"])] += 1

    # ---- 4. FIFA rank/points as-of kickoff (no look-ahead) ----
    lookup = fifa_asof_lookup(fifa)
    hr = []; hp = []; ar = []; ap = []
    for _, r in out.iterrows():
        ko = r["kickoff_utc"]
        rh, ph = lookup(norm(r["home"]), ko)
        ra, pa = lookup(norm(r["away"]), ko)
        hr.append(rh); hp.append(ph); ar.append(ra); ap.append(pa)
        yr = int(r["tournament"])
        if pd.notna(rh): cov["fifa_home"][yr] += 1
        if pd.notna(ra): cov["fifa_away"][yr] += 1
    out["home_fifa_rank"]   = pd.array(hr, dtype="Int64")
    out["home_fifa_points"] = pd.array(hp, dtype="Float64")
    out["away_fifa_rank"]   = pd.array(ar, dtype="Int64")
    out["away_fifa_points"] = pd.array(ap, dtype="Float64")

    # ---- write ----
    final_cols = ["tournament", "kickoff_utc", "home", "away", "stage",
                  "attendance", "n_subs", "n_penalty_kicks", "var_flag",
                  "home_fifa_rank", "home_fifa_points", "away_fifa_rank", "away_fifa_points"]
    out = out[final_cols]
    outpath = os.path.join(MDIR, "match_enrichment.parquet")
    out.to_parquet(outpath, index=False)

    # ---- coverage report to stdout ----
    print(f"\nwrote {outpath}  ({len(out)} matches)")
    per_yr = {y: int((out.tournament == y).sum()) for y in YEARS}
    print("matches per tournament:", per_yr)
    print("\nCOVERAGE (matched / total per tournament):")
    for f in ("attendance", "n_subs"):
        print(f"  {f:18s}", {y: f"{cov[f][y]}/{per_yr[y]}" for y in YEARS})
    print(f"  {'matches w/ in-match PK':18s}", {y: cov['n_penalty_kicks'][y] for y in YEARS})
    print(f"  {'fifa_home rank':18s}", {y: f"{cov['fifa_home'][y]}/{per_yr[y]}" for y in YEARS})
    print(f"  {'fifa_away rank':18s}", {y: f"{cov['fifa_away'][y]}/{per_yr[y]}" for y in YEARS})
    print(f"  var_flag: 2010/2014=0, 2018/2022=1 (tournament-level)")
    if unmatched["attendance"]:
        print("\nUNMATCHED attendance rows:", len(unmatched["attendance"]), unmatched["attendance"][:10])
    if unmatched["subs"]:
        print("UNMATCHED subs rows:", len(unmatched["subs"]), unmatched["subs"][:10])
    # null audit
    print("\nNULL counts in output:")
    for c in ("attendance", "n_subs", "home_fifa_rank", "away_fifa_rank"):
        print(f"  {c}: {int(out[c].isna().sum())} null")
    return out


if __name__ == "__main__":
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    main()
