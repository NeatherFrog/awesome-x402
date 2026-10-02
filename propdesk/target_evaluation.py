"""Frozen 8%-monthly research objective; no claim of profit or cash payout.

Uses net TOTAL account returns and complete calendar-day equity. Historical
screens never enable orders or certify a prop contract. The old statistical
producers are deliberately reused without modification.
"""
from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta
import math
from statistics import median

from propdesk import research_stats as stats


TARGET_MONTHLY_RETURN = .08
MAX_ACCOUNT_DRAWDOWN = .10
MAX_REFERENCE_DAILY_LOSS = .05


def _finite(values, label):
    result = [float(value) for value in values]
    if any(not math.isfinite(value) for value in result):
        raise ValueError(label + " must be finite; missing observations cannot be dropped")
    return result


def _calendar(dates, count, period_start, period_end_exclusive):
    if len(dates) != count or not dates:
        raise ValueError("Every daily return requires exactly one calendar date")
    parsed = [date.fromisoformat(value) for value in dates]
    if any(day.isoformat() != text for day, text in zip(parsed, dates)):
        raise ValueError("Calendar dates must be canonical YYYY-MM-DD")
    if any((right - left).days != 1 for left, right in zip(parsed, parsed[1:])):
        raise ValueError("Include every calendar day, including verified flat closed-market days")
    begin = date.fromisoformat(period_start) if period_start else parsed[0]
    finish = date.fromisoformat(period_end_exclusive) if period_end_exclusive else parsed[-1] + timedelta(days=1)
    if begin != parsed[0] or finish != parsed[-1] + timedelta(days=1):
        raise ValueError("Daily equity does not completely cover the declared period")
    return parsed, begin, finish


def monthly_equivalent(dates, daily_returns):
    """Geometric return per actual elapsed calendar month, including partials.

    Each complete daily observation contributes 1/(days in its calendar month).
    This is not an arithmetic average or an assertion every month earned 8%.
    """
    returns = _finite(daily_returns, "Daily account returns")
    parsed, _, _ = _calendar(dates, len(returns), None, None)
    if any(value <= -1 for value in returns):
        raise ValueError("Positive account equity is required for geometric inference")
    months = math.fsum(1 / monthrange(day.year, day.month)[1] for day in parsed)
    log_growth = math.fsum(math.log1p(value) for value in returns)
    return {
        "elapsed_calendar_months": months,
        "geometric_monthly_return": math.expm1(log_growth / months),
        "total_return": math.expm1(log_growth),
        "definition": "Compound total account growth raised to 1/elapsed calendar months, minus one.",
    }


def _month_metrics(parsed, returns):
    groups = {}
    for day, value in zip(parsed, returns):
        month = day.strftime("%Y-%m")
        groups.setdefault(month, []).append((day, value))
    complete, partial = {}, {}
    for month, observations in groups.items():
        first, last = observations[0][0], observations[-1][0]
        growth = math.expm1(math.fsum(math.log1p(value) for _, value in observations))
        is_full = (first.day == 1 and last.day == monthrange(last.year, last.month)[1]
                   and len(observations) == monthrange(last.year, last.month)[1])
        (complete if is_full else partial)[month] = growth
    values = list(complete.values())
    positive = sum(value > 0 for value in values)
    return {
        "full_month_returns": complete, "partial_month_returns": partial,
        "full_month_count": len(values), "positive_full_months": positive,
        "positive_full_month_fraction": positive / len(values) if values else None,
        "median_full_month_return": median(values) if values else None,
        "worst_full_month_return": min(values) if values else None,
        "best_full_month_return": max(values) if values else None,
        "full_months_at_least_8_percent": sum(value >= TARGET_MONTHLY_RETURN or
                                              math.isclose(value, TARGET_MONTHLY_RETURN, rel_tol=1e-12, abs_tol=1e-14)
                                              for value in values),
    }


def _risk(equities, initial, daily_worst_equity, daily_peak_equity):
    provided = daily_worst_equity is not None and daily_peak_equity is not None
    if (daily_worst_equity is None) != (daily_peak_equity is None):
        raise ValueError("Supply both adverse and peak daily dollar equity envelopes")
    worst = _finite(daily_worst_equity, "Daily adverse equity") if provided else list(equities)
    peaks = _finite(daily_peak_equity, "Daily peak equity") if provided else list(equities)
    if len(worst) != len(equities) or len(peaks) != len(equities):
        raise ValueError("Daily equity envelopes must cover the same complete dates")
    running_peak, max_drawdown, maximum_daily_loss = initial, 0.0, 0.0
    for i, closing in enumerate(equities):
        if worst[i] > closing + 1e-7 or peaks[i] < closing - 1e-7 or peaks[i] < worst[i]:
            raise ValueError("Adverse/peak envelopes must include marked closing equity")
        starting = equities[i - 1] if i else initial
        # A same-day best/worst ordering is unknowable from aggregated envelopes.
        # Best before worst is a conservative bound, not an exact intraday path.
        running_peak = max(running_peak, starting, peaks[i])
        max_drawdown = max(max_drawdown, 1 - worst[i] / running_peak)
        maximum_daily_loss = max(maximum_daily_loss, (starting - worst[i]) / initial)
        running_peak = max(running_peak, closing)
    return {
        "adverse_envelopes_supplied": provided,
        "max_account_drawdown": max_drawdown,
        "max_reference_daily_loss": maximum_daily_loss,
        "daily_loss_denominator": "initial TOTAL account capital",
        "daily_reference": "Previous calendar close marked equity to adverse daily equity; not a prop-rule replay.",
        "path": "Conservative daily peak/worst envelopes; actual intraday ordering not established.",
    }


def evaluate_period(
    dates, daily_returns, stressed_daily_returns, completed_episodes, *,
    initial_equity=100_000.0, daily_worst_equity=None, daily_peak_equity=None,
    period_start=None, period_end_exclusive=None, role="validation",
    risk_day_timezone="UTC", minimum_episodes=None, samples=5000, seed=20261002,
):
    """Evaluate a frozen train/validation/final period on actual account dollars.

    TRAIN: positive net/stress returns, 30 episodes, 60 calendar days, adverse
    drawdown<=10%, reference daily loss<=5%. OOS additionally requires geometric
    monthly equivalent>=8%, six FULL calendar months, 99% block CI lower>0,
    positive median month, >=2/3 positive months, both chronological halves
    positive and 60 episodes. A higher preregistered episode minimum is allowed.
    """
    if role not in ("training", "validation", "final"):
        raise ValueError("role must be training, validation or final")
    if not math.isfinite(initial_equity) or initial_equity <= 0:
        raise ValueError("Positive finite total initial account capital is required")
    if not isinstance(completed_episodes, int) or isinstance(completed_episodes, bool) or completed_episodes < 0:
        raise ValueError("Completed episodes must be a nonnegative integer, not fill count")
    required_episodes = 30 if role == "training" else 60
    if minimum_episodes is not None:
        if (not isinstance(minimum_episodes, int) or isinstance(minimum_episodes, bool)
                or minimum_episodes < required_episodes):
            raise ValueError("A preregistered episode minimum cannot weaken the common gate")
        required_episodes = minimum_episodes
    if not isinstance(risk_day_timezone, str) or not risk_day_timezone:
        raise ValueError("A frozen daily risk-reference timezone is required")
    returns = _finite(daily_returns, "Daily account returns")
    stressed = _finite(stressed_daily_returns, "Cost-stressed daily account returns")
    if len(returns) != len(stressed):
        raise ValueError("Base and stress must cover the identical declared calendar")
    parsed, begin, finish = _calendar(dates, len(returns), period_start, period_end_exclusive)
    if any(value <= -1 for value in returns + stressed):
        raise ValueError("Account insolvency cannot qualify for geometric inference")
    base_equivalent = monthly_equivalent(dates, returns)
    stress_equivalent = monthly_equivalent(dates, stressed)
    equities, equity = [], float(initial_equity)
    for value in returns:
        equity *= 1 + value
        if not math.isfinite(equity) or equity <= 0:
            raise ValueError("Account equity is not positive and finite")
        equities.append(equity)
    months = _month_metrics(parsed, returns)
    risk = _risk(equities, initial_equity, daily_worst_equity, daily_peak_equity)
    interval = (stats.bootstrap_mean_ci(returns, confidence=.99, samples=samples,
                                       block_length=7, seed=seed) if len(returns) >= 7 else None)
    midpoint = len(returns) // 2
    halves = [math.expm1(math.fsum(math.log1p(value) for value in part))
              for part in (returns[:midpoint], returns[midpoint:])]
    checks = {
        "positive_net_total_return": base_equivalent["total_return"] > 0,
        "positive_double_cost_geometric_monthly_return": stress_equivalent["geometric_monthly_return"] > 0,
        "minimum_completed_episodes": completed_episodes >= required_episodes,
        "minimum_60_calendar_days": len(returns) >= 60,
        "adverse_risk_envelopes_present": risk["adverse_envelopes_supplied"],
        "max_account_drawdown_at_most_10_percent": risk["adverse_envelopes_supplied"] and risk["max_account_drawdown"] <= MAX_ACCOUNT_DRAWDOWN,
        "max_reference_daily_loss_at_most_5_percent": risk["adverse_envelopes_supplied"] and risk["max_reference_daily_loss"] <= MAX_REFERENCE_DAILY_LOSS,
    }
    if role != "training":
        monthly = base_equivalent["geometric_monthly_return"]
        checks.update({
            "geometric_monthly_return_at_least_8_percent": monthly >= TARGET_MONTHLY_RETURN or math.isclose(monthly, TARGET_MONTHLY_RETURN, rel_tol=1e-12, abs_tol=1e-14),
            "at_least_six_full_calendar_months": months["full_month_count"] >= 6,
            "daily_mean_ci99_lower_positive": interval is not None and interval["lower"] > 0,
            "median_full_calendar_month_positive": months["median_full_month_return"] is not None and months["median_full_month_return"] > 0,
            "at_least_two_thirds_full_months_positive": months["full_month_count"] > 0 and 3 * months["positive_full_months"] >= 2 * months["full_month_count"],
            "both_chronological_half_returns_positive": all(value > 0 for value in halves),
        })
    return {
        "role": role, "passed": all(checks.values()), "checks": checks,
        "status": "historical_reference_screen_passed" if all(checks.values()) else "not_qualified",
        "initial_total_equity": initial_equity, "final_total_equity": equities[-1],
        "period_start": begin.isoformat(), "period_end_exclusive": finish.isoformat(),
        "calendar_days": len(returns), "completed_episodes": completed_episodes,
        "required_completed_episodes": required_episodes,
        "base": base_equivalent, "double_cost_stress": stress_equivalent,
        "calendar_months": months, "daily_mean_ci99": interval,
        "chronological_half_returns": halves, "risk": {**risk, "timezone": risk_day_timezone},
        "selection_score_net_return_over_drawdown": base_equivalent["total_return"] / max(risk["max_account_drawdown"], .0025),
        "monthly_8_percent_is_not_a_guarantee": True, "cash_payout_evaluated": False,
        "prop_contract_verified": False, "live_orders": False, "telegram_enabled": False,
        "limitations": "Adaptive historical research only. Conditional block inference does not erase selection or nonstationarity. Profit is not a withdrawal; exact contract/stage/reset replay and genuinely new forward data remain required.",
    }
