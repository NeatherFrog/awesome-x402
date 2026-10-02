# Completed baseline research handoff — 0.5.0

**Active continuation:** see [HIGH_RETURN_CAMPAIGN.md](HIGH_RETURN_CAMPAIGN.md).
The user reopened research with an 8% monthly objective. The preserved results
below do not end that active task; new separately preregistered families and
their actual progress are recorded in the continuation and read-only API.

The executor is available. User priority: evaluate hundreds of strategies and
statistical/correlation evidence, choose one robust strategy, **then** Telegram.
User-facing replies must remain at most 50 words. No Telegram implementation or
messages and no actual exchange orders were introduced in this session.

## Completed evidence

292 registered configurations were evaluated: 208 hourly spot variants, 64
low-turnover portfolio variants, four liquidity/FVG rules, and 16 sequential
funding constructions (including repeated alpha with different risk allocations).
These are not 292 independent discoveries. The separate quarter FVG replay has
eight asset/variant evaluations; full FVG has 24 period/asset/variant evaluations.
All prior ETF, prop-rule, eight-market and diary evidence is preserved.

**No strategy qualified.** The one fixed TRAIN-calibrated static funding hedge
returned +1.823768% in2024, +0.483292% in2025 and +0.114545% inJanuary–September2026
after modeled expenses.2025 passed all unchanged confirmation gates.2026 failed
the99% daily-mean block interval (it includes zero) and both-positive-halves rule:
first half−0.005923736%, second+0.120475809%. No other candidate replaced it, and
no size or gate was changed after final outcomes. Nominal USDT cash assumes USD
parity; trade-price marks, maintenance and tariffs are provisional. Venue default,
depeg, outages and opportunity cost are not guaranteed or eliminated by hedging.

Every other study failed training or validation. The hourly/portfolio2026 model
performance remains unopened; full FVG final results are descriptive, already
inspected and ineligible as a fresh blind test. Earlier Yahoo2026 and FVG-quarter
prices overlap, so no globally blind2026 claim applies. See
[EXPERIMENT_REGISTRY.md](EXPERIMENT_REGISTRY.md) and
[FUNDING_CALIBRATED_RESEARCH.md](FUNDING_CALIBRATED_RESEARCH.md).

## Implemented and audited

Causal liquidity engine, official spot/perpetual/funding parsers, bounded strategy
matrices, correlation/regime/uncertainty analysis, isolated-account funding
ledger, durable subscription-review queue and a read-only evidence API/UI.
`GET /api/trader/evidence` lists seven studies with checked protocol/source hashes.
Promotion requires a completed passing phase, every required validation **and**
final check, and the explicit candidate flag. Reports never enable live orders.
The primary screen says no verified strategy; old SMA/RSI/WATCH models are folded
into an optional archive. Negative experiments remain internal records, not alerts.

Official Binance checksum-verified data were acquired on this repository's
GitHub Actions runner because local proxy CONNECT403 blocked venue hosts:

- Spot original: run36990296162, branch`research-data-5c9d14d21a38`.
- Perpetual/funding: run36991406076, branch`funding-data-8a9b6d7dcd03`.
- Full spot: run36991940852, branch`research-data-623b09c49417`.

Each BTC/ETH hourly series has24,096 complete bars, each full5m series289,152;
each actual funding series3,012 events. Inputs spanJan2024–Sep2026, without gaps
or imputation. Export gzip/decoded/manifest/CSV hashes match original receipts.
Raw data and full accounting ledgers stay under`.local/`, outside packages.
Archive terms are CC-BY-NC-SA4.0 personal non-production research; live execution
needs a permitted production feed and executable contract/fee/mark verification.
Code licensing does not change data licensing.

## Subscription runtime blocker

Official CodexCLI0.159.0-alpha.3 is installed and logged in via ChatGPT. Actual
bounded execution failed before model startup: read-only filesystem. The pinned
implementation requires writing/locking the existing`CODEX_HOME/installation_id`.
Supported SQLite/log overrides did not resolve it. The durable queue is paused
`runtime_unavailable`; no model-token usage or remaining quota was reported.
Do not copy credentials, repurpose HOME/CODEX_HOME, retry unchanged startup,
or claim a24-hour worker is running. A normal local writable official installation
can be tested separately. See[RESEARCH_RUNNER.md](RESEARCH_RUNNER.md).

## Preservation and next evidence

The manual journal was backed up via SQLite before development and had0 rows.
SHA256 of its canonical empty JSON is
`4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945`.
Do not overwrite user state or redefine a historical replay as actual trading.
All producer files frozen by completed studies must remain byte-identical;
fixes require new registered versions, preserving old outcomes.

Further useful research needs a new causal hypothesis, properly permitted data,
verified executable costs/marks, a new preregistration and genuinely later
prospective observations. Reopening2026 or endlessly resizing the failed final
candidate is not new independent evidence. Telegram remains deferred by the
user's priority. No prop firm or live connection is certified by crypto carry.

Release validation and exact native package evidence are tracked in
[VALIDATION.md](VALIDATION.md). A saved cloud draft does not apply network changes,
publish a snapshot or prove fresh-task restoration.

## Portable timezone correction

The first native0.5.0 run36994215927 found a missing host IANA database before
package publication. Existing bundled IANA2026b files are now appended to stdlib
TZPATH only if the normal New York lookup fails. No frozen engine/producer/data
bytes changed. Six additional regression tests cover Windows-style import,
2024–2026 DST and lunch boundaries; independent full5m clock comparison matches
all289,152 observations. Native package smoke includes actual isolated NY lookup.
