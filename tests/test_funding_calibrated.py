"""Single TRAIN-based risk allocation; synthetic fixtures are not alpha evidence."""
import ast
from pathlib import Path
import unittest

from propdesk import funding_calibrated as lab
from tests.test_funding_lab import fixtures


class FundingCalibratedTests(unittest.TestCase):
    def test_fixed_train_only_allocation_has_no_validation_input(self):
        self.assertAlmostEqual(lab.SPOT_FRACTION, .09938375375865606)
        self.assertEqual(lab.SPOT_FRACTION,
                         min(.2, .2 * (1.5 / 3.0186020214986176)))
        spot, perp, events, start, end = fixtures(3)
        out = lab.simulate(spot, perp, events, lab.variants()[0], start, end,
                           capital=1000, friction=0)
        expected_q = int(1000 * lab.SPOT_FRACTION / 100 * 1e6) / 1e6
        self.assertEqual(out["records"][0]["quantity"], expected_q)
        self.assertAlmostEqual(out["daily_equity"][-1], 1000 + expected_q * .1)
        self.assertAlmostEqual(out["reconciliation_error"], 0)

    def test_finite_physical_margin_and_negative_funding_remain_charged(self):
        spot, perp, events, start, end = fixtures(5, rate=-.001)
        out = lab.simulate(spot, perp, events, lab.variants()[0], start, end,
                           capital=1000, friction=0, positive_funding_multiplier=.75)
        self.assertEqual(out["entries"], 1)
        self.assertEqual(out["fills"], 4)
        self.assertEqual(out["settlements"], 3)
        self.assertLess(out["funding_received"], 0)
        self.assertAlmostEqual(out["reconciliation_error"], 0)

    def test_extreme_common_gap_can_still_liquidate_isolated_short(self):
        spot, perp, events, start, end = fixtures(5, rate=0)
        for rows in (spot, perp):
            for i in range(2, 5):
                rows[i].update(open=1100, high=1100, low=1100, close=1100)
        out = lab.simulate(spot, perp, events, lab.variants()[0], start, end,
                           capital=1000, friction=0)
        self.assertEqual(out["liquidations"], 1)
        self.assertEqual(out["entries"], 1)
        self.assertAlmostEqual(out["reconciliation_error"], 0)

    def test_model_is_exact_static_engine_with_allocation_only_changed(self):
        root = Path(__file__).resolve().parents[1]
        def function(path):
            tree = ast.parse(path.read_text())
            return next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "simulate")
        original = ast.unparse(function(root / "propdesk/funding_static.py"))
        original = original.replace("spot_cash, derivative_cash = (capital * 0.2, capital * 0.8)",
                                    "spot_cash, derivative_cash = (capital * SPOT_FRACTION, capital * (1 - SPOT_FRACTION))")
        original = original.replace("budget = min(capital * 0.2, spot_cash)",
                                    "budget = min(capital * SPOT_FRACTION, spot_cash)")
        original = original.replace("Each bucket has20% capital spot cash and80% isolated collateral.",
                                    "Each bucket has fixed TRAIN-calibrated spot cash and remaining isolated collateral.")
        self.assertEqual(original, ast.unparse(function(root / "propdesk/funding_calibrated.py")))


if __name__ == "__main__":
    unittest.main()
