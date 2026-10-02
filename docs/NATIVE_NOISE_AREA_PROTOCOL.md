# Native noise-area protocol before outcomes

This is a new BTCUSDT/ETHUSDT perpetual crypto adaptation after previous
research on the same history. It does not reproduce the original SPY results,
establish a globally untouched holdout, or certify FTMO trading or payouts.
Original Concretum noise and ORB papers were read in full extracted text;
provenance and precise page references are in INTRADAY_PRIMARY_METHODS.md.

The fixed catalog has24 joint portfolio configurations: band multiplier
0.75/1/1.25, closed checkpoint15/30minutes, current-band/current-band-plus-VWAP
exits, and aggregate risk0.5%/1%. The lookback is exactly14 prior completed
local weekday sessions. Direct pinned NewYork TZif handles DST. Session opens
09:30, first checkpoint10:00, final checkpoint15:45/15:30, and scheduled flat
is first genuine traded16:00opening. Crypto weekday convention does not
pretend that NYSE holidays or actual prop news restrictions were verified.

For each asset and current closed slot t, sigma is the arithmetic mean of
abs(prior-session-slot-close/prior-session09:30open−1) across exactly14 prior
completed weekday sessions. It is not a standard deviation. A missing or
zero-trade reference slot makes that current slot unknown; no older date is
substituted. Today's future16:00close or future full-day availability never
filters today's earlier entry. Upper band is max(current09:30open, previous
eligible16:00close)*(1+k*sigma), lower band uses min and (1−k*sigma).

Session VWAP is actual sum(original executed USDT quote volume)/sum(original
executed BTC-or-ETH base volume), including only known completed5m bars since
09:30. This uses checksum-verified original Binance12-field archives rather
than a typical-price approximation or invented TradingView observation.

Closed checkpoint close above/below band gives long/short intent. Next
native5m observed opening is an execution proxy after the observation closes;
same-boundary latency and an executable quoted book are unverified. Initial
protective stop uses current band or band/VWAP max(long)/min(short), strictly
on loss side of adverse entry and prior completed mark. Known opening gaps
execute at actual adverse opening, not at a band. Checkpoint stops ratchet
monotonically and activate no earlier than the next opening. A completed
computed-mark adverse endpoint touching the stop queues an exit at the next
genuine traded opening. It cannot fabricate an earlier intrabar stop fill.
No same5m re-entry/flip after any exit. These stops and no-immediate-flip
choices differ from the authors' semi-hourly model.

TOTAL modeled initial equity is100000 USDT-equivalent. Each isolated wallet
reserves quantity*adverse_fill/2 plus entry fee from actual shared cash. Total
new entry gross is capped at2*min(initial,current known-mark equity), each
asset at1x. Each asset requests half of aggregate0.5/1% stop-risk budget,
including adverse entry, planned adverse stop exit and both notional fees;
quantity rounds down to declared .001 base-unit steps. Actual exchange
contract filters and tariffs were not verified. Gaps, funding and delayed
execution can exceed the nominal risk; this is not a guaranteed loss limit.

All new intents reserve known cash/equity/gross/risk before any old exit can
release collateral conditional on that opening's future whole-bar volume.
Known exact-T old funding debits use completed marks before reservation;
positive exact-T credits are omitted. Old released margin may finance a
later decision only. This explicitly fixes the inherited old-exit release
ordering problem in the new interpreter without rewriting prior studies.
The preserved markV1 producer is used for reviewed immutable source/math
helpers only. Its old exit-to-entry chronology was independently blocked;
pinning its hash does not validate that earlier study's selection. The new
Noise reservation order is separately tested and preregistered here.

Assumed friction is5bps commission/side,2bps slippage/side,1bps full spread.
Each side charges its actual filled notional. Stress doubles every component
and reruns fills, sizing, stops and cash. Realized funding retains actual
millisecond timestamps and is not an entry forecast. Settlement-point exact
mark/entitlement, historical tiers and insurance remain unknown. Canonical
funding JSON/acquisition manifests have original checksum receipts; original
funding ZIP bytes are not retained locally, unlike trade and mark ZIPs. Their
raw byte revalidation is not claimed.

Authentic Binance calculated5m mark OHLC is independent of trade volume;
all21 absent-trade intervals retain genuine nonflat mark observations. Closed
marks alone inform strategy budgets. Observed extrema bound risk and never
fill orders. An OLD-wallet opening mark maintenance breach conservatively
forfeits collateral before a simultaneous native exit when mark/order timing
is unknown. Liquidation never recovers after favorable later marks. Sparse
mark sampling, unknown checkpoint updates/reopening fills, terminal positions,
liquidation/debt, insolvency or negative cash block historical eligibility.
Higher mark sample counts do not prove a continuous risk path. A5% UTC daily
and10% conservative account drawdown screen is not exact Prague prop-stage
replay or payout certification.

Source metadata/hashes and synthetic fixtures precede native strategy P&L.
Every native TRADE/FUNDING/MARK input is immutable; original author PDFs and
full extracted texts remain private and are checksum-bound. Role features
are constructed only through that role's exclusive end, so failed2025 does
not open2026 strategy features/P&L. Sources may be fully inspected for quality.

Fixed windows are TRAIN2024, sole validation2025 and final2026Jan–Sep if and
only if the sole validation passes. TRAIN requires unchanged common positive
base/doubled-cost performance,30episodes/60calendar days, risk/physical/source
guards and two of three fixed chronological folds positive with valid guards.
One maximum net-return/adverse-drawdown score, tiesID, is locked against all24
exact TRAIN identities before validation. No replacement, changed target or
postfailure leverage increase is permitted.

OOS keeps EIGHT_PERCENT_PROTOCOL.json unchanged: at least8% geometric monthly,
60episodes/6full months, positive99% daily mean-return7day5000bootstrap lower
bound, positive double-cost month-equivalent, median month positive, two thirds
positive months, both halves positive, plus activity/risk/cash/source gates.
Conditional daily mean confidence bounds cannot prove a future8% monthly
expectation. Full base/stress ledgers and confirmations remain immutable.
No historical result activates live orders, Telegram or prop qualification.
