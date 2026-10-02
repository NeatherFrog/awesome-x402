# Relative-value perpetual-pair research

Phase: **completed_no_training_candidate**.

Protocol SHA256: `f1d7189ee6ad5ac58f780d2a0a948a6b65277fb3162313463d53805cb3c7cff5`.

48 fixed BTCETH log-price residual variants; all2024–2026 market history has already been inspected generally. Adaptive exploratory study, no blind-history claim.

Both actual USD-M perpetual legs, historical funding,5bps/side fees+2bps adverse slippage+1bp full spread. Mark-price/maintenance/quantity assumptions remain provisional; no live or prop payout certification.

Training variants: 48; common TRAIN survivors: 0.

No relative-value variant passed frozen TRAIN cost/risk/activity/CV requirements;2025 and2026 strategyperformance remainunopened bythisstudy. No substitute orrescaling.

No winner substitution or rescaling after validation/final failure.8% monthly equivalent is not a guarantee of8% each month, a withdrawal or a payout. Telegram/exchange execution remain disabled.

## Actual bounded result

All48 variants failed the common TRAIN cost/risk/CV screen. The primary isnull; neither2025 nor2026 strategyperformance was opened. The exact priorstudies and allfrozenproducerhashes remain unchanged.

The least-negative training variant was `relative_value-e07c517c6e63`: return-66.4815%, doublecost-75.6438%, completedpairs161, PF0.07294, modeledfees$8266.20, fundingPNL$31.44. It had no modeledliquidations or unfundeddeficit, and still failed positive-return/drawdown/daily-loss/fold gates. This is a rejected hypothesis, not a trade recommendation.

Reported stop returns are conservative bounds using each leg's adverse hourly endpoints. Those endpoints need not occur together. The extreme losses therefore **must not be presented as exact realizable market execution losses**, or as proof that every relative-value approach fails. Finer synchronized derivatives/mark data and a separately registered protocol would be needed to narrow that execution uncertainty; the existing result cannot be silently recalculated with favorable assumptions.

Training-only residual summaries: AR1phi0.9812/0.9907/0.9947, approximatehalflife36.6/74.1/131.4hours for168/336/720hourwindows; Hurstvariogram0.454/0.486/0.481. Rolling regression can itself induce apparent residualstationarity. These descriptive quantities do not support a fast, stable cointegration edge or an8%-monthly payout claim.

Funding attribution uses actual millisecondtimestamp eligibility and never finances an earlier order. Gap and intrabar liquidation cannot be rescued by later credits; both baseline and doubledcost liquidation/debt guards are mandatory. No Telegram messages, exchange executions or prop withdrawals occurred.
