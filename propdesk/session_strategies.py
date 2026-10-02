"""Fixed futures session hypotheses with integer contracts and causal OHLC fills.

Yahoo hourly futures use whole-hour regular anchors. The opening range here is
explicitly the first full RTH hour (10–11 NY), not a fabricated 09:30 range.
VWAP is only an OHLC/volume proxy. These are research models, not broker orders.
"""
from __future__ import annotations

from datetime import datetime, timedelta
import math
from itertools import product

from .market import utc_datetime, validate_bars
from .timezones import timezone_for

VERSION = "futures-rth-sessions-v1"
SPECS = {"MES=F": {"multiplier": 5.0, "tick_size": .25},
         "MNQ=F": {"multiplier": 2.0, "tick_size": .25}}
DEFAULT_CONFIG = {"account_size": 50000.0, "risk_pct": .5, "fee_per_contract_side": .61,
                  "spread_ticks": 1.0, "slippage_ticks": 1.0, "max_contracts": 10,
                  "cost_multiplier": 1.0}


def catalog():
    """48 fixed economic variants, shared across MES and MNQ (96 market tests)."""
    variants = []
    for opening_hours, buffer, reward, trend in product((1, 2), (0.0, .1), (1.5, 2.5), (False, True)):
        variants.append({"id": f"orb_h{opening_hours}_b{buffer:g}_r{reward:g}_t{int(trend)}",
                         "family": "late_opening_range", "opening_hours": opening_hours,
                         "buffer_atr": buffer, "reward_risk": reward, "trend_filter": trend})
    for opening_hours, excursion, target, trend in product((1, 2), (0.0, .25), ("midpoint", "vwap_proxy"), (False, True)):
        variants.append({"id": f"failure_h{opening_hours}_e{excursion:g}_{target}_t{int(trend)}",
                         "family": "failed_range_reversion", "opening_hours": opening_hours,
                         "excursion_atr": excursion, "target_type": target, "trend_filter": trend})
    for channel, expansion, reward, trend in product((4, 8), (.75, 1.25), (1.5, 2.5), (False, True)):
        variants.append({"id": f"release_c{channel}_e{expansion:g}_r{reward:g}_t{int(trend)}",
                         "family": "volatility_release", "channel": channel, "expansion_atr": expansion,
                         "reward_risk": reward, "trend_filter": trend})
    return variants


def _variant(value):
    known = {item["id"]: item for item in catalog()}
    if not isinstance(value, str) or value not in known:
        raise ValueError("Unknown frozen session variant")
    return known[value]


def prepare_bars(raw_bars, calendar, start_date, end_date, *, require_complete=True):
    """Retain expected RTH full-hour features and observed flatten-open markers.

    Halfday marker OHLC/volume are never used as a full-hour feature. Session
    dates and clock rules come from the frozen calendar, not missing prices.
    """
    canonical = validate_bars(raw_bars, max_bars=1_000_000)
    ny = timezone_for("America/New_York")
    groups = {}
    holidays, early = set(calendar["holidays"]), set(calendar["early_close_dates"])
    for bar in canonical:
        local = utc_datetime(bar["time"]).astimezone(ny)
        date, slot = local.date().isoformat(), local.strftime("%H:%M")
        if not start_date <= date < end_date or local.weekday() >= 5 or date in holidays:
            continue
        slots = ("09:30", "10:30", "11:30", "12:30") if date in early else ("10:00", "11:00", "12:00", "13:00", "14:00", "15:00")
        if slot not in slots:
            continue
        if local.second or local.microsecond:
            raise ValueError("Session opening anchor must have exact zero seconds")
        group = groups.setdefault(date, {})
        if slot in group:
            raise ValueError("Duplicate session opening anchor")
        group[slot] = {**bar, "session_date": date, "slot": slot, "flatten": slots[-1],
                       "marker_only": slot == slots[-1]}
    dates = []
    stamp, end = datetime.fromisoformat(start_date).date(), datetime.fromisoformat(end_date).date()
    while stamp < end:
        date = stamp.isoformat()
        if stamp.weekday() < 5 and date not in holidays:
            dates.append(date)
        stamp += timedelta(days=1)
    failures, result = [], []
    for date in dates:
        slots = ("09:30", "10:30", "11:30", "12:30") if date in early else ("10:00", "11:00", "12:00", "13:00", "14:00", "15:00")
        actual = groups.get(date, {})
        missing = [slot for slot in slots if slot not in actual]
        if missing:
            failures.append({"date": date, "missing_slots": missing})
        for slot in slots:
            if slot in actual:
                result.append(actual[slot])
    if require_complete and failures:
        raise ValueError("Calendar coverage incomplete: " + str(failures[:10]))
    return result, {"expected_sessions": len(dates), "complete_sessions": len(dates) - len(failures),
                    "missing_sessions": failures, "first_full_hour": "10:00–11:00 NY normal;09:30–10:30 declared halfday",
                    "normal_flatten": "15:00", "early_flatten": "12:30", "raw_bars": len(canonical),
                    "selected_rows": len(result), "excluded_rows_not_imputed": len(canonical) - len(result)}


def entry_decisions(bars, variant_id):
    """At open i, use only closed feature bars <=i-1 from that same session."""
    params = _variant(variant_id)
    observations, features, history = [], {}, []
    atr, seed, ema, previous_close = None, [], None, None
    date, session_indices, volume, turnover = None, [], 0.0, 0.0
    for index, bar in enumerate(bars):
        if bar["session_date"] != date:
            date, session_indices, volume, turnover = bar["session_date"], [], 0.0, 0.0
        observation = {"direction": 0, "stop": None, "target": None, "reward_risk": params.get("reward_risk"),
                       "variant": variant_id, "family": params["family"], "session_date": date,
                       "slot": bar["slot"], "flatten": bar["marker_only"], "signal_time": None,
                       "range_high": None, "range_low": None, "vwap_proxy": None, "atr": None}
        if not bar["marker_only"] and session_indices:
            signal_index = session_indices[-1]
            signal = bars[signal_index]
            feature = features[signal_index]
            prior_atr, prior_ema = feature["prior_atr"], feature["prior_ema"]
            observation.update(signal_time=(utc_datetime(signal["time"]) + timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
                               atr=prior_atr, vwap_proxy=feature["vwap_proxy"])
            if prior_atr is not None and prior_atr > 0:
                direction = 0
                family = params["family"]
                if family in ("late_opening_range", "failed_range_reversion"):
                    count = params["opening_hours"]
                    if len(session_indices) > count:
                        opening = session_indices[:count]
                        high, low = max(bars[item]["high"] for item in opening), min(bars[item]["low"] for item in opening)
                        observation.update(range_high=high, range_low=low)
                        if family == "late_opening_range":
                            buffer = params["buffer_atr"] * prior_atr
                            direction = 1 if signal["close"] > high + buffer else -1 if signal["close"] < low - buffer else 0
                            stop = low - .1 * prior_atr if direction == 1 else high + .1 * prior_atr
                        else:
                            excursion = params["excursion_atr"] * prior_atr
                            rejected_high = signal["high"] > high + excursion and low < signal["close"] < high
                            rejected_low = signal["low"] < low - excursion and low < signal["close"] < high
                            # A candle sweeping both sides has no observable sequence.
                            direction = -1 if rejected_high and not rejected_low else 1 if rejected_low and not rejected_high else 0
                            stop = signal["low"] - .1 * prior_atr if direction == 1 else signal["high"] + .1 * prior_atr
                            target = (high + low) / 2 if params["target_type"] == "midpoint" else feature["vwap_proxy"]
                            observation["target"] = target
                        observation["stop"] = stop
                else:
                    previous = feature["previous_indices"][-params["channel"]:]
                    if len(previous) == params["channel"]:
                        high, low = max(bars[item]["high"] for item in previous), min(bars[item]["low"] for item in previous)
                        body, width = signal["close"] - signal["open"], signal["high"] - signal["low"]
                        threshold = params["expansion_atr"] * prior_atr
                        if width > 0:
                            long = body >= threshold and signal["close"] > high and signal["close"] >= signal["high"] - .25 * width
                            short = -body >= threshold and signal["close"] < low and signal["close"] <= signal["low"] + .25 * width
                            direction = 1 if long else -1 if short else 0
                            observation.update(range_high=high, range_low=low,
                                               stop=signal["low"] - .1 * prior_atr if direction == 1 else signal["high"] + .1 * prior_atr)
                if direction and params["trend_filter"]:
                    if prior_ema is None:
                        direction = 0
                    elif family == "failed_range_reversion":
                        direction = direction if (direction == -1 and signal["close"] > prior_ema) or (direction == 1 and signal["close"] < prior_ema) else 0
                    else:
                        direction = direction if (direction == 1 and signal["close"] > prior_ema) or (direction == -1 and signal["close"] < prior_ema) else 0
                observation["direction"] = direction
        observations.append(observation)
        if bar["marker_only"]:
            continue
        # These values become available only for the next opening decision.
        volume += bar["volume"]
        turnover += (bar["high"] + bar["low"] + bar["close"]) / 3 * bar["volume"]
        features[index] = {"prior_atr": atr, "prior_ema": ema,
                           "vwap_proxy": turnover / volume if volume > 0 else None,
                           "previous_indices": tuple(history[-8:])}
        true_range = max(bar["high"] - bar["low"], abs(bar["high"] - previous_close) if previous_close is not None else 0,
                         abs(bar["low"] - previous_close) if previous_close is not None else 0)
        if atr is None:
            seed.append(true_range)
            if len(seed) == 14:
                atr = sum(seed) / 14
        else:
            atr = (atr * 13 + true_range) / 14
        ema = bar["close"] if ema is None else (2 / 21) * bar["close"] + (19 / 21) * ema
        previous_close = bar["close"]
        session_indices.append(index)
        history.append(index)
    return observations


def _config(config):
    supplied = {} if config is None else config
    if not isinstance(supplied, dict) or set(supplied) - set(DEFAULT_CONFIG):
        raise ValueError("Invalid session execution configuration")
    result = {**DEFAULT_CONFIG, **supplied}
    for key, value in result.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValueError(f"Invalid {key}")
    if not result["account_size"] or not 0 < result["risk_pct"] <= 5 or not result["cost_multiplier"]:
        raise ValueError("Invalid account or risk budget")
    if int(result["max_contracts"]) != result["max_contracts"] or not 1 <= result["max_contracts"] <= 100:
        raise ValueError("max_contracts must be an integer between1and100")
    return result


def _adverse_price(price, side, tick):
    # Exact integer tick fills; floating representation errors are tolerated.
    return (math.ceil(price / tick - 1e-10) if side > 0 else math.floor(price / tick + 1e-10)) * tick


def _open_position(bar, observation, cfg, spec, balance, index):
    direction, stop = observation["direction"], observation["stop"]
    multiplier, tick = spec["multiplier"], spec["tick_size"]
    fee = cfg["fee_per_contract_side"] * cfg["cost_multiplier"]
    friction = (cfg["slippage_ticks"] + cfg["spread_ticks"] / 2) * cfg["cost_multiplier"] * tick
    raw_entry = bar["open"]
    stop = _adverse_price(stop, -direction, tick)
    target = observation["target"]
    if target is None and observation["reward_risk"] is not None:
        target = raw_entry + direction * abs(raw_entry - stop) * observation["reward_risk"]
    if target is None or direction * (raw_entry - stop) <= 0 or direction * (target - raw_entry) <= 0:
        return None
    if observation["family"] == "late_opening_range":
        boundary = observation["range_high"] if direction == 1 else observation["range_low"]
        if direction * (raw_entry - boundary) <= 0:
            return None
    target = _adverse_price(target, -direction, tick)
    entry_price = _adverse_price(raw_entry + direction * friction, direction, tick)
    stop_fill = _adverse_price(stop - direction * friction, -direction, tick)
    unit_risk = direction * (entry_price - stop_fill) * multiplier + 2 * fee
    reward_net = direction * (_adverse_price(target - direction * friction, -direction, tick) - entry_price) * multiplier - 2 * fee
    if reward_net <= 0 or unit_risk <= 0 or balance <= 0:
        return None
    risk_budget = balance * cfg["risk_pct"] / 100
    quantity = min(int(risk_budget // unit_risk), int(cfg["max_contracts"]))
    if quantity < 1:
        return None
    return {"direction": direction, "raw_entry": raw_entry, "entry_price": entry_price,
            "entry_index": index, "signal_time": observation["signal_time"], "quantity": quantity,
            "entry_fee": quantity * fee, "stop": stop, "target": target,
            "risk_amount": quantity * unit_risk, "risk_budget": risk_budget}


def simulate(bars, variant_id, symbol, *, config=None, start_date=None, end_date=None):
    """Risk-budgeted futures research, one actual entry per market/session."""
    if symbol not in SPECS:
        raise ValueError("Session research supports MES=F or MNQ=F")
    cfg, spec = _config(config), SPECS[symbol]
    observations = entry_decisions(bars, variant_id)
    multiplier, tick = spec["multiplier"], spec["tick_size"]
    fee = cfg["fee_per_contract_side"] * cfg["cost_multiplier"]
    friction = (cfg["slippage_ticks"] + cfg["spread_ticks"] / 2) * cfg["cost_multiplier"] * tick
    balance, position, traded_date = cfg["account_size"], None, None
    trades, curve = [], []

    def pnl_at(raw_price, include_exit_fee=True):
        fill = _adverse_price(raw_price - position["direction"] * friction, -position["direction"], tick)
        return position["direction"] * (fill - position["entry_price"]) * position["quantity"] * multiplier - (fee * position["quantity"] if include_exit_fee else 0)

    def close(raw_price, reason, index):
        nonlocal balance, position
        net_before_entry_fee = pnl_at(raw_price)
        net = net_before_entry_fee - position["entry_fee"]
        balance += net_before_entry_fee
        exit_price = _adverse_price(raw_price - position["direction"] * friction, -position["direction"], tick)
        gross = position["direction"] * (raw_price - position["raw_entry"]) * position["quantity"] * multiplier
        trades.append({"symbol": symbol, "variant": variant_id, "session_date": bars[index]["session_date"],
                       "direction": position["direction"], "signal_time": position["signal_time"],
                       "entry_time": bars[position["entry_index"]]["time"], "exit_bar_time": bars[index]["time"],
                       "exit_time_precision": "bar_open" if reason in ("session_flatten", "gap_stop", "gap_target") else "within_bar_unknown",
                       "quantity": position["quantity"], "contract_multiplier": multiplier,
                       "entry_notional": abs(position["raw_entry"] * position["quantity"] * multiplier),
                       "raw_entry": position["raw_entry"], "entry_price": position["entry_price"],
                       "raw_exit": raw_price, "exit_price": exit_price,
                       "stop": position["stop"], "target": position["target"], "gross_pnl": gross,
                       "net_pnl": net, "costs": gross - net, "entry_fee": position["entry_fee"],
                       "exit_fee": fee * position["quantity"], "planned_risk_amount": position["risk_amount"],
                       "risk_budget": position["risk_budget"], "r_multiple": net / position["risk_amount"],
                       "exit_reason": reason, "balance_after": balance, "mode": "historical_replay"})
        position = None

    for index, (bar, observation) in enumerate(zip(bars, observations)):
        date = bar["session_date"]
        if start_date and date < start_date or end_date and date >= end_date:
            continue
        if traded_date != date:
            if position:
                raise ValueError("Missing scheduled session-flatten opening; overnight carry forbidden")
            traded_date = None
        worst = best = balance
        if position:
            if bar["marker_only"]:
                opening_value = balance + pnl_at(bar["open"])
                worst, best = min(worst, opening_value), max(best, opening_value)
                close(bar["open"], "session_flatten", index)
            else:
                direction = position["direction"]
                gap_stop = bar["open"] <= position["stop"] if direction == 1 else bar["open"] >= position["stop"]
                gap_target = bar["open"] >= position["target"] if direction == 1 else bar["open"] <= position["target"]
                stop_hit = bar["low"] <= position["stop"] if direction == 1 else bar["high"] >= position["stop"]
                target_hit = bar["high"] >= position["target"] if direction == 1 else bar["low"] <= position["target"]
                raw_adverse = bar["open"] if gap_stop else position["target"] if gap_target else position["stop"] if stop_hit else bar["low"] if direction == 1 else bar["high"]
                raw_favorable = bar["open"] if gap_stop else position["target"] if target_hit or gap_target else bar["high"] if direction == 1 else bar["low"]
                worst, best = min(worst, balance + pnl_at(raw_adverse)), max(best, balance + pnl_at(raw_favorable))
                if gap_stop:
                    close(bar["open"], "gap_stop", index)
                elif gap_target:
                    close(position["target"], "gap_target", index)
                elif stop_hit:
                    close(position["stop"], "stop_first_collision" if target_hit else "stop", index)
                elif target_hit:
                    close(position["target"], "target", index)
        if position is None and traded_date != date and not bar["marker_only"] and observation["direction"]:
            position = _open_position(bar, observation, cfg, spec, balance, index)
            if position:
                direction, stop, target = position["direction"], position["stop"], position["target"]
                balance -= position["entry_fee"]
                traded_date = date
                stop_hit = bar["low"] <= stop if direction == 1 else bar["high"] >= stop
                target_hit = bar["high"] >= target if direction == 1 else bar["low"] <= target
                adverse = stop if stop_hit else bar["low"] if direction == 1 else bar["high"]
                favorable = target if target_hit else bar["high"] if direction == 1 else bar["low"]
                worst, best = min(worst, balance + pnl_at(adverse)), max(best, balance + pnl_at(favorable))
                if stop_hit:
                    close(stop, "stop_first_collision" if target_hit else "stop", index)
                elif target_hit:
                    close(target, "target", index)
        equity = balance + pnl_at(bar["close"]) if position else balance
        curve.append({"time": bar["time"], "session_date": date, "balance": balance, "equity": equity,
                      "worst_equity": min(worst, equity), "best_equity": max(best, equity),
                      "position_quantity": position["quantity"] if position else 0,
                      "position_notional": abs(bar["close"] * position["quantity"] * multiplier) if position else 0})
    if position:
        raise ValueError("Sample lacks the predeclared observed session-flatten opening; no invented boundary fill")
    profits = [trade["net_pnl"] for trade in trades]
    gains, losses = sum(value for value in profits if value > 0), -sum(value for value in profits if value < 0)
    peak, dd = cfg["account_size"], 0.0
    for point in curve:
        dd = max(dd, (peak - point["worst_equity"]) / peak * 100)
        peak = max(peak, point["equity"])
    return {"variant": variant_id, "symbol": symbol, "config": cfg, "trades": trades, "curve": curve,
            "metrics": {"net_profit": balance - cfg["account_size"], "return_pct": (balance / cfg["account_size"] - 1) * 100,
                        "total_trades": len(trades), "profit_factor": gains / losses if losses else None,
                        "max_drawdown_pct": dd, "costs": sum(trade["costs"] for trade in trades)},
            "qualified_for_live_trading": False,
            "limitations": ["Continuous Yahoo futures are not a fixed executable contract or verified broker quotes.",
                             "OHLC-volume VWAP is an explicit proxy, not trade-level VWAP.",
                             "Nominal prop balance is not margin or available drawdown; actual firm constraints remain separate.",
                             "Commission uses the advertised TopstepX MES/MNQ tariff; personal contract and spread/slippage assumptions remain unverified."]}
