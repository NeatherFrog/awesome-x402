"""Objective arithmetic and rejection tests; synthetic fixtures provide no alpha."""
from calendar import monthrange
from datetime import date, timedelta
import math
import unittest

from propdesk import target_evaluation as objective


def monthly_fixture(monthly_returns, start=date(2025, 1, 1)):
    dates, returns = [], []
    day = start
    for value in monthly_returns:
        length = monthrange(day.year, day.month)[1]
        daily = (1 + value) ** (1 / length) - 1
        for _ in range(length):
            dates.append(day.isoformat())
            returns.append(daily)
            day += timedelta(days=1)
    return dates, returns


def envelopes(returns, initial=100_000):
    equity, worst, peak = initial, [], []
    for value in returns:
        before = equity
        equity *= 1 + value
        worst.append(min(before, equity))
        peak.append(max(before, equity))
    return worst, peak


def evaluate(dates, returns, **kwargs):
    worst, peak = envelopes(returns)
    return objective.evaluate_period(dates, returns, kwargs.pop("stress", returns),
                                     kwargs.pop("episodes", 60),
                                     daily_worst_equity=kwargs.pop("worst", worst),
                                     daily_peak_equity=kwargs.pop("peak", peak),
                                     samples=200, **kwargs)


class TargetEvaluationTests(unittest.TestCase):
    def test_eight_percent_actual_calendar_months_and_total_capital(self):
        dates, returns = monthly_fixture([.08] * 12)
        result = evaluate(dates, returns)
        self.assertAlmostEqual(result["base"]["elapsed_calendar_months"], 12)
        self.assertAlmostEqual(result["base"]["geometric_monthly_return"], .08)
        self.assertAlmostEqual(result["base"]["total_return"], 1.08 ** 12 - 1)
        self.assertEqual(result["calendar_months"]["full_month_count"], 12)
        self.assertTrue(result["passed"])
        self.assertFalse(result["cash_payout_evaluated"])
        self.assertFalse(result["live_orders"])
        self.assertFalse(result["prop_contract_verified"])

    def test_arithmetic_average_cannot_replace_geometric_objective(self):
        dates, returns = monthly_fixture([.25, -.07] * 3)
        result = evaluate(dates, returns)
        self.assertGreater(sum([.25, -.07]) / 2, .08)
        self.assertLess(result["base"]["geometric_monthly_return"], .08)
        self.assertFalse(result["checks"]["geometric_monthly_return_at_least_8_percent"])
        self.assertAlmostEqual(result["calendar_months"]["worst_full_month_return"], -.07)

    def test_high_average_does_not_require_every_month_eight_percent(self):
        dates, returns = monthly_fixture([.16, .04] * 3)
        result = evaluate(dates, returns)
        self.assertTrue(result["passed"])
        self.assertEqual(result["calendar_months"]["full_months_at_least_8_percent"], 3)
        self.assertTrue(result["monthly_8_percent_is_not_a_guarantee"])

    def test_partial_months_do_not_satisfy_six_full_month_gate(self):
        dates, returns = monthly_fixture([.08] * 6)
        dates, returns = dates[1:], returns[1:]
        result = evaluate(dates, returns)
        self.assertEqual(result["calendar_months"]["full_month_count"], 5)
        self.assertIn("2025-01", result["calendar_months"]["partial_month_returns"])
        self.assertFalse(result["checks"]["at_least_six_full_calendar_months"])

    def test_loss_half_fails_despite_full_period_target(self):
        dates, returns = monthly_fixture([-.001] * 3 + [.25] * 3)
        result = evaluate(dates, returns)
        self.assertGreater(result["base"]["geometric_monthly_return"], .08)
        self.assertFalse(result["checks"]["both_chronological_half_returns_positive"])
        self.assertFalse(result["passed"])

    def test_true_adverse_intraday_loss_rejects_positive_close_curve(self):
        dates, returns = monthly_fixture([.08] * 6)
        worst, peak = envelopes(returns)
        worst[0] = 94_900
        result = evaluate(dates, returns, worst=worst, peak=peak)
        self.assertFalse(result["checks"]["max_reference_daily_loss_at_most_5_percent"])
        self.assertGreater(result["risk"]["max_reference_daily_loss"], .05)
        self.assertFalse(result["prop_contract_verified"])

    def test_missing_adverse_marks_cannot_qualify_using_closes_alone(self):
        dates, returns = monthly_fixture([.08] * 6)
        result = objective.evaluate_period(dates, returns, returns, 60, samples=200)
        self.assertFalse(result["checks"]["adverse_risk_envelopes_present"])
        self.assertFalse(result["passed"])

    def test_cost_stress_and_episode_minimum_are_actual_gates(self):
        dates, returns = monthly_fixture([.08] * 6)
        bad_cost = evaluate(dates, returns, stress=[-.0001] * len(returns))
        self.assertFalse(bad_cost["checks"]["positive_double_cost_geometric_monthly_return"])
        sparse = evaluate(dates, returns, episodes=59)
        self.assertFalse(sparse["checks"]["minimum_completed_episodes"])
        with self.assertRaises(ValueError):
            evaluate(dates, returns, minimum_episodes=59)

    def test_training_has_distinct_prespecified_gates(self):
        dates, returns = monthly_fixture([.01] * 3, start=date(2024, 10, 1))
        result = evaluate(dates, returns, episodes=30, role="training")
        self.assertTrue(result["passed"])
        self.assertNotIn("geometric_monthly_return_at_least_8_percent", result["checks"])
        self.assertNotIn("at_least_six_full_calendar_months", result["checks"])
        self.assertEqual(result["calendar_days"], 92)

    def test_calendar_gaps_insolvency_and_different_stress_period_reject(self):
        dates, returns = monthly_fixture([.08] * 6)
        with self.assertRaises(ValueError):
            evaluate(dates[:5] + dates[6:], returns[:5] + returns[6:])
        with self.assertRaises(ValueError):
            evaluate(dates, [-1] + returns[1:])
        with self.assertRaises(ValueError):
            evaluate(dates, returns, stress=returns[:-1])
        with self.assertRaises(ValueError):
            evaluate(dates, returns, period_end_exclusive="2025-06-29")


if __name__ == "__main__":
    unittest.main()
