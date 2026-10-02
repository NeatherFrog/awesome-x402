# Final independent research audit — 2026-10-02

**Outcome: no strategy qualifies.** The evidence board contains 292 completed
parameter configurations across seven preserved studies. These are correlated,
adaptively explored configurations, not 292 independent discoveries. Earlier
research is additional selection history. All seven board protocol/producer
checks passed at this audit; no paper primary, live orders or Telegram trading
signals are enabled.

This audit read existing outcomes and recomputed accounting/statistics. It did
not test another strategy or select an alternative using the final period.

## Audited final carry construction

The fixed static BTC/ETH spot-long/perpetual-short model uses two physical
$50,000 asset buckets. Its fixed spot fraction is
`min(.2, .2*(1.5/3.0186020214986176)) = .09938375375865606`; remaining capital is
isolated derivative collateral. The formula uses the preserved 2024 training
risk envelope, rather than validation/final outcomes. There is no additional
idle capital, interest income or transfer of spot gains into collateral.

| Period / scenario | Total account return |
| --- | ---: |
| 2024 training | +1.823768% |
| 2025 confirmation | +0.483292% |
| January–September 2026 final | +0.114545% |
| Final with doubled friction | +0.076163% |
| Final with positive funding reduced 25% | +0.057895% |
| First final chronological half | −0.005923736% |
| Second final chronological half | +0.120475809% |

The final 99% seven-day circular-block percentile interval for **mean daily**
account return is **[−0.000071985%, +0.000842495%]**. This is not an interval for
total return. Its lower bound is negative, and the first half loses money.
Consequently the frozen `block_ci99_lower_positive` and `both_halves_positive`
checks fail. `phase = completed_final_failed` and
`retrospective_provisional_candidate = false` correctly retain this rejection,
despite positive full-period and cost-stressed returns.

Historical inference is conditional on dependence/stationarity assumptions and
does not account for every adaptive selection decision. Prior 2025 strategy
results and general 2026 market periods were already inspected. The carry model
also uses trade-price funding/liquidation mark proxies and assumed executable
fees, precision and maintenance margins. These limitations prevent a stable
future-profit, executable-account or prop-firm qualification claim.

## Receipt and accounting verification

The audit verified the complete frozen producer chain, protocol hash, original
input hashes, preserved predecessor-report hashes, immutable training selection
and immutable validation confirmation. The disk lock JSONs exactly match the
report objects. Recorded timestamps and local final-ledger creation times are
consistent with this order:

1. Fixed protocol and training-based sizing.
2. Training selection: `2026-10-02T10:06:16.672180Z`.
3. Validation confirmation: `2026-10-02T10:06:18.922578Z`.
4. Creation of all three final-period ledgers.

These are local execution records, not an external timestamp attestation.
The audit checked nine actual run ledgers: training, confirmation and final,
each under base costs, doubled costs and a positive-funding haircut. Both
compressed and decompressed SHA256 values match their receipts. Compact public
summaries match the retained full local ledgers.

For every ledger, each asset and the total account reconcile to within
$0.0000001:
`final equity - initial equity = funding + paired price PnL - fees - liquidation penalties`.
Every daily total dollar equity equals the sum of the two asset dollar equities.
Recomputing all nine daily 99% block intervals and monthly/concentration
summaries reproduced the recorded objects exactly.

Final base accounting is $152.313712471337 funding, −$9.053036899657 paired
price PnL and $28.715738911634 fees, with no liquidation penalty, producing
$114.544936660 approximately of net profit on $100,000. The recorded total
reconciliation residual is approximately −$0.000000000154.

| Artifact | SHA256 |
| --- | --- |
| Final calibrated protocol | `c9c0d85ddb6be7fbd9b08a54dc6dc7692eefba2bb8b373efdce6b148f6c38615` |
| Original input lock object | `ebf60bba392a9ef3a766e499753428e82e7a511f88cb33dc435e7b3de5e5fa71` |
| Training results object | `d5ccc3c1f3b55b13e1529bae522425407a8cb2cb81128beb8043bce6355e5100` |
| Training selection object | `5c13d5a8311579da47ff448880f36776ac34a6d8d78d99fb434a67061e1230df` |
| Validation results object | `54baaf427865889bc6986dc0db1f5503e5f044b3b79e1d09a4fc813339baec7b` |
| Validation confirmation object | `e821595ea6af5bfb1217f335f03c7ea3ff426a27f93c75d90515c8af7f7f289f` |
| Final report file | `a705c22248b0fbe11a2cc3400c4f95da3da089fa19bd587fd1ca843c448b99af` |
| Final base compressed ledger | `ec8f71504a0e7d71bbdaf4cb908d3d2fd473938bb05b4e3004c20e6bb774dec4` |
| Final base decompressed ledger | `c23e94f999f3714a27cf1fc63ac81ee905adf62b2d8c425043071c20d3359fa4` |

Object hashes use the producers' sorted compact JSON encoding. File hashes use
the exact file bytes. Local raw ledgers remain outside source distributions.

## Promotion guard regression audit

The original promotion guard's confirmation fallback was corrected before
delivery. Eligibility now requires the actual `validation` **and** `final`
objects, all 13 required checks present and exactly `true`, candidate flag
exactly `true`, verified protocol/producer hashes, and the exact successful
producer phase `completed_provisional_candidate`. An optional `confirmation`
object cannot override a failed final result. Even a qualifying historical
artifact enables only a paper candidate; live orders and Telegram remain off.

The three committed evidence tests passed. An independent mutation check also
rejected 109 cases covering false, missing, null and numeric check values in
both stages, absent stages, stale positive confirmation and nonpassing phases.
The real board reports `no_qualified_strategy`, 292 completed configurations,
seven verified studies and `primary = null`. No remaining P0/P1 issue was found
in the reviewed accounting, stage selection or promotion guard.

Audited evidence implementation SHA256:
`9a26577bfcf4da65d47665d834789d013821b2b838862a482a0229eafa9af520`.
