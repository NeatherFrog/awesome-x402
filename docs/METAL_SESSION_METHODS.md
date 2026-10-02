# Gold-session hypotheses, before native outcomes

This study adds 96 explicitly registered gold hypotheses. It does not reproduce
an author's reported return or certify a prop-firm payout. The native MGC price
history has not been used for strategy P&L before these rules, synthetic tests,
source audit and immutable freeze. Earlier market studies remain part of the
adaptive research history; these periods are not globally unseen observations.

## Source identity and executable units

The unchanged acquisition record is
`data/prop-data/fx-2026-10-02T10-40-40Z/manifest.json`, SHA-256
`62bb29793c2f5ffb8d0b4b63a3c2f75027d9d0b5808f21bb4e97996d63fb2d43`.
Its `MGC=F` source is Yahoo's public, unofficial continuous micro-gold futures
reference, quoted in USD: 11,464 bars from 2024-10-02 10:00 UTC through
2026-10-02 09:00 UTC. Timestamps identify openings of requested hourly bars.
The immutable native JSON SHA-256 is
`35822acf991337ef7e267f3ac7f1cb6704e4bcb2e74aeeb706d5bca587f8e789`;
the CSV SHA-256 is
`facff3c5b9c924a9325d3c8d28f52085bc0e04ef91483c325171a60e5a43d28a`.
The canonical OHLC fingerprint is
`38c18b3fa654cf757f5448f1a77a2657815e712280a8fd8844bdd6d9486d0650`.

Current FTMO metadata was retrieved from
<https://ftmo.com/wp-json/ftmo/symbols> and retained privately at
`.local/prop-research/2026-10-02T10-37-13Z/ftmo_public_symbols.raw`, SHA-256
`166e40fe629ff0e0d9e32713e3e0cfa09fafe2ae15174763e140dcc6f4d95aea`.
The actual `XAU/USD` row says `Metals CFD`, 100 units per lot, USD profit
currency, Swing leverage 15, maximum trade volume 100 lots, `commission=0.0014`
and `commissionType=percent`. It does **not** publish minimum lot or lot step.
Two quote digits do not independently establish an executable tick-size rule.

The model interprets the futures price as USD per gold ounce and quantities as
modeled XAU/USD ounces. It never treats those quantities as MGC contract counts.
The 0.01-lot/one-ounce minimum and step are explicit unverified assumptions.
Actual historical broker bid/ask, continuous-futures rollover, holiday and
maintenance calendars, historical leverage/commissions, margin stop-out and
venue execution are unavailable. Passing these proxy tests cannot establish
prop or live eligibility.

## Causal economic hypotheses

London's prior range uses completed bars opening at 00, 01, 02, 03, 04 and 05
in London. Signal bars open at 07, 08 or 09; orders execute at the next nominal
hourly opening. New York's prior range uses 08, 09 and 10; signals open at
11, 12 or 13. London positions must be flat by 15:00 London and US positions
by 16:00 New York. Repository-pinned London/New York TZif files are loaded
directly, including their respective daylight-saving transitions.

Let `A` be the average true range of the previous 14 completed, observed
whole-hour bars; the signal bar is excluded. For previous observed close `C`,
true range is `max(H−L, |H−C|, |L−C|)`. Let `Rhi,Rlo` be the completed prior
range. Require `0.5 A ≤ Rhi−Rlo ≤ 6 A`.

* **Breakout:** a signal close above `Rhi` selects a long; below `Rlo` selects
  a short. The stop is the opposite range edge extended by `0.1 A`.
* **Rejection:** a high above `Rhi+0.05 A` followed by a close strictly inside
  the range selects a short; a low below `Rlo−0.05 A` selects a long.
  Simultaneous upper/lower raids are rejected. The stop is the signal extreme
  extended outward by `0.1 A`.
* **Drift continuation:** only the first signal hour is eligible. The last
  range close minus the first range open must exceed `0.5 A` in magnitude.
  Its sign determines direction; the stop is one `A` beyond the signal close.

The optional trend context requires the direction to agree with the previous
completed close minus the average of the previous 24 completed closes. This
is a price-history filter; it does not claim knowledge of news or sentiment.

The fixed Cartesian catalog is two sessions × three families × two context
filters × risk 0.5%/1% × gross-price reward/risk 1/2 × maximum holding 3/6 hours
= 96 configurations. One actual modeled entry is permitted per chosen local
session date. Entry invalidation is rechecked at the observed opening; no order
is entered beyond its known stop. A decision is timestamped independently of
whether the future execution quote exists.

## Cash, margin and costs

Initial total modeled equity is USD 100,000. For gold quantity `q` ounces,
direction `s∈{−1,+1}`, entry `Pe` and exit `Px`, price P&L is
`q s(Px−Pe)`. Reserved initial margin is `q Pe/15`, within existing equity.
The published percentage becomes `0.0014/100 = 0.000014` of each actual modeled
fill notional, conservatively charged on **each side** because side/round-trip
semantics are not independently verified. This is a current-spec historical
reference assumption, not a historical fee series.

Modeled full spread is USD 0.40 per ounce and adverse slippage USD 0.10 per
ounce per side. Entry adds and exit subtracts `s×0.30`. Stop-risk sizing includes
both fill frictions and entry/exit commissions. Quantity is floored to one
ounce, capped at 10,000 ounces, and constrained so reserved margin plus entry
commission fits available total cash. Margin is not added to capital.

Double-cost stress doubles the commission, spread and slippage, recomputing
sizes and fills. It is not a deduction from an unchanged winning ledger.
Risk marks include estimated liquidation costs and use conservative full-bar
high/low envelopes; their chronology, including extrema after an intrabar
exit, is not asserted as an observed broker equity path.

Known opening stop gaps execute at the actual adverse opening. A known opening
target takes precedence over later unknown OHLC extrema, without favorable
gap improvement. When stop and target are reached within a bar whose order is
unknown, the stop executes first. Intrabar execution intervals remain explicit.
Time exits use scheduled nominal closes, an additional proxy execution assumption.

## Missing observations and inferential stopping

The raw source contains 20 nonaligned `:30` observations on five holiday or
half-day dates. Those observations are retained and hashed. They do not become
hourly ATR, trend or range inputs, and no entire date is discarded because a
later partial observation exists. An exposed missing/nonaligned interval exits
at the next observed opening and blocks qualification. A later `:30` marker
also flags an overlapping prior nominal-hour exposure interval even if its
stop or target had already been modeled as an intrabar exit. Future window
completeness is a source diagnostic, never an entry filter.

TRAIN covers 2024-10-03 through 2024-12-31; validation is calendar 2025; final
is 2026-01-01 through 2026-09-30. Period returns include every calendar day.
The existing common eight-percent protocol and all its thresholds remain
unchanged. Generic UTC daily-risk and peak-drawdown checks are research
screens; exact FTMO Prague balance/stage/payout rules are a separate requirement.

Exactly one primary is selected from all 96 TRAIN identities by the existing
net-return/adverse-drawdown score, with deterministic ID ties. Its selection
binds the protocol, every TRAIN result and private compressed execution ledger.
Failed validation ends this study with final outcomes unopened. Passing
validation requires an immutable same-primary confirmation before one final
evaluation. Missing claimed locks, changed producer/input hashes, changed
ledgers, replacement primaries and changed confirmation are refused.

A historical 8% monthly equivalent is an average, not a claim of 8% every
month. Positive mean-return confidence intervals do not prove a future 8%
expectation. No live orders, prop qualification or Telegram alerts are enabled
by this study, including if the historical target passes.
