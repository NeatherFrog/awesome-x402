# Retained TRAIN campaign dependence

Daily paths are retained for **169/808** additional configurations; **639** compact-only configurations cannot enter a correlation matrix.

This is a descriptive audit of existing arrays and registered ledger bytes. No new strategy simulation, P&L selection or qualification is performed. The previous292 and missing rows are not assigned invented returns; there is no complete1100 matrix.

| Study | Evaluated TRAIN | Retained daily configs | Cost paths |
|---|---:|---:|---:|
|pairs|48|0|0|
|pairs_close|48|0|0|
|sessions|144|0|0|
|fx|72|72|144|
|native_fvg|192|1|2|
|native_trend|96|0|0|
|native_context|48|0|0|
|metals|96|96|192|
|crypto_flow|64|0|0|

| Exact calendar | Days | Base configs | Covariance rank: base | Covariance rank: base+doublecost |
|---|---:|---:|---:|---:|
|2024-01-01 → 2025-01-01 exclusive|366|1|1.000000|1.008487|
|2024-10-03 → 2025-01-01 exclusive|90|168|11.659847|12.031516|

2024-01-01 window: **1** nonzero-variance base paths, **0** constant paths; **0** catalogue risk-sibling groups and **0** groups of exactly identical observed base-return vectors.
Median base/double-cost Pearson correlation: **0.991506**; these are scenarios of the same models.

2024-10-03 window: **168** nonzero-variance base paths, **0** constant paths; **84** catalogue risk-sibling groups and **20** groups of exactly identical observed base-return vectors.
Median base/double-cost Pearson correlation: **0.996009**; these are scenarios of the same models.
Median risk-sibling Pearson correlation: **0.999987**. All original paths remain in the matrix; no outcome-based deduplication or profit selection changes the rank.

Effective covariance rank is `trace(C)^2 / trace(C*C)` with sample covariance of daily simple TOTAL-account returns. It measures observed variance concentration and depends on risk size, fees and window. It is not a count of independent strategies/tests, a sample-size estimate, a multiplicity correction or a profitable allocation.

Pearson matrices use only identical complete date arrays. Flat days remain exactly as recorded; zero-variance correlations are null. The full2024 crypto primary is kept separate from the90-day FX/goldTRAIN window. No daily returns are recovered from monthly totals. Cost pairs and risk siblings are identified explicitly in JSON.

The one crypto daily path is the parent's originally locked TRAIN primary, not a model chosen by this audit. All other crypto/index/pair families retain compact outcome metrics only. FX/gold ledger files supply both actual modeled cost scenarios; those extra paths do not increase the economic trial count.

TRAIN paths are adaptive and some were originally selected; this is not independent heldout inference.
Correlation and effective covariance rank do not determine independent trials, adjust p-values or resurrect failed models.
Risk/cost replicas share economic rules and source paths; covariance rank depends on risk scales and the observed window.
Exactly matching windows are separate groups; no nonoverlapping dates, missing compact rows or unknown calendar returns are invented.
Counterfactual doubled costs are scenarios of the same models, not extra strategies.
OHLC/reference execution, missing active marks and source-use restrictions remain unchanged; observed dependence proves neither profit nor payouts.

The JSON binds each inspected report and raw/compressed ledger receipt plus daily-array fingerprints. Reproduction requires those original retained inputs; portable receipt files do not substitute raw history or ledgers.
