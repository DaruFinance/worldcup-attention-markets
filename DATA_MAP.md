# DATA_MAP — World Cup attention-shock study

Source-of-truth for every dataset: where it comes from, granularity, and whether it is
**PERISHABLE** (must be captured live — unrecoverable later) or **ON-DEMAND** (can be
pulled historically at any time). Today is 2026-06-13; the tournament runs 2026-06-11 →
2026-07-19 (104 matches). All timestamps stored in **UTC**.

## Legend
- 🔴 PERISHABLE — capture live now or lose it
- 🟢 ON-DEMAND — historical, pull whenever
- ⚙️ STATUS: ✅ running/done · 🟡 built-not-run · ⬜ todo

---

## 1. Match-event spine  🟢  ✅
| item | source | granularity | notes |
|---|---|---|---|
| 2026 schedule + scores + bracket | fixturedownload.com live JSON | match-level | `ingest/build_matches.py`; auto-refreshed hourly by `ingest/refresh_matches.py` (daemon). 104 matches, UTC kickoff, venue→tz, team→market map. |
| 2018 / 2022 schedule + results | same feed (historical) / Wikipedia / football API | match-level | ⬜ loaders stubbed in build_matches.py |
| goal / card / actual-whistle timestamps | live football API (API-Football / fotmob / ESPN) | event-level | ⬜ NOT in feed; needed for goal-windows + exact FT. Layer on; 2026 capturable live, 2018/22 from archives. |
| closing betting odds, FIFA/Elo | football-data / clubelo / oddsportal | match-level | ⬜ for importance + closeness (H7/H8) |

## 2. US equity complex  🟢  ⬜  (algoseek — ON-DEMAND, not perishable)
| instrument | source | granularity | notes |
|---|---|---|---|
| SPY (+QQQ/DIA/IWM) trades+NBBO | AlgoSeek US-equity buckets | 1-min bar + tick/quote | spreads/depth historical → NOT perishable. `algoseek_data/as_pull.py` extends to these. |
| ES / NQ / RTY / YM futures | AlgoSeek futures bucket (P545) | 1-min trades + quotes | roots already in as_pull.py ROOTS |
| SPY/SPX options (ATM, 25Δ skew, IV) | AlgoSeek equity-options (confirm entitlement) / ORATS / CBOE | 1-min snapshot | ⬜ confirm options entitlement; compact bucket only (ATM + 25Δ, 8–60d) |
| country ETFs (EWZ/EWW/EWC/EWU/EWG…) | AlgoSeek equities | 1-min | expanded universe (H6) |

## 3. Global macro  🟢/🔴 mixed  ⬜
| instrument | source | granularity | perishable? |
|---|---|---|---|
| EUR/USD, GBP/USD, USD/JPY (+CHF/CAD/AUD) spot | TradingView premium export / dukascopy tick | 1-min OHLC + tick-count | 🟢 dukascopy archives ticks. Label as **tick-volume**, not traded volume. |
| CME FX futures 6E/6B/6J/6C/6A/6S/6M | AlgoSeek futures (in ROOTS) | 1-min trades+quotes | 🟢 centralized true volume — preferred for FX volume tests |
| Gold (GC), Crude (CL) [+SI/NG/HG] | AlgoSeek futures (in ROOTS) | 1-min trades+quotes | 🟢 |

## 4. Crypto spot + perp  🔴 (liquidity/OI/liq) + 🟢 (klines/funding)  ✅ live / ⬜ backfill
| stream | source | granularity | perishable? | status |
|---|---|---|---|---|
| **order-book depth (50 lvl)** BTC/ETH spot+perp | Binance REST (live collector) | ~60s snapshot | 🔴 not archived | ✅ `collectors/crypto_live.py` |
| **best bid/ask + sizes** | Binance REST | ~60s | 🔴 | ✅ |
| **open interest** | Binance REST | ~60s live (API hist only 30d) | 🔴 | ✅ |
| **liquidations** (forceOrder) | Binance WS `!forceOrder@arr` | event | 🔴 not archived | ✅ |
| funding / mark / index | Binance REST live + archive | 60s live / 8h hist | 🟢 archived too | ✅ live + ⬜ backfill |
| 1-min klines, aggTrades | data.binance.vision | 1-min / trade | 🟢 | ⬜ backfill |
| 2nd exchange (Bybit/Coinbase) depth+liq | Bybit/Coinbase WS | event/60s | 🔴 | ⬜ add for robustness |

## 5. Controls  🟢  ⬜
| item | source | notes |
|---|---|---|
| VIX 1-min | AlgoSeek / TradingView | overnight return, vol regime |
| Macro-announcement calendar (CPI/NFP/FOMC/ECB…) | econoday / investing.com / TradingEconomics | EXACT release UTC timestamps → exclusion windows. **mandatory.** |
| Trading calendars, holidays, futures rolls, OPEX, triple-witch | exchange calendars (`pandas_market_calendars`) | session/DST handling |

## 6. Attention proxies (mechanism, expanded)  🟡/🔴  ⬜
| item | source | granularity | perishable? |
|---|---|---|---|
| Google Trends ("World Cup", team names) | pytrends | hourly | 🔴 high-freq window-limited → pull per-window during tournament |
| Wikipedia pageviews (teams/matches) | Wikimedia REST API | hourly | 🟢 archived |
| TV/streaming audience | FIFA / Nielsen / press | match-level | 🟢 ex-post |
| In-play betting odds (suspense proxy) | betfair exchange / oddsAPI | 1s–1min | 🔴 | 

---

## What is running RIGHT NOW (daemons)
- `collectors/crypto_live.py` → `data/crypto_live/{depth,book,oi,funding,liquidations}_YYYYMMDD.jsonl` + `_heartbeat.json`. PERISHABLE crypto capture.
- `ingest/refresh_matches.py` → hourly rebuild of the match spine.

## Backfill / pull order (Phase 2)
1. Crypto klines+aggTrades+funding from data.binance.vision for 2026 window (+ 2018/2022 for BTC/ETH where available).
2. AlgoSeek 1-min + NBBO for SPY, ES, NQ, GC, CL, 6E, 6B, 6J around each tournament window (±60 trading days). Quota: 100 GB/mo — budget per window.
3. FX spot (dukascopy/TradingView) as cross-check to FX futures.
4. Macro calendar + VIX + trading calendars.
5. (Expanded) options, country ETFs, attention proxies.
