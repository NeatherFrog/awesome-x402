# Statistical research protocol

The objective is a reproducible net-return hypothesis suitable for future paper
trading. Neither a positive historical result nor passing this protocol proves
stable future profit. Synthetic tests validate software only.

## Data and selection

Use exchange-specific hourly BTC/ETH spot candles only after verifying source,
completeness, timestamps and archive hashes. Long-only spot does not test short,
leveraged perpetual, FX, metal or prop-account execution. Use calendar UTC daily
marked account equity, retaining flat days and open-position costs. Account
returns are decimal fractions. Never count every correlated hourly observation
or trade as an independent sample.

The account arithmetic is explicit: daily return
`r[t] = E[t] / E[t-1] - 1`; compounded return
`R = product(1 + r[t]) - 1`; and close-equity drawdown
`DD = max_t(1 - E[t] / max_{s<=t} E[s])`. Trading cash and marked positions,
not the sum of individual percentage trade returns, define `E[t]`.

Freeze all candidate parameters, split boundaries, cost assumptions, selection
rules and trial counts before outcomes are inspected. The intended splits are
2024 training (January warmup), 2025 validation and January–September 2026 final.
Previously inspected data cannot honestly be described as unseen. Every added
feature, lag, parameter, market and post-result variation is another inspected
hypothesis. Keep failed experiments internally; do not send rejected setups as
trade signals.

Select fixed family representatives using training only. Evaluate the frozen
shortlist on validation, then fix one primary candidate before accessing final
performance. If it fails, publish no qualifying strategy. Selecting its runner-up
using the same final results would consume the holdout. Further redesign needs
new future data, not renamed old data.

## Dependence, uncertainty and multiple comparisons

`propdesk/research_stats.py` provides a deterministic circular moving-block
bootstrap percentile interval for mean daily net account returns. Report a 99%
interval, sample count, seed and block length. Seven consecutive days is a
declared primary block choice; longer blocks can be reported as sensitivity
checks, counted as additional inspected results. A bootstrap assumes sufficiently
stationary observations and an adequate block length. It cannot cover arbitrary
regime changes, model selection or missing data.

Pearson correlation and autocorrelation return `null` for zero variance or too
few observations. Descriptive feature[t]/return[t+lag] correlations use training
only and causally available features. Correlation is not causal evidence and
does not establish profit after execution costs.

Pearson's coefficient is
`sum((x-x_mean)*(y-y_mean)) / sqrt(sum((x-x_mean)^2)*sum((y-y_mean)^2))`.
Each bootstrap replication concatenates sampled circular daily blocks, trims
to the original daily sample length and calculates its mean. The 99% percentile
interval uses replication quantiles 0.005 and 0.995, with linear interpolation.

The block sign-flip diagnostic flips complete nonoverlapping daily-return blocks
and measures a one-sided positive-mean statistic. Its null requires independent,
jointly sign-symmetric block sums. Those assumptions are not verified merely by
running this code and may fail for financial returns. Fewer than 12 blocks yields
no p-value. Finite Monte Carlo values include a +1 correction and a recorded seed.
Do not label this a distribution-free p-value or a probability of profitable
trading.

For observed statistic `T = sum(r[t])`, Monte Carlo diagnostic
`p = (1 + count(T_random >= T)) / (B + 1)` for `B` sign randomizations. Nonpositive
observed mean is conservatively assigned 1. With `m` registered trials and sorted
raw probabilities `p_(i)`, Holm adjusted values are
`min(1, max_{j<=i}((m-j+1)*p_(j)))`, mapped back to their original trial IDs.
Monte Carlo resolution matters: at 208 trials, 9,999 randomizations cannot yield
a smallest Holm-adjusted value below 0.0208. Do not imply a 1% rejection when
the randomization count cannot resolve that threshold.

Apply Holm adjustment across every registered training variant and separately
across the complete frozen validation shortlist. Report raw and adjusted values.
Holm tolerates dependent tests when marginal p-values are valid; it cannot make
the sign-flip model valid or repair unrecorded trials. Any familywise-error claim
is therefore conditional on the diagnostic's null assumptions. The optional
Benjamini–Hochberg function is exploratory: its usual independence or positive
dependence conditions are not established for a correlated strategy grid.

## Qualification and execution limits

For one preselected candidate, the statistical screen requires positive final
net return, positive final return under increased costs, a positive lower 99%
mean-daily-return interval, at least 50 closed trades, at least 180 calendar days
and six calendar months, no single month contributing more than half the sum of
positive monthly returns, and marked close-equity maximum drawdown at most 10%.
All conditions must be fixed before final evaluation. Fifty trades is a minimum
activity threshold, not 50 independent observations. The engine should separately
enforce intrabar and daily adverse-equity risk; a close-equity drawdown alone
cannot establish compliance with a prop-firm drawdown rule.

Report a cash baseline, a synchronized buy-and-hold benchmark, market-return
correlation, exposure/turnover and gross versus net costs. Positive return that
merely reflects long market exposure is not evidence of unique trading skill.
Increase costs in the actual execution engine; do not subtract an arbitrary
aggregate afterward. Include fee, bid/ask or slippage, lot precision, gaps and
conservative same-candle stop/target priority. Funding and borrowing must be
added before claiming a futures or shorting result.

Passing means **eligible for a genuinely future forward test**, not ready for
unattended real-money trading. Forward evidence must come from later data and
include venue-specific order acknowledgments, actual fills, retries, reconnects,
position reconciliation and risk-limit behavior. Telegram trading signals are
deferred until a candidate qualifies and the user has a reviewed working result.
