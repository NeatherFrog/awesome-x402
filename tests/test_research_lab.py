import copy
from datetime import datetime, timedelta, timezone
import tempfile
from pathlib import Path
import unittest

from propdesk import market, research_lab as lab
from scripts import research_broad


def bars(count=12, price=100):
    beginning = datetime(2024, 1, 1, tzinfo=timezone.utc)
    return [{"time": (beginning+timedelta(hours=i)).isoformat().replace("+00:00", "Z"),
             "open": price, "high": price+1, "low": price-1, "close": price, "volume": 1000}
            for i in range(count)]


def observations(data, enter=1, leave=None, atr=1):
    result = [None]*len(data)
    for i in range(1, len(data)):
        result[i] = {"entry": i == enter, "exit": i == leave, "atr": atr,
                     "signal_time": data[i-1]["time"]}
    return result


VARIANT = {"stop_atr": 2, "max_hold": 72}


class ResearchLabTests(unittest.TestCase):
    def simulate(self, data, signal, **kwargs):
        return lab.simulate_asset(data, signal, VARIANT, 0, len(data), initial=1000,
                                  risk_budget=10, fee_bps=0, slip_bps=0, full_spread_bps=0, **kwargs)

    def test_bounded_distinct_grid(self):
        grid = lab.make_grid()
        self.assertEqual(len(grid), 208)
        self.assertEqual(len({x["id"] for x in grid}), 208)
        self.assertEqual(len({x["family"] for x in grid}), 9)
        self.assertEqual(lab.digest(grid), lab.digest(lab.make_grid()))

    def test_all_variants_prefix_causal(self):
        data = bars(330)
        for i, row in enumerate(data):
            price = 100+i*.1+((i%11)-5)*.15
            row.update(open=price-.05, high=price+.25, low=price-.3, close=price,
                       volume=1000+(i%13)*80)
        changed = copy.deepcopy(data)
        for row in changed[270:]:
            for key in ("open", "high", "low", "close"):
                row[key] *= 5
            row["volume"] *= 3
        original, future = lab.FeatureCache(data), lab.FeatureCache(changed)
        for variant in lab.make_grid():
            with self.subTest(variant=variant["id"]):
                left, right = lab.decisions(original, variant), lab.decisions(future, variant)
                self.assertEqual(left[:271], right[:271])
                for i, decision in enumerate(left):
                    if decision:
                        self.assertEqual(decision["signal_time"], data[i-1]["time"])

    def test_next_open_not_signal_close_fill(self):
        data = bars()
        data[1].update(open=110, high=111, low=109, close=110)
        result = self.simulate(data, observations(data))
        self.assertEqual(result["trades"][0]["entry_price"], 110)
        self.assertEqual(result["trades"][0]["signal_time"], data[0]["time"])

    def test_entry_bar_stop_and_no_reentry(self):
        data = bars()
        data[1].update(low=95)
        result = self.simulate(data, observations(data))
        self.assertEqual(len(result["trades"]), 1)
        self.assertEqual(result["trades"][0]["reason"], "entry_bar_stop")
        self.assertEqual(result["trades"][0]["pnl"], -10)

    def test_gap_stop_before_known_indicator_exit(self):
        data = bars()
        data[2].update(open=90, high=91, low=89, close=90)
        result = self.simulate(data, observations(data, leave=2))
        trade = result["trades"][0]
        self.assertEqual(trade["reason"], "gap_stop")
        self.assertEqual(trade["exit_price"], 90)
        self.assertLess(trade["pnl"], -trade["risk_budget"])

    def test_open_indicator_exit_precedes_future_low(self):
        data = bars()
        data[2].update(open=102, high=103, low=10, close=100)
        result = self.simulate(data, observations(data, leave=2))
        self.assertEqual(result["trades"][0]["reason"], "indicator_exit")
        self.assertEqual(result["trades"][0]["exit_price"], 102)
        self.assertGreater(result["equity_curve"][2]["worst_equity"], 999)

    def test_final_bar_no_new_entry(self):
        data = bars()
        result = self.simulate(data, observations(data, enter=len(data)-1))
        self.assertEqual(result["trades"], [])
        self.assertEqual(result["metrics"]["final_equity"], 1000)

    def test_boundary_close_timestamp_is_not_open(self):
        data = bars()
        result = self.simulate(data, observations(data))
        trade = result["trades"][0]
        self.assertTrue(trade["boundary_liquidation"])
        self.assertEqual(trade["exit_timing"], "close")
        self.assertEqual(trade["exit_bar_time"], data[-1]["time"])
        self.assertEqual(trade["exit_time"], "2024-01-01T12:00:00Z")

    def test_cash_cap_and_roundtrip_cost_accounting(self):
        data = bars()
        result = lab.simulate_asset(data, observations(data, atr=.01), VARIANT, 0, len(data),
                                    initial=1000, risk_budget=100, fee_bps=10, slip_bps=2, full_spread_bps=1)
        trade = result["trades"][0]
        self.assertLessEqual(trade["entry_cost"], 1000)
        self.assertAlmostEqual(result["metrics"]["final_equity"], 1000+sum(t["pnl"] for t in result["trades"]), places=8)
        self.assertGreater(result["metrics"]["fees_paid"], 0)
        self.assertGreater(result["metrics"]["adverse_fill_cost"], 0)
        self.assertLess(result["metrics"]["return_pct"], 0)

    def test_training_only_correlation_independent_of_future(self):
        data = bars(400)
        for i, row in enumerate(data):
            row.update(open=100+i*.05, high=101+i*.05, low=99+i*.05, close=100+i*.05)
        cache = lab.FeatureCache(data)
        correlations = research_broad.training_correlations({"BTCUSDT": cache}, {"fixed": [0]*20})
        self.assertEqual(len(correlations["feature_forward_correlations"]), 18)
        for item in correlations["feature_forward_correlations"]:
            self.assertLessEqual(item["observations"], 400-item["forward_hours"])

    def test_hourly_source_gaps_fail_without_imputation(self):
        data = bars()
        del data[5]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"data.csv"
            path.write_text(market.to_csv(data), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "gaps"):
                research_broad.read_csv(path)

    def test_synchronized_portfolio_rejects_dropped_asset_bar(self):
        data = bars(220)
        other = copy.deepcopy(data)
        del other[8]
        caches = {"BTCUSDT": lab.FeatureCache(data), "ETHUSDT": lab.FeatureCache(other)}
        variant = lab.make_grid()[0]
        signal = {s: lab.decisions(c, variant) for s, c in caches.items()}
        with self.assertRaisesRegex(ValueError, "synchronized"):
            lab.portfolio(caches, signal, variant, "2024-01-01", "2024-01-10")


if __name__ == "__main__":
    unittest.main()
