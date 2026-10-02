# Mark 96 V2: locked strategy rejected on 2025

Protocol SHA256: `e67fb6db565023a616a211c487a7e55aa70d48dc5b367c02f7f71a8c21858274`.

The same 96 fixed alpha/risk/cost cases were retested after an explicitly revoked V1 execution model. V2 reserves every new opening before old exit, funding, volume or mark outcomes. All previous outcomes remain immutable; this is adaptive execution correction, not 96 new independent strategies or globally blind history.

**Outcome:** one fixed TRAIN primary lost money on 2025. No alternative was substituted, no sizing changed and 2026 strategy performance remains unopened. No live orders, paper qualification, Telegram alerts or payout claim.

| TRAIN family | Cases | Net and double-cost positive | All TRAIN gates pass |
|---|---:|---:|---:|
| calendar_channel_breakout | 36 | 36 | 10 |
| calendar_ema_trend | 36 | 12 | 10 |
| fast_reversion_momentum_context | 24 | 0 | 0 |

The sole locked primary `native_trend-12db6855362d` is a five-day breakout with a two-day channel exit, using completed hourly observations on BTCUSDT/ETHUSDT perpetuals. Close above/below the preceding 120-hour high/low permits a long/short at the next genuine native opening; exit on the opposite preceding 48-hour boundary. Fixed stop is 3 previous completed daily ATR14. A completed mark stop queues an exit for a later genuine trade opening. There is no invented fixed take-profit for this trend rule.

Risk is 1% of prior known total marked equity per position, from one physical $100,000 account and isolated 2x collateral. Both old exposures stay reserved; released old collateral cannot enlarge a new same-opening order. Retrospective old-plus-new opening gross-cap evidence cannot resize or remove a trade. Fees 5 bps/side, slippage 2 bps/side and full spread 1 bp are modeled; double friction is required. These tariffs, native opening quotes, funding point marks and contractual applicability remain provisional.

| Metric | TRAIN 2024 | Locked 2025 |
|---|---:|---:|
| Net total-account return | 10.2642% | -1.5233% |
| Double-friction return | 9.0518% | -2.8331% |
| Geometric monthly equivalent | 0.8176% | -0.1278% |
| Completed episodes | 94 | 109 |
| Observed adverse peak drawdown | 6.3328% | 5.4117% |
| UTC daily loss / initial total capital | 3.7107% | 1.3188% |
| Positive full months | 7/12 | 6/12 |
| Worst full month | -1.5942% | -3.2919% |
| Full months at least 8% | 0 | 0 |

2025 mean daily return has conditional 99% seven-day/5000-block interval [-0.000474774, 0.000444210], which includes zero. The first chronological half returned -3.9306%, the second +2.5058%. Conditional inference does not remove nonstationarity or adaptive selection.

At the actual quantities/exits,2025 gross-price PnL was only$127.49; fees$881.88, adverse fill costs$440.94 and funding$-327.94 reduced it to$-1,523.28. This decomposition is an accounting identity, not a new zero-cost resized backtest. The economic failure persists even if source coverage is resolved.

The locked2025 path also held 12 sparse computed-mark asset-bars (six bars per asset on May 12) whose auxiliary counts do not establish intrabar coverage; base and stress source guards reject them. Zero modeled liquidations, unpaid deficits, cash/reconciliation errors, unknown reopening exits, terminal positions or opening gross-cap breaches were observed. Ordinary computed-mark extrema and their order still do not establish a full tick path.

**Evidence:** immutable full base/stress daily adverse/favorable curves, trades and funding ledgers are retained in `data/native-crypto-mark-v2-research/training_primary_evidence.json` and `validation_evidence.json`. The selection/results/protocol digests bind them. No validation confirmation or FINAL artifact exists because validation failed. Original V1 remains separately blocked by `retrospective-causality-audit.json`.

Independent pre-outcome review covered all 96 nonvacuous synthetic variants/468 episodes; 37 tests included 72 old-exit/new-entry contexts, 12 doubled-cost controls and 4 old-first-print controls. Final sealed evidence passed independent read-only checks of all four TRAIN/validation base/stress ledgers: 406 completed trades and 5,388 funding rows. Cash, margins, lots, both-side fees, net/funding identities, calendars and the exact conditional interval reconcile; maximum accounting error is 1.165e-9 dollars. No fresh strategy simulations or alternative OOS runs occurred. Common 8% monthly, risk, statistical and source gates were retained; exact prop-contract/payout replay and fresh forward execution evidence remain separate.
