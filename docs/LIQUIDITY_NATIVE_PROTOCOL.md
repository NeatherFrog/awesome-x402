# Native perpetual liquidity sweep / displacement / FVG study

This independent, adaptive historical study extends the frozen 8% monthly
objective. Previous strategies and generally inspected 2024–2026 markets remain
selection history; none of these years is globally blind. No old producer changes.

Before outcomes, register exactly 64 economic/time combinations: signal timeframe 15m/1h;
prior rolling liquidity 24/72 completed signal bars; middle-candle displacement
body at least 0.6/1.0 prior ATR20; reward/risk 1.5/2.5; FVG retest expiry 4/12
signal bars; prior EMA24/96 directional context disabled/enabled. Cross these with predeclared per-position
risk0.25%/0.5%/1% (aggregate0.5%/1%/2%), giving exactly192 configurations.
Risk is selected only on TRAIN and remains locked through later periods.

Source candles are genuine synchronized Binance USD-M BTCUSDT and ETHUSDT
five-minute trade OHLC, never spot shorts or synthetic interpolations. Resamples
contain every three/twelve complete native candles. A signal becomes known only
at resample close. Liquidity excludes the sweep candle; no retrospective pivots.
A sweep must pierce a prior rolling extreme and close back inside. A later
middle candle must displace in the opposite direction; a third candle must
complete the three-candle FVG. The latest unconsumed sweep expires after six
signal bars. The first subsequent midpoint retest can fill. Stop is the actual
sweep extreme plus 0.1 of ATR known before the sweep. Target is the registered
multiple of entry-to-stop distance. The entry zone, stop, target, invalidation,
confirmation and sweep times are stored. A newer confirmed setup replaces an
unfilled one; setups detected while holding that asset are discarded. Expiry is
exclusive. There is no same-bar profitable target credit after an uncertain
intrabar entry. If stop and target both touch, stop wins; gaps worsen stops.
Maximum hold is 24 hours. Sample-end liquidation is explicit and costed.

One physical 100,000-USDT account is the complete denominator. Each position
risks at most its registered0.25%/0.5%/1% of current marked equity, including modeled round-trip
friction at its stop. Combined entry stop risk is at most twice that risk (0.5%/1%/2%); at most one
position per asset/two total. Combined entry gross is at most initial account
capital; each derivative has isolated 1x collateral paid from available cash,
with entry fees also paid. No free extra margin, reinjection, spot-profit transfer
or implicit loan. Quantity step 0.001 and 0.5% maintenance / liquidation fee are
explicit unverified historical venue assumptions. Negative isolated gap deficits
are reported; any liquidation/deficit disqualifies a candidate.

Fees are 5bps taker per side, adverse slippage 2bps per side and full spread 1bp
(half on each side). All friction doubles in the stress replay. Actual historical
funding settlements retain exact timestamps and are cashflows only, never
forecasts or signal inputs. Missing official marks use the known five-minute
open proxy. Intrabar entry/exit order is unknown: positive funding requires a
position certainly held before settlement and no possibly prior exit; adverse
charges apply whenever position entitlement is possible. Negative charges precede
maintenance checks; positive credits cannot rescue a possible earlier breach.
Conservative daily best/worst envelopes may combine nonsimultaneous extremes.
They are bounds rather than a reconstructed executable intrabar path.

TRAIN 2024: all192 base and double-cost replays; common positive net/stress,
30 completed trades, 60 calendar days, conservative drawdown <=10% and reference
daily loss <=5% of initial total capital, plus no liquidation or isolated deficit.
Select ONE eligible highest net-return/max(adverse drawdown,0.25%), tie by ID,
and persist the selection before any 2025 strategy return. No replacement.
2025 validation and, only if it passes, locked 2026 Jan–Sep final use the unchanged
common target: geometric calendar-month equivalent >=8%, 60 completed episodes,
six full months, daily block-bootstrap 99% lower bound >0, positive double costs,
positive median month, >=2/3 positive months and both chronological halves
positive, plus the same risk/zero-liquidation limits. Bootstrap is the frozen
7-calendar-day circular blocks / 5,000 samples, conditional on stationarity.
Failed validation/final stops this study; no risk multiplier or alternative swap.

Each stage stores exact producer/input hashes and compact evidence; full primary
ledgers are gzip local artifacts with hashes. Independent statistical and source
audits precede protocol freeze and the first performance calculation. Archive
CC-BY-NC-SA data permits this personal historical research, not a licensed live
service. Mark prices, queue/fills, historical filters/fees, funding entitlement,
USDT/USD parity and an approved prop contract remain unverified. No exchange
orders, Telegram signals, prop purchases, withdrawal or live-profit label.

Before testing touches, both pending orders reserve quantities, cash and risk
from the known opening account in deterministic BTC/ETH order. An unfilled
reservation cannot finance another order in that interval. Known opening
resting targets exit before a later unknown intrabar stop. Exact sample-end
funding/exit ties retain adverse debits and exclude positive credits. Positive
funding requires a certainly held position for60 seconds; ambiguous possible
debits remain. Zero-volume native bars cannot prove fills: exclude affected
signal candles, retain calendar marks from the preceding traded-close proxy,
and disqualify any held absent-trade exposure. Provider-native anomalies remain
unchanged and their independent raw source audits are hash-bound.
