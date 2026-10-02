"""Frozen, causal liquidity-sweep/FVG hypotheses and conservative OHLC replay.

This module does not execute orders or certify profitability. Bar timestamps
are UTC opening labels. A pivot requires two completed bars on either side;
signals become available at the third FVG bar's CLOSE, never its opening time.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timedelta, timezone
from numbers import Real
from zoneinfo import ZoneInfo

from .market import utc_datetime, validate_bars

VARIANTS = ("sweep_all", "mss_all", "sweep_lunch", "mss_lunch")
PROTOCOL_VERSION = "liquidity-fvg-v1"
DEFAULT_CONFIG = {"interval_seconds": 300, "fee_bps": 10.0,
                  "slippage_bps": 2.0, "spread_bps": 1.0,
                  "initial_balance": 100_000.0, "risk_pct": 0.25,
                  "max_gross_leverage": 1.0, "expiry_bars": 6}
_NY = ZoneInfo("America/New_York")
LIMITATIONS = [
    "Unqualified research hypothesis: no stable-profit or prop-account claim.",
    "OHLC replay has no tick queue, order-book depth, latency, exchange outage or live fills.",
    "Fees/spread/slippage are illustrative; funding, borrow costs and liquidation rules are missing.",
    "Spot short signals are theoretical unless a separately verified executable short venue is used.",
    "No contract precision, minimum notional or venue/prop-rule verification is performed.",
    "Limit orders require strict trade-through; entry-bar targets are deferred; ambiguous stops win.",
    "Sample-boundary liquidation is hypothetical and is separately labelled in each trade.",
]


def _iso(stamp):
    return stamp.isoformat(timespec="microseconds" if stamp.microsecond else "seconds").replace("+00:00", "Z")


def _interval(value):
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 86400:
        raise ValueError("interval_seconds must be an integer between 1 and 86400")
    return value


def _symbol(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 40:
        raise ValueError("symbol must be a nonempty string of at most 40 characters")
    return value.strip().upper()


def normalize_config(config=None):
    if config is None:
        config = {}
    if not isinstance(config, dict):
        raise ValueError("config must be an object")
    unknown = set(config) - set(DEFAULT_CONFIG)
    if unknown:
        raise ValueError("unknown config keys: " + ", ".join(sorted(unknown)))
    result = {**DEFAULT_CONFIG, **config}
    result["interval_seconds"] = _interval(result["interval_seconds"])
    if (isinstance(result["expiry_bars"], bool) or not isinstance(result["expiry_bars"], int)
            or result["expiry_bars"] != 6):
        raise ValueError("expiry_bars is frozen at 6 for this protocol")
    bounds = {"fee_bps": (0, 1000), "slippage_bps": (0, 1000), "spread_bps": (0, 1000),
              "initial_balance": (1, 1e12), "risk_pct": (0.001, 5),
              "max_gross_leverage": (0.01, 10)}
    for key, (low, high) in bounds.items():
        value = result[key]
        if isinstance(value, bool) or not isinstance(value, Real):
            raise ValueError(f"{key} must be a finite number")
        value = float(value)
        if not math.isfinite(value) or not low <= value <= high:
            raise ValueError(f"{key} must be between {low} and {high}")
        result[key] = value
    return result


def _validated(bars, interval_seconds):
    canonical = validate_bars(bars, max_bars=1_000_000)
    times = [utc_datetime(bar["time"]) for bar in canonical]
    delta = timedelta(seconds=interval_seconds)
    for index in range(1, len(times)):
        if times[index] - times[index - 1] != delta:
            raise ValueError(f"row {index + 1}: missing or irregular candles; no imputation allowed")
    return canonical, times


def _lunch(stamp):
    local = stamp.astimezone(_NY)
    return local.weekday() < 5 and 11 <= local.hour < 13


def _scan(bars, times, symbol, variant, interval_seconds):
    """Linear scan: one unresolved sweep per side, finite six-bar windows."""
    if variant not in VARIANTS:
        raise ValueError("variant must be one of " + ", ".join(VARIANTS))
    need_mss, lunch_only = variant.startswith("mss"), variant.endswith("lunch")
    high_pivot = low_pivot = None
    sweeps = {}
    atr = None
    tr_seed = []
    setups = []
    interval = timedelta(seconds=interval_seconds)
    for index, bar in enumerate(bars):
        # ATR is based only on previous completed bars at this decision.
        prior_atr = atr
        for side, sweep in list(sweeps.items()):
            if index - sweep["index"] > 6:
                del sweeps[side]
                continue
            sweep["extreme"] = (max(sweep["extreme"], bar["high"]) if side == "short"
                                 else min(sweep["extreme"], bar["low"]))
            if index < 2 or prior_atr is None or prior_atr <= 0:
                continue
            body, width = abs(bar["close"] - bar["open"]), bar["high"] - bar["low"]
            if body < prior_atr or width <= 0:
                continue
            if side == "short":
                gap_low, gap_high = bar["high"], bars[index - 2]["low"]
                directional = bar["close"] < bar["open"] and bar["close"] <= bar["low"] + .25 * width
                shifted = sweep["opposing"] is not None and bar["close"] < sweep["opposing"]["price"]
            else:
                gap_low, gap_high = bars[index - 2]["high"], bar["low"]
                directional = bar["close"] > bar["open"] and bar["close"] >= bar["high"] - .25 * width
                shifted = sweep["opposing"] is not None and bar["close"] > sweep["opposing"]["price"]
            if not directional or gap_high - gap_low < .1 * prior_atr or gap_high <= gap_low:
                continue
            if need_mss and not shifted:
                continue
            entry = (gap_low + gap_high) / 2
            sign = 1 if side == "long" else -1
            stop = sweep["extreme"] - sign * .1 * prior_atr
            risk = sign * (entry - stop)
            target = entry + sign * 2 * risk
            if risk <= 0 or stop <= 0 or target <= 0:
                continue
            signal_time = _iso(times[index] + interval)
            payload = {"symbol": symbol, "variant": variant, "side": side,
                       "signal_time": signal_time, "entry": entry, "stop": stop,
                       "target": target, "gap_low": gap_low, "gap_high": gap_high,
                       "reference_time": sweep["pivot"]["time"], "sweep_time": sweep["time"],
                       "interval_seconds": interval_seconds, "protocol_version": PROTOCOL_VERSION}
            digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                               allow_nan=False).encode()).hexdigest()[:20]
            reasons = ["Строгий выход за подтверждённый pivot и закрытие обратно за его уровнем.",
                       "Направленное тело >= предыдущего ATR14; закрытие в крайней четверти диапазона.",
                       "Трёхсвечный FVG >= 0.1 предыдущего ATR14; лимит на середине разрыва."]
            if need_mss:
                reasons.append("Закрытие за противоположным pivot, известным до снятия ликвидности (MSS).")
            if lunch_only:
                reasons.append("Снятие ликвидности завершилось в будний день 11:00–13:00 America/New_York.")
            setups.append({"id": f"{symbol}:{variant}:{digest}", "symbol": symbol, "side": side,
                           "direction": side, "signal_time": signal_time,
                           "entry_low": gap_low, "entry_high": gap_high, "entry": entry,
                           "stop": stop, "target": target, "invalidation": stop,
                           "expires_at": _iso(times[index] + interval * 7),
                           "reference_time": sweep["pivot"]["time"],
                           "reference_price": sweep["pivot"]["price"],
                           "reference_available_at": sweep["pivot"]["available_at"],
                           "opposing_reference_price": sweep["opposing"]["price"] if sweep["opposing"] else None,
                           "sweep_time": sweep["time"], "gap_low": gap_low, "gap_high": gap_high,
                           "atr14_before_signal": prior_atr, "reasons": reasons,
                           "variant": variant, "status": "candidate", "mode": "paper_candidate",
                           "qualified": False, "protocol_version": PROTOCOL_VERSION,
                           "signal_index": index, "sweep_index": sweep["index"]})
            del sweeps[side]

        # The newly closed bar may create a sweep, but cannot retrospectively
        # satisfy its own displacement. Pivot confirmation below is also late.
        if not lunch_only or _lunch(times[index] + interval):
            if high_pivot and bar["high"] > high_pivot["price"] and bar["close"] < high_pivot["price"]:
                sweeps["short"] = {"index": index, "time": _iso(times[index] + interval),
                                   "extreme": bar["high"], "pivot": high_pivot, "opposing": low_pivot}
            if low_pivot and bar["low"] < low_pivot["price"] and bar["close"] > low_pivot["price"]:
                sweeps["long"] = {"index": index, "time": _iso(times[index] + interval),
                                  "extreme": bar["low"], "pivot": low_pivot, "opposing": high_pivot}
        if index >= 4:
            center = index - 2
            candidate = bars[center]
            surrounding = (bars[center - 2], bars[center - 1], bars[center + 1], bar)
            if all(candidate["high"] > other["high"] for other in surrounding):
                high_pivot = {"price": candidate["high"], "time": times[center].isoformat().replace("+00:00", "Z"),
                              "available_at": _iso(times[index] + interval)}
            if all(candidate["low"] < other["low"] for other in surrounding):
                low_pivot = {"price": candidate["low"], "time": times[center].isoformat().replace("+00:00", "Z"),
                             "available_at": _iso(times[index] + interval)}
        previous_close = bars[index - 1]["close"] if index else bar["open"]
        tr = max(bar["high"] - bar["low"], abs(bar["high"] - previous_close), abs(bar["low"] - previous_close))
        if atr is None:
            tr_seed.append(tr)
            if len(tr_seed) == 14:
                atr = sum(tr_seed) / 14
        else:
            atr = (atr * 13 + tr) / 14
    return setups


def _stop_gap(setup, bar):
    return bar["open"] <= setup["stop"] if setup["side"] == "long" else bar["open"] >= setup["stop"]


def _touch_entry(setup, bar):
    return bar["low"] < setup["entry"] if setup["side"] == "long" else bar["high"] > setup["entry"]


def _lifecycle(setups, bars, times, interval_seconds):
    delta = timedelta(seconds=interval_seconds)
    for setup in setups:
        signal_index = setup["signal_index"]
        for index in range(signal_index + 1, min(signal_index + 7, len(bars))):
            bar = bars[index]
            if index == signal_index + 1 and _stop_gap(setup, bar):
                setup.update(status="invalidated", status_time=_iso(times[index]),
                             status_reason="next_open_already_beyond_stop")
                break
            if _touch_entry(setup, bar):
                setup.update(status="triggered", status_time=_iso(times[index] + delta),
                             status_reason="strict_trade_through_in_completed_bar")
                break
        else:
            if signal_index + 6 < len(bars):
                setup.update(status="expired", status_time=setup["expires_at"],
                             status_reason="six_completed_bars_without_fill")
    return setups


def detect_setups(bars, *, symbol="BTCUSDT", variant="mss_all", interval_seconds=300):
    """Return independent paper candidates with causal later-bar lifecycle.

    Immutable signal fields are prefix invariant. Lifecycle status may change
    as additional bars close. Triggered does not mean a real exchange fill.
    """
    interval_seconds, symbol = _interval(interval_seconds), _symbol(symbol)
    canonical, times = _validated(bars, interval_seconds)
    return _lifecycle(_scan(canonical, times, symbol, variant, interval_seconds),
                      canonical, times, interval_seconds)


def _exit(position, bar, *, entry_bar=False):
    setup = position["setup"]
    long = setup["side"] == "long"
    stop_hit = bar["low"] <= setup["stop"] if long else bar["high"] >= setup["stop"]
    target_hit = bar["high"] > setup["target"] if long else bar["low"] < setup["target"]
    if _stop_gap(setup, bar):
        return bar["open"], "gap_stop", target_hit
    if stop_hit:
        return setup["stop"], "entry_stop_ambiguous" if entry_bar else "stop_first_collision" if target_hit else "stop", target_hit or entry_bar
    if target_hit and not entry_bar:
        return setup["target"], "take_profit", False
    return None, None, False


def backtest(bars, *, symbol="BTCUSDT", variant="mss_all", config=None):
    """Single-position, risk-sized, costed research replay of a fixed variant."""
    cfg = normalize_config(config)
    symbol = _symbol(symbol)
    canonical, times = _validated(bars, cfg["interval_seconds"])
    setups = _scan(canonical, times, symbol, variant, cfg["interval_seconds"])
    by_index = {}
    for setup in setups:
        by_index.setdefault(setup["signal_index"], []).append(setup)
    _lifecycle(setups, canonical, times, cfg["interval_seconds"])
    balance = peak = cfg["initial_balance"]
    max_drawdown = 0.0
    trades, pending, position = [], None, None
    fee = cfg["fee_bps"] / 10_000
    friction = (cfg["slippage_bps"] + cfg["spread_bps"] / 2) / 10_000
    total_fees = 0.0
    ambiguous_bars = 0
    delta = timedelta(seconds=cfg["interval_seconds"])

    def mark(value):
        nonlocal peak, max_drawdown
        if not math.isfinite(value):
            raise ValueError("nonfinite account value; check price and configuration scales")
        peak = max(peak, value)
        max_drawdown = max(max_drawdown, (peak - value) / peak * 100)

    def liquidation_value(raw_exit):
        direction = position["direction"]
        exit_price = raw_exit * (1 - direction * friction)
        return balance + direction * (exit_price - position["entry_price"]) * position["quantity"] - exit_price * position["quantity"] * fee

    def close(raw_exit, reason, index, ambiguous=False):
        nonlocal balance, position, total_fees, ambiguous_bars
        direction = position["direction"]
        exit_price = raw_exit * (1 - direction * friction)
        exit_fee = position["quantity"] * exit_price * fee
        gross = direction * (exit_price - position["entry_price"]) * position["quantity"]
        net = gross - position["entry_fee"] - exit_fee
        balance += gross - exit_fee
        total_fees += exit_fee
        ambiguous_bars += bool(ambiguous)
        setup = position["setup"]
        trades.append({"setup_id": setup["id"], "symbol": symbol, "side": setup["side"],
                       "variant": variant, "signal_time": setup["signal_time"],
                       "entry_bar_time": canonical[position["entry_index"]]["time"],
                       "entry_time_precision": "within_bar_unknown",
                       "entry_price": position["entry_price"], "entry_raw": setup["entry"],
                       "exit_bar_time": canonical[index]["time"],
                       "exit_time_precision": "within_bar_unknown" if reason != "end_of_data_hypothetical" else "bar_close",
                       "exit_observed_at": _iso(times[index] + delta), "exit_price": exit_price,
                       "exit_raw": raw_exit, "stop": setup["stop"], "target": setup["target"],
                       "quantity": position["quantity"], "entry_fee": position["entry_fee"],
                       "exit_fee": exit_fee, "fees": position["entry_fee"] + exit_fee,
                       "gross_pnl_after_price_friction": gross, "net_pnl": net, "pnl": net,
                       "planned_risk_amount": position["risk_amount"],
                       "r_multiple": net / position["risk_amount"], "exit_reason": reason,
                       "ambiguous": bool(ambiguous), "bars_held": index - position["entry_index"],
                       "balance_after": balance, "mode": "historical_replay",
                       "hypothetical_boundary_exit": reason == "end_of_data_hypothetical"})
        mark(balance)
        position = None

    for index, bar in enumerate(canonical):
        if position is not None:
            raw_exit, reason, ambiguous = _exit(position, bar)
            adverse = raw_exit if reason and reason != "take_profit" else bar["low"] if position["direction"] == 1 else bar["high"]
            mark(liquidation_value(adverse))
            if reason:
                close(raw_exit, reason, index, ambiguous)
            else:
                mark(liquidation_value(bar["close"]))
        elif pending is not None:
            signal_index = pending["signal_index"]
            if index > signal_index + cfg["expiry_bars"]:
                pending = None
            elif index == signal_index + 1 and _stop_gap(pending, bar):
                pending = None
            elif _touch_entry(pending, bar) and balance > 0:
                direction = 1 if pending["side"] == "long" else -1
                entry_price = pending["entry"] * (1 + direction * friction)
                stop_price = pending["stop"] * (1 - direction * friction)
                unit_risk = direction * (entry_price - stop_price) + fee * (entry_price + stop_price)
                quantity = min(balance * cfg["risk_pct"] / 100 / unit_risk,
                               balance * cfg["max_gross_leverage"] / entry_price)
                entry_fee = quantity * entry_price * fee
                position = {"setup": pending, "entry_index": index, "direction": direction,
                            "entry_price": entry_price, "quantity": quantity, "entry_fee": entry_fee,
                            "risk_amount": unit_risk * quantity}
                balance -= entry_fee
                total_fees += entry_fee
                pending = None
                raw_exit, reason, ambiguous = _exit(position, bar, entry_bar=True)
                adverse = raw_exit if reason else bar["low"] if direction == 1 else bar["high"]
                mark(liquidation_value(adverse))
                if reason:
                    close(raw_exit, reason, index, ambiguous)
                else:
                    mark(liquidation_value(bar["close"]))
        if position is None and pending is None and balance > 0:
            available = by_index.get(index)
            if available:
                # Stable chronological first-candidate choice; no outcome selection.
                pending = available[0]
    if position is not None:
        close(canonical[-1]["close"], "end_of_data_hypothetical", len(canonical) - 1)
    profits = [trade["net_pnl"] for trade in trades]
    positive, negative = sum(value for value in profits if value > 0), -sum(value for value in profits if value < 0)
    count = len(trades)
    metrics = {"total_trades": count, "wins": sum(value > 0 for value in profits),
               "losses": sum(value < 0 for value in profits),
               "win_rate_pct": sum(value > 0 for value in profits) / count * 100 if count else 0.0,
               "net_profit": balance - cfg["initial_balance"],
               "return_pct": (balance / cfg["initial_balance"] - 1) * 100,
               "profit_factor": positive / negative if negative else None,
               "max_drawdown_pct": max_drawdown, "gross_profit": positive, "gross_loss": negative,
               "total_fees": total_fees, "expectancy": sum(profits) / count if count else 0.0,
               "avg_r": sum(trade["r_multiple"] for trade in trades) / count if count else 0.0,
               "total_setups": len(setups), "fill_rate_pct": count / len(setups) * 100 if setups else 0.0,
               "ambiguous_bars": ambiguous_bars,
               "boundary_liquidations": sum(trade["hypothetical_boundary_exit"] for trade in trades),
               "qualification": "unqualified", "qualified": False}
    result = {"metrics": metrics, "trades": trades, "setups": setups, "config": cfg,
              "symbol": symbol, "variant": variant, "protocol_version": PROTOCOL_VERSION,
              "limitations": list(LIMITATIONS)}
    json.dumps(result, allow_nan=False)
    return result
