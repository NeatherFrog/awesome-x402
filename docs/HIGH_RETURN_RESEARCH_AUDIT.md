# Independent audit of the 8% monthly research campaign

Audit date: 2026-10-02 UTC. This receipt supplements
[FINAL_RESEARCH_AUDIT.md](FINAL_RESEARCH_AUDIT.md); that earlier audit and the
original frozen producers, protocols, selections and ledgers were preserved.

## Finding and actual scope

At this snapshot, nine completed new studies evaluated **808 registered TRAIN
configurations**, in addition to the earlier **292 configurations**, giving
**1,100 evaluated configurations**. None of these nine studies produced an eligible
8% monthly historical candidate. A configuration is a parameter/risk/market
choice, **not an independent discovery**. Cost stresses, asset subtests,
synthetic test fixtures and repeated selected-primary accounting checks do not
increase this count. An authentic-mark refinement study is still pending
at this snapshot and are excluded from the completed total.

| Completed study | Actual TRAIN configurations | Passing TRAIN | Subsequent primary result |
|---|---:|---:|---|
| BTC/ETH hourly pair reversion, conservative intrabar spread bound | 48 | 0 | 2025/2026 strategy results unopened |
| Same pair hypothesis, close-confirmed exit interpretation | 48 | 0 | 2025/2026 strategy results unopened |
| MES/MNQ cash-session strategies | 144 | 0 | 2025/2026 strategy results unopened |
| EURUSD/GBPUSD/USDJPY London session strategies | 72 | 4 | One TRAIN winner failed 2025; 2026 unopened |
| Native BTC/ETH liquidity sweep/displacement/FVG | 192 | 9 | One TRAIN winner failed 2025; 2026 unopened |
| Native BTC/ETH trend/channel/short-term reversion | 96 | 0 | 2025/2026 strategy results unopened |
| Native FVG with known NY lunch/London clock context | 48 | 0 | 2025/2026 strategy results unopened |
| Gold London/US session reference strategies | 96 | 4 | One TRAIN winner failed 2025; 2026 unopened |
| Native BTC/ETH aggressor-flow/absorption hypotheses | 64 | 0 | 2025/2026 strategy results unopened |

Rejection does not establish that every strategy has negative expected returns.
For example, 51 native trend configurations had positive TRAIN returns, but none
met all registered activity, risk and executable-observation gates. Conservative
independent hourly OHLC corners in the first pair study are a simultaneous
adverse bound, not an observed synchronized spread-stop path. A separate,
explicitly adaptive close-confirmed interpretation was registered before its
own outcomes; the first study was not rewritten.

No audit operation placed an order, sent a Telegram signal, selected a different
heldout winner or ran an alternative historical configuration. Every new
historical result below came from its owning study driver. This audit read
existing outputs and recomputed ledger identities and statistical summaries;
it did not perform a fresh complete replay of every historical configuration.

## Frozen target and inference limits

The common machine-readable objective is [EIGHT_PERCENT_PROTOCOL.json](EIGHT_PERCENT_PROTOCOL.json),
SHA256 `5495a0683efeb6da230cf454b71c8e8ae952dc03534d23f3cedbcd9f56e9e839`.
The unchanged `target_evaluation.py` evaluates actual TOTAL account equity,
calendar day returns including verified flat dates, doubled costs and adverse
daily envelopes. TRAIN requires positive net and stressed return, at least
30 completed episodes and 60 calendar days, at most 10% adverse drawdown and
5% referenced daily loss. OOS additionally requires at least 60 episodes,
six full months, 8% geometric calendar-month-equivalent growth, a positive
99% seven-day-block daily mean lower bound, positive median full month,
at least two-thirds positive full months, and both chronological halves positive.
Engine-specific liquidation, unpaid-deficit, missing-exposure and reconciliation
gates remain additional requirements.

For calendar-month-equivalent growth, accumulated log growth is divided by
the sum of each observed calendar day's `1 / days_in_its_month`, then transformed
with `expm1`. It is an average compound growth measure; it does not require or
promise 8% in every month. Daily risk uses initial TOTAL capital and a previous
UTC calendar close to the adverse daily envelope. It is not an actual FTMO
Prague-midnight or Topstep Chicago stage-specific compliance replay.

The moving-block percentile intervals use dependent daily returns, not a false
assumption that hundreds of individual trades are independent. They remain
conditional approximations under stationarity and the chosen block model.
Serial model selection, overlapping data, regime change and the shared BTC/ETH
exposure prevent a blanket false-discovery or future-profit guarantee. One
primary is selected using TRAIN only, then validation is a screen and final
performance is inspected only after that screen passes. Prior 2024–2026 research
and general prices have already been seen, so these are adaptive exploratory
studies, not a globally blind holdout campaign.

A lower daily mean bound above zero alone does **not** statistically establish
future monthly growth above 8%. The later separate `monthly_inference.py`
diagnostic maps a block bootstrap of daily log growth to calendar-month-equivalent
growth and explicitly tests the 8% threshold without changing frozen gates.
Its four tests passed. For the rejected 2025 FX primary, observed monthly growth
was +0.072569% and the conditional 99% monthly interval was approximately
[-0.913399%, +1.035470%], far below support for the 8% target.

## Before-outcome engine checks

The audit read the new engines and stage drivers before their own market
performance runs. Synthetic checks exercised actual entries and exits for every
registered variant, rather than passing vacuous zero-trade causality tests.

- Session strategies: all 144 portfolio configurations across both instruments;
  known closed features to next opening, integer contracts, tick rounding,
  both-side fees, daily flattening, marker exclusion, conservative collision
  ordering and actual sum of the two 50,000 capital buckets. All 26 session
  tests and the 10 common evaluator tests passed independently.
- FX: all 72 configurations; prior London range, known closes to next opening,
  cost-inclusive stop sizing, physical margin within 100,000 equity, USDJPY
  conversion at contemporaneous price, integer base-unit lots and future-prefix
  invariance. Twelve engine/driver tests passed. Source-span, receipt binding,
  ambiguous intrabar timestamps and explicit insolvency screens were fixed
  before freeze; future partial-day completeness never filtered past entries.
- Native FVG: all 192 configurations; joint pending-order quantities and capital
  reservations fixed from the same known opening equity before either asset's
  future touch, parent setup causality, physical 1x collateral/gross, lot steps,
  two-side fees, full native calendars and final cash conservation. Twenty
  engine/driver tests and the 10 common tests passed. Gap-through-entry-stop,
  opening target precedence, simultaneous sizing, absent execution and null
  insolvent geometric metrics were corrected before the market study froze.
- Native trend: all 96 configurations; prior completed-day ATR, hourly/daily
  causal aggregation, next native opening quantities, 2x isolated capital,
  lot/cash/fees, funding entitlement, missing-volume guards and prefix curves.
  Twenty-five engine tests and the 10 common tests passed. Explicit immutable
  validation-confirmation checks before final and insolvent-account handling
  were completed before freeze.
- Context study: before its own market outcomes, all 48 configurations produced synthetic
  trades while retaining the original parent's prices, stops, targets and expiry.
  Exact pinned New York/London clocks, native prefix curves, physical 100,000
  cash/gross and final PnL identities passed. Fourteen tests passed, including
  altered validation and missing confirmation rejection before final.
- Aggressor-flow study: before its own market outcomes, all 64 configurations produced synthetic
  trades from genuinely additional original quote-volume/trade-count/taker-buy
  fields. Closed signal windows, separate prior activity/impact ATR and latest
  complete hourly stop ATR, future-prefix curves, physical 100,000 cash/2x
  collateral, cost-inclusive aggregate risk and both-side fees reconciled.
  Forty engine/source/common tests passed. Exact original 3,012 funding slots,
  frozen parent/common hashes and immutable FINAL authorization checks were
  strengthened before freeze. Prior zero-volume activity/ATR references remain
  provisional; undefined current flow fractions are never assigned zero.
- Metal study: before its own market outcomes, all 96 configurations across London/US sessions,
  range families, prior-trend context, risk, target and hold produced synthetic
  trades. Ounces/100-ounce CFD lot conversion, reserved 15x margin inside the
  actual 100,000 account, cost-inclusive stop budgets, both notional commissions,
  known clocks/closed features, causal prefixes and full-calendar cash identities
  passed; 20 tests passed independently. Partial-hour markers remain source
  uncertainty, never a future whole-date entry filter. Exposed gaps/overlapping
  intervals disqualify. MGC continuous FUTURE prices remain a provisional
  XAU/USD reference, not actual CFD bid/ask or micro-futures execution proof.

Positive future funding cannot repair an earlier possible isolated liquidation.
Actual event timestamps are processed; model quantities are not chosen using a
future funding rate. Newly entered positions cannot assume immediate entitlement.
When within-bar entry or exit timing is unresolved, possible adverse funding is
retained and uncertain positive receipts are omitted. Boundary debits and source
absences are retained rather than hidden by dropping exposure dates.

### Later-discovered limitation of the rejected original native trend engine

A NEW synthetic stress case during review of the authentic-mark refinement
revealed an additional same-bar dependency in the already frozen original
`native_crypto_trend.py`: skipping BTC after examining its current five-minute
whole-bar volume releases capital before sizing ETH. With unchanged observations
and opening prices in a tight gross/margin case, changing that BTC volume to
zero changed the original ETH quantity from **997.752 to 999.75**. Whole-bar
volume is not known at its opening. Retrospective absence of fill evidence
must not enlarge another simultaneous order's earlier quantity.

The original 96 configurations all failed qualification. Their producers,
protocol, positive/negative TRAIN values and rejection locks remain unchanged;
this audit does not retroactively repair them or certify their positive PnL as
fully causal. The earlier all-96 prefix tests passed their actual tested
condition, later-bar price changes; they did not cover this same-bar
volume-dependent capital-ordering case. No historical configuration was rerun
to obtain the synthetic counterexample.

The NEW mark interpreter fixes this with joint opening intent reservations;
the same case leaves ETH quantity unchanged. The separate flow engine already
reserved both assets' cash/gross/risk before either current-volume fill check
and its explicit regression passed before its own freeze. The native FVG
engine's equivalent reservation issue had been fixed before its original
192-configuration run. Authentic marks and revised risk execution are additional
new assumptions, not permission to alter the old rejected history.

## Existing result receipts checked independently

### Native FVG primary

The report's exact ordered 192 TRAIN rows, nine passing rows and immutable
maximum-score primary selection were verified. Primary
`fvg_60_24_0.6_1.5_4_1_r0.01` was locked at
`2026-10-02T11:14:10.358073Z`, before the validation ledger's local creation
timestamp. All four existing TRAIN/validation base/double-cost gzip ledgers
matched both compressed and raw SHA256 receipts and the report's metrics/daily
arrays. Independently checked:

- final equity = 100,000 + summed net completed-trade PnL;
- net PnL = signed quantity times entry/exit price difference, minus both fees,
  plus actual modeled funding;
- funding-event and trade funding sums equal the reported funding total;
- fees and adverse fill costs equal their per-trade sums;
- daily compounded returns reconcile with final TOTAL account equity;
- quantities follow the registered lot step, collateral equals quantity times
  actual entry fill, signal precedes entry, and final reserved margin is zero.

Maximum absolute reconciliation error was **5.821e-11 account currency units**.
The complete 2025 target assessment, all 21 common/engine checks and conditional
99% interval reproduced exactly from those existing daily arrays. TRAIN net
return was +9.511863%, stressed +3.153981%. The one primary's 2025 return was
**-11.640318%**, doubled costs **-15.109409%**, monthly equivalent **-1.025987%**,
and adverse drawdown **14.442623%**. There were 52 completed trades and two
unresolved held zero-volume observations. Daily 99% mean interval was
[-0.074955%, +0.009291%]. Phase is `completed_validation_failed`; 2026 and a
passing validation-confirmation artifact remain absent.

Protocol SHA256:
`8f23bcfc5223fe191fd9d23dbe1566ad326f3733362f8733861b4e62bfbfbfdf`.
Selection-lock digest:
`5ae9b5cadc5fa5e61ee9df236559ba18e4a45f6c9aff88c7d8a9b74331246d76`.
Report SHA256 at this audit:
`767ac2b60343e1ec246166b0233d7008ae78cc4eb835fba84f9f2a774384fa2c`.

The parent's legacy shared metric `marked_hours_in_position` actually counts
five-minute curve observations. `marked_native_bars_in_position` is the correct
explicit count; dividing by 12 yields elapsed marked hours. This descriptive
label is not used by qualification. Prior zero-volume rolling extrema remain
provisional references, not verified traded liquidity.

### FX primary and clock provenance

All 146 existing FX gzip ledgers (72 TRAIN configurations times two cost
scenarios, plus the one primary's two validation scenarios) passed raw/compressed
hashes, lots, costs, contemporaneous JPY conversion, trade cash, complete daily
growth and monthly accounting checks. Maximum reconciliation error was
**1.310e-10**. The 2025 common assessment/CI reproduced exactly. One primary
`USDJPY_asian_breakout_0.01_1_3` was selected from four TRAIN survivors before
validation. Its +0.072569% monthly validation growth failed six gates, including
the 8% objective, stressed profitability, uncertainty, positive-month frequency,
both halves and active-quote continuity. Final 2026 remains unopened.

Protocol digest:
`fb67d169210a1768e44706ebdf87c7a2103b6d96d3192f6eb17e2b3959918f61`.
Report SHA256:
`5b0d7745f7d555b0bd2f471e7900e203e8adf23d45582614bf31a6c71b02dbe6`.

The host London timezone used by the frozen FX engine was checked retrospectively
against the bundled registration. Bytes were identical, SHA256
`c85495070dca42687df6a1c3ee780a27cbcb82f1844750ea6f642833a44d29b4`,
and all **36,895** source labels, UTC offsets and folds agreed. The separate
`data/fx-session-research/runtime-timezone-audit.json` receipt has SHA256
`ca035cff952f8f936d191bb7aef82177a6c798794d9c457963e7e01b71862e59`.
This is a retrospective structural check, not contemporaneous external clock
attestation. Original protocol/producer bytes were not rewritten. Future replay
must verify the actual runtime timezone bytes.

### Native trend and other completed studies

The native trend protocol, current producer/source hashes, exact ordered 96
registered rows, immutable `training_results.json` and NO-primary selection
digest were checked. All reported gate/phase combinations agreed; 2025/2026
and passing confirmation artifacts are absent. Its best TRAIN return,
+15.333615% total (+1.195917% monthly), failed daily risk and unresolved
zero-volume exposure requirements. It is not an OOS profitable strategy.
Protocol digest:
`b692184bfda6da87510f10be08620e0cef1d4af7473b10764fab66f07ba0507e`.
Selection digest:
`2fc634ca32abc7c930fcd2f6c02797c1ef59637b12eadf00d749ec8ed47c9821`.
Report SHA256:
`4867805e50ce680deded720f2b1bd58d8157c7349f7a03eb4d50f525992f153c`.

The completed futures session protocol/source locks and nine producer hashes
were checked. Its best TRAIN result was +0.249980% total but **-0.711010%** with
doubled costs; no candidate or OOS result was selected. Protocol digest
`6a44ec48585a5a88190cb60936c828073cc9e441b7d885fa1ebd32eb82359a04`.
The two pair registrations/producers/locks were checked; each contains 48 actual
TRAIN configurations and no OOS primary. Close-confirmed pair protocol digest
`d2c485a7f01990b7e9ac67a475bd5b0a676bc85f224ebc890498e96e62d7f12f`.

The context study's exact ordered 48 TRAIN rows, every check/status combination,
frozen producers/inputs and immutable NO-primary selection digest were verified.
There is no validation, final or passing confirmation artifact. Best TRAIN
base return +1.4928% became -3.4875% at doubled costs; the few positive stressed
London-hourly configurations had one episode, below registered activity gates.
Protocol digest:
`61fe7a2f66044884d4fa3d3dc7411c983bd98dd6b7044ed7db3de8954aa110ca`.
Selection digest:
`f342fc39de7fa2980f270146459a722612559d703939b5bba1887f2083f3c9f0`.
Report SHA256:
`afccffa5483938ebd2f02a5febf8d07801ea4eed29a380c271aa5a90ed299dd5`.

### Gold primary and aggressor-flow rejection

All 194 existing gold base/doubled-cost ledgers (96 TRAIN configurations times
two, plus the one primary's validation pair) were checked against compressed/raw
SHA256 receipts. Actual per-trade ounces/lot size, reserved initial margin,
entry/exit notional commissions, net trade PnL, final 100,000-account cash and
full-calendar compound growth reconciled with maximum absolute error
**1.165e-10**. The registered ordered 96 rows, four TRAIN survivors, complete
TRAIN-identity digest and sole maximum-score selection were verified. Selection
`XAUUSD_us_drift_prior_trend_0.01_1_3` was locked before validation ledger creation.
TRAIN net +2.9714% is not an OOS result. The one primary's 2025 return was
**-3.361234%**, monthly equivalent **-0.284513%**, doubled costs **-10.405492%**,
with 149 episodes, adverse drawdown **9.095191%** and referenced daily loss
**3.851247%**. All common validation gates and its conditional 99% daily mean
interval **[-0.068952%, +0.049599%]** reproduced exactly from existing ledgers.
Active quote gaps and multiple profitability/uncertainty/consistency requirements
failed. Final 2026, a confirmation and an alternate primary remain absent.

Gold protocol digest:
`b17f1b51f9f83db14e117a42fc52a256f898758926b256260217d80591364d1a`.
Selection digest:
`8a53487ca287e87be7908b7c895d9830bbdb5f2ee7fcfa01b95aaeece344a805`.
Report SHA256:
`fe7095220a0cc4bea63a8ede9dc7c819bccc3b7a636cb710504b72abe6890542`.

The flow study's current frozen parent/common/source/producer hashes, exact
ordered 64 configurations, every check/status and immutable NO-primary TRAIN
selection digest were verified. All 64 base and doubled-cost TRAIN returns were
negative. Best descriptive TRAIN return was **-3.701870%**, stressed **-7.076095%**,
with 76 completed trades. No 2025/2026 flow-strategy result or confirmation exists.
Rejected flow rows retain compact metrics and reported accounting checks, not
full raw trade ledgers: the audit did not claim an independent historical ledger
reconciliation or rerun those strategies. Its accounting implementation had
already passed the before-outcome synthetic/AST/property audits.

Flow protocol digest:
`9d5fbdc03563bc184286bfbdc7d7532954183ee33675baf4a8128f5d31b641d5`.
Selection digest:
`922a597ee71605edf1803bd220bff4e89ff515fcbe965ebbbda27970e506aa22`.
Report SHA256:
`ffa23a4f242059fbd8ab749cedcf9a2f538ba9d5d95bc7ed9555e10d4b451b07`.

Across FX, native FVG and gold, **344 existing scenario ledgers** received hash
and accounting checks. This count is separate from the 1,100 TRAIN configurations
and does not denote 344 independent profitable strategies or new complete
historical strategy replays.

Local hashes, immutable files and creation-order checks establish local artifact
consistency. They are not cryptographic external timestamps, proof that the
underlying vendor delivered every real exchange event, or a fresh independent
market replay. Public trade OHLC, modeled spread/slippage, unknown queue and
historical specification/maintenance assumptions keep execution provisional.

## Profit, payout and application promotion remain separate

The separate `prop_objective.py` payout model's 16 tests, eight embedded synthetic
scenarios and two fresh-stage lifecycle cases were independently replayed and
matched their input/result digests. The model preserves FTMO Prague reset/DST
and challenge/verification/reward distinctions; Topstep Chicago reset/EOD,
trailing floor, first payout floor, consistency windows, gross withdrawal,
split, payout caps and retained-balance accounting are separate. Unknown actual
contract clocks/fees/scaling and within-envelope DLL ordering remain disclosed.
Synthetic scenarios are not real trades, account approval or payouts.

On a nominal 100,000 account, 8% trading profit is 8,000 **before** payout splits,
fees, caps and stage limitations. At 80% it is 6,400; at 90% it is 7,200 before
further constraints. Evaluation-stage gains are not funded-account withdrawals.
Report SHA256:
`eab8f6d68c28a9547e78da97454d70a367b9345b60bb26d054a6f56dbe8b851c`.
Refreshed official-source document SHA256:
`01f3b4ef0b93679e8b44858c554f0df06527ddd7a42dd80d20d28c3151fc9597`.

The read-only campaign card reports actual completed TRAIN counts and distinguishes
reported artifacts from protocol/producer/input/selection consistency checks.
Its `replay_artifacts_verified` label does not attest a new complete backtest run.
Twenty-one API/card tests passed independently, including forged or missing inputs,
unsafe paths, staged locks, actual context/trend schemas and zero contribution
from merely registered metal/flow budgets. It always disables live orders and Telegram.
Earlier evidence promotion requires the actual validation AND final checks,
the exact passing phase and verified frozen producers; a stale passing
confirmation cannot replace a failed actual final result.

No eligible strategy or approved account execution was established by this
snapshot. Any subsequent study needs its own before-outcome registration and
audit, preserved rejected results, exact execution/contract reconciliation and
new forward observations; this receipt does not pre-approve it.
