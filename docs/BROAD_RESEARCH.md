# Bounded broad venue-spot research

Status: **completed_no_candidate_final_unopened**.

208 preregistered parameter variants across nine hypothesis families; these are correlated variants, not 208 independent strategies.

Frozen protocol SHA256: `ff16be1f7750f10bc00530a7b311dbaf82274fa9579e1a5855a31316f174f64e`.

BTCUSDT and ETHUSDT spot long/cash only. Training: 2024; validation: 2025; final: January–September 2026.

Fees10bps/side + slippage2bps/side + full spread1bp are conservative modeling assumptions, not verified executable venue tariffs. Fractional quantity precision is modeled, not a verified historical filter.

No funding, borrowing, short positions, leverage, prop execution, withdrawals or Telegram messages. Rejected experiments remain in the research record; they are not user-facing trade alerts.

No train-selected family finalist passed the frozen validation gates. Final2026 performance remains unopened; no winner replacement or source substitution.

Training variants evaluated: 208. Bounded family shortlist: 4.

**No candidate passed the preregistered selection gates.**

The final candidate cannot be replaced after final outcomes are opened. Historical profitability alone is not proof of stable future profit. No data-source substitution is permitted.

## Actual validation result

Official SHA256-verified spot archives yielded24,096 complete hourly bars per asset.29/208 variants passed training gates; four train-selected family finalists entered2025 validation. No finalist survived cost stress and the conditional multiplicity screen.2026 final performance remains unopened.

| Train-selected family |2025 net return | Doubled-friction return | Trades | Worst drawdown |
| --- | ---: | ---: | ---: | ---: |
| donchian | -1.0601% | -8.5015% | 136 | 8.4526% |
| ma_trend | +0.1000% | -6.1872% | 198 | 8.9107% |
| momentum | -3.7006% | -13.3529% | 311 | 8.0311% |
| volume_breakout | +2.8571% | -4.1330% | 119 | 8.1794% |

The best positive validation return, volume-confirmed breakout+2.8571%, hadPF1.1163 and became−4.1330% under doubled friction. It is rejected, not a profitable/stable recommendation. The mean208-variant daily-return pair correlation was0.43483 across21,528 pairs;36 training-only feature/forward-return correlations are preserved in the JSON ledger.

The2024 fully invested spot benchmark returned+83.3309% at modeled costs. Different strategy exposure prevents a risk-matched alpha conclusion. Positive training results during a strong market do not establish repeatable edge.

Acquisition run36990296162 and exact CSV SHA256/canonical fingerprints are bound in the input lock. The archives carryCC BY-NC-SA; this is personal non-production analysis, not a redistribution or commercial-data permission. No exchange execution, Telegram message, payout or prospective trade is claimed.
