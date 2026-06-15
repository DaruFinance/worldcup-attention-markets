#!/usr/bin/env python3
"""
fetch_odds_retry.py -- SECOND attempt at closing 1X2 odds for the historical
World Cups (2010 / 2014 / 2018), to extend the 2022-only coverage already in
data/matches/odds.parquet.

This script does NOT overwrite odds.parquet. It writes a NEW combined file
data/matches/odds_v2.parquet = (existing 2022 odds) + (whatever historical
years this retry recovers cleanly).

----------------------------------------------------------------------------
WHAT THIS RETRY FOUND (full source log; see handoffs/odds_retry.md)
----------------------------------------------------------------------------
(A) *** SOLVED 2010 + 2014 ***  -- "Beat the Bookie" worldwide football dataset
    (Kaunitz, Zhong & Kreiner 2017, arXiv:1710.02824).
    Kaggle dataset austro/beat-the-bookie-worldwide-football-dataset is
    DIRECTLY DOWNLOADABLE WITHOUT A KAGGLE TOKEN via the public endpoint
    https://www.kaggle.com/api/v1/datasets/download/<slug> (an 88 MB zip).
    Inside: closing_odds.csv.gz -- 479,441 matches, 2005..2015, league column.
    The league "World: World Cup" holds exactly 64 matches in 2010 and 64 in
    2014 = the two complete finals tournaments. Columns avg_odds_{home,draw,away}
    are the AVERAGE closing decimal odds across ~24-27 bookmakers per match
    (n_odds_* ~= 24-27), i.e. a clean consensus closing line. We de-vig those.
    The GitHub repo Lisandro79/BeatTheBookie is code-only; its Dropbox links are
    dead (403) and its Google Drive folder is now permission-restricted, so the
    Kaggle public-download endpoint is the working free path.

(B) *** 2018 STILL BLOCKED for a clean free direct-download source. ***
    - The-Odds-API-derived datasets (eatpizzanot/soccer-dataset, used by the
      first attempt) start 2020-06, so they carry 2022 only -- ZERO 2018.
    - Beat-the-Bookie ends 2015-09, so it cannot cover 2018.
    - football-data.co.uk carries European CLUB leagues only -- no internationals.
    - oddsportal.com world-cup-2018 results + individual match pages ARE archived
      on the Wayback Machine, BUT oddsportal renders the odds table from a
      separate XHR feed (/feed/match-odds/...{xhash}.dat). Those feed responses
      were never captured by Wayback (verified via the CDX index: zero snapshots
      of /feed/match-odds*), and the archived HTML shells carry an EMPTY
      #tournamentTable / odds-data div. So the 2018 odds VALUES are not
      retrievable from the archive even though the page shells are.
    - Club-only Kaggle odds dumps (rayenjlassi, eladsil) contain WC qualifiers
      but not the 2018 finals.
    To get 2018 cleanly you need EITHER (i) a Kaggle/GitHub dataset that mirrors
    2018-finals consensus closing odds (none found free + auth-less), OR
    (ii) a live OddsHarvester-class scrape of oddsportal's current
    world-cup-2018 finals pages (JS feed decode; the box's Playwright MCP could
    do this but it is a heavier, fragile job left for a follow-up).

NET NEW COVERAGE vs the first attempt: +2010 (64) +2014 (64) = 128 matches.
Combined odds_v2.parquet now carries 2010, 2014, 2022 with real odds; 2018 rows
are present but NaN (still blocked), same status they had in odds.parquet.

Usage:  python3 ingest/fetch_odds_retry.py
Output: data/matches/odds_v2.parquet   (NEW file; odds.parquet untouched)
"""
import os
import gzip
import sys
import urllib.request
import zipfile
import io

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPINE_ALL = os.path.join(ROOT, "data/matches/matches_all.parquet")
SPINE_HIST = os.path.join(ROOT, "data/matches/matches_hist.parquet")
EXISTING_ODDS = os.path.join(ROOT, "data/matches/odds.parquet")
OUT = os.path.join(ROOT, "data/matches/odds_v2.parquet")

KAGGLE_URL = ("https://www.kaggle.com/api/v1/datasets/download/"
              "austro/beat-the-bookie-worldwide-football-dataset")
CACHE = "/tmp/btb_closing_odds.csv.gz"

# Beat-the-Bookie team name (or HTML-mangled name) -> matches_hist spine name.
# The spine (matches_hist) uses: South Korea, North Korea, Cote d'Ivoire,
# Bosnia-Herzegovina, USA, etc. Most names already agree; only a few differ.
ALIAS = {
    "Ivory Coast": "Côte d'Ivoire",
    "Bosnia &amp; Herzego": "Bosnia-Herzegovina",   # truncated HTML entity in source
    "Bosnia & Herzego": "Bosnia-Herzegovina",
    "Bosnia and Herzegovina": "Bosnia-Herzegovina",
    # South/North Korea, USA, etc. pass through unchanged (already match spine).
}


def norm_team(t):
    t = (t or "").strip()
    return ALIAS.get(t, t)


# ---------------------------------------------------------------------------
def download_btb():
    """Download Beat-the-Bookie via Kaggle's public (no-token) endpoint, cache
    closing_odds.csv.gz to /tmp. Returns the path, or None on failure."""
    if os.path.exists(CACHE) and os.path.getsize(CACHE) > 1_000_000:
        return CACHE
    print(f"[A] downloading {KAGGLE_URL} ...", file=sys.stderr)
    req = urllib.request.Request(
        KAGGLE_URL, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    )
    try:
        blob = urllib.request.urlopen(req, timeout=240).read()
    except Exception as e:  # noqa
        print(f"[A] download failed: {e}", file=sys.stderr)
        return None
    try:
        zf = zipfile.ZipFile(io.BytesIO(blob))
        name = next(n for n in zf.namelist() if n.endswith("closing_odds.csv.gz"))
        with zf.open(name) as src, open(CACHE, "wb") as dst:
            dst.write(src.read())
        return CACHE
    except Exception as e:  # noqa
        print(f"[A] unzip failed: {e}", file=sys.stderr)
        return None


def load_source_a():
    """Return 2010 + 2014 World Cup finals closing odds from Beat-the-Bookie."""
    path = download_btb()
    if not path:
        return pd.DataFrame()
    with gzip.open(path, "rt", encoding="utf-8", errors="ignore") as fh:
        df = pd.read_csv(fh)
    wc = df[df["league"] == "World: World Cup"].copy()
    wc["date"] = pd.to_datetime(wc["match_date"])
    wc["tournament"] = wc["date"].dt.year
    wc = wc[wc["tournament"].isin([2010, 2014])]
    out = pd.DataFrame({
        "tournament": wc["tournament"].astype(int),
        "date": wc["date"].dt.tz_localize("UTC"),
        "home": wc["home_team"].map(norm_team),
        "away": wc["away_team"].map(norm_team),
        "home_odds": wc["avg_odds_home_win"].astype(float),
        "draw_odds": wc["avg_odds_draw"].astype(float),
        "away_odds": wc["avg_odds_away_win"].astype(float),
        "bookmaker": "avg-of-~25-bookies",
        "odds_source": "Beat-the-Bookie (Kaunitz+2017, Kaggle austro/...); avg closing 1X2",
    })
    return out.reset_index(drop=True)


# ---------------------------------------------------------------------------
def devig(df):
    """De-vig to implied probabilities (proportional inverse-odds) + closeness."""
    df = df.copy()
    inv_h, inv_d, inv_a = 1.0 / df.home_odds, 1.0 / df.draw_odds, 1.0 / df.away_odds
    overround = inv_h + inv_d + inv_a
    df["overround"] = overround
    df["p_home"] = inv_h / overround
    df["p_draw"] = inv_d / overround
    df["p_away"] = inv_a / overround
    df["closeness_ha"] = 1.0 - (df.p_home - df.p_away).abs()
    p = df[["p_home", "p_draw", "p_away"]].clip(lower=1e-12).values
    df["entropy"] = -(p * np.log(p)).sum(axis=1)
    df["entropy_norm"] = df["entropy"] / np.log(3.0)
    df["p_max"] = p.max(axis=1)
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


OUT_COLS = [
    "tournament", "match_no", "kickoff_utc", "home", "away",
    "home_odds", "draw_odds", "away_odds", "overround",
    "p_home", "p_draw", "p_away",
    "closeness_ha", "entropy", "entropy_norm", "p_max",
    "bookmaker", "odds_source",
]


def main():
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
    os.environ.setdefault("OMP_NUM_THREADS", "1")

    # --- new historical odds (2010 + 2014) ---
    a = load_source_a()
    print(f"[A] Beat-the-Bookie WC rows: {len(a)}  by tournament: "
          f"{a.tournament.value_counts().sort_index().to_dict() if len(a) else {}}")
    if len(a) == 0:
        print("NO historical odds obtained. odds_v2 would equal odds.parquet; aborting.",
              file=sys.stderr)
        sys.exit(2)

    a = devig(a)

    # Map historical odds to the spine by tournament + teams, with a +-1 day
    # tolerance on the date: Beat-the-Bookie's match_date is the LOCAL calendar
    # date, while the spine's date_only comes from kickoff_utc. Late-evening UTC
    # kickoffs (e.g. 22:00 UTC in Brazil 2014) roll the local date back a day, so
    # an exact date join silently drops ~10 matches. We require the same teams &
    # tournament and |spine_date - odds_date| <= 1 day.
    sp = load_spine()
    odds_cols = ["home_odds", "draw_odds", "away_odds", "overround",
                 "p_home", "p_draw", "p_away",
                 "closeness_ha", "entropy", "entropy_norm", "p_max",
                 "bookmaker", "odds_source"]
    cand = sp.merge(
        a[["tournament", "home", "away", "date"] + odds_cols],
        on=["tournament", "home", "away"], how="left",
    )
    sp_d = pd.to_datetime(cand["kickoff_utc"]).dt.tz_convert("UTC").dt.normalize()
    od_d = pd.to_datetime(cand["date"]).dt.normalize()
    daygap = (sp_d - od_d).abs()
    ok = cand["home_odds"].notna() & (daygap <= pd.Timedelta(days=1))
    new_hist = cand[ok].copy()
    # one row per spine match (guard against any duplicate odds rows)
    new_hist = new_hist.drop_duplicates(subset=["tournament", "match_no"])
    print(f"[A] mapped to spine (teams + ±1d): {len(new_hist)} matches")

    mapped_keys = set(zip(new_hist.tournament, new_hist.home, new_hist.away))
    unmapped = a[~a.apply(lambda r: (r.tournament, r.home, r.away) in mapped_keys, axis=1)]
    if len(unmapped):
        print("    WARNING unmapped (team/date mismatch):")
        print(unmapped[["tournament", "home", "away"]].to_string())

    new_hist = new_hist[OUT_COLS]

    # --- existing odds (carries 2018 NaN placeholders + 2022 real + 2010/2014
    #     NaN placeholders). Drop its empty 2010/2014 rows; keep 2018 + 2022. ---
    existing = pd.read_parquet(EXISTING_ODDS)
    keep_existing = existing[existing.tournament.isin([2018, 2022])].copy()
    print(f"[B] carrying forward from odds.parquet: 2018+2022 "
          f"({len(keep_existing)} rows, "
          f"{int(keep_existing.home_odds.notna().sum())} with odds)")

    combined = pd.concat([keep_existing[OUT_COLS], new_hist], ignore_index=True)
    combined = combined.sort_values(["tournament", "match_no"]).reset_index(drop=True)

    print("\n=== odds_v2 COVERAGE (matches with real odds / total spine) ===")
    cov = combined.assign(has=combined.home_odds.notna()).groupby("tournament").has.agg(
        ["sum", "count"])
    cov.columns = ["with_odds", "total"]
    print(cov.to_string())
    print(f"TOTAL: {int(combined.home_odds.notna().sum())}/{len(combined)} "
          f"spine matches now have odds")

    combined.to_parquet(OUT, index=False)
    print(f"\nwrote {OUT}  ({len(combined)} rows, "
          f"{int(combined.home_odds.notna().sum())} populated)")


if __name__ == "__main__":
    main()
