"""Conservative, explicit paper-trading checks for user-supplied prop rules.

Percentages are percentages, not fractions. Daily loss defaults to the larger
of start-of-day balance and equity, less a fixed percentage of original account
size; daily_reference_basis selects a different explicit baseline. Trailing allowances also use original size; trailing EOD high-water input
must be the previous completed daily close. Fee and slippage basis points are
per side; spread basis points are the full spread. fee_per_unit is cash per unit
per side, matching the research engine. This checker does not authorize live orders.
"""
from __future__ import annotations

import math
from datetime import datetime
from zoneinfo import ZoneInfoNotFoundError

from .timezones import timezone_for


_ACTIVITY_FIELDS = ("news_allowed", "overnight_allowed", "weekend_allowed", "ea_allowed")


def _number(value, name, minimum=0.0, maximum=None, allow_none=False):
    # Bounded finite inputs also keep all downstream arithmetic finite.
    if maximum is None:
        maximum = 1e12
    if value is None and allow_none:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{name}: требуется число, не boolean")
    try:
        result = float(value)
    except (ValueError, TypeError):
        raise ValueError(f"{name}: требуется конечное число") from None
    if not math.isfinite(result) or result < minimum or (maximum is not None and result > maximum):
        raise ValueError(f"{name}: недопустимое число")
    return result


def _integer(value, name, minimum=0, maximum=100000):
    result = _number(value, name, minimum, maximum)
    if result != int(result):
        raise ValueError(f"{name}: требуется целое число")
    return int(result)


def normalize_profile(payload: dict) -> dict:
    """Validate a complete or partial custom profile without inventing verification."""
    if not isinstance(payload, dict):
        raise ValueError("Профиль должен быть объектом")
    defaults = {
        "id": "custom", "name": "Пользовательский профиль", "account_size": 100000,
        "challenge_fee": 0, "profit_target_pct": 8, "daily_loss_pct": 5,
        "max_loss_pct": 10, "drawdown_type": "static", "payout_split_pct": 80,
        "min_trading_days": 5, "max_calendar_days": 60, "best_day_pct": None,
        "daily_reset_timezone": "UTC", "verified_at": None, "source_url": "",
        "status": "illustrative", "risk_buffer_amount": 1.0, "max_risk_pct": 1.0,
        "quantity_step": 0.01, "challenge_required": True,
        "daily_reference_basis": "max_balance_equity", "trailing_cap_at_initial": False,
    }
    defaults.update({key: None for key in _ACTIVITY_FIELDS})
    profile = {key: payload.get(key, value) for key, value in defaults.items()}
    for key in ("id", "name", "source_url", "daily_reset_timezone"):
        if not isinstance(profile[key], str):
            raise ValueError(f"{key}: требуется строка")
    if not profile["id"].strip() or not profile["name"].strip():
        raise ValueError("Название и id профиля не могут быть пустыми")
    profile["account_size"] = _number(profile["account_size"], "account_size", 0.01)
    profile["challenge_fee"] = _number(profile["challenge_fee"], "challenge_fee")
    for key in ("profit_target_pct", "daily_loss_pct", "max_loss_pct", "max_risk_pct"):
        profile[key] = _number(profile[key], key, 0.000001, 100)
    profile["payout_split_pct"] = _number(profile["payout_split_pct"], "payout_split_pct", 0, 100)
    if profile["best_day_pct"] == "":
        profile["best_day_pct"] = None
    profile["best_day_pct"] = _number(profile["best_day_pct"], "best_day_pct", 0.000001, 100, True)
    profile["risk_buffer_amount"] = _number(profile["risk_buffer_amount"], "risk_buffer_amount")
    profile["quantity_step"] = _number(profile["quantity_step"], "quantity_step", 0.000000001)
    profile["min_trading_days"] = _integer(profile["min_trading_days"], "min_trading_days", 0, 3650)
    profile["max_calendar_days"] = _integer(profile["max_calendar_days"], "max_calendar_days", 1, 3650) if profile["max_calendar_days"] is not None else None
    if profile["daily_reference_basis"] not in ("max_balance_equity", "balance", "equity", "initial"):
        raise ValueError("Неизвестный daily_reference_basis")
    if not isinstance(profile["trailing_cap_at_initial"], bool):
        raise ValueError("trailing_cap_at_initial: требуется boolean")
    if profile["drawdown_type"] not in ("static", "trailing_eod", "trailing_intraday"):
        raise ValueError("Неизвестный тип drawdown")
    if profile["status"] not in ("illustrative", "user_verified"):
        raise ValueError("status должен быть illustrative или user_verified")
    if profile["verified_at"] is not None:
        if not isinstance(profile["verified_at"], str):
            raise ValueError("verified_at: требуется ISO дата или null")
        try:
            datetime.fromisoformat(profile["verified_at"].replace("Z", "+00:00"))
        except ValueError:
            raise ValueError("verified_at: требуется ISO дата или null") from None
    if not isinstance(profile["challenge_required"], bool):
        raise ValueError("challenge_required: требуется boolean")
    for key in _ACTIVITY_FIELDS:
        if profile[key] is not None and not isinstance(profile[key], bool):
            raise ValueError(f"{key}: допустимы true, false или null (неизвестно)")
    try:
        timezone_for(profile["daily_reset_timezone"])
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError("daily_reset_timezone: неизвестный часовой пояс IANA") from None
    return profile


def default_profiles() -> list[dict]:
    """Educational examples only: these do not describe or verify any real firm."""
    common = {"status": "illustrative", "verified_at": None, "source_url": "", "ea_allowed": True,
              "news_allowed": False, "overnight_allowed": True, "weekend_allowed": False}
    return [
        normalize_profile({**common, "id": "generic-static", "name": "Учебный: статический лимит (одна фаза)",
                           "account_size": 100000, "challenge_fee": 500, "profit_target_pct": 8,
                           "daily_loss_pct": 5, "max_loss_pct": 10, "drawdown_type": "static",
                           "payout_split_pct": 80, "min_trading_days": 5, "max_calendar_days": 60}),
        normalize_profile({**common, "id": "generic-futures", "name": "Учебный: futures / trailing EOD",
                           "account_size": 50000, "challenge_fee": 150, "profit_target_pct": 6,
                           "daily_loss_pct": 3, "max_loss_pct": 5, "drawdown_type": "trailing_eod",
                           "payout_split_pct": 90, "min_trading_days": 5, "max_calendar_days": 45,
                           "quantity_step": 1, "overnight_allowed": False}),
        normalize_profile({**common, "id": "generic-consistency", "name": "Учебный: instant / consistency",
                           "account_size": 25000, "challenge_fee": 350, "profit_target_pct": 1,
                           "daily_loss_pct": 3, "max_loss_pct": 6, "drawdown_type": "static",
                           "payout_split_pct": 80, "min_trading_days": 5, "max_calendar_days": 60,
                           "best_day_pct": 25, "challenge_required": False}),
    ]


def loss_floors(profile: dict, account: dict) -> dict:
    """Reusable floor math; EOD high water is caller's previous day close maximum."""
    initial = profile["account_size"]
    balance = account["balance"]
    equity = account["equity"]
    day_reference = {"max_balance_equity": max(account["day_start_balance"], account["day_start_equity"]),
                     "balance": account["day_start_balance"], "equity": account["day_start_equity"],
                     "initial": initial}[profile["daily_reference_basis"]]
    daily_floor = day_reference - initial * profile["daily_loss_pct"] / 100
    high_water = max(initial, account["high_water_equity"])
    if profile["drawdown_type"] == "trailing_intraday":
        high_water = max(high_water, equity, balance)
    total_reference = initial if profile["drawdown_type"] == "static" else high_water
    total_floor = total_reference - initial * profile["max_loss_pct"] / 100
    if profile["drawdown_type"] != "static" and profile["trailing_cap_at_initial"]:
        total_floor = min(total_floor, initial)
    return {"daily_floor": daily_floor, "total_floor": total_floor, "daily_reference": day_reference,
            "total_reference": total_reference, "daily_remaining": equity - daily_floor,
            "total_remaining": equity - total_floor, "high_water_equity": high_water}


def check_trade(profile: dict, account: dict, trade: dict) -> dict:
    """Check worst-case stop risk plus adverse costs against confirmed rules.

    Quantity omitted means size a paper proposal up to the budget in the supplied
    quantity_step. A supplied zero quantity is rejected. Existing open_risk is
    reserved in addition to current equity (do not subtract it from equity too).
    """
    result = {"allowed": False, "decision": "BLOCK", "reasons": [], "warnings": [],
              "risk_amount": None, "risk_pct": None, "quantity": None, "max_safe_quantity": None,
              "daily_remaining": None, "total_remaining": None, "effective_budget": None,
              "rule_checks": {}}
    try:
        profile = normalize_profile(profile)
        if not isinstance(account, dict) or not isinstance(trade, dict):
            raise ValueError("Счёт и сделка должны быть объектами")
        for key in ("balance", "equity", "day_start_balance", "day_start_equity"):
            if key not in account:
                raise ValueError(f"{key}: требуется актуальный снимок счёта")
        if profile["drawdown_type"] != "static" and "high_water_equity" not in account:
            raise ValueError("high_water_equity: требуется подтверждённый исторический максимум")
        balance = _number(account.get("balance"), "balance")
        equity = _number(account.get("equity", balance), "equity")
        values = {"balance": balance, "equity": equity,
                  "day_start_balance": _number(account.get("day_start_balance", balance), "day_start_balance"),
                  "day_start_equity": _number(account.get("day_start_equity", balance), "day_start_equity"),
                  "high_water_equity": _number(account.get("high_water_equity", max(profile["account_size"], balance, equity)), "high_water_equity"),
                  "open_risk": _number(account.get("open_risk", 0), "open_risk"),
                  "realized_today": _number(account.get("realized_today", 0), "realized_today", -1e12),
                  "trading_days": _integer(account.get("trading_days", 0), "trading_days")}
        entry = _number(trade.get("entry"), "entry", 0.000000001)
        stop = _number(trade.get("stop"), "stop", 0.000000001)
        target = _number(trade.get("target"), "target", 0.000000001)
        multiplier = _number(trade.get("contract_multiplier", 1), "contract_multiplier", 0.000000001, 1e9)
        requested_pct = _number(trade.get("risk_pct", 0.25), "risk_pct", 0.000000001, 100)
        costs = {key: _number(trade.get(key, 0), key, 0, 10000) for key in ("spread_bps", "fee_bps", "slippage_bps")}
        fee_per_unit = _number(trade.get("fee_per_unit", 0), "fee_per_unit")
        side = trade.get("side", "long")
        if side not in ("long", "short", "buy", "sell"):
            raise ValueError("side: допустимы long или short")
        long = side in ("long", "buy")
        if (long and not stop < entry < target) or (not long and not target < entry < stop):
            raise ValueError("Стоп и цель должны лежать по правильные стороны цены входа")
        for key in ("news_window", "hold_overnight", "hold_weekend", "is_automated"):
            if key in trade and not isinstance(trade[key], bool):
                raise ValueError(f"{key}: требуется boolean")
        floors = loss_floors(profile, values)
        buffer = profile["risk_buffer_amount"]
        daily_available = floors["daily_remaining"] - values["open_risk"] - buffer
        total_available = floors["total_remaining"] - values["open_risk"] - buffer
        requested_budget = profile["account_size"] * min(requested_pct, profile["max_risk_pct"]) / 100
        budget = max(0.0, min(requested_budget, daily_available, total_available))
        unit_price_risk = abs(entry - stop) * multiplier
        roundtrip_cost_bps = costs["spread_bps"] + 2 * costs["fee_bps"] + 2 * costs["slippage_bps"]
        unit_cost = entry * multiplier * roundtrip_cost_bps / 10000 + 2 * fee_per_unit
        unit_risk = unit_price_risk + unit_cost
        step = profile["quantity_step"]
        safe_quantity = max(0.0, math.floor(min(budget / unit_risk, 1e12) / step + 1e-12) * step)
        quantity = _number(trade["quantity"], "quantity", 0.000000001) if "quantity" in trade else safe_quantity
        risk = unit_risk * quantity
        checks = {**floors, "buffer_amount": buffer, "open_risk_reserved": values["open_risk"],
                  "requested_risk_budget": requested_budget, "daily_available_after_reserves": daily_available,
                  "total_available_after_reserves": total_available, "unit_price_risk": unit_price_risk,
                  "unit_roundtrip_cost": unit_cost, "roundtrip_cost_bps": roundtrip_cost_bps,
                  "fee_per_unit_per_side": fee_per_unit, "roundtrip_fixed_fee_per_unit": 2 * fee_per_unit,
                  "cost_definitions": {"fee_bps": "per side", "slippage_bps": "per side",
                                       "spread_bps": "full spread", "fee_per_unit": "cash per quantity unit per side"},
                  "rules_confirmed": account.get("confirmed_rules") is True,
                  "daily_reference_basis": profile["daily_reference_basis"],
                  "daily_reference_definition": "selected start-of-day reference - original_size * daily_loss_pct",
                  "trailing_definition": "high_water - original_size * max_loss_pct; capped at initial balance only when explicitly enabled",
                  "trailing_cap_at_initial": profile["trailing_cap_at_initial"],
                  "timezone": profile["daily_reset_timezone"], "live_execution_authorized": False}
        result.update({"risk_amount": round(risk, 8), "risk_pct": round(risk / profile["account_size"] * 100, 8),
                       "quantity": round(quantity, 8), "max_safe_quantity": round(safe_quantity, 8),
                       "daily_remaining": round(floors["daily_remaining"], 8),
                       "total_remaining": round(floors["total_remaining"], 8),
                       "effective_budget": round(budget, 8), "rule_checks": checks})
        reasons = result["reasons"]
        if account.get("confirmed_rules") is not True:
            reasons.append("Подтвердите актуальные правила в личном кабинете фирмы; примеры не являются проверенными правилами")
        for activity, rule in (("news_window", "news_allowed"), ("hold_overnight", "overnight_allowed"),
                               ("hold_weekend", "weekend_allowed"), ("is_automated", "ea_allowed")):
            active = trade.get(activity, False)
            checks[rule] = {"requested": active, "allowed": profile[rule]}
            if active and profile[rule] is not True:
                reasons.append(f"{activity}: активность запрещена или правило не подтверждено ({rule})")
        if requested_pct > profile["max_risk_pct"]:
            reasons.append("Запрошенный риск превышает установленный лимит риска на сделку")
        if floors["daily_remaining"] <= 0:
            reasons.append("Дневной лимит уже достигнут или нарушен")
        if floors["total_remaining"] <= 0:
            reasons.append("Общий лимит уже достигнут или нарушен")
        if quantity <= 0 or safe_quantity <= 0:
            reasons.append("Нет допустимого размера позиции с учётом шага объёма и резерва")
        if abs(quantity / step - round(quantity / step)) > 1e-7:
            reasons.append("Объём не соответствует шагу quantity_step")
        if risk > budget + 1e-8:
            reasons.append("Убыток до стопа с издержками превышает доступный бюджет")
        if risk + values["open_risk"] >= min(floors["daily_remaining"], floors["total_remaining"]):
            reasons.append("Суммарный открытый риск достигает границы drawdown; касание считается нарушением")
        if profile["status"] == "user_verified" and (not profile["source_url"].strip() or not profile["verified_at"]):
            result["warnings"].append("Пользователь отметил правила как проверенные, но source_url или verified_at отсутствует")
        if profile["status"] == "illustrative":
            result["warnings"].append("Учебный профиль: реальная фирма и её правила не проверены")
        if profile["drawdown_type"] == "trailing_eod":
            result["warnings"].append("high_water_equity должен отражать максимум завершённых дней, без текущего внутридневного пика")
        if profile["best_day_pct"] is not None:
            result["warnings"].append("Consistency оценивается по всей дневной истории; эта проверка не подтверждает доступность выплаты")
        result["warnings"].append("Стоп не гарантирует цену исполнения; гэп может превысить заданное проскальзывание")
        result["allowed"] = not reasons
        result["decision"] = "ALLOW_PAPER" if result["allowed"] else "BLOCK"
    except (ValueError, TypeError, OverflowError) as error:
        result["reasons"].append(str(error))
    return result
