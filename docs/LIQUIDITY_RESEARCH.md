# Fixed liquidity / FVG study

Protocol declared on 2026-10-02 **before any strategy returns were calculated**. The screenshots motivated a measurable hypothesis: take prior liquidity, create a directional displacement and three-candle fair value gap, then test a later return into the gap. Chart examples are not statistical evidence.

Four fixed variants are retained: `sweep_all`, `mss_all`, `sweep_lunch`, `mss_lunch`. The strategy engine documents its exact causal pivot/sweep, displacement, structure-shift, gap-entry, stop, target and expiry definitions; lunch variants use America/New_York local time with daylight saving rules. One entry attempt cannot fill on the candle that first confirms its setup. OHLC same-bar entry/stop/target uncertainty is disclosed rather than turned into favorable fills.

## Frozen data and evaluation

- Venue and instruments: Binance **Spot BTCUSDT / ETHUSDT**, 5-minute closed bars, USDT quote units.
- Training: January 1, 2024 inclusive through January 1, 2025 exclusive.
- Validation: January 1, 2025 through January 1, 2026.
- Final descriptive test: January 1, 2026 through October 1, 2026.
- Training selection: highest positive aggregate training net profit across the two equal-sized instrument simulations; if no variant is positive, selected strategy is null. Save `training-lock.json` before later-period performance is inspected. A failed winner is never replaced using validation/final results.
- Fixed modeled costs: fee 10 bps per side, slippage 2 bps per side, full quoted spread 1 bp. These are explicit assumptions rather than a verified personal Binance fee tier.
- Initial modeled balance 100,000; position risk 0.25%; maximum gross leverage 1; gap entry expiry six bars. The two instruments are separate simulations, not an independently verified portfolio.
- Every trial and failed data request remains in the ledger. Gaps, duplicates, malformed OHLC, wrong timestamp units, mismatched checksums and partial calendars are rejected. No imputation or replacement market is used.

`scripts/research_liquidity.py` writes the protocol before acquisition. Official archive checksums and canonical CSV/JSON hashes are retained in the manifest. Downloading only July–September 2026's 5-minute data is an infrastructure acquisition phase; `limited_acquisition=true` and `complete_calendar=false` prevent it from certifying the full-calendar study or being silently substituted for training.

## Current result

Data acquisition is pending. The development runtime's direct venue requests returned proxy CONNECT 403. Official specification/terms were read from the pinned upstream GitHub repositories. **No historical profitability, robust edge, broker fills or live strategy qualification is claimed at this stage.**

The engine may model both long and short chart setups, but spot short borrowing, derivative funding, borrow fees, instrument filters, executable liquidity and account eligibility are unverified. Consequently a positive chart backtest remains unqualified for live trading. The archived dataset terms also require separate production-data verification before deployment. Telegram delivery and live orders remain disabled.

## Reproduction

Acquire official data, retaining raw snapshots outside Git/application packages:

```sh
python scripts/research_liquidity.py --download-only --intervals both --workers 6 --data-dir .local/exchange-history
```

For the first, intentionally limited 5-minute acquisition while acquiring the full hourly dataset for a separate broad study:

```sh
python scripts/research_liquidity.py --download-only --intervals both --5m-start-month 2026-07 --workers 6 --data-dir .local/exchange-history
```

Only after the full frozen 5-minute calendar exists:

```sh
python scripts/research_liquidity.py --research-only --data-dir .local/exchange-history --output docs/liquidity-research.json
```

The hourly research protocol is separate: acquiring the same two instruments' 1h snapshots does not count as an SMC strategy test, and that research must register its own variants and selection rule before inspecting validation/final outcomes.
