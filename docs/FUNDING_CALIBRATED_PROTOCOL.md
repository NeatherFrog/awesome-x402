# Frozen TRAIN-calibrated static carry protocol

Same static alpha, ONE risk allocation from known2024 only. Old studies and all gates preserved; static2025 and funding2026 outcomes remain unopened.

```json
{
  "version": "funding-static-train-risk-v1",
  "frozen_at": "2026-10-02T10:06:14.195044Z",
  "lineage_protocol_sha256": "70afef903117b3b1421602055421e0f8f6b55d1dbcbc66a6f8f6e6c9746163c1",
  "lineage_report_sha256": "44e24a04a4f1eb42183d33dad7a6829d974ca1c26969caf33463dd6cd88632b5",
  "lineage_sized_protocol_sha256": "9d9a6d768376725a860d2725919e3b497ceb2970150cf425b07f653eebc85ba7",
  "lineage_sized_report_sha256": "c0cd965d447074c20662cdd94ac314db765e84398f8be86a3a1387b8131881a5",
  "lineage_static_protocol_sha256": "672dde83bc0b7ad550f5f942be1fe7e358572efa8191caa5d2db294a74c9c981",
  "lineage_static_report_sha256": "688dd85098123bf0b2fd2636ba5364e67a18fe44a43e87b0ddeaf48ade3bada7",
  "producers": {
    "propdesk/funding_lab.py": "211642137591cfb735495f2d98375ef0856e3962284d90c5df8eb517fc16aa76",
    "scripts/research_funding.py": "e91c16924ab86d9ba3d92a943611a8f7a6381ce71d3407e9cc8113d26e121998",
    "propdesk/research_stats.py": "1beee93dc5d400ccb7c4967c649c5d7b64d68a6456150ca68bdf038dd18dee16",
    "propdesk/funding_sized.py": "11921dda2abac16c809111e99b612ae53abaa039220eafb3079810ed9c098a0c",
    "scripts/research_funding_sized.py": "d1ef0c68a2adddb14e43b1aa7cff0459f93d84bcaef990e5906b0d3d8ed8ba00",
    "propdesk/funding_static.py": "88a85628741c3a67160d48223f0229e7a1eadfe35adb6d1dcf0da6687bea6659",
    "scripts/research_funding_static.py": "f2157e935e0547e1d8692d2eafdbbfe0aaefb81f7358c045729361dd1a28535a",
    "propdesk/funding_calibrated.py": "70b02b45924ade67efa88369101894e4c367007f1c5032d149767bc19232e58c",
    "scripts/research_funding_calibrated.py": "4c9d2bf0100095e032afb4de5923cf41298236d5614298001d821f839530795d"
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
  "trial_accounting": "Seven original funding variants plus seven half-active variants plus one static allocation plus this ONE TRAIN-calibrated risk construction equals16 sequential funding configurations. The underlying static alpha is unchanged; all earlier research remains selection history.",
  "calibration": "V3 static TRAIN2024 had positive base/stressed cashflow but conservative daily envelope3.0186020214986176%, above unchanged2.5% gate. Risk manager uses only that2024 input to allocate spotfraction=min(.2,.2*(1.5/TRAINenvelope)); remaining physical cash is isolated derivative collateral. Allocation frozen before FIRST static2025 evaluation;2026 funding also unopened. Prior2025 other-strategy outcome is known, so no global blind claim. Never retry or change allocation after validation/final.",
  "risk_calibration": {
    "input_report_sha256": "688dd85098123bf0b2fd2636ba5364e67a18fe44a43e87b0ddeaf48ade3bada7",
    "input_metric": "training[0].base.max_daily_drawdown_pct",
    "input_value_pct": 3.0186020214986176,
    "target_pct": 1.5,
    "formula": "min(.2, .2*(1.5/input_value_pct))",
    "fixed_spot_fraction": 0.09938375375865606,
    "fixed_derivative_fraction": 0.900616246241344,
    "target_is_not_a_relaxed_gate": true
  },
  "capital": {
    "total_account": 100000,
    "btc_bucket": 50000,
    "eth_bucket": 50000,
    "spot_fraction_per_bucket": 0.09938375375865606,
    "derivative_fraction_per_bucket": 0.900616246241344,
    "spot_cash_per_asset": 4969.187687932803,
    "isolated_derivative_cash_per_asset": 45030.812312067195,
    "idle_external_cash": 0,
    "cash_interest": 0,
    "cross_wallet_transfers": false,
    "spot_profit_can_rescue_margin": false
  },
  "arithmetic": "At each calendar close and conservative worst mark, total equity is the sum of two physical50k asset buckets. Spotcash+derivativecash+spot market value+short unrealized PnL, with fees and actual settled funding. No extra idle capital or synthetic collateral. Compute daily/account risk/inference from successive total dollar equity.",
  "original_selection_rules_reference": "Evaluate seven variants in2024, require positive base/doubled-cost/75%-positive-funding return,>=200 credited settlements, zero modeled liquidations,<=5% drawdown,<=2.5% daily envelope drawdown. ChooseONE by return/max(drawdown,.25), then lexicographicID. Persist selection hash BEFORE2025 simulation. No replacement if2025 fails. Persist confirmation hash BEFORE2026 simulation; never open2026 performance if validation fails.",
  "validation_final_gates": "Positive base/doubled-cost/75%-positive-funding return;>=180 full calendar days and>=6months;>=200 funding settlements; zero modeled liquidations;99%7-day block mean CI lower>0; both chronological halves positive; largest positive month share<=.5;<=5% maxdrawdown and<=2.5% daily envelope; per-asset beta absolute<=.1. Candidate remains provisional, live/propfalse.",
  "execution_signals_funding_margin": "Literal copy of frozen funding_static.simulate: only fixed SPOT_FRACTION replaces.2, remaining collateral1-SPOT_FRACTION replaces.8, and entrybudgetusesSPOT_FRACTION. Constant equalbase units from next known hour; no rate exits or defensive reductions. Negative funding fully charged; both-leg fees, isolated wallets, conservative liquidation before funding,1minute settlement entitlement, previous trade-close funding mark proxy and hypothetical boundary close unchanged.",
  "selection_procedure": "EXACTLY ONE alpha/risk construction. Require original TRAIN basic gates, persist immutable one-candidate/derivedallocation before FIRST static2025 evaluation. If2025 fails any original confirmation gate STOP without2026. Ifpasses, immutable confirm hash BEFORE ONE2026 final. No candidate/exposure/gate changes after outcomes; no further risk-calibration retries.",
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
  "limitations": "TRAIN-based risk allocation is adaptive after16 sequential funding configurations and inspected2025 other-strategy failure. Static2025 and funding2026 outcome vectors were not computed at freeze;2026 market periods were inspected elsewhere. Proxy marks, executable tariffs/filters, finite margin and venue default/outages unverified. Passing requires fresh prospective evidence and does not certify stable profit/live/prop suitability."
}
```
