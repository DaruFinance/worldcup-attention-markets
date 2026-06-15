#!/usr/bin/env python3
"""
Parse the NEWLY-pulled extra instruments using the EXACT logic of the existing
parsers (imported, not duplicated; existing scripts are not edited).

It imports parse_futures.parse_root and parse_equity.parse_ticker and calls them
for the new roots/tickers only. Each writes into the same output dirs the existing
parsers use:
  futures -> data/market/futures/{ROOT}_1m.parquet
  equity  -> data/market/equity/{TICKER}_1m.parquet

New futures roots: RTY,YM,SI,NG,HG,ZT,ZF,ZN,ZB   (DX absent from CME bucket)
New equity ticker: DIA
"""
import os, sys
from datetime import datetime, timezone
from concurrent.futures import ProcessPoolExecutor

HERE=os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import parse_futures as pf
import parse_equity as pe

NEW_ROOTS=["RTY","YM","SI","NG","HG","ZT","ZF","ZN","ZB"]
NEW_TICKERS=["DIA"]

def log(m):
    print(f"[{datetime.now(timezone.utc):%H:%M:%S}] {m}", flush=True)

def main():
    log(f"parsing {len(NEW_ROOTS)} new futures roots: {NEW_ROOTS}")
    with ProcessPoolExecutor(max_workers=4) as ex:
        for root,n in ex.map(pf.parse_root, NEW_ROOTS):
            log(f"  {root}: {n:,} minute-bars")
    log(f"parsing {len(NEW_TICKERS)} new equity tickers: {NEW_TICKERS}")
    with ProcessPoolExecutor(max_workers=2) as ex:
        for tk,n in ex.map(pe.parse_ticker, NEW_TICKERS):
            log(f"  {tk}: {n:,} minute-bars")
    log("done")

if __name__=="__main__":
    main()
