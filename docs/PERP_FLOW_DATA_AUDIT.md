# Preserved perpetual aggressor-volume fields

This independent input audit examines the original **66 official Binance USD-M five-minute ZIPs**, already preserved under `.local/perp-5m-history/raw`. It adds no source downloads, repairs, venue changes, strategy returns or execution claims. The original resolution adapter, canonical snapshots and acquisition receipts remain unchanged.

The [official Binance public-data README](https://github.com/binance/binance-public-data/blob/f446ce3812bd4e5521f21faecd4ae3c6460e49fc/README.md#klines-1) identifies USD-M kline fields as data from `/fapi/v1/klines`. Its previously retrieved local bytes have SHA-256 `2e133d9945a9263a02781369078e72805eff074680f305cd5460016471c6caad`. COIN-M kline units differ and are excluded from this study.

The actual twelve-column CSV header is:

```text
open_time,open,high,low,close,volume,close_time,quote_volume,count,taker_buy_volume,taker_buy_quote_volume,ignore
```

| Zero-based column | Actual field | Unit and interpretation |
| ---: | --- | --- |
| 0 | `open_time` | UTC interval opening, integer milliseconds in every year |
| 5 | `volume` | Total traded base quantity, BTC or ETH |
| 6 | `close_time` | Last included millisecond, exactly opening + 299,999 |
| 7 | `quote_volume` | Total traded quote amount in USDT |
| 8 | `count` | Nonnegative integer number of trades; unique orders and participants are unknown |
| 9 | `taker_buy_volume` | Base quantity whose buyer was the taker |
| 10 | `taker_buy_quote_volume` | Corresponding quote amount in USDT |

Raw source decimal strings retain **three decimal places for nonzero base-volume rows and five for quote amounts**; OHLC strings have two decimal places. These are observed archive representations, not verified account lot steps or exchange-wide order precision rules.

Every source ZIP was rechecked against its adjacent checksum filename and SHA-256, its manifest ZIP hash, its single expected CSV member, and its manifest CSV hash. All raw OHLCV rows exactly reproduce the previously frozen canonical JSON. Calendar labels remain consecutive UTC five-minute openings from **2024-01-01 inclusive through 2026-10-01 exclusive**. Both instruments contain **289,152 rows**, including zero-volume placeholders.

| Structural check | BTCUSDT | ETHUSDT |
| --- | ---: | ---: |
| Checksum-verified monthly ZIPs | 33 | 33 |
| Rows matching frozen native OHLCV | 289,152 | 289,152 |
| Positive-volume rows | 289,131 | 289,131 |
| Zero-volume rows | 21 | 21 |
| Maximum integer trade count in a bar | 512,917 | 1,019,179 |
| Taker-buy quantity exceeding total, exact decimal comparison | 0 | 0 |
| Defined quote/base averages outside the OHLC envelope | 0 | 0 |

The audit checks finite nonnegative decimal values and separately verifies base and quote taker-buy amounts are no greater than their respective totals. For a future decoder, numerical acceptance tolerances are `max(1e-12 base units, total_base * 1e-12)` and `max(1e-8 USDT, total_quote * 1e-12)`. The observed archives require no tolerance to satisfy buy ≤ total. All defined total, buy and complementary sell quote/base averages satisfy `base * low ≤ quote ≤ base * high`, allowing quote rounding of `max(1e-8 USDT, abs(quote) * 1e-12)`. No values are clipped or replaced to obtain these findings.

For every zero-volume row, total quote volume, both taker-buy amounts and trade count are also zero. **Buy fractions, signed normalized flow and quote/base averages are undefined on these rows and must remain `None`.** A zero denominator does not indicate neutral flow. The preceding known traded-price proxy can support an explicitly uncertain mark; a flat zero-volume record cannot substantiate an executable fill. Both assets share the same 21 affected timestamps, including the 70-minute interval starting 2024-10-28T20:00:00Z, already recorded in the independent native-source audit.

These aggregate fields become usable only **after the five-minute bar closes**, at the earliest opening + five minutes. Actual publication delay is unknown. A signal using them cannot act at the source opening label. Taker-buy fraction or `2 * buy - total` measures completed aggregate aggressor activity; it does not reveal order-book depth, trade sequence, hidden liquidity, queue position, future demand or synchronized intrabar paths. Quote/base ratios are aggregate traded-price averages, not executable bid/ask quotes. Resampled features require every constituent bar to be closed; undefined source flow must remain explicitly detectable.

The full independent receipt is stored locally at `.local/perp-flow-data-audit.json`, SHA-256 `26e56f30c91447551b1754c52dcc81d8f3cb9cf88a9ed744dbaba527be3627dc`. It records all 66 ZIP/CSV/checksum hashes, source-unit checks, raw precision histograms, unchanged canonical input hashes and affected timestamps. Audit producer `.local/audit_perp_flow_sources.py` is separately hashed in that receipt. The receipt was created before new flow-strategy returns were examined; no profit result follows from passing these input checks.

The original [source manifest](../data/perp-resolution/manifest.json) remains SHA-256 `a849e9ae1891a8974bedd1dd294e0779a7f8cbf5d0cdffdd1416c91049403ea3`; the original [data protocol](../data/perp-resolution/protocol.json) remains `221d0b2905545ee641b6d4f35c3259830811060c169b5ecd415d710498370995`. Existing Binance Vision CC BY-NC-SA 4.0 attribution and personal non-production historical-research terms apply to derived fields. Raw ZIPs and canonical price datasets remain local and excluded from application packages.

The new reader was independently executed against all original archives without calculating strategy outcomes. Captured reader SHA-256: `25960010ebad7f714ef76047a1e5e962aec8de33536eed6449460f348fc01d34`. Its local receipt `.local/perp-flow-reader-audit.json`, SHA-256 `9e2736b7f73cfa8acf37f4cc89d717257ffce4d7025f6904d028fe129e8b51a3`, records 66 matching source receipts, all 578,304 records, complete calendar endpoints, every feature's exact bar-close `known_at`, integer trade counts, defined fractions in [0, 1], and 21 undefined zero-volume fractions per instrument. The captured reader remained unchanged during that audit; a subsequent revision needs its own verification before exact reproduction.

Thirteen [independent source-contract tests](../tests/test_flow_source_audit.py) passed. They test distinct base/quote fractions, absent-trade records, bar-close knowledge, checksum byte and filename binding, strict field order, buy-volume excess, price-envelope consistency, nonfinite values, integer trade counts, incomplete/duplicated intervals, USD-M millisecond timestamps after 2025, and isolation of earlier decoded records from a later flow change. These are decoder/source checks, not evidence of a profitable trading model.
