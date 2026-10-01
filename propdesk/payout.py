"""Empirical first-payout economics; not a forecast of actual firm acceptance.

Net R observations must come from the out-of-sample evaluation. A deterministic
moving-block bootstrap preserves five adjacent trade returns. Returns include
all market costs; they are rescaled using fixed initial-size risk. Challenge and
funded accounts are separate stages, each with fresh balance and high water.
Completed-trade frequency can be fractional and is inferred from timestamped
OOS trades when not explicitly supplied; returns are never forced into 3/day
for a timestamped daily strategy.
"""
from __future__ import annotations

import random
from datetime import date, datetime, timedelta, timezone

from .risk import normalize_profile, loss_floors, _number, _integer


def _quantile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    position = probability * (len(ordered) - 1)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _extract_returns(trades, config):
    if not isinstance(trades, list):
        raise ValueError("trades: требуется массив сделок с net_r")
    if len(trades) > 50000:
        raise ValueError("Не более 50 000 сделок на один расчёт")
    samples = []
    every_row_oos = True
    has_excursions = True
    for index, trade in enumerate(trades):
        if not isinstance(trade, dict):
            raise ValueError(f"trades[{index}]: требуется объект с net_r")
        key = next((key for key in ("net_r", "return_r", "r") if key in trade), None)
        if key is None:
            raise ValueError(f"trades[{index}]: отсутствует net_r / return_r / r")
        value = _number(trade[key], f"trades[{index}].{key}", -1e6, 1e6)
        row_oos = trade.get("out_of_sample") is True or trade.get("split") in ("oos", "test", "out_of_sample")
        every_row_oos = every_row_oos and row_oos
        # MAE is a nonnegative R loss magnitude, independent of terminal return.
        mae = _number(trade.get("mae_r"), f"trades[{index}].mae_r", 0, 1e6, True)
        mfe = _number(trade.get("mfe_r"), f"trades[{index}].mfe_r", 0, 1e6, True)
        if mae is None or mfe is None:
            has_excursions = False
        samples.append({"r": value, "mae": mae, "mfe": mfe})
    return samples, config.get("returns_are_oos") is True or (bool(samples) and every_row_oos), has_excursions


def _block_stream(samples, rng, length=5):
    """Contiguous non-wrapping blocks keep clusters without treating tail as head."""
    width = min(length, len(samples))
    while True:
        start = rng.randrange(len(samples) - width + 1)
        for sample in samples[start:start + width]:
            yield sample


def _business_day_count(first, last):
    """Inclusive weekday count without a loop across the full historical range."""
    span = (last - first).days + 1
    if span <= 0:
        return 0
    weeks, remainder = divmod(span, 7)
    return weeks * 5 + sum((first + timedelta(days=i)).weekday() < 5 for i in range(remainder))


def _observed_cadence(trades):
    """Estimate completed-trade cadence from the full timestamped sample span.

    This is a throughput estimate, not a reconstruction of simultaneous holdings
    or time spent exposed. A partial timestamp history cannot justify inference.
    """
    timestamps = []
    for trade in trades:
        try:
            entry_value, exit_value = trade["entry_time"], trade["exit_time"]
            if not isinstance(entry_value, str) or not isinstance(exit_value, str):
                return None
            entry = datetime.fromisoformat(entry_value.replace("Z", "+00:00"))
            exit_at = datetime.fromisoformat(exit_value.replace("Z", "+00:00"))
            entry = entry.replace(tzinfo=timezone.utc) if entry.tzinfo is None else entry.astimezone(timezone.utc)
            exit_at = exit_at.replace(tzinfo=timezone.utc) if exit_at.tzinfo is None else exit_at.astimezone(timezone.utc)
            if exit_at < entry:
                return None
            timestamps.append((entry, exit_at))
        except (KeyError, ValueError, TypeError, OverflowError):
            return None
    if not timestamps:
        return None
    first_entry = min(item[0] for item in timestamps)
    last_exit = max(item[1] for item in timestamps)
    business_days = _business_day_count(first_entry.date(), last_exit.date())
    if business_days < 1:
        return None
    return {"closed_trade_count": len(trades), "business_days": business_days,
            "first_entry": first_entry.isoformat(), "last_exit": last_exit.isoformat(),
            "trades_per_day": len(trades) / business_days,
            "mean_holding_calendar_days": sum((end - start).total_seconds() / 86400 for start, end in timestamps) / len(timestamps)}


def _stage(stream, profile, config, funded=False, cadence_rng=None):
    initial = profile["account_size"]
    balance = initial
    high_water = initial
    total_loss = initial * profile["max_loss_pct"] / 100
    risk_amount = initial * config["risk_pct"] / 100
    target_pct = config["payout_target_pct"] if funded else profile["profit_target_pct"]
    target = initial * target_pct / 100
    max_days = config["funded_max_calendar_days"] if funded else config["max_calendar_days"]
    positive_best_day = 0.0
    trading_days = 0
    trades_count = 0
    buffer = profile["risk_buffer_amount"]
    cadence_rng = cadence_rng or random.Random(0)
    integral_rate = int(config["trades_per_day"])
    fractional_rate = config["trades_per_day"] - integral_rate
    # An arbitrary Monday gives a reproducible five-day week. No holiday or DST
    # feed is invented; those limitations are explicit in the result.
    start = date(2026, 1, 5)
    for calendar_day in range(max_days):
        if (start + timedelta(days=calendar_day)).weekday() >= 5:
            continue
        day_has_trade = False
        day_start = balance
        daily_floor = loss_floors(profile, {"balance": balance, "equity": balance,
                                          "day_start_balance": day_start, "day_start_equity": day_start,
                                          "high_water_equity": high_water})["daily_floor"]
        scheduled_trades = integral_rate + int(fractional_rate > 0 and cadence_rng.random() < fractional_rate)
        for _ in range(scheduled_trades):
            total_floor = loss_floors(profile, {"balance": balance, "equity": balance,
                                                "day_start_balance": day_start, "day_start_equity": day_start,
                                                "high_water_equity": high_water})["total_floor"]
            if balance <= daily_floor or balance <= total_floor:
                return {"outcome": "breach", "balance": balance, "trading_days": trading_days,
                        "calendar_days": calendar_day + 1, "trades": trades_count, "profit": balance - initial}
            # Pre-trade nominal stop risk is constrained by the same drawdown
            # reserve as the checker. If no room remains, sit out this day.
            if risk_amount + buffer >= min(balance - daily_floor, balance - total_floor):
                break
            sample = next(stream)
            if not day_has_trade:
                trading_days += 1
                day_has_trade = True
            trades_count += 1
            if sample["mae"] is not None:
                trough = balance - risk_amount * sample["mae"]
                excursion_floor = total_floor
                if profile["drawdown_type"] == "trailing_intraday" and sample["mfe"] is not None:
                    # OHLC/excursion inputs cannot establish event order. Assume
                    # favorable excursion precedes adverse excursion conservatively.
                    high_water = max(high_water, balance + risk_amount * sample["mfe"])
                    excursion_floor = high_water - total_loss
                    if profile["trailing_cap_at_initial"]:
                        excursion_floor = min(excursion_floor, initial)
                if trough <= daily_floor or trough <= excursion_floor:
                    return {"outcome": "breach", "balance": trough, "trading_days": trading_days,
                            "calendar_days": calendar_day + 1, "trades": trades_count, "profit": trough - initial}
            balance += sample["r"] * risk_amount
            if profile["drawdown_type"] == "trailing_intraday":
                high_water = max(high_water, balance)
            total_floor = loss_floors(profile, {"balance": balance, "equity": balance,
                                                "day_start_balance": day_start, "day_start_equity": day_start,
                                                "high_water_equity": high_water})["total_floor"]
            if balance <= daily_floor or balance <= total_floor:
                return {"outcome": "breach", "balance": balance, "trading_days": trading_days,
                        "calendar_days": calendar_day + 1, "trades": trades_count, "profit": balance - initial}
        day_profit = balance - day_start
        positive_best_day = max(positive_best_day, day_profit)
        if profile["drawdown_type"] == "trailing_eod":
            high_water = max(high_water, balance)
        net_profit = balance - initial
        consistency = (profile["best_day_pct"] is None or
                       (net_profit > 0 and positive_best_day / net_profit * 100 <= profile["best_day_pct"] + 1e-10))
        if net_profit >= target and trading_days >= profile["min_trading_days"] and consistency:
            return {"outcome": "payout" if funded else "pass", "balance": balance,
                    "trading_days": trading_days, "calendar_days": calendar_day + 1,
                    "trades": trades_count, "profit": net_profit,
                    "best_day_pct": positive_best_day / net_profit * 100 if net_profit else None}
    return {"outcome": "timeout", "balance": balance, "trading_days": trading_days,
            "calendar_days": max_days, "trades": trades_count, "profit": balance - initial}


def simulate(trades: list[dict], profile: dict, config: dict | None = None) -> dict:
    """Return empirical single-attempt first-payout economics and support status.

    A fee is charged once for every modeled attempt, including failed/timeout
    challenges and funded breaches. Nominal drawdown losses are simulated account
    losses, never silently booked as personal debt. Only paid profit split minus
    attempt fee becomes personal net cash flow. Fee refund/subscription, multiple
    challenge phases and multiple payouts are outside this one-attempt model.
    """
    base = {"feasible": False, "status": "unsupported", "net_expected_value": None,
            "payout_probability": None, "challenge_pass_probability": None,
            "breach_probability": None, "percentiles": {}, "distribution": [],
            "inputs": {}, "limitations": [], "reasons": []}
    try:
        if config is None:
            config = {}
        elif not isinstance(config, dict):
            raise ValueError("config: требуется объект")
        else:
            config = dict(config)
        profile = normalize_profile(profile)
        samples, is_oos, excursions = _extract_returns(trades, config)
        paths = _integer(config.get("paths", 500), "paths", 200, 1000)
        seed = _integer(config.get("seed", 42), "seed", 0, 2**32 - 1)
        risk_pct = _number(config.get("risk_pct", 0.25), "risk_pct", 0.000001, profile["max_risk_pct"])
        observed_cadence = _observed_cadence(trades)
        if "trades_per_day" in config:
            raw_trade_rate = config["trades_per_day"]
            rate_basis = config.get("trade_rate_basis", "user_supplied")
        elif observed_cadence is not None:
            raw_trade_rate = observed_cadence["trades_per_day"]
            rate_basis = "oos_closed_trades_per_business_day"
        else:
            raw_trade_rate = 3
            rate_basis = "illustrative_default_no_timestamps"
        if not isinstance(rate_basis, str) or len(rate_basis) > 1000:
            raise ValueError("trade_rate_basis: требуется строка до 1000 символов")
        trades_per_day = _number(raw_trade_rate, "trades_per_day", 0.001, 100)
        max_calendar_days = _integer(config.get("max_calendar_days", profile["max_calendar_days"] or 60), "max_calendar_days", 1, 365)
        if profile["max_calendar_days"] is not None and max_calendar_days > profile["max_calendar_days"]:
            raise ValueError("max_calendar_days превышает лимит профиля")
        funded_max_days = _integer(config.get("funded_max_calendar_days", 60), "funded_max_calendar_days", 1, 365)
        payout_target = _number(config.get("payout_target_pct", 2), "payout_target_pct", 0.000001, 100)
        maximum_daily_slots = int(trades_per_day) + int(trades_per_day % 1 > 0)
        if paths * (max_calendar_days + funded_max_days) * maximum_daily_slots > 3000000:
            raise ValueError("Объём simulation превышает лимит: уменьшите paths, дни или trades_per_day")
        for key in ("allow_illustrative", "returns_are_oos"):
            if key in config and not isinstance(config[key], bool):
                raise ValueError(f"{key}: требуется boolean")
        explicit_illustration = config.get("allow_illustrative") is True
        data_source = config.get("data_source", "unknown")
        if not isinstance(data_source, str):
            raise ValueError("data_source: требуется строка")
        synthetic_source = any(label in data_source.lower() for label in ("demo", "synthetic", "generated", "illustrative"))
        base["inputs"] = {"sample_count": len(samples), "returns_are_oos": is_oos, "data_source": data_source,
                          "paths": paths, "seed": seed, "risk_pct": risk_pct,
                          "trades_per_day": trades_per_day, "trade_rate_basis": rate_basis,
                          "observed_cadence": observed_cadence, "max_calendar_days": max_calendar_days,
                          "funded_max_calendar_days": funded_max_days, "payout_target_pct": payout_target,
                          "block_length": min(5, len(samples)), "account_size": profile["account_size"],
                          "attempt_fee": profile["challenge_fee"], "payout_split_pct": profile["payout_split_pct"],
                          "challenge_required": profile["challenge_required"], "drawdown_type": profile["drawdown_type"],
                          "daily_reference_basis": profile["daily_reference_basis"],
                          "trailing_cap_at_initial": profile["trailing_cap_at_initial"],
                          "intratrade_excursions": excursions, "single_modeled_challenge_phase": True}
        base["limitations"] = [
            "Вероятности — эмпирическая модель на выбранных доходностях, не проверенный прогноз и не гарантия выплаты.",
            "Один challenge или activation fee на попытку; без подписок, повторных фаз, возврата fee и повторных выплат.",
            "Правила профиля требуют проверки в личном кабинете фирмы; generic-профили учебные.",
            "Пять соседних сделок в bootstrap сохраняют локальные серии, но не все рыночные режимы или зависимость активов.",
            "Модель не подтверждает допустимость стратегии, новостного режима, EA или принятие фирмой payout-заявки.",
            "Риск фиксирован от начального капитала; пятидневная неделя без праздников и точного календаря reset.",
            "Частота — завершённые сделки на рабочий день; дробная часть выбирается Bernoulli, серии доходностей bootstrap сохраняются.",
            "Исторические timestamps и длительность позиций не воспроизводятся: закрытия попадают в календарные слоты, без полного учёта overnight/одновременной equity-экспозиции.",
            "Drawdown — убыток условного prop-счёта; личный денежный результат = split первой выплаты минус fee.",
        ]
        if rate_basis == "oos_closed_trades_per_business_day":
            base["limitations"].append("Автоматическая частота использует first entry → last exit; простой до первой/после последней сделки OOS не включён и может завысить частоту.")
        if rate_basis == "illustrative_default_no_timestamps":
            base["limitations"].append("Без timestamps и заданной частоты применяется учебное допущение 3 сделки/день; оно не подтверждает реальную частоту стратегии.")
        if data_source == "unknown":
            base["limitations"].append("Источник рыночных данных не указан: происхождение OOS должно быть проверено отдельно.")
        if excursions:
            base["limitations"].append("MAE/MFE могут быть границами OHLC-бара, а не проверенной последовательностью tick-событий.")
        if not excursions:
            base["limitations"].append("Нет полной MAE/MFE истории: intraday equity между закрытиями неизвестна; drawdown может быть занижен.")
        elif profile["drawdown_type"] == "trailing_intraday":
            base["limitations"].append("Порядок MAE/MFE неизвестен: для trailing intraday благоприятный пик учитывается до просадки консервативно.")
        if profile["best_day_pct"] is not None:
            base["limitations"].append("Consistency = лучший положительный день / чистая прибыль этапа; формула конкретной фирмы может отличаться.")
        if synthetic_source:
            base["reasons"].append("Демонстрационные или синтетические доходности допустимы только как явная иллюстрация")
        if len(samples) < 30:
            base["reasons"].append("Требуется минимум 30 out-of-sample сделок для исследовательской модели")
        if not is_oos:
            base["reasons"].append("Не подтверждено происхождение доходностей из out-of-sample периода")
        if not samples:
            return base
        if base["reasons"] and not explicit_illustration:
            return base
        if base["reasons"]:
            base["status"] = "illustrative"
            base["limitations"].append("Явно включена иллюстрация на недостаточных или неподтверждённых данных; эти результаты не являются оценкой edge.")
        else:
            base["status"] = "supported"
        active_config = {"risk_pct": risk_pct, "trades_per_day": trades_per_day,
                         "max_calendar_days": max_calendar_days, "funded_max_calendar_days": funded_max_days,
                         "payout_target_pct": payout_target}
        rng = random.Random(seed)
        outcomes = []
        for _ in range(paths):
            cadence_rng = random.Random(rng.getrandbits(64))
            stream = _block_stream(samples, rng)
            challenge = _stage(stream, profile, active_config, cadence_rng=cadence_rng) if profile["challenge_required"] else {
                "outcome": "pass", "balance": profile["account_size"], "profit": 0,
                "calendar_days": 0, "trading_days": 0, "trades": 0}
            funded = _stage(stream, profile, active_config, funded=True, cadence_rng=cadence_rng) if challenge["outcome"] == "pass" else None
            paid = funded is not None and funded["outcome"] == "payout"
            gross = funded["profit"] * profile["payout_split_pct"] / 100 if paid else 0.0
            outcomes.append({"challenge": challenge, "funded": funded, "paid": paid,
                             "gross": gross, "net": gross - profile["challenge_fee"],
                             "breach": challenge["outcome"] == "breach" or (funded is not None and funded["outcome"] == "breach")})
        passed = sum(item["challenge"]["outcome"] == "pass" for item in outcomes)
        paid_count = sum(item["paid"] for item in outcomes)
        breach_count = sum(bool(item["breach"]) for item in outcomes)
        net_values = [item["net"] for item in outcomes]
        expected = sum(net_values) / paths
        distribution = []
        for label, predicate in (
            ("challenge_breach", lambda item: item["challenge"]["outcome"] == "breach"),
            ("challenge_timeout", lambda item: item["challenge"]["outcome"] == "timeout"),
            ("funded_breach", lambda item: item["funded"] is not None and item["funded"]["outcome"] == "breach"),
            ("funded_timeout", lambda item: item["funded"] is not None and item["funded"]["outcome"] == "timeout"),
            ("first_payout", lambda item: item["paid"]),
        ):
            selected = [item for item in outcomes if predicate(item)]
            distribution.append({"outcome": label, "count": len(selected), "probability": len(selected) / paths,
                                 "average_net": round(sum(item["net"] for item in selected) / len(selected), 2) if selected else None})
        base.update({"feasible": True, "net_expected_value": round(expected, 2),
                     "payout_probability": paid_count / paths, "challenge_pass_probability": passed / paths,
                     "breach_probability": breach_count / paths,
                     "funded_payout_probability_conditional": paid_count / passed if passed else None,
                     "economically_positive": expected > 0,
                     "mean_gross_payout": round(sum(item["gross"] for item in outcomes) / paths, 2),
                     "attempt_fee": profile["challenge_fee"],
                     "percentiles": {"p10": round(_quantile(net_values, 0.1), 2), "p50": round(_quantile(net_values, 0.5), 2),
                                     "p90": round(_quantile(net_values, 0.9), 2)},
                     "distribution": distribution,
                     "stage_losses": {
                         "mean_challenge_account_pnl": round(sum(item["challenge"]["profit"] for item in outcomes) / paths, 2),
                         "mean_funded_account_pnl_unconditional": round(sum(item["funded"]["profit"] if item["funded"] else 0 for item in outcomes) / paths, 2),
                         "mean_total_fees_paid": profile["challenge_fee"],
                         "losses_are_nominal_account_pnl_not_personal_debt": True},
                     "mean_days_to_payout_conditional": round(sum(item["challenge"]["calendar_days"] + item["funded"]["calendar_days"] for item in outcomes if item["paid"]) / paid_count, 2) if paid_count else None,
                     "first_payout_account_reset": {"balance": profile["account_size"], "high_water": profile["account_size"],
                                                    "applies_to": "new funded stage only; repeated withdrawals are outside this model"}})
        return base
    except (ValueError, TypeError, OverflowError) as error:
        base["reasons"].append(str(error))
        return base
