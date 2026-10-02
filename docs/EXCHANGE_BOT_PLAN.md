# Exchange strategy research and execution plan

The current priority is to evaluate a bounded, registered set of hundreds of
strategy variants, select at most one on training and validation data, and test
that locked selection on a later period. Telegram delivery and exchange order
execution are deferred until the evidence and execution prerequisites are met.
Failed hypotheses remain in the research registry; they are not trade alerts.

## Workstreams

* `research_lab`: a reproducible, costed, spot-long-only search over at least
  eight strategy families. Parameter variants are not independent discoveries.
* `liquidity`: causal sweep/structure/FVG hypotheses inspired by supplied charts.
  Chart labels and our numerical interpretation are not empirical evidence.
* `exchange`: official venue candle ingestion, archive checksums, closed-bar
  timestamps, completeness and source provenance.
* `research_stats`: dependent-return uncertainty, correlation diagnostics and
  explicitly qualified multiple-comparison screens.

The first data target is BTCUSDT and ETHUSDT on Binance Spot. Venue reachability
and completeness must be established; spot shorting is not assumed available.
The broader hourly study targets 2024 training, 2025 validation and the available
closed part of January–September 2026 for the final evaluation. Those dates are
fixed before outcomes. Missing data block conclusions, rather than disappearing
from the calendar. Separate five-minute research uses its own registered periods.

Research decisions are deterministic and versioned. A language model may propose
and implement an experiment, but cannot label a strategy qualified, change live
risk settings or send an order by writing a convincing explanation.

## Completion criteria

1. Input files have provider, instrument, timeframe, timestamps and hashes.
2. The grid, costs, selection rule and evaluation periods are frozen before use.
3. All trials and train/validation decisions are retained.
4. Only the locked primary is eligible for final assessment. A losing final
   result is not replaced with a diagnostic winner.
5. Fees, spreads, adverse fills and concentration/dependence limits are visible.
6. An historical candidate still needs genuinely later paper observations and
   verified venue execution before financial deployment.

Positive history is a conditional model result, not guaranteed stable profit.
If no candidate passes, the software must say so and send no qualified alerts.

## Persistent handoff

Each milestone records its source commit, input and protocol hashes, executed
tests, outcomes and next action in `PROJECT_STATUS.md` and the experiment
registry. Continue from these files when a chat's context is exhausted.
