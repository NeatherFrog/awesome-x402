"""Bounded, causal spot research. Standard library only; never places orders.

All indicator observations use fully closed bars. Decisions at bar i refer
exclusively to bar i-1; fills occur at i's open with adverse modeled friction.
The different parameter variants are correlated hypotheses, not independent
economic strategies. Historical results cannot certify future profitability.
"""
from __future__ import annotations

from collections import deque
from datetime import timedelta
import hashlib
import itertools
import json
import math
from statistics import mean

from propdesk import market

FAMILY_RULES = {
    "ma_trend": "Strict close SMA fast/slow upward crossover; downward crossover exit.",
    "donchian": "Close exceeds previous N highs in specified SMA uptrend; exit below previous half-N lows.",
    "rsi_reversion": "Wilder RSI is below threshold while close>SMA200; exit RSI>60 or close>SMA200 fails.",
    "bollinger_reversion": "Close falls below rolling mean minus z standard deviations in SMA200 uptrend; exit at rolling mean.",
    "return_shock": "Negative one-hour log-return standardized against prior N return observations below -z in SMA200 uptrend; exit SMA8 recovery.",
    "momentum": "N-hour price return crosses above positive threshold; exit when that return<=0.",
    "atr_expansion": "Positive candle true range exceeds prior ATR14 multiple in specified SMA uptrend; exit close<SMA24.",
    "volume_breakout": "Close exceeds previous N highs and volume exceeds previous N mean volume multiple; exit below previous half-N lows.",
    "trend_pullback": "Close recrosses EMA fast from below while EMA fast>EMA slow; exit EMA fast<=EMA slow or close<EMA fast.",
}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def make_grid():
    """208 frozen variants in nine economically distinct hypothesis families."""
    variants = []
    grids = {
        "ma_trend": {"fast": [8, 16, 24], "slow": [48, 96], "stop_atr": [2, 3], "max_hold": [72, 168]},
        "donchian": {"lookback": [12, 24, 48], "trend": [96, 192], "stop_atr": [2, 3], "max_hold": [72, 168]},
        "rsi_reversion": {"period": [2, 5, 14], "threshold": [10, 20], "stop_atr": [2, 3], "max_hold": [24, 72]},
        "bollinger_reversion": {"lookback": [24, 48, 96], "z": [1.5, 2.0], "stop_atr": [2, 3], "max_hold": [24, 72]},
        "return_shock": {"lookback": [24, 48, 96], "z": [1.5, 2.0], "stop_atr": [2, 3], "max_hold": [24, 72]},
        "momentum": {"lookback": [12, 24, 48], "threshold": [.01, .02], "stop_atr": [2, 3], "max_hold": [72, 168]},
        "atr_expansion": {"multiple": [1.5, 2.0], "trend": [48, 96], "stop_atr": [2, 3], "max_hold": [24, 72]},
        "volume_breakout": {"lookback": [12, 24, 48], "volume_multiple": [1.5, 2.0], "stop_atr": [2, 3], "max_hold": [72, 168]},
        "trend_pullback": {"fast": [12, 24, 48], "slow": [96, 192], "stop_atr": [2, 3], "max_hold": [72, 168]},
    }
    for family, choices in grids.items():
        keys = list(choices)
        for values in itertools.product(*(choices[key] for key in keys)):
            item = {"family": family, **dict(zip(keys, values))}
            item["id"] = family + "-" + digest(item)[:12]
            variants.append(item)
    return variants


def rolling(values, period, *, mode="mean"):
    out = [None] * len(values)
    queue = deque()
    total = squares = 0.0
    for i, value in enumerate(values):
        queue.append(value)
        total += value
        squares += value * value
        if len(queue) > period:
            removed = queue.popleft()
            total -= removed
            squares -= removed * removed
        if len(queue) == period:
            out[i] = total / period if mode == "mean" else math.sqrt(max(0, squares / period-(total / period)**2))
    return out


def extrema(values, period, *, maximum=True):
    """Rolling extrema include current bar; callers lag the array for breakouts."""
    queue = deque()
    out = [None] * len(values)
    for i, value in enumerate(values):
        while queue and queue[0] <= i-period:
            queue.popleft()
        while queue and ((values[queue[-1]] <= value) if maximum else (values[queue[-1]] >= value)):
            queue.pop()
        queue.append(i)
        if i >= period-1:
            out[i] = values[queue[0]]
    return out


def exponential(values, period):
    out = [None] * len(values)
    if len(values) < period:
        return out
    value = sum(values[:period])/period
    out[period-1] = value
    alpha = 2/(period+1)
    for i in range(period, len(values)):
        value += alpha*(values[i]-value)
        out[i] = value
    return out


def wilder(values, period):
    out = [None] * len(values)
    if len(values) < period:
        return out
    value = sum(values[:period])/period
    out[period-1] = value
    for i in range(period, len(values)):
        value = ((period-1)*value+values[i])/period
        out[i] = value
    return out


class FeatureCache:
    def __init__(self, bars):
        self.bars = market.validate_bars(bars, max_bars=100_000)
        self.close = [b["close"] for b in self.bars]
        self.high = [b["high"] for b in self.bars]
        self.low = [b["low"] for b in self.bars]
        self.volume = [b["volume"] for b in self.bars]
        self.returns = [0.0]+[math.log(self.close[i]/self.close[i-1]) for i in range(1, len(bars))]
        self.tr = [max(b["high"]-b["low"], abs(b["high"]-self.close[i-1]), abs(b["low"]-self.close[i-1]))
                   if i else b["high"]-b["low"] for i, b in enumerate(self.bars)]
        self._cache = {}

    def get(self, kind, period):
        key = kind, period
        if key not in self._cache:
            source = {"volume_mean": self.volume, "return_mean": self.returns,
                      "return_std": self.returns, "high": self.high, "low": self.low,
                      "atr": self.tr}.get(kind, self.close)
            if kind == "ema":
                value = exponential(source, period)
            elif kind == "atr":
                value = wilder(source, period)
            elif kind in ("high", "low"):
                value = extrema(source, period, maximum=kind == "high")
            elif kind == "rsi":
                changes = [self.close[i]-self.close[i-1] for i in range(1, len(self.close))]
                gains = wilder([max(x, 0) for x in changes], period)
                losses = wilder([max(-x, 0) for x in changes], period)
                value = [None]+[None if g is None else (50.0 if g == l == 0 else 100.0 if l == 0 else 100-100/(1+g/l)) for g, l in zip(gains, losses)]
            else:
                value = rolling(source, period, mode="std" if kind in ("std", "return_std") else "mean")
            self._cache[key] = value
        return self._cache[key]


def decisions(cache, variant):
    """Entry/exit evaluated at prior close, not contemporaneous open/high/low."""
    family, c, n = variant["family"], cache.close, len(cache.close)
    result = [None]*n
    atr, trend = cache.get("atr", 14), cache.get("mean", 200)
    p = variant.get("lookback", 24)
    if family == "ma_trend":
        fast, slow = cache.get("mean", variant["fast"]), cache.get("mean", variant["slow"])
    elif family == "trend_pullback":
        fast, slow = cache.get("ema", variant["fast"]), cache.get("ema", variant["slow"])
    elif family in ("donchian", "volume_breakout"):
        highs, lows = cache.get("high", p), cache.get("low", max(2, p//2))
        trend = cache.get("mean", variant.get("trend", 200))
        volumes = cache.get("volume_mean", p)
    elif family == "rsi_reversion":
        rsi = cache.get("rsi", variant["period"])
    elif family == "bollinger_reversion":
        avg, std = cache.get("mean", p), cache.get("std", p)
    elif family == "return_shock":
        avg, std, fast = cache.get("return_mean", p), cache.get("return_std", p), cache.get("mean", 8)
    elif family == "atr_expansion":
        trend, fast = cache.get("mean", variant["trend"]), cache.get("mean", 24)
    for i in range(2, n):
        j = i-1
        if atr[j] is None or atr[j] <= 0:
            continue
        enter = leave = False
        if family == "ma_trend":
            if slow[j-1] is None:
                continue
            enter = fast[j] > slow[j] and fast[j-1] <= slow[j-1]
            leave = fast[j] < slow[j] and fast[j-1] >= slow[j-1]
        elif family == "trend_pullback":
            if slow[j] is None or fast[j-1] is None:
                continue
            enter = fast[j] > slow[j] and c[j] > fast[j] and c[j-1] <= fast[j-1]
            leave = fast[j] <= slow[j] or c[j] < fast[j]
        elif family in ("donchian", "volume_breakout"):
            if highs[j-1] is None or lows[j-1] is None or trend[j] is None:
                continue
            enter = c[j] > highs[j-1]
            enter = enter and (c[j] > trend[j] if family == "donchian" else cache.volume[j] > variant["volume_multiple"]*volumes[j-1])
            leave = c[j] < lows[j-1]
        elif family == "rsi_reversion":
            if trend[j] is None or rsi[j] is None:
                continue
            enter = c[j] > trend[j] and rsi[j] < variant["threshold"]
            leave = rsi[j] > 60 or c[j] <= trend[j]
        elif family == "bollinger_reversion":
            if avg[j] is None or trend[j] is None:
                continue
            enter = c[j] > trend[j] and c[j] < avg[j]-variant["z"]*std[j]
            leave = c[j] >= avg[j]
        elif family == "return_shock":
            if trend[j] is None or avg[j-1] is None or std[j-1] is None or std[j-1] <= 0:
                continue
            z = (cache.returns[j]-avg[j-1])/std[j-1]
            enter = c[j] > trend[j] and z < -variant["z"]
            leave = c[j] > fast[j]
        elif family == "momentum":
            if j <= p:
                continue
            momentum, before = c[j]/c[j-p]-1, c[j-1]/c[j-1-p]-1
            enter = momentum > variant["threshold"] and before <= variant["threshold"]
            leave = momentum <= 0
        elif family == "atr_expansion":
            if trend[j] is None or atr[j-1] is None:
                continue
            enter = c[j] > trend[j] and c[j] > cache.bars[j]["open"] and cache.tr[j] > variant["multiple"]*atr[j-1]
            leave = c[j] < fast[j]
        else:
            raise ValueError("Unknown hypothesis family")
        result[i] = {"entry": bool(enter), "exit": bool(leave), "atr": atr[j], "signal_time": cache.bars[j]["time"]}
    return result


def metrics(curve, trades, initial):
    if not curve:
        raise ValueError("Empty active window")
    peak, worst_dd = initial, 0.0
    for row in curve:
        peak = max(peak, row["opening_equity"])
        worst_dd = max(worst_dd, 100*(peak-row["worst_equity"])/peak)
        peak = max(peak, row["equity"])
    gains = sum(max(t["pnl"], 0) for t in trades)
    losses = sum(max(-t["pnl"], 0) for t in trades)
    exposure = [row.get("notional", 0)/row["equity"] for row in curve if row["equity"] > 0]
    return {"initial_equity": initial, "final_equity": curve[-1]["equity"],
            "return_pct": (curve[-1]["equity"]/initial-1)*100,
            "max_drawdown_pct": worst_dd, "trade_count": len(trades),
            "profit_factor": gains/losses if losses else None,
            "wins": sum(t["pnl"] > 0 for t in trades), "gross_wins": gains, "gross_losses": losses,
            "fees_paid": sum(t["entry_fee"]+t["exit_fee"] for t in trades),
            "adverse_fill_cost": sum(t.get("entry_adverse_cost", 0)+t.get("exit_adverse_cost", 0) for t in trades),
            "turnover_notional": sum(t["quantity"]*(t["entry_price"]+t["exit_price"]) for t in trades),
            "mean_exposure_fraction": sum(exposure)/len(exposure) if exposure else 0,
            "max_exposure_fraction": max(exposure, default=0),
            "marked_hours_in_position": sum(row.get("notional", 0) > 0 for row in curve)}


def simulate_asset(bars, observations, variant, start, end, *, initial=50_000,
                   risk_budget=250, fee_bps=10, slip_bps=2, full_spread_bps=1,
                   cost_multiplier=1, quantity_step=.000001):
    """Cash-limited spot long only. Gaps and intrabar stops filled adversely.

    Fixed risk budget never implies a guaranteed loss cap: gaps and fees can
    exceed it. Stop takes priority over open indicator/time exit. No same-bar
    reentry after an exit. Final liquidation is explicit retrospective mark.
    Fractional quantities are modeled assumptions, not verified venue filters.
    """
    if not 0 <= start < end <= len(bars) or len(observations) != len(bars):
        raise ValueError("Invalid simulation range")
    if min(initial, risk_budget, quantity_step, cost_multiplier) <= 0:
        raise ValueError("Positive cash, risk, step and cost multiplier required")
    if any(x < 0 for x in (fee_bps, slip_bps, full_spread_bps)):
        raise ValueError("Nonnegative costs required")
    fee = fee_bps*cost_multiplier/10_000
    adverse = (slip_bps+full_spread_bps/2)*cost_multiplier/10_000
    cash, position, trades, curve = float(initial), None, [], []

    def liquidate(price, bar, reason):
        nonlocal cash, position
        fill = max(price*(1-adverse), 1e-12)
        proceeds = position["quantity"]*fill*(1-fee)
        cash += proceeds
        at_close = reason == "sample_boundary"
        exit_time = (market.utc_datetime(bar["time"])+timedelta(hours=1)).isoformat().replace("+00:00", "Z") if at_close else bar["time"]
        timing = "close" if at_close else "open" if reason in ("gap_stop", "indicator_exit", "time_exit") else "intrabar_unobserved"
        trades.append({**position, "exit_time": exit_time, "exit_bar_time": bar["time"],
                       "exit_timing": timing, "exit_price": fill,
                       "exit_adverse_cost": position["quantity"]*(price-fill),
                       "exit_fee": position["quantity"]*fill*fee,
                       "reason": reason, "pnl": proceeds-position["entry_cost"],
                       "return_on_cost": proceeds/position["entry_cost"]-1,
                       "boundary_liquidation": reason == "sample_boundary"})
        position = None

    for i in range(start, end):
        bar, signal = bars[i], observations[i]
        opening_equity = cash+(position["quantity"]*bar["open"] if position else 0)
        worst_equity = opening_equity
        exited = False
        if position:
            if bar["open"] <= position["stop_price"]:
                liquidate(bar["open"], bar, "gap_stop")
                exited = True
            elif signal and signal["exit"]:
                liquidate(bar["open"], bar, "indicator_exit")
                exited = True
            elif i-position["entry_index"] >= variant["max_hold"]:
                liquidate(bar["open"], bar, "time_exit")
                exited = True
            elif bar["low"] <= position["stop_price"]:
                liquidate(position["stop_price"], bar, "intrabar_stop")
                exited = True
            else:
                worst_equity = min(worst_equity, cash+position["quantity"]*bar["low"])
        if not position and not exited and i < end-1 and signal and signal["entry"]:
            fill = bar["open"]*(1+adverse)
            distance = variant["stop_atr"]*signal["atr"]
            if 0 < distance < fill:
                quantity = min(risk_budget/distance, cash/(fill*(1+fee)))
                quantity = math.floor(quantity/quantity_step)*quantity_step
                if quantity > 0:
                    entry_cost = quantity*fill*(1+fee)
                    cash -= entry_cost
                    position = {"entry_time": bar["time"], "signal_time": signal["signal_time"],
                                "entry_index": i, "entry_price": fill, "quantity": quantity,
                                "entry_fee": quantity*fill*fee, "entry_cost": entry_cost,
                                "entry_adverse_cost": quantity*(fill-bar["open"]),
                                "stop_price": fill-distance, "risk_budget": risk_budget}
                    # Entry occurs at open; its same-bar low may trigger protection.
                    if bar["low"] <= position["stop_price"]:
                        liquidate(position["stop_price"], bar, "entry_bar_stop")
                    else:
                        worst_equity = min(worst_equity, cash+quantity*bar["low"])
        if i == end-1 and position:
            liquidate(bar["close"], bar, "sample_boundary")
        equity = cash+(position["quantity"]*bar["close"] if position else 0)
        worst_equity = min(worst_equity, equity, cash if not position else equity)
        curve.append({"time": bar["time"], "opening_equity": opening_equity,
                      "equity": equity, "worst_equity": worst_equity,
                      "notional": position["quantity"]*bar["close"] if position else 0})
    return {"metrics": metrics(curve, trades, initial), "trades": trades, "equity_curve": curve}


def daily_returns(curve, initial=100_000):
    endings = {}
    for row in curve:
        endings[row["time"][:10]] = row["equity"]
    out, previous = [], initial
    for date, equity in endings.items():
        out.append({"date": date, "return": equity/previous-1})
        previous = equity
    return out


def portfolio(caches, observations, variant, start_date, end_date, *, cost_multiplier=1,
              keep_details=True):
    if set(caches) != {"BTCUSDT", "ETHUSDT"}:
        raise ValueError("Fixed two-asset spot universe required")
    symbols = sorted(caches)
    clocks = [[row["time"] for row in caches[s].bars] for s in symbols]
    if clocks[0] != clocks[1]:
        raise ValueError("Exact synchronized venue timestamps required; no dropped sessions")
    active = [i for i, stamp in enumerate(clocks[0]) if start_date <= stamp[:10] < end_date]
    if not active:
        raise ValueError("No data in fixed window")
    parts = [simulate_asset(caches[s].bars, observations[s], variant, active[0], active[-1]+1,
                            cost_multiplier=cost_multiplier) for s in symbols]
    curve, trades = [], []
    for points in zip(*(part["equity_curve"] for part in parts)):
        curve.append({"time": points[0]["time"], **{key: sum(p[key] for p in points)
                      for key in ("equity", "opening_equity", "worst_equity", "notional")}})
    for symbol, part in zip(symbols, parts):
        trades.extend({**trade, "symbol": symbol} for trade in part["trades"])
    result = {"metrics": metrics(curve, trades, 100_000), "daily_returns": daily_returns(curve),
              "start": curve[0]["time"], "end": curve[-1]["time"]}
    if keep_details:
        result.update(trades=trades, equity_curve=curve)
    return result


def selection_score(result):
    m = result["metrics"]
    return m["return_pct"]/max(m["max_drawdown_pct"], .25)


def window_gates(result, stress, *, trades=20, drawdown=12):
    m = result["metrics"]
    return {"positive_costed_return": m["return_pct"] > 0,
            "minimum_trades": m["trade_count"] >= trades,
            "drawdown_limit": m["max_drawdown_pct"] <= drawdown,
            "positive_double_friction": stress["metrics"]["return_pct"] > 0}
