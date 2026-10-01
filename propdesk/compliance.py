"""Replay the modeled equity path against explicit prop-account loss floors.

This is one uninterrupted holdout account, not a second challenge/payout model.
OHLC best-before-worst ordering is conservative for intraday trailing floors.
"""
from __future__ import annotations

import math
from datetime import datetime

from .risk import loss_floors, normalize_profile
from .timezones import timezone_for


def evaluate(curve, profile, trades=None):
    profile = normalize_profile(profile)
    result = {"status": "incomplete", "breaches": [], "reasons": [], "daily_loss_max": 0,
              "total_loss_max": 0, "target_first_reached": None, "minimum_trading_days_met": None,
              "best_day_share_pct": None, "consistency_met": None,
              "basis": "uninterrupted modeled holdout account; no challenge/funded resets",
              "warnings": ["OHLC-границы заменяют tick-путь; внутридневной пик перед просадкой выбран консервативно.",
                           "Дневной reset использует последний доступный бар перед сменой локальной даты; точный equity на reset неизвестен.",
                           "Переносы, новости, EA и реальные календарные ограничения требуют отдельной проверки."]}
    if not isinstance(curve, list) or not curve:
        result["reasons"].append("Нет полной equity-кривой для проверки правил")
        return result
    initial = profile["account_size"]
    timezone = timezone_for(profile["daily_reset_timezone"])
    high_water = day_balance = day_equity = previous_balance = previous_equity = initial
    current_day = None
    days = {}
    target = initial * (1 + profile["profit_target_pct"] / 100)
    try:
        previous_stamp = None
        for point in curve:
            stamp = datetime.fromisoformat(point["time"].replace("Z", "+00:00"))
            if stamp.tzinfo is None or (previous_stamp is not None and stamp <= previous_stamp):
                raise ValueError("Кривая должна быть в возрастающем времени с часовым поясом")
            previous_stamp = stamp
            values = [float(point[k]) for k in ("equity", "balance", "worst_equity", "best_equity")]
            if not all(math.isfinite(value) for value in values):
                raise ValueError("Кривая содержит неконечные значения")
            equity, balance, worst, best = values
            if worst > best:
                raise ValueError("worst_equity превышает best_equity")
            day = stamp.astimezone(timezone).date().isoformat()
            if day != current_day:
                if current_day is not None and profile["drawdown_type"] == "trailing_eod":
                    high_water = max(high_water, previous_equity)
                day_balance, day_equity = previous_balance, previous_equity
                current_day = day
            if profile["drawdown_type"] == "trailing_intraday":
                high_water = max(high_water, best, equity)
            account = {"balance": balance, "equity": equity,
                       "day_start_balance": day_balance, "day_start_equity": day_equity,
                       "high_water_equity": high_water}
            floors = loss_floors(profile, account)
            result["daily_loss_max"] = max(result["daily_loss_max"], floors["daily_reference"] - worst)
            result["total_loss_max"] = max(result["total_loss_max"], floors["total_reference"] - worst)
            for kind, floor in (("daily", floors["daily_floor"]), ("total", floors["total_floor"])):
                if worst <= floor and not any(b["type"] == kind for b in result["breaches"]):
                    result["breaches"].append({"type": kind, "time": point["time"],
                                                "worst_equity": round(worst, 6), "floor": round(floor, 6)})
            if equity >= target and result["target_first_reached"] is None:
                result["target_first_reached"] = point["time"]
            days[day] = balance - day_balance
            previous_balance, previous_equity = balance, equity
    except (ValueError, KeyError, TypeError, OverflowError) as exc:
        result["reasons"].append(f"Неполная проверка equity-кривой: {exc}")
        return result
    if trades is not None:
        active_days = {datetime.fromisoformat(t["entry_time"].replace("Z", "+00:00")).astimezone(timezone).date()
                       for t in trades}
        result["trading_days"] = len(active_days)
        result["minimum_trading_days_met"] = len(active_days) >= profile["min_trading_days"]
    net_profit = previous_balance - initial
    if net_profit > 0:
        share = max(0, max(days.values(), default=0)) / net_profit * 100
        result["best_day_share_pct"] = round(share, 4)
        result["consistency_met"] = profile["best_day_pct"] is None or share <= profile["best_day_pct"]
    result["status"] = "breach" if result["breaches"] else "pass"
    if result["breaches"]:
        result["reasons"] = [f"На holdout достигнут {b['type']} лимит в {b['time']}" for b in result["breaches"]]
    result["daily_loss_max"] = round(max(0, result["daily_loss_max"]), 6)
    result["total_loss_max"] = round(max(0, result["total_loss_max"]), 6)
    result["verified_real_account"] = False
    return result
