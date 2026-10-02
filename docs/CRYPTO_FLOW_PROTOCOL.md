# Native aggressor-volume research before outcomes

This study adds genuinely new source fields from the original, preserved
Binance USD-M5m ZIPs: USDT quote volume, integer trade count and taker-buy base /
quote volumes. These are contemporaneous traded-notional facts. They do not
identify a resting order book, hidden liquidity, actual stop raids, dealer
inventory or liquidation trades. Previous price-based studies and generally
inspected2024–2026 prices remain adaptive selection history; no globally blind
period or independent-profit claim.

Two economic hypotheses are fixed: strong aggressive flow accompanied by a
directional displacement may continue; strong aggressive flow accompanied by
little price movement may reverse (an absorption hypothesis, not an observed
book fact). Exactly64 configurations cross family2 ×flow window1/3 complete5m
bars ×absolute signed-quote-flow threshold0.15/0.30 ×hold1h/3h ×stop1/2 latest
fully closed1hATR20 ×risk0.5%/1% current total account equity.

Signed flow is `2*sum(taker_buy_quote_volume)/sum(quote_volume)-1`. No zero-total
ratio is imputed. Every candle in the signal window must have actual trades.
Current summed quote volume must be at least1.25 times the prior72-bar mean
scaled by window size, and summed trade count at least the corresponding prior
mean. The activity baseline excludes the ENTIRE current signal window.
Continuation requires the window price body to agree with flow and exceed
0.5 of prior5mATR20 times square-root(window). Absorption requires the absolute
body to be at most0.25 of that scale and trades opposite signed flow. Body and
flow become known together only when the last window candle closes.

Orders fill at the subsequent native5m open with modeled adverse friction.
Stop is one or two times the latest complete hourlyATR20 from the actual entry fill;
there is no profit-price target or optimized trailing exit. Close at the first
traded native opening at least1h/3h after entry, or adverse stop/liquidation or
explicit costed sample boundary. These are time-exit hypotheses, not exact
future exit-price predictions. At most one position per asset/two total; no
same-bar reentry after an exit.

The physical account contains100,000USDT total. Isolated2x collateral plus
entry fees must be paid from positive shared cash. Gross entry exposure is at
most2x `min(initial,current marked account)`; each asset at most1x. Stop risk
includes modeled adverse stop-fill friction and both fees. Combined new and
existing stop budgets are at most twice the registered position risk. Both
asset order quantities, risk and cash are reserved from the already-known
opening account BEFORE checking current5m future zero-volume evidence; unused
reservations cannot enlarge the other order within that interval. There is no
external money, collateral reinjection or free funding income.

Copy the independently reviewed immutable native-trend executor
SHA256`75f43df5e547c3853369e5734d359d07df6409a19bb63939e1da1567a4956d28`
into a NEW producer. Its nested wallet/equity/close/funding functions and final
daily/metrics accounting remain AST-identical. Explicit registered adaptations:
native5m decision size; prior-native ATRindex; actual complete-hour ATR known-at;
prior5m signal timestamp; fixed age exit; stop-factor field name; joint causal
entry reservations and quantity sizing including stop friction/aggregate risk.
These are a new volatility/risk interpretation, not unchanged parent alpha.
Original producers remain unchanged. An independent diff and property audit
must precede freeze and the first strategy-return calculation.

Fees are5bps taker per side, adverse slippage2bps per side, full spread1bp
(half each side); all double under stress. Actual realized funding retains
settlement milliseconds, uses the parent's causal hold/settlement chronology,
and never forecasts entries. Missing official marks use trade-open proxies.
Positive ambiguous funding cannot rescue possible earlier liquidation; gaps,
deficits, nonexecuted mark uncertainty and both fees remain explicit. Zero-volume
source rows cannot create signed flow or prove entry fills. Any held zero-volume
mark/execution gap disqualifies the historical period. Parent maintenance/fee
proxy0.5% and lot-step0.001 are historically unverified assumptions. Any
liquidation or unfunded deficit disqualifies; counterparty/mark risks remain.

All64 TRAIN2024 configurations receive separate base / double-cost replays.
Unchanged common TRAIN: positive net and stress,30 completed episodes,60 calendar
days, conservative account drawdown<=10%, reference daily loss<=5% initial total
capital, plus zero liquidation/deficit/unknown held gap and cash/PnL reconciliation.
Select ONE passing highest net-return/max(adverse drawdown,0.25%), tie by ID;
persist its risk/hold/parameters before any2025 strategy-return calculation.
Validation2025 uses common8%-monthly-equivalent /60episodes /6full months /
99%daily block lower bound>0 /positive double costs /positive median month /
>=2/3 positive months /both chronological halves positive /same risk limits.
Only a passed fixed primary receives an immutable confirmation and ONE2026
Jan–Sep final. Any failure stops without a replacement, new risk multiplier or
threshold revision. Complete UTC calendar daily total-dollar marks are required;
bankruptcy makes geometric inference undefined rather than fabricated.

Raw input/archive/field-document/source-audit/parent/common/producer hashes,
all rejected configurations and primary full ledgers are retained. Source
CC-BY-NC-SA permits personal historical research; it does not establish a licensed
production feed. Intrabar paths, executable tariffs, marks, queue, historical
filters, USDT/USD parity, actual contract, platform and payout eligibility are
unknown. No exchange orders, purchases, withdrawal or Telegram signals.

The prior activity mean and ATR history can include zero-volume placeholder
bars. Those zeros are recorded absence, never neutral signed-flow observations;
these historical price/activity/volatility references remain provisional rather
than executable liquidity. New flow ratios still require every current-window
bar to trade. The original source snapshot has exactly3012 recorded8h funding
slots per asset; this dataset identity check does not extrapolate a universal
future funding schedule. Common objective and reviewed parent identities are
literally pinned and verified; immutable selection/confirmation files are
checked immediately before FINAL. Missing claimed locks are never repaired.
