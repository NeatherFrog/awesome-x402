# Primary-source review for the crypto research protocol

Completed **2 October 2026, UTC**. This is an audit of ten source groups with
actually retrieved bodies, not a review of every trading course. It does not
establish profitability. Full retrieval receipts, pinned Git commits, final
URLs, HTTP outcomes, UTC timestamps and response SHA-256 values are in
[crypto-source-review.json](crypto-source-review.json). Foreign articles and
source code were read in temporary storage and are not redistributed here.

Previous audits of official SMA/EMA, RSI2 and intraday implementations remain in
[STRATEGY_SOURCES.md](STRATEGY_SOURCES.md),
[MEAN_REVERSION_SOURCES.md](MEAN_REVERSION_SOURCES.md) and
[PROP_STRATEGY_SOURCES.md](PROP_STRATEGY_SOURCES.md). Their software examples do
not establish a crypto trading edge.

## Evidence and its actual scope

### 1. Official Binance historical-data definitions

Read the [pinned official README](https://github.com/binance/binance-public-data/blob/f446ce3812bd4e5521f21faecd4ae3c6460e49fc/README.md)
and its explicitly linked [dataset terms](https://github.com/binance/binance-public-data/blob/f446ce3812bd4e5521f21faecd4ae3c6460e49fc/TERMS_AND_CONDITIONS.md).
Spot archive timestamps switch to **microseconds from 1 January 2025**. Futures
examples show millisecond-sized timestamps; a parser must identify the specific
data product rather than apply the spot transition universally. Opening and
closing times, OHLC, base/quote volume, trade count and taker-buy volumes have
separate meanings. Close time is not the opening label.

Zip files have SHA-256 checksum companions. Binance notes that archives may be
replaced after data corrections. A reproducible experiment therefore retains
the exact downloaded bytes, retrieval date, advertised checksum and computed
hash. Monthly archives become available on the first Monday of the next month;
a current partial month must not be silently treated as complete.

The pinned dataset terms permit personal **non-production historical
backtesting** under section 4.1. Sections 3.4 and 4.2 impose additional commercial
licensing and prohibit using these datasets for live proprietary execution or
specified commercial signal/order uses. The README's code licence label does
not remove the separately referenced dataset conditions. This historical lab
fits the research scope; a future live bot needs a separately valid realtime
data/API binding. This review downloaded documentation, not market archives.

### 2. Official spot REST semantics

Read relevant sections of the [pinned REST specification](https://github.com/binance/binance-spot-api-docs/blob/828ca74b809cfedbd5602df328b5f706368d483b/rest-api.md).
API JSON timestamps default to milliseconds; requesting microseconds uses
`X-MBX-TIME-UNIT`. This differs from post-2025 archive defaults.

A matching-engine timeout leaves execution status **unknown**. The documented
response is to check user-stream/order status, not assume rejection and submit
another order. A client order ID is unique among open orders and can be accepted
again after the earlier order fills. Durable local intent and reconciliation
are consequently needed beyond simply assigning an ID.

Spot BUY/SELL orders acquire/dispose of the base asset. This specification does
not establish a margin borrowing or perpetual short contract. BTCUSDT spot OHLC
cannot by itself validate an executable short or funding strategy.

### 3. Official quantity and price constraints

Read the [pinned symbol-filter definitions](https://github.com/binance/binance-spot-api-docs/blob/828ca74b809cfedbd5602df328b5f706368d483b/filters.md).
`PRICE_FILTER`, `LOT_SIZE`, `MARKET_LOT_SIZE`, `MIN_NOTIONAL`, `NOTIONAL` and
`MAX_POSITION` constrain orders independently. A continuous backtest quantity
or arbitrary fractional step does not prove an order would pass historical or
current instrument filters. No actual numeric BTC/ETH filter history was obtained
in this audit.

### 4. Official commission definitions

The [pinned commission FAQ](https://github.com/binance/binance-spot-api-docs/blob/828ca74b809cfedbd5602df328b5f706368d483b/faqs/commission_faq.md)
explicitly calls its example rates **fictional** and **spot-only**. It distinguishes
standard, tax and special commissions plus account/symbol-dependent discounts.
Actual current rates are obtained with `/api/v3/account/commission`; a test order
with `computeCommissionRates` returns order-specific rates.

The project's 10 basis points per side is a declared modeling assumption. It is
not authenticated fee information, a historical tariff, or evidence of costs
on a perpetual, FX or prop-firm account. Fees must be applied to actual modeled
fills and not replaced with whichever example makes a strategy positive.

### 5. Official derivative connector: useful definitions, version defect

Read `mark_price`, `funding_rate` and `funding_info` in the [pinned official
connector](https://github.com/binance/binance-futures-connector-python/blob/a6bfbbf10fe2c1b4eb76fc24ffb82eb94bf9df89/binance/um_futures/market.py).
The source exposes premium-index and historical funding endpoints. Its funding
information description includes adjustments to caps, floors and interval hours;
a universal eight-hour assumption is therefore unjustified.

There is also an apparent version defect: `funding_info` documents
`/fapi/v1/fundingInfo` but calls `/fapi/v1/fundingRate`. The deprecated connector
must not be copied as current endpoint authority. Its linked developer-hosted
docs were inaccessible through the proxy in this session. No historical funding
series, borrow rates, liquidation rules or profitable two-leg hedge was verified.

### 6. Cointegration differs from correlation

Read `coint`, `adfuller` and `kpss` documentation in [statsmodels 0.14.5](https://github.com/statsmodels/statsmodels/blob/1107ea567121b80f90562d6c72085eed7e882113/statsmodels/tsa/stattools.py).
`coint` is an augmented Engle–Granger two-step test with **no cointegration** as
its null, assuming I(1) inputs. Its residual test uses appropriate cointegration
critical values. ADF has a unit-root null; KPSS has a stationarity null. None is
equivalent to a large Pearson price/return correlation.

For a possible future pair, a training-only relationship could define
`spread[t] = log(Pa[t]) - intercept - beta * log(Pb[t])`. A stationary spread
still does not establish profit after synchronized two-leg fills, fees, funding,
borrowing and structural change. The current long/cash BTC/ETH lab is not a
tested pairs portfolio. All selected pairs and lag choices count as trials.

### 7. Data snooping and dependent observations

Read the official [arch multiple-comparison implementation](https://github.com/bashtage/arch/blob/88ffcf87042ed5d4adf48bac41b144bc90b287a2/arch/bootstrap/multiple_comparison.py).
Its SPA compares a benchmark loss series with multiple model loss series using
stationary, circular or moving-block bootstraps. The code explicitly recommends
a data-appropriate block length. Its documentation cites Hansen (2005), White
(2000) and Romano–Wolf (2005); their complete original papers were not read here.

This supports retaining every trial and accounting for temporal and
cross-strategy dependence. **The project's block sign-flip/Holm diagnostic is
not this SPA implementation.** Its symmetry/block assumptions and limits are
stated separately in [STATISTICAL_PROTOCOL.md](STATISTICAL_PROTOCOL.md). A large
number of correlated trades or variants does not create independent evidence.

### 8. Liquidity/FVG implementations need causal availability

Read the [creator README](https://github.com/joshyattridge/smart-money-concepts/blob/1b62fd6c41e1f508e7ed76831a039fa4c82d42f6/README.md)
and relevant [indicator code](https://github.com/joshyattridge/smart-money-concepts/blob/1b62fd6c41e1f508e7ed76831a039fa4c82d42f6/smartmoneyconcepts/smc.py).
This is an ICT-inspired implementer's repository, not an authenticated original
ICT course or audited trading record.

The three-candle FVG is labeled at the middle candle but uses the **next** candle
(`shift(-1)`). It becomes available only after the third candle closes. Swing
labels inspect both earlier and later candles and perform retrospective pruning.
`MitigatedIndex`, `Swept` and analogous future annotations are outcomes, not
information available when creating the signal. Using these labels without
availability delays can fabricate a profitable backtest.

The reviewed repository supplies indicator definitions and an educational
disclaimer, without verified cost-adjusted out-of-sample profitability. The
project's pivot length, displacement/ATR thresholds, lunch window, entry price,
stop buffer and 2R target come from [LIQUIDITY_PROTOCOL.md](LIQUIDITY_PROTOCOL.md).
They are test hypotheses, not thresholds verified from either screenshot or
attributed to the indicator author.

### 9. Original-author summary of time-series momentum

Actually obtained [AQR's author-affiliated 2012 summary](https://www.aqr.com/Insights/Research/Journal-Article/Time-Series-Momentum),
including its downloadable two-page summary PDF. It reports a study of 58
traditional futures/forward markets and predictability from each instrument's
own preceding 12-month excess return. It distinguishes this from cross-sectional
ranking of assets.

The download ending `?aqrPDF=1` **is not the complete journal paper**. Its exact
cost-adjusted returns, complete equations and dataset were not obtained. A
guessed full-paper URL redirected to a branded 404 page despite HTTP 200; it is
recorded as unverified. None of these claims establishes an hourly crypto edge.

### 10. Full original paper on a century of trend evidence

Obtained and read the author-hosted full paper by Brian Hurst, Yao Hua Ooi and
Lasse Heje Pedersen, *A Century of Evidence on Trend-Following Investing*,
*Journal of Portfolio Management*, Fall 2017:
[original PDF](https://www.aqr.com/-/media/AQR/Documents/Insights/Journal-Article/AQR-JPM-Fall-2017.pdf).
SHA-256: `d2b96b73e6b7e90c244562822e98455c110796bc03056d12fff17fb1bf825dfa`.

It studies monthly data for 67 traditional markets: 29 commodities, 11 equity
indices, 15 bond markets and 12 currency pairs. The January 1880–December 2016
simulation equally combines **1-, 3- and 12-month excess-return sign signals**,
rebalances monthly, holds long/short positions, equalizes market volatility and
targets 10% annualized ex-ante portfolio volatility. A rolling 36-month
covariance estimate is used in portfolio scaling. Earlier noncommodity cash
proxies differ from later traded futures; the paper expressly does not claim
its 1880s strategy was then implementable.

Its historical simulation includes estimated transaction costs and hypothetical
2% management/20% performance fees. The authors note significant uncertainty in
historical cost estimates and omitted futures-roll costs. They report positive
historical mean returns while also reporting drawdowns up to **25%**. Reversals
and lack of clear trends cause losses.

Lower pairwise correlations were associated with better trend performance in
this study; volatility targeting also reduces exposures when correlations rise.
This is evidence in its specific traditional-market construction, not a rule
that correlation alone predicts crypto profit. The authors warn that recession
dates are not known in real time and inflation classifications were made ex
post, so regime analyses cannot simply become causal trade filters.

## Consequences for our experiments

1. The broad lab's 208 preregistered variants are **correlated parameter variants
   across nine implementation families**. SMA, Donchian, price momentum, volume
   breakouts and volatility expansions overlap economically. They are not 208
   independent trading strategies or nine proven independent sources of alpha.
2. Monthly traditional-futures evidence supports a trend-family hypothesis.
   Hourly spot, ATR stops, holding limits and other modified rules are our own
   adaptations and need their own costed results.
3. Mean-reversion and liquidity/FVG patterns remain hypotheses. Correlations
   measured on training data are descriptive; causal information timing,
   untouched chronological evaluation and dependence-aware uncertainty matter.
4. Archive spot data can support the declared historical long/cash study. It
   cannot validate shorting, funding, FX, metals, actual prop-firm execution or
   uninterrupted API fills.
5. No Telegram signal, paid-course profit claim, live trade or stable profitable
   project strategy is established by this source review. A qualifying result
   must come from the separately frozen experiment and genuinely future data.

## Unavailable sources

NBER's Liu/Tsyvinski cryptocurrency paper, David Bailey's deflated-Sharpe PDF
and current Binance derivative/margin documentation returned proxy CONNECT 403.
Their content is **not claimed as read**. An AQR backtest-overfitting URL and two
guessed article PDF URLs redirected to branded 404 pages. Exact outcomes are
retained in the machine-readable registry; failure to fetch is not proof that
the hypothesis is true or false.
