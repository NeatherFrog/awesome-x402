# Frozen funding-carry protocol

Preregistered before funding strategy outcomes.

```json
{
  "version": "funding-carry-v1",
  "frozen_at": "2026-10-02T09:45:56.115016Z",
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
  "producers": {
    "propdesk/funding_lab.py": "211642137591cfb735495f2d98375ef0856e3962284d90c5df8eb517fc16aa76",
    "scripts/research_funding.py": "e91c16924ab86d9ba3d92a943611a8f7a6381ce71d3407e9cc8113d26e121998",
    "propdesk/research_stats.py": "1beee93dc5d400ccb7c4967c649c5d7b64d68a6456150ca68bdf038dd18dee16"
  },
  "hypothesis": "Positive perpetual funding may compensate a fully funded spot-long/perpetual-short hedge after both-leg friction, basis changes and isolated-margin risk. Actual realized funding is only known at settlement.",
  "previous_studies": "208 hourly spot variants failed2025 validation; eight liquidity/FVG variants lost on inspected2026Q3. Daily ETF studies and market periods previously inspected. No global blind-final claim; all seven additional variants count in the cumulative research ledger.",
  "selection": "Evaluate seven variants in2024, require positive base/doubled-cost/75%-positive-funding return,>=200 credited settlements, zero modeled liquidations,<=5% drawdown,<=2.5% daily envelope drawdown. ChooseONE by return/max(drawdown,.25), then lexicographicID. Persist selection hash BEFORE2025 simulation. No replacement if2025 fails. Persist confirmation hash BEFORE2026 simulation; never open2026 performance if validation fails.",
  "validation_final_gates": "Positive base/doubled-cost/75%-positive-funding return;>=180 full calendar days and>=6months;>=200 funding settlements; zero modeled liquidations;99%7-day block mean CI lower>0; both chronological halves positive; largest positive month share<=.5;<=5% maxdrawdown and<=2.5% daily envelope; per-asset beta absolute<=.1. Candidate remains provisional, live/propfalse.",
  "capital": "100kportfolio BTCETH50keach; each spotcash25k+isolatedperpcash25k; baseqty=min25kspotbudget/perpsafeavailablecollateral, roundeddown1e-6. Equalfixedunitsbetweenfills,<=initial25kspotnotionalperasset; market drift may change notional. No spot-profittransfer into collateral, borrow, idlecashinterest or free margin.",
  "signals": "Static alwayson benchmark. Persistence mean of3/9/21 past realized settlementrates; entry strictmean>0or.00005; exit mean<=0; decisions use only eventsstrictlybeforecurrentopen; eachdecisionfillsnextclosedbaropen. Tradecosts included; ratesnotquotedfuturefunding. Staticdisabledafterliquidation.",
  "margin": "Maintenanceproxy.5%currentperpnotional, tradeOHLCupperpriceproxy(marknotverified). Gapbreachprioritizesliquidation beforeplannedexit; intrabarbreach usesperphigh andspotlow nonsimultaneousadverseenvelope+1%perpliquidationpenalty. Persistencepriorclosedperpmarginequity<50%currentnotional reducespairedquantity50%atnextopen. No futurehigh usedforrebalancing.",
  "settlements": "Creditshortq*actualsettledrate*officialmarkwhenpresent; otherwise PRECEDING closedperptradeprice. Nevercurrent/futureclose/highasfundingmark. Newlyopenedpair mustbeheld>1minute beforeeligiblesettlement; exitatsettlementtimestamp closesbeforeevent andreceivesnopaymentafterexit. Eventratemeanupdatedafterexecution, cannotpredictsame-eventrate. MillisecondtimestampsparsedasUTCdatetime. Conservativepre-receiptperphighmargincheck liquidatespair BEFORE allfundingreceiptsifpriorcollateral insufficient; positivefundingcannotrescueanambiguous earlierhigh. Negativefundingthenanotherhighcheck. Nofundingafterliquidation.",
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
  "inference": "Dailycalendar returns includingflatdays;5000circular7dayblocks,99%CI seed20261002; inferenceapproxconditionalstationarity, noindependenceclaim. Seven adaptivevariantsandallpriorstudiesremainselectionuncertainty. Perassetregressionbeta/correlationdescriptive, notcausalproof.",
  "permissions": "PersonalnonproductionCCBYNCSAarchivalresearch; noactualaccounts/orders/purchases/Telegram/credentials. Requireverifiedlicensedproductionfeedandprospectivepaperdata beforelive."
}
```

## Accounting and interpretation

For one asset, initial capital is split into spot cash and isolated perpetual collateral. The portfolio has two equal BTC/ETH buckets. Buying spot and selling the same base quantity removes first-order base delta; it does not remove basis, collateral, default, outage or execution risk.

At a mark:

`account_equity = spot_cash + derivative_cash + q * spot_price + q * (perp_entry - perp_price)`

`isolated_margin_equity = derivative_cash + q * (perp_entry - perp_mark_proxy)`

`short_funding_payment = q * settlement_mark_proxy * actual_settled_rate`

`daily_return = daily_close_equity / previous_daily_close_equity - 1`

`market_beta = covariance(daily_account_return, daily_spot_return) / variance(daily_spot_return)`

Every paired entry/exit includes both legs' fees and adverse fills. Spot profit is unavailable to isolated margin until actually sold; the model does not transfer any spot proceeds to the derivative wallet. Positive funding is reduced25% in a separate stress, while negative funding remains fully charged. Another stress doubles all ordinary trading friction.

Signals use past realized settlements. There is no claim that the next funding rate was quoted, known or guaranteed. The1minute eligibility delay deliberately excludes ambiguous settlement receipts immediately after a modeled hourly-open fill. Conservative high-envelope liquidation happens before funding could rescue an earlier unknown intrabar breach. Closing at a settlement timestamp receives no later funding payment.

One winner is chosen on2024. Its2025 validation is then evaluated without replacement. Only a candidate passing every frozen validation gate opens2026 funding performance. Previous research already inspected the same general market periods; this is adaptive historical evidence, not a globally untouched experiment. Block bootstrap confidence intervals are conditional on the chosen dependence/stationarity model and do not certify future stability.

## Source references

- Official archive and checksum format: https://github.com/binance/binance-public-data
- Official USD-M funding settlement history API: https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-History
- Archived exact monthly source URLs and SHA256 receipts are bound by the input lock in `funding-research.json`.

These references describe sources and interfaces; this model neither verifies an account's executable tariffs nor places trades. Archive usage remains personal non-production underCC BY-NC-SA. Production requires appropriate data permission and an actual-account contract/API check.
