# USD-M perpetual and funding source contract

Registered acquisition coverage: **2024-01-01T00:00:00Z inclusive through 2026-10-01T00:00:00Z exclusive**, Binance USD-M BTCUSDT and ETHUSDT. This is a distinct dataset and hypothesis family from the rejected spot-indicator and liquidity/FVG studies. Existing spot snapshots and studies remain immutable.

## Official references actually read

1. [Official public-data README, commit f446ce3812bd4e5521f21faecd4ae3c6460e49fc](https://github.com/binance/binance-public-data/blob/f446ce3812bd4e5521f21faecd4ae3c6460e49fc/README.md): USD-M kline field order, raw milliseconds in the futures examples, adjacent `.CHECKSUM` verification and archive update history. The January 2025 microsecond change is explicitly **Spot**, and is not applied to USD-M files.
2. [Official USD-M Python connector, commit a6bfbbf10fe2c1b4eb76fc24ffb82eb94bf9df89](https://github.com/binance/binance-futures-connector-python/blob/a6bfbbf10fe2c1b4eb76fc24ffb82eb94bf9df89/binance/um_futures/market.py): `funding_rate` documents public `GET /fapi/v1/fundingRate`, ascending event order, `startTime`/`endTime`, maximum `limit=1000`. Fetched source SHA-256 is `9e55db014233d92bad66a90ec36212f1fada7f1f93a092ec5d6bc9298988659f`; no SDK trading code was copied.
3. [Funding Rate History reference](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-History): linked by the official connector. The developer website itself was not accessible from this worker; the connector documentation was actually read through GitHub.
4. [Dataset terms](https://github.com/binance/binance-public-data/blob/f446ce3812bd4e5521f21faecd4ae3c6460e49fc/TERMS_AND_CONDITIONS.md): CC BY-NC-SA 4.0 dataset license, personal non-production historical research permitted, production/commercial execution permissions unverified. See [EXCHANGE_SOURCES.md](EXCHANGE_SOURCES.md) for pinned content hashes and exact limitations.

An [upstream issue with exact official USD-M kline/funding URLs](https://github.com/binance/binance-public-data/issues/500) corroborates the location pattern and warns about post-delisting records for other symbols. Its author is not verified as a Binance employee; it is not authority that every archived event represents an executable live trade. BTCUSDT/ETHUSDT are the fixed symbols; no newly selected delisted asset is substituted.

## Archive URLs and strict expected schema

Perpetual hourly archive example:

```text
https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/1h/BTCUSDT-1h-2024-01.zip
```

Funding archive example:

```text
https://data.binance.vision/data/futures/um/monthly/fundingRate/BTCUSDT/BTCUSDT-fundingRate-2024-01.zip
```

Each ZIP must pass its official adjacent `.CHECKSUM` SHA-256 and contain exactly its named CSV. Perpetual candles use twelve source fields and preserve OHLCV, UTC opening times and milliseconds. The parser accepts the actual documented OHLC header when supplied, and never interprets a USD-M archive as Spot microseconds.

The registered funding CSV header is `calc_time,funding_interval_hours,last_funding_rate`. Actual acquired schemas are recorded in source receipts; an unexpected header blocks acquisition instead of guessing. Funding calculation/settlement timestamps are Unix milliseconds and their fractional milliseconds are retained. Rates are **decimal fractions per realized event**, not percent per hour or APR. Source interval hours are retained individually, including changes. The parser checks internal event gaps against each event's reported interval with an explicit 60-second timing tolerance; no universal eight-hour schedule or missing rate is synthesized.

For September 2026 only, an unpublished monthly archive returning HTTP404 may use all same-venue official daily kline files. A missing monthly funding archive may use the fully paginated official funding REST endpoint with exact month bounds. REST responses have raw-response SHA-256 receipts, **not** an official archive checksum. Missing historical `funding_interval_hours` remains null; current `fundingInfo` cannot establish past interval policy. Unknown availability, incomplete pages, wrong symbols, invalid prices/rates, duplicates, gaps or missing calendar exposure block the corresponding complete snapshot.

## Canonical exports

`scripts/download_funding.py` writes its immutable data protocol before acquisition. Files remain under `.local/funding-history`, excluded from application source/packages:

- `{BTCUSDT,ETHUSDT}-1h.json`: canonical perpetual OHLCV arrays, `time` is UTC **bar opening**.
- `{BTCUSDT,ETHUSDT}-funding.json`: actual realized event arrays with `time`, `funding_rate`, `funding_interval_hours`, `mark_price`, `known_at` and `rate_kind`.
- `manifest.json`: source URLs, verified archive hashes, raw REST response hashes where applicable, original CSV hashes, canonical JSON hashes, exact coverage, failures and completeness.
- `protocol.json`, original ZIP/checksum pairs and REST pages under `raw/`.

Funding archives do **not** provide a mark price in their registered three-field schema; `mark_price` is explicitly null. Official REST may provide `markPrice`. A later funding-PnL study must identify any mark-price proxy and cannot present a perpetual close proxy as the true exchange settlement notional.

`known_at` denotes the archived event's settlement/calculation label. Actual publication latency is not independently verified. A historical funding outcome cannot be used as a known prediction before that settlement: a causal study must use only strictly earlier observed events for sizing and regime decisions. Parse event times as datetimes; fractional-millisecond ISO labels must not be compared lexically to whole-second boundaries.

## Costs and remaining execution questions

The later study's conservative assumptions are Spot fee10 bps/side, perpetual fee5 bps/side, slippage2 bps/side/leg and full spread1 bp/leg. These are assumptions, not a verified user's fee tier. Hedged carry must count cash tied up in Spot, perpetual collateral, mark/basis divergence, negative funding, both legs' fees, rebalancing, liquidation and exchange risk. Profitability of a data-research strategy is separate from live execution and production data permission.

No account credentials, order endpoints, Telegram messages or actual positions are involved in acquisition. No profitable carry strategy is claimed before the separately registered funding study completes.

```sh
python scripts/download_funding.py --data-dir .local/funding-history --workers 6
```

Historical data attribution: **Binance Vision**, [official public data](https://data.binance.vision/). Dataset and derived research exports use **CC BY-NC-SA 4.0**, subject to the dataset terms; application source licensing is separate.
