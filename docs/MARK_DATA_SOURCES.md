# Official calculated-mark source history

This separate acquisition supplies **Binance USD-M BTCUSDT and ETHUSDT calculated-mark OHLC**, at five-minute resolution for 2024-01-01T00:00:00Z inclusive through 2026-10-01T00:00:00Z exclusive. It preserves every earlier trade-price, funding and strategy dataset. Computed marks may describe floating collateral risk during an absence of executed trades; they do not establish executable entries, exits or order fills.

The exact official monthly source pattern is:

```text
https://data.binance.vision/data/futures/um/monthly/markPriceKlines/BTCUSDT/5m/BTCUSDT-5m-2024-10.zip
```

Every original ZIP must match its adjacent `.zip.CHECKSUM`, contain its single expected CSV and preserve the exact twelve-field source header. The [official Binance connector](https://github.com/binance/binance-futures-connector-python/blob/a6bfbbf10fe2c1b4eb76fc24ffb82eb94bf9df89/binance/um_futures/market.py) describes `/fapi/v1/markPriceKlines` as kline bars for a symbol's mark price, uniquely identified by opening time. Its previously retrieved source SHA-256 is `9e55db014233d92bad66a90ec36212f1fada7f1f93a092ec5d6bc9298988659f`.

## Verified source probe

The BTCUSDT October 2024 monthly probe succeeded directly against the official domain: **227,784 ZIP bytes and 8,928 complete rows**. ZIP SHA-256: `f0a0db1bfec84b80e5d7e1f718d3d8a822585717aa10d26531ef2d8002170cd3`; CSV SHA-256: `80924f92d2d5e65d3f3f9bf50bb54308eb1c1fb8f68dbd66723bf83202db5bf9`. Original probe ZIP/checksum bytes and receipt remain under `.local/mark-5m-probe`.

The actual header is:

```text
open_time,open,high,low,close,volume,close_time,quote_volume,count,taker_buy_volume,taker_buy_quote_volume,ignore
```

Times are **integer UTC milliseconds in every year**, including 2025 onward. Five-minute `close_time` equals opening + 299,999 milliseconds. Observed OHLC strings have eight decimal places. Source volume, quote volume, taker volumes and ignore fields are zero; this is normal calculated-mark metadata. The source `count` field is retained as `source_auxiliary_count`, **not executed trade count**. In the October probe it is 300 on 8,921 rows and 299 on seven rows; uninterrupted sampling is not inferred from those counts.

During the known 14-bar native trade-price outage from 2024-10-28T20:00:00Z through 21:10:00Z, all 14 corresponding official mark bars have nonflat OHLC and auxiliary count 300. This is independent calculated-mark information; no executable quote is manufactured for those intervals.

## Preserved incomplete source revision

The first full-calendar acquisition rejected **both June 2026 monthly mark ZIPs**: each has 8,352 rows instead of 8,640, omitting all 288 June 29 opening labels. All other 64 monthly archives passed. No complete canonical output was certified from that run.

- BTC incomplete June ZIP SHA-256: `e02cf899d32a506fcb3165e795040dadea291989bdd12082bec1a83875d908fc`.
- ETH incomplete June ZIP SHA-256: `de38736aea72c09d2802071b7c49bb108557fc5a5c81022bf8d706fd7e42430d`.
- Preserved blocked manifest SHA-256: `3029309a8533141dda91ddc4ade82b3b470d07cdf69552caa75cc367ba7e65fe`.
- Preserved original protocol SHA-256: `252c687ff8cae38ab9a65f3469710794b5dc45f11487e96ca9e7e292deeab250`.

The blocked manifest/protocol remain under `.local/mark-5m-history`; the original captured producers are preserved under its `producer-source` directory. Original rejected monthly bytes, checksums and exact missing timestamps are recorded under `.local/mark-5m-probe/june-incomplete`, receipt SHA-256 `0d988c1d50dee103dbbfd4aca4aaa36768e65482e41694762b155bd51c7ffe1e`.

## Separately registered complete-source revision

The official June 29 **daily** mark archives are available and checksum-verified for both instruments. A new data protocol, `binance-usdm-btceth-calculated-mark-five-minute-2024-2026-v2`, therefore replaces the entire June container with **all 30 official daily archives per instrument**. It never inserts one invented bar, borrows a trade-price value or fills a stale mark forward. Every daily file must be complete, consecutively labeled and checksum-verified. Existing monthly-overlap OHLC must agree exactly with the official daily values; disagreement or any missing daily file leaves the revision blocked.

This source-container correction was registered from a documented calendar defect before new mark-strategy outcomes. It leaves all trading hypotheses and historical qualification requirements to their separate frozen study protocols. The other 64 monthly sources reuse only original bytes that pass their original checksums again.

The separate [mark decoder](../propdesk/mark_data.py), [initial downloader](../scripts/download_mark_5m.py) and [complete-source downloader](../scripts/download_mark_5m_complete.py) record original CSV hashes, full source coverage, producer hashes, preceding blocked-revision hashes and exact opening-label identity with the immutable native trade calendar. Twelve decoder/initial-policy tests and seven revision tests passed before acquisition.

```sh
python scripts/download_mark_5m_complete.py \
  --data-dir .local/mark-5m-complete-history \
  --native-data-dir .local/perp-5m-history --workers 6
```

Canonical files are `{BTCUSDT,ETHUSDT}-mark-5m.json`: lists of `time`, `open`, `high`, `low`, `close`, `known_at` and `source_auxiliary_count`. They omit trade-volume fields to preserve source meaning. All complete five-minute labels must match the separately frozen native calendar; source prices are never equated.

## Actual complete acquisition

Revision 2 completed with **289,152 bars per instrument, 124 used official ZIP/checksum pairs and zero failures**: 32 monthly and 30 June daily files per instrument. All 8,352 preserved June monthly rows agree with their daily counterparts in both OHLC and auxiliary count. Every complete label equals the immutable native trade label; every `known_at` equals opening + five minutes. Original raw checksums and CSV hashes were independently reverified after acquisition.

| Receipt or canonical file | SHA-256 |
| --- | --- |
| [Complete source manifest](../data/mark-resolution/manifest.json) | `9887c9b08a73a6a63e71c00815f45d9534977045e15d79805e10ae4f37f59e94` |
| [Complete source protocol](../data/mark-resolution/protocol.json) | `84c03585b12b75ada698f942581953ddd4e56e9c96b474b12f748c38c7fc1aef` |
| BTCUSDT canonical JSON | `4ca24c13af46cb6650e88f2aa26a113e7b45bb036a920818d45a93d1e1f39265` |
| ETHUSDT canonical JSON | `cc0b1d5c0e2116f4a7907f70511e57a6ad2dbdf6f6579948df558ec0eb7dde65` |
| [Independent full-source audit](../data/mark-resolution/source-audit.json) | `339d1f7ce0784f871ad8c9ca9c1f044c0cd790c07ef1b009ca315790f6c95b96` |

Canonical JSON sizes are 49,036,413 bytes for BTC and 48,150,582 bytes for ETH. Both share opening-label SHA-256 `56dca16f339ecda30266d43f98498a2153014ab2ce6621c6a7810bd396a586d9`. All captured producer hashes match the actual unchanged files. The repository retains byte-identical small copies of the complete receipts and of the [blocked original manifest](../data/mark-resolution/blocked-v1-manifest.json) and [original protocol](../data/mark-resolution/blocked-v1-protocol.json).

All **21 absent-trade intervals per instrument** have nonflat calculated-mark OHLC and auxiliary count 300. This directly supplies historical mark information missing from the traded-price records. Separately, both calculated-mark datasets contain six very sparse auxiliary-count ≤ 2 records on **2025-05-12 from 09:25 through 09:55 UTC**: five flat records with count 1 and one nonflat record with count 2. No record has auxiliary count 0. These original sparse observations are preserved; complete calendar coverage must not be described as proof of continuously observed mark sampling. Later research must retain that distinction before interpreting collateral or liquidation bounds.

## Causal and account interpretation

The UTC opening label does not make the following five-minute high, low or close known at opening. Complete mark bars become usable no earlier than opening + five minutes; publication delay remains unverified. Entry sizing must use a preceding completed mark or another separately justified contemporaneous observation. Historical mark extrema can provide provisional floating-equity bounds after the interval is observed, while entry and exit prices continue to require genuine trade evidence.

Five-minute calculated-mark OHLC and auxiliary counts do not prove a continuously observed tick path, broker bid/ask, liquidation priority, historical account tiers or exact maintenance-margin rules. Missing or uncertain marks must remain visible. Source acquisition improves evidence; it does not by itself certify strategy profit or live prop-account eligibility.

Binance Vision CC BY-NC-SA 4.0 attribution and the previously verified personal non-production historical-research terms apply. Original ZIPs and canonical source prices remain local and excluded from application packages. Public repository files retain small source receipts and code only; no credentials, orders or account information are used.
