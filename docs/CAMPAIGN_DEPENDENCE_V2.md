# Retained TRAIN campaign dependence — version 2

Retained daily paths: **267/1096** additional configurations; **829** have no verified retained full daily path. Observed campaign total including the previous292: **1388**.

Existing TRAIN artifacts only: no simulation, winning-model selection, independent-trial estimate, p-value correction or trading admission. Cost scenarios are not extra strategies. Every date is exactly retained, including verified flat days; missing dates are never filled. The earlier CAMPAIGN_DEPENDENCE publication remains unchanged.

| Study | Evaluated TRAIN | Retained models | Cost paths | Revoked execution |
|---|---:|---:|---:|---|
|pairs|48|0|0|no known revocation in this registry|
|pairs_close|48|0|0|no known revocation in this registry|
|sessions|144|0|0|no known revocation in this registry|
|fx|72|72|144|no known revocation in this registry|
|native_fvg|192|1|2|no known revocation in this registry|
|native_trend|96|0|0|no known revocation in this registry|
|native_context|48|0|0|no known revocation in this registry|
|metals|96|96|192|no known revocation in this registry|
|crypto_flow|64|0|0|no known revocation in this registry|
|native_mark|96|1|2|yes, diagnostic only|
|native_mark_v2|96|1|2|no known revocation in this registry|
|native_noise|24|24|48|no known revocation in this registry|
|cross_sectional|72|72|144|no known revocation in this registry|

| Exact TRAIN calendar | Days | Base models | Covariance rank all | Covariance rank excluding revoked |
|---|---:|---:|---:|---:|
|2024-01-01 → 2025-01-01 exclusive|366|99|2.087648|2.075542|
|2024-10-03 → 2025-01-01 exclusive|90|168|11.659847|11.659847|

2024-01-01: 99 varying paths, 0 constant paths; 1 causal-revoked diagnostic path(s). Constant-path Pearson values are undefined, not zero.
Median base/double-cost Pearson: **0.993304**; observed repetition does not measure independent trials.

2024-10-03: 168 varying paths, 0 constant paths; 0 causal-revoked diagnostic path(s). Constant-path Pearson values are undefined, not zero.
Median base/double-cost Pearson: **0.996009**; observed repetition does not measure independent trials.
Median registered risk siblings Pearson: **0.999987**; observed repetition does not measure independent trials.

Effective covariance rank is `trace(C)^2 / trace(C*C)` of centered daily simple total-account returns, sample ddof1. It describes covariance concentration in each exact calendar window and changes with risk, costs and coverage. It is not the number of independent hypotheses, an effective sample size, a multiplicity correction or a profitable allocation.

All observed paths are retained without outcome-based deduplication. Risk siblings, identical observed vectors, cost twins and matched mark execution interpretations are labeled in JSON. The mark-V1 path has a known causal failure and appears only as explicitly blocked diagnostic data; the parallel non-revoked matrices exclude it. Other models remain unqualified as well.

TRAIN paths are adaptive and some were originally selected; this is not independent heldout inference.
Correlation and effective covariance rank do not determine independent trials, adjust p-values or resurrect failed models.
Risk/cost replicas share economic rules and source paths; covariance rank depends on risk scales and the observed window.
Exactly matching windows are separate groups; no nonoverlapping dates, missing compact rows or unknown calendar returns are invented.
Counterfactual doubled costs are scenarios of the same models, not extra strategies.
OHLC/reference execution, missing active marks and source-use restrictions remain unchanged; observed dependence proves neither profit nor payouts.
One already selected TRAIN primary is retained per mark interpretation; this audit does not search for a correlated or profitable replacement.
The known mark-V1 causal counterexample invalidates its execution interpretation. Its preserved path is a diagnostic, not causal economic evidence; non-revoked-only matrices are also reported.
The original dependence V1 publication is an immutable earlier snapshot, not overwritten by new coverage.

JSON binds report, source/producer consistency, original ledger hashes, exact date/return fingerprints and the unchanged V1 snapshot. Full-history and full-ledger availability remain explicit. Monthly totals are never converted into invented daily returns.
