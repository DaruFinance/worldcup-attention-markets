#!/usr/bin/env python3
"""Hourly refresher: re-fetch the live 2026 feed and rebuild the match spine so scores
and the resolving knockout bracket stay current through the tournament. Low footprint."""
import os, sys, time, urllib.request, traceback
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
FEED = os.path.join(HERE, "..", "data", "matches", "wc2026_fixturedownload.json")
URL  = "https://fixturedownload.com/feed/json/fifa-world-cup-2026"
sys.path.insert(0, HERE)

def log(m):
    print(f"[{datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S}] {m}", flush=True)

def once():
    req = urllib.request.Request(URL, headers={"User-Agent": "wc-refresh/1.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        data = r.read()
    with open(FEED, "wb") as f:
        f.write(data)
    import build_matches as bm
    import importlib; importlib.reload(bm)
    df = bm.build_2026(); bm.build_match_state_2026(df)
    log(f"refreshed: {len(df)} matches, played={int(df['played'].sum())}, "
        f"teams_known={int(df['teams_known'].sum())}")

if __name__ == "__main__":
    interval = int(os.environ.get("REFRESH_SEC", "3600"))
    if "--once" in sys.argv:
        once(); sys.exit(0)
    while True:
        try: once()
        except Exception: log("refresh error:\n" + traceback.format_exc())
        time.sleep(interval)
