# Active trading research — 8% monthly objective

The user's active instruction is to keep seeking a profitable strategy under prop-firm rules. The completed 0.5.0 investigation is a preserved baseline, not a reason to stop. Replies to the user remain at most 50 words. Do not claim a profitable bot, send rejected setups to Telegram, or present historical simulated trades as actual trading.

The objective and unchanged reference screens are registered in `EIGHT_PERCENT_PROTOCOL.json` and `.md`. An 8% geometric monthly account return compounds to about 151.8% annually. It is not 8% every month or an 8% cash withdrawal. FTMO's base 80% split converts $8,000 account profit to $6,400 before other expenses; $10,000 account profit is needed for an $8,000 gross reward. Topstep has separate stage balances, drawdown floors, payout caps and qualifying-day rules. `PROP_PAYOUT_OBJECTIVE.md` records the verified arithmetic and its contractual limits.

## Completed additional experiments

| Study | Actual configurations | Outcome | Unopened performance |
| --- | ---: | --- | --- |
| Relative BTC/ETH value, conservative hourly spread stops | 48 | No TRAIN survivor; non-simultaneous OHLC corners are bounds, not actual simultaneous spread losses | 2025 and 2026 |
| Relative value, synchronized closed-hour decisions | 48 | All TRAIN gross price PnLs negative before fees/funding; no survivor | 2025 and 2026 |
| MES/MNQ late-session opening ranges, rejection and volatility release | 144 portfolio configurations | No TRAIN survivor | 2025 and 2026 |
| EUR/USD, GBP/USD, USD/JPY Asian/London rules | 72 | One fixed USD/JPY primary selected; 2025 failed, including costs and the 8% target | 2026 |
| Native BTC/ETH sweep, displacement and FVG | 192 | Nine TRAIN survivors; one locked primary: 2024 +9.5119%, double costs +3.1540%; 2025 −11.6403%, double costs −15.1094%, failed | 2026 |
| Native BTC/ETH slow momentum, price channels and regime context | 96 | No TRAIN survivor; 51 positive base/double-cost results are rejected by activity, risk or absent-trade marking gates. Twenty fail only the marking-evidence guard | 2025 and 2026 |
| Native BTC/ETH photo-motivated FVG clocks: New York lunch and London | 48 | No TRAIN survivor; best base +1.4928% in 2024 becomes −3.4875% at double costs. The best stressed positive case has just one episode | 2025 and 2026 |
| Gold Asian/US ranges, drift and rejection | 96 | Four TRAIN survivors; one locked US drift/prior-trend primary failed 2025: −3.3612% net, −0.2845% monthly equivalent, 149 episodes and unresolved active-source gaps | 2026 |
| Native BTC/ETH taker-flow persistence and exhaustion | 64 | Every TRAIN base result negative; best −3.7019%, double costs −7.0761%, 76 episodes. No TRAIN survivor | 2025 and 2026 |

The current completed count is **1,100 = 292 previous + 808 additional configurations across nine studies**. This counts repeated economic ideas, execution interpretations and risk versions, not 1,100 independent discoveries. Individual assets and doubled-cost scenarios are not extra strategies. The 96 gold-session and 64 aggressor-flow runs now have actual completed TRAIN rows and locked outcomes. Any later mark-refinement study must be separately registered after authentic marks are available; it has no completed count here.

No additional family has passed the complete objective. The native trend maximum +15.334% annual TRAIN result is an unselected diagnostic (about +1.196% monthly); its 5.766% reference daily loss and missing marking evidence block qualification. Evidence insufficiency does not prove negative alpha, but it does prevent promotion. The clock-context study's best +1.4928% annual result is about +0.1236% monthly and fails doubled costs. Neither is an 8% monthly or payout result.

Each study freezes its inputs, producer files, hypotheses, costs and risk catalogue before computing its returns. All TRAIN variants run; one eligible maximum net-return/adverse-drawdown score wins with a deterministic tie-break. Its selection is written before 2025. A failed primary is never replaced. A passing validation is confirmed before the single 2026 evaluation; failure stops that family's held-out sequence. Previously inspected market history and adaptive research are disclosed; these are not globally blind datasets.

## Data and execution evidence

Authentic official Binance USD-M BTC/ETH five-minute histories cover January 2024 through September 2026, each with 289,152 timestamps. All 66 monthly archives have independently checked adjacent SHA-256 receipts. The native five-minute prices are not substituted spot prices. Actual funding events retain milliseconds and their position-entitlement chronology. The raw archive contains 21 zero-volume flat records per asset; absent-trade intervals do not prove fills. New engines flag held exposure and exclude affected signals. One hourly versus five-minute provider inconsistency is preserved and explained in `PERP_RESOLUTION_SOURCES.md`.

Yahoo FX/metals history starts in October 2024. Its public unofficial prices are research proxies, not broker bid/ask or a certified calendar. Missing bars are reported, not invented. New snapshots revise some previously shared candles and therefore are not independent forward observations. Native timezone files and actual runtime equivalence are audited; frozen research clocks should use pinned IANA files directly.

Capital is physical total account equity, including reserved margin and fees. No extra cash, collateral rescue or favorable simultaneous-bar ordering is invented. Stops win ambiguous intrabar stop/target cases; fills, gap prices, funding, missing execution intervals and exit-time precision are explicit. Margin tiers, official mark paths, queue execution, historical broker tariffs and production-data permissions remain material limits.

Archive data is CC-BY-NC-SA personal/nonproduction research. Source code licensing does not authorize commercial use of those archives. Production evaluation needs a permitted feed and the actual executable broker contract. An exchange-perpetual proxy result does not certify an FTMO CFD or Topstep futures strategy.

## Statistics and prop rules

`target_evaluation.py` is frozen across the studies. The 10% peak-drawdown and 5% initial-equity daily-loss screens are conservative reference envelopes, not an exact FTMO/Topstep stage replay. Actual static versus trailing floors, Prague resets, stage starts, split/cap fees and payout withdrawals are separately modeled in `prop_objective.py`.

The separate `monthly_inference.py` converts a moving-block interval on daily log returns to calendar-month growth. A positive-mean interval alone does not establish an 8% expected monthly return. For the selected FX primary's 2025 result, observed monthly growth is +0.072569%; conditional 99% monthly bounds are −0.913399% to +1.035470%. This diagnostic does not alter any frozen study or erase adaptive selection or changing regimes.

Author-method sources are recorded separately in `AUTHOR_REGIME_METHODS.md`: pinned original implementations of slow momentum/fast reversion, changepoints and robust portfolio objectives were read. Their claimed profits are not inherited. Backfilled warmups, omitted entry fees, clipped returns, realized-test volatility normalization and licensed unavailable panels are explicitly identified. Blocked original PDFs were not represented as fully reviewed.

## Software and continuation

The passive `/api/trader/research-progress` card reads completed and partial TRAIN rows automatically, including all nine additional studies. The current local board reports 1,100 evaluations, with protocol/producer/input/result-lock SHA consistency for the 808 new configurations; it does not claim complete input verification for the previous 292. Missing or registered-only future reports contribute zero completed evaluations. The API does not rerun simulations or provide external attestation, and absent local history does not rewrite the reported historical count.

The campaign has `primary: null`, `eligible_for_paper: false`, `live_orders: false` and `telegram_enabled: false`. Every study card and report wrapper retains the same false permission flags regardless of candidate claims inside a historical report. Existing evidence authority and the manual journal are preserved. Details and rejected reports are collapsed; no new research button is introduced. Viewing progress performs read-only local retrieval and sends no Telegram message.

The primary navigation is **Find setups / Strategy / Rules / Journal / Settings / Updates**. Strategy evidence has its own view; automatic checks are in Settings. Manual market calculations and backtests remain behind the closed Additional tools menu and a second disclosure, while historical replay is collapsed separately from actual journal records. Existing control IDs, API contracts, setup admission and updater behavior are unchanged.

Portable releases include public protocol/selection/source/result-lock copies under `docs/research-receipts/`. Progress prefers the original `data/<study>` receipt and uses the packaged copy only when that original is missing. A present damaged or changed original cannot be hidden by the copy. Raw history has no such fallback: omitted market inputs still report `input_available: false` and `replay_artifacts_verified: false`, with reported evaluation counts and producer consistency distinguished.

The current setup path is `POST /api/trader/find-setups` → `Autopilot.run_now()` → hourly scanner/backtest job → cached `Trader.board()` → `build_setup()`. It can expose only its own training-selected eligible candidate with fresh closed bars, verified account/contract inputs and no context blockers. It has no adapter from these nine campaign research engines and no Telegram transport. Its displayed entry tolerance is a paper-review aid, not a proven native-limit fill model. The campaign results are not imported into that old path or promoted by this update.

A proposed signal-only user flow keeps one **Find setups** action and automatic checks of closed bars from a permitted feed. A separately qualified, fixed model bundle would provide its exact tested entry, stop, target, invalidation, expiry, clock rule, reason and chart; the runtime would verify the bundle hash, source freshness and account context without optimizing parameters again. Until such a bundle exists, show **No admitted strategy** and no invented levels. A later Telegram outbox would deduplicate signal/expiry/cancellation events and record actual publication times and paper outcomes. These are proposed next components, not a running sender, executed trading journal or profitable bot. Rejected models and exploratory diagrams never enter the qualified signal list.

The official subscription CLI's protected `CODEX_HOME/installation_id` prevented model startup in this environment. That paused queue is not a running token-consuming daemon. Active Codex agents are doing the present research. Do not copy credentials, change protected installation files or claim measured token usage. Standalone strategy backtests use CPU, not subscription tokens. Continuation requires a new defensible hypothesis and a separate preregistration, not repeated evaluation or after-outcome resizing of a failed study.

All completed producer bytes and original outcomes must remain unchanged. New fixes require separate versioned research files. Preserve `.local`, the user database and backups; actual orders, account purchases, Telegram messages and invented journal entries remain outside this completed work.
