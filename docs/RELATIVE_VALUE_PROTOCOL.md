# Relative-value BTCETH perpetual research protocol

This new economic family tests mean reversion of relative prices rather than
directional trend or spot/perpetual carry. All2024–2026 market history has already
been inspected generally; this is adaptive exploratory research. The original
studies and producers remain unchanged. No source can be relabeled an unseen
holdout, and no final failure permits an alternative or new sizing search.

## Fixed hypotheses and source bindings

48 parameter variants: rolling log-price hedge window168/336/720hours; absolute
entry z1.5/2; exit z0/0.5; fixed initial-account risk0.25/0.5%; maximum holding
72/168hours. All variants have residual stop3.5z, allowed beta0.25–3, maximum entry
gross2x initial equity and2x isolated leverage for each physical perpetual leg.

The model is `log(BTC)=alpha+beta*log(ETH)+residual`. Rolling OLS uses previous
fullyclosed hours only. Alpha, beta and residual sigma are frozen on entry; a
later fit never retroactively changes an existing trade's hedge or exits. A
positive residual sells BTC and buys beta-scaled ETH; a negative residual does
the reverse. Hedge quantities are based on dollar sensitivity, not arbitrary
equal coin quantities.

Actual Binance USD-M BTCUSDT/ETHUSDT hourly perpetual candles and actual funding
settlements come from `.local/funding-history`. Protocol binds every canonical
file SHA256, the manifest, producer hashes, official per-source CHECKSUM receipts
and the common `docs/EIGHT_PERCENT_PROTOCOL.json` hash. Original price
fingerprints and complete source coverage are independently checked. Missing
hours or funding events cannot be imputed. Archive license is CC BY-NC-SA;
personal non-production analysis does not establish commercial data rights.

Train2024; validation2025; final January–September2026. The fixed training folds
are February–April, May–August and September–December2024. Windows start flat,
with prior history providing indicator warmup only.

## Real capital and execution assumptions

Initial **total** account equity is100,000; isolated collateral is reserved from
that same cash, never added as a second account. Both legs reserve notional/2
margin and pay entry fees. Available cash remains nonnegative. Funding and
unrealized PNL stay inside each leg wallet until closing. No margin reinjection,
unlimited financing, spot borrowing or assumed futures leverage is hidden.

For entry-direction `d`, log-spread adverse distance is
`D=(3.5+d*z_open)*sigma`. BTC dollar notional is capped at
`initial_equity*risk_fraction/D`, at total gross2x and by available collateral
plus fees. ETH notional is beta times BTC. This is a first-order log-PNL risk
approximation; fees, gaps, model drift and conservative intrabar stops can exceed
the nominal risk budget. BTC/ETH modeled quantity increments0.001 and actual
historical minnotional/precision tiers are not certified.

Each of the **four** entry/exit leg sides pays5bps fee,2bps adverse slippage and
half a1bp full spread. Fees are assumptions, not certified personal tariffs.
Double-cost stress increases all those frictions. A separate funding stress
doubles adverse settled charges and halves credits; baseline still uses actual
recorded funding outcomes.

Signals known at the prior close execute at the next open. Entry must still lie
between frozen target and stop; stale gaps outside that region cancel it.
Opening residual-stop gaps precede prior-close target/time exits. A target is
recognized only after a fullyclosed candle, never from a favorable intrabar wick.
No final-bar new entry; remaining legs close at the final close timestamp.

Intrabar two-asset spread paths cannot be recovered from hourly OHLC. An adverse
stop therefore closes at each leg's individually adverse candle endpoint with
friction, conservatively; those endpoints need not be simultaneous. Favorable
and adverse equity envelopes likewise bound uncertainty rather than claim exact
intrabar chronology. Exact execution requires finer synchronized data.

## Funding timestamp causality

Historical settlements often occur at00:00:00.002 rather than the hour exactly.
The actual timestamp is retained. An exactT settlement can charge a position
already held atT beforeT orders; a T+.002 settlement occurs **after** T orders.
An open exit avoids a later settlement. A new entry must have been held for a
fixed60seconds and therefore cannot collect that entry-hour millisecond funding.
Later realized funding never finances or selects an earlier open order.

The settlement mark price is unavailable, so its corresponding bar open is an
explicit provisional price proxy. If an intrabar residual stop or isolated
liquidation might precede a later settlement, positive credits are omitted and
adverse charges retained conservatively, with an ambiguity flag. This does not
claim an exact entitlement replay. Tests cover delayed settlement, excluded new
entries, open exits and future funding's inability to alter earlier quantities.

## Liquidation and positive funding

Maintenance0.5% and liquidation fee0.5% are explicit modeling assumptions.
Liquidation checks **before** funding credits prevent a known gap or possible
intrabar liquidation from being rescued by a later positive funding receipt.
Proxy liquidation forfeits the full affected leg collateral. Isolated wallet
marks are floored at zero; any gap beyond collateral is separately disclosed as
an unfunded deficit. Exchange insurance, mark-price tiers and actual liquidation
fills have not been verified. Zero modeled liquidations **and** zero deficits are
mandatory in both baseline and doubled-cost stress for all research eligibility, so capped unpaid economic losses cannot
create a qualified profitable strategy.

## One primary and the8%-monthly objective

Unmodified common evaluator supplies TRAIN: positive baseline/doublecost return,
adverse total drawdown<=10%, daily reference loss<=5% initial account,30 completed
pairs and60 calendar days. Two of three fixed training folds must be positive.
Choose **one** highest net-return/adverse-drawdown candidate, ID tie-breaker, and
write an immutable primary lock **before2025 performance**. No survivor means
2025/2026 strategy performance is unopened. Validation failure ends evaluation;
another variant cannot replace it. Only a validation survivor opens2026.

OOS requires geometric calendar-month equivalent>=8%, six full months,60 completed
pairs, positive99% daily-mean interval lower bound (seven-day circular blocks,
5000 resamples), positive doubledcost geometric monthly return, positive median
month, at least two thirds positive full months, both chronological halves
positive, total adverse drawdown<=10%, daily reference loss<=5% initial equity,
and zero liquidation/deficit flags. Calendar days include flat days. UTC risk
reference is a model, not the actual Prague/reset rule replay of a prop contract.

Eight-percent monthly equivalent is total compound growth normalized to elapsed
calendar months. It does not assert8% every month, an8% cash withdrawal or payout.
Conditional block inference cannot erase adaptive selection, regime changes or
limited independent observations. Execution remains provisional and live/prop
qualification remains false even if retrospective target reference screens pass.

Training-only AR1, approximate half-life and variogram Hurst summaries are
descriptive. Rolling regression can itself manufacture apparent stationarity.
Those quantities are not Engle–Granger critical values, formal cointegration
evidence or proof of a profitable residual trade.

```sh
python -m unittest tests.test_relative_value
python scripts/research_relative_value.py --freeze
python scripts/research_relative_value.py --run
```

Every variant, cost, funding event, rejection and lock remains reproducible.
There are no exchange orders, Telegram messages, challenges or claimed payouts.
