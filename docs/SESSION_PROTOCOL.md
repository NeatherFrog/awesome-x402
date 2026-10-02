# Preregistered futures session study

This is a separate economic study of index-futures session behavior, not a risk
rescaling of failed liquidity/FVG models. The objective and chronological gates
are fixed in [EIGHT_PERCENT_PROTOCOL.json](EIGHT_PERCENT_PROTOCOL.json), SHA256
`5495a0683efeb6da230cf454b71c8e8ae952dc03534d23f3cedbcd9f56e9e839`.
Its statistical rules take precedence over any previous lower return objective.

The machine protocol is frozen by `scripts/research_sessions.py --freeze` before
the first study P&L calculation, with immutable locks under `data/session-research`.
The engine is independently reviewed and tested before outcomes. Previously
inspected Yahoo2024–2026 history and all prior292 trials remain selection history;
there is **no globally blind holdout or proof of future stable profit**.

## Markets and sessions

The declared markets are continuous Yahoo hourly `MES=F` and `MNQ=F` from the
verified 2026-10-01 snapshot. MES multiplier is5dollars/point, MNQ2, both .25tick;
this is not a fixed-contract broker quote feed. Source/provenance hashes and full
calendar coverage are locked. Rollover, actual margin, queue execution and broker
fees remain limitations even if a historical reference screen passes.

The pinned official Lean US-equity calendar defines which **NYSE cash-open** days
are observed; it does not pretend to be the complete CME trading calendar. All501
cash sessions must be complete on both markets. Additional futures quotes on cash
holidays are excluded by the already declared calendar, not after observing P&L.
Missing required anchors fail the entire study; prices are never imputed.

Normal futures hourly candles have whole-hour NY opening labels. The09:00 candle
straddles the09:30 cash open and is excluded. The first fully contained RTH hour
is **10:00–11:00**, so this is explicitly a late-opening-range adaptation, not a
09:30 range or exact implementation of a published minute strategy. Feature
candles open10,11,12,13,14; the actual15:00 opening flattens all positions. The
15:00 candle's later OHLC/volume is never used for execution or indicators.

Five calendar halfdays use the vendor's observed09:30,10:30,11:30 anchors and
the observed12:30 opening to flatten. The later12:30 OHLC/volume is not treated
as a full hour. Full-session feature state resets the intraday proxy VWAP; Wilder
ATR14 and EMA20 retain only previously closed full-hour feature observations.
Timezone conversion uses real IANA `America/New_York` transitions.

## Fixed hypothesis inventory

Three families each have16 economic variants, or48 economic rules total. Every
rule is paired with three **TRAIN-only sizing choices**, aggregate account risk
.5%,1%,1.5%, giving144 portfolio variants and288 market hypotheses. Cost stress
is a fixed robustness scenario, not a new optimized choice. All failed attempts
and the full training grid remain in the experiment ledger.

| Family | Fixed choices | Exact trigger |
|---|---|---|
| Late opening-range breakout | First1or2fullhours; buffer0or.1priorATR; target1.5or2.5R; priorEMA20 filter off/on | Later closed hour ends strictly beyond the completed opening range+buffer; next opening must remain beyond the unbuffered range edge |
| Failed-range reversion | First1or2hours; excursion0or.25priorATR; target range midpoint or VWAP proxy; EMA20 stretch filter off/on | A later closed candle strictly sweeps one range edge and closes strictly inside; candles sweeping both sides are rejected because sequence is unknown |
| Volatility release | Prior4or8feature-hour channel; body .75or1.25priorATR; target1.5or2.5R; priorEMA20 filter off/on | Closed directional body exceeds expansion threshold, closes beyond the prior channel and in the terminal quarter; channel excludes the signal candle |

Breakout stop is beyond the opposite opening-range edge plus .1priorATR.
Reversion/release stop is beyond the signal candle's adverse extreme plus
.1priorATR. For breakout/release, the target is fixed from actual next-open entry
and the frozen stop. Reversion target is frozen at the signal close; a next-open
gap leaving no positive net reward blocks entry. The EMA20 filter in a reversion
model requires a short signal above priorEMA or a long signal below it; trend
models use the matching direction. Missing or zero-volume VWAP proxy is unknown,
not an invented price.

The VWAP proxy is cumulative current-window `(high+low+close)/3 * reported volume`
divided by reported volume. It contains only closed feature candles, but **is not
trade-level VWAP or full09:30-session VWAP**. Prior-channel features may cross a
previous cash session; unseen overnight ranges are not substituted.

## Futures sizing and execution

Total nominal account is100,000, split into two independent50,000risk buckets.
Aggregate risk grid .5%,1%,1.5% corresponds initially to250,500,750dollars of planned
cost-inclusive risk per asset. This grid is registered before outcomes, selected
only in TRAIN, and never applied later to multiply a failed heldout result.
Whole contract quantity is the floor of risk budget divided by cost-inclusive
stop loss, capped at10micros per asset (20total). This is a conservative research
cap, not a claim that a personal prop account or broker permits that exposure.
If one contract exceeds budget, the order is skipped and the flat day retained.
The100k label is not cash margin or available drawdown: actual firm MLL/daily
loss rules and permitted position limits require separate replay and verification.

Commission is the verified published TopstepX MES/MNQ tariff of1.22dollars round
trip, derived as .61dollars/contract/side; one-tick full spread and
one-tick slippage per side. Each execution price rounds adversely to a quarter
tick. The fixed stress scenario doubles commissions, spread and slippage before
rounding. The advertised tariff is not a verified personal contract; spread and
slippage are research assumptions. The source receipts below are frozen in the
protocol. The advertised100K Combine maximum is100micros aggregate, but XFA
balance-tier limits differ and the numeric tier image was unavailable. The
20micro study cap therefore remains an explicit assumption, not verified XFA
buying power.

- [TopstepX commissions](https://help.topstep.com/en/articles/8284213-topstepx-commissions-and-fees), retrieved body SHA256 `89e0285102d116bd1c1590a3f5e317a940d4ee7b1ccf42a51ad02b26697a20e2`.
- [Trading Combine parameters](https://help.topstep.com/en/articles/8284197-trading-combine-parameters), SHA256 `dceedd3fb2d025d783fef0bb84ad702bdc5fb9df113d3b0a7ce1c1a65f16d0ed`.
- [XFA scaling](https://help.topstep.com/en/articles/8284223-what-is-the-scaling-plan), SHA256 `9c4a40cc17b884f9389fa81b0630d966f8774345b7ac0bbb337ea888f4870807`.

Signals use only the previous closed hour, stamped at its close; orders enter at
the next observed opening. Entry may hit stop or target later in that bar because
entry is at its known opening. Stop wins if both are hit. Held-position adverse
gaps stop at the worse opening price; target gaps receive only the target price.
At most one actual entry is allowed per market per cash session; no pyramiding,
averaging or reentry. A scheduled flatten opening exits before later candle
extremes. Missing that opening fails instead of inventing an end-of-data close.

Equity envelopes are explicitly conservative **liquidation estimates including
modeled exit costs**, not actual broker MTM. Synchronous asset envelopes are
summed before daily aggregation. Best/worst hourly ordering is not known; the
common evaluator treats adverse-after-peak daily ordering as a conservative
bound. All calendar days, including verified flat weekends/holidays, are kept.
Target gates use these best/worst envelopes, not the simpler closing-peak engine
metric. Complete transaction records preserve exact units, notional, costs and
cash flows. Nominal account percentages are never averaged across assets.

## Chronological selection and stopping

- TRAIN:2024-10-01 through2024-12-31, physically truncated before2025 input reaches
  the engine. All144 variants are assessed at base and doubled costs. Positive
  net/base stress,30completed episodes,60calendar days, adverseDD≤10%, reference
  daily loss≤5% of initial total account are required.
- Only passing TRAIN candidates compete on total net return divided by adverse
  DD with .25% floor, then lexical ID tie. One candidate is locked before OOS.
  With no passing candidate, OOS stays unevaluated; the best failed TRAIN score
  is only a labelled diagnostic.
- VALIDATION: calendar2025, only the locked primary. It must satisfy the common
  8% geometric monthly equivalent, six full months,60episodes, conditional99%
  daily-mean CI lower>0(7calendar-day blocks,5000resamples, fixed seed), positive
  stress/median month, at least2/3positive months, both chronological halves
  positive and the same reference risk limits. Failure stops final evaluation.
- FINAL:2026-01-01 through2026-09-30, only after a passing validation-confirmation
  lock. One primary final run, identical rules/risk/costs. No alternate OOS winner
  or reoptimization is substituted. Inputs remain globally previously inspected.

Even a passed historical reference screen does not authorize Telegram trading
signals, a real order or a cash-payout claim. Exact FTMO Prague-day / Topstep MLL
conditions, executable quotes, contract/fee/margin verification and genuinely
new forward observation remain separate requirements.
