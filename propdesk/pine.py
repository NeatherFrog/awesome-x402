"""Generate transparent TradingView research templates, never live execution.

Pine cannot be compiled by the local Python test suite. The exported script must
be checked in TradingView's Pine Editor and compared with its broker emulator.
Only the default signal formulas are translated; fill/risk engines are separate.
"""
from __future__ import annotations


SUPPORTED_STRATEGIES = (
    "ema_pullback", "donchian_breakout", "rsi_reversion",
    "bollinger_reversion", "trend_momentum", "inside_bar_breakout",
    "volatility_expansion",
)

_PARAMETERS = {
    "ema_pullback": (1.7, 1.8, 36),
    "donchian_breakout": (2.0, 2.0, 72),
    "rsi_reversion": (1.4, 1.4, 24),
    "bollinger_reversion": (1.5, 1.5, 24),
    "trend_momentum": (2.0, 2.0, 48),
    "inside_bar_breakout": (1.4, 1.8, 24),
    "volatility_expansion": (2.0, 1.8, 36),
}

_SIGNALS = {
    "ema_pullback": '''fastLength = input.int(12, "Fast EMA", minval=2)
slowLength = input.int(48, "Slow EMA", minval=4)
emaFast = ta.ema(close, fastLength)
emaSlow = ta.ema(close, slowLength)
warmup = math.max(60, slowLength + 3)
longSignal = emaFast > emaSlow and emaSlow > emaSlow[3] and close[1] <= emaFast[1] and close > emaFast
shortSignal = emaFast < emaSlow and emaSlow < emaSlow[3] and close[1] >= emaFast[1] and close < emaFast
plot(emaFast, "Fast EMA", color=color.teal)
plot(emaSlow, "Slow EMA", color=color.orange)''',
    "donchian_breakout": '''lookback = input.int(20, "Donchian lookback", minval=2)
previousHigh = ta.highest(high, lookback)[1]
previousLow = ta.lowest(low, lookback)[1]
warmup = math.max(60, lookback + 2)
longSignal = close > previousHigh
shortSignal = close < previousLow
plot(previousHigh, "Previous channel high", color=color.teal)
plot(previousLow, "Previous channel low", color=color.orange)''',
    "rsi_reversion": '''rsiLength = input.int(14, "RSI length", minval=2)
oversold = input.float(30, "RSI lower level", minval=1, maxval=49)
overbought = input.float(70, "RSI upper level", minval=51, maxval=99)
rsiValue = ta.rsi(close, rsiLength)
noise = math.sum(math.abs(ta.change(close)), 20)
efficiency = noise > 0 ? math.abs(close - close[20]) / noise : 0.0
warmup = math.max(60, rsiLength + 2)
longSignal = rsiValue[1] <= oversold and rsiValue > oversold and efficiency < 0.4
shortSignal = rsiValue[1] >= overbought and rsiValue < overbought and efficiency < 0.4''',
    "bollinger_reversion": '''bbLength = input.int(20, "Bollinger length", minval=2)
deviation = input.float(2.0, "Bollinger deviations", minval=0.1, step=0.1)
middle = ta.sma(close, bbLength)
spread = ta.stdev(close, bbLength, true) * deviation
upper = middle + spread
lower = middle - spread
noise = math.sum(math.abs(ta.change(close)), 20)
efficiency = noise > 0 ? math.abs(close - close[20]) / noise : 0.0
warmup = math.max(60, bbLength + 2)
longSignal = close[1] <= lower[1] and close > lower and efficiency < 0.4
shortSignal = close[1] >= upper[1] and close < upper and efficiency < 0.4
plot(upper, "Upper band", color=color.orange)
plot(lower, "Lower band", color=color.teal)''',
    "trend_momentum": '''momentumLength = input.int(12, "Momentum lookback", minval=2)
emaTrend = ta.ema(close, 50)
momentum = close - close[momentumLength]
warmup = math.max(60, momentumLength + 2)
longSignal = momentum > 2.0 * atr and momentum[1] <= 2.0 * atr[1] and close > emaTrend
shortSignal = momentum < -2.0 * atr and momentum[1] >= -2.0 * atr[1] and close < emaTrend
plot(emaTrend, "Trend EMA", color=color.orange)''',
    "inside_bar_breakout": '''emaTrend = ta.ema(close, 50)
inside = high[1] < high[2] and low[1] > low[2]
warmup = 60
longSignal = inside and close > high[1] and close > emaTrend
shortSignal = inside and close < low[1] and close < emaTrend
plot(emaTrend, "Trend EMA", color=color.orange)''',
    "volatility_expansion": '''expansion = input.float(1.4, "Candle body / previous ATR", minval=0.1, step=0.1)
lookback = input.int(10, "Breakout lookback", minval=2)
emaTrend = ta.ema(close, 50)
previousHigh = ta.highest(high, lookback)[1]
previousLow = ta.lowest(low, lookback)[1]
expanded = math.abs(close - open) > expansion * atr[1]
warmup = math.max(60, lookback + 2)
longSignal = expanded and close > previousHigh and close > emaTrend
shortSignal = expanded and close < previousLow and close < emaTrend
plot(emaTrend, "Trend EMA", color=color.orange)''',
}

_HEADER = r'''//@version=6
// PropDesk research template. Paper planning only; no broker integration.
// Default signal formulas are translated; execution is NOT equivalent to Python.
// Configure actual commission/slippage in Strategy Properties before testing.
// Default commission: 0.02% per side; default slippage: 1 minimum tick per fill.
// TradingView may choose a profitable target when Python chooses the stop first.
// Bar Magnifier, timezone, gaps, sessions and data providers also change results.
strategy("PropDesk / __ID__ / PAPER", overlay=true,
    initial_capital=100000, currency=currency.USD, pyramiding=0,
    commission_type=strategy.commission.percent, commission_value=0.02,
    slippage=1, calc_on_every_tick=false, calc_on_order_fills=false,
    process_orders_on_close=false, margin_long=100, margin_short=100)

stopATR = input.float(__STOP__, "Stop distance / ATR", minval=0.1, step=0.1)
rewardRisk = input.float(__RR__, "Target / stop distance", minval=0.1, step=0.1)
maxHoldBars = input.int(__HOLD__, "Maximum holding bars", minval=1)
riskPct = input.float(0.25, "Paper risk budget (% of equity)", minval=0.01, maxval=2, step=0.01)
contractMultiplier = input.float(1.0, "Account currency per price point per quantity unit", minval=0.000001)
quantityStep = input.float(1.0, "Quantity step (units or contracts, not lots)", minval=0.000001)
costReserveBps = input.float(6.0, "Sizing reserve: roundtrip costs (basis points)", minval=0.0)
// The sizing reserve does not configure tester costs; use Strategy Properties.
allowShort = input.bool(true, "Enable short research signals")
webhookToken = input.string("", "Optional planning-inbox token; never share settings")
atr = ta.atr(14)

__SIGNALS__

// Position sizing is approximate: signal close precedes actual next-open fill.
// Validate contract/account-currency conversion manually. No prop-rule checks.
stopDistance = math.max(atr * stopATR, syminfo.mintick)
stopTicks = math.max(1, math.ceil(stopDistance / syminfo.mintick))
targetTicks = math.max(1, math.floor(stopTicks * rewardRisk))
unitRisk = stopTicks * syminfo.mintick * contractMultiplier + close * contractMultiplier * costReserveBps / 10000
rawQuantity = unitRisk > 0 ? strategy.equity * riskPct / 100 / unitRisk : 0.0
quantity = math.floor(rawQuantity / quantityStep) * quantityStep
ready = barstate.isconfirmed and bar_index >= warmup and not na(atr) and atr > 0 and quantity > 0

f_escape(string value) =>
    escaped = str.replace_all(value, "\\", "\\\\")
    escaped := str.replace_all(escaped, "\"", "\\\"")
    escaped := str.replace_all(escaped, "\n", "\\n")
    escaped := str.replace_all(escaped, "\r", "\\r")
    escaped

f_payload(string side) =>
    signalTime = str.format_time(time_close, "yyyy-MM-dd'T'HH:mm:ss'Z'", "UTC")
    '{"mode":"paper","event":"signal","strategy":"__ID__","symbol":"' + f_escape(syminfo.tickerid) + '","side":"' + side + '","price":' + str.tostring(close, format.mintick) + ',"price_kind":"signal_close","time":"' + signalTime + '","token":"' + f_escape(webhookToken) + '"}'

// Entry created at close; broker emulator fills on the next available tick.
// Relative loss/profit distances refer to the eventual entry fill price.
if ready and strategy.position_size == 0
    if longSignal
        strategy.entry("L", strategy.long, qty=quantity, disable_alert=true)
        strategy.exit("L bracket", from_entry="L", loss=stopTicks, profit=targetTicks, disable_alert=true)
        alert(f_payload("long"), alert.freq_once_per_bar_close)
    else if shortSignal and allowShort
        strategy.entry("S", strategy.short, qty=quantity, disable_alert=true)
        strategy.exit("S bracket", from_entry="S", loss=stopTicks, profit=targetTicks, disable_alert=true)
        alert(f_payload("short"), alert.freq_once_per_bar_close)

var int filledBar = na
if strategy.position_size != 0 and strategy.position_size[1] == 0
    filledBar := bar_index
if strategy.position_size == 0
    filledBar := na
if strategy.position_size != 0 and not na(filledBar) and bar_index - filledBar >= maxHoldBars
    strategy.close_all(comment="Time stop / next tick", disable_alert=true)

plotshape(ready and longSignal, title="Long setup", style=shape.triangleup, location=location.belowbar, color=color.teal, size=size.tiny)
plotshape(ready and shortSignal and allowShort, title="Short setup", style=shape.triangledown, location=location.abovebar, color=color.orange, size=size.tiny)
'''


def generate(strategy_id: str) -> str:
    """Export a v6 research strategy; reject unknown IDs and baseline explicitly."""
    if strategy_id not in SUPPORTED_STRATEGIES:
        raise ValueError("Pine-экспорт доступен для: " + ", ".join(SUPPORTED_STRATEGIES))
    stop, reward, hold = _PARAMETERS[strategy_id]
    return (_HEADER.replace("__ID__", strategy_id)
            .replace("__STOP__", str(stop))
            .replace("__RR__", str(reward))
            .replace("__HOLD__", str(hold))
            .replace("__SIGNALS__", _SIGNALS[strategy_id]))
