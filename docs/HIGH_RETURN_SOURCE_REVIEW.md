# Source review for the 8% monthly prop-account objective

Current public terms were retrieved on **2 October 2026, UTC**. This is a new,
separate audit; the older source registries remain unchanged. Retrieval receipts,
HTTP outcomes, hashes, causal hypotheses and product distinctions are in
[high-return-source-review.json](high-return-source-review.json).

**No strategy meeting 8% monthly has been established by this review.** A source
supports a hypothesis or a contract constraint; it does not transfer its returns
to our code, prices, account or execution. Original-paper review remains partial.
Unavailable papers are identified below, without pretending their full text was
read. The actual historical experiments belong to the separately frozen target
protocol and experiment registry.

## What the objective actually measures

An 8% monthly return compounds to `1.08^12 − 1 = 151.817%` annually. The simple,
noncompounded sum is 96%. Neither is evidence that this rate is attainable.

With each trade risking 0.25% of the nominal account, the arithmetic hurdle is
**32 net R per month**. At 20, 40 or 60 trades, the respective required averages
are 1.6, 0.8 or 0.533 net R per trade. Fees, spreads, slips, gaps and correlated
losses make risk and realized R differ from a neat stop/target illustration.

Prop labels are not deployable cash. Topstep 100K initially permits only a $3,000
loss allowance: an $8,000 nominal monthly target is 266.7% of that allowance.
An XFA starts with a **zero** cash-like balance, not $100,000. Trading P&L divided
by nominal buying power, return on the usable loss buffer and the trader's net
cash payout must be reported separately. Compounding nominal XFA returns as if
the trader deposited $100,000 is misleading.

At FTMO 2-Step's base 80% reward split, 8% trading profit corresponds to 6.4% of
nominal capital in the trader's gross reward, before other costs. To target 8%
cash at that split requires at least 10% trading profit before those costs.
Topstep additionally caps individual XFA withdrawal requests and leaves a
retained risk buffer; trading profit is not immediately withdrawable cash.

A positive lower confidence bound for historical mean return tests profitability
under its assumptions. It does **not** statistically establish an 8% monthly
mean. That stronger assertion would need an appropriately selected, dependence-
aware bound above 8%, adequate later observations and pathwise account survival.
Mean, median, bad months, month-to-month consistency and payout outcomes remain
distinct measurements. Increasing position size to reach the headline without
respecting the loss floor does not satisfy the objective.

## Refreshed official product constraints

### FTMO CFD 2-Step versus 1-Step

[Objectives](https://ftmo.com/en/trading-objectives/) and
[comparison](https://ftmo.com/en/comparison-table/) confirm separate products.

| Constraint | 2-Step | 1-Step |
| --- | --- | --- |
| Evaluation targets | 10%, then 5% | 10% |
| Daily allowance from initial capital | 5% | 3% |
| Daily reference | Midnight balance, 00:00 CE(S)T | Same |
| Total floor | Static 90% of initial capital | Highest previous midnight balance or initial capital, minus 10% of initial capital |
| Evaluation opening days | At least four in each phase | No corresponding fixed minimum in comparison |
| Best Day | No corresponding rule in comparison | Best closed-profit day / total net profit of profitable days ≤50% |
| Swing | Available at initial 2-Step selection | Unavailable |

Equity includes floating P&L, swaps and commissions. A constant UTC reset cannot
replace Prague daylight-saving time. The 1-Step floor never decreases; the
funded withdrawal/new-account reset is a separate event. A static 2-Step backtest
must not be advertised as compliance with 1-Step trailing rules.

[News rules](https://ftmo.com/en/faq/can-i-trade-news/) distinguish evaluation,
funded Standard and Swing. Funded Standard prohibits entry/exit, including
triggered SL/TP, in the selected event's affected instrument from two minutes
before through two minutes after. Swing and evaluation have specified exemptions.
[Holding rules](https://ftmo.com/en/faq/do-i-have-to-close-my-positions-overnight-or-before-the-weekend/)
also differ. General event-gap, overexposure and manipulation restrictions still
apply; an exemption is not a free event-gambling strategy.

[Algorithm policy](https://ftmo.com/en/faq/which-instruments-can-i-trade-and-what-strategies-am-i-allowed-to-use/)
allows legitimate, replicable EAs. The source separately discusses 200 concurrent
orders, 2,000 daily positions and excessive server messages. The
[forbidden-practices page](https://ftmo.com/en/forbidden-trading-practices/)
describes abusive slow-feed/error exploitation, manipulative opposite positions
across accounts and artificial profit spreading. Its single-account exception
in the opposite-position clause does not exempt a pairs strategy from all other
risk and contract requirements.

[Rewards](https://ftmo.com/en/faq/how-do-i-withdraw-my-profits/) confirm 80% base
for 2-Step, 90% under additional conditions, and 90% for 1-Step. Requests require
closed positions and pending orders and are described as available on the 14th
or a following day after the first trade. Exact inclusive-calendar versus elapsed
24-hour interpretation is not established. The $20 bank/$50 crypto threshold is
described as minimum **closed profit**, not guaranteed net money received. A
conservative modeled time rule must be labeled as an assumption.

The [general specifications](https://ftmo.com/en/faq/what-are-the-account-specifications/)
advertise maximum Swing leverage 1:30. Independently inspected current public
symbol metadata in [prop-data-audit.json](prop-data-audit.json) is more specific:
US100.cash and US500.cash have contract size 1 and Swing leverage 15; EUR/USD has
100,000 per contract and Swing leverage 30; XAU/USD has 100 per contract and Swing
leverage 15. This is current instrument metadata, not historical executable
bid/ask prices or confirmation of every commission's per-side meaning.

### Topstep Trading Combine, XFA and API

For 100K, the current [MLL](https://help.topstep.com/en/articles/8284204-what-is-the-maximum-loss-limit)
allowance is $3,000. The Combine begins at $100,000 with $97,000 floor; the floor
trails end-of-day balance upward and locks at starting balance. It is monitored
intraday including unrealized P&L; touching it triggers liquidation. Exact
backend update time is not established merely by the words end-of-day.

[Combine](https://help.topstep.com/en/articles/8284197-trading-combine-parameters)
requires $6,000 for 100K with a 55% best-day threshold. The optional
[daily limit](https://help.topstep.com/en/articles/10490293-daily-loss-limit-in-the-trading-combine-and-express-funded-account)
is $2,000 for 100K: its trigger creates a session lockout, rather than an MLL
breach. The funded account must be modeled as a new stage, not continued
evaluation equity.

The current 100K Combine position ceiling is **10 minis or 100 micros in total
per account**, with a 10:1 ratio, including combinations. It is not 100 micros
for each instrument. XFA follows a separate
[balance-dependent scaling plan](https://help.topstep.com/en/articles/8284223-what-is-the-scaling-plan):
additional buying power becomes available only in the next session. Its numeric
balance-tier chart is an embedded image that could not be retrieved locally, so
this audit does not certify the initial 100K XFA cap. The example for a 50K
account must not be substituted for 100K. Special weighting for SIL/MBT/MET also
prevents treating every micro product identically.

[XFA](https://help.topstep.com/en/articles/8284215-express-funded-account-parameters)
starts at $0 with initial floor −$3,000 for 100K; the floor eventually locks at
$0 and becomes $0 after the first payout regardless of its previous value.
[Payout policy](https://help.topstep.com/en/articles/8284233-topstep-payout-policy)
requires either five winning days of at least $150 net for Standard or three
traded days plus 40% consistency for Consistency. Requests are limited to 50% of
balance, capped at $3,000/$4,000 respectively for 100K, with 90/10 split. The
published $125 minimum does not explicitly resolve gross versus after-split
interpretation; that modeling choice remains flagged.

The [consistency source](https://help.topstep.com/en/articles/8284208-consistency-at-topstep)
explicitly excludes retained balance from the next payout window's denominator.
Only new-window net trading profit counts; losing days remain in that net
denominator. Request-day trades do not count toward the next window. Payout days
lock at 4 PM CT; the separate history example uses 3:10 PM CT. These do not by
themselves certify the exact MLL settlement clock.

Current processing fees include $30 for ACH or Wire/SWIFT. The policy's $500
request example subtracts $50 profit split and $30 processing to deliver $420.
Other method/region eligibility and intermediary charges differ. A strategy's
reward accounting must not silently equate gross request with received cash.

[Trading hours](https://help.topstep.com/en/articles/8284206-when-and-what-products-can-i-trade)
require flat by 3:10 PM Chicago time; risk flattening starts at 3:08 PM, with
reopening at 5 PM. Earlier instrument closes override this schedule. No swing
or spot FX is offered. Published [fees](https://help.topstep.com/en/articles/8284213-topstepx-commissions-and-fees)
are $1.22 roundtrip for MES/MNQ and $3.78 for ES/NQ, before spread/slippage.
The MES/MNQ roundtrip fee implies $0.61 per side. A backtest using $1.25 per side
is a declared conservative fee assumption, rather than the current published
base commission. Historical fee schedules and variable slippage still matter.
[Pricing](https://help.topstep.com/en/articles/14289835-topstep-pricing-and-payment-questions)
currently lists 100K Standard $99/month plus $149 XFA activation; the alternative
No Activation Fee path is $149/month. Promotions are not universal assumptions.

[API policy](https://help.topstep.com/en/articles/11187768-topstepx-api-access)
permits eligible SIM bots and Practice-account testing, not LFA API execution.
There is no separate sandbox. All order transmission, modification, cancellation,
triggering and relay must originate on the user's personal device; a private
server may research, store and observe. A cloud research process must not become
the order executor. [Cross-account hedging](https://help.topstep.com/en/articles/13747047-understanding-hedging)
in the same or correlated instruments remains prohibited, including accidental
brief overlaps. Enforcement warnings do not make the practice an allowed edge.

## Distinct causal hypotheses worth testing

These are **our proposals**, not claimed reproductions of inaccessible papers.
Numerical thresholds, contracts, periods, fees and selection rules belong in the
new frozen protocol before outcomes are inspected.

| Hypothesis | Causal construction | Critical executable-data limit |
| --- | --- | --- |
| RTH opening-range breakout | Freeze high/low of completed 09:30–09:45 New York bars; enter after a later completed breakout at the next available open | Actual futures contract/roll, price grid, integer quantity, spread and margin; not a three-minute rule reconstructed from hourly data |
| Session VWAP rejection | Use session VWAP from already executed trades; define distance and residual scale from past data; enter only after completed rejection | Tick VWAP differs from typical-price OHLC-volume proxy; CFD tick volume is not exchange traded volume |
| Early-to-late session momentum | Use an explicitly defined first-session return to choose a fixed late-session position; exit before the applicable account deadline | Original paper's exact gap/open/half-hour construction still needs verification; full-day return and later extrema are unavailable at entry |
| FX time-of-day reversal | Standardize completed past returns by historical local-time slot volatility; freeze a session-specific rule using training only | Need bid/ask, DST, broker rollover, swaps and news; no verified universal currency direction is claimed |
| Same-account relative value | Fit a spread and stationarity diagnostics on the formation period; trade a declared cost-exceeding deviation on synchronized next quotes | Two-leg fills, swaps/borrow, margin and stale quotes; no cross-account prop hedge or assumed atomic fill |

Exact VWAP is `sum(trade_price * trade_size) / sum(trade_size)` over the current
session up to the decision. The bar approximation uses `(H+L+C)/3 * volume` and
must be named as an approximation. A full-session average is unavailable during
that session.

A candidate spread is `s = log(Pa) − alpha − beta*log(Pb)`, fitted solely on
training. A large price correlation does not establish stationarity. In the
specific AR(1) approximation `s[t]−mu = phi*(s[t−1]−mu)+error`, only `0<phi<1`
supports the simple half-life `−log(2)/log(phi)`. Cointegration tests need the
correct residual critical values and assumptions. Re-estimation, pair selection,
lags, regime conditions and stop/target choices all count as additional trials.

## Actually retrieved research and rejected evidence

The author-linked [Al-Aradi pairs repository](https://github.com/alialaradi/PairsTrading/tree/2b479b9b5c910ff58692b4e7a0894983477e011f)
provides a theoretical OU spread/common Brownian factor, temporary price impact,
absolute and relative inventory penalties, and terminal liquidation. Its linked
original PDF was inaccessible locally. Its code is entirely simulated, not an
empirical track record. The simulator also draws unit-normal increments without
`sqrt(dt)` in diffusion updates, so changing its time step changes effective
variance. We do not copy its synthetic P&L as evidence.

The actual document titled *Profitable Algorithmic Trading Strategies in
Mean-Reverting Markets*, Vittoria Volta, was retrieved from a pinned unaffiliated
GitHub mirror. The body uses a synthetic sinusoid plus Gaussian noise, no
transaction costs and all-in long-only allocation. It is explicitly **rejected
as empirical market evidence**. The title alone would have produced a false
profitability claim.

AQR's actually retrieved author summaries
[Which Trend Is Your Friend?](https://www.aqr.com/Insights/Research/Journal-Article/Which-Trend-Is-Your-Friend)
and [Value and Momentum Everywhere](https://www.aqr.com/Insights/Research/Journal-Article/Value-and-Momentum-Everywhere)
support filter-family overlap and correlated factor premia, respectively. Their
full original papers were not retrieved in this audit. Multiple trend filters
should not be counted as independent economic discoveries, and traditional
monthly factor evidence does not authenticate hourly prop-account returns.

Additional actually retrieved AQR author summaries give three useful boundaries.
[Time Series Momentum](https://www.aqr.com/Insights/Research/Journal-Article/Time-Series-Momentum)
describes own prior **12-month excess return**, 58 futures/forward contracts and
more than 25 years of data. Its horizon cannot be relabeled as twelve hours.
[Trading Costs of Asset Pricing Anomalies](https://www.aqr.com/Insights/Research/Working-Paper/Trading-Costs-of-Asset-Pricing-Anomalies)
summarizes nearly $1 trillion of institutional equity trades across 19 markets
in 1998–2011: the described short-term reversal portfolios fail their cost/capacity
test while size/value/momentum survive. That is a specific equity result, not a
universal ban on reversal or a retail cost model.
[Dynamic Trading With Predictable Returns and Transactions Costs](https://www.aqr.com/Insights/Research/Journal-Article/Dynamic-Trading-With-Predictable-Returns-and-Transactions-Costs)
supports accounting for signal decay and covariance when trading forecasts.
Only these published summaries were read; full original policy formulas and
empirical tables were not verified here.

### Original author code for trend, reversals and regime context

Actual primary method evidence is available from Wood and coauthors:
[Slow Momentum with Fast Reversion](https://github.com/kieranjwood/slow-momentum-fast-reversion/tree/b22006066c274cd5953446baf24b99a2726068e4)
and [Momentum Transformer](https://github.com/kieranjwood/trading-momentum-transformer/tree/e0352cb0bdbf8045accb1bf1a5705ae0cb9ea624).
The fetched original code and MIT licenses are pinned and hashed individually.
The original PDFs ([2021 changepoint preprint](https://arxiv.org/pdf/2105.13727.pdf),
[2021 transformer preprint](https://arxiv.org/pdf/2112.08534.pdf)) remain blocked
locally. Code-method verification is not a claim to have read those papers or
reproduced their returns.

Their daily slow/fast reference position is
`w*sign(P[t]/P[t−21]−1) + (1−w)*sign(P[t]/P[t−252]−1)`.
Next-day returns are normalized by past EWM volatility, span 60, with 15% annual
volatility target and 252 trading days. MACD decay pairs are `(8,24)`, `(16,48)`
and `(32,96)`, using `alpha=1/time_scale`: those numbers are not literal pandas
EMA spans. Signals are normalized first by 63-day price standard deviation and
then by 252-day standard deviation of the resulting ratio.

The original changepoint implementation fits one stationary Matérn 3/2 Gaussian
process and a bounded one-change pair of Matérn processes over the completed
trailing return window. Its score is
`sigmoid(NLML_stationary − NLML_change)` and its relative change age is
`(latest_index − estimated_change)/(latest_index − window_start)`.
This is a model-fit score, not a calibrated news probability, sentiment measure
or statistical p-value. The network learns exposure from these features; no
universal deterministic reversal threshold is specified by the inspected code.

The legacy network trains on gross Sharpe. Its separate cost calculation charges
`c*abs(0.15*x[t]/(sqrt(252)*sigma[t]) − previous_scaled_exposure)`, with declared
0.5–3 basis-point scenarios. The real-feature scaler fits on TRAIN; validation
selection precedes later year test windows. The example's per-asset chronological
90/10 split is not automatically a synchronized global calendar split.

Important implementation limits remain: backward-filled indicator warmups must
be removed or fully discarded; the cost function omits the first entry cost;
some diagnostic volatility normalization uses realized test returns. The README
example chooses its 100 futures partly by availability through December 2021,
rather than documenting a point-in-time historical universe. The current example
loop also stops one year before its configured end because of its range bounds.
No source-code metric is copied as a deployable trading return.

The newer, actually retrieved original MIT
[DeePM implementation](https://github.com/kieranjwood/deepm/tree/94aa148295d9147f6533f877256b663b918ed2e6)
provides another precise method: causal past-return/price-z-score inputs,
one-step delayed cross-asset attention and a joint objective of pooled portfolio
Sharpe plus `0.1*SoftMin_beta(window Sharpes)`, default `beta=5`.
Here `SoftMin_beta = −log(sum(exp(−beta*S)))/beta` under the inspected default.
Training subtracts turnover costs, using half the estimated asset half-spread in
the default configuration. Its expanding test starts are 2010, 2015 and 2020.
The [original 2026 preprint](https://arxiv.org/pdf/2601.05975) has not been read.

This method is useful as a research direction, with substantial reproduction
limits. The licensed 1990–2025 panel of 50 continuous futures is absent. The
configured transaction costs are author half-spread estimates, including 0.25
basis points for ES/NQ, rather than actual micro-contract prop commissions.
The inspected backtest again omits initial turnover cost, clips its normalized
next-day target to ±20, and rescales diagnostic returns using whole-test realized
volatility to a 10% annual target. Our realized execution P&L must retain actual
losses, charge entry/exit costs and use prospective sizing. The source's daily
overnight exposure also changes when Topstep requires intraday flattening.

These methods support a **new, explicitly adapted** causal trend/regime hypothesis.
Hourly periods, rolling-channel rules, ATR stops, deterministic context thresholds,
crypto annualization and account sizing are our choices; every choice adds a
registered trial. No published Sharpe improvement establishes our 8% target.

The additional public retrieval ran successfully as
[GitHub Actions run 36996838955](https://github.com/NeatherFrog/awesome-x402/actions/runs/36996838955).
The separately hashed receipt artifact is `.local/pattern-source-receipts.json`;
its producer and receipt commits, body hashes and final URLs are bound into this
audit's JSON. Full copyrighted bodies remained in the temporary CI workspace.
At most 78 quoted words from each successful source are locally available. A
receipt verifies retrieval; a handful of excerpts cannot verify the full study.

The publisher-hosted [Gatev pairs PDF](https://www.nber.org/system/files/working_papers/w7032/w7032.pdf)
was actually fetched: 35 pages, 163,124 bytes, SHA-256
`30a54a682259681e163f79120393281a4f158f9cd97c33ca032469f1924f6cf4`.
One introductory excerpt contains the authors' positive-after-costs claim.
The local reviewer has not read the complete paper; its exact pairing method,
formation and trading windows, dataset, cost model and numerical statistics
are not verified by those excerpts. A headline claim supplies no calibrated
expectation for current futures, FX, prop drawdown or an 8% monthly goal.

The actual Concretum author webpages for
[ORB](https://concretumgroup.com/a-profitable-day-trading-strategy-for-the-u-s-equity-market/)
and [intraday momentum](https://concretumgroup.com/beat-the-market-an-effective-intraday-momentum-strategy-for-sp500-etf-spy/)
were fetched remotely and their titles verified. The pages expose real original
PDF links: [equity ORB](https://concretumgroup.com/wp-content/uploads/2026/02/A-Profitable-Day-Trading-Strategy-For-The-U.S.-Equity-Market.pdf)
and [SPY intraday momentum](https://concretumgroup.com/wp-content/uploads/2026/02/Beat-the-Market.pdf).
The full PDFs remain inaccessible locally. Exact noise-band formulas, instrument
selection, stops, sizing, commissions and results must be verified from the
originals before calling any proposed rule a reproduction. SSRN retrieval of
Gao and the two author studies failed even in CI.

The guessed SNB FX link successfully redirected to a working paper about
reciprocity in labor relations. It is **rejected as an FX source**. Its HTTP 200
status would otherwise have concealed a material relevance error. CME contract
specification pages also remained inaccessible; no claim of fresh specification
verification is made here.

## What remains before a useful trading result

Freeze the new goal and candidate definitions before loading outcomes; obtain
market-specific executable histories; retain all failed experiments internally;
select on training/validation without changing the final winner after exposure.
Evaluate marked equity throughout each actual product stage, risk floors,
integer contracts, calendar, fees, payout cycles and remaining capital buffer.
If one candidate survives, observe genuinely subsequent data before enabling
alerts or trading. A failed first search does not exhaust the research objective;
an additional search is recorded as a new inspected hypothesis, not a fresh
unseen version of the same history.
