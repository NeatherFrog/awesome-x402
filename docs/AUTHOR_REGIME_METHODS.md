# Original author methods for causal trend and regime research

This audit follows the reopened research request on 2 October 2026. It verifies
selected methods in actual author code and published author summaries. It does
not claim a profitable strategy, 8% monthly returns, complete paper reviews or
historical reproduction. Every native request and code-body hash is recorded in
[author-regime-methods.json](author-regime-methods.json).

## Source revision and preserved payout bindings

The earlier high-return source handoff had JSON SHA-256
`01f3b4ef0b93679e8b44858c554f0df06527ddd7a42dd80d20d28c3151fc9597`.
The subsequently reopened source pass appended retrieval attempts and author-code
findings before the later instruction to preserve that file arrived. The current
source JSON snapshot is
`b47f3ccd66d61a0fbb09d891763f32270d13ad7244cc193d13c23b511d1691d5`;
its complete bytes are preserved under `.local/source-revisions/`.
The matching Markdown SHA-256 is
`5e5d05c575d61eaf75133daefed6ce7188d14c4ed9344ef1a1aa6941731a413f`.

No earlier timestamp or matching hash was invented. All twelve official receipt
objects bound by [prop-payout-objective.json](prop-payout-objective.json) remain
exactly equal to their corresponding source objects. That report binds individual
official receipts and has no whole-document source-hash gate. All further author
investigations are isolated in this audit; preserved source bytes remain unchanged.

## Actually verified author code

| Source | Pinned tree | Review scope |
| --- | --- | --- |
| [Slow Momentum with Fast Reversion](https://github.com/kieranjwood/slow-momentum-fast-reversion/tree/b22006066c274cd5953446baf24b99a2726068e4) | `b22006066c274cd5953446baf24b99a2726068e4` | Daily baselines, rolling changepoint model, feature preparation |
| [Momentum Transformer](https://github.com/kieranjwood/trading-momentum-transformer/tree/e0352cb0bdbf8045accb1bf1a5705ae0cb9ea624) | `e0352cb0bdbf8045accb1bf1a5705ae0cb9ea624` | Sharpe loss, chronological splits, turnover costs, backtest normalization |
| [DeePM](https://github.com/kieranjwood/deepm/tree/94aa148295d9147f6533f877256b663b918ed2e6) | `94aa148295d9147f6533f877256b663b918ed2e6` | Features, lagged cross-asset context, robust loss, actual configurations and cost accounting |

The actual licenses were downloaded and identify MIT permission for these code
repositories. Full original paper bodies were not obtained. Code behavior may
also differ from the final paper; the inspected snapshot is the evidence here.

### Daily slow/fast baseline

The first author's baseline mixes past 21-day and 252-day price-return signs:

`x[t] = w*sign(P[t]/P[t−21]−1) + (1−w)*sign(P[t]/P[t−252]−1)`.

Its EWM volatility estimator uses daily returns, span 60. The next-day payoff is
scaled with `0.15/(sqrt(252)*sigma[t])`. A future-return shift is a target/payoff
construction; it is never an entry-time feature. The annualization and calendar
are daily traditional futures conventions.

MACD pairs `(8,24)`, `(16,48)` and `(32,96)` describe decay timescales with
`alpha=1/time_scale`. Substituting `ewm(span=time_scale)` changes the rule. The
price-based MACD is normalized by rolling 63-day price standard deviation and
then by rolling 252-day standard deviation of that ratio.

This is evidence for an explicitly defined daily method. It is not evidence that
the same period numbers in hours are profitable, or that an ATR stop reproduces
the author's position policy.

### Rolling changepoint context

The original code fits a stationary Matérn 3/2 Gaussian process and a bounded
one-change pair of Matérn processes on the completed trailing-return window.
The comparison produces:

`severity = sigmoid(NLML_stationary − NLML_change)`

`relative_change_age = (latest_index − estimated_change)/(latest_index − window_start)`.

The window contains only information available through its ending observation.
The score measures fitted model support. It is not a calibrated probability,
p-value, news classification or sentiment feed. The author's network learns to
combine these features with trend/return features; the inspected code provides
no universal deterministic reversal entry threshold.

### Legacy costs and chronological evaluation

The inspected legacy neural-network training objective is gross Sharpe. Its
separate backtest subtracts declared basis-point turnover costs:

`cost[t] = c*abs(0.15*x[t]/(sqrt(252)*sigma[t]) − previous_scaled_exposure)`.

Configured cost scenarios range from 0.5 to 3 basis points. Real-feature scalers
fit on training, followed by validation selection and later-year test windows.
The example's chronological split is per asset; different asset histories can
produce different calendar split boundaries, so this alone does not establish
a synchronized global chronological validation period.

Several implementation limits require attention in any adaptation:

- Indicator warmups backward-fill from later values; remove these fills or
  discard the entire affected warmup before allowing a decision.
- The cost function's initial `diff` is filled with zero, omitting first-entry
  turnover cost. An explicit initial/terminal position policy is needed.
- Some normalized diagnostic returns use realized test-window volatility;
  this cannot be deployed as a prospective leverage setting.
- The README example's universe uses availability through December 2021;
  a historical point-in-time universe is not verified by that example.
- The default annual-window loop stops before its configured final year because
  of its range bounds. Configured dates alone do not verify included dates.
- Daily overnight continuous futures are a different strategy once a prop
  product requires flattening intraday. Neither integer contracts, market depth,
  actual rolls nor prop payout survival follow from the source baseline.

### Current DeePM method

The actually retrieved 2026 author configuration uses normalized daily/monthly/
quarterly/annual returns and 21/252-day log-price z-scores. Daily volatility is
EWM span 63 with a full minimum period and no backward fill in the inspected
new feature builder. Cross-asset hidden states are delayed one completed step
in the default architecture; optional close-order variants are separately
configured. Event-time alignment remains necessary when adapting to other data.

The default joint loss maximizes pooled portfolio Sharpe plus
`0.1*SoftMin_beta(window Sharpes)`, with `beta=5` and
`SoftMin_beta = −log(sum(exp(−beta*S)))/beta` when centering is disabled.
This encourages the model to consider weaker historical windows. It does not
guarantee future stability or a minimum monthly return.

The training cost penalty charges changes in volatility-scaled exposure. The
default weight is half the author-estimated half-spread; the separate backtest
applies the configured full estimate. Its expanding test starts are 2010, 2015
and 2020, training begins in 1990, and the configured panel ends in 2025.
Training and backtest configs have different seed-retention counts; actual
available checkpoints determine execution, rather than a label in the README.

The licensed panel of fifty daily continuous futures is absent from the repository.
There has been no empirical reproduction here. Its estimated half-spread costs,
including 0.25 basis points for ES/NQ, are not verified micro-contract prop fees.
The inspected backtest omits initial entry cost, consumes a normalized target
clipped to ±20 and rescales diagnostic returns using whole-test realized volatility
to a 10% annual target. Our actual account P&L must preserve raw execution losses,
charge all costs and use prospective sizing.

## What the published author summaries establish

[AQR Time Series Momentum](https://www.aqr.com/Insights/Research/Journal-Article/Time-Series-Momentum)
describes prior 12-month excess returns, 58 traditional futures/forward contracts
and more than 25 years of data. Only its author summary was read in this pass;
no hourly adaptation or current crypto result is established.

[AQR Trading Costs of Asset Pricing Anomalies](https://www.aqr.com/Insights/Research/Working-Paper/Trading-Costs-of-Asset-Pricing-Anomalies)
summarizes nearly $1 trillion of actual institutional equity trading across
nineteen developed markets in 1998–2011. The described reversal portfolios fail
their costs/capacity test while several slower styles survive. That is a specific
equity result, not a universal claim about reversal or a retail cost calibration.

[AQR Dynamic Trading With Predictable Returns and Transactions Costs](https://www.aqr.com/Insights/Research/Journal-Article/Dynamic-Trading-With-Predictable-Returns-and-Transactions-Costs)
supports considering signal strength, decay, covariance and transaction costs
together. Its complete optimal-policy derivation was not read; no exact policy
is claimed from the summary alone.

## Original PDFs still needing verification

Native proxy requests for the actual Concretum
[equity ORB](https://concretumgroup.com/wp-content/uploads/2026/02/A-Profitable-Day-Trading-Strategy-For-The-U.S.-Equity-Market.pdf)
and [SPY momentum](https://concretumgroup.com/wp-content/uploads/2026/02/Beat-the-Market.pdf)
PDFs failed. The original author-page retrieval established those links, rather
than their precise trading formulas, costs, sample or out-of-sample methodology.
Those must be verified before calling an implementation a paper reproduction.

The author papers [2105.13727](https://arxiv.org/pdf/2105.13727.pdf),
[2112.08534](https://arxiv.org/pdf/2112.08534.pdf) and
[2601.05975](https://arxiv.org/pdf/2601.05975) also failed native retrieval.
The possible Ranaldo FX lead,
[SNB 2007/03](https://www.snb.ch/en/publications/research/working-papers/2007/working_paper_2007_03),
remains an unverified bibliographic lead: its native request failed, and its
actual title and PDF still require confirmation. The earlier SNB 2010/10
misidentification remains rejected.

## Applying this evidence to the new studies

Original daily periods and exact normalization/cost caveats were sent to the
crypto trend researcher before its freeze. Crypto hourly periods, channel rules,
ATR stops, contexts and risk sizes are independently defined adaptations owned
by that experiment's protocol. They must count as inspected hypotheses.
The source audit neither freezes that grid nor selects its winner.

Use only completed features, retain full warmup, charge initial/terminal costs,
use raw realized execution returns and ex-ante position sizing, and distinguish
nominal capital from the usable prop loss buffer. Historical source claims and
paper risk-adjusted improvements cannot establish our monthly target or enable
live orders or Telegram alerts.
