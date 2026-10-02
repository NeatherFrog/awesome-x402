# Native perpetual trend/context preregistration

This is a new adaptive economic study after the frozen coarse and close-confirmed
relative-value studies failed. All general 2024–2026 market history has already
been inspected. Existing producers, input locks and outcomes remain immutable.
No globally untouched-history claim is made.

The exact machine grid is `native_crypto_trend.grid()`: **96 total variants**,
not independent discoveries. Eight economic configurations × hourly/daily
decisions × current-account risk .25/.5/1% × fixed 2/3 prior daily-ATR stops.

| Family | Economic configurations | Total variants |
|---|---|---:|
| EMA long/short trend | Fast/slow calendar days 5/20,10/40,20/60 | 36 |
| Channel long/short breakout | Entry/exit calendar days 5/2,20/10,55/20 | 36 |
| Fast reversion with momentum context | RSI2 extreme5/10; past63 calendar-day momentum | 24 |

Original-author slow-momentum/fast-reversion code informs the economic question,
not these precise crypto rules or their profit. The pinned source receipt is
`docs/author-regime-methods.json`. Its daily continuous-futures, learned models
and performance are not reproduced here. No warmup backfill, future-return
features, realized-test-volatility scaling or omitted initial entry cost.

Hourly/day candles are aggregated from authentic BTC/ETH USD-M perpetual5m
trade candles; spot prices are not mixed in. Entry decisions use only the prior
fully completed aggregate. EMA seeds the first real known-window average. Day
periods multiply24 for hourly decisions; the daily version keeps calendar days.
Channel thresholds exclude the current completed bar. ATR14 Wilder smoothing
uses only the **previous completed UTC day**, never the running day.

EMA enters the current known regime when flat and exits after the known regime
disagrees. Channel entry requires a completed close strictly above/below prior
N-bar highs/lows; exit uses prior M-bar lows/highs. Reversion longs require
RSI2≤5/10 with positive63-day momentum, shorts RSI2≥95/90 with negative momentum;
exit at RSI recovery50 or context reversal, plus fixed2R target. Trend/channel
have no fixed target. All stops are fixed2/3× prior dailyATR from adverse entry
fill. Gap stops fill opening prices; targets get no favorable gap improvement.
Within the same native5m candle, stop precedes target; liquidation has priority
where the OHLC cannot exclude an adverse isolated-margin breach. No same-native
bar reentry after exit. Final-boundary exits are labeled retrospective close.
Zero-volume candles cannot fill entries/indicator exits/stops/targets; any held
exposure across such a candle is recorded as unresolved and disqualifies both
base and stress eligibility.

All positions use one physical $100,000 account. Isolated2x margin and entry fees
are reserved from positive freecash; no additional capital or margin topups.
Risk is .25/.5/1% of current total marked account equity, divided by fixed stop
distance, rounded down BTC/ETH .001 quantity steps. Per-asset entry gross is
capped at1×min(initial,current equity), total2×; prices can alter exposure after
entry. These are fixed pre-outcome caps. Fees/gaps/funding can exceed nominal
stop risk. Historical quantity/maintenance tiers are provisional assumptions.

Each side incurs5bps fee,2bps adverse slippage and .5bp halfspread. Required
stress doubles all friction. Actual settled funding retains exact milliseconds:
exactT old-held events precedeT orders after checking earlier gap liquidation;
T+.002 events followT orders. Held age must exceed/equal60seconds. A future
receipt cannot size or finance an earlier order. Missing historical mark price
uses the native opening trade-price proxy. Positive funding is omitted when
same-candle stop/target/liquidation could precede settlement; adverse charges
remain, with ambiguity recorded. Both base and doubled-cost liquidation or
unfunded deficit prevent eligibility; wallet floors do not imply insurance.
An exact sample-end settlement/boundary-close tie retains possible debits and
omits uncertain positive credits; a later millisecond event follows the exit.

Native5m portfolio adverse/favorable corners and daily peak-before-worst are
conservative bounds because extrema ordering and simultaneous prices are not
known. Whole-candle extrema can lie after an exit. Common accountDD≤10% and
priorUTC-close-to-daily-worst loss≤5%INITIAL capital are research references,
not exact FTMO staticfloor/Prague contract rules.

Freeze machine protocol, all sources, author receipt, common objective and all
producers **after synthetic tests and independent audit but before outcomes**.
Train2024; three chronological folds use the existing common boundaries.
Eligibility: positive net and doublecost;30 completed episodes;60 calendar days;
risk bounds; no base/stress liquidation/debt;≥2/3 positive net folds. Select
**one** by net return/max(adverseDD,.25%), then lexicographicID, and lock before
opening2025. Low episode counts mean insufficient evidence, not necessarily
absent economic alpha. No candidate means no OOS performance is computed.

Only that primary can face2025. The unchanged common8%-monthly screen requires
60 completed episodes,6 full months,99%7day/5000 bootstrap dailymean lower>0,
positive doublecost monthly equivalent, positive medianmonth and≥2/3 positive
months, both chronological halves positive and risk/debt guards.2026Jan–Sep
opens only after2025 passes; no replacement or outcomes-guided sizing.

Gross price PnL, fees, adverse fills, funding, turnover, capital exposure and
daily BTC/ETH correlation/beta are TRAIN-only diagnostic evidence. The price
decomposition uses the same actual quantities/exits, not a zero-cost resized
strategy. Market return references are uncosted, not executable benchmarkalpha.

Personal non-production CC BY-NC-SA source data. Historical screening cannot
enable real orders/Telegram, certify future profit, provide a cash withdrawal
or prove8% every month. Exact prop-stage/rules/mark execution and genuinely new
forward observations remain required.
