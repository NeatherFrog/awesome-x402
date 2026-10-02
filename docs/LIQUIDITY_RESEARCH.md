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

`scripts/research_liquidity.py` writes the protocol before acquisition. Official archive checksums and canonical CSV/JSON hashes are retained in the manifest. The initial July–September acquisition was marked limited and did not certify the full-calendar study. Subsequently, a distinct full official snapshot under `.local/exchange-full-history` supplied **289,152 consecutive five-minute bars per instrument**, with reconstructed CSV/source manifest hashes verified before the frozen study ran.

## Full registered study completed

The four original policies were tested on the original 2024 training, 2025 validation and January–September 2026 final periods: **24 period/instrument evaluations**, with no policy or source-code change. The source engine hash is `1d309d7316a494e8d49b0b0b78166f2946ad0fadf164ff9b5b35c75cb554f3b1`; research producer hash is `e360898edf3c76029b90c9dc7ed6478f35a195fd7aa998b809197392bd17c237`.

All four 2024 aggregate training scores were negative, so **no strategy was selected before validation/final inspection**:

| Policy | BTC 2024 net return | ETH 2024 net return | Aggregate training net PnL |
| --- | ---: | ---: | ---: |
| sweep_all | -29.6234% | -22.5634% | -52,186.86 |
| mss_all | -19.4071% | -16.4974% | -35,904.52 |
| sweep_lunch | -1.4167% | -0.9761% | -2,392.79 |
| mss_lunch | -0.6736% | -0.9761% | -1,649.70 |

Aggregate scores add two independently modeled 100,000-USDT simulations for the preregistered selection rule; they are not a portfolio-return claim. The saved training lock has SHA-256 `0389964aa1c97c73b15bf07901ee62cc1052221848a1ebe17a9be379c17ec535` and retains `selected: null`.

The final January–September 2026 period confirms the all-day variants' losses:

| Instrument | Policy | Trades | Net return | Profit factor | Maximum drawdown |
| --- | --- | ---: | ---: | ---: | ---: |
| BTCUSDT | sweep_all | 190 | -23.6823% | 0.1548 | 24.1128% |
| BTCUSDT | mss_all | 118 | -15.9517% | 0.1496 | 16.3996% |
| ETHUSDT | sweep_all | 127 | -15.0657% | 0.2295 | 15.1039% |
| ETHUSDT | mss_all | 89 | -12.0606% | 0.1844 | 12.2394% |

Lunch variants have only one to three final trades per instrument. ETH `mss_lunch` has a positive **+0.12553% from one trade**, following negative 2024 training. ETH's two lunch policies have positive +0.20400% validation results from five trades. These small later-period observations cannot replace a rejected training policy or demonstrate stable profit. **All policies remain unqualified and the selected strategy remains null.**

The [full machine-readable report](liquidity-full-research.json) contains every period's metrics and frozen plan/source lineage. The original acquisition-blocked report remains byte-for-byte in [liquidity-full-blocked.json](liquidity-full-blocked.json), SHA-256 `4df269471700df784e998f1294fd332a25195e38d59730e60ae7367faed9a22f`. Completing acquisition resolves that historical blocker without rewriting the earlier evidence.

This is a preregistered **retrospective** comparison. Shared 2026 market-price history was already inspected in prior Yahoo studies and the separate July–September quarter replay. Official Binance acquisition changes provenance, not that earlier exposure; 2026 must not be described as globally untouched or as prospective live trading. No selection is changed after seeing its outcomes.

## Actual quarter results

Official archive acquisition succeeded on [GitHub Actions run 36990296162](https://github.com/NeatherFrog/awesome-x402/actions/runs/36990296162), source commit `5c9d14d21a38b9745863e9e12c860c5af9c13867`. Each instrument has **26,496 consecutive five-minute bars**, July 1 through September 30, 2026. July/August monthly ZIPs and all thirty September daily ZIPs passed their official adjacent SHA-256 checksums. The development runtime's direct venue requests still returned proxy CONNECT 403; acquisition on the GitHub worker does not prove local live-API access.

The separate [quarter protocol](liquidity-quarter-protocol.json) was registered before acquired-data performance was inspected: SHA-256 `005dc1e7bea522fc6f5f584da2bbf627a19e475f0bdcff752a4e69c0f855e8c0`. It specifies **eight descriptive replays and no selected winner**. This quarter does not replace the original full-calendar training/validation/final protocol, now completed separately above. The quarter report and protocol remain unchanged.

| Instrument | Fixed variant | Trades | Net return | Profit factor | Maximum drawdown |
| --- | --- | ---: | ---: | ---: | ---: |
| BTCUSDT | sweep_all | 84 | -11.0171% | 0.1303 | 11.5191% |
| BTCUSDT | mss_all | 56 | -7.9786% | 0.1121 | 8.4690% |
| BTCUSDT | sweep_lunch | 1 | -0.2500% | 0 | 0.2500% |
| BTCUSDT | mss_lunch | 1 | -0.2500% | 0 | 0.2500% |
| ETHUSDT | sweep_all | 52 | -7.1548% | 0.1954 | 7.3046% |
| ETHUSDT | mss_all | 40 | -6.9340% | 0.0912 | 6.9340% |
| ETHUSDT | sweep_lunch | 1 | -0.2500% | 0 | 0.2500% |
| ETHUSDT | mss_lunch | 0 | 0% | Undefined | 0% |

**Every nonempty replay lost money after modeled costs.** No stable-profit, live qualification or prop payout claim follows. A screenshot's visual pattern did not produce a profitable mechanically defined strategy in these tests; different hypotheses require separate registration and genuinely new verification data.

The [machine-readable report](liquidity-research.json) retains all trials, directional counts, engine/input/producer fingerprints and descriptive uncertainty. Seven-calendar-day circular block bootstrap includes all 92 calendar days and zero-trade days; 4,000 deterministic replications give nominal individual 99.375% intervals for eight comparisons. These are approximate sample-dependent estimates, not proof of calibrated familywise error, independent market regimes or future performance. They summarize realized exit-PnL rather than daily unrealized equity.

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

Reproduce the full frozen study from the full snapshot:

```sh
python scripts/research_liquidity.py --research-only --data-dir .local/exchange-full-history --output docs/liquidity-full-research.json
```

Reproduce the distinct registered quarter replay from the complete July–September snapshot:

```sh
python scripts/research_liquidity.py --quarter-replay --data-dir .local/exchange-history --output docs/liquidity-research.json
```

The hourly research protocol is separate: acquiring the same two instruments' 1h snapshots does not count as an SMC strategy test, and that research must register its own variants and selection rule before inspecting validation/final outcomes.

Historical data attribution: **Binance Vision**, [official public data](https://data.binance.vision/), retrieved 2026-10-02. Historical data and this derived numerical research use **CC BY-NC-SA 4.0**, subject to the [dataset terms](EXCHANGE_SOURCES.md). Application source licensing is separate.
