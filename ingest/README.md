# ingest

Builds the event spine and pulls the market data, attention proxies, and controls into the
`data/` tree. Each script is independent and writes its outputs under `data/`.

**Match spine and events**
- `build_matches.py`, `build_matches_all.py`, `build_matches_hist.py` build the schedule,
  kickoff times, team-to-market map, and per-minute match state.
- `build_goals.py` reconstructs goal timestamps from match-clock minutes and stoppage offsets.
- `fetch_match_events.py`, `fetch_match_enrichment.py`, `build_elo.py`, `fetch_odds.py`,
  `fetch_odds_retry.py` add events, pre-match Elo, and bookmaker odds.
- `refresh_matches.py` re-pulls the 2026 schedule while that tournament runs.

**Markets**
- Crypto: `backfill_crypto.py`, `expand_crypto.py` (Binance klines and funding).
- Futures: `pull_futures_windows.py` then `parse_futures.py` (AlgoSeek).
- Liquidity: `pull_taq_liquidity.py` then `parse_taq_liquidity.py`; `probe_liquidity_and_brl.py`.
- Options: `pull_options.py`, `pull_options_spill2023.py`, `options_probe.py` (AlgoSeek OPRA).
- Cash equities and country ETFs: `pull_equity_windows.py` then `parse_equity.py`.
- Extra instruments (rates, metals, energy, more indices): `pull_extra_instruments.py`,
  `parse_extra_instruments.py`, `parse_extra.py`.
- FX spot: `pull_fx_spot.py` (Dukascopy).
- Home markets: `pull_intl_equities.py` (Yahoo daily), `pull_exotic_fx_daily.py`,
  `pull_home_intraday.py` (vendor-agnostic intraday adapter; set `EODHD_API_KEY` or
  `HOME_INTRADAY_CSV_DIR`).
- `fetch_vix_brl.py`.

**Attention and controls**
- `fetch_wikipedia.py`, `fetch_trends_gdelt.py` (attention proxies).
- `build_macro_calendar.py` (macro-release exclusion windows).
- `build_constructs.py`.
