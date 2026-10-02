# Photo-driven native liquidity clock-context protocol

This is a distinct, adaptive time-context hypothesis inspired by the user's
liquidity-raid/displacement/FVG photographs, including the NY lunch narrative.
FX intraday clock effects are motivation for a test; transfer to BTC/ETH
perpetuals is not assumed. Previous broad and native partial TRAIN results and
general2024–2026 history have already been seen. The study is **not globally
blind**. The existing192 native FVG study remains immutable.

## Exactly48 configurations before outcomes

Two complete decision resolutions(15m/1h), two prior liquidity lookbacks(24/72),
two displacement bodies(.6/1 priorATR), two clock contexts and three risks
(.25/.5/1% per position) give48 configurations, representing16 economic/time
contexts across3 preregistered exposures. Every setup inherits the parent's
**fixed2.5R target, expiry4 decision bars and EMA context off**. There are no
extra target, news, regime or parameter choices after results.

| Context | Known completed sweep CLOSE, local time | Confirmed signal CLOSE |
|---|---|---|
| NY lunch | Weekday, **[11:00,14:00)** America/New_York | Same local weekday/date, strictly before17:00 |
| London | Weekday, **[07:00,10:00)** Europe/London | Same local weekday/date, strictly before13:00 |

The intervals include their start and exclude their end. These are **close**
timestamps, not candle opening times. A sweep known after its confirmation is
invalid. Only a completed parent confirmation event, keyed by its UTC close,
can be filtered. Context uses timestamps only; the parent price levels, entry
zone, stop, target, invalidation and expiry remain unchanged. No price from a
later hour, daily range, future news or retrospectively assigned sentiment is
consulted. This is a crypto weekday experiment, not a London/NYSE exchange
holiday calendar claim. After admission, a pending order retains the parent's
expiry; no unregistered session flatten rule is introduced.

## Exact IANA clocks

Load `ZoneInfo.from_file` directly from the bundled, checksum-pinned TZif files;
host timezone data and handwritten DST formulas cannot affect the study.

- America/New_York: `e9ed07d7bee0c76a9d442d091ef1f01668fee7c4f26014c0a868b19fe6c18a95`.
- Europe/London: `c85495070dca42687df6a1c3ee780a27cbcb82f1844750ea6f642833a44d29b4`.

The New York file's IANA2026b provenance is documented in the bundled timezone
README. London was independently acquired for the frozen FX study and is bound
to its exact verified bytes. DST mismatch weeks between the US and UK are
retained. UTC source timestamps are preserved; source bars are never relabelled
as local opens.

## Unchanged execution and target gates

Reuse `liquidity_native.Features`, `setups` and `simulate` without editing them.
Native5m BTCUSDT/ETHUSDT perpetual candles and realized funding come from the
same checksum-verified official archive manifests. The parent protocol,
source files, context/parent producers, tests, TZif bytes and common objective
are fingerprinted before outcomes. The JSON protocol is the machine-readable
registration. Native license and executable quote limitations remain unchanged.

One actual100,000account, physical cash, separate1x isolated positions, at most
two concurrent assets, cost-inclusive risk and1x entry-gross cap are inherited.
Fee is5bps per side; modeled slippage2bps per side plus1bp full spread, with
double-friction stress. Missing/zero-volume intervals, uncertain funding
entitlement, maintenance, gap/collision ordering, margin reservations, absence
disqualification and cash reconciliation use the frozen parent implementation.
No synthetic market prices or journal trades are generated as research evidence.

Use the unchanged [8% monthly objective](EIGHT_PERCENT_PROTOCOL.md), JSON file
SHA256 `5495a0683efeb6da230cf454b71c8e8ae952dc03534d23f3cedbcd9f56e9e839`:

1. TRAIN2024: all48 base/double-cost variants, positive net and stressed net,
   at least30 completed episodes and60calendar days, adverseDD≤10%, referenced
   daily loss≤5% initial total capital. Both scenarios additionally require zero
   liquidation, deficit and unresolved held absent-trade exposure, plus account
   reconciliation error<1e-7.
2. Select one passing maximumTRAIN net/adverse-DD-floor score, with lexicalID
   tie. Persist selection before2025. No passing TRAIN means all OOS performance
   remains unopened; a failed diagnostic is never substituted.
3. VALIDATION2025: only that primary, common8% geometric monthly equivalent,
   six full months,60episodes, conditional99%daily7day-block mean lower>0,
   positive doubled costs/median month,≥2/3positive months, both halves positive
   and unchanged risk/execution gates. Failure leaves2026 unopened.
4. FINAL2026Jan–Sep: one identical primary, only after an immutable passing
   validation-confirmation lock. No alternate OOS winner or resizing. The
   bootstrap seed is20261002 for every period/configuration,5000resamples;
   uncertainty remains conditional on stationarity and does not remove selection.

Immediately before FINAL, require equality and digests for the persisted
TRAIN-selection and validation-confirmation files, the passing validation result,
selected ID, training results and protocol identity. A missing, changed or
mismatched confirmation blocks execution on fresh runs and resumed runs alike.

Before generating setups for each stage, physically truncate the parent feature
object to source bars strictly before its exclusive end and exclude later
funding outcomes. Preserve settlement exactly at the boundary because the
unchanged parent conservatively includes possible debits there. Warm features
use earlier visible bars, not post-window prices.

Full selected-primary ledgers are saved in a separate local gzip directory with
fingerprints; compact results retain every failed TRAIN candidate. A historical
pass is provisional, **never a future-profit, prop-payout or API-execution
permission**. Actual broker bid/ask/marks/specifications, source-use rights,
contract/stage risk replay and genuinely new forward observation remain separate.
This driver has no exchange order or Telegram sender.
