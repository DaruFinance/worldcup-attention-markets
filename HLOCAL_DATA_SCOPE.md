# Closing the $H_{\text{local}}$ Gap: Intraday Home-Exchange Data Scope

*The one test the World Cup paper bounds but cannot run, scoped with a pre-purchase power calculation.*
Daniel Gatto · daru.finance · 2026-06-14

---

## 1. The estimand, stated exactly

The Ehrmann–Jansen object is a **minute-level trade count on a nation's own cash exchange, whose marginal
trader is the local viewer**, during the in-play window of that nation's own World Cup match. The paper's
current $H_{\text{local}}$ arm matches at most two of those three features in any cell (CME currency
futures are minute-level but globally traded; country ETFs are minute-level but US-traded; home equities
have the right trader but only daily bars). No freely available data match all three. This document scopes
the paid pull that does, and pre-registers the test before any data is bought.

**Pre-registered specification.** For home exchange $e$ (mapping to nation $n(e)$), instrument $i$ on $e$,
and minute $t$ in local exchange time:
$$\log(\text{trades}_{it}) = \beta\,\text{OwnMatch}_{n(e),t} + \alpha_{i,\,w(t)} + \gamma_{d(t)} + \varepsilon_{it},$$
$\text{OwnMatch}=1$ when nation $n(e)$'s own team is in play and exchange $e$ is open; $\alpha_{i,w(t)}$ is
instrument $\times$ minute-of-week; $\gamma_{d(t)}$ is a date effect; SE clustered by date. Primary outcome
is **log trade count** (the literal Ehrmann–Jansen object), with log share volume and the quoted-spread/
depth liquidity outcomes as secondaries. Pre-committed verdict: $H_{\text{local}}$ is **rejected** if the
pooled $\beta$ excludes the $-30\%$ lower edge of the prior range; it is **confirmed** if $\beta\le-0.30$
at $p<0.05$ pooled; otherwise it is reported as the bound the achieved power supports. This rule is fixed
here, before purchase.

## 2. The binding constraint is power, not cost

The intraday own-exchange test only has observations where a nation's own match is **in play while its home
exchange is open**. Most kickoffs are evening or weekend in local time, when the exchange is shut, so the
schedule, not the data budget, sets the achievable sample. Counting own-team match in-play windows
$[\text{kickoff},\,\text{kickoff}+105\text{min}]$ that overlap the home exchange's regular session (weekday
only), 2010–2022 (`analysis/hlocal_feasibility.py`, run on the existing Fjelstul schedule):

| Exchange (nation) | own matches | **in-session** | 2010 | 2014 | 2018 | 2022 |
|---|---:|---:|---:|---:|---:|---:|
| B3 (Brazil) | 22 | **14** | 4 | 1 | 4 | 5 |
| BMV (Mexico) | 15 | **10** | 3 | 3 | 2 | 2 |
| BYMA (Argentina) | 23 | **8** | 1 | 2 | 2 | 3 |
| Euronext (Netherlands) | 19 | **8** | 3 | 2 | 0 | 3 |
| Euronext (Portugal) | 16 | **8** | 3 | 2 | 1 | 2 |
| Euronext (France) | 22 | **7** | 1 | 2 | 3 | 1 |
| Xetra (Germany) | 20 | **6** | 1 | 3 | 1 | 1 |
| SIX (Switzerland) | 15 | **6** | 2 | 1 | 1 | 2 |
| BME (Spain) | 18 | 4 | 1 | 1 | 0 | 2 |
| LSE (England), Euronext (Belgium), Borsa (Italy), JSE (S.Africa), GPW (Poland) | — | 2–3 each | | | | |
| **JPX (Japan), KRX (Korea), ASX (Australia), NGX (Nigeria)** | — | **0** | 0 | 0 | 0 | 0 |
| **Pooled, all exchanges** | | **83** | 22 | 21 | 17 | 23 |

Three facts decide the pull:

1. **Pooled, the test is powered.** 83 in-session own-match clusters is comparable to the currency arm
   (74) and equity-index arm (110). At a home-exchange trade-count standard error in the $0.05$–$0.07$
   log-point range (the level seen in every other arm), 83 clusters give a minimum detectable effect near
   $15$–$20\%$, well inside the $45$–$55\%$ Ehrmann–Jansen reports. A pooled null here genuinely bounds the
   local effect at its own resolution and trader; a pooled confirmation recovers it.
2. **Only the Americas and Europe matter.** Japan, Korea, Australia, and Nigeria contribute **zero**
   in-session overlaps across four tournaments, because Qatar/Russia kickoffs land in the Asian/Pacific
   evening or on weekends relative to those exchanges. No vendor fixes a timezone; **do not buy JPX, KRX,
   ASX, or NGX data for this test.** The purchase list is B3, BMV, BYMA, the Euronext venues, Xetra, SIX,
   BME, LSE, Borsa Italiana, JSE, GPW.
3. **Brazil is the one near-standalone.** B3 carries 14 in-session own matches, the best single-nation
   case; still under the $\sim30$-cluster floor, so reported within the pool, but B3 alone is the natural
   headline cut and the cheapest first buy.

## 3. Source matrix

The windows span 2010–2022, which rules out the free intraday feeds (yfinance 1-min retains $\sim30$ days;
Twelve Data / Marketstack free tiers similar). Three viable routes, cheapest first:

| Tier | Source | Coverage | Reaches | Cost | Gets us |
|---|---|---|---|---|---|
| **1 (pilot)** | EODHD *All-World Extended* 1-min intraday | B3, BMV, Euronext, Xetra, SIX, BME, LSE, JSE, GPW | $\sim$2020$\to$ (so **2022 only**) | $\sim$\$60–100/mo | $\sim$23 in-session clusters from 2022 alone $\Rightarrow$ MDE $\sim$25–30%, already a real test of the 45–55% effect at the right resolution/trader |
| **2 (full)** | LSEG/Refinitiv Tick History (TRTH) | all listed exchanges, tick $\to$ 1-min | 2010$\to$ | institutional | the full **83-cluster** test, MDE $\sim$15–20%, the definitive $H_{\text{local}}$ result |
| **2′ (à la carte)** | Per-exchange historical archives (B3 UP2DATA, Euronext, Deutsche Börse) | the bought exchange only | 2010$\to$ | moderate per exchange | Brazil-only or Europe-only deep history without a TRTH seat |

AlgoSeek (your existing entitlement) is US equity/options/futures and does not cover these venues; I did not
assume it. Bloomberg intraday history is capped below the 2010–2018 windows and is not a fit.

**Recommendation.** Run the **Tier-1 2022 pilot** first: it is cheap, it reaches the right resolution and
the right marginal trader, and 23 clusters already test the 45–55% effect. If the pilot is null (which the
rest of the paper predicts), escalate to **Tier 2** only if a $15\%$-MDE definitive bound is worth the
institutional cost; if the pilot shows a real decline, Tier 2 becomes mandatory to nail it across
tournaments.

## 4. What the outcome variable is, concretely

The Ehrmann–Jansen object is a **count of trades**, not dollar volume. Per exchange we pull 1-min bars for
the **main index constituents** (e.g.\ the Ibovespa names on B3, the CAC/AEX/PSI names on Euronext) and
aggregate the per-minute trade count across constituents, which reconstructs the exchange-level activity
series Ehrmann–Jansen used. Where a vendor only serves the index level, the index's own 1-min trade count
is the fallback. Share volume and, where the feed carries quotes, the quoted half-spread and depth are
pulled as secondaries so the liquidity channel is tested at the same resolution as the activity channel.

## 5. Pipeline (built, vendor-agnostic, ready for data)

Two scaffolds are in the repo and run the moment bars land, mirroring the existing matched-control engine:

- `ingest/pull_home_intraday.py` — a vendor adapter (EODHD and generic-CSV back ends) that maps
  nation $\to$ exchange $\to$ constituent tickers, pulls 1-min bars inside each tournament's $\pm21$-day
  window in the exchange's local timezone, and writes `data/market/home_intraday/<EXCH>_1m.parquet`.
- `analysis/hlocal_intraday.py` — the pre-registered regression above: builds OwnMatch from the Fjelstul
  schedule in each exchange's local time, applies the in-session filter, fits the matched-control FE with
  date-clustered SE, and reports the pooled $\beta$, its 95% CI and equivalence bound, the Brazil-only cut,
  and the per-exchange table, in the same format as Tables 2–3 of the paper.

Timezone handling is the one subtlety the scaffold gets right: kickoffs are converted to each exchange's
local clock, DST is resolved per date, and a minute enters the panel only inside the exchange's session, so
OwnMatch and the controls share the same trading calendar.

## 6. Threats specific to this pull

The local-trader assumption is itself approximate at the margin: B3 and Euronext carry foreign
institutional flow that does not watch the match, which biases any true effect toward zero, so a null here
bounds the effect *for the realised trader mix*, not for a hypothetical pure-local exchange. Index-
constituent trade counts aggregate names of differing liquidity, so the series is dominated by the largest
constituents; an equal-weight or index-level robustness cut is pre-committed. And the in-session sample,
though pooled-powered, is thin per nation, so per-exchange cells will over-reject exactly as the currency
per-nation cells do, and are reported with that flag rather than as findings.

## 7. The one thing I need from you

Which data route to use: a Tier-1 **EODHD-class subscription** (cheap, 2022 pilot, I can wire the API key
and pull within the session), a **TRTH/Refinitiv seat** if you have one (full 83-cluster test), or a
**per-exchange archive** purchase (Brazil-first). Name the route and, for the API options, drop a key where
I can read it, and the pipeline above runs end to end against it.
