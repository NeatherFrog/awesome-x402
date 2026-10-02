# Native perpetual sweep / displacement / FVG research

Phase: **completed_validation_failed**.

Protocol SHA256: `8f23bcfc5223fe191fd9d23dbe1566ad326f3733362f8733861b4e62bfbfbfdf`.

192 explicitly preregistered causal price-action configurations on genuine BTC/ETH perpetual5m candles. Signals use only completed15m/1h resamples; recorded entry zone, stop, target and invalidation. No retrospective pivots or spot short assumptions.

Adaptive historical study: other strategies previously inspected2024–2026 markets. No globally blind claim. Complete100kphysicalcapital; .25/.5/1%perposition and .5/1/2%aggregate stoprisk;1xisolatedmargin and1xentrygross cap; actual settlementcashflows; doublefriction stress.

TRAIN evaluated: **192/192**; eligible: **9**.

| TRAIN ID | Net % | Double costs % | Trades | Eligible |
|---|---:|---:|---:|---|
| fvg_60_24_0.6_1.5_4_1_r0.01 | +9.5119 | +3.1540 | 53 | True |
| fvg_60_24_1_2.5_4_1_r0.01 | +8.9677 | +5.8341 | 29 | False |
| fvg_60_24_1_2.5_12_1_r0.01 | +7.5409 | +4.0544 | 35 | True |
| fvg_60_24_1_1.5_4_1_r0.01 | +7.1579 | +4.1078 | 29 | False |
| fvg_60_24_1_1.5_12_1_r0.01 | +7.0721 | +3.5104 | 35 | True |

Top TRAIN rows are diagnostic only; eligibility and the immutable ONE-primary lock govern selection.

The immutable ONE-primary failed registered validation gates; no replacement or post-outcome sizing. 2026strategyperformance remains unopened.

Validation ONE-primary net **-11.6403%**, monthly equivalent **-1.0260%**, double costs **-15.1094%**, completed trades **52**, passed **False**.

Failed checks: positive_net_total_return, positive_double_cost_geometric_monthly_return, minimum_completed_episodes, max_account_drawdown_at_most_10_percent, geometric_monthly_return_at_least_8_percent, daily_mean_ci99_lower_positive, median_full_calendar_month_positive, at_least_two_thirds_full_months_positive, both_chronological_half_returns_positive, base_zero_unresolved_absent_trade_exposure, double_cost_zero_unresolved_absent_trade_exposure.

Zero-volume archive bars cannot prove fills; affected signals are excluded and any held exposure flags an unverified mark gap that disqualifies the period. Native/hourly provider differences are retained with raw source receipts.

TradeOHLC proxies official marks and assumes historical filters/maintenance/fees, uncertain intrabar funding entitlement, USDT/USD parity and queue availability. Adverse daily envelopes are conservative bounds. ArchiveCC-BY-NC-SA is personal/nonproduction research. A historical screen does not certify a prop contract, payout, future profit or licensed executable data.

No alternative substitution, after-validation scaling, exchange orders or Telegram.8%monthly equivalent is not8%everymonth or cash received. Full primary ledgers are localgzip artifacts with hashes; compact results retain all rejected variants.

The shared metric named `marked_hours_in_position` is a legacy name for counted native observations here; divide by12 for elapsed hours. `marked_native_bars_in_position` is the explicit unit. No risk/selection gate uses this diagnostic. Prior rolling extrema may retain official stale zero-volume prices; they remain provisional price references rather than proof of actual order-book liquidity. Current sweep/FVG candle omissions and held-exposure failures remain recorded.
