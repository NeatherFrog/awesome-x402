# Cross-sectional cryptocurrency rotation: pre-outcome design

Status: **design only, not a preregistered or evaluated strategy**. Prepared on 2026-10-02. No new market PnL has been calculated, and no existing producer, input, protocol, or result has been changed.

The next useful hypothesis is persistent relative strength across a historically defined cryptocurrency universe. This adds information absent from the completed BTC/ETH studies: the dispersion of returns, liquidity, volatility, and financing across different assets. A successful paper result would still require executable venue data, an approved contract, and forward observation.

## Recommendation

Use a fixed broad **retrospective, survivor-conditioned cohort**: BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT, ADAUSDT, DOGEUSDT, LINKUSDT, LTCUSDT, BNBUSDT, BCHUSDT, and DOTUSDT. All have December 2023 archive-checksum evidence and map to the current FTMO crypto catalogue. This deliberate current-deployment scope is not a point-in-time historical universe, historical FTMO eligibility claim, or unbiased estimate for all cryptocurrencies. Current survival and the discretionary cohort choice are explicit selection history. A complete historical roster with delisted assets would be a separate stronger study, rather than an implied property of this experiment.

Acquire December 2023 warm-up plus all of 2024 trade1h, mark1h, and realized funding for these 11 assets before freezing the first implementation. Acquire new-cohort 2025 only after the immutable ONE primary passes TRAIN; acquire 2026 only after passing validation. Previously inspected BTC/ETH years remain adaptively reused information. No asset can be removed because its prices, funding, or performance are inconvenient.

A bounded **72-configuration** proposal is described below. Root approved its economic scope; precise producers and the protocol still require independent review and a freeze before performance. The three economic families, their formulas, the liquidity rules, and the risk catalogue would be fixed before any strategy results. One 2024 primary would be selected, locked before 2025 validation, and evaluated on 2026 only after passing validation. A failed primary ends that study.

## What is available now

The initial feasibility pass covered BTC/ETH only. The new fixed-cohort acquisition is now complete: 429 checksum-verified original monthly archives reconstructed into 33 trade1h/mark1h/funding datasets for all eleven assets, December 2023 through December 2024. Each asset has 9,528 trade hours, 9,528 calculated-mark hours and 1,191 realized funding events. An independent reviewer reconstructed every original source and confirmed its canonical hash, calendar and units before any strategy PnL. No new-cohort 2025/2026 data has been acquired.

The FTMO public-symbol snapshot is at `.local/prop-research/2026-10-02T10-37-13Z/ftmo_public_symbols.raw`, retrieved at 2026-10-02T10:37:17.121818+00:00 from <https://ftmo.com/wp-json/ftmo/symbols>. Its SHA256 is `166e40fe629ff0e0d9e32713e3e0cfa09fafe2ae15174763e140dcc6f4d95aea`. The 166 records comprise 30 Crypto CFD records, 28 Forex, 15 Exotics, 9 Metals CFD, 25 Cash CFD, and 59 Equities CFD.

All 30 Crypto CFD records currently report commission `0.065` with type `percent`, Standard leverage `3.33`, Swing leverage `1`, and USD profit currency. Whether the displayed commission is per side or round trip is not established by this response. The contract sizes differ. The `start` fields include 1969 or year-zero sentinels, and 20 records have July 2025 timestamps. Those configuration fields cannot establish historical FTMO eligibility.

The primary construction will therefore use a **1x total physical exposure ceiling** and interpret the commission conservatively as **0.065% per side**. This is an FTMO-inspired cost and leverage screen on Binance perpetual observations, not an FTMO trade replay. Binance realized funding is not an FTMO CFD swap tariff. USD and USDT prices, spreads, sessions, contract sizes, and financing must remain separate. Lower exchange commissions may be shown only as a separately identified diagnostic, never as the primary qualification result.

### Current FTMO mapping and pre-2024 archive probes

These mappings follow the asset name as well as the code. They do not assume that the abbreviated FTMO code is a Binance ticker. On 2026-10-02 between 11:41:09 and 11:41:11 UTC, all 30 official December 2023 1h ZIP checksum URLs returned HTTP 200. A checksum file supports archive presence; the corresponding ZIP rows and full month still need validation. This does not prove historical contract onboarding, continued availability, or settlement on delisting.

| FTMO Crypto CFD | Binance USD-M candidate | December 2023 checksum |
|---|---|---|
| BTCUSD | BTCUSDT | Present |
| DASHUSD | DASHUSDT | Present |
| ETHUSD | ETHUSDT | Present |
| LTCUSD | LTCUSDT | Present |
| XRPUSD | XRPUSDT | Present |
| XMRUSD | XMRUSDT | Present |
| NEOUSD | NEOUSDT | Present |
| ADAUSD | ADAUSDT | Present |
| DOTUSD | DOTUSDT | Present |
| DOGEUSD | DOGEUSDT | Present |
| SOLUSD | SOLUSDT | Present |
| AVAUSD | AVAXUSDT | Present |
| BCHUSD | BCHUSDT | Present |
| ETCUSD | ETCUSDT | Present |
| BNBUSD | BNBUSDT | Present |
| SANUSD | SANDUSDT | Present |
| LNKUSD | LINKUSDT | Present |
| NERUSD | NEARUSDT | Present |
| ALGUSD | ALGOUSDT | Present |
| ICPUSD | ICPUSDT | Present |
| AAVUSD | AAVEUSDT | Present |
| BARUSD | HBARUSDT | Present |
| GALUSD | GALAUSDT | Present |
| GRTUSD | GRTUSDT | Present |
| IMXUSD | IMXUSDT | Present |
| MANUSD | MANAUSDT | Present |
| VECUSD | VETUSDT | Present |
| XLMUSD | XLMUSDT | Present |
| UNIUSD | UNIUSDT | Present |
| XTZUSD | XTZUSDT | Present |

The probe URL template is `https://data.binance.vision/data/futures/um/monthly/klines/{PAIR}/1h/{PAIR}-1h-2023-12.zip.CHECKSUM`. Local temporary receipts are `/tmp/cross-sectional-mapping-probe.json`; they contain each URL, request time, response hash, bytes, and checksum body. These are source-feasibility receipts, not a frozen data manifest.

Additional checks at 11:46 UTC found December 2023 **markPriceKlines1h and fundingRate checksum files for all 11 selected assets**, also HTTP 200. All 33 source-kind checksum probes for this cohort therefore succeeded. Their financing/mark receipts are `/tmp/cross-sectional-financing-mark-probe.json`. Those small probes alone did not certify calendars; the subsequent complete acquisition and independent reconstruction now do. Source manifest SHA256 is `7345f51f6733f1d3b62e3c911f5fcafed45940eb2951456d3cd8aca4fd106d5c`; source protocol file SHA256 is `21ad25b060d9f88909c7e1a5cf48ce9065bece325e85c3efd033004df3a95a92`.

The official archive website identifies its directory-listing backend as `https://s3-ap-northeast-1.amazonaws.com/data.binance.vision`. This runtime returned tunnel HTTP 403 for that backend and both tested virtual-host S3 endpoints. Adding listing parameters to `https://data.binance.vision/` returned the HTML interface, not an XML listing. Current `/fapi/v1/exchangeInfo` returned HTTP 451. Individual archive checksums were accessible. Complete historical-roster discovery is consequently still a sourcing requirement, potentially using the already authorized cloud download workflow. No current `exchangeInfo` response would resolve survivorship by itself.

## Fixed cohort and data contract

1. Freeze the exact 11 names above before outcomes and verify their actual December 2023 rows. Use December 2023's 31 calendar days as warm-up for fixed 7/14/28-day features. Archive presence is an observational proxy for listing, not an authoritative exchange onboarding timestamp.
2. Keep the cohort fixed. Do not add coins launched during the tested years, select today's market capitalization winners, or silently remove contracts that later delist. Historical notices and explicit final settlement or a conservatively unresolved exposure are required for termination. A missing terminal archive is not a zero return or permission to drop that asset.
3. At each decision use only the previous 30 complete UTC days to screen the cohort for median daily **USDT quote volume** of at least $20 million. Require at least six eligible contracts and complete feature history for the balanced families. No future volume can determine today's membership. Zero-volume observations indicate absence of trades; they do not prove executable prices.
4. Acquire all 11 contracts' required sources for a stage, including the contracts that fail a liquidity screen on particular dates. Mark incomplete source prefixes explicitly and stop before performance if the requested stage cannot be fully reconciled. Acquisition success cannot silently choose a smaller profitable cohort.
5. Bind all required original ZIPs, adjacent checksums, parsed CSV fingerprints, calendar coverage, fields, source notices, and converter versions before execution. Initial source range is 2023-12-01 through 2025-01-01 exclusive, with 2024 alone scored and calendar-day accounting. Daily signals are formed from complete UTC days; native **1h** records provide next-opening execution and pessimistic risk bounds. The coarse interval and ambiguous ordering are explicit limitations. Mark-price bars support floating-risk estimates, not invented executable fills.
6. Preserve actual funding timestamp milliseconds, realized rates, and rate availability. Do not presume every altcoin pays every eight hours. Source interval changes and fully paginated REST receipts must be handled explicitly. Events missing from the receipt-supported coverage invalidate that asset-period rather than become zero funding.
7. Historical quantity steps, tick sizes, maintenance tiers, fees, delisting terms, and production data permission remain sourcing requirements. Today's filters are not verified historical filters. A historical exchange proxy may remain provisional when those details cannot be obtained; it cannot be called a verified prop account.

The initial acquisition comprises 11 assets × 13 monthly periods × 3 source kinds, plus checksums, where each source kind is available. This is modest compared with full 5m market history. It remains a survivor-conditioned experiment even if every source checksum is correct. Do not evaluate a shorter completed prefix as if it were the whole requested TRAIN year.

## Proposed economic construction

At decision day `d`, every feature is calculated from information known before the intended entry. Skip the latest complete day in the price-momentum score to separate this weekly/monthly hypothesis from the already rejected short-term flow study:

`M(i,L,d) = log(close(i,d-2) / close(i,d-2-L))`.

Use a fixed 28-day standard deviation of completed daily log returns for volatility estimates. The optional normalized rank is `M / max(sigma_daily, 0.005)`. Daily crypto annualization, where required, uses 365; it does not inherit an equity business-day convention. Undefined or incomplete volatility is not replaced with zero.

The three families are:

- **Long relative strength:** buy the three highest-ranked eligible assets whose price momentum is positive. Unfilled slots remain cash. This deliberately retains crypto market exposure; its excess return must be distinguished from BTC and an equal-weight universe benchmark.
- **Dollar-balanced momentum:** long the three highest ranks and short the three lowest ranks, with disjoint assets and equal planned dollar totals on each side. Rank requires no positive/negative absolute return filter. Dollar balance is not beta neutrality, so report market beta, residual return, and basis/funding contributions.
- **Dollar-balanced momentum with observed financing:** replace the daily momentum score by `M/L - F7`, where `F7` is the sum of realized funding rates known in the previous seven calendar days divided by seven. High adjusted ranks are long; low ranks short. `F7` is a deliberately simple persistence estimate, not a promised future rate. Actual future settlements are paid using their realized signs and modeled mark notionals. If the volatility-normalized option is selected, divide this adjusted daily score by `sigma_daily`.

Within each selected side, use inverse daily-volatility weights, then normalize sides separately for the dollar-balanced families. An unchanged position is retained rather than closed and reopened solely to charge artificial turnover. Reductions, additions, rotations, and sign changes each pay their real modeled leg costs. The initial stop is fixed at two completed daily ATR20 units from the modeled entry; no outcome-selected take-profit is added. A stopped asset cannot re-enter until the next registered rebalance. Position sizing and all order reservations are determined jointly at the known opening, before any subsequent bar extrema or absent-volume observations are examined.

### Proposed bounded catalogue: 72 configurations

| Dimension | Fixed proposed choices |
|---|---|
| Economic family | Long strength; dollar-balanced momentum; dollar-balanced momentum with financing |
| Momentum lookback | 7, 14, 28 complete days |
| Rebalance | Daily; every seventh UTC day, anchored to 2024-01-01 |
| Ranking | Raw; volatility normalized |
| Per-position entry stop-risk cap | 0.5%; 1.0% of current total account equity |

The count is `3 × 3 × 2 × 2 × 2 = 72`. The liquidity screen, asset counts, skipped day, carry history, volatility history, stop distance, costs, leverage, and acquisition policy are fixed design choices, not an uncounted optimization grid. All choices need independent review before a final protocol is frozen. All prior adaptive studies count as search history; the reused years are not globally blind.

## Physical capital, cost, and risk proposal

Initial total capital is **$100,000**, with one shared free-cash wallet and separately reserved isolated collateral. Maximum entry gross is `min(initial_capital, current_marked_equity)`; each asset is capped at `0.35 × min(initial_capital, current_marked_equity)`. Each position reserves its full entry notional as 1x collateral plus entry fees. There is no extra spot cash, unreconciled margin top-up, or immediately spendable unrealized profit. Marked equity is free cash plus all isolated account balances and marked open-position PnL, with no double counting.

For the 0.5% position catalogue, aggregate planned stop risk is capped at 3% of total equity; for the 1.0% catalogue it is capped at 4%. Stop risk includes entry/exit fees, spread, and modeled adverse fills. Allocate a common scalar to all intended quantities to satisfy both collateral and aggregate risk before examining either fill. Round quantities down to the fixed 0.001-base-unit research proxy; historical FTMO contract filters remain unverified. A 1x ceiling is a maximum, not a claim that the strategy will use all exposure when its stops require lower size.

Primary research costs interpret the current FTMO catalogue conservatively: commission **6.5 basis points per side**, adverse slippage 2 basis points per side, and a 1-basis-point full spread split across sides, totaling 9 basis points per modeled side before financing. Double all three for the fixed cost stress. Report commission, spread/slippage, turnover, funding, and raw price PnL separately. Spread/slippage, the per-side commission interpretation, USDT parity, and financing remain model assumptions pending an actual executable FTMO tariff. An exchange-fee diagnostic must not replace this primary screen.

Use independently reviewed wallet, liquidation, gap-stop, zero-volume, funding entitlement, and sample-boundary logic. Calculated marks govern conservative floating risk and maintenance estimates; traded opens govern modeled executable fills. Ambiguous subbar chronology cannot award favorable funding or target fills. Negative funding can consume collateral and trigger forced closure before a favorable event is credited. Exact sample-end debits must not disappear. A contract becoming unavailable must preserve its last held exposure and a failed/unresolved status until receipt-supported termination accounting exists.

The unchanged common objective remains the 8% geometric calendar-month target with its net OOS, confidence, stress, activity, monthly, half-period, drawdown, and daily-loss conditions. The 10% drawdown and 5% daily-loss screens are not relaxed. Apply additional zero-liquidation, zero unfunded deficit, complete-mark coverage, and dollar-reconciliation gates. These reference screens are not a replacement for FTMO's Prague resets, stage targets, rewards, or actual contract rules.

## Evidence status and methodological limits

The verified primary source is **Yukun Liu, Aleh Tsyvinski, and Xi Wu, _Common Risk Factors in Cryptocurrency_, NBER working paper 25882**, original 48-page PDF <https://www.nber.org/system/files/working_papers/w25882/w25882.pdf>. The authorized source-acquisition workflow `37002836679`, producer `4f486d93a08db4c2d58e35bcefb5c927d49bdf71`, retrieved this actual author paper. PDF SHA256: `01fa7e448623627078b43cc75ca70471caa1c436e48795f12704106392b486f2`; private extracted-text SHA256: `6fe41b0a5a7a48d4caff80399e22208964ea3e92c147dd6e476ab5b7feccba21`. Local private originals and receipts are under `.local/original-intraday-4f486d93a08d/`; the complete copyrighted paper is not redistributed in the public design.

Reading sections 2, 3.2, and 5 establishes a concrete but different source method. The authors use 1,707 CoinMarketCap coins during 2014-2018, including active and defunct coins, and filter for available price/volume/market-cap data and market capitalization of at least $1 million. Their weekly portfolios are quintile sorts, rebalanced weekly, with value-weighted returns. Their 1/2/3/4-week momentum results motivate a bounded short-to-medium weekly hypothesis; the paper also investigates longer horizons, which must not be silently advertised as equally supported. The reference week convention is 52 within-year weeks with a longer final week, rather than our uninterrupted seven-day schedule.

The paper explicitly discusses the feasibility of shorting and an alternative that shorts Bitcoin. Its research returns are not an executable Binance perpetual ledger with our commission, spread, funding, mark-risk, cash-collateral, and daily prop constraints. The size-strategy discussion explicitly acknowledges trading-cost and short-selling limitations; the inspected momentum table does not provide our complete modeled net-execution accounting. No table result is transferred as a return estimate for this application.

Our 11 current survivors, liquidity minimum, inverse-volatility weights, daily option, 7/14/28-day lookbacks, skipped latest day, financing adjustment, 1x physical account, stops, and conservative fees are **new adaptations**, not a faithful replication. In particular the source's inclusion of defunct coins is stronger than our acknowledged retrospective cohort. That limitation cannot be repaired by citing the source paper's own survivorship discussion. The primary-source method and receipt are now known before any new strategy performance; our engine and source calendar still require audit and freeze.

Liu and Tsyvinski's _Risks and Returns of Cryptocurrency_ is a separate potential source for time-series return predictability. It should not be cited as already verified evidence of a cross-sectional portfolio. Jegadeesh and Titman's equity momentum work and already retrieved AQR value/momentum or time-series sources motivate a hypothesis in other asset classes; their results do not transfer into these crypto assets, calendar conventions, retail costs, or prop constraints.

The actual requested TRAIN cohort calendars, calculated marks and funding have now been acquired and independently reconstructed from all 429 originals. Historical contract/termination evidence and unbiased full-universe discovery remain outside this retrospective scope. A correct source checksum does not resolve the execution, financing or survivorship limitations. There is no new return estimate, strategy qualification, Telegram signal, or automated order authorization in this design.

## Required pre-outcome review

The next implementation should be a new producer. Before freezing it, independently test future-price/volume/rate perturbations against prior membership, scores, orders, reservations, and equity; include simultaneous rotations, stop gaps, zero-volume holdings, changing funding intervals, negative funding, insolvency, fees, partial reductions, exact boundary events, and deliberately missing delisting/mark evidence. Verify a fresh $100,000 physical cash ledger, the 1x ceiling, the conservative commission interpretation, and calendar-day worst/best envelopes across all 72 nonvacuous synthetic configurations.

Select exactly one TRAIN primary using the unchanged registered eligibility gates and a predeclared score. Persist its ID, variant, full training digest, protocol, producer, and input identities before 2025. Require an existing passing-validation confirmation before 2026, refuse repair of a missing claimed lock, and never substitute an alternative after failure. Preserve all failed configurations and all previous studies. Even a historical survivor must then complete forward observation with licensed account data before live execution or prop-payout claims.
