# Data availability

This study uses both freely available data and data licensed from paid vendors. Our policy is
to publish **everything that can lawfully be redistributed** — all code, all results, all
figures, the manuscript, and every free or derived dataset — and to withhold **only the raw
licensed series**, which the vendor agreements forbid us from redistributing. Redistributing
them would breach those licenses, so we document exactly how each was obtained instead.

## What is in this repository

| Committed here | Path |
|---|---|
| All analysis and data-build code | `analysis/`, `ingest/`, `collectors/`, `figures/` |
| Every result (regression cells, equivalence bounds, Monte-Carlo and bootstrap output) | `analysis/out/*.csv` |
| Publication figures (vector PDF) and the manuscript (`.tex`, `.pdf`) | `paper/` |
| Match spine, goal timestamps, importance/closeness, odds | `data/matches/` |
| Fjelstul World Cup database, FIFA rankings, attendance | `data/external/` |
| International football results / shootouts (Elo inputs) | `data/raw_elo/` |
| Attention proxies (Wikipedia daily + hourly, Google Trends, GDELT) and controls (ACWI, DXY, macro calendar, trading calendar) | `data/controls/` |

Because every result CSV is committed, **a reader with no data license can still regenerate
every figure and table in the paper offline** (`figures/make_figures.py` and
`paper/make_paper_figs.py` read only from `analysis/out/`). Every stochastic step pins a seed,
so the bootstrap p-values, the Monte-Carlo false-positive rate, and the injection power figures
reproduce bit-for-bit.

## What is withheld, and why

| Withheld (licensed — not redistributable) | Vendor | What it is |
|---|---|---|
| Futures 1-min trades + quote-bearing TAQ (ES, NQ, GC, CL, 6E, 6B, 6J); SPY OPRA options + greeks; US cash equities and country ETFs | **AlgoSeek** | the core intraday panel and the liquidity/options arms |
| National stock-index and currency daily series (the deep-history `indices_daily` / FX exports) | **TradingView / ICE** | the 20-index and 16-currency home-market panels |

These live under `data/market/` and `data/options_probe/` locally and are **git-ignored** so
they can never be pushed. Reproducing the arms that consume them requires an equivalent license
from the vendor; the `ingest/pull_*` and `ingest/parse_*` scripts document the exact products,
fields, and build steps so a licensee can recreate the inputs.

## Samples

Small illustrative samples of the licensed formats (a few rows showing the schema each
`parse_*` script expects) can be provided on request to `daniel@daru.finance`, to the extent
each vendor's license permits sample redistribution. AlgoSeek also publishes its own sample
files. Email is the right channel because the permissible sample scope is vendor-specific.

## Free sources, in full

Binance (`data.binance.vision`) — BTC/ETH spot and perpetual 1-min klines and funding;
Dukascopy — major-pair FX 1-min; Yahoo Finance — home-equity daily series for 26 nations;
Wikimedia, Google Trends, GDELT — attention proxies; Fjelstul World Cup Database — match
results, dates, eliminations 1930–2022; MSCI ACWI and the dollar index — market-return and
dollar controls (cached here for offline reproduction). All of these run without credentials.
