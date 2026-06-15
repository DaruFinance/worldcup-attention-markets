# collectors

`crypto_live.py` records the 2026 crypto microstructure that Binance does not archive: 50-level
order-book depth, best bid/ask, open interest, funding, mark and index, and forced liquidations
for BTC and ETH spot and perpetual, on a fixed poll interval. Output goes to `data/crypto_live/`
by default; override with `WC_OUT` and `POLL_SEC`.

```
WC_OUT=data/crypto_live POLL_SEC=60 python3 collectors/crypto_live.py
```

This is the perishable feed for the out-of-sample extension. It writes newline-delimited JSON
per stream per day plus a heartbeat file.
