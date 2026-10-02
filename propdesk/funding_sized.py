"""Funding risk sizing with idle cash retained in total-account arithmetic.

The original frozen execution engine is reused unchanged. This is an adaptive
second protocol calibrated from its TRAIN risk envelope, not a relaxed gate.
"""
from __future__ import annotations

from datetime import date
import math

from propdesk import funding_lab, research_stats as stats


def account(results, *, idle_cash=50_000.0, samples=5000):
    """Compute marked TOTAL equity, returns and inference from actual dollars."""
    if not results or not math.isfinite(idle_cash) or idle_cash < 0:
        raise ValueError("Finite nonnegative idle cash and active assets required")
    if any(row["dates"] != results[0]["dates"] for row in results):
        raise ValueError("Active asset dates must match exactly")
    dates = results[0]["dates"]
    if not dates:
        raise ValueError("At least one calendar day required")
    parsed = [date.fromisoformat(day) for day in dates]
    if any((right - left).days != 1 for left, right in zip(parsed, parsed[1:])):
        raise ValueError("Daily crypto account must include contiguous calendar days")
    capital = idle_cash + sum(row["capital"] for row in results)
    if capital <= 0:
        raise ValueError("Total account capital must be positive")
    equities = [idle_cash + math.fsum(row["daily_equity"][i] for row in results) for i in range(len(dates))]
    if any(not math.isfinite(value) or value <= 0 for value in equities):
        raise ValueError("Account equity must be positive and finite")
    returns = [value / (equities[i - 1] if i else capital) - 1 for i, value in enumerate(equities)]
    peak, drawdown, daily_drawdown = capital, 0.0, 0.0
    worst_values = []
    for i, day in enumerate(dates):
        worst = idle_cash + math.fsum(row["daily_rows"][day]["worst_equity"] for row in results)
        conservative_peak = idle_cash + math.fsum(row["daily_rows"][day]["maximum_close_equity"] for row in results)
        peak = max(peak, conservative_peak)
        drawdown = max(drawdown, 1 - worst / peak)
        daily_drawdown = max(daily_drawdown, 1 - worst / (equities[i - 1] if i else capital))
        peak = max(peak, equities[i])
        worst_values.append(worst)
    financial = {key: math.fsum(row[key] for row in results) for key in
                 ("funding_received", "fees", "paired_price_pnl", "liquidation_penalties")}
    reconciled = (financial["funding_received"] + financial["paired_price_pnl"]
                  - financial["fees"] - financial["liquidation_penalties"])
    return {"dates": dates, "daily_equity": equities, "daily_worst_equity": worst_values,
            "daily_returns": returns, "total_initial_capital": capital, "idle_cash": idle_cash,
            "active_initial_capital": capital - idle_cash,
            "return_pct": (equities[-1] / capital - 1) * 100,
            "annualized_return_pct": ((equities[-1] / capital) ** (365 / len(dates)) - 1) * 100,
            "max_drawdown_pct": drawdown * 100, "max_daily_drawdown_pct": daily_drawdown * 100,
            "settlements": sum(row["settlements"] for row in results),
            "liquidations": sum(row["liquidations"] for row in results),
            "fills": sum(row["fills"] for row in results), **financial,
            "block_mean_ci99": stats.bootstrap_mean_ci(returns, confidence=.99, samples=samples, block_length=7, seed=20261002) if len(returns) >= 7 else None,
            "monthly": stats.monthly_return_concentration(dates, returns), "assets": results,
            "accounting_reconciliation_error": equities[-1] - capital - reconciled,
            "live_qualified": False, "prop_qualified": False,
            "limitations": "Adaptive TRAIN-based capital calibration; trade-close funding and OHLC liquidation proxies; dormant cash earns zero and cannot rescue isolated margin; archive licensing and executable tariffs unverified."}


def simulate_portfolio(inputs, variant, start, end, *, friction=1.0,
                       positive_funding_multiplier=1.0, samples=5000):
    assets = []
    for symbol in ("BTCUSDT", "ETHUSDT"):
        result = funding_lab.simulate(inputs[symbol + "_spot"], inputs[symbol + "_perp"],
                                     inputs[symbol + "_funding"], variant, start, end,
                                     capital=25_000.0, friction=friction,
                                     positive_funding_multiplier=positive_funding_multiplier,
                                     allow_unknown_intervals=inputs.get(symbol + "_allow_unknown_intervals", False))
        result["symbol"] = symbol
        assets.append(result)
    return account(assets, idle_cash=50_000.0, samples=samples)
