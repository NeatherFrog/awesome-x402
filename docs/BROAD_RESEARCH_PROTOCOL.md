# Bounded research protocol: venue spot

The user requested substantive statistical research before Telegram work. This
study searches a fixed, finite hypothesis pool and may honestly return no
qualified candidate. The prospective strategy must earn its qualification;
neither a visual liquidity illustration nor a positive selected backtest proves
stable future profitability.

## Scope frozen before outcomes

208 parameter variants across **nine hypothesis families**, not208 independent
strategies:

| Family | Economic hypothesis | Variants |
| --- | --- | ---: |
| Moving-average trend | Persistent price direction after crossover |24|
| Donchian breakout | Prior range escape in an established trend |24|
| RSI pullback | Short-term overshoot within an upward market |24|
| Bollinger pullback | Price-distance reversion toward a rolling mean |24|
| Negative return shock | Abrupt standardized hourly return reversal |24|
| Time-series momentum | Positive cumulative return continuation |24|
| ATR expansion | Directional continuation after unusually large range |16|
| Volume breakout | Prior range breakout with unusually high activity |24|
| Trend retracement | Fast EMA recovery inside a slower upward trend |24|

The exact grids, indicator rules, producer hashes and gates live in immutable
`data/broad-research/protocol.json`; its hash is copied into the report. Families
with similar behavior can have highly correlated returns. More variants do not
mean more independent evidence. No unspecified indicator, threshold, market,
news filter or execution assumption may be swapped after outcomes are read.

The registered market is **Binance spot BTCUSDT and ETHUSDT, one-hour bars**.
2024 is training;2025 validation; January–September2026 final. Prior history warms
indicators; each evaluation window starts in cash. Exactly contiguous UTC hourly
bars, matching BTC/ETH clocks, full registered coverage, official-source receipt,
exact CSV SHA256 and canonical price fingerprints are mandatory. No other venue,
Yahoo series, synthetic series, missing-date deletion or imputation can replace
this dataset. Unit-test fixtures are explicitly synthetic and are not research.

## Causal execution and costs

At each bar open the engine observes only the previous fully closed candle.
Signals fill at the next open. Buy fills are increased and sell fills decreased
by2bps slippage and half the modeled1bp full spread. Both sides incur10bps fees.
These are assumed tariffs, not evidence of an executable personal account fee.
Cash spot has no funding, borrowing, leverage or cash-interest credit.

A100,000 account allocates50,000 cash and250 absolute stop-risk budget per asset.
Exposure cannot exceed available cash; quantity uses a modeled0.000001 increment.
This increment and minimum-order filters have not been certified against actual
historical venue rules. All variants use fixed2ATR14 or3ATR14 protection and a
bounded holding period. Fees and opening gaps can exceed the nominal risk budget.

Opening-gap stops precede prior-known indicator/time exits. Otherwise intrabar
low-touch stops execute at the stop with adverse sell friction. Protection can
trigger on the entry candle. No same-candle reentry is allowed. At a sample
boundary the last-bar new entry is disabled and open positions are liquidated at
the final close, explicitly labeled hypothetical boundary liquidation. Intrabar
timestamps remain unknown; open and boundary-close execution timing are recorded
separately. Summed per-asset low equity is conservative because lows may not be
simultaneous.

## Selection without final winner replacement

All208 variants are evaluated on training. The fixed chronological folds are
February–April, May–August and September–December2024. Training candidates need
positive net and doubled-friction returns,40 trades, worst intrabar drawdown at
most15%, and two positive folds. The score is net return divided by
`max(drawdown,0.25%)`; ties resolve lexicographically by registered ID. At most one
candidate per family enters the immutable training shortlist.

Only that shortlist, at most nine candidates, is evaluated on2025 validation.
Each needs positive net and doubled-friction returns,20 trades, worst drawdown at
most12%, and Holm-adjusted one-sided seven-day block sign-randomization diagnostic
at most0.05 across the full shortlist. One highest-scoring survivor is locked in
`validation_selection.json` **before any final performance evaluation**. No
survivor means final performance remains unopened. A failed final cannot be
replaced by another candidate.

The block-sign test assumes independent symmetric block signs. Financial series
may violate that assumption; Holm cannot repair an invalid null model. All208
training adjusted values are diagnostic and are retained, rather than offered as
proof. Unavailable p-values are treated conservatively as1 in multiplicity counts.

## Final qualification

The single locked candidate needs positive costed and doubled-friction returns,
at least50 trades,180 daily observations and six calendar months, worst intrabar
account drawdown at most10%, day-opening-to-intrabar loss at most2.5%, positive
returns in both fixed halves, and no month exceeding half of the sum of positive
monthly returns. Its99% mean-daily-return interval must have a strictly positive
lower bound: circular seven-day moving blocks,5000 resamples, registered seed.

The interval is conditional on suitable dependence modeling and sufficient
stationarity. It is not the probability that future trading will be profitable.
Passing these checks yields a **retrospective candidate**, never automatic live,
prop or payout qualification. Fresh forward paper observations, executable fees,
venue precision filters and order reconciliation remain outstanding.

## Correlations, benchmark and reproducibility

Training-only daily strategy-return correlations quantify overlap. Six observed
features per asset are compared descriptively with1/6/24-hour forward log returns:
return, RSI14, distance to SMA200, ATR fraction, volume ratio and24-hour momentum.
All36 inspected feature/horizon/asset relationships are recorded. Overlapping
labels and dependent observations prevent a naive independent-observation
significance interpretation. No final feature labels are used in selection.

The report includes exposure, turnover, modeled fees and adverse-fill costs. A
costed equal-cash spot buy/hold benchmark and descriptive daily beta/intercept
help identify market-direction exposure. The benchmark is not risk-matched;
return difference and OLS intercept alone are not statistically established alpha.

Protocol, input, training-selection, validation-selection and final-result locks
are immutable and hashed. Source CSVs stay outside published artifacts. Full
rejected results remain in the research ledger; rejected signals are not sent to
the user. Changing the code or grid requires a separately named new exploratory
protocol that acknowledges any already inspected data.

## Reproduce

```sh
python scripts/research_broad.py --freeze
python scripts/research_broad.py --run \
  --data BTCUSDT=.local/exchange-history/BTCUSDT-1h.csv \
  --data ETHUSDT=.local/exchange-history/ETHUSDT-1h.csv \
  --manifest .local/exchange-history/manifest.json
python -m unittest tests.test_research_lab tests.test_research_stats
```

No Telegram message, exchange order, account creation, purchase or withdrawal is
part of this study. A Telegram implementation follows only after the research
result meets the chosen evidence requirements and the user-facing strategy can
be stated concretely.

Acquisition provenance: official archives were downloaded and SHA256-checked on
GitHub Actions run36990296162 from source5c9d14d21a38b9745863e9e12c860c5af9c13867.
The local export index records original ZIP/checksum receipts and the archive
license (CC BY-NC-SA). This is a personal, non-production backtest study; no
commercial redistribution permission or production-data license is asserted.
