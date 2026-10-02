# Gold-session reference research

Status: **completed_validation_failed_final_unopened**;96 configurations.

Quantities are modeled XAU/USD ounces, not MGC contracts. Continuous futures prices and assumed costs/lotstep do not certify actual FTMO trading or payouts.

| TRAIN variant | Net period | Monthly equivalent | Double-cost monthly | Episodes | Adverse DD |
| --- | ---: | ---: | ---: | ---: | ---: |
|XAUUSD_us_rejection_none_0.01_2_6|+3.5822%|+1.2062%|+0.6228%|23|+4.9381%|
|XAUUSD_us_drift_prior_trend_0.01_1_3|+2.9714%|+1.0025%|+0.0559%|38|+5.9464%|
|XAUUSD_us_drift_prior_trend_0.01_2_3|+2.7905%|+0.9420%|+0.0171%|38|+5.9474%|
|XAUUSD_us_rejection_none_0.01_2_3|+1.8914%|+0.6403%|+0.1619%|23|+5.2143%|
|XAUUSD_us_rejection_none_0.005_2_6|+1.8025%|+0.6104%|+0.3217%|23|+2.4827%|

Immutable TRAIN primary: `{'id': 'XAUUSD_us_drift_prior_trend_0.01_1_3', 'symbol': 'XAUUSD', 'session': 'us', 'family': 'drift', 'context': 'prior_trend', 'risk': 0.01, 'reward_risk': 1, 'hold_hours': 3}`. No alternative replaces it.

validation: net -3.3612%; monthly equivalent -0.2845%; passed False.

```json
{
  "positive_net_total_return": false,
  "positive_double_cost_geometric_monthly_return": false,
  "minimum_completed_episodes": true,
  "minimum_60_calendar_days": true,
  "adverse_risk_envelopes_present": true,
  "max_account_drawdown_at_most_10_percent": true,
  "max_reference_daily_loss_at_most_5_percent": true,
  "geometric_monthly_return_at_least_8_percent": false,
  "at_least_six_full_calendar_months": true,
  "daily_mean_ci99_lower_positive": false,
  "median_full_calendar_month_positive": true,
  "at_least_two_thirds_full_months_positive": false,
  "both_chronological_half_returns_positive": false,
  "no_missing_active_exposure": false,
  "source_spans_declared_period": true,
  "cash_reconciliation": true
}
```

A positive mean-return99%interval does not prove an8%future monthly expectation. Actual executable broker data, exact prop-stage replay and future forward observations remain necessary. No orders or Telegram alerts; prop/live qualification remains false.
