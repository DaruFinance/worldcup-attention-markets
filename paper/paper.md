# When the World Watches Football: Attention Shocks Across Financial Markets
### Evidence from Cryptoassets, Equity-Index Futures, Commodities, and FX

**Daniel Gatto** · daru.finance · draft 2026-06-13

---

## Abstract

FIFA World Cup matches are among the largest synchronized attention events in the world, and
prior work reports that trading in a country's own stock market falls sharply while its team
plays. We ask whether that distraction effect survives in markets built differently: globally
traded, nearly-continuous, derivative, and retail-heavy venues. Using one-minute data on eleven
instruments across five market structures — Bitcoin and Ether (spot and perpetual), E-mini S&P 500
and Nasdaq-100 futures, gold and crude futures, and CME euro, sterling, and yen futures, plus a
separate cash-equity arm of US and single-country ETFs — over the 2018 and 2022 tournaments (128 matches, 341 dated goals; 1.4 million instrument-minutes in the
estimation window, 1.63 million across the full assembly including the ongoing 2026 tournament), we
compare each match-minute against the same instrument at the same minute-of-week on non-match days.
Wikipedia pageviews confirm the tournament is highly salient at the daily level — tournament-article
views run 5.7 to 8.0 times their off-tournament baseline and rise with the daily match count — and the
matches draw television audiences in the hundreds of millions, so the during-match windows are
high-attention by construction. Yet we find no commensurate market response. The average during-match
effect on trading volume is economically small and statistically indistinguishable from zero in every
market group, and survives no multiple-testing correction. Even cross-market return comovement — the
channel the original studies emphasize — shows no decline once we hold fixed which instruments are
trading: the naive measure that appears to fall during matches (−0.086, p = 0.005) is a composition
artifact that vanishes within the constant-instrument crypto set (+0.01, not significant). Cash
equities — the literature's own venue — are null too in regular trading hours (US broad-ETF volume
−6%, n.s.); a naive specification that includes thin pre/post-market bars yields a spurious +19%,
another composition artifact. For the markets with no national mapping
(crypto, gold, crude) the estimates are tight enough to exclude the 30–50% declines reported for
national cash equities — for crypto we rule out during-match volume declines beyond about 9% — so the
effect does not generalize to global, continuously-traded, or derivative venues. The structurally
comparable test, a home team's own currency or index futures, is individually underpowered (two to six
match-days per market); pooled across markets the own-team effect is a non-significant **+11%**
(minimum detectable effect ≈ 23%), if anything the wrong sign for distraction and driven almost
entirely by euro-area matches. Single-market effects that look dramatic (sterling −34%, Nasdaq +35%)
rest on two to six match-days and do not withstand honest inference. Extending the home-market test as far
as free data allows — home equities for 26 nations, 20 national stock indices back to 1998, and 16 home
currencies (Brazil included, six tournaments, each gated at its float date — 1998 for developed units,
2000–2007 for the rest), pooled into 60–110 match-day clusters — finds
no match-day distraction (home volume null, bounded below ~15%) and no Edmans–García–Norli loser effect in
either stocks or currencies; the hypothesis that the effect concentrates in small, retail-dominated
markets is correctly signed in one measure but reverses in another and is never significant. We read the
evidence as a bounded
non-generalization of the distraction effect to modern market structures, alongside an inconclusive
null in the venues where it was originally found. The null is consistent across every channel we
measure — liquidity (quoted spreads flat and depth essentially unchanged across 2.2 million
instrument-minutes of bid/ask data), options (implied vol, 25-delta skew and option volume all flat),
match intensity (closeness, extra time, penalties), price efficiency (variance ratios, spot–futures
and spot–perp basis, lead–lag, abnormal returns), and post-match sentiment (win/loss returns) — each
indistinguishable from zero, and the effect does not grow on the highest-attention days. Estimation uses the completed 2010–2022 tournaments; the
ongoing 2026 World Cup is excluded, though a live collector is recording it for a future extension.

---

## 1. Introduction

When a national team plays in the World Cup, a large share of a country's population stops what it
is doing and watches. If some of those people are also traders, market activity should fall while
the match is on. Several studies find exactly this in national stock markets: Ehrmann and Jansen
(2017) document that trading volume on a country's exchange drops substantially during its team's
matches, and that the cross-market comovement of returns weakens, consistent with investors
processing less information. Edmans, García, and Norli (2007) show that football results move
national stock returns through mood. The common thread is that a synchronized attention shock,
external to fundamentals and precisely timed, leaves a fingerprint on trading.

That literature is built almost entirely on national cash-equity markets — venues that are
segmented by geography, open only during local business hours, and dominated by domestic
participants. Modern markets are not all like that. Cryptoassets trade continuously, worldwide, and
with heavy retail participation. Index, commodity, and currency futures trade nearly around the
clock on globally integrated, highly automated venues where the marginal participant is rarely a
fan of any one team. Whether the distraction effect generalizes to these structures is an open
empirical question, and it is the question this paper answers.

We assemble one-minute data on eleven instruments spanning five market structures and align them to
the universe of World Cup matches for 2018, 2022, and the ongoing 2026 tournament. Our identification
is deliberately simple and transparent: we compare a match-minute to the same instrument at the same
minute-of-week on non-match days within the same tournament window, which removes each instrument's
normal intraday and weekly seasonality — the feature that would otherwise let a quiet trading hour
masquerade as a match effect.

Our findings are mostly null, and we think the nulls are the contribution. First, we validate that
the treatment is real: Wikipedia tournament-article pageviews run 5.7 to 8.0 times their
off-tournament baseline and rise with the number of matches in a day. Second, despite that
demonstrable attention, the average during-match effect on volume, trade count, and volatility is
near zero in every market group and survives no false-discovery correction. Third, the best-powered
test of a domestic-team effect — pooling all mapped markets across 28 treated match-days, though able
to detect only effects above roughly 23% and dominated by euro-area matches — returns a non-significant
**+11%**, pointing if anything toward slightly *more* activity when the home team plays, not less.
Fourth, for the markets the original theory never predicted would respond, the estimates are tight
enough to rule out the large declines reported for national cash equities, bounding how far the effect
generalizes. Where individual markets do show striking coefficients
(sterling futures volume −34% when England or Scotland plays), they rest on a handful of match-days
and dissolve under proper inference; we report them as cautions, not findings.

The contribution is therefore (i) the first intraday, multi-market-structure test of World Cup
attention effects, covering crypto and electronic derivatives alongside the equity complex; (ii) a
power-bounded null measured against a day-level-validated and audience-corroborated attention shock —
formalized with equivalence tests and a global multiple-testing correction across 158 estimates —
which is more informative than an unbounded "no effect"; (iii) a methodological caution that we think
generalizes beyond this setting: two natural ways to measure an attention effect — cross-market return
comovement, and trading activity pooled over sessions — each *manufacture* a spurious, significant
"distraction" result that exactly mimics the prior literature, and each is shown to be a composition
artifact (of which instruments, or which session, enters the average) that vanishes under the right
control; and (iv) an open data pipeline, including a live collector recording the 2026 tournament's
microstructure (depth, open interest, funding, liquidations) for out-of-sample use.

## 2. Related literature

Three strands connect. The *investor-attention* literature (Barber and Odean 2008; Da, Engelberg,
and Gao 2011) shows that shifts in attention move trading and prices. The *sports-sentiment*
literature (Edmans, García, and Norli 2007; Kaplanski and Levy 2010) links match outcomes to
returns through mood. Closest to us, the *World Cup distraction* literature (Ehrmann and Jansen 2017)
finds large drops in national-market trading and weaker return comovement during a country's
matches. We depart from this work in venue rather than method: instead of one national cash market,
we test whether the same precisely-timed shock registers across market structures that differ in
hours, automation, investor base, and geographic segmentation, and we add the modern crypto and
2026 evidence those papers could not.

### 2.1 Hypotheses
We pre-designate the hypotheses the design tests, and the primary outcomes for each. **H1 (activity):**
trading volume and trade counts fall during match windows. **H3 (volatility):** intraday volatility
changes during matches, sign unspecified. **H4 (price efficiency):** cross-market return comovement
weakens during matches. **H5 (structure):** effects differ across market structures (continuous/retail
vs exchange-hours/institutional, spot vs derivative). **H6 (domestic team):** effects are stronger
when the market's mapped national team plays. **H7 (importance):** knockout matches move markets more
than group matches. **H8 (intensity):** goals and acute moments amplify the during-match effect. H1
and H3 are the primary activity/volatility tests; H4–H8 are the mechanism and heterogeneity tests.
**H9 (sentiment):** post-match returns weaken after a loss. **H2 (liquidity)** — that quoted spreads
widen and depth thins — is tested directly from AlgoSeek's quote-bearing TAQ products (per-minute
bid/ask, spread, and depth for all four tournaments); the live 2026 microstructure collector adds
order-book depth and liquidations at finer granularity for a future extension.

## 3. Data

### 3.1 Attention events
The event spine is every World Cup match for the completed tournaments 2010 (South Africa, 64),
2014 (Brazil, 64), 2018 (Russia, 64), and 2022 (Qatar, 64). The cross-market panel that anchors the
headline results uses 2018 and 2022 (the period over which all market structures, including crypto,
coexist); the own-team, intensity, efficiency, and sentiment tests extend to 2010 and 2014 for the
instruments that predate crypto. The 2026 tournament is **ongoing as we write and is excluded from
all estimates** (§5.7); a live collector records it for a future extension only. Each match carries
its scheduled UTC kickoff, venue and time zone, stage, teams, and score, and is enriched with a
pre-match World Football Elo rating (favourite, closeness), extra-time/penalty flags, and — for 2022,
the only tournament with reproducible free data — closing bookmaker odds.
We add minute-level structure (pre-match −60→0, first half 0→45, halftime, second half, post-match
to +60) and, for 2018 and 2022, 341 goal timestamps reconstructed from match-clock minutes plus
stoppage offsets and the halftime break. Each match is mapped conservatively to the markets exposed
to the relevant trading population: the United States to the S&P 500 / Nasdaq complex; euro-area
members (dated per tournament — the Netherlands enters 2022, Croatia and Austria 2026) to the euro;
England and Scotland to sterling; Japan to the yen. Gold, crude, and the cryptoassets carry no
national mapping and serve as global comparison markets.

### 3.2 Markets
We group by structure, because structure is the question.

| group | instruments | structure |
|---|---|---|
| Crypto spot | BTC, ETH spot (Binance) | continuous, global, retail-heavy |
| Crypto perp | BTC, ETH USDⓈ-M perpetual | continuous, leveraged, retail-heavy |
| Equity futures | ES, NQ (CME) | near-24h, institutional |
| Commodity futures | GC, CL (CME) | near-24h, global |
| FX futures | 6E, 6B, 6J (CME) | near-24h, automated, globally integrated |
| Cash equities | SPY, QQQ, IWM + 9 country ETFs (AlgoSeek) | exchange-hours, the literature's venue |

The first five groups form the core cross-market panel; cash equities are analyzed separately
(§5.2a) because they trade only in US hours. Crypto one-minute bars come from data.binance.vision and carry dollar volume, trade count, and
taker-buy volume; spot covers all three tournaments and the perpetual enters in 2022. Futures
one-minute trade bars come from AlgoSeek, front contract by daily volume. All series are restricted
to ±21 days around each tournament so controls share the instrument's own regime. A structural fact
shapes interpretation: many World Cup matches fall on weekends, when futures are closed and crypto
is the only open venue, so the futures during-match sample concentrates in weekday and
Sunday-Globex matches.

For the live 2026 tournament a separate collector records, every minute, order-book depth, best
bid/ask, open interest, funding, mark/index, and forced liquidations for BTC and ETH spot and
perpetual — data Binance does not archive — so that the out-of-sample extension can study liquidity
and leverage directly.

The home-market arm (§5.2e) draws on three additional daily sources, the finest resolution freely
available for foreign venues. Home equities for 26 nations (main index plus top-capitalization names,
101 series, 2009–2023) come from the Yahoo Finance daily feed. Twenty national stock indices with deep
history (1998–2022, several to the early 1990s) and sixteen home currencies (gated at each unit's float
date: 1998 for the five developed units and South Korea, 2000–2007 for the rest (Brazil from 2002), 2015 for the rouble) come from
TradingView/ICE daily exports; each currency is gated at its post-float or post-redenomination date, and
Argentina (1991–2001 dollar peg) and the pre-2005 Turkish lira (redenomination) are excluded as
untestable. Match results, dates, and eliminations for tournaments back to 1998 come from the Fjelstul
World Cup database. Index returns are world-market (ACWI) adjusted and currency returns are normalized to
the dollar value of the local unit, so that a negative return denotes home-currency depreciation.

### 3.3 Outcomes
Per instrument-minute: log dollar (or contract) volume, log trade count, and average trade size;
absolute and squared one-minute returns and the high–low range as volatility proxies; the Amihud
illiquidity ratio; and a signed aggressor imbalance. Outcomes are in logs so the Match coefficient
is a comparable percentage change across instruments regardless of native units.

## 4. Methodology

The core comparison is a match-minute against the same instrument at the same minute-of-week on
non-match days in the same window. We estimate

> Y_{i,t} = β · Match_t + α_{i × weekday × minute-of-day} + γ_{date} + ε_{i,t},

where the interacted fixed effect removes each instrument's intraday-weekly seasonality (the
intraday analogue of the lunch-hour artifact earlier authors warn about) and the date effect removes
day-level shocks such as volatility regime and macro releases. Standard errors are clustered by date.
Because matches cluster within days, the effective number of clusters is the number of *match-days*,
so the design has power against effects of the size reported for national equities (tens of percent)
but not against effects of a few percent; we report this bound rather than dress a null as a precise
zero.

We extend the model with concurrent-match intensity, knockout stage, the relevant domestic team, and
goal windows (±5 and ±15 minutes). To test the information channel (H4) we form a block-level
comovement measure: for each match block (kickoff to +105 minutes) and matched same-weekday/clock
control blocks on non-match days, we compute the mean pairwise correlation of one-minute returns
across the instruments trading in the block and regress it on the match indicator with
weekday-and-clock fixed effects and date clustering (because controls fall on non-match days, a date
effect would be collinear with the match indicator, so it is omitted). Because average pairwise
correlation depends on which instruments are open, we guard against composition by reporting a
constant-instrument crypto-only universe, an instrument-count control, and a fully-open-blocks subset
alongside the raw all-instrument measure. Primary outcomes (volume, trade count, absolute
return, range) are
designated in advance, separated from exploratory ones, and corrected across the primary
outcome-by-market family with the Benjamini–Hochberg procedure. Robustness comprises placebo
treatments shifting match windows by ±1 day and +3 hours, macro-release exclusion, a formal
pre-trend test, alternative windows, and a properly-pooled domestic test extended to four
tournaments. The design is
contemporaneous association, not prediction, and carries no look-ahead: no statistic describing
minute t uses information from t or later.

## 5. Results

Table 8 collects every channel in one place — activity, liquidity, volatility, comovement, the
domestic-team effect, intensity, goal windows, sentiment, options, and attention-scaling — each a null
with the effect size it rules out. The subsections below walk through them; the one-line summary is
that nothing moves, in any market, on any margin, even as attention multiplies several-fold.

### 5.1 The attention shock is real (Table 1, validation)
Wikipedia tournament-article pageviews average 5.7× (2018) and 8.0× (2022) their off-tournament
level, and within each tournament daily views correlate with the daily match count (r = 0.34 and
0.70). This validation is at daily resolution — the Wikimedia per-article endpoint does not serve
hourly data, so we cannot use it to confirm attention inside the specific during-match window the
regressions test. For the intraday window we rely on external evidence: FIFA and broadcaster figures
put live audiences in the hundreds of millions per match (roughly 1.5 billion for the 2022 final), so
the during-match minutes are high-attention by construction even though our pageview proxy speaks only
to the match-day. Whatever markets do or do not do, they are not responding to a non-event. We can
push this further: if attention drove trading, the effect should be larger on higher-attention days.
Interacting the match indicator with the day's worldwide Google-Trends interest, the scaling term is
indistinguishable from zero for both crypto (−0.04, p = 0.70) and futures (+0.07, p = 0.46) — the
highest-attention matches move markets no more than the rest, so the null is not an artifact of weak
attention.

### 5.2 No average during-match effect (Table 3, Figure 1, Figure 2)
The during-match coefficient on log volume is +2.3% pooled across all instruments, −2.7% for crypto
spot, −3.9% for crypto perpetual, −2.9% for equity futures, +7.2% for commodity futures, and +11.0%
for FX futures. None is statistically significant, and none survives the false-discovery correction
(all q ≈ 0.71). Trade counts, absolute returns, and the high–low range tell the same story. The
kickoff-centered event study (Figure 1) shows deviations from the matched control wandering inside a
±0.2 log-point band with no dip at kickoff, through halftime, or at the final whistle.

### 5.2a Cash equities — the literature's own venue
The original effect lives in national cash-equity markets, so we add a cash-equity arm: US broad
ETFs (SPY, QQQ, IWM) and nine single-country ETFs (EWZ, EWW, EWU, EWG, EWQ, EWP, EWJ, ARGT, EWY),
one-minute trade bars from AlgoSeek, the same matched-control design restricted to regular US
trading hours. Two caveats bound it: these trade only in US hours, so the during-match sample is
the subset of matches overlapping the US session (32 match-days for the broad ETFs), and US-listed
country ETFs measure US trading of country exposure, not activity on the home exchange. We treat the
arm as exploratory (seven uncorrected tests). Within these bounds cash equities are null: US
broad-ETF dollar volume is −5.7% during match windows (p = 0.19) and trade count −2.5% (p = 0.53),
a correct same-clock one-day placebo is equally null (and itself partly overlaps adjacent match
days, since consecutive tournament days share clock times, so it can only fail to manufacture a
false positive, which it does), and there is no effect within either tournament taken alone
(2018 −4.2%, 2022 +6.8%, both n.s.). The own-team tests are underpowered and
null: the USA-playing interaction rests on three match-days, and the nine country ETFs' own-country
effect pooled over 28 dates is −3% volume (p = 0.75). Extending the own-team test to four tournaments
(2010–2022) raises the country-ETF sample to 55 own-country match-days, where the effect is −5%
volume (p = 0.48) — a better-powered but still clean null in the literature's venue; the US-broad
USA-playing test stays underpowered at six regular-hours match-days.

This arm also supplies a second cautionary example, alongside the comovement test, of how a naive
specification manufactures an effect. Including pre- and post-market minutes, US broad-ETF trade
counts appear to rise 19% during matches (p = 0.02). But extended-hours bars carry a handful of
trades each, match windows over-weight the regular session relative to controls, and a correct
same-clock placebo reproduces the same +20%: the apparent effect is a session-mix artifact that
vanishes the moment the sample is restricted to regular hours. The genuine home-market test —
intraday volume on the FTSE, DAX, Nikkei, or Bovespa during their own teams' matches — needs data we
do not have and remains the open question.

### 5.2b Liquidity — spreads and depth (H2)
Activity is one half of the liquidity hypothesis; the other is market quality. Using AlgoSeek's
quote-bearing TAQ products — per-minute relative quoted spread, top-of-book depth, and aggressor
imbalance for all four tournaments — we test H2 directly across 2.2 million instrument-minutes
spanning equity, commodity and FX futures, US cash equities, and country ETFs (equities in regular
hours), with the same matched-control design. H2 predicted spreads widen and depth thins as liquidity
suppliers stop monitoring; we pre-registered the alternative that spreads hold because market-making
is automated. The data favour the alternative. The during-match effect on the relative quoted spread
is +0.2% pooled (p = 0.66) and statistically zero in every market group — spreads do not widen.
Displayed depth leans marginally lower, −2.7% pooled (p = 0.08), with a single nominally significant
cell (country ETFs, −4.0%, p = 0.03) that does not survive the false-discovery correction across the
liquidity family. With 2.2 million minute-observations this is a precise null on spreads and at most a
few-percent depth reduction: World Cup matches do not measurably impair liquidity in these automated
markets. The result fills the study's largest data gap and reinforces the headline — attention spikes,
but neither trading nor market quality moves.

### 5.2c Options (SPY)
We add the one derivative layer the equity complex has — SPY options, from AlgoSeek's OPRA feed.
Intraday (one-minute) option volume and put-call ratios test the activity channel; end-of-day implied
volatility and 25-delta skew test whether the attention shock shows up in option pricing. Neither
does. During-match SPY option volume is −7.9% (p = 0.15) and the log put-call volume ratio is flat
(+0.004, p = 0.88; the raw volume ratio is borderline at +2.8, p = 0.054, but on the natural log scale
the effect vanishes, and this exploratory family carries no correction); on match-days versus non-match
weekdays, at-the-money implied volatility (+0.4
vol-points-scaled, p = 0.39) and the 25-delta put-call skew (p = 0.17) are unchanged. The options
market neither trades more nor reprices risk around World Cup matches. (The IV/skew test is at daily
resolution — the greeks feed is an end-of-day snapshot — and so is weaker than the minute-level volume
test; both point the same way.)

### 5.2d Retail spot FX
The one decentralized, retail-facing venue is spot FX, and the spec's classic warning applies: a retail
FX feed reports quote activity (price-update counts), not true traded volume, because there is no
consolidated tape. Using Dukascopy tick data for seven major pairs (2010–2022), the during-match effect
on log quote activity is +5.6% (p = 0.05), concentrated in non-domestic matches (+6.5%); when the pair's
own country plays it is −0.7% (p = 0.91). This is the single nominally significant during-match activity
estimate in the study, and it points the *wrong* way for distraction — if anything quote activity is
marginally higher during matches, on a measure that is itself inflated by the volatility-driven
price-update rate. It does not survive the study-wide correction. Pooled across pairs, both FX venues —
centralized futures and decentralized retail spot — show no withdrawal; the sharper question of whether a
currency reacts when *its own* nation plays is taken up next.

### 5.2e Home markets and home currencies (Table 9)
Every test above pools across instruments for which most matches involve no mapped country, which dilutes
any home-specific effect toward zero. The economically sharp question is narrower: does a nation's *own*
market move when its *own* team plays? Two obstacles make this hard, and both shape the design. First,
free historical data for foreign exchanges is daily, not intraday — minute bars for the Bovespa or the
Nikkei back to the 2000s are not distributed — so this arm runs at daily resolution and tests match-*day*
activity, the next-session return (the Edmans–García–Norli "loser effect"), and daily volatility, rather
than the during-match minutes. Second, no single nation supplies enough World Cup matches for a valid
single-market test: clustered by match-day, the binding sample size is the number of own-match days, and
across all tournaments since 2002 no nation exceeds the low thirties (Brazil, the best case, has 34).
Below roughly thirty clusters, date-clustered inference over-rejects, and for a volatile emerging-market
asset the minimum detectable effect at ten to twenty clusters is 30–70%. A single exotic pair therefore
cannot be tested honestly, and a longer calendar window does not help, because a nation does not play more
World Cup matches if more years are added. The valid design is to pool, stacking each nation's own-match
days into one panel.

We assemble three home-market panels. The loser-effect return is measured on the single first trading
session strictly after each match (one treated observation per match, so returns are not stacked across
autocorrelated days). (i) **Home equities, daily, 26 nations** (main index plus top-capitalization names,
about 100 series): on days the nation plays, index and stock volume is −0.6% (p = 0.92) and Parkinson
volatility −0.06% (p = 0.28); with 63 match-day clusters this null now rules out a home-market volume
distraction beyond about 15%. The matching loser-effect panel on these same 2009-onward equities (ACWI
world-return adjusted) shows the next-session index return after a loss is −39bps but after a *win* −70bps
(p = 0.03 for the win cell) — wins are followed by *larger* declines than losses, so the +31bps
loss-minus-win difference is the wrong sign for a loser effect and the common negative drift is a
tournament-season calendar effect. (ii) **National stock indices, 1998–2022, 20 countries** (110 match-day
clusters), which extend the loser effect across six more tournaments and to the deep history: the
first-session index return after the nation's own match, world-return adjusted, is −0.5bps after a loss (p
= 0.96); the developed-market subset shows −15bps (p = 0.14) but matched by an equal post-*win* dip
(−10bps, p = 0.14), confirming the same calendar drift, and the loss-minus-win difference is small and
insignificant. (iii) **Home currencies, daily, 16 floating units gated at each one's float or
redenomination date — 1998 for the five developed units and South Korea, 2000–2007 for the rest (Brazil
from 2002) and 2015 for the post-float rouble** (74 match-day clusters, ICE/IDC series; Argentina's
convertibility-peg era and Turkey's pre-2005 redenomination are excluded as untestable): the loser effect
is +9.9bps (p = 0.13), if anything an *appreciation* and the wrong sign for the literature's prediction.
Match-day currency volatility is flat (p = 0.43).

The hypothesis that the effect should be largest in the smallest, most football-absorbed economies — for
which the home market is most retail-dominated — is directly testable by interacting the own-match term
with an emerging-market indicator. It is not supported. The three measures conflict: emerging-market home
volume is 15% lower on own-match days than the developed baseline (p = 0.30, correctly signed but
insignificant), the currency loser-effect interaction is +3bps (p = 0.82), and the equity loser-effect
interaction is +45bps and even reaches nominal significance (p = 0.05) — but with the *wrong* sign,
emerging markets falling *less* after a loss, not more, and it does not survive the study-wide correction.
A correctly-signed but underpowered volume dip in the smallest markets is the one seam where a home effect
could still hide, but the freely available data cannot resolve it, and only intraday home-exchange data,
which is not freely available, could.

A standalone single-nation loser effect is, in the end, not estimable — which is itself the cluster-count
argument confirmed rather than a result. Brazil, the closest any nation comes to a valid standalone test
with 34 World Cup matches across six tournaments, has only *six* losses in 2002–2022; Japan a similar
handful. A return regression on six treated observations yields degenerate, high-leverage standard errors
(the point estimates swing from −43 to +61bps across the real and the Bovespa depending on the control),
and we report no single-nation loser-effect p-value, because none would be honest. This is exactly why the
panel must be pooled.

The during-match *activity* cut, which has ten to sixty match-days per market and so can be tested, makes
the heterogeneity vivid: run currency by currency, the per-nation effects conflict in sign and none is
robust — sterling-futures volume −30% when England plays (p = 0.002, ten match-days), the yen +13% (p =
0.02), the euro +13% (p = 0.04), the peso −21% (p = 0.09), and a meaningless Canadian-dollar +91% (p =
0.01) that rests on *two* match-days and sits beside its own physically-impossible volatility cell. These
are striking single-market numbers in both directions — the same low-cluster mirage as the sterling and
Nasdaq cells of §5.3 — that the pooled, powered evidence does not bear out, and that the global correction
discards.

### 5.3 The domestic-team effect, done honestly (Table 4)
Run market by market, two cells look dramatic: sterling-futures volume −34% when England or Scotland
plays (p = 0.010; the trade-count version is −31%, p = 0.003) and Nasdaq volume +35% when the USA
plays (p = 0.04). These are interaction coefficients — the differential relative to a match with no
mapped team, not the total own-playing effect (which is smaller, about −25% for sterling once the
common match term is added). Both are mirages of low cluster counts — six and two match-days respectively — for
which date-clustered inference is known to over-reject. Pooling all mapped markets so the own-team
effect is identified from 28 treated match-days, the coefficient on (Match × own team playing) is
**+11.0%** for volume (p = 0.16), and +14.9% in an FX-only specification (p = 0.10; this FX-only set
spans the same 28 treated days, so it is a near-identical sample rather than an independent subset);
a +1-day placebo is null. Two caveats temper this. First, 24 of the 28 treated calendar dates carry a euro-area match
(6E), so the pooled and FX-only figures are essentially the euro effect rather than independent
corroboration across four currencies. Second, even pooled the test is not sharply powered: with a standard error of
0.074 log-points its minimum detectable effect (80% power, 5% size; 2.8 standard errors, exponentiated)
is about 23% in volume, so it can
reject the 30–50% declines of the cash-equity literature but cannot rule out a moderate (under ~20%)
own-team effect. The honest reading of H6 is therefore no significant domestic effect, with a point
estimate that leans positive — the opposite of distraction — and inconclusive power against
moderate-sized effects in the very markets where distraction was originally found.

To press on that power limitation we extend the own-team test to four tournaments (2010, 2014, 2018,
2022) using the index and currency futures, which predate crypto. This doubles the treated sample to
60 own-team match-days and tightens the minimum detectable effect to about 20%. The pooled own-team
estimate is then +9% volume (p = 0.18) and +10% trade count (p = 0.17), with the foreign-match term at
zero — almost identical to the two-tournament result. The own-team effect is thus a stable small
positive across four tournaments, not a small-sample accident: we can exclude own-team *declines*
beyond roughly 20% while still finding nothing that resembles distraction. Doubling the clusters this way also serves as a robustness to the small
treated-cluster count of the two-tournament test (28 → 60 date-clusters), and the answer is unchanged. The pooled identification
remains euro-dominated, as in the two-tournament case, so this buys statistical power rather than
independent corroboration across currencies. A triple-difference — does the own-team response
strengthen specifically in knockout matches? — returns a knockout-specific own-team term of −11%
(p = 0.25), but it rests on only nineteen own-team-knockout match-days and so neither confirms nor
rules out a stronger high-stakes effect. (The own-team main term in that richer specification is
+12.2%, nominally p = 0.037 — the same positive, distraction-wrong sign as the pooled estimate, and
like every other cell it does not survive the global multiple-testing correction.) Figure 3 plots the own-team against the foreign-match volume
effect by market group; Figure 6 shows the own-team estimate is stable (and zero-straddling) across
all four tournaments, with no single-tournament driver. Full per-test numbers and the consolidated
robustness battery are tabulated in the Appendix.

As a final, sharper proxy for the home-market channel we cannot observe directly, we use the
single-country ETFs — US-listed instruments that track a country's equity exposure. Pooling the nine
country ETFs, an ETF's volume when its own national team plays is −4.8% (p = 0.50, over 55
own-country match-days in US hours), and — the mechanism check — interacting that own-team term with
the country's own Google-Trends attention adds nothing (−0.03, p = 0.80). So even at the country
level, even scaled by the home nation's own attention, the distraction effect does not appear in the
exposure that US investors trade.

### 5.4 Intensity, stage, and goals (Table 4b; Figure 5)
Knockout matches add nothing detectable beyond group-stage matches in any market. In crypto, where
continuous trading lets us look at acute moments, the ±5-minute goal window carries a −7.8% volume
coefficient (p = 0.12) and the ±15-minute window −6.8% (p = 0.095): leaning negative but never
significant, and showing no sign of the gambling-like volume spike one might expect from a
retail-heavy market. The goal-centered event study (Figure 5) is flat. We also test match intensity
directly (H8) using a pre-match Elo rating attached to every match, which lets us measure closeness
(the inverse Elo gap) and flag matches that ran to extra time or penalties. Pooling the futures over
four tournaments, a one-standard-deviation closer match changes during-match volume by −3.3%
(p = 0.35) and trade count by −3.5% (p = 0.32), and extra-time/penalty matches by −6.2% (p = 0.66, on
ten such match-days, underpowered). The closeness test is reasonably powered (65 match-days) and is a
clean null: a tighter or more dramatic match does not move these markets more. Defining stakes a third way — knockout or last-group-round must-win, do-or-die
matches — leaves the interaction null as well (futures +14.5%, p = 0.16; crypto −1.7%, p = 0.85).

### 5.4b Price efficiency (variance ratio, basis, lead–lag, abnormal returns)
We round out the price-discovery channel with four families of efficiency measures, computed
block-by-block against matched controls. None shows an economically meaningful shift during matches.
Lo–MacKinlay variance ratios are statistically unchanged for the equity/futures complex (ΔVR = −0.01,
p = 0.83); the spot–futures basis between SPY and ES is flat in both level and dispersion (p = 0.42
and 0.52), as is the crypto spot–perpetual basis (p = 0.87); lead–lag cross-correlations show no shift
of price discovery toward futures during matches (ES→SPY p = 0.37, crypto perp→spot p = 0.20); and
market-adjusted cumulative abnormal returns are null in both equities and crypto (|CAR| p = 0.46 and
0.35). Across thirteen efficiency outcomes the only sub-5% hits are two borderline variance-ratio
statistics (an equity |VR−1| and a crypto VR level) pointing in opposite directions that survive no multiple-testing discipline. Intraday
price formation is not measurably altered.

### 5.4a Return comovement (H4)
The original World Cup result is not really about volume — it is about *information*: Ehrmann and
Jansen (2017) find that cross-market return comovement falls during a country's matches, as investors
process less common information. We test this directly, and the test is instructive as much for its
trap as for its answer. For each match we form a block from kickoff to +105 minutes and compute the
mean pairwise correlation of one-minute returns across the instruments trading in that block, matched
to control blocks on non-match days with the same weekday and clock time. A naive all-instrument
measure appears to confirm the literature: average pairwise correlation falls from 0.49 in control
blocks to 0.39 in match blocks (−0.086, p = 0.005). But that decline is composition, not attention.
Match and control blocks differ in how many instruments are trading — 7.8 versus 6.4 on average,
because some match windows fall when fewer futures markets are open — and average pairwise correlation
mechanically depends on which instruments are in the set. Once composition is held fixed the decline
disappears: within the always-trading crypto set (the four BTC/ETH spot and perpetual series, three on
average since the perpetual enters only in 2022) it is +0.012 (p = 0.54),
within blocks where all eleven instruments trade it is +0.010 (p = 0.64), and controlling directly for
instrument count it is +0.002 (p = 0.93). We therefore find no evidence that World Cup matches reduce
cross-market return comovement; the only specification that "confirms" the prior finding is the one
contaminated by which markets happen to be open. This is not an accident of our sample. In a Monte Carlo with *no* true match
effect, in which match blocks merely sample fewer instruments — as when futures are shut for weekend
matches — the naive mean-pairwise-correlation registers a spurious comovement decline of −0.05 that is
significant in 100% of 400 simulations; adding an instrument-count control returns the false-positive
rate to its nominal 5%. Any attention study that pools heterogeneous instruments without holding
composition fixed will reproduce the original literature's result whether or not an effect exists.

### 5.5 How big an effect can we rule out? (equivalence bounds)
Because the headline result is a null, its value is in its precision. The 95% confidence interval on
the during-match volume effect is [−9.4%, +4.5%] for crypto spot, [−15.3%, +11.3%] for equity
futures, and [−6.1%, +11.5%] for the across-instrument average. We can therefore exclude, at
conventional confidence, the 30–50% declines reported for national cash-equity markets during a
country's own matches — but with an important scope condition. These tight bounds come from the
*average* match (most matches involve no team mapped to the instrument) and from markets with no
national mapping at all (crypto, gold, crude), which the original theory never predicted would
respond. They establish that the effect does not *generalize* to these structures; they are not a
like-for-like replication of the own-team cash-equity test, which is the underpowered exercise of
§5.3. Read together: whatever drives the cash-equity declines does not operate at a detectable scale
in continuously traded, derivative, or crypto venues, and in the structurally comparable own-team
futures we can neither confirm nor reject a moderate effect. To make this formal rather than a
confidence-interval reading, we run a two-one-sided-tests (TOST) equivalence procedure against the
30% margin: all ten headline estimates reject, at the 5% level, an effect as large as the 30%
national-equity decline. The equivalence margins — the smallest effect each estimate is statistically
consistent with bounding — run from ±1.1% for the quoted spread and ±5–9% for crypto volume and depth
to ±25% for the underpowered pooled own-team test. The large effects of the original literature are
not merely outside our confidence intervals; they are formally rejected in every venue we measure
(each estimate's lower equivalence bound excludes a decline of the literature's magnitude; Figure 8).

### 5.6 Post-match sentiment (H9, Table 6)
The during-match results are about attention; a separate channel is mood. Edmans, García and Norli
(2007) find that a country's stock market falls after its team loses. We test it directly: for each
completed match we map each playing team to its national instrument(s), classify the result from that
team's perspective (win/draw/loss, with extra time and shoot-outs resolved to the true winner), and
measure the mapped instrument's gross return over the hour after the final whistle, the second
post-match hour, and the next trading session, pooling all mapped instruments with instrument and date
fixed effects and date-clustered errors. The sentiment prediction is a negative post-loss return with
win > loss; we find neither. In the hour after the whistle the loss coefficient is −3.8 bps (p = 0.79)
and is statistically indistinguishable from the win coefficient. The only nominally significant
coefficients appear at the next-session horizon, but they load *equally* on wins and losses
(+103 and +74 bps) — a calendar coincidence in a thin sample (only 31 dates carry both a mapped win
and a mapped loss): both load positively, so the win-vs-loss separation the sentiment channel
predicts is absent, and restricting to macro-clean country ETFs the loss coefficient itself turns
insignificant (the win coefficient stays positive, confirming this is a calendar coincidence, not a
loss effect). An "unexpected loss"
cut, flagged from pre-tournament favourites, is likewise null (+19 bps, p = 0.18). With 286
team-match observations the test is power-limited, so we report a power-bounded null on the sentiment
channel rather than evidence against it — consistent with the during-match nulls.

### 5.7 The 2026 tournament (excluded; live extension underway)
The 2026 World Cup is ongoing as we write and is **not** part of the estimates above; all results use
the completed tournaments (2010–2022 for futures and cash equities, 2018–2022 for crypto). A live
collector is recording the 2026 order book, open interest, funding, and liquidations for a future
out-of-sample extension, but with the tournament only days old that sample is far too small to test
and we make no claim from it here.

## 6. Robustness

Placebo treatments that shift the crypto match windows by +1 day, −1 day, and +3 hours produce
coefficients indistinguishable from zero, confirming the matched-control design is not manufacturing
effects. A formal pre-trend test supports the parallel-trends assumption directly: regressing volume
on fifteen-minute event-time bins relative to kickoff, none of the eight pre-kickoff bins (−120 to 0
minutes) is significant (largest deviation 8%, smallest p = 0.19), so treated and control periods do
not diverge before the match starts. The pooled domestic result holds when 2018 is dropped
(2022-only) and when restricted to FX.
We also re-estimate the during-match effect after dropping every minute within 90 minutes of a
high-impact US or euro-area macro release (payrolls, CPI, FOMC, ECB decisions overlapping the
tournament windows). Only 1.2% of match-minutes are so contaminated, and excluding them moves the
during-match volume coefficient by about 0.02 log-points (largest 0.021, crypto perpetual) in any
market group, leaving every null intact. Splitting the window into its phases leaves each coefficient
within about ±5% of zero and non-significant (pre-match −2.1%, first half +5.5%, second half −0.5%,
post-match −5.2%), and re-estimating the during-match effect at five- and fifteen-minute aggregation
gives +1.8% and +1.9%, essentially identical to the one-minute +2.3% and equally non-significant.

Finally, a global multiple-testing check. Pooling every during-match and own-team coefficient this
study produces — 158 coefficients spanning activity, liquidity, options, price efficiency, comovement, match
intensity, goal windows, post-match sentiment, domestic effects, and the home-market and home-currency
family of §5.2e — 19 are nominally significant at
the 5% level, against the 8 expected by chance, and none survives a single global Benjamini–Hochberg
correction across all 158. We do not rest the conclusion on FDR survival alone, for two honest reasons:
this family mixes primary tests with nested robustness specifications, so the exact count — and therefore
whether the very smallest cells clear a leaner correction — is sensitive to how the family is delimited;
and a true null with this many tests would itself produce a handful of small p-values. What carries the
argument is that the smallest-p cells are each independently diagnosed by mechanism, not by arithmetic:
the six-match-day sterling interaction and the two-match-day Canadian-dollar cell are low-cluster
over-rejections, the comovement decline is a composition artifact demonstrated by Monte Carlo, and the
sentiment win coefficient is a calendar coincidence. None is a distraction effect. The study is a null
cell by cell, by mechanism, and as a body of evidence.

Nor is the null an artifact of instrument selection. Re-running the during-match volume test on the
full assembled universe — 29 instruments across seven asset classes, adding equity-index (RTY, YM),
metals (silver, copper), energy (natural gas), the Dow ETF, and the entire Treasury complex (2-, 5-,
10-, and 30-year) — produces two nominal rejections out of 29, against the 1.5 expected by chance, and
a median absolute effect of 2.8%. The Treasury complex is dead flat (−0.3% to +2.8%, every p > 0.68);
the two nominal hits (the UK and German country ETFs, −11% to −12%) are two of twenty-nine tests and
do not survive correction. Across rates, metals, energy, equity indices, FX, cash equities, and
crypto, the answer is the same.

## 7. Conclusion

The World Cup is a clean, repeated, globally synchronized attention shock, and in national stock
markets it leaves a clear mark. And even in cash equities, the venue where the effect was first
documented, we find no during-match effect in regular hours in the US-traded instruments we can
observe. Across five market structures that define modern trading — spot and
perpetual crypto, equity-index futures, commodities, and currency futures — it does not. Attention
demonstrably spikes, by a factor of six to eight in our proxy, while trading volume, trade counts,
and volatility do not move beyond a few percent in any direction, and the best-powered test of a
home-team effect — itself able to detect only effects above about 23%, and dominated by euro-area
matches — leans, if anything, the wrong way for distraction. The reason is structural: the
markets where the effect was found are segmented, locally-houred, and human-intermediated, while the
markets tested here are global, near-continuous, and automated, so no single nation's distracted
fans are pivotal. For practitioners the implication is reassuring and specific: liquidity provision,
execution, and risk in these venues need not be re-timed around the football calendar, within bounds
we quantify. The limitations are honest ones — historical quoted spread and depth are unobserved in
trades-only futures/equity data, the structurally comparable home-market test (intraday volume on the
FTSE, DAX, Nikkei, or Bovespa) needs data we do not have, betting odds are reproducible only for 2022,
and goal timing is approximate. The ongoing 2026 tournament is deliberately excluded from these
estimates; the live microstructure collector now recording it will supply a genuine out-of-sample
extension once the tournament is complete.

---

*Data and code: `worldcup_markets/`. Tables in `paper/tables.md`; figures in `analysis/figures/`.
Estimation on 2018+2022; 2026 live out-of-sample. All times UTC; analysis fully reproducible from
the ingest and analysis scripts.*
