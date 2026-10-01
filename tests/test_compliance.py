import unittest

from propdesk.compliance import evaluate
from propdesk.risk import default_profiles


def point(time, equity, worst=None, best=None, balance=None):
    return {"time": time, "equity": equity, "balance": equity if balance is None else balance,
            "worst_equity": equity if worst is None else worst, "best_equity": equity if best is None else best}


class ComplianceTests(unittest.TestCase):
    def setUp(self):
        self.profile = default_profiles()[0]

    def test_intrabar_daily_limit_not_hidden_by_positive_close(self):
        result = evaluate([point("2026-01-01T10:00:00Z", 101000, 95000, 102000)], self.profile)
        self.assertEqual(result["status"], "breach")
        self.assertEqual(result["breaches"][0]["type"], "daily")

    def test_reset_uses_local_timezone_and_prior_day_equity(self):
        profile = {**self.profile, "daily_reset_timezone": "Europe/Kyiv"}
        result = evaluate([point("2026-01-01T21:00:00Z", 103000),
                           point("2026-01-01T22:00:00Z", 98500, 97999, 103000)], profile)
        self.assertEqual(result["status"], "breach")
        self.assertEqual(result["breaches"][0]["floor"], 98000)

    def test_static_vs_trailing_intraday(self):
        curve = [point("2026-01-01T10:00:00Z", 100000, 99500, 112000)]
        profile = {**self.profile, "daily_loss_pct": 20}
        self.assertEqual(evaluate(curve, profile)["status"], "pass")
        self.assertEqual(evaluate(curve, {**profile, "drawdown_type": "trailing_intraday"})["status"], "breach")

    def test_target_and_active_day_count_are_not_firm_verification(self):
        result = evaluate([point("2026-01-01T10:00:00Z", 109000)], self.profile,
                          [{"entry_time": "2026-01-01T09:00:00Z"}])
        self.assertEqual(result["target_first_reached"], "2026-01-01T10:00:00Z")
        self.assertFalse(result["minimum_trading_days_met"])
        self.assertFalse(result["verified_real_account"])

    def test_missing_marks_cannot_pass(self):
        result = evaluate([{"time": "2026-01-01T10:00:00Z", "equity": 100000}], self.profile)
        self.assertEqual(result["status"], "incomplete")


if __name__ == "__main__":
    unittest.main()
