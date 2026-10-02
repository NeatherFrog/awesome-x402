# Higher-resolution source feasibility — 2026-10-02

**Current result: no new Dukascopy quotes or long futures history were acquired.**
Fresh requests to four small official Dukascopy minute-candle files failed at
the environment's HTTPS proxy with `Tunnel connection failed: 403 Forbidden`.
The origin did not provide a response, so this does not establish that a file
is missing, that Dukascopy rejected a user, or that a paid subscription is
required. Public GitHub documentation was readable. No alternate route to a
denied quote host, bulk download, paid API call, price-return calculation or
strategy test was attempted.

This is a source feasibility review, separate from the immutable existing
experiments. Checks completed by **2026-10-02T11:01:05Z**. Raw probe receipts and
documentation were retained temporarily in `/tmp/high-res-feasibility`; that
directory is not a distributed data archive. Exact public locators and document
fingerprints below make the conclusions reviewable.

## Fresh bounded retrieval checks

Each request used ordinary verified HTTPS, a 20-second timeout and a 1,500,000-byte
body limit. Every row below returned the same proxy CONNECT403 before any body.
There are no downloaded candle counts, binary hashes or decoded prices to report.

| Purpose | Requested public URL | Result |
|---|---|---|
| EURUSD BID, 2024-01-03 minute candles | `https://datafeed.dukascopy.com/datafeed/EURUSD/2024/00/03/BID_candles_min_1.bi5` | Proxy CONNECT403; zero bytes |
| EURUSD ASK, same day | `https://datafeed.dukascopy.com/datafeed/EURUSD/2024/00/03/ASK_candles_min_1.bi5` | Proxy CONNECT403; zero bytes |
| XAUUSD BID, same day | `https://datafeed.dukascopy.com/datafeed/XAUUSD/2024/00/03/BID_candles_min_1.bi5` | Proxy CONNECT403; zero bytes |
| XAUUSD ASK, same day | `https://datafeed.dukascopy.com/datafeed/XAUUSD/2024/00/03/ASK_candles_min_1.bi5` | Proxy CONNECT403; zero bytes |
| Official Dukascopy history/export page | `https://www.dukascopy.com/swiss/english/marketwatch/historical/` | Proxy CONNECT403; no terms reviewed |
| Official CME DataMine page | `https://www.cmegroup.com/market-data/datamine-historical-data.html` | Proxy CONNECT403; access/price/coverage unverified |
| Databento pricing | `https://databento.com/pricing` | Proxy CONNECT403; no price or free entitlement inferred |

An environment-settings network allowance for the intended source domains would
permit a fresh diagnosis. Preserve the existing allowlist; this review does not
replace it or change environment configuration. A later successful connection
must still verify the sample's content and source terms before a historical
adapter or download is approved.

## Legacy BI5 format: supported by third-party code, not a decoded vendor sample

The public `dukascopy-node` project explicitly says it is not affiliated with,
endorsed or vetted by Dukascopy Bank SA. Its **v1.46.4**, commit
`4bb92bcbcd2edf7c7d75783173f1dae40bee7ef4`, supplies a coherent legacy format
description. This verifies what that implementation expects; it does not verify
current Dukascopy bytes, contractual rights or broker execution.

- The URL generator uses the UTC year/day and **zero-based UTC month**: January
  is `00`. Daily minute files have the exact BID/ASK names probed above.
- The decompressor expects an LZMA file and **24-byte big-endian candle records**,
  equivalent to Python `struct.Struct('>5if')`: signed 32-bit
  `seconds, open, close, low, high`, then 32-bit floating volume.
- The normalizer adds `seconds * 1000` to the UTC daily bucket timestamp and
  divides all price integers by an instrument-specific decimal factor. The
  legacy metadata gives **EURUSD 100000**, **XAUUSD 1000**, and the USA500/USATECH
  index CFD instruments **1000**. These factors need vendor-sample calibration;
  they must not be guessed from a currency name.
- Hourly tick files use a different **20-byte `>3i2f`** record:
  `milliseconds, ask, bid, askVolume, bidVolume`; milliseconds are relative to
  the UTC hour. A candle decoder must never be reused for ticks.
- Candle volume is a vendor quote/feed field. It is not evidence of exchange
  executed volume, market depth or a broker contract quantity.

| Pinned third-party document | SHA256 of retrieved bytes |
|---|---|
| [Legacy URL generator](https://github.com/Leo4815162342/dukascopy-node/blob/4bb92bcbcd2edf7c7d75783173f1dae40bee7ef4/src/url-generator/index.ts) | `2f6c88b204e19217fb18746b8aa069e78cbc5d1d2c3fa44fa5da499bedbe861e` |
| [Legacy UTC date helpers](https://github.com/Leo4815162342/dukascopy-node/blob/4bb92bcbcd2edf7c7d75783173f1dae40bee7ef4/src/utils/date.ts) | `50fb038aa07a40cac325a918fc1ddca96b6591a47fc4a85440488422b36fa8b2` |
| [Legacy decompressor](https://github.com/Leo4815162342/dukascopy-node/blob/4bb92bcbcd2edf7c7d75783173f1dae40bee7ef4/src/decompressor/index.ts) | `9f2e4b548f2019a30904065fc345cff1a4197f4f7786f2f97fb0726ea71bc47c` |
| [Legacy normalizer](https://github.com/Leo4815162342/dukascopy-node/blob/4bb92bcbcd2edf7c7d75783173f1dae40bee7ef4/src/data-normaliser/index.ts) | `3270e2a2c14d8fe67baefc83776422b423a4485430640e42ae3f80fdf1619b3e` |
| [Legacy instrument metadata](https://github.com/Leo4815162342/dukascopy-node/blob/4bb92bcbcd2edf7c7d75783173f1dae40bee7ef4/src/utils/instrument-meta-data/generated/instrument-meta-data.json) | `b6203e4ca39b9fd23c8443124a18f8738209f0430bed6c7a8d4158eccf0732eb` |

The third-party legacy catalog claims minute/tick history beginning in 2003 for
EURUSD and XAUUSD, and minute data beginning in 2011 for the index CFDs. These
are **metadata claims, not acquired or audited coverage**. Spot gold XAUUSD is
not a CME gold future; USA500.IDX/USD and USATECH.IDX/USD are index quote/CFD
instruments, not executable ES/MES or NQ/MNQ contracts.

## The current library changed protocol and inserts synthetic gap candles

The same project's current **v1.50.0**, commit
`519a79017b49431c21049944934cce525f708ba5`, generates a JSON API protocol rather
than legacy BI5 URLs. Its instrument identifiers and response-supplied price
multiplier differ from the legacy format. This review did not contact that
alternative endpoint or use it to route around the denied legacy quote host.

Its current candle normalizer inserts flat, zero-volume candles when response
time deltas contain gaps. That is useful application behavior in some contexts,
but it is unacceptable as silent price imputation for the proposed immutable
research data. Preserve original gaps and classify them explicitly. The EURUSD
minute-history start timestamp also differs between legacy and current metadata,
so exact historical clock conventions need an observed vendor sample rather
than assuming the two protocols are identical.

| Current pinned document | SHA256 |
|---|---|
| [JSON URL generator](https://github.com/Leo4815162342/dukascopy-node/blob/519a79017b49431c21049944934cce525f708ba5/src/url-generator/index.ts) | `ce6bbaa4397768ab065347ef9311fe3965e03c9c9f00bf27da902b64825ab376` |
| [Normalizer, including flat gap insertion](https://github.com/Leo4815162342/dukascopy-node/blob/519a79017b49431c21049944934cce525f708ba5/src/data-normaliser/index.ts) | `857b54f73acf31208ec3e3f09b3e895b33485ce230f817c9035c97258dde8fce` |
| [Current instrument metadata](https://github.com/Leo4815162342/dukascopy-node/blob/519a79017b49431c21049944934cce525f708ba5/src/utils/instrument-meta-data/generated/instrument-meta-data.json) | `76b2ebc72624db19a3a2c4dbbe2ac1ac11a2d81db48f378fb2568dc3d0f26b36` |

## Proposed immutable quote adapter contract

No adapter or strategy was implemented in this feasibility task. Once source
access and terms are available, the first validation remains **one completed UTC
day of matching EURUSD BID/ASK plus one XAUUSD day**, before broader acquisition.

1. Store each original response separately with requested/final URL, UTC
   retrieval time, status/type, byte length, SHA256, requested instrument/date/
   side, decoder version and verified price scale. Empty, denied and absent are
   separate statuses; no failed response becomes a successful empty day.
2. Apply compressed/uncompressed size limits, validate LZMA decoding and exact
   record length, reject nonfinite/invalid OHLC/volume, validate UTC minute-open
   timestamps, monotonic ordering, uniqueness and within-day bounds. Preserve
   missing minutes and retain the original side data.
3. Pair only matching timestamped BID/ASK minutes and report unmatched rows,
   duplicate/overlap counts and calendar coverage. A matched minute alone does
   not prove that independently formed high/low extrema occurred simultaneously.
   Do not infer an instantaneous spread from `ask_high - bid_low` or a synthetic
   executable midpoint high/low.
4. Mark derived features as quote proxies. Decisions use completed bars only;
   a later NY/London/session conversion uses verified IANA zones without changing
   source UTC timestamps. Freeze signal definition, session calendar, costs,
   gap treatment and train/validation/final boundaries before return outcomes.
5. For an illustrative quote replay, long entry uses the next **ASK** open and
   long exit/stop/target uses **BID**; short entry uses **BID** and exit uses **ASK**.
   Add commission and adverse slippage separately, avoiding a second artificial
   spread charge on top of the actual two quote sides. Stop-first OHLC collisions
   and adverse gaps remain conservative; minute extrema cannot certify event
   ordering, order acceptance, queue position or fills at a prop broker.
6. Classify the result as **historical vendor bid/ask quote proxy**, not an
   executable broker backtest. Broker feed, asset specification, rollover/swap,
   latency, fee tariff, sessions, prop risk reset and actual order constraints
   require separate verification. Trading authority is unaffected.

Public accessibility alone does not establish permission to republish an entire
vendor history. Official export/data-use terms were inaccessible, so storage,
redistribution and automation rights remain unverified here.

## Futures intraday history beyond two years

No verified freely accessible multi-year CME intraday dataset was found or
downloaded. The existing Yahoo hourly MES/MNQ snapshots remain the existing
approximately two-year continuous-futures source; this review does not extend
their coverage or reinterpret an index CFD as a futures contract.

One concrete provider route is documented by the **official Databento Python
SDK**, pinned at commit `25eef4ee8e66559e2370166a57c20925ce244d49`:

- Its README demonstrates `GLBX.MDP3`, parent symbol `ES.FUT`, and a historical
  interval on **2022-06-10**, older than two years at this review date. It also
  documents top-of-book/order-book/trades/OHLCV schemas and point-in-time
  instrument definitions. This is evidence of a documented provider capability,
  **not an acquired current entitlement or proof of complete MES/MNQ coverage**.
- A user account API key is required. Official `get_dataset_range` explicitly
  reports availability **given the user's entitlements**. `get_cost` estimates
  historical request cost in dollars, with explicit symbol/schema/interval/limit
  fields. No account was created, key requested in chat, quote API called or
  expenditure authorized in this task.
- The appropriate future step is an entitlement-specific range and cost quote
  for fixed executable contracts and necessary quote schemas, then an explicitly
  authorized tiny sample. API credentials belong in secure environment settings.
  A free signup or public SDK does not imply free exchange data, zero cost or
  redistribution rights.
- CME DataMine is a separate official candidate, but its page was inaccessible;
  coverage, licensing, account requirements and price remain unverified. No
  free-history assertion is based on that inaccessible page.

| Official provider document | SHA256 |
|---|---|
| [Databento SDK README](https://github.com/databento/databento-python/blob/25eef4ee8e66559e2370166a57c20925ce244d49/README.md) | `5b494741354dc3f6aef08daffa1af1d4d3ddffc755b4b43543abb1141867a229` |
| [Databento historical metadata API: range/cost](https://github.com/databento/databento-python/blob/25eef4ee8e66559e2370166a57c20925ce244d49/databento/historical/api/metadata.py) | `f6e0d1dac704b017597b270a6ef5c7f21d8b446b4bb3b35d4fceddfae524d890` |

The next useful research prerequisite is actual, legally available bid/ask or
exchange quote data with audited coverage. This feasibility review supplies no
new profit evidence and makes no change to previous failed-strategy results.
