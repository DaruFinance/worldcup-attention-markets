#!/usr/bin/env python3
"""
fetch_odds.py -- Fetch closing 1X2 odds for World Cup matches (2010/2014/2018/2022),
de-vig to implied probabilities, compute closeness measures, and map to the
combined 4-tournament spine.

Sources tried (free, in priority order), see handoffs/odds.md for the full log:
  (A) GitHub eatpizzanot/soccer-dataset  -- clean Pinnacle closing odds via The-Odds-API,
      committed as csv/parquet, NO API key required.  Reproducible.
      COVERAGE: FIFA World Cup league only has odds for 2022 (56/64 matches); The-Odds-API
      history starts 2020-06 so 2010/2014/2018 have ZERO odds in this repo.
  (B) checkbestodds.com archive pages    -- static HTML, parseable, but each archive page is
      TRUNCATED to a partial window (2022: 64 full; 2018: ~43; 2014: ~25; 2010: 0 / CF-blocked).
      Used here only as an independent cross-check for 2022.
  (C) football-data.co.uk                -- carries European CLUB leagues only, NO internationals. N/A.
  (D) oddsportal.com                     -- the only complete free source, but JS-rendered behind a
      geo/anti-bot redirect (headless session is bounced to a regional mirror serving the homepage;
      the results-archive XHR never fires). Not reachable without OddsHarvester-class circumvention.

NET: clean reproducible coverage = 2022 only. 2010/2014/2018 remain BLOCKED for a clean free source.
This script ships what was cleanly obtained (2022) and de-vigs it; it does NOT fabricate the
missing tournaments. See handoffs/odds.md.

Usage:  python3 ingest/fetch_odds.py
Output: data/matches/odds.parquet
"""
import os
import re
import subprocess
import sys
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPINE_ALL = os.path.join(ROOT, "data/matches/matches_all.parquet")
SPINE_HIST = os.path.join(ROOT, "data/matches/matches_hist.parquet")
OUT = os.path.join(ROOT, "data/matches/odds.parquet")

# eatpizzanot/soccer-dataset clone location (LFS skipped; parquet files are committed plainly)
DS_DIR = "/tmp/soccer-dataset"
DS_REPO = "https://github.com/eatpizzanot/soccer-dataset.git"
WC_LEAGUE_ID = 78  # 'FIFA World Cup' in leagues.parquet

# team-name alias -> spine canonical name
ALIAS = {
    "South Korea": "Korea Republic",
    "Korea Republic": "Korea Republic",
    "USA": "USA",
    "United States": "USA",
    "Ivory Coast": "Côte d'Ivoire",
    "Bosnia and Herzegovina": "Bosnia-Herzegovina",
    "Bosnia & Herzegovina": "Bosnia-Herzegovina",
}


def norm_team(t):
    t = (t or "").strip()
    return ALIAS.get(t, t)


# ---------------------------------------------------------------------------
def ensure_dataset():
    """Clone the eatpizzanot soccer-dataset (parquet files committed plainly, no LFS, no key)."""
    if os.path.isdir(os.path.join(DS_DIR, "parquet")):
        return True
    env = dict(os.environ, GIT_LFS_SKIP_SMUDGE="1")
    try:
        subprocess.run(
            ["git", "clone", "--depth", "1", DS_REPO, DS_DIR],
            check=True, env=env, capture_output=True, timeout=300,
        )
        return os.path.isdir(os.path.join(DS_DIR, "parquet"))
    except Exception as e:  # noqa
        print(f"[A] clone failed: {e}", file=sys.stderr)
        return False


def load_source_a():
    """Return df[tournament, date, home, away, home_odds, draw_odds, away_odds, bookmaker, src]."""
    if not ensure_dataset():
        return pd.DataFrame()
    fx = pd.read_parquet(os.path.join(DS_DIR, "parquet/fixtures.parquet"))
    od = pd.read_parquet(os.path.join(DS_DIR, "parquet/odds.parquet"))
    wc = fx[fx.league_id == WC_LEAGUE_ID].copy()
    wc["tournament"] = wc.date.dt.year
    wc = wc[wc.tournament.isin([2010, 2014, 2018, 2022])]
    # one odds row per fixture (here: a single Pinnacle closing row per fixture)
    od = od.drop_duplicates("fixture_id")
    m = wc.merge(
        od[["fixture_id", "home_win", "draw", "away_win", "bookmaker"]],
        left_on="id", right_on="fixture_id", how="inner",
    )
    out = pd.DataFrame({
        "tournament": m.tournament.astype(int),
        "date": pd.to_datetime(m.date).dt.tz_localize("UTC"),
        "home": m.home_team.map(norm_team),
        "away": m.away_team.map(norm_team),
        "home_odds": m.home_win.astype(float),
        "draw_odds": m.draw.astype(float),
        "away_odds": m.away_win.astype(float),
        "bookmaker": m.bookmaker,
        "odds_source": "eatpizzanot/soccer-dataset (The-Odds-API, Pinnacle close)",
    })
    return out


# ---------------------------------------------------------------------------
def load_source_b_2022():
    """Cross-check: parse checkbestodds.com 2022 archive (static HTML). 2022 page carries all 64."""
    import urllib.request
    url = "https://checkbestodds.com/football-odds/archive-world-cup-2022"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    try:
        html = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "ignore")
    except Exception as e:  # noqa
        print(f"[B] fetch failed: {e}", file=sys.stderr)
        return pd.DataFrame()
    pat = re.compile(
        r'<span ts="(\d+)" class="time[^"]*">[^<]*</span>\s*'
        r'<a href="[^"]*">\s*([^<]+?)\s*</a></td>\s*'
        r'<td class="r">\s*<b[^>]*>([\d.]+)</b></td>\s*'
        r'<td class="r">\s*<b[^>]*>([\d.]+)</b></td>\s*'
        r'<td class="r">\s*<b[^>]*>([\d.]+)</b></td>'
    )
    rows = []
    for ts, teams, h, d, a in pat.findall(html):
        if " - " not in teams:
            continue
        ht, at = [s.strip() for s in teams.split(" - ", 1)]
        rows.append({
            "tournament": 2022,
            "date": pd.to_datetime(int(ts), unit="s", utc=True),
            "home": norm_team(ht), "away": norm_team(at),
            "home_odds": float(h), "draw_odds": float(d), "away_odds": float(a),
            "bookmaker": "checkbestodds-archive",
            "odds_source": "checkbestodds.com archive (cross-check)",
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
def devig(df):
    """Add de-vigged implied probs (proportional / Shin-free normalization) + closeness measures."""
    inv_h = 1.0 / df.home_odds
    inv_d = 1.0 / df.draw_odds
    inv_a = 1.0 / df.away_odds
    overround = inv_h + inv_d + inv_a
    df = df.copy()
    df["overround"] = overround
    df["p_home"] = inv_h / overround
    df["p_draw"] = inv_d / overround
    df["p_away"] = inv_a / overround
    # closeness measures
    df["closeness_ha"] = 1.0 - (df.p_home - df.p_away).abs()  # 1 - |P(home)-P(away)|; high = even
    p = df[["p_home", "p_draw", "p_away"]].clip(lower=1e-12).values
    df["entropy"] = -(p * np.log(p)).sum(axis=1)              # nats; max ln3=1.0986 = most uncertain
    df["entropy_norm"] = df["entropy"] / np.log(3.0)          # 0..1
    df["p_max"] = p.max(axis=1)                               # favorite strength (low = close)
    return df


def load_spine():
    a = pd.read_parquet(SPINE_ALL)
    h = pd.read_parquet(SPINE_HIST)
    cols = ["tournament", "match_no", "kickoff_utc", "home", "away"]
    sp = pd.concat([a[a.tournament.isin([2018, 2022])][cols], h[cols]], ignore_index=True)
    sp["home"] = sp.home.map(norm_team)
    sp["away"] = sp.away.map(norm_team)
    sp["date_only"] = pd.to_datetime(sp.kickoff_utc).dt.date
    return sp


def main():
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
    os.environ.setdefault("OMP_NUM_THREADS", "1")

    a = load_source_a()
    b = load_source_b_2022()
    print(f"[A] eatpizzanot rows: {len(a)}  by tournament: "
          f"{a.tournament.value_counts().sort_index().to_dict() if len(a) else {}}")
    print(f"[B] checkbestodds 2022 rows: {len(b)}")

    # Source A is primary; B (checkbestodds) used only to fill 2022 matches A lacks (8 of 64).
    odds = a.copy()
    if len(b):
        have = set(zip(odds.tournament, odds.date.dt.date, odds.home, odds.away))
        b_add = b[~b.apply(lambda r: (r.tournament, r.date.date(), r.home, r.away) in have, axis=1)]
        odds = pd.concat([odds, b_add], ignore_index=True)
        print(f"    + {len(b_add)} 2022 matches supplemented from checkbestodds")

    if len(odds) == 0:
        print("NO odds obtained from any free source.", file=sys.stderr)
        sys.exit(2)

    odds = devig(odds)

    # map to spine by tournament + date + teams
    sp = load_spine()
    odds["date_only"] = odds.date.dt.date
    merged = sp.merge(
        odds.drop(columns=["date"]),
        on=["tournament", "date_only", "home", "away"], how="left",
    )

    matched = merged.home_odds.notna()
    print("\n=== SPINE MATCH COVERAGE ===")
    cov = merged.assign(has=matched).groupby("tournament").has.agg(["sum", "count"])
    cov.columns = ["with_odds", "total"]
    print(cov.to_string())
    print(f"TOTAL: {int(matched.sum())}/{len(merged)} spine matches have odds")

    out_cols = [
        "tournament", "match_no", "kickoff_utc", "home", "away",
        "home_odds", "draw_odds", "away_odds", "overround",
        "p_home", "p_draw", "p_away",
        "closeness_ha", "entropy", "entropy_norm", "p_max",
        "bookmaker", "odds_source",
    ]
    merged[out_cols].to_parquet(OUT, index=False)
    print(f"\nwrote {OUT}  ({len(merged)} rows, {int(matched.sum())} populated)")


if __name__ == "__main__":
    main()
