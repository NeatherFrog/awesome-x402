# Public exchange sources

Reviewed on 2026-10-02. These are source and access checks, not a trading-result claim.

| Source | Pinned source | Verified fact |
| --- | --- | --- |
| Official Binance public-data repository | [README at f446ce3812bd4e5521f21faecd4ae3c6460e49fc](https://github.com/binance/binance-public-data/blob/f446ce3812bd4e5521f21faecd4ae3c6460e49fc/README.md) | Spot OHLCV archives use the 12 documented kline fields. January 2025 onward uses microseconds; earlier spot archives use milliseconds. Monthly archives normally appear on the first Monday of the following month; daily archives on the following day. Every ZIP has an adjacent SHA-256 `.CHECKSUM`. |
| Official Spot REST specification | [rest-api.md at 828ca74b809cfedbd5602df328b5f706368d483b](https://github.com/binance/binance-spot-api-docs/blob/828ca74b809cfedbd5602df328b5f706368d483b/rest-api.md) | Public data base endpoint is `https://data-api.binance.vision`; `GET /api/v3/klines` needs no trading credentials. Default REST timestamp unit is milliseconds; maximum kline limit is 1,000. |
| Dataset terms, version 1.0, updated August 26, 2026 | [TERMS_AND_CONDITIONS at f446ce3812bd4e5521f21faecd4ae3c6460e49fc](https://github.com/binance/binance-public-data/blob/f446ce3812bd4e5521f21faecd4ae3c6460e49fc/TERMS_AND_CONDITIONS.md) | Datasets use CC BY-NC-SA 4.0, distinct from repository-code MIT licensing. Section 4.1 permits personal non-production historical research; 4.2 excludes live proprietary execution and commercial order generation/signals. Derivative redistribution must include attribution and matching licensing (4.5). |

Actual downloaded specification SHA-256 values:

- `TERMS_AND_CONDITIONS.md`: `dcf358e9d18f598a7a635fac80f6e643fa24a0e111a4d39bda47f1e246b31eb1`.
- `rest-api.md`: `49ea6809243fc7fb426e07f2fe662097736c7bb405bd2da5eef637d715427999`.

## Selected data contract

The historical study uses Binance **Spot BTCUSDT and ETHUSDT**, preserving USDT quote units, same-venue OHLCV and UTC opening timestamps. No Yahoo or another venue is substituted. Raw ZIPs, source checksums and canonical snapshots live under `.local/exchange-history`, excluded from the application repository/package. A separate research export must preserve Binance Vision attribution and CC BY-NC-SA dataset terms; it does not change application source licensing.

Archives alone do not establish permission or technical feasibility for a production trading service. An eventual execution venue, production data permissions, instrument filters, current fee tier, bid/ask feeds, order handling and actual account eligibility require separate verification. Ordinary spot short trades require inventory/borrowing; spot OHLCV cannot stand in for perpetuals and their historical funding.

## Actual access checks

In this cloud session, Binance REST/data archives, Coinbase Exchange candles and Kraken OHLC all returned proxy `CONNECT 403`. Repeating the Binance archive read outside the filesystem sandbox did not change the result. GitHub-hosted official documentation was successfully read. No public-candle access was claimed from that local runtime.

The reproducible downloader can run on a GitHub Actions worker with normal venue access, then export checksum-verified snapshots. The development worker verifies snapshot hashes after download; a GitHub worker is a different acquisition environment and does not establish local API availability. Any missing monthly/daily exposure blocks the frozen full-calendar study. September 2026's not-yet-published monthly file may be replaced only by all official daily files for that same month, interval, symbol and venue.

The read-only `propdesk.exchange` adapter never accepts account credentials and never sends order requests.
