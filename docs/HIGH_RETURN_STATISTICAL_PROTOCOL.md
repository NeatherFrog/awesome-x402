# Prespecified high-return research screen

The requested objective is an **8% geometric calendar-month equivalent net
account return**. It is not an 8% return every month, a guaranteed return, a
withdrawal amount or a prop payout. Every strategy, size, asset, condition and
revised idea counts in the cumulative experiment history. This new research is
adaptive: general 2024–2026 prices and prior strategy outcomes have already been
inspected. There is no globally blind qualification claim.

## Data and arithmetic

`propdesk/target_evaluation.py` accepts one complete calendar date per net total
account daily return, a matching doubled-cost return series, completed trading
episodes and adverse/peak daily **dollar equity** envelopes. Include verified
flat nontrading calendar days. Missing dates, mismatched dates/series, nonfinite
observations and insolvent account returns fail rather than being omitted.

For `r[t] = E[t]/E[t-1]-1`, compound total growth is
`G = exp(sum(log(1+r[t])))`. Actual elapsed calendar months are
`M = sum(1 / days_in_calendar_month[t])`. The objective statistic is
`G^(1/M)-1`. Thus a complete 12-month period contains exactly 12 months despite
February or leap years. Arithmetic mean monthly returns cannot replace this
statistic. Partial months contribute to elapsed growth/time but never count as
full months in the consistency requirements. Worst full-month returns and all
partial-month returns are reported.

All calculations use the real initial TOTAL account denominator. Partial
allocation, isolated derivative collateral and idle cash cannot be relabeled as
extra capital, income or independent accounts. Count completed paired/session
position episodes, not individual leg fills, partial exits, funding settlements
or rebalances. Sample-boundary forced closures must remain explicitly labeled
by the engine.

## Selection and period requirements

Freeze all candidate parameters, risk sizes, costs, market data identities,
calendar conventions, trial counts, selection rules and split boundaries before
each new run. Risk sizes such as 0.25%, 0.5% and 1% may be compared in TRAIN only
when preregistered; each is a distinct inspected configuration. Never scale up
after final results or replace a failed primary with a runner-up using the same
final period.

TRAIN requires positive net total return, positive doubled-cost geometric
monthly return, at least 30 completed episodes, at least 60 full calendar days,
account adverse drawdown at most 10%, and daily adverse reference loss at most
5% of INITIAL account capital. Selection among passing TRAIN configurations uses
net total return divided by `max(adverse_drawdown, .0025)`, with a frozen tie
rule. The 8% objective is not a TRAIN selection gate, allowing a three-month
futures training window without weakening later requirements.

Both validation and final independently require all TRAIN risk/return gates,
at least 60 completed episodes and:

- At least six complete calendar months.
- Geometric calendar-month equivalent net return at least 8%.
- Positive lower 99% interval for mean daily net account return.
- Positive median full calendar-month return.
- At least two thirds of complete calendar months positive.
- Both chronological daily-return halves have positive compounded return.

All conditions must hold; positive total return alone is insufficient. A higher
episode threshold is allowed only if declared before outcomes. Floating-point
comparison at the exact 8% boundary uses a numerical tolerance of approximately
1e-12 relative, not a financial relaxation of the target.

## Risk, uncertainty and prop limitations

Daily peak/worst envelopes provide a conservative risk bound: the evaluator
assumes a day's largest peak precedes its worst mark because their true order
is unavailable. Missing adverse marks cannot qualify based on daily closes
alone. Daily reference loss is previous calendar-close equity minus the day's
worst modeled equity, divided by INITIAL total capital. The timezone is recorded.

This is a **research reference screen**, not actual FTMO daily-loss certification.
FTMO uses its contract's Prague reset and balance/floating-PnL accounting;
Topstep uses its own stage-dependent Chicago-time trailing limits. Overnight
positions, fees, drawdown floors, stage resets and payouts need separate exact
contract replay with authoritative marks. A 5% reference threshold cannot
replace Topstep's tighter limits or infer that a $100k challenge has $100k
spendable cash. Nominal trading profit is distinct from eligible withdrawal,
profit split, payout caps and challenge/subscription expenses.

Use the unchanged `research_stats.bootstrap_mean_ci`: circular seven-day blocks,
5,000 resamples, 99% percentile interval and recorded deterministic seed. It
estimates mean daily return under approximate dependence/stationarity assumptions.
Trade count is not independent sample size; the interval does not erase adaptive
selection or nonstationarity. Holm adjustment of registered train/shortlist
diagnostics can be reported, conditional on their null assumptions. Descriptive
correlations use TRAIN only and causally available features. No formula proves
stable future profit.

All qualifying outcomes remain provisional historical candidates until genuinely
future forward data, actual account fees/specifications, verified execution and
exact firm-rule replay support deployment. This evaluator never enables live
orders or Telegram, and rejected candidates produce no trading alerts.
