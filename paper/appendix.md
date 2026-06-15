# Appendix

All estimates use the core identification: outcome `Y` on a `Match` indicator with fixed effects
`instrument × (weekday × minute-of-day) + date`, standard errors clustered by date, on completed
tournaments only (2026 is ongoing and excluded from estimation). Match-in-progress for a match is the
minute window `[kickoff, kickoff + 105 min)`. Futures/equity samples use 2010, 2014, 2018, 2022;
crypto uses 2018, 2022 (Binance data begins 2017).

## A.1 Instruments

### A.1.1 Five market groups (1-minute, UTC, 2010–2026 where available)

| Market group | Instruments | Source kind |
|---|---|---|
| Equity-index futures | ES (E-mini S&P 500), NQ (E-mini Nasdaq-100) | futures |
| Commodity futures | GC (gold), CL (WTI crude) | futures |
| FX futures | 6E (EUR/USD), 6B (GBP/USD), 6J (JPY/USD) | futures |
| Crypto spot | BTCUSDT, ETHUSDT (Binance spot) | crypto (2018–) |
| Crypto perpetual | BTCUSDT, ETHUSDT (Binance perp) | crypto (2018–) |

Futures fields: `ts, open, high, low, close, volume, count, buy, sell`.
Crypto fields: `ts, open, high, low, close, volume, quote_volume, count, taker_buy_base, taker_buy_quote`.

### A.1.2 Cash equities (1-minute, US regular hours ET 09:30–16:00, 2010–2026)

US broad-market ETFs: SPY, QQQ, IWM.
Country ETFs (national markets): EWZ (Brazil), EWW (Mexico), EWU (UK), EWG (Germany), EWQ (France),
EWP (Spain), EWJ (Japan), ARGT (Argentina), EWY (Korea).
Fields: `ts, open, high, low, close, volume, count`. Cash-equity tests apply a regular-trading-hours
filter and a matched same-weekday/clock control on non-match days (a naive all-session specification
produces a spurious positive volume effect and is reported as an artifact, not a result).

## A.2 Variable definitions

All outcomes are computed on the FULL per-instrument 1-minute series before restricting to tournament
windows, so no statistic describing minute `t` uses information from `t` or later.

| Variable | Definition |
|---|---|
| `lvol` | log dollar (crypto: `quote_volume`) or contract (futures/equity: `volume`) volume per minute; `NaN` where volume = 0 |
| `ltrades` | log trade count per minute (`count`); `NaN` where count = 0 |
| `lavg_trade` | log average trade size = `log(volume / count)` |
| `absret` | absolute one-minute log return `|log(close_t / close_{t-1})|` |
| `sqret` | squared one-minute log return |
| `hlrange` | high–low range = `log(high / low)` (volatility proxy) |
| `amihud` | Amihud illiquidity = `|absret| / volume × 1e9` |
| `signed_imb` | signed aggressor imbalance = `(buy − sell) / (buy + sell)`; crypto uses `taker_buy_quote` for buy |
| `comovement` | mean pairwise correlation of one-minute returns across instruments open in a match block (kickoff → +105 min) vs matched control blocks; reported composition-free (constant-instrument and fully-open subsets) because raw average correlation depends on which instruments are open |
| `VR` | `k`-step variance ratio (here `VR(5)`); `|VR − 1|` is the inefficiency measure (deviation from random walk) |
| `basis` | crypto spot–perp basis in basis points, `log(perp / spot)`; reported as level and intraday volatility |

## A.3 Country → market mapping

`own` flags mark the minute as one in which the indicated country's national team is in a match in
progress; the pooled domestic / triple-difference tests map only the index/FX futures.

| Country / region | FX & index futures | ETFs / cash equity |
|---|---|---|
| USA | ES, NQ | SPY, QQQ, IWM |
| Euro-area (DE/FR/ES) | 6E | EWG, EWQ, EWP |
| UK (England / Scotland) | 6B | EWU |
| Japan | 6J | EWJ |
| Brazil | — | EWZ |
| Mexico | — | EWW |
| Argentina | — | ARGT |
| Korea Republic | — | EWY |

## A.4 Consolidated robustness table

Volume (`lvol`) is the headline outcome throughout. Coefficients are log points; `%` is
`expm1(coef) × 100`. Numbers read directly from `analysis/out/*.csv`.

### A.4.1 Placebo treatments (`reg_placebo.csv`)

Match windows shifted by a fake offset; a genuine effect should vanish — and the true-window null
should not suddenly become significant under a shift. All offsets are null.

| Outcome | Shift | coef | SE | p | N |
|---|---|---|---|---|---|
| lvol | +1 day | 0.0241 | 0.0415 | 0.563 | 619,741 |
| lvol | +3 h | −0.0764 | 0.0486 | 0.118 | 619,741 |
| lvol | −1 day | −0.0417 | 0.0371 | 0.263 | 619,741 |
| ltrades | +1 day | 0.0139 | 0.0339 | 0.681 | 619,741 |
| ltrades | +3 h | −0.0712 | 0.0392 | 0.072 | 619,741 |
| ltrades | −1 day | −0.0305 | 0.0306 | 0.321 | 619,741 |

### A.4.2 Macro-release exclusion (`robustness_macro.csv`, lvol)

Dropping minutes around scheduled macro releases barely moves any group coefficient; every group
stays null.

| Market group | Sample | coef | SE | p | N |
|---|---|---|---|---|---|
| crypto_spot | baseline | −0.0272 | 0.0363 | 0.455 | 415,261 |
| crypto_spot | ex-macro | −0.0303 | 0.0328 | 0.357 | 409,831 |
| crypto_perp | baseline | −0.0398 | 0.0696 | 0.569 | 204,480 |
| crypto_perp | ex-macro | −0.0612 | 0.0625 | 0.331 | 201,584 |
| equity_fut | baseline | −0.0298 | 0.0698 | 0.671 | 220,174 |
| equity_fut | ex-macro | −0.0368 | 0.0675 | 0.587 | 216,555 |
| commodity_fut | baseline | 0.0699 | 0.0665 | 0.296 | 221,928 |
| commodity_fut | ex-macro | 0.0554 | 0.0633 | 0.383 | 218,308 |
| fx_fut | baseline | 0.1043 | 0.0658 | 0.116 | 325,733 |
| fx_fut | ex-macro | 0.0951 | 0.0594 | 0.112 | 320,308 |

### A.4.3 Alternative match windows (`robustness_windows.csv`, lvol)

Re-defining the treated window (pre-match, halves, post-match) leaves every window null.

| Window | coef | SE | p | % |
|---|---|---|---|---|
| in-match (default) | 0.023 | 0.0438 | 0.600 | +2.33 |
| pre −60…0 | −0.0215 | 0.0299 | 0.473 | −2.12 |
| first half | 0.0539 | 0.0408 | 0.189 | +5.54 |
| second half | −0.0048 | 0.0389 | 0.901 | −0.48 |
| post +60 | −0.0531 | 0.0395 | 0.181 | −5.17 |

### A.4.4 Pre-trend / event-time (`pre_trend.csv`, lvol)

Coefficients in 15-minute bins relative to kickoff. No pre-match trend; the during/post bins are
indistinguishable from zero except a single marginal point at +105 min (`p = 0.041`, uncorrected),
consistent with noise across 16 bins.

| Bin (min) | Phase | coef | SE | p |
|---|---|---|---|---|
| −120 | pre | 0.0052 | 0.0578 | 0.928 |
| −60 | pre | −0.0217 | 0.0579 | 0.709 |
| −15 | pre | −0.0643 | 0.0649 | 0.323 |
| 0 | during/post | −0.0267 | 0.0744 | 0.721 |
| +60 | during/post | −0.0633 | 0.0567 | 0.266 |
| +105 | during/post | −0.1244 | 0.0604 | 0.041 |

(Full 16-bin series in `analysis/out/pre_trend.csv`.)

### A.4.5 Equivalence bounds (`equivalence_bounds.csv`, lvol)

90% two-one-sided-test interval on the volume effect, in %. The pooled estimate rules out volume
moves outside roughly ±6–12% — far smaller than the tens-of-percent national-equity drops in the
single-market literature, but not a tight zero.

| Group | point % | lo % | hi % |
|---|---|---|---|
| ALL | 2.33 | −6.09 | 11.51 |
| crypto_spot | −2.68 | −9.37 | 4.50 |
| crypto_perp | −3.90 | −16.16 | 10.15 |
| equity_fut | −2.93 | −15.34 | 11.29 |
| commodity_fut | 7.24 | −5.86 | 22.16 |
| fx_fut | 11.00 | −2.42 | 26.26 |

### A.4.6 Pooled domestic / own-team, four tournaments (`own_team_4tourn.csv`, lvol & ltrades)

Index/FX futures (ES, NQ → USA; 6E → euro; 6B → GB; 6J → Japan), 2010–2022. The own-team point
estimate is positive (≈ +9% volume) but insignificant (`p = 0.18`) across 60 own-team treated
date-clusters.

| Outcome | Term | coef | SE | p | % | own treated dates | N |
|---|---|---|---|---|---|---|---|
| lvol | foreign_match | −0.0044 | 0.0533 | 0.934 | −0.44 | 60 | 1,064,189 |
| lvol | own_match | 0.0857 | 0.0642 | 0.183 | +8.95 | 60 | 1,064,189 |
| ltrades | foreign_match | −0.0064 | 0.0552 | 0.907 | −0.64 | 60 | 1,064,189 |
| ltrades | own_match | 0.0988 | 0.0725 | 0.175 | +10.39 | 60 | 1,064,189 |

### A.4.7 Triple-difference: own-team × knockout (`triple_diff.csv`, lvol)

Does the own-team response strengthen in high-importance (knockout) matches? The triple term
`match:own:knock` is the difference-in-difference-in-differences. It is negative and insignificant
(`p = 0.25`) and rests on only 19 own-team-knockout treated date-clusters, so it is underpowered and
should not be read as evidence either way.

| Term | coef | SE | t | p | % | N |
|---|---|---|---|---|---|---|
| match (base) | −0.0191 | 0.0596 | −0.321 | 0.748 | −1.90 | 1,064,189 |
| match:own | 0.1149 | 0.0547 | 2.103 | 0.037 | +12.18 | 1,064,189 |
| match:knock | 0.0694 | 0.1332 | 0.521 | 0.603 | +7.19 | 1,064,189 |
| match:own:knock (DDD) | −0.1169 | 0.1010 | −1.158 | 0.248 | −11.04 | 1,064,189 |

Treated date-clusters: own = 60, knockout = 20, own-AND-knockout = 19 (2,350 own-knockout treated
minutes).

## A.5 Figures

- `fig1_kickoff.png` — event-time volume around kickoff.
- `fig2_bymarket.png` — Match effect by market group.
- `fig3_domestic.png` — own-team vs foreign-team match volume effect, by grouping (4-tournament,
  2-tournament all-mapped, FX-only), 95% CI.
- `fig4_knockout.png` — knockout-vs-group-stage heterogeneity.
- `fig5_goal.png` — event-time volume around goals.
- `fig6_by_tournament.png` — own-team match volume effect estimated separately by tournament
  (2010 / 2014 / 2018 / 2022), 95% CI, with the 4-tournament pooled reference. Replaces the dropped
  2026 figure (the 2026 World Cup is ongoing and excluded from estimation). The per-tournament
  estimates straddle zero with wide CIs (14–16 own-team treated date-clusters each), consistent with
  the pooled null.
