# World Cup attention shocks across financial markets

Code to reproduce the empirical results in *When the World Watches Football: Bounds on the
Aggregate Attention Channel and the Limits of the World Cup Distraction Effect*.

The study asks whether the trading slowdown that Ehrmann and Jansen document on national
stock exchanges during a country's World Cup matches shows up in markets built differently:
crypto (spot and perpetual), index, commodity and currency futures, US-listed country ETFs,
and the daily home-market panels of 26 nations, 20 national indices, and 16 currencies. The
panel is one-minute data on eleven core instruments over the 2018 and 2022 tournaments, with
the futures and daily arms reaching back to 2010 and 1998. The 2026 tournament is held out of
every estimate and recorded live for an out-of-sample extension.

This repository holds everything needed to reproduce the paper except the raw licensed
market data: the full analysis and data-build code, every result CSV (`analysis/out/`), the
publication figures and the manuscript (`paper/`), and all free / public-source / derived data
(`data/`). The only series withheld are those licensed from paid vendors (AlgoSeek, and the
TradingView/ICE index and currency exports), which cannot be redistributed. With those in
hand the pipeline reproduces end to end; without them, every figure and table still
regenerates from the committed result CSVs. See [`DATA.md`](DATA.md) for the full
data-availability statement and what a non-licensee can and cannot reproduce.

## Layout

```
ingest/        pull and build the match spine, market data, attention proxies, and controls
analysis/      estimate every channel; each script writes one CSV to analysis/out/
collectors/    live recorder for the 2026 crypto microstructure (order book, OI, funding, liquidations)
figures/       render the publication figures from the analysis/out CSVs
update_2026.py  one command to refresh the panel and the 2026 out-of-sample estimates
```

## Data

All free, public-source, and derived data **is** committed under `data/` (the match spine and
goal timestamps, Fjelstul/Elo/FIFA-ranking inputs, attention proxies, the ACWI/DXY controls,
and every result in `analysis/out/`). The raw **licensed** market data is not, because the
vendor licenses forbid redistribution; the table below marks each source. Set `WC_INDEX_DIR`
to point the daily index and currency loaders at your own licensed exports.

| Source | Series | Access |
|---|---|---|
| AlgoSeek | futures (ES, NQ, GC, CL, 6E, 6B, 6J) 1-min trades and quote-bearing TAQ; SPY options (OPRA, greeks); US cash equities and country ETFs | licensed; not redistributable |
| Binance (`data.binance.vision`) | BTC/ETH spot and perpetual 1-min klines; funding | public |
| Dukascopy | major FX pairs, 1-min | public |
| Yahoo Finance | home-equity daily series for 26 nations | public |
| TradingView / ICE exports | national index and currency daily series (place under `data/market/indices_daily/`) | user export |
| Wikimedia, Google Trends, GDELT | attention proxies | public |
| Fjelstul World Cup Database | match results, dates, eliminations 1930 to 2022 | public |
| MSCI ACWI, DXY | market-return and dollar controls (cached for offline reproduction) | public |

Scripts read from a `data/` tree under the repository root. Set `WC_INDEX_DIR` to point the
daily index and currency loaders somewhere else. Expected layout:

```
data/
  matches/        match spine, goal timestamps, Fjelstul export
  market/
    crypto/         Binance 1-min klines
    futures/        parsed AlgoSeek futures 1-min
    taq_raw/        AlgoSeek TAQ (futures, equity)
    liquidity/      per-instrument spread and depth
    options/        AlgoSeek OPRA and greeks
    equity/         US cash equities and country ETFs
    equities_intl/  Yahoo home-equity series
    indices_daily/  TradingView/ICE index and currency daily CSVs
    fx_spot/        Dukascopy 1-min
    panel/          all_panel.parquet (the unified estimation panel)
  controls/         ACWI, DXY, Google Trends, GDELT, macro calendar, VIX
analysis/out/       result CSVs
```

## Reproducing the results

```
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Then, in order:

1. **Build the inputs.** Run the `ingest/` scripts for the sources you have access to. The
   free arms (crypto, FX, Yahoo equities, attention, the match spine) run without credentials;
   the AlgoSeek arms need an entitlement and are metered. `ingest/build_matches_all.py` and
   `ingest/build_goals.py` build the event spine; the `pull_*` and `parse_*` scripts build the
   market series.
2. **Assemble the panel.** `analysis/build_panel.py` and `analysis/build_panel_crypto.py` write
   `data/market/panel/all_panel.parquet`.
3. **Estimate.** Each `analysis/` script is self-contained, reads the panel and the relevant
   inputs, and writes one CSV to `analysis/out/`. The headline cells are
   `regress_crossmarket.py` (aggregate channel), `pooled_domestic.py` and `own_team_4tourn.py`
   (own-team), `liquidity.py`, `options_analysis.py`, `comovement.py` with
   `artifact_montecarlo.py` (the composition artifact), `equities_extended.py`,
   `fx_exotic_extended.py` and `home_equities.py` (home-market and loser effect),
   `equivalence_tost.py` and `hypothesis_split.py` (bounds), `wild_bootstrap.py` and
   `pooled_bootstrap.py` (few-cluster inference), `injection_power.py` (positive control),
   `sentiment.py`, `pre_trend.py`, `robustness_macro.py`, and `master_fdr.py`.
4. **Figures.** `figures/make_figures.py` renders the publication figures from the CSVs.

`update_2026.py` chains the crypto refresh, panel build, and 2026 out-of-sample estimate for
use while that tournament is in progress.

## Notes on inference

Every estimate compares a match minute to the same instrument at the same minute of the same
weekday on non-match days, with an instrument-by-minute-of-week fixed effect, a calendar-date
fixed effect, and standard errors clustered by date, so the effective sample size is the
number of match-days. Cells resting on few match-day clusters are read through a wild-cluster
restricted bootstrap rather than the asymptotic p-value. Nulls are reported with equivalence
bounds (two one-sided tests against a 30% margin) and a positive-control injection that
confirms the design recovers a 30 to 45% effect at the realized cluster counts. Random seeds
are fixed in every script that resamples, and the control series are cached so the regressions
run offline.
