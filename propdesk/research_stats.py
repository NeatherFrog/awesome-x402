"""Dependence-aware research summaries; these are not proof of future profit.

All returns are decimal, net account returns (0.01 means 1%). Include flat
calendar days. This module deliberately uses only the Python standard library.
"""

from __future__ import annotations

from datetime import date
import math
import random
from collections import defaultdict
from typing import Iterable, Mapping, Sequence


def _numbers(values: Iterable[float]) -> list[float]:
    result = [float(value) for value in values]
    if not all(math.isfinite(value) for value in result):
        raise ValueError("Observations must be finite; missing returns cannot be dropped")
    return result


def _quantile(sorted_values: Sequence[float], probability: float) -> float:
    index = (len(sorted_values) - 1) * probability
    left = math.floor(index)
    right = math.ceil(index)
    return sorted_values[left] + (sorted_values[right] - sorted_values[left]) * (index - left)


def _block_length(count: int, block_length: int | None) -> int:
    # Cube-root choice is an explicit approximation, not a fitted optimum.
    length = max(1, math.ceil(count ** (1 / 3))) if block_length is None else block_length
    if not isinstance(length, int) or isinstance(length, bool) or not 1 <= length <= count:
        raise ValueError("block_length must be an integer between 1 and sample length")
    return length


def bootstrap_mean_ci(
    daily_returns: Iterable[float], *, confidence: float = .99,
    samples: int = 2000, block_length: int | None = None, seed: int = 402,
) -> dict:
    """Percentile CI of mean daily net return, resampling circular daily blocks.

    Preserves dependence inside blocks, not arbitrarily long dependence or regime
    changes. The nominal confidence is conditional on a stationary-enough sample
    and a suitable block length. It is not a probability of future profitability.
    """
    values = _numbers(daily_returns)
    if len(values) < 2:
        raise ValueError("At least two daily returns are required")
    if not 0 < confidence < 1:
        raise ValueError("confidence must lie between zero and one")
    if not isinstance(samples, int) or isinstance(samples, bool) or samples < 100:
        raise ValueError("At least 100 bootstrap samples are required")
    count = len(values)
    length = _block_length(count, block_length)
    rng = random.Random(seed)
    # Precompute every complete circular block sum, reducing repeated additions.
    wrapped = values + values[:length - 1]
    block_sums = [sum(wrapped[index:index + length]) for index in range(count)]
    full_blocks, remainder = divmod(count, length)
    means = []
    for _ in range(samples):
        total = sum(block_sums[rng.randrange(count)] for _ in range(full_blocks))
        if remainder:
            start = rng.randrange(count)
            total += sum(wrapped[start:start + remainder])
        means.append(total / count)
    means.sort()
    tail = (1 - confidence) / 2
    return {
        "mean": math.fsum(values) / count,
        "lower": _quantile(means, tail),
        "upper": _quantile(means, 1 - tail),
        "confidence": confidence, "samples": samples, "block_length": length,
        "observations": count, "seed": seed,
        "method": "circular_moving_block_percentile_mean_daily_return",
        "limitations": "Conditional approximate interval; does not cover nonstationarity or selection bias.",
    }


def pearson_correlation(left: Iterable[float], right: Iterable[float]) -> float | None:
    """Pearson r, or None for insufficient observations/zero variance."""
    x, y = _numbers(left), _numbers(right)
    if len(x) != len(y):
        raise ValueError("Correlation vectors must have the same length")
    if len(x) < 2:
        return None
    mx, my = math.fsum(x) / len(x), math.fsum(y) / len(y)
    dx, dy = [value - mx for value in x], [value - my for value in y]
    xx, yy = math.fsum(value * value for value in dx), math.fsum(value * value for value in dy)
    if xx == 0 or yy == 0:
        return None
    covariance = math.fsum(a * b for a, b in zip(dx, dy))
    return max(-1.0, min(1.0, covariance / math.sqrt(xx * yy)))


def autocorrelation(values: Iterable[float], lag: int = 1) -> float | None:
    observations = _numbers(values)
    if not isinstance(lag, int) or isinstance(lag, bool) or lag < 1:
        raise ValueError("lag must be a positive integer")
    if lag >= len(observations):
        return None
    return pearson_correlation(observations[:-lag], observations[lag:])


def correlations_with_forward_returns(
    features: Mapping[str, Iterable[float]], returns: Iterable[float], *, max_lag: int = 1,
) -> dict:
    """Descriptive TRAIN-only feature[t] versus return[t+lag] correlations.

    The caller must pass the training segment only and features known at t. This
    function cannot prove timestamp causality from a vector. Each feature/lag is
    an additional inspected hypothesis and must count in the experiment ledger.
    """
    outcomes = _numbers(returns)
    if not isinstance(max_lag, int) or isinstance(max_lag, bool) or max_lag < 1:
        raise ValueError("max_lag must be a positive integer")
    result = {}
    for name, feature in features.items():
        known = _numbers(feature)
        if len(known) != len(outcomes):
            raise ValueError("Feature and return vectors must have the same length")
        result[name] = {}
        for lag in range(1, max_lag + 1):
            count = max(0, len(outcomes) - lag)
            result[name][str(lag)] = {
                "correlation": pearson_correlation(known[:count], outcomes[lag:]),
                "observations": count,
            }
    return {
        "split": "caller_supplied_training_only", "hypotheses": len(features) * max_lag,
        "features": result,
        "limitations": "Descriptive correlation, not causal or executable profit evidence.",
    }


def _pvalues(values: Iterable[float]) -> list[float]:
    probabilities = _numbers(values)
    if any(value < 0 or value > 1 for value in probabilities):
        raise ValueError("p-values must lie between zero and one")
    return probabilities


def holm_adjust(p_values: Iterable[float]) -> list[float]:
    """Holm adjusted p-values; valid marginal p-values are a prerequisite.

    Arbitrary dependence between tests is allowed by Holm itself. Applying Holm
    cannot repair an invalid null model, incomplete trial count or data leakage.
    """
    values = _pvalues(p_values)
    ordered = sorted(range(len(values)), key=values.__getitem__)
    result, previous = [0.0] * len(values), 0.0
    for rank, index in enumerate(ordered):
        previous = max(previous, min(1.0, (len(values) - rank) * values[index]))
        result[index] = previous
    return result


def benjamini_hochberg_adjust(p_values: Iterable[float]) -> list[float]:
    """Exploratory FDR screen; usual independent/positive-dependence assumptions.

    Correlated strategy returns need not satisfy those assumptions. Use Holm for
    a conservative confirmatory family and explicitly retain all tested variants.
    """
    values = _pvalues(p_values)
    ordered = sorted(range(len(values)), key=values.__getitem__)
    result, previous = [0.0] * len(values), 1.0
    for rank in range(len(values) - 1, -1, -1):
        index = ordered[rank]
        previous = min(previous, values[index] * len(values) / (rank + 1))
        result[index] = min(1.0, previous)
    return result


def block_signflip_pvalue(
    daily_returns: Iterable[float], *, block_length: int = 7,
    samples: int = 9999, seed: int = 402,
) -> dict:
    """One-sided block sign-randomization screen for positive mean return.

    Validity requires independent block signs and joint sign symmetry under the
    zero-mean null. These are assumptions, not established facts about financial
    returns. Therefore the reported value is a conditional diagnostic, not a
    general distribution-free p-value or profit probability.
    """
    values = _numbers(daily_returns)
    if not values:
        raise ValueError("At least one daily return is required")
    length = _block_length(len(values), block_length)
    if not isinstance(samples, int) or isinstance(samples, bool) or samples < 100:
        raise ValueError("At least 100 randomization samples are required")
    blocks = [math.fsum(values[index:index + length]) for index in range(0, len(values), length)]
    assumptions = "Independent symmetric block signs under zero-mean null; not verified for market returns."
    base = {
        "blocks": len(blocks), "block_length": length, "samples": samples, "seed": seed,
        "assumptions": assumptions, "method": "one_sided_nonoverlapping_block_signflip",
    }
    if len(blocks) < 12:
        return {**base, "p_value": None, "status": "insufficient_blocks"}
    observed = math.fsum(values)
    if observed <= 0:
        return {**base, "p_value": 1.0, "status": "conditional_diagnostic"}
    rng, at_least_as_large = random.Random(seed), 0
    for _ in range(samples):
        statistic = math.fsum(block if rng.getrandbits(1) else -block for block in blocks)
        at_least_as_large += statistic >= observed
    return {**base, "p_value": (at_least_as_large + 1) / (samples + 1),
            "status": "conditional_diagnostic"}


def return_summary(daily_returns: Iterable[float]) -> dict:
    """Compounded return/max drawdown of the marked net equity series."""
    values = _numbers(daily_returns)
    if any(value < -1 for value in values):
        raise ValueError("Account return cannot be below -100 percent")
    equity, peak, maximum = 1.0, 1.0, 0.0
    for value in values:
        equity *= 1 + value
        peak = max(peak, equity)
        maximum = max(maximum, 1 - equity / peak)
    return {
        "total_return": equity - 1,
        "max_drawdown": maximum,
        "mean_daily_return": math.fsum(values) / len(values) if values else None,
        "days": len(values),
        "lag1_autocorrelation": autocorrelation(values),
    }


def monthly_return_concentration(dates: Sequence[str], daily_returns: Iterable[float]) -> dict:
    values = _numbers(daily_returns)
    if len(dates) != len(values):
        raise ValueError("Each daily return requires its own calendar date")
    months = defaultdict(lambda: 1.0)
    parsed = [date.fromisoformat(day) for day in dates]
    if parsed != sorted(set(parsed)):
        raise ValueError("Dates must be unique and strictly increasing")
    for day, value in zip(parsed, values):
        if value < -1:
            raise ValueError("Account return cannot be below -100 percent")
        months[day.strftime("%Y-%m")] *= 1 + value
    returns = {month: equity - 1 for month, equity in sorted(months.items())}
    positive = [value for value in returns.values() if value > 0]
    contribution = max(positive) / math.fsum(positive) if positive else None
    return {"monthly_returns": returns, "months": len(returns),
            "largest_positive_month_share": contribution,
            "definition": "Largest positive monthly return / sum of positive monthly returns; descriptive."}


def qualification_report(
    final_daily_returns: Iterable[float], *, dates: Sequence[str], trade_count: int,
    stressed_daily_returns: Iterable[float], benchmark_daily_returns: Iterable[float] | None = None,
    seed: int = 402, samples: int = 5000, block_length: int = 7,
) -> dict:
    """Frozen research screen for one selected final-period candidate.

    This function supplies no selection correction: the caller must have selected
    exactly one candidate before observing final data. Passing means eligible for
    a future forward test; it never means a guaranteed or stable profitable bot.
    """
    final, stressed = _numbers(final_daily_returns), _numbers(stressed_daily_returns)
    if len(final) != len(stressed):
        raise ValueError("Base and stress account returns must cover the same dates")
    if not isinstance(trade_count, int) or isinstance(trade_count, bool) or trade_count < 0:
        raise ValueError("trade_count must be a nonnegative integer")
    concentration = monthly_return_concentration(dates, final)
    parsed = [date.fromisoformat(day) for day in dates]
    if any((right - left).days != 1 for left, right in zip(parsed, parsed[1:])):
        raise ValueError("Final crypto daily equity must include every calendar day")
    base, stress = return_summary(final), return_summary(stressed)
    interval = bootstrap_mean_ci(final, samples=samples, block_length=block_length, seed=seed)
    span = (parsed[-1] - parsed[0]).days + 1 if parsed else 0
    monthly_share = concentration["largest_positive_month_share"]
    checks = {
        "positive_net_return": base["total_return"] > 0,
        "positive_stressed_net_return": stress["total_return"] > 0,
        "lower_99_percent_mean_daily_ci_positive": interval["lower"] > 0,
        "at_least_50_closed_trades": trade_count >= 50,
        "at_least_180_calendar_days": span >= 180,
        "at_least_six_calendar_months": concentration["months"] >= 6,
        "largest_positive_month_share_at_most_half": monthly_share is not None and monthly_share <= .5,
        "max_drawdown_at_most_10_percent": base["max_drawdown"] <= .1,
    }
    benchmark = None
    if benchmark_daily_returns is not None:
        reference = _numbers(benchmark_daily_returns)
        if len(reference) != len(final):
            raise ValueError("Benchmark must cover the same account dates")
        benchmark = return_summary(reference)
        benchmark["daily_return_correlation"] = pearson_correlation(final, reference)
        benchmark["active_total_return_difference"] = base["total_return"] - benchmark["total_return"]
    return {
        "status": "eligible_for_forward_test" if all(checks.values()) else "not_qualified",
        "qualified": all(checks.values()), "checks": checks, "final": base, "stress": stress,
        "mean_daily_ci": interval, "monthly_concentration": concentration, "benchmark": benchmark,
        "trade_count": trade_count, "calendar_span_days": span,
        "limitations": "Historical research screen only; trade count is not independent sample size. Future forward validation required.",
    }
