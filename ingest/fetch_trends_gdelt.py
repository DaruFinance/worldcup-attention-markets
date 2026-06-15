#!/usr/bin/env python3
"""
Free attention/news controls for the FOUR completed World Cups (2010, 2014, 2018, 2022).

Two independent sources, both free, both saved to data/controls/:
  1. Google Trends (via pytrends)  -> google_trends.parquet  [date, geo, term, interest]
     Daily search-interest over each tournament window +/- 3 weeks, worldwide + per mapped country.
     (Hourly history isn't available for old dates; daily is the right resolution.)
  2. GDELT 2.0 DOC API (no key)     -> gdelt_news.parquet     [date, query, volume, tone]
     Daily article volume + average tone for "World Cup"/team queries, global + mapped countries.
     GDELT GKG/DOC coverage is strong from 2017 on; 2018/2022 well covered, 2014 partial, 2010 absent.

Design notes:
  - Both sources rate-limit. We go gently, cache every raw response to data/controls/_cache/,
    and on a 429 / "limit requests" message we back off exponentially. Cached responses are
    re-used so re-running is cheap and idempotent.
  - We DO NOT fabricate. If a source/year is unreachable after retries, we record nothing for it
    and report the gap honestly in the handoff.

Run:
  export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
  python3 ingest/fetch_trends_gdelt.py
"""
import os, json, time, hashlib, urllib.parse, urllib.request, sys
from datetime import datetime, timedelta, timezone

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
OUT  = os.path.join(HERE, "..", "data", "controls")
CACHE = os.path.join(OUT, "_cache")
os.makedirs(OUT, exist_ok=True)
os.makedirs(CACHE, exist_ok=True)

# ---------------------------------------------------------------------------
# Tournament windows (from data/matches/*; kickoff_utc min/max), padded +/- 3 weeks
# ---------------------------------------------------------------------------
PAD = timedelta(weeks=3)
TOURN = {
    2010: (datetime(2010, 6, 11), datetime(2010, 7, 11)),
    2014: (datetime(2014, 6, 12), datetime(2014, 7, 13)),
    2018: (datetime(2018, 6, 14), datetime(2018, 7, 15)),
    2022: (datetime(2022, 11, 20), datetime(2022, 12, 18)),
}
def window(yr):
    s, e = TOURN[yr]
    return (s - PAD).date(), (e + PAD).date()

# Country -> Google-Trends geo code (per _CONTEXT country->market mapping)
GEOS = {
    "WORLD": "",     # worldwide
    "US": "US", "BR": "BR", "GB": "GB", "DE": "DE", "FR": "FR",
    "ES": "ES", "JP": "JP", "MX": "MX", "AR": "AR",
}
TRENDS_TERMS = ["World Cup", "FIFA World Cup"]

# ---------------------------------------------------------------------------
# Generic cached HTTP GET with backoff on rate-limit
# ---------------------------------------------------------------------------
def _cache_path(url):
    h = hashlib.sha1(url.encode()).hexdigest()[:20]
    return os.path.join(CACHE, h + ".txt")

def http_get(url, *, min_gap=5.5, max_tries=6, ua="wc-research/1.0 (research; contact research@example.org)"):
    """GET with on-disk cache + exponential backoff on GDELT/HTTP rate limits.
       Returns text or None (after exhausting retries)."""
    cp = _cache_path(url)
    if os.path.exists(cp):
        with open(cp) as f:
            return f.read()
    wait = min_gap
    for attempt in range(1, max_tries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": ua})
            with urllib.request.urlopen(req, timeout=60) as r:
                txt = r.read().decode("utf-8", "replace")
        except Exception as ex:
            print(f"   http err (try {attempt}): {ex}", flush=True)
            time.sleep(wait); wait = min(wait * 2, 120); continue
        low = txt.lstrip()[:200].lower()
        if "limit requests" in low or "rate limit" in low or low.startswith("<!doctype html") and "error" in low:
            print(f"   rate-limited (try {attempt}); backing off {wait:.0f}s", flush=True)
            time.sleep(wait); wait = min(wait * 2, 180); continue
        # success: cache it
        with open(cp, "w") as f:
            f.write(txt)
        time.sleep(min_gap)  # be polite even on success
        return txt
    return None

# ---------------------------------------------------------------------------
# GDELT news volume + tone
#
# Primary attempt: GDELT 2.0 DOC API (timelinevol/timelinetone). On this shared
# box the DOC API hard-blocks our IP with HTTP 429 ("limit requests ... one every
# 5 seconds"), so we FALL BACK to the free GKG v1 daily bulk files on the
# unthrottled host http://data.gdeltproject.org/gkg/YYYYMMDD.gkg.csv.zip .
#
# GKG v1 daily files exist for 2014, 2018, 2022 (start ~Apr-2013); 2010 is absent
# (404), which matches GDELT's documented coverage. We stream each daily zip
# (curl|funzip), never writing it to disk (D: is near-full), count articles whose
# GKG record mentions "world cup" (global volume), average the first V2Tone
# subfield over those records (tone), and break down by the country codes that
# appear in the LOCATIONS column (US/UK/BR/GM=DE/FR/SP=ES/JA=JP/MX/AR).
# NOTE: country counts are "World-Cup articles that also reference country X",
# an attention proxy, NOT exclusive source-country counts.
# ---------------------------------------------------------------------------
GDELT_DOC = "https://api.gdeltproject.org/api/v2/doc/doc"
GKG_HOST  = "http://data.gdeltproject.org/gkg"

# country label -> GKG LOCATIONS substring (FIPS country codes wrapped in '#')
GKG_COUNTRY = {
    "US": "#US#", "UK": "#UK#", "BR": "#BR#", "DE": "#GM#", "FR": "#FR#",
    "ES": "#SP#", "JP": "#JA#", "MX": "#MX#", "AR": "#AR#",
}

# awk body (the BEGIN with FS + country map is prepended per-call).
_AWK_BODY = r'''
tolower($0) ~ /world cup/ {
  n++; split($8,t,","); tone+=t[1];
  for (c in CC) if (index($5, CC[c])) cnt[c]++;
}
END{
  printf "GLOBAL\t%d\t%.4f\n", n, (n>0? tone/n : 0);
  for (c in CC) printf "%s\t%d\n", c, cnt[c]+0;
}
'''

def _doc_probe():
    """Quick liveness probe of the DOC API. Returns True only if it serves JSON."""
    url = (GDELT_DOC + "?query=" + urllib.parse.quote('"World Cup"') +
           "&mode=timelinevol&format=json&TIMESPAN=1day")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "wc-research/1.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            txt = r.read().decode("utf-8", "replace")
        return txt.lstrip().startswith("{")
    except Exception:
        return False

def _gkg_day(date):
    """Stream one GKG v1 daily file and return (global_vol, global_tone, {country:cnt}) or None.
       Streams via curl|funzip|awk; nothing is written to disk."""
    ymd = date.strftime("%Y%m%d")
    url = f"{GKG_HOST}/{ymd}.gkg.csv.zip"
    cc_assign = ";".join(f'CC["{k}"]="{v}"' for k, v in GKG_COUNTRY.items())
    awk_full = 'BEGIN{FS="\t";' + cc_assign + "}" + _AWK_BODY
    import subprocess
    # curl (fail on 404) | funzip (unzip first member from stdin) | awk
    cmd = (f'curl -sf --max-time 240 {url} | funzip | '
           f'awk {shquote(awk_full)}')
    try:
        out = subprocess.run(["bash", "-lc", cmd], capture_output=True, text=True, timeout=300)
    except Exception as ex:
        print(f"   gkg {ymd}: exec err {ex}", flush=True); return None
    if out.returncode != 0 or not out.stdout.strip():
        # 404 (year/day absent) or empty -> caller decides
        return None
    gvol, gtone, cc = None, None, {}
    for ln in out.stdout.strip().splitlines():
        p = ln.split("\t")
        if p[0] == "GLOBAL":
            gvol, gtone = int(p[1]), float(p[2])
        elif len(p) == 2:
            cc[p[0]] = int(p[1])
    return gvol, gtone, cc

def shquote(s):
    return "'" + s.replace("'", "'\\''") + "'"

def fetch_gdelt():
    rows, cover = [], {}
    doc_ok = _doc_probe()
    print(f"  GDELT DOC API live? {doc_ok}  (falling back to GKG bulk files: {not doc_ok})", flush=True)
    for yr in (2010, 2014, 2018, 2022):
        s, e = window(yr)
        days = pd.date_range(s, e, freq="D")
        got = 0
        # quick 2010 short-circuit: GKG v1 doesn't reach 2010
        if yr == 2010:
            print(f"  GDELT {yr}: GKG v1 does not cover 2010 (pre-2013) -> SKIP", flush=True)
            cover[("world_cup", yr)] = "no_coverage_pre2013"
            continue
        for d in days:
            res = _gkg_day(d.date())
            if res is None:
                continue
            gvol, gtone, cc = res
            rows.append(dict(date=pd.Timestamp(d.date()), query="world_cup_global",
                             volume=gvol, tone=gtone, tournament=yr))
            for c, n in cc.items():
                rows.append(dict(date=pd.Timestamp(d.date()), query=f"world_cup_{c}",
                                 volume=n, tone=None, tournament=yr))
            got += 1
            if got % 10 == 0:
                print(f"   GDELT {yr}: {got}/{len(days)} days...", flush=True)
        cover[("world_cup", yr)] = got
        print(f"  GDELT {yr}: {got}/{len(days)} daily files parsed", flush=True)
    df = pd.DataFrame(rows)
    return df, cover

# ---------------------------------------------------------------------------
# Google Trends via pytrends
# ---------------------------------------------------------------------------
def fetch_trends():
    try:
        from pytrends.request import TrendReq
    except Exception as ex:
        print(f"pytrends import failed: {ex}", flush=True)
        return pd.DataFrame(), {}
    rows = []
    cover = {}
    pt = TrendReq(hl="en-US", tz=0, retries=3, backoff_factor=1.5,
                  timeout=(10, 30))
    for yr in (2010, 2014, 2018, 2022):
        s, e = window(yr)
        tf = f"{s.isoformat()} {e.isoformat()}"
        for term in TRENDS_TERMS:
            for label, geo in GEOS.items():
                ck = os.path.join(CACHE, "trends_" +
                    hashlib.sha1(f"{term}|{geo}|{tf}".encode()).hexdigest()[:18] + ".json")
                df = None
                if os.path.exists(ck):
                    try:
                        df = pd.read_json(ck, orient="split")
                    except Exception:
                        df = None
                if df is None:
                    ok = False
                    wait = 8.0
                    for attempt in range(1, 6):
                        try:
                            pt.build_payload([term], timeframe=tf, geo=geo)
                            df = pt.interest_over_time()
                            ok = True
                            break
                        except Exception as ex:
                            msg = str(ex)
                            print(f"   trends {term}/{label}/{yr} try{attempt}: {msg[:80]}", flush=True)
                            time.sleep(wait); wait = min(wait * 2, 120)
                    if not ok:
                        cover[(term, label, yr)] = "unreachable"
                        continue
                    if df is not None and len(df):
                        try:
                            df.to_json(ck, orient="split")
                        except Exception:
                            pass
                    time.sleep(2.0)  # gentle pacing between successful calls
                if df is None or not len(df):
                    cover[(term, label, yr)] = 0
                    print(f"  trends {term}/{label}/{yr}: 0 (empty)", flush=True)
                    continue
                col = term if term in df.columns else df.columns[0]
                n = 0
                for ts, val in df[col].items():
                    rows.append(dict(date=pd.Timestamp(ts), geo=(geo or "WORLD"),
                                     term=term, interest=int(val), tournament=yr))
                    n += 1
                cover[(term, label, yr)] = n
                print(f"  trends {term}/{label}/{yr}: {n} daily points", flush=True)
    df = pd.DataFrame(rows)
    return df, cover

# ---------------------------------------------------------------------------
def _save_coverage(tcov=None, gcov=None):
    p = os.path.join(CACHE, "_coverage.json")
    cov = {}
    if os.path.exists(p):
        try: cov = json.load(open(p))
        except Exception: cov = {}
    if tcov is not None:
        cov["trends"] = {f"{k[0]}|{k[1]}|{k[2]}": v for k, v in tcov.items()}
    if gcov is not None:
        cov["gdelt"] = {f"{k[0]}|{k[1]}": v for k, v in gcov.items()}
    with open(p, "w") as f:
        json.dump(cov, f, indent=2, default=str)

def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "all"  # all | trends | gdelt

    if which in ("all", "trends"):
        print("=== Google Trends ===", flush=True)
        tdf, tcov = fetch_trends()
        if len(tdf):
            tdf = tdf.sort_values(["term", "geo", "date"]).reset_index(drop=True)
            tdf.to_parquet(os.path.join(OUT, "google_trends.parquet"))
            print(f"google_trends.parquet: {len(tdf)} rows saved", flush=True)
        else:
            print("google_trends: NO ROWS (source blocked)", flush=True)
        _save_coverage(tcov=tcov)

    if which in ("all", "gdelt"):
        print("=== GDELT ===", flush=True)
        gdf, gcov = fetch_gdelt()
        if len(gdf):
            gdf = gdf.sort_values(["query", "date"]).reset_index(drop=True)
            gdf.to_parquet(os.path.join(OUT, "gdelt_news.parquet"))
            print(f"gdelt_news.parquet: {len(gdf)} rows saved", flush=True)
        else:
            print("gdelt_news: NO ROWS (source blocked)", flush=True)
        _save_coverage(gcov=gcov)

    print("done.", flush=True)

if __name__ == "__main__":
    main()
