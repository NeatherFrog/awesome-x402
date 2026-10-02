# Adaptive low-turnover spot protocol

The hourly208-variant pool failed its fixed2025 validation screen. In particular,
fees and turnover removed apparent gains. This **new** protocol tests economically
different portfolio allocation hypotheses. The original grid, code, locks and
results are preserved. This is an adaptive exploratory follow-up, not a fresh
unseen2024/2025 experiment.2026 prices/calendar also overlap other existing
studies; an untouched final within this protocol cannot reset global research
knowledge.

## Fixed pool and data

64 variants in four families,16 each:

| Family | Fixed dimensions | Economic premise |
| --- | --- | --- |
| Relative rotation |1/3calendar months; weekly/monthly;4h/daily;8/12% vol target| Allocate to the strongest positive-return asset; cash when neither rises |
| Inverse-volatility trend | same dimensions | Risk-balance eligible upward assets, rather than frequent stopped single-market entries |
| Channel portfolio |20/60day channel; weekly/monthly;4h/daily;8/12% target | Persistent range-breakout state, deactivated below prior half-length channel lows |
| BTC regime rotation |1/3calendar months; weekly/monthly;4h/daily;8/12% target | Relative rotation only when BTC exceeds its60day mean and has positive20day return |

The data are the exact original official Binance BTCUSDT/ETHUSDT hourly spot CSVs.
Source hashes, download receipts and canonical price fingerprints were already
verified in the predecessor. Each UTC aggregate requires all underlying hours;
incomplete groups or gaps fail. Candle close information is available at the next
aggregate opening, never earlier.

Time-series momentum is a documented research concept (Moskowitz,Ooi,Pedersen,
2012). That paper uses monthly futures momentum horizons including1/3/12months.
This spot implementation is our distinct adaptation. It calculates **calendar
months**, not1/3/12hours: shift the observation's UTC close timestamp backward,
clamp month-end dates, and look up the most recent available complete close.
12month training requires unavailable2023 warmup and is excluded before outcomes.

Train2024, validate2025, final January–September2026. February–April, May–August
and September–December2024 folds are unchanged. All windows start cash.

## Allocation mathematics and causality

For log return `r[t]=log(C[t]/C[t-1])`, estimate30calendar-day sample-population
standard deviation from prior closed bars and annualize by
`sqrt(365*24/resolution_hours)`. The volatility estimate is a model, not a future
risk guarantee. Flat/no-variance or insufficient-warmup observations do not trade.

Within eligible assets, inverse volatility defines proportions:

`u[i]=(1/sigma[i])/sum(1/sigma[j])`.

The realized two-asset covariance estimate yields portfolio volatility:

`sigma_p=sqrt(u1^2*sigma1^2+u2^2*sigma2^2+2*u1*u2*rho*sigma1*sigma2)`.

Final risky weights are `w[i]=u[i]*min(1,target_vol/sigma_p)`; remaining wealth is
cash. Rotation has only one eligible asset and therefore uses its volatility.
The30day correlation is estimated causally from the same prior returns. BTC
regime conditions and momentum eligibility are previous-close observations.

Weekly rebalances occur Monday00UTC; monthly on the first day00UTC. Decisions
come from the fully closed prior candle, including signals whose close timestamp
equals this next open. Sell reductions precede buys; fees and adverse execution
reduce available cash. All buys are proportionally cash-capped after sells. The
strategy never borrows or takes negative asset weights.

Model:10bps fees per side,2bps adverse slippage per side,1bp full spread, modeled
0.000001 quantity increment, zero funding/borrow/cash interest. Actual venue
tariffs and historical filters are not certified. Original archives carry
CC BY-NC-SA; this is personal non-production research, not commercial data rights.

These allocation hypotheses do not use individual ATR stop orders. Portfolio
volatility targets do not cap gap losses. Conservative summed asset-candle lows
measure intrabar account drawdown; lows may not be simultaneous. Final-bar new
rebalance is disabled, and remaining positions are explicitly liquidated at the
sample boundary close with correct close timestamp.

## Selection and evidence levels

The64 variants are preregistered before their outcomes.272 sequential variants
in this venue pool now include the failed208 predecessor; parameter variants are
not independent strategies. Training candidates require positive net and
doubled-friction returns, worst drawdown<=15%, four completed position episodes
and two positive fixed training folds. Pick one per family by return divided by
`max(drawdown,0.25%)`, ties by ID. Only this fixed shortlist is evaluated on2025.

Validation candidates require positive net and doubled-friction returns, worst
drawdown<=12%, two completed position episodes and the same conditional
Holm-adjusted seven-day block-signflip diagnostic<=0.05. Exactly one survivor is
locked by the same score before2026 performance. No survivor means final remains
unopened. No replacement is allowed after final failure.

The small **research-screen** episode thresholds allow measuring long-horizon
rules; they do not lower qualification standards. Strict final qualification
still requires50 completed position episodes,180 daily observations, six months,
positive net and doubled-friction return,99% circular-seven-day-block mean-return
CI lower bound>0, both fixed halves positive, no positive month exceeding half of
positive-month total, drawdown<=10% and daily opening-to-intrabar loss<=2.5%.
Frequent rebalances/partial fills are not counted as independent completed trades.
Even a profitable few-episode result fails activity evidence and stable-profit
qualification. Adaptive inspected history further requires future paper evidence.

All64 training conditional p-values are retained and Holm-adjusted. Signflip
requires independent symmetric block signs, not established for financial returns.
The99% interval is approximate and conditional, not a probability of future
profitability. Positive mean-return evidence does not establish benchmark alpha.

Outputs include fees, adverse-fill drag, turnover, actual holding exposure,
rebalance fills, completed episode cash flows, exact conditional assumptions,
training/validation/final benchmarks where opened, and descriptive beta/intercept.
Cash-flow conservation is independently tested. Prior study artifacts must stay
unchanged, and all new producers and selections are immutable and hashed.

```sh
python -m unittest tests.test_low_turnover
python scripts/research_low_turnover.py --freeze
python scripts/research_low_turnover.py --run
```

No Telegram messages, actual orders, challenges or payouts are authorized or
claimed by this research protocol. A concrete qualified result precedes alert
development; rejected research stays in the ledger, not the user's signal feed.
