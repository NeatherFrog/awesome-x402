"""Static carry allocation, accounting and causal risk tests; synthetic only."""
from pathlib import Path
import ast
import unittest

from propdesk import funding_static as lab
from tests.test_funding_lab import fixtures


class FundingStaticTests(unittest.TestCase):
    def test_two_leg_account_allocates_twenty_spot_eighty_collateral(self):
        spot, perp, events, start, end = fixtures(3)
        out = lab.simulate(spot, perp, events, lab.variants()[0], start, end,
                           capital=1000, friction=0)
        self.assertEqual(out["records"][0]["quantity"], 2)
        self.assertEqual(out["settlements"], 1)
        self.assertAlmostEqual(out["daily_equity"][-1], 1000.2)
        self.assertAlmostEqual(out["reconciliation_error"], 0)

    def test_large_common_price_rally_does_not_transfer_spot_profit_or_liquidate(self):
        spot, perp, events, start, end = fixtures(5, rate=0)
        for rows in (spot, perp):
            for i in range(2, 5):
                rows[i].update(open=300, low=300, high=300, close=300)
        out = lab.simulate(spot, perp, events, lab.variants()[0], start, end,
                           capital=1000, friction=0)
        self.assertEqual(out["liquidations"], 0)
        self.assertEqual(out["entries"], 1)
        self.assertAlmostEqual(out["daily_equity"][-1], 1000)
        # Collateral remains800; unrealized short loss400 uses that wallet.
        self.assertAlmostEqual(out["daily_rows"]["2024-01-01"]["isolated_collateral"], 400)

    def test_finite_collateral_can_still_liquidate_on_extreme_gap(self):
        spot, perp, events, start, end = fixtures(5, rate=0)
        for rows in (spot, perp):
            for i in range(2, 5):
                rows[i].update(open=510, low=510, high=510, close=510)
        out = lab.simulate(spot, perp, events, lab.variants()[0], start, end,
                           capital=1000, friction=0)
        self.assertEqual(out["liquidations"], 1)
        self.assertEqual(out["entries"], 1)
        self.assertAlmostEqual(out["liquidation_penalties"], 10.2)
        self.assertAlmostEqual(out["reconciliation_error"], 0)

    def test_negative_settlements_are_paid_without_switching_or_reentry(self):
        spot, perp, events, start, end = fixtures(8, rate=-.001)
        out = lab.simulate(spot, perp, events, lab.variants()[0], start, end,
                           capital=1000, friction=0, positive_funding_multiplier=.75)
        self.assertEqual(out["entries"], 1)
        self.assertEqual(out["fills"], 4)
        self.assertAlmostEqual(out["funding_received"], -1.2)
        self.assertLess(out["return_pct"], 0)

    def test_both_leg_friction_and_adverse_basis_reconcile(self):
        spot, perp, events, start, end = fixtures(5, rate=0)
        perp[-1].update(open=120, low=120, high=120, close=120)
        out = lab.simulate(spot, perp, events, lab.variants()[0], start, end, capital=1000)
        self.assertGreater(out["fees"], 0)
        self.assertLess(out["paired_price_pnl"], -39)
        self.assertAlmostEqual(out["reconciliation_error"], 0, places=8)

    def test_later_positive_funding_cannot_rescue_extreme_intrabar_high(self):
        spot, perp, events, start, end = fixtures(4, rate=0)
        events[2]["time"] = "2024-01-01T02:00:00.001Z"
        events[2]["funding_rate"] = .9
        perp[2].update(open=100, high=510, low=100, close=100)
        out = lab.simulate(spot, perp, events, lab.variants()[0], start, end,
                           capital=1000, friction=0)
        self.assertEqual(out["liquidations"], 1)
        self.assertEqual(out["funding_received"], 0)

    def test_model_derivation_changes_only_allocation_and_docstring(self):
        root = Path(__file__).resolve().parents[1]
        original_tree = ast.parse((root / "propdesk/funding_lab.py").read_text())
        static_tree = ast.parse((root / "propdesk/funding_static.py").read_text())
        original = next(node for node in original_tree.body if isinstance(node, ast.FunctionDef) and node.name == "simulate")
        static = next(node for node in static_tree.body if isinstance(node, ast.FunctionDef) and node.name == "simulate")
        source = ast.unparse(original)
        source = source.replace("spot_cash, derivative_cash = (capital / 2, capital / 2)",
                                "spot_cash, derivative_cash = (capital * 0.2, capital * 0.8)")
        source = source.replace("budget = min(capital / 2, spot_cash)",
                                "budget = min(capital * 0.2, spot_cash)")
        source = source.replace("Each bucket has half capital spot cash, half isolated perpetual collateral.",
                                "Each bucket has20% capital spot cash and80% isolated collateral.")
        self.assertEqual(source, ast.unparse(static))


if __name__ == "__main__":
    unittest.main()
