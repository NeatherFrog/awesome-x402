# Frozen half-active-capital carry protocol

Original study and gates preserved. Risk calibration uses known2024 results; later funding performance is not yet evaluated.

```json
{
  "version": "funding-half-active-v1",
  "frozen_at": "2026-10-02T09:52:03.410938Z",
  "lineage_protocol_sha256": "70afef903117b3b1421602055421e0f8f6b55d1dbcbc66a6f8f6e6c9746163c1",
  "lineage_report_sha256": "44e24a04a4f1eb42183d33dad7a6829d974ca1c26969caf33463dd6cd88632b5",
  "producers": {
    "propdesk/funding_lab.py": "211642137591cfb735495f2d98375ef0856e3962284d90c5df8eb517fc16aa76",
    "scripts/research_funding.py": "e91c16924ab86d9ba3d92a943611a8f7a6381ce71d3407e9cc8113d26e121998",
    "propdesk/research_stats.py": "1beee93dc5d400ccb7c4967c649c5d7b64d68a6456150ca68bdf038dd18dee16",
    "propdesk/funding_sized.py": "11921dda2abac16c809111e99b612ae53abaa039220eafb3079810ed9c098a0c",
    "scripts/research_funding_sized.py": "d1ef0c68a2adddb14e43b1aa7cff0459f93d84bcaef990e5906b0d3d8ed8ba00"
  },
  "windows": {
    "training": [
      "2024-01-01T00:00:00Z",
      "2025-01-01T00:00:00Z"
    ],
    "validation": [
      "2025-01-01T00:00:00Z",
      "2026-01-01T00:00:00Z"
    ],
    "final": [
      "2026-01-01T00:00:00Z",
      "2026-10-01T00:00:00Z"
    ]
  },
  "variants": [
    {
      "id": "static",
      "lookback": 0,
      "entry_rate": 0.0,
      "margin_reduction": false
    },
    {
      "id": "persist_3_0ppm",
      "lookback": 3,
      "entry_rate": 0.0,
      "margin_reduction": true
    },
    {
      "id": "persist_3_50ppm",
      "lookback": 3,
      "entry_rate": 5e-05,
      "margin_reduction": true
    },
    {
      "id": "persist_9_0ppm",
      "lookback": 9,
      "entry_rate": 0.0,
      "margin_reduction": true
    },
    {
      "id": "persist_9_50ppm",
      "lookback": 9,
      "entry_rate": 5e-05,
      "margin_reduction": true
    },
    {
      "id": "persist_21_0ppm",
      "lookback": 21,
      "entry_rate": 0.0,
      "margin_reduction": true
    },
    {
      "id": "persist_21_50ppm",
      "lookback": 21,
      "entry_rate": 5e-05,
      "margin_reduction": true
    }
  ],
  "cases": {
    "base": [
      1.0,
      1.0
    ],
    "cost_stress": [
      2.0,
      1.0
    ],
    "funding_stress": [
      1.0,
      0.75
    ]
  },
  "trial_accounting": "Seven prior funding variants plus seven newly sized variants equals14 sequential funding trials. All other prior trading research remains additional selection history.",
  "calibration": "Original2024 persistence variants earned positive net/stressed returns but exceeded the frozen2.5% daily conservative equity envelope. Halve active capital while leaving the other half dormant.2024 outcomes are known calibration data, never confirmatory evidence.2025/2026 funding performance remains unopened until the one-candidate locks below.",
  "capital": {
    "total_account": 100000,
    "btc_active": 25000,
    "eth_active": 25000,
    "dormant_cash": 50000,
    "active_asset_spot_cash": 12500,
    "active_asset_isolated_derivative_cash": 12500,
    "dormant_cash_interest": 0,
    "dormant_cash_can_rescue_margin": false
  },
  "arithmetic": "At each calendar close and conservative worst mark, total equity is50000 idle cash plus BTC/ETH actual active dollar equity. Compute daily percentage returns from successive TOTAL equity; never halve active percentages or treat dormant cash as profit/collateral. Recompute bootstrap/monthly/concentration/half-period statistics on total equity.",
  "selection": "Evaluate seven variants in2024, require positive base/doubled-cost/75%-positive-funding return,>=200 credited settlements, zero modeled liquidations,<=5% drawdown,<=2.5% daily envelope drawdown. ChooseONE by return/max(drawdown,.25), then lexicographicID. Persist selection hash BEFORE2025 simulation. No replacement if2025 fails. Persist confirmation hash BEFORE2026 simulation; never open2026 performance if validation fails.",
  "validation_final_gates": "Positive base/doubled-cost/75%-positive-funding return;>=180 full calendar days and>=6months;>=200 funding settlements; zero modeled liquidations;99%7-day block mean CI lower>0; both chronological halves positive; largest positive month share<=.5;<=5% maxdrawdown and<=2.5% daily envelope; per-asset beta absolute<=.1. Candidate remains provisional, live/propfalse.",
  "execution_signals_funding_margin": "Reuse original frozen funding_lab.simulate unchanged, capital25000 per asset only. Every signal, fee, separate wallet, pre-settlement liquidation check,1minute settlement entitlement delay, previous-closed-price mark proxy and sample-boundary hypothetical liquidation remains unchanged.",
  "selection_procedure": "Complete exact seven-variant2024 grid; choose ONE survivor by total return/max(total worst drawdown,.25), lexicographicID ties. Persist immutable training selection hash before ANY2025 simulation. If2025 fails any frozen gate, do not open2026 and never replace the winner. Persist immutable validation confirmation before the single2026 evaluation. No changes to gates after outcomes.",
  "inference": "Dailycalendar returns includingflatdays;5000circular7dayblocks,99%CI seed20261002; inferenceapproxconditionalstationarity, noindependenceclaim. Seven adaptivevariantsandallpriorstudiesremainselectionuncertainty. Perassetregressionbeta/correlationdescriptive, notcausalproof.",
  "friction": {
    "spot_fee_bps": 10,
    "perp_fee_bps": 5,
    "slippage_bps": 2,
    "full_spread_bps": 1,
    "stress_multiplier": 2,
    "positive_funding_stress_multiplier": 0.75,
    "negative_funding_stress": "Unchanged; no loss discount",
    "status": "Illustrative conservative assumptions, notverified tariffs/filters"
  },
  "data": "SamevenueofficialBinancespot1h andUSD-Mperpetual1h closedcandles full2024Jan\u20132026Sep; fundingsettlementarchive actualrates/intervals. ImmutableSHA256receiptsandchecksums required. Allhourlytimestampsmustmatch; no gaps/imputation/date deletion. Knownfundingintervalschecksettlementgaps. NullintervalallowedonlyverifiedexhaustiveofficialRESTpaginationreceipt; expectedintervalunknownrecorded, neverinvent8h or missingrate. Finalboundarypositionsclosedhypothetically, noentrylastbar.",
  "permissions": "PersonalnonproductionCCBYNCSAarchivalresearch; noactualaccounts/orders/purchases/Telegram/credentials. Requireverifiedlicensedproductionfeedandprospectivepaperdata beforelive.",
  "limitations": "Adaptive capital calibration, imperfect funding/liquidation marks, actual current/historical account fees and filters unverified, counterparty/default/outage risks not quantified. Passing means a historical provisional candidate for further investigation, not stable future profit, live/prop suitability or Telegram production authorization."
}
```
