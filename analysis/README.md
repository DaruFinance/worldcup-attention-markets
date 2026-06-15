# analysis

Each script reads the panel and the relevant inputs and writes one CSV to `analysis/out/`.
Grouped by what they estimate.

**Panel build**
- `build_panel.py`, `build_panel_crypto.py` assemble `data/market/panel/all_panel.parquet`.

**Aggregate channel (during-match effect)**
- `regress_crossmarket.py`, `regressions.py` cross-market during-match effects and 2026 OOS.
- `event_study.py` kickoff and goal-centered event curves; the goal-window regression.
- `breadth.py` the 29-instrument breadth check.

**Own-team and home markets**
- `pooled_domestic.py`, `own_team_4tourn.py` pooled own-team effect, two and four tournaments.
- `fx_home_country.py`, `fx_exotic_extended.py` currency arm, per-nation and pooled.
- `home_equities.py`, `equities_extended.py` daily home equities and the loser effect.
- `cash_equity.py`, `cash_equity_4tourn.py` US-listed cash equities and country ETFs.
- `triple_diff.py`, `domestic_attention.py` knockout and attention-scaled own-team cuts.

**Other channels**
- `liquidity.py` quoted spread and depth (TAQ).
- `options_analysis.py` option volume, implied vol, skew.
- `comovement.py` with `artifact_montecarlo.py` the comovement decline and its composition artifact.
- `efficiency.py` variance ratios, basis, lead-lag.
- `intensity.py`, `stakes.py` closeness, extra time, must-win.
- `sentiment.py` post-match win/loss returns.
- `fx_spot_test.py` retail spot FX quote activity.

**Attention validation**
- `attention_validation.py`, `attention_final.py`, `attention_hourly.py` Wikipedia daily ratio
  and the intraday reconstruction of the 2022 final.

**Inference and bounds**
- `equivalence_tost.py`, `validate_and_bounds.py`, `hypothesis_split.py` equivalence bounds,
  minimum detectable effects, and the two-hypothesis classification.
- `wild_bootstrap.py`, `pooled_bootstrap.py` wild-cluster restricted bootstrap for few-cluster cells.
- `injection_power.py` positive-control injection (does the design recover a known effect).
- `pre_trend.py`, `robustness_macro.py`, `robustness_windows.py` placebo, pre-trend, macro
  exclusion, aggregation.
- `master_fdr.py` the global multiple-testing pool.

**Home-market feasibility (paid intraday extension)**
- `hlocal_feasibility.py`, `hlocal_intraday.py` in-session cluster counts and the pre-registered
  intraday own-exchange test, vendor-agnostic, ready to run on a data route.

**Tables and figures**
- `make_tables.py`, `make_figures.py`, `make_figures2.py`, `extra_figures.py`,
  `summary_table.py`, `build_tv_audience.py`.
