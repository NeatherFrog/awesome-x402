# Frozen liquidity-sweep / FVG protocol

`liquidity-fvg-v1` implements four hypotheses suggested by the user's chart
examples. It formalizes otherwise discretionary concepts; it does not reproduce
or verify the pictured trade, whose instrument and full causal history are not
available. No course author's profit claim is evidence for this implementation.
Thresholds and execution rules below are fixed before reading study outcomes.

## Four declared variants

| Identifier | Reference rejection + displacement/FVG | Opposing-pivot MSS | Sweep session |
| --- | --- | --- | --- |
| `sweep_all` | Required | No | Every completed bar |
| `mss_all` | Required | Required | Every completed bar |
| `sweep_lunch` | Required | No | NY weekday lunch |
| `mss_lunch` | Required | Required | NY weekday lunch |

The intended research timeframe is five minutes (`interval_seconds=300`).
The API can represent another regular interval explicitly; that constitutes
another declared experiment and must not be silently substituted after failure.
Lunch means the **sweep bar close**, converted with IANA `America/New_York`,
Monday–Friday from 11:00 inclusive to 13:00 exclusive. DST is therefore handled.
The displacement and entry may occur after the sweep session ends. Crypto trades
24/7; lunch variants still deliberately exclude Saturday and Sunday.

## Causal signal definition

1. Input OHLCV timestamps are opening labels in explicit UTC. Every supplied bar
   must already be closed. The caller is responsible for excluding an exchange's
   current unfinished candle. Rows must be ascending, unique, valid, and separated
   by exactly the declared interval. Missing candles cause rejection, never
   interpolation, silent sorting or deletion. The engine permits 1,000,000 rows.
2. A high/low pivot has two bars on each side. Its high must be strictly higher,
   or low strictly lower, than all four neighbors; ties are excluded. It becomes
   known only at the second right neighbor's close. A sweep can reference only
   the latest same-side pivot already confirmed **before that sweep bar**.
3. A bearish sweep strictly exceeds that high and closes strictly below it.
   A bullish sweep strictly breaks that low and closes strictly above it. Freeze
   the opposing pivot that was also known before the sweep. One unresolved sweep
   per side is kept; a newer valid sweep replaces an older unresolved sweep.
4. The first qualifying displacement must occur in bars 1–6 **after** the sweep;
   the sweep cannot qualify itself. The directional body is at least the prior
   completed Wilder ATR14, and the close is in the terminal quarter of the bar's
   range. ATR begins with the arithmetic mean of the first 14 true ranges, then
   uses Wilder's `(13 * previous + new TR) / 14`. The current displacement bar's
   true range is excluded from its own threshold. First-bar TR references its
   opening price because earlier history is not supplied.
5. The third bar of a three-bar bearish FVG has `high[t] < low[t-2]`; for bullish,
   `low[t] > high[t-2]`. Its width must be at least 0.1 prior ATR14. In MSS variants,
   the displacement close must also strictly cross the frozen opposing pivot in
   the intended direction. A later pivot cannot retroactively supply MSS.
6. The signal becomes available at the **third bar's close**. Entry is the FVG
   midpoint. Stop is beyond the most adverse extreme from sweep through signal,
   plus a 0.1 prior-ATR buffer. The target is fixed at 2R from that midpoint.
   Price levels, ATR and reference timestamps are immutable after the signal.

Signals contain exact `entry_low/high`, `entry`, `stop`, `target`, `invalidation`,
reference price/availability, signal close, sweep close, expiry and reasons.
Their deterministic ID includes symbol, variant and a hash of frozen signal
data. No screenshot-only information or future pivot contributes to detection.

## Orders and lifecycle

There is one pending midpoint limit starting at the next bar open. It is valid
for six subsequent bars and expires at the sixth bar's close. No signal-bar fill
is permitted. A long needs `low < entry`; a short needs `high > entry`. Equality
is insufficient because a candle touch does not prove queue execution.

If the very next opening price already invalidates the stop, the order is
cancelled before being placed. Once a limit has rested, a later price gap through
entry and stop conservatively fills at the limit and stops at the worse opening
price. This can exceed the planned loss.

`detect_setups` evaluates independent hypothetical lifecycles: `candidate`,
`triggered`, `expired`, `invalidated`. `triggered` means an OHLC condition was
observed, not an exchange acknowledgement or real fill. Later lifecycle fields
can change as more candles close; frozen signal fields are prefix invariant.
Lifecycle `status_time` for an intrabar trade-through is when the candle closes,
because OHLC does not reveal the exact execution time.

## Conservative research execution

`backtest` keeps only one pending order or one position at a time, accepting the
first chronological signal when flat. New signals are still recorded while an
order/position exists but are not executed. This is not a backtest of simultaneous
independent setup positions, and signal-trigger frequency is not portfolio fills.

Stop-price touches execute; target limits need strict trade-through. Stop and
target in one candle are resolved stop-first. An entry-and-stop collision is a
loss, including when a favorable extreme also occurs in that candle. An entry
bar's target is not credited because the favorable excursion may have happened
before entry. Opening gaps beyond a held stop use the worse opening price;
favorable target gaps receive no price improvement beyond the target.

Illustrative defaults:

| Parameter | Default | Interpretation |
| --- | --- | --- |
| `initial_balance` | 100,000 | Account currency |
| `risk_pct` | 0.25 | Percent of current balance, including modeled stop costs |
| `max_gross_leverage` | 1 | Gross entry notional / current balance |
| `fee_bps` | 10 | Each side, entry and exit notional |
| `slippage_bps` | 2 | Each side, adverse price adjustment |
| `spread_bps` | 1 | Full spread; half applied at each side |
| `expiry_bars` | 6 | Fixed for this protocol |
| `interval_seconds` | 300 | Five-minute bar interval |

Position size is the smaller of the cost-inclusive risk budget and gross notional
cap. Fees are debited at entry and exit. Market-data opening gaps are modeled;
missing-candle intervals are not. Drawdown uses conservative adverse OHLC marks,
with the mark limited to the already-executed stop when a stop exits a position.
Open positions at the data boundary are liquidated at its last close **only for
research accounting**, paying modeled exit costs; those exits are labelled
`end_of_data_hypothetical` and counted separately. A live trader would still
have that position. `profit_factor=null` means no loss denominator, not infinity
or proof of an edge.

No real trading can be inferred from these results. Funding, borrow, contract
precision, minimum notional, queue/depth, liquidation rules, outages and firm
constraints are not available in this module. In particular, ordinary spot
historical prices do not make short signals executable. All results remain
`qualified=false` even if retrospective returns are positive. Statistical
selection, an untouched holdout, cost stress and genuine forward execution
belong to the surrounding research protocol.

## API and verification

```python
from propdesk.liquidity import backtest, detect_setups

setups = detect_setups(closed_bars, symbol="BTCUSDT", variant="mss_all")
study = backtest(closed_bars, symbol="BTCUSDT", variant="mss_all",
                 config={"fee_bps": 10, "slippage_bps": 2, "spread_bps": 1})
```

`study` returns `metrics`, `trades`, `setups`, normalized `config`, protocol version
and explicit `limitations`. Trade records distinguish hypothetical boundary
liquidation, ambiguous bars, raw and cost-adjusted fills, fees, planned risk,
net P&L and within-bar timestamp uncertainty.

`python -m unittest tests.test_liquidity -v` checks pivot confirmation and ties,
MSS causality, signal close timing, prefix invariance and future mutation,
bull/bear symmetry, NY session/DST, strict limit touches, expiry, gap invalidation,
resting-order and held-position adverse gaps, collisions, fees, leverage,
boundary exits, input integrity, finite JSON and histories exceeding 30,000 rows.
