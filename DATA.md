# Data availability

This repository ships **code and results, not data**. It contains the full analysis and
data-build pipeline, every result table the figures are drawn from (`analysis/out/*.csv`), and
a synthetic-sample generator. No market data is distributed — neither the licensed series nor
the free ones — to keep the repository a clean code package and to stay within the vendor
licenses. The real inputs are rebuilt from the sources documented below.

## What is in this repository

| Committed here | Path |
|---|---|
| All analysis and data-build code | `analysis/`, `ingest/`, `collectors/`, `figures/` |
| Every result (regression cells, equivalence bounds, Monte-Carlo and bootstrap output) | `analysis/out/*.csv` |
| Synthetic-sample generator (runnable demo, no real data) | `synthetic_sample.py` |

Because every result table is committed, **a reader with no data can still regenerate every
figure offline** (`figures/make_figures.py` reads only from `analysis/out/`). Every stochastic
step pins a seed, so the bootstrap p-values, the Monte-Carlo false-positive rate, and the
injection power figures reproduce bit-for-bit. To exercise the estimation pipeline itself
without any data, run `python synthetic_sample.py` — it writes a schema-correct synthetic panel
to the git-ignored `data/` tree — then any cross-market script; the synthetic panel has a zero
during-match effect by construction, so its output carries no meaning.

## Rebuilding the real inputs

No `data/` is shipped; the scripts read from a git-ignored `data/` tree you build from the
sources below. The `ingest/pull_*` and `ingest/parse_*` scripts document the exact products,
fields, and build steps.

**Free / public (run without credentials):** Binance (`data.binance.vision`) — BTC/ETH spot and
perpetual 1-min klines and funding; Dukascopy — major-pair FX 1-min; Yahoo Finance — home-equity
daily series for 26 nations; Wikimedia, Google Trends, GDELT — attention proxies; Fjelstul World
Cup Database — match results, dates, eliminations 1930–2022; international football results / Elo
inputs; MSCI ACWI and the dollar index — market-return and dollar controls.

**Licensed (require a vendor entitlement — not redistributable):**

| Series | Vendor | What it is |
|---|---|---|
| Futures 1-min trades + quote-bearing TAQ (ES, NQ, GC, CL, 6E, 6B, 6J); SPY OPRA options + greeks; US cash equities and country ETFs | **AlgoSeek** | the core intraday panel and the liquidity/options arms |
| National stock-index and currency daily series (deep-history index / FX exports) | **TradingView / ICE** | the 20-index and 16-currency home-market panels |

## Samples

Small illustrative samples of the licensed formats (a few rows showing the schema each
`parse_*` script expects) can be provided on request to `daniel@daru.finance`, to the extent
each vendor's license permits. AlgoSeek also publishes its own sample files.
