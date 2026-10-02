"""Statistical correctness tests; synthetic data is never trading evidence."""

from datetime import date, timedelta
import math
import unittest

from propdesk import research_stats as stats


class ResearchStatsTests(unittest.TestCase):
    def test_bootstrap_deterministic_and_constant_observations(self):
        values = [.001] * 240
        result = stats.bootstrap_mean_ci(values, samples=200, block_length=7, seed=13)
        self.assertEqual(result, stats.bootstrap_mean_ci(values, samples=200, block_length=7, seed=13))
        self.assertAlmostEqual(result["lower"], .001)
        self.assertAlmostEqual(result["upper"], .001)
        self.assertEqual(result["observations"], 240)

    def test_dependence_blocks_widen_interval_for_persistent_series(self):
        values = ([.01] * 14 + [-.01] * 14) * 10
        independent = stats.bootstrap_mean_ci(values, samples=1000, block_length=1, seed=17)
        dependent = stats.bootstrap_mean_ci(values, samples=1000, block_length=14, seed=17)
        self.assertGreater(dependent["upper"] - dependent["lower"],
                           2 * (independent["upper"] - independent["lower"]))
        self.assertLess(dependent["lower"], 0)

    def test_invalid_or_missing_return_is_not_silently_removed(self):
        for values in ([.01], [0, float("nan")], [0, float("inf")]):
            with self.assertRaises(ValueError):
                stats.bootstrap_mean_ci(values)
        with self.assertRaises(ValueError):
            stats.bootstrap_mean_ci([0, 1], block_length=3)

    def test_correlations_and_degeneracy(self):
        self.assertAlmostEqual(stats.pearson_correlation([1, 2, 3], [3, 2, 1]), -1)
        self.assertIsNone(stats.pearson_correlation([1, 1, 1], [1, 2, 3]))
        self.assertIsNone(stats.pearson_correlation([], []))
        self.assertIsNone(stats.autocorrelation([0, 0, 0]))
        self.assertIsNone(stats.autocorrelation([1, 2], lag=2))
        with self.assertRaises(ValueError):
            stats.pearson_correlation([1], [1, 2])

    def test_forward_correlation_alignment_and_trial_count(self):
        feature = [1, 2, 3, 4, 5]
        result = stats.correlations_with_forward_returns({"known_close": feature},
                                                        [5, 1, 2, 3, 4], max_lag=2)
        self.assertEqual(result["hypotheses"], 2)
        self.assertAlmostEqual(result["features"]["known_close"]["1"]["correlation"], 1)
        self.assertEqual(result["features"]["known_close"]["2"]["observations"], 3)

    def test_holm_preserves_input_order_and_counts_all_trials(self):
        values = [.03, .001, .02, .8]
        expected = [.06, .004, .06, .8]
        for actual, wanted in zip(stats.holm_adjust(values), expected):
            self.assertAlmostEqual(actual, wanted)
        self.assertEqual(stats.holm_adjust([]), [])
        self.assertEqual(stats.holm_adjust([.01] + [1] * 199)[0], 1)
        with self.assertRaises(ValueError):
            stats.holm_adjust([float("nan")])
        with self.assertRaises(ValueError):
            stats.holm_adjust([-1])

    def test_bh_adjustment_monotonic_and_bounded(self):
        adjusted = stats.benjamini_hochberg_adjust([.01, .02, .5])
        for actual, wanted in zip(adjusted, [.03, .03, .5]):
            self.assertAlmostEqual(actual, wanted)

    def test_randomization_requires_blocks_and_reports_assumptions(self):
        short = stats.block_signflip_pvalue([.01] * 30, samples=100)
        self.assertIsNone(short["p_value"])
        self.assertEqual(short["status"], "insufficient_blocks")
        positive = stats.block_signflip_pvalue([.01] * 140, samples=1000, seed=9)
        self.assertEqual(positive, stats.block_signflip_pvalue([.01] * 140, samples=1000, seed=9))
        self.assertGreaterEqual(positive["p_value"], 1 / 1001)
        self.assertIn("not verified", positive["assumptions"])
        self.assertEqual(stats.block_signflip_pvalue([-.01] * 140, samples=100)["p_value"], 1)
        self.assertEqual(stats.block_signflip_pvalue([0] * 140, samples=100)["p_value"], 1)

    def test_compounding_and_drawdown_use_account_equity(self):
        result = stats.return_summary([.1, -.1, .1])
        self.assertAlmostEqual(result["total_return"], .089)
        self.assertAlmostEqual(result["max_drawdown"], .1)
        with self.assertRaises(ValueError):
            stats.return_summary([-1.1])

    def test_positive_base_is_rejected_when_cost_stress_turns_negative(self):
        dates = [(date(2026, 1, 1) + timedelta(days=index)).isoformat() for index in range(240)]
        result = stats.qualification_report([.001] * 240, dates=dates, trade_count=100,
                                             stressed_daily_returns=[-.001] * 240, samples=200)
        self.assertFalse(result["qualified"])
        self.assertEqual(result["status"], "not_qualified")
        self.assertFalse(result["checks"]["positive_stressed_net_return"])
        self.assertTrue(result["checks"]["lower_99_percent_mean_daily_ci_positive"])
        self.assertIn("Future forward", result["limitations"])

    def test_pass_is_forward_eligibility_and_activity_is_not_independence(self):
        dates = [(date(2026, 1, 1) + timedelta(days=index)).isoformat() for index in range(240)]
        result = stats.qualification_report([.001] * 240, dates=dates, trade_count=50,
                                             stressed_daily_returns=[.0005] * 240,
                                             benchmark_daily_returns=[.002] * 240, samples=200)
        self.assertTrue(result["qualified"])
        self.assertEqual(result["status"], "eligible_for_forward_test")
        self.assertLess(result["benchmark"]["active_total_return_difference"], 0)
        self.assertIsNone(result["benchmark"]["daily_return_correlation"])
        self.assertIn("not independent sample size", result["limitations"])
        sparse = stats.qualification_report([.001] * 240, dates=dates, trade_count=49,
                                             stressed_daily_returns=[.0005] * 240, samples=200)
        self.assertFalse(sparse["qualified"])
        self.assertFalse(sparse["checks"]["at_least_50_closed_trades"])

    def test_one_lucky_month_fails_concentration_screen(self):
        dates = [(date(2026, 1, 1) + timedelta(days=index)).isoformat() for index in range(240)]
        values = [.02 if day.startswith("2026-03") else -.00001 for day in dates]
        result = stats.qualification_report(values, dates=dates, trade_count=100,
                                             stressed_daily_returns=values, samples=200)
        self.assertFalse(result["checks"]["largest_positive_month_share_at_most_half"])
        self.assertEqual(result["monthly_concentration"]["largest_positive_month_share"], 1)

    def test_contiguous_dates_and_aligned_stress_benchmark_required(self):
        with self.assertRaises(ValueError):
            stats.qualification_report([.01, .02], dates=["2026-01-01", "2026-01-03"],
                                       trade_count=50, stressed_daily_returns=[0, 0], samples=100,
                                       block_length=1)
        with self.assertRaises(ValueError):
            stats.qualification_report([.01, .02], dates=["2026-01-01", "2026-01-02"],
                                       trade_count=50, stressed_daily_returns=[0], samples=100,
                                       block_length=1)


if __name__ == "__main__":
    unittest.main()
