# Spot/perpetual funding carry research

Status: **completed_no_training_candidate_final_unopened**.

Seven bounded variants: one static benchmark and six realized-funding-persistence variants. New economic hypothesis after208 hourly spot variants failed2025 validation; this is additional adaptive research, not an untouched global holdout.

Frozen protocol SHA256: `70afef903117b3b1421602055421e0f8f6b55d1dbcbc66a6f8f6e6c9746163c1`.

One100,000USD portfolio, two50,000USD asset buckets. Each holds25,000USD spot cash and25,000USD isolated perpetual collateral initially. Equal base units long spot/short perpetual. Spot unrealized profit is not collateral and no hidden cash transfer occurs.

Spot10bp/side, perpetual5bp/side, slippage2bp/side and full spread1bp are modeling assumptions, not verified account tariffs. Trade OHLC is not liquidation mark OHLC. Missing funding mark prices use preceding closed perpetual trade price. Every result is provisional, unsuitable for live execution/prop qualification.

CC BY-NC-SA archive data is used only for personal non-production analysis; this is not production-data licensing. No exchange orders, real account, payouts or Telegram messages are created.

No funding variant passed frozen2024 gates.2025/2026 outcomes remain unopened.

| Variant |2024 net | Double costs |75% positive funding | Liquidations |
| --- | ---: | ---: | ---: | ---: |
|static|+5.5727%|+5.2878%|+4.2831%|1|
|persist_3_0ppm|+2.6365%|+0.2204%|+1.3752%|0|
|persist_3_50ppm|+3.8698%|+2.7423%|+2.5981%|0|
|persist_9_0ppm|+3.6036%|+2.9756%|+2.4956%|0|
|persist_9_50ppm|+3.6223%|+3.1495%|+2.5533%|0|
|persist_21_0ppm|+3.4868%|+2.8809%|+2.4003%|0|
|persist_21_50ppm|+3.5375%|+3.1344%|+2.4984%|0|

Retrospective provisional candidate: **False**. Live/prop qualification: **false**.

Funding settlement count is not an independent trade sample. Correlated days, changing regimes, venue default/counterparty/outage risk and imperfect marks limit the evidence. Forward observation and official executable account data remain required. No alternative replaces a failed locked candidate.

## Observed outcome and limits

All seven registered2024 variants were fully evaluated. No candidate passed every frozen gate, so neither2025 validation nor2026 funding outcomes were opened. This is an observed training result, not a validated strategy or a notification-ready signal.

Six persistence variants earned positive2024 modeled net return and remained positive under both separate stresses, with zero modeled liquidation. Their conservative daily spot-low/perpetual-high equity envelopes exceeded the frozen2.5% daily limit. Those extrema need not occur together; this intentionally pessimistic envelope does not establish an actual contemporaneous account loss. Conversely, trade OHLC cannot establish actual liquidation-mark safety. We retain the failed risk gate rather than silently changing it after results.

The highest training return among persistence variants was `persist_3_50ppm`: mean of the last3 actual funding events must exceed0.00005 before entry; a nonpositive realized mean exits. It produced+3.8697919558%2024 net,+2.7423087390% with doubled ordinary friction,+2.5981217457% with positive funding receipts reduced25%. Funding income was4996.5672434USD, fees840.5873072USD, paired price PnL−286.1879804USD on100,000USD initial total capital. Its conservative drawdown was4.0214769528%, daily envelope3.9613293516%, and no modeled liquidation occurred. The99% block interval for mean daily account return was[+0.0055604880%,+0.0156058977%]. This is the highest observed TRAIN result, not a selected recommendation.

The static hedge earned+5.5726689127%2024 but suffered one modeled isolated-short liquidation, so it fails independently of its positive return. Unrealized spot gains were not used to rescue the short's collateral. Reducing exposure could reduce envelope risk, but doing so would be a new, explicitly adaptive protocol with the original failure preserved; it cannot retroactively qualify this study.

Every actual funding mark was absent in the archive and modeled with the preceding closed perpetual trade price. Complete inputs contain24,096 matched hourly prices and3012 actual settlement events per asset, acquired in official archive run36991406076. Source checksums and complete-calendar receipts were verified. The accounting reconciliation error of every training asset/stress run was below0.0000001USD.

Monthly TRAIN account returns for `persist_3_50ppm`:

| Month | Return |
| --- | ---: |
|2024-01|+0.494628%|
|2024-02|+0.500833%|
|2024-03|+1.243308%|
|2024-04|+0.215497%|
|2024-05|+0.162429%|
|2024-06|+0.353130%|
|2024-07|+0.146668%|
|2024-08|-0.227878%|
|2024-09|-0.077048%|
|2024-10|+0.237164%|
|2024-11|+0.395072%|
|2024-12|+0.366235%|

Input lock SHA256: `ebf60bba392a9ef3a766e499753428e82e7a511f88cb33dc435e7b3de5e5fa71`. Source paths and exact JSONSHA256 are retained in the machine-readable report. No next-year alternative winner was substituted.
