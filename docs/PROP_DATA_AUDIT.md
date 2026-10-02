# Prop-market data audit

Read-only source audit completed on **2026-10-02**. Eight existing immutable snapshots passed their saved JSON/CSV/canonical-bar hashes. Eight distinct new Yahoo snapshots and three FX plus micro-gold datasets were acquired. No strategy returns, 8%-monthly qualification, account orders or Telegram messages are produced by this acquisition script.

Audit producer: [fetch_prop_research.py](../scripts/fetch_prop_research.py). Aggregate receipt: [prop-data-audit.json](prop-data-audit.json). All original and new price snapshots remain local; raw source material is not placed in application packages or public data branches.

## Preserved existing snapshots

The existing `data/current-history/2026-10-01T09-23-08Z` files remain byte-for-byte unchanged. JSON payloads have `bars` and `provenance`; CSV columns are `time,open,high,low,close,volume`. UTC timestamps are **opening labels**, not real fill clocks. Source hashes match [current-research.json](current-research.json).

| Logical market | Actual Yahoo symbol | Bars | First open UTC | Last open UTC | Unit |
| --- | --- | ---: | --- | --- | --- |
| MES | MES=F | 11,485 | 2024-10-01 09:00 | 2026-10-01 08:00 | USD per index point, continuous futures proxy |
| MNQ | MNQ=F | 11,488 | 2024-10-01 09:00 | 2026-10-01 08:00 | USD per index point, continuous futures proxy |
| EURUSD | EURUSD=X | 12,348 | 2024-10-01 09:00 | 2026-10-01 08:00 | USD per EUR |
| XAUUSD logical proxy | GC=F | 11,490 | 2024-10-01 09:00 | 2026-10-01 08:00 | USD gold futures proxy, not spot CFD |
| NAS100 logical proxy | ^NDX | 3,493 | 2024-10-01 13:30 | 2026-09-30 20:00 | USD index level, not an executable contract |
| AAPL | AAPL | 3,493 | 2024-10-01 13:30 | 2026-09-30 20:00 | USD per share |
| MSFT | MSFT | 3,493 | 2024-10-01 13:30 | 2026-09-30 20:00 | USD per share |
| BTCUSD | BTC-USD | 17,330 | 2024-10-01 09:00 | 2026-10-01 08:00 | Public BTC/USD aggregate proxy |

There is **no January–September 2024 hourly coverage** in these rolling two-year snapshots. Previously inspected prices are not independent unseen data. Continuous futures do not establish delivery-contract identity, rollover adjustment, broker margin, current spread or real order fills.

## NY cash-session audit

The exact [pinned QuantConnect Lean US equity calendar](https://github.com/QuantConnect/Lean/blob/41c6e603e5671ca7b5d3de0cbe13b3c4b109bba4/Data/market-hours/market-hours-database.json) was downloaded and verified against SHA-256 `bffec9c2e5efe30c0f21a1af9d1803b2a8e9a1356ac4f7408130693b7261e440`. It is an equity cash-session reference, **not** an official CME Globex or prop-broker calendar. Dates use `America/New_York` with daylight-saving transitions; no fixed UTC offset substitutes for it.

MES/MNQ have all **501 completed cash-open sessions**: 496 ordinary sessions and five halfdays. Ordinary source clocks are 09:00,10:00,11:00,12:00,13:00,14:00,15:00 NY. The 09:00 candle includes pre-open time, so a 09:30 opening-range strategy cannot be reconstructed from it. A separately declared late-hour model may use the first wholly contained cash hour 10:00–11:00, then later closed bars and actual later opens.

On 2024-11-29, 2024-12-24, 2025-07-03, 2025-11-28 and 2025-12-24, MES/MNQ show 09:30,10:30,11:30,12:30 and a 13:00 closing marker. An actual 12:30 opening observation can support a predeclared flatten-at-open policy. A 13:00 marker must not be treated as a fresh full hourly candle. NDX/equity halfday grids have no 12:30 open; their 13:00 close marker cannot be used as that missing entry/exit.

Four NYSE-closed dates contain partial futures observations: 2025-01-09, 2025-05-26, 2025-06-19 and 2025-07-04. They remain in raw snapshots. A cash-window study excludes them only through its predeclared cash calendar; it does not infer a CME market closure or delete observations because of performance. Missing expected slots and whole days are retained as audit errors; none are filled.

## Distinct refreshed observations

The new eight-market receipt is [data/prop-data/2026-10-02T10-37-13Z/manifest.json](../data/prop-data/2026-10-02T10-37-13Z/manifest.json), with raw canonical data under `.local/prop-research/2026-10-02T10-37-13Z`. Shared OHLCV rows differ from the earlier snapshots: MES1,167, MNQ1,323, EURUSD178, GC934, NDX964, AAPL254, MSFT257 and BTC5,736. These counts include volume updates and any price revisions; they do not establish the reason for changes. The new download is **not an append-only extension** and is never silently substituted for a frozen experiment.

The exact first-audit producer was retained locally as `.local/prop-research/2026-10-02T10-37-13Z/producer.py`, SHA-256 `b674eece20088b66e91f31674be55073ee7e7c8ced36c2c31f9a7240bbd0a8a5`, before the script gained a distinct FX-acquisition mode. Original receipts and protocol hashes remain immutable.

## Fresh FX and micro-gold sources

Complete new receipts: [data/prop-data/fx-2026-10-02T10-40-40Z/manifest.json](../data/prop-data/fx-2026-10-02T10-40-40Z/manifest.json). Canonical data are under `.local/prop-research/fx-2026-10-02T10-40-40Z`.

| Market | Actual provider ticker | Bars | Price quote | Non-hourly gaps |
| --- | --- | ---: | --- | ---: |
| EURUSD | EURUSD=X | 12,320 | USD per EUR | 114 |
| GBPUSD | GBPUSD=X | 12,322 | USD per GBP | 114 |
| USDJPY | JPY=X | 12,253 | JPY per USD | 113 |
| Micro-gold continuous futures | MGC=F | 11,464 | USD | 516 |

All four run from 2024-10-02T10:00:00Z through 2026-10-02T09:00:00Z. Gap histograms, UTC daily counts, source URLs, request/response clocks, actual currency metadata and every canonical hash are in the receipt. Weekend/session gaps are retained; a verified historical broker holiday/session schedule is absent. A London/Asian-range model must test its required hourly slots explicitly and retain zero-trade/unavailable calendar exposure rather than inventing bars.

The initial request `USDJPY=X` was rejected by strict feed identity checking because Yahoo returned symbol `JPY=X`. Its failed receipt is preserved in [fx-2026-10-02T10-39-27Z/manifest.json](../data/prop-data/fx-2026-10-02T10-39-27Z/manifest.json). Before strategy outcomes, the verified alias was corrected: actual metadata says `JPY=X`, currencyJPY, `USD/JPY`, typeCURRENCY. This changes only ticker identity, not the selected market. USDJPY PnL is denominated in JPY and requires contemporaneous JPY→USD conversion for a USD-account study.

## Actually retrieved FTMO symbol specifications

The public [FTMO symbols page](https://ftmo.com/en/symbols/) loads [https://ftmo.com/wp-json/ftmo/symbols](https://ftmo.com/wp-json/ftmo/symbols). This official endpoint returned166 symbols; exact HTTP-response bytes and SHA-256 are retained locally, with their receipt in the audit. It supplies current instrument metadata and current weekly trading intervals, **not executable bid/ask prices**.

| Official FTMO symbol | Contract size | Profit currency | Digits | Current commission field | Standard / Swing leverage |
| --- | ---: | --- | ---: | --- | --- |
| US100.cash | 1 | USD | 2 | 0, percent | 50 / 15 |
| US500.cash | 1 | USD | 2 | 0, percent | 50 / 15 |
| EUR/USD | 100,000 | USD | 5 | 5, flat_USD | 100 / 30 |
| GBP/USD | 100,000 | USD | 5 | 5, flat_USD | 100 / 30 |
| USD/JPY | 100,000 | JPY | 3 | 5, flat_USD | 100 / 30 |
| XAU/USD | 100 | USD | 2 | 0.0014, percent | 50 / 15 |

These numeric fields alone do not settle per-side/roundtrip commission semantics, volume steps, historical tariffs or the user's selected platform/account contract. Digits are displayed precision, not verified exchange tick size. Current swap fields are not historical swap schedules; current `platformTimeOffset.UTC=3` is not a historical timezone conversion rule. Commission0 excludes neither spread nor slippage. `usdCommission` and `spreadConversionToUsd` must not be misrepresented as live quotes or observed spreads.

FTMO US100.cash differs from a nontradable Yahoo^NDX index; FTMO XAU/USD differs from Yahoo GC=F/MGC=F. Source specifications do not turn these proxies into exact prop execution feeds.

## Longer-history source checks

The official CME MES/MNQ specification pages, official Dukascopy historical-data page/terms/hourly binary probe and Nasdaq Data landing page each returned proxy CONNECT403 in this development runtime. Error receipts preserve exact URLs and access times. This indicates local access failure, not proof that those publishers lack data. No paid account, API key, third-party mirror, fabricated contract quote or synthetic decoder output substitutes for them.

No longer independent intraday dataset was acquired from these probes. A legitimate separate acquisition environment could check official Dukascopy bid/ask candles and applicable personal-research terms, retaining broker identity, zero-based source month, binary schema/units, bid/ask choice and exact bytes before accepting prices. Its CFD/FX history would still require separation from the actual execution venue. Redistribution permission is unverified, so uncertain raw data must stay private/local.

Standard micro-futures conventions ($5/MES point, $2/MNQ point, 0.25-point tick) and earlier $1.25/contract/side cost assumptions are not reverified by the locally blocked CME pages or by current FTMO CFD metadata. Any later futures study must label its sizing/tariff assumptions and stress them rather than call them a verified user's contract.

```sh
python scripts/fetch_prop_research.py --output /workspace/trading/docs/NEW_PROP_DATA_AUDIT.json
python scripts/fetch_prop_research.py --fx-only
```

The output path must be new: immutable reports/snapshots are never overwritten. Neither fresh source access nor a source audit establishes 8% every month, prop approval, actual broker fills or payouts.
