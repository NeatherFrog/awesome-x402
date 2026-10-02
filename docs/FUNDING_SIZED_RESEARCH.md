# Funding carry with half active capital

Status: **completed_validation_failed_final_unopened**.

Adaptive risk sizing follows the original seven-variant2024 carry study. The original study is preserved; this adds seven variants for **14 sequential funding trials**, alongside all previous research.2024 is calibration data;2025/2026 funding performance was unopened when this protocol froze. General market periods were already inspected, so no global blind-final claim applies.

Protocol SHA256: `9d9a6d768376725a860d2725919e3b497ceb2970150cf425b07f653eebc85ba7`.

Total initial account100,000USD: two25,000USD active BTC/ETH buckets plus50,000USD dormant cash. Each active bucket initially splits12,500USD spot cash and12,500USD isolated derivative collateral. Dormant cash earns zero and never rescues isolated collateral. All equity, daily returns, drawdowns and inference use the total account's actual dollar curve.

The original model, costs, causal signals, conservative liquidation ordering and every selection/confirmation gate remain unchanged. Trade-price liquidation and funding-mark proxies, unknown executable tariffs and counterparty/outage risk make every outcome provisional. Personal non-production archive usage only; live/prop qualification is false. No Telegram messages or actual orders.

The ONE locked sized candidate failed unchanged2025 gates.2026 funding outcomes remain unopened; no winner replacement.

| Variant |2024 net | Double costs |75% positive funding | Daily risk envelope | Liquidations |
| --- | ---: | ---: | ---: | ---: | ---: |
|static|+2.7863%|+2.6439%|+2.1415%|3.7669%|1|
|persist_3_0ppm|+1.3182%|+0.1102%|+0.6876%|1.9806%|0|
|persist_3_50ppm|+1.9349%|+1.3712%|+1.2991%|1.9806%|0|
|persist_9_0ppm|+1.8018%|+1.4878%|+1.2478%|1.9132%|0|
|persist_9_50ppm|+1.8111%|+1.5747%|+1.2767%|1.9132%|0|
|persist_21_0ppm|+1.7434%|+1.4405%|+1.2002%|1.9010%|0|
|persist_21_50ppm|+1.7687%|+1.5672%|+1.2492%|1.9010%|0|

The **one** training-locked candidate is `persist_3_50ppm`. Selection was persisted before validation outcomes. A failed candidate cannot be replaced.

## Validation

Total-account net **-0.269474%**, annualized -0.269474%; doubled costs -1.573777%;25% haircut to positive funding -0.528422%.

Conservative maximum drawdown 2.328368%, daily envelope 2.316399%, credited settlements 1658, modeled liquidations 0.

99%7-day circular-block interval for mean total-account daily return: [-0.00254419%, +0.00101069%]. Conditional approximate inference cannot certify future profit.

Funding income 1020.404768USD, paired price PnL -297.455990USD, fees 992.422289USD, fills 138. Accounting error -0.000000000010USD.

| Frozen check | Passed |
| --- | --- |
|positive_net|False|
|positive_double_costs|False|
|positive_reduced_funding|False|
|at_least_200_settlements|True|
|no_liquidations|True|
|max_drawdown_at_most_5pct|True|
|daily_envelope_at_most_2_5pct|True|
|at_least_180_days|True|
|at_least_6_months|True|
|block_ci99_lower_positive|False|
|both_halves_positive|False|
|positive_month_concentration_at_most_half|True|
|asset_beta_abs_at_most_point1|True|

| Month | Total-account net return |
| --- | ---: |
|2025-01|+0.149794%|
|2025-02|-0.050975%|
|2025-03|-0.256421%|
|2025-04|-0.041642%|
|2025-05|+0.058263%|
|2025-06|-0.158431%|
|2025-07|+0.176663%|
|2025-08|+0.059055%|
|2025-09|-0.055834%|
|2025-10|-0.038088%|
|2025-11|+0.003947%|
|2025-12|-0.115300%|

Retrospective **provisional** candidate: False. Live/prop qualification remains false. Every failed trial is retained in the record; no failed trade alerts are sent.

Full execution/accounting ledgers are retained locally with exact raw/compressed hashes. Compact public summaries retain daily total-account curves and monthly results; they do not redistribute the archival input data.
