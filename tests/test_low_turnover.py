from datetime import datetime, timedelta, timezone
import copy
import math
import unittest

from propdesk import low_turnover as low


def fixture(days=130):
    first = datetime(2024, 1, 1, tzinfo=timezone.utc)
    result = []
    for i in range(days*24):
        price = 100*math.exp(i*.00005+.015*math.sin(i*.02)+.005*math.sin(i*.13))
        result.append({"time": (first+timedelta(hours=i)).isoformat().replace("+00:00", "Z"),
                       "open": price, "high": price*1.002, "low": price*.998,
                       "close": price*1.0001, "volume": 1000})
    return {"BTCUSDT": result, "ETHUSDT": copy.deepcopy(result)}


class LowTurnoverTests(unittest.TestCase):
    def test_calendar_month_end_clamp_and_year_boundary(self):
        stamp = datetime(2024, 3, 31, 16, tzinfo=timezone.utc)
        self.assertEqual(low.months_back(stamp, 1), datetime(2024, 2, 29, 16, tzinfo=timezone.utc))
        self.assertEqual(low.months_back(stamp, 3), datetime(2023, 12, 31, 16, tzinfo=timezone.utc))

    def test_grid_and_family_counts(self):
        grid = low.grid()
        self.assertEqual(len(grid), 64)
        self.assertEqual(len({v["id"] for v in grid}), 64)
        self.assertEqual(len({v["family"] for v in grid}), 4)

    def test_missing_entire_aggregate_group_rejected(self):
        hourly = fixture(3)["BTCUSDT"]
        del hourly[24:48]
        with self.assertRaisesRegex(ValueError, "between aggregate"):
            low.aggregate(hourly, 24)

    def test_aggregation_complete_and_causal(self):
        hourly = fixture(2)["BTCUSDT"]
        bars = low.aggregate(hourly, 24)
        self.assertEqual(bars[0]["open"], hourly[0]["open"])
        self.assertEqual(bars[0]["close"], hourly[23]["close"])
        self.assertEqual(bars[0]["high"], max(row["high"] for row in hourly[:24]))
        self.assertEqual(bars[0]["volume"], 24000)
        with self.assertRaises(ValueError):
            low.aggregate(hourly[:-1], 24)
        broken = copy.deepcopy(hourly)
        del broken[5]
        broken.append({**broken[-1], "time": "2024-01-03T00:00:00Z"})
        with self.assertRaisesRegex(ValueError, "Missing"):
            low.aggregate(broken, 24)

    def test_all64_variants_ignore_future_prices(self):
        data = fixture()
        changed = copy.deepcopy(data)
        for rows in changed.values():
            for row in rows[110*24:]:
                for key in ("open", "high", "low", "close"):
                    row[key] *= 4
        features = {n: low.Features(data, n) for n in (4, 24)}
        future = {n: low.Features(changed, n) for n in (4, 24)}
        for variant in low.grid():
            with self.subTest(id=variant["id"]):
                n = variant["resolution_hours"]
                before = low.target_weights(features[n], variant)
                after = low.target_weights(future[n], variant)
                boundary = 110*24//n
                self.assertEqual(before[:boundary+1], after[:boundary+1])
                for i, row in enumerate(before):
                    if row:
                        self.assertEqual(row["signal_time"], features[n].times[i-1])
                        self.assertEqual(row["asof"], features[n].times[i])
                        self.assertLessEqual(sum(row["weights"].values()), 1+1e-12)

    def test_rotation_cash_cap_and_cashflow_conservation(self):
        feature = low.Features(fixture(5), 24)
        signal = [None]*5
        for i, weights in ((1, {"BTCUSDT": 1., "ETHUSDT": 0.}), (2, {"BTCUSDT": 0., "ETHUSDT": 1.})):
            signal[i] = {"weights": weights, "signal_time": feature.times[i-1], "asof": feature.times[i]}
        result = low.simulate(feature, signal, "2024-01-01", "2024-01-06")
        self.assertEqual(result["metrics"]["closed_position_episodes"], 2)
        self.assertAlmostEqual(result["metrics"]["final_equity"], 100_000+result["metrics"]["completed_episode_pnl"], places=7)
        self.assertGreater(result["metrics"]["fees_paid"], 0)
        self.assertGreater(result["metrics"]["adverse_fill_cost"], 0)
        self.assertLessEqual(result["metrics"]["max_exposure_fraction"], 1.001)
        self.assertEqual(result["episodes"][-1]["exit_time"], "2024-01-06T00:00:00Z")

    def test_rebalance_fills_do_not_inflate_episode_count(self):
        feature = low.Features(fixture(8), 24)
        signal = [None]*8
        for i in (1, 2, 3, 4, 5, 6):
            signal[i] = {"weights": {"BTCUSDT": .3 if i%2 else .2, "ETHUSDT": 0.},
                         "signal_time": feature.times[i-1], "asof": feature.times[i]}
        result = low.simulate(feature, signal, "2024-01-01", "2024-01-09")
        self.assertEqual(result["metrics"]["closed_position_episodes"], 1)
        self.assertGreater(result["metrics"]["rebalance_fill_count"], 4)
        self.assertAlmostEqual(result["metrics"]["completed_episode_pnl"], result["metrics"]["final_equity"]-100_000, places=7)

    def test_fee_stress_worsens_constant_price(self):
        data = fixture(5)
        for rows in data.values():
            for row in rows:
                row.update(open=100., high=100., low=100., close=100.)
        feature = low.Features(data, 24)
        signal = [None]*5
        signal[1] = {"weights": {"BTCUSDT": .5, "ETHUSDT": .5}, "signal_time": feature.times[0], "asof": feature.times[1]}
        base = low.simulate(feature, signal, "2024-01-01", "2024-01-06")
        stress = low.simulate(feature, signal, "2024-01-01", "2024-01-06", cost_multiplier=2)
        self.assertLess(stress["metrics"]["return_pct"], base["metrics"]["return_pct"])
        self.assertLess(base["metrics"]["return_pct"], 0)

    def test_final_bar_rebalance_disabled(self):
        feature = low.Features(fixture(5), 24)
        signal = [None]*5
        signal[-1] = {"weights": {"BTCUSDT": 1., "ETHUSDT": 0.}, "signal_time": feature.times[-2], "asof": feature.times[-1]}
        result = low.simulate(feature, signal, "2024-01-01", "2024-01-06")
        self.assertEqual(result["fills"], [])
        self.assertEqual(result["metrics"]["final_equity"], 100_000)


if __name__ == "__main__":
    unittest.main()
