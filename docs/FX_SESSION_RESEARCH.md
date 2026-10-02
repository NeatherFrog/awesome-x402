# Asian-range / London FX research

Status: **completed_validation_failed_final_unopened**;72 preregistered configurations.

Risk .5%/1%, RR1/2,3/6h hold were selected only on training; account return is not a cash payout. Provisional Yahoo quotes and assumed friction, not actual broker executions.

| Training variant | Net period | Monthly equivalent | Double-cost monthly | Episodes | Adverse DD |
| --- | ---: | ---: | ---: | ---: | ---: |
|USDJPY_asian_breakout_0.01_1_3|+2.1652%|+0.7324%|+0.1910%|33|+2.3492%|
|USDJPY_asian_breakout_0.01_2_3|+2.1652%|+0.7324%|+0.1910%|33|+2.3492%|
|EURUSD_asian_rejection_0.01_2_6|+1.7268%|+0.5849%|-0.6196%|23|+5.2031%|
|GBPUSD_asian_rejection_0.01_2_3|+1.7067%|+0.5782%|-1.9789%|33|+8.2096%|
|USDJPY_asian_breakout_0.01_2_6|+1.3083%|+0.4438%|-0.0943%|33|+4.5951%|

Fixed selection: `{'id': 'USDJPY_asian_breakout_0.01_1_3', 'symbol': 'USDJPY', 'family': 'asian_breakout', 'risk': 0.01, 'reward_risk': 1, 'hold_hours': 3}`. No alternative replaces it.

validation: net+0.8743%; monthly equivalent+0.0726%; passedFalse.

{
  "positive_net_total_return": true,
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
  "source_spans_declared_period": true
}

No live/prop qualification or Telegram signals. Existing overlapping history and sequential decisions are disclosed;99% positive-mean CI alone does not support an8% future monthly expectation.
