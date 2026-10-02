# Same-venue five-minute perpetual inputs

Separate registered data protocol: `binance-usdm-btceth-five-minute-2024-2026-v1`, declared 2026-10-02. Acquire **BTCUSDT and ETHUSDT USD-M perpetual trade OHLCV**, from 2024-01-01T00:00:00Z inclusive through 2026-10-01T00:00:00Z exclusive. Each complete instrument must contain **289,152 consecutive five-minute UTC opening labels**. Existing funding, Spot, quarterly and hourly snapshots/producers are not changed.

Official example:

```text
https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/5m/BTCUSDT-5m-2024-01.zip
```

Every ZIP must match the adjacent `.zip.CHECKSUM`, contain exactly its documented CSV and preserve twelve-field source kline order. USD-M timestamps remain **milliseconds**, including 2025 onward; the Spot microsecond change is not applied. Gaps, malformed OHLCV, duplicate/reordered timestamps, wrong units, incomplete source months and altered cached bytes fail validation. No substitute prices or bars are invented.

If September 2026's monthly ZIP returns HTTP404, only its complete thirty same-venue official daily ZIPs may replace that one unpublished monthly container. Failure of any required source prevents a complete canonical output. Funding histories remain separately sourced; this acquisition does not manufacture funding, mark prices, maintenance-margin paths or executable bid/ask.

The [new parser](../propdesk/perp_resolution.py) reuses only the unchanged checksum/TLS helpers and canonical kline converter. The [new downloader](../scripts/download_perp_5m.py) writes its data protocol before acquisition; preserves original ZIP/checksum bytes; and records source original CSV hashes, canonical fingerprints, full source coverage, both assets' shared UTC label hash and all producer hashes. Inputs are stored under `.local/perp-5m-history`; raw files are excluded from Git/application packages.

The actual development-worker probe on 2026-10-02 returned **HTTP200**, with408,813 bytes for the official BTCUSDT5m January2024 ZIP, recorded at `.local/perp-5m-access-probe.json`. Earlier session-level access failures are not substituted for this current observation. Full acquisition still verifies every adjacent checksum before accepting data. A proposed [GitHub Actions workflow](../.github/workflows/perp-5m-data.yml) can acquire the same official sources on the repository's own runner and publish attributed canonical research-only JSON on a separate `perp5m-data-<producercommit>` branch. All source pushes remain coordinated by the parent task; default main is not changed by this downloader.

## Actual completed acquisition

Direct official acquisition completed with **all66 monthly ZIPs checksum-verified and zero failures**. September's monthly files were available, so no daily fallback was used in this run. Each instrument has289,152 bars; canonical JSON files are31,767,606 bytes(BTC) and31,692,056 bytes(ETH). Raw ZIP/checksum pairs and canonical prices remain local; only small [source manifest](../data/perp-resolution/manifest.json) and [data protocol](../data/perp-resolution/protocol.json) receipts are retained in the application repository.

- Manifest SHA-256: `a849e9ae1891a8974bedd1dd294e0779a7f8cbf5d0cdffdd1416c91049403ea3`.
- Protocol SHA-256: `221d0b2905545ee641b6d4f35c3259830811060c169b5ecd415d710498370995`.
- BTC canonical JSON SHA-256: `d97e8537641ec3133b3866e12acb5d39ed394303031c1ec39694e428fdce3948`.
- ETH canonical JSON SHA-256: `55382a96966c51f9d314d2f8f7a37c02eaed1bf3bb5441b64b37d395308002ab`.
- Both open-label SHA-256 values: `56dca16f339ecda30266d43f98498a2153014ab2ce6621c6a7810bd396a586d9`.

Every actual UTC label was compared against the separately frozen full Spot CSVs and matched exactly; the prices remain different independently acquired markets. All recorded producer-file hashes matched the unchanged source after acquisition. Twelve parser/downloader tests passed. No CI push, publication or trading performance calculation was performed to obtain these local inputs.

Public research exports include the frozen protocol, source manifest, producer publication receipt, Binance Vision attribution and CC BY-NC-SA4.0 licensing. The [official dataset terms](https://github.com/binance/binance-public-data/blob/f446ce3812bd4e5521f21faecd4ae3c6460e49fc/TERMS_AND_CONDITIONS.md) permit personal non-production historical research; production-trading permissions remain unverified. Export never contains credentials, account data or trading orders.

Five-minute synchronized **opening labels** improve resolution; they do not reveal joint tick paths or prove that two legs' separate OHLC extrema occurred together. A later spread study must not invent residual highs/lows by combining incompatible leg corners, use future closes for fills, or describe these reused 2024–2026 price regimes as a fresh prospective test. Perpetual prices stay independently sourced and are never equated with Spot prices. Slippage, both legs' costs, funding, margin, liquidation and basis risk still require explicit modeling and new forward verification.

```sh
python scripts/download_perp_5m.py --data-dir .local/perp-5m-history --workers 6
```

`--publish-ci` is restricted to this repository's own authorized Actions runtime; it is not a local publication bypass. No profitability claim follows from acquiring or validating this dataset.
