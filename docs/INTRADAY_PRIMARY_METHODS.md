# Original intraday methods and a separately testable crypto adaptation

The complete extracted text of the original Concretum noise-area paper (43
pages) and individual-stock ORB paper (26 pages) was actually read, including
their FAQs, tables and references. Figure images were not digitized. These
are now original-paper method reviews; their empirical trading results have
not been reproduced with the authors' vendor data or broker executions.

The original files were acquired from the authors' HTTPS site in authorized
GitHub Actions run `37002836679`, producer commit
`4f486d93a08db4c2d58e35bcefb5c927d49bdf71`. The receipt SHA-256 is
`c9dfc54479f322d52c21f9fd95c832d650a0bdbae429f790c73f5a50a6ba0702`.
Full copyrighted PDFs and extracted texts remain in the short-lived
authenticated artifact and ignored private workspace. No full paper is
republished in this repository. The structured companion
`docs/intraday-primary-methods.json` binds URLs, PDF/text hashes, read scopes,
page references, native failures and secondary-code provenance.

## Noise-area method actually specified by the authors

Zarattini, Aziz and Barbon's *Beat the Market: An Effective Intraday Momentum
Strategy for S&P500 ETF (SPY)* was first published May 10, 2024; this retrieved
version is dated September 22, 2025. Original PDF SHA-256:
`865010dfd938d513c1cd22a7be5932bc232afe498c3cf493d6d8bd4b0de86ebb`.
The principal study uses IQFeed one-minute SPY/VIX OHLCV from May 2007 to
April 2024 (p.6).

For each checkpoint `t`, compute the previous 14 sessions' absolute return
from their own 09:30 opening to that same clock time. The arithmetic average
is `σ(d,t)=mean |C(d−i,t)/O(d−i,09:30)−1|`, for `i=1..14` (p.6).
This is a mean absolute movement, not a standard deviation or an estimate
of news sentiment. Gap-aware bounds are
`UB=max(today_open,prior_16_close)×(1+VM×σ)` and
`LB=min(today_open,prior_16_close)×(1−VM×σ)` (pp.7,21).
The primary multiplier is one; other multipliers are historical diagnostics.

The primary model checks at 10:00 and subsequent HH:00/HH:30 times. A price
above the upper bound selects a long; below the lower bound selects a short.
An opposite breakout can close and reverse the exposure. Every position
closes at 16:00; the original stop checks are also semi-hourly (pp.9,21).
The refined long exit threshold is `max(UB,VWAP)`; the short threshold is
`min(LB,VWAP)`, using only the current regular session (p.13). The main paper
does not establish an always-active tick stop, monotonic stop ratchet or the
precise tick-versus-bar VWAP construction.

The refined position size is previous closing equity divided by today's
opening price, multiplied by `min(4,0.02/s_daily)` and floored to shares.
`s_daily` is the sample standard deviation of the previous 14 daily returns,
with denominator 13 (p.15). The 2% quantity is a daily volatility target,
not a guaranteed 2% maximum loss or a prop drawdown allowance.

The authors report 19.6% annual return, Sharpe 1.33 and 25% maximum drawdown
for the dynamic-size SPY model; the one-times-exposure same-band/VWAP model
reports 9.7% annual return and 12% drawdown (pp.14–16,43). These reported
returns neither establish 8% monthly nor fit a 10% static drawdown rule by
themselves. Commission is USD 0.0035/share/side and fixed adverse slippage
USD 0.001/share/side (pp.10,24–25). The slippage calibration is an author
reported limited April 2024 experiment on SPY, with more than 1,000 trades;
its original executions are unavailable to this review.

Volatility, previous-day patterns, weekdays, multipliers and lookbacks are
examined on historical samples (pp.17–24,31,36). Five-day RSI is proposed as
a dealer-gamma proxy; it is not measured dealer inventory. The main sample
contains several rule refinements and no fully specified preregistered
untouched split. Later FAQs report different endpoints and post-publication
monthly results through August 2025, including losing months (pp.40–42).
Those author updates are neither independently verified fills nor evidence
of stable income for a different asset or fee schedule.

## The individual-stock ORB result cannot be transferred to indices or crypto

Zarattini, Barbon and Aziz's *A Profitable Day Trading Strategy For The U.S.
Equity Market* is dated February 16, 2024. Original PDF SHA-256:
`9423012e9f0199e3f6925c500725815c236d7ddbdd7500d50d10bac2be745e91`.
The sample is approximately 7,000 NYSE/Nasdaq stocks, including delisted
companies, during 2016–2023; CRSP supplies the universe and IQFeed the
unadjusted intraday prices (pp.7–8).

Eligibility requires opening price above USD 5, previous 14-day average
volume at least one million shares and daily ATR above USD 0.50. The first
09:30–09:35 candle's direction determines the only permitted side. Stop-entry
is at that candle's high or low; a doji produces no order. The protective
stop is 10% of previous daily ATR from the actual entry; the remaining
position exits at 16:00 (pp.6–10).

The profitable refinement selects the daily top 20 eligible individual stocks
by first-five-minute volume relative to their previous 14 corresponding
opening volumes, requiring a ratio of at least one (pp.13–16). Company news
and unusual individual-stock trading activity are central to the mechanism.
The printed denominator's repeated `t−1` subscript is inconsistent with the
surrounding 14-day-average description; it should not be copied literally
as a fourteen-times repeated one-day observation.

The authors report 41.6% annual return, Sharpe 2.81 and 12% drawdown for this
stock-selection portfolio; the unfiltered base model reports 3.2% annual
return and Sharpe 0.48 (pp.12,17). Commission is USD 0.0035/share/side. The
paper does not supply enough verified slippage, stock-borrow, multi-position
capital allocation or untouched split detail to certify a retail prop
reproduction. Selecting retrospective best stocks or replacing those stocks
with BTC/ETH or hourly index futures would be a different experiment.

## What the public implementations establish

The pinned MIT repository
`giovannibrusco/zarattini-2024-momentum-spy` at
`ec10608398b86c1a48d83411ae3e0fc9ab4cbfd1` supplies a readable independent
implementation. It is a secondary replication, not verified author code.
Its documented minute bars cover `[HH:MM,HH:MM+1)`, yet it uses their closes
to execute at `HH:MM`; the corresponding price is not then available.
It may execute at a stale quote when the checkpoint observation is missing,
and defaults to only seven usable sessions for a 14-day band. Its VWAP is
a typical-price approximation. Those choices will not be inherited silently.

An additional GitHub `article.pdf` claiming the cryptocurrency paper's title
was actually inspected and identified as a student course replication; it
was rejected as an original source. An AQR candidate returned HTTP 200 at
the `/404` destination and was likewise rejected. Native direct Concretum
PDF requests still return proxy 403; actual original access came through
the reviewed CI producer, not a claimed successful native request.

## Bounded native crypto experiment proposed before outcomes

The feasible next experiment is **a crypto adaptation** using synchronized
official BTCUSDT/ETHUSDT five-minute trade prices, original quote/base volume,
actual funding settlements and separately acquired five-minute marks.
It is a joint two-asset portfolio with 24 configurations:
band multiplier 0.75/1/1.25 × completed checkpoint 15/30 minutes ×
current-band/current-band-plus-VWAP exits × aggregate stop-risk 0.5%/1%.
The lookback remains exactly 14 prior completed local weekday sessions.

Use pinned New York time, actual 09:30 opening and known prior eligible
16:00 close. The 24/7 crypto weekday convention is not an NYSE holiday
calendar. A signal price is the last completed native candle, and orders or
stop updates first act at the next observed opening. All exposure exits at
the first traded 16:00 opening. Missing later observations cannot remove an
earlier decision; stale or zero-trade quotes cannot manufacture fills.
Aggregate session VWAP is `sum(original_quote_volume)/sum(original_base_volume)`
from already completed candles, which uses actual executed trade totals.

An initial protective band/VWAP stop, monotonic checkpoint ratchet,
cost-inclusive stop-risk budget, two-times gross exposure limit and physical
isolated collateral are explicit changes to the authors' model. Margin and
both notional fees must be paid from total modeled equity, with actual
funding booked chronologically and independent mark extrema retained.
Five-basis-point taker commission/side, two-basis-point slippage/side and
one-basis-point full spread are stated research assumptions; double-cost
stress replays fills, sizing and cash. Current/historical venue tariffs,
quantity filters, maintenance tiers and executable book depth are unverified.

The own protective implementation uses a completed-mark breach as a queued
exit at the next genuinely traded five-minute opening. It never backfills an
intrabar execution at the old band. Opening gaps can exceed the stop budget.
No same-bar re-entry or reversal follows an exit. All new entry intents reserve
cash, known equity, gross exposure and risk before any old volume-dependent
exit can release collateral; that released cash is usable at a later decision.
These are conservative research choices, distinct from the original paper's
semi-hourly discretionary stop checks and opposite-side reversals.

Before native P&L, the final implementation needs causal/nonvacuous fixtures,
source and unit checks, independent review and immutable protocol/input
locks. Use unchanged common gates, 2024 TRAIN and exactly one primary before
2025 validation; failed validation leaves 2026 unopened. No historical proxy
outcome activates live orders, prop qualification or Telegram alerts.
