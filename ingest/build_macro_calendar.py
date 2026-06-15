#!/usr/bin/env python3
"""
High-impact US macro releases overlapping the 2018 & 2022 tournament windows, with
scheduled UTC times. Used to drop contaminated minutes (release ±90m) in robustness.
Date FE already absorbs whole-day shocks; this is the finer within-day control that
matters when a release coincides with a match window (esp. 2022 morning matches vs the
13:30 UTC US data drops).

Out: data/controls/macro_events.parquet  [event_utc, kind, label]
"""
import os
from datetime import datetime, timezone
import pandas as pd

OUT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"..","data","controls")
os.makedirs(OUT, exist_ok=True)

def U(y,m,d,hh,mm): return datetime(y,m,d,hh,mm,tzinfo=timezone.utc)

# (utc, kind, label)  -  scheduled release/decision times (UTC)
EV=[
 # ---- 2018 window (May-Aug 2018) ----
 (U(2018,6,1,12,30),"NFP","Payrolls May18"),(U(2018,7,6,12,30),"NFP","Payrolls Jun18"),
 (U(2018,8,3,12,30),"NFP","Payrolls Jul18"),
 (U(2018,6,12,12,30),"CPI","CPI May18"),(U(2018,7,12,12,30),"CPI","CPI Jun18"),
 (U(2018,6,13,18,0),"FOMC","FOMC Jun18"),(U(2018,8,1,18,0),"FOMC","FOMC Aug18"),
 # ---- 2022 window (Oct 2022-Jan 2023) ----
 (U(2022,11,4,12,30),"NFP","Payrolls Oct22"),(U(2022,12,2,13,30),"NFP","Payrolls Nov22"),
 (U(2023,1,6,13,30),"NFP","Payrolls Dec22"),
 (U(2022,11,10,13,30),"CPI","CPI Oct22"),(U(2022,12,13,13,30),"CPI","CPI Nov22"),
 (U(2023,1,12,13,30),"CPI","CPI Dec22"),
 (U(2022,11,2,18,0),"FOMC","FOMC Nov22"),(U(2022,12,14,19,0),"FOMC","FOMC Dec22"),
 (U(2022,12,15,12,45),"ECB","ECB Dec22"),(U(2022,10,27,12,15),"ECB","ECB Oct22"),
]
def main():
    df=pd.DataFrame([(e[0],e[1],e[2]) for e in EV],columns=["event_utc","kind","label"])
    df["event_utc"]=pd.to_datetime(df["event_utc"],utc=True)
    df.to_parquet(os.path.join(OUT,"macro_events.parquet"))
    print(f"macro_events: {len(df)} releases | kinds={sorted(df['kind'].unique())}")
if __name__=="__main__":
    main()
