"""Causal gold-session hypotheses on a futures OHLC price proxy.

Quantities are modeled XAU/USD ounces, never MGC futures contracts. This
reference simulation cannot certify broker quotes, fills or prop rules.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
import math
from pathlib import Path
from zoneinfo import ZoneInfo


def _pinned_zone(name):
    path = Path(__file__).resolve().parent / "tzdata" / name
    with path.open("rb") as stream:
        return ZoneInfo.from_file(stream, key=name)


LONDON = _pinned_zone("Europe/London")
NEW_YORK = _pinned_zone("America/New_York")
CONTRACT_OUNCES = 100.0
LOT_STEP = .01  # Explicit model assumption: absent from the official metadata.
MIN_OUNCES = CONTRACT_OUNCES * LOT_STEP
MAX_LOTS = 100.0
SWING_LEVERAGE = 15.0
COMMISSION_RATE = .0014 / 100  # Published percent field; conservative per SIDE.
SPREAD_PER_OUNCE = .40
SLIPPAGE_PER_SIDE = .10


def variants():
    return [
        {"id": f"XAUUSD_{session}_{family}_{context}_{risk}_{rr}_{hold}",
         "symbol": "XAUUSD", "session": session, "family": family,
         "context": context, "risk": risk, "reward_risk": rr,
         "hold_hours": hold}
        for session in ("london", "us")
        for family in ("breakout", "rejection", "drift")
        for context in ("none", "prior_trend")
        for risk in (.005, .01) for rr in (1, 2) for hold in (3, 6)
    ]


def stamp(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Timezone-aware bar opening times required")
    return result.astimezone(timezone.utc)


def _session(variant):
    if variant["session"] == "london":
        return LONDON, tuple(range(6)), (7, 8, 9), 15
    return NEW_YORK, (8, 9, 10), (11, 12, 13), 16


def validate(bars):
    previous = None
    for bar in bars:
        time = stamp(bar["time"])
        values = [float(bar[key]) for key in ("open", "high", "low", "close")]
        if previous is not None and time <= previous:
            raise ValueError("Strictly ordered unique quote times required")
        if not all(math.isfinite(value) and value > 0 for value in values):
            raise ValueError("Finite positive OHLC required")
        opening, high, low, closing = values
        if not low <= min(opening, closing) <= max(opening, closing) <= high:
            raise ValueError("Invalid OHLC envelope")
        if time.second or time.microsecond:
            raise ValueError("Minute-anchored source quotes required")
        previous = time


def pnl(ounces, side, entry, exit_price):
    return ounces * side * (exit_price - entry)


def commission(ounces, fill_price, cost_multiplier=1.0):
    return ounces * fill_price * COMMISSION_RATE * cost_multiplier


def source_coverage(bars, variant, begin, finish):
    """Diagnostics only: future window completeness never determines an entry."""
    begin, finish = stamp(begin), stamp(finish)
    zone, range_hours, signal_hours, flat_hour = _session(variant)
    times = [stamp(bar["time"]) for bar in bars]
    by_date = defaultdict(set)
    unusual = []
    for time in times:
        if begin <= time < finish and time.minute:
            unusual.append(time.isoformat())
        local = time.astimezone(zone)
        if not local.minute:
            by_date[local.date().isoformat()].add(local.hour)
    calendar = []
    day = begin.astimezone(zone).date()
    last_day = (finish - timedelta(microseconds=1)).astimezone(zone).date()
    expected = set(range(min(range_hours), flat_hour))
    while day <= last_day:
        first_entry = datetime(day.year, day.month, day.day,
                               signal_hours[0] + 1, tzinfo=zone).astimezone(timezone.utc)
        if day.weekday() < 5 and begin <= first_entry < finish:
            missing = sorted(expected - by_date[day.isoformat()])
            calendar.append({"local_date": day.isoformat(), "missing_hours": missing,
                             "status": "partial_or_unobserved" if missing else "observed_complete"})
        day += timedelta(days=1)
    return {
        "source_spans_declared_window": bool(times and times[0] <= begin and
                                               times[-1] + timedelta(hours=1) >= finish),
        "timezone": zone.key, "broker_calendar_verified": False,
        "weekdays": len(calendar),
        "complete_windows": sum(row["status"] == "observed_complete" for row in calendar),
        "missing_or_partial_windows": [row for row in calendar if row["missing_hours"]],
        "nonaligned_quote_times": unusual,
        "calendar_dates": calendar,
    }


def decisions(bars, variant):
    """Decisions use completed bars; execution times do not inspect future rows."""
    validate(bars)
    if variant not in variants():
        raise ValueError("Unregistered metal variant")
    zone, range_hours, signal_hours, flat_hour = _session(variant)
    history_by_day = defaultdict(dict)
    true_ranges, closes, result = [], [], {}
    previous_observed_close = None
    for index, bar in enumerate(bars):
        time = stamp(bar["time"])
        local = time.astimezone(zone)
        if local.minute:
            # An unsupported partial-hour marker is current quote information,
            # not an hourly indicator observation or a future whole-date filter.
            continue
        history = history_by_day[local.date().isoformat()]
        atr = sum(true_ranges[-14:]) / 14 if len(true_ranges) >= 14 else None
        complete_range = all(hour in history for hour in range_hours)
        prior_trend = closes[-1] - sum(closes[-24:]) / 24 if len(closes) >= 24 else None
        if local.weekday() < 5 and atr and complete_range and local.hour in signal_hours:
            reference = [history[hour] for hour in range_hours]
            high = max(float(row["high"]) for row in reference)
            low = min(float(row["low"]) for row in reference)
            side = 0
            if .5 * atr <= high - low <= 6 * atr:
                if variant["family"] == "breakout":
                    side = 1 if bar["close"] > high else -1 if bar["close"] < low else 0
                elif variant["family"] == "rejection":
                    upper = bar["high"] > high + .05 * atr and low < bar["close"] < high
                    lower = bar["low"] < low - .05 * atr and low < bar["close"] < high
                    side = (-1 if upper else 1 if lower else 0) if not (upper and lower) else 0
                elif local.hour == signal_hours[0]:
                    drift = reference[-1]["close"] - reference[0]["open"]
                    side = 1 if drift > .5 * atr else -1 if drift < -.5 * atr else 0
                if variant["context"] == "prior_trend" and (
                    prior_trend is None or not side or side * prior_trend <= 0
                ):
                    side = 0
            if side:
                if variant["family"] == "breakout":
                    stop = low - .1 * atr if side > 0 else high + .1 * atr
                elif variant["family"] == "rejection":
                    stop = bar["low"] - .1 * atr if side > 0 else bar["high"] + .1 * atr
                else:
                    stop = bar["close"] - side * atr
                execute = time + timedelta(hours=1)
                deadline = datetime(local.year, local.month, local.day,
                                    flat_hour, tzinfo=zone).astimezone(timezone.utc)
                result[execute.isoformat()] = {
                    "side": side, "stop": stop, "known_at": execute.isoformat(),
                    "signal_bar": index, "reference_high": high, "reference_low": low,
                    "atr": atr, "prior_trend": prior_trend, "reason": variant["family"],
                    "session_day": local.date().isoformat(), "flat_at": deadline.isoformat(),
                }
        if local.weekday() < 5:
            history[local.hour] = bar
        last_close = previous_observed_close if previous_observed_close is not None else bar["open"]
        true_ranges.append(max(bar["high"] - bar["low"],
                               abs(bar["high"] - last_close), abs(bar["low"] - last_close)))
        closes.append(float(bar["close"]))
        previous_observed_close = float(bar["close"])
    return result


def simulate(bars, variant, begin, finish, *, capital=100_000.0, cost_multiplier=1.0):
    if not all(math.isfinite(value) and value > 0 for value in (capital, cost_multiplier)):
        raise ValueError("Positive finite capital and costs required")
    begin, finish = stamp(begin), stamp(finish)
    if finish <= begin or any(time.hour or time.minute or time.second or time.microsecond
                              for time in (begin, finish)):
        raise ValueError("Ordered UTC calendar-midnight evaluation boundaries required")
    # Later-period strategy decisions are never computed by a TRAIN run.
    history = [bar for bar in bars if stamp(bar["time"]) < finish]
    signals = decisions(history, variant)
    coverage = source_coverage(bars, variant, begin.isoformat(), finish.isoformat())
    friction = (SPREAD_PER_OUNCE / 2 + SLIPPAGE_PER_SIDE) * cost_multiplier
    fee_rate = COMMISSION_RATE * cost_multiplier
    cash, position = float(capital), None
    trades, curve, gaps = [], [], []
    daily_close, daily_worst, daily_best = {}, {}, {}
    used_dates = set()
    previous_quote, previous_exposure_end = None, None

    def exit_fill(price, side):
        fill = price - side * friction
        if fill <= 0 or not math.isfinite(fill):
            raise ValueError("Modeled friction requires a positive executable quote")
        return fill

    def mark(price):
        fill = exit_fill(price, position["side"])
        return cash + pnl(position["ounces"], position["side"], position["entry"], fill) - fee_rate * position["ounces"] * fill

    def close(price, when, reason, *, precision="known_open", interval_start=None):
        nonlocal cash, position
        fill = exit_fill(price, position["side"])
        gross = pnl(position["ounces"], position["side"], position["entry"], fill)
        exit_fee = fee_rate * position["ounces"] * fill
        cash += gross - exit_fee
        trades.append({**position, "expiry": position["expiry"].isoformat(),
                       "exit": fill, "exit_time": when.isoformat(), "exit_reason": reason,
                       "exit_time_precision": precision,
                       "exit_interval_start": (interval_start or when).isoformat(),
                       "exit_interval_end": when.isoformat(), "price_pnl": gross,
                       "exit_fee": exit_fee, "net_pnl": gross - exit_fee - position["entry_fee"]})
        position = None

    active_rows = [(index, bar) for index, bar in enumerate(history)
                   if begin <= stamp(bar["time"]) < finish]
    for row_number, (index, bar) in enumerate(active_rows):
        time = stamp(bar["time"])
        closing_time = time + timedelta(hours=1)
        before = cash
        worst = best = cash
        if previous_exposure_end and time < previous_exposure_end:
            gaps.append({"observed_at": time.isoformat(), "reason": "overlapping_exposure_interval",
                         "previous_nominal_end": previous_exposure_end.isoformat()})
        if position:
            missing = previous_quote is None or time - previous_quote != timedelta(hours=1) or time.minute
            if missing:
                gaps.append({"observed_at": time.isoformat(), "reason": "unsupported_active_quote_interval",
                             "previous_quote": previous_quote.isoformat() if previous_quote else None})
                close(bar["open"], time, "unobserved_interval_exit")
            else:
                side = position["side"]
                stop_at_open = bar["open"] <= position["stop"] if side > 0 else bar["open"] >= position["stop"]
                target_at_open = bar["open"] >= position["target"] if side > 0 else bar["open"] <= position["target"]
                if stop_at_open:
                    close(bar["open"], time, "gap_stop")
                elif target_at_open:
                    # A resting favorable limit is known before the later bar's
                    # unknown high/low order. No favorable gap improvement assumed.
                    close(position["target"], time, "target_at_open")
                elif time >= position["expiry"]:
                    close(bar["open"], time, "time_exit")
        signal = signals.get(time.isoformat())
        if (position is None and cash > 0 and signal and not time.minute
                and signal["session_day"] not in used_dates and time < stamp(signal["flat_at"])):
            side, stop = signal["side"], signal["stop"]
            entry = bar["open"] + side * friction
            # Invalidation must still be intact at the actual raw entry quote.
            if entry > 0 and side * (bar["open"] - stop) > 0 and stop > friction:
                stopped_fill = exit_fill(stop, side)
                loss_per_ounce = abs(side * (stopped_fill - entry)) + fee_rate * (entry + stopped_fill)
                risk_budget = cash * variant["risk"]
                risk_size = risk_budget / loss_per_ounce
                margin_size = cash / (entry / SWING_LEVERAGE + fee_rate * entry)
                ounces = math.floor(min(risk_size, margin_size, MAX_LOTS * CONTRACT_OUNCES) / MIN_OUNCES) * MIN_OUNCES
                if ounces >= MIN_OUNCES:
                    entry_fee = fee_rate * ounces * entry
                    cash -= entry_fee
                    position = {
                        "ounces": ounces, "lots": ounces / CONTRACT_OUNCES, "side": side,
                        "entry": entry, "stop": stop,
                        "target": entry + side * variant["reward_risk"] * abs(entry - stop),
                        "entry_time": time.isoformat(), "known_at": signal["known_at"],
                        "entry_fee": entry_fee, "initial_margin": ounces * entry / SWING_LEVERAGE,
                        "risk_budget": risk_budget, "modeled_stop_loss": ounces * loss_per_ounce,
                        "expiry": min(time + timedelta(hours=variant["hold_hours"]), stamp(signal["flat_at"])),
                        "session_day": signal["session_day"], "reason": signal["reason"],
                    }
                    used_dates.add(signal["session_day"])
        held_during_bar = position is not None
        if position:
            side = position["side"]
            favorable = bar["high"] if side > 0 else bar["low"]
            adverse = bar["low"] if side > 0 else bar["high"]
            # Full candle marks are conservative exposure bounds, not known
            # actual mark chronology or post-stop broker account equity.
            worst = min(worst, mark(adverse))
            best = max(best, mark(favorable))
            stop_hit = adverse <= position["stop"] if side > 0 else adverse >= position["stop"]
            target_hit = favorable >= position["target"] if side > 0 else favorable <= position["target"]
            if stop_hit:
                close(position["stop"], closing_time, "stop_first", precision="intrabar_unknown", interval_start=time)
            elif target_hit:
                close(position["target"], closing_time, "target", precision="intrabar_unknown", interval_start=time)
            elif closing_time >= position["expiry"]:
                close(bar["close"], closing_time, "scheduled_close", precision="known_close")
            elif row_number + 1 == len(active_rows):
                close(bar["close"], closing_time, "boundary_close", precision="known_close")
        equity = mark(bar["close"]) if position else cash
        worst, best = min(worst, cash, equity), max(best, before, cash, equity)
        day = (closing_time - timedelta(microseconds=1)).date().isoformat()
        daily_close[day] = equity
        daily_worst[day] = min(daily_worst.get(day, math.inf), worst)
        daily_best[day] = max(daily_best.get(day, -math.inf), best)
        curve.append({"time": closing_time.isoformat(), "balance": cash, "equity": equity,
                      "worst_equity": worst, "best_equity": best})
        previous_quote = time
        previous_exposure_end = closing_time if held_during_bar else None
    if position:
        raise ValueError("Open boundary position lacks a modeled exit quote")
    dates, returns, worsts, peaks = [], [], [], []
    prior = capital
    day = begin.date()
    while day < finish.date():
        key = day.isoformat()
        closing = daily_close.get(key, prior)
        dates.append(key)
        returns.append(closing / prior - 1 if prior > 0 else None)
        worsts.append(daily_worst.get(key, closing))
        peaks.append(daily_best.get(key, closing))
        prior = closing
        day += timedelta(days=1)
    return {
        "variant": variant, "dates": dates, "daily_returns": returns,
        "daily_worst_equity": worsts, "daily_peak_equity": peaks,
        "final_equity": cash, "trades": trades, "completed_episodes": len(trades), "curve": curve,
        "insolvent": cash <= 0 or any(value <= 0 for value in worsts),
        "source_coverage": coverage, "missing_exposure_exits": gaps,
        "reconciliation_error": cash - capital - math.fsum(trade["net_pnl"] for trade in trades),
        "quantity_unit": "modeled gold ounces;100oz per modeled CFD lot, not MGC contracts",
        "mark_basis": "conservative hypothetical liquidation including spread/slip and estimated exit commission",
        "live_qualified": False, "prop_qualified": False, "futures_price_proxy": True,
    }
