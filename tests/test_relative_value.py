from datetime import datetime, timedelta, timezone
import copy
import math
import unittest

from propdesk import relative_value as pair
from scripts import research_relative_value as driver


def fixture(n=1000, *, constant=False):
    beginning = datetime(2024, 1, 1, tzinfo=timezone.utc)
    rows = {s: [] for s in pair.SYMBOLS}
    for i in range(n):
        x = 0 if constant else i*.00004+.008*math.sin(i*.05)
        residual = 0 if constant else .012*math.sin(i*.11)
        prices = {"BTCUSDT": 40000*math.exp(1.2*x+residual), "ETHUSDT": 2000*math.exp(x)}
        for s, price in prices.items():
            rows[s].append({"time": (beginning+timedelta(hours=i)).isoformat().replace("+00:00", "Z"),
                            "open": price, "high": price*1.001, "low": price*.999, "close": price, "volume": 100})
    return rows


def fixed_signal(features, entry=1):
    rows = [None]*len(features.times)
    rows[entry] = {"alpha": math.log(40000)-math.log(2000)+.04, "beta": 1.0,
                   "sigma": .02, "z": -2., "entry": True, "signal_time": features.times[entry-1]}
    return rows


def funding_at(features, index, rates=(.001, .002), micros=0):
    stamp = (datetime.fromisoformat(features.times[index].replace("Z", "+00:00"))+timedelta(microseconds=micros)).isoformat().replace("+00:00", "Z")
    return {s: [{"time": stamp, "known_at": stamp, "funding_rate": rate,
                 "funding_interval_hours": 8, "rate_kind": "realized_settlement_outcome"}]
            for s, rate in zip(pair.SYMBOLS, rates)}


class RelativeValueTests(unittest.TestCase):
    def test_grid_count(self):
        self.assertEqual(len(pair.grid()), 48)
        self.assertEqual(len({v["id"] for v in pair.grid()}), 48)

    def test_all48_decisions_prefix_causal(self):
        data = fixture()
        changed = copy.deepcopy(data)
        for rows in changed.values():
            for row in rows[850:]:
                for key in ("open", "high", "low", "close"):
                    row[key] *= 3
        before, after = pair.PairFeatures(data), pair.PairFeatures(changed)
        for variant in pair.grid():
            with self.subTest(id=variant["id"]):
                self.assertEqual(pair.observations(before, variant)[:851], pair.observations(after, variant)[:851])

    def run_pair(self, feature, funding, signal=None, variant=None, **kwargs):
        return pair.simulate(feature, signal or fixed_signal(feature), funding,
                             variant or pair.grid()[0], "2024-01-01", "2024-01-03", **kwargs)

    def test_margin_cashflows_fees_bothlegs(self):
        features = pair.PairFeatures(fixture(24, constant=True))
        result = self.run_pair(features, {s: [] for s in pair.SYMBOLS})
        self.assertEqual(len(result["trades"]), 1)
        self.assertAlmostEqual(result["metrics"]["final_equity"], 100000+sum(t["pnl"] for t in result["trades"]), places=7)
        self.assertGreater(result["metrics"]["fees_paid"], 0)
        self.assertGreater(result["metrics"]["adverse_fill_cost"], 0)
        self.assertGreaterEqual(min(r["available_cash"] for r in result["equity_curve"]), 0)
        self.assertLess(result["metrics"]["return_pct"], 0)

    def test_funding_payers_receivers_actual_ms(self):
        features = pair.PairFeatures(fixture(24, constant=True))
        events = funding_at(features, 8, micros=2000)
        result = self.run_pair(features, events)
        records = result["funding_ledger"]
        self.assertEqual(len(records), 2)
        self.assertTrue(all(r["time"].endswith(".002000Z") for r in records))
        self.assertLess(next(r["pnl"] for r in records if r["symbol"] == "BTCUSDT"), 0)
        self.assertGreater(next(r["pnl"] for r in records if r["symbol"] == "ETHUSDT"), 0)
        self.assertAlmostEqual(result["metrics"]["final_equity"], 100000+sum(t["pnl"] for t in result["trades"]), places=7)

    def test_new_entry_cannot_receive_later_millisecond_funding(self):
        features = pair.PairFeatures(fixture(24, constant=True))
        result = self.run_pair(features, funding_at(features, 1, micros=2000))
        self.assertEqual(result["funding_ledger"], [])
        self.assertEqual(result["metrics"]["funding_pnl"], 0)

    def test_open_exit_precedes_future_settlement(self):
        features = pair.PairFeatures(fixture(24, constant=True))
        variant = {**pair.grid()[0], "max_hold_hours": 7}
        result = self.run_pair(features, funding_at(features, 8, micros=2000), variant=variant)
        self.assertEqual(result["trades"][0]["exit_time"], features.times[8])
        self.assertEqual(result["funding_ledger"], [])

    def test_future_funding_does_not_affect_entry_sizing(self):
        features = pair.PairFeatures(fixture(24, constant=True))
        a = self.run_pair(features, funding_at(features, 8))
        b = self.run_pair(features, funding_at(features, 8, rates=(.1, -.1)))
        for s in pair.SYMBOLS:
            self.assertEqual(a["trades"][0]["legs"][s]["quantity"], b["trades"][0]["legs"][s]["quantity"])

    def test_hedge_model_frozen_at_entry(self):
        features = pair.PairFeatures(fixture(24, constant=True))
        signal = fixed_signal(features)
        for i in range(2, len(signal)):
            signal[i] = {"alpha": 0, "beta": 2.5, "sigma": .1, "z": 10, "entry": False, "signal_time": features.times[i-1]}
        result = self.run_pair(features, {s: [] for s in pair.SYMBOLS}, signal=signal)
        self.assertEqual(result["trades"][0]["model"]["beta"], 1)

    def test_liquidation_proxy_no_cash_injection(self):
        data = fixture(24, constant=True)
        data["ETHUSDT"][2]["high"] = 100000
        features = pair.PairFeatures(data)
        result = self.run_pair(features, {s: [] for s in pair.SYMBOLS})
        self.assertEqual(result["metrics"]["liquidation_count"], 1)
        self.assertGreater(result["metrics"]["unfunded_isolated_deficit"], 0)
        self.assertGreaterEqual(min(r["equity"] for r in result["equity_curve"]), 0)
        self.assertGreaterEqual(min(r["available_cash"] for r in result["equity_curve"]), 0)
        self.assertAlmostEqual(result["metrics"]["final_equity"], 100000+sum(t["pnl"] for t in result["trades"]), places=7)

    def test_doubled_friction_worsens_flat_prices(self):
        features = pair.PairFeatures(fixture(24, constant=True))
        funding = {s: [] for s in pair.SYMBOLS}
        a, b = self.run_pair(features, funding), self.run_pair(features, funding, cost_multiplier=2)
        self.assertLess(b["metrics"]["return_pct"], a["metrics"]["return_pct"])

    def test_positive_exact_funding_cannot_rescue_gap_liquidation(self):
        data = fixture(24, constant=True)
        data["ETHUSDT"][2].update(open=5000, high=5001, low=4999, close=5000)
        features = pair.PairFeatures(data)
        result = self.run_pair(features, funding_at(features, 2, rates=(0, 1)))
        self.assertEqual(result["metrics"]["liquidation_count"], 1)
        self.assertEqual(result["funding_ledger"], [])

    def test_future_positive_funding_cannot_rescue_intrabar_liquidation(self):
        data = fixture(24, constant=True)
        data["ETHUSDT"][2]["high"] = 5000
        features = pair.PairFeatures(data)
        signal = fixed_signal(features)
        signal[1].update(alpha=math.log(40000)-math.log(2000)+4, sigma=2)
        result = self.run_pair(features, funding_at(features, 2, rates=(0, 5), micros=2000), signal=signal)
        self.assertEqual(result["metrics"]["liquidation_count"], 1)
        ethfunding = next(r for r in result["funding_ledger"] if r["symbol"] == "ETHUSDT")
        self.assertTrue(ethfunding["intrabar_entitlement_ambiguous"])
        self.assertEqual(ethfunding["pnl"], 0)

    def test_stressed_liquidation_and_unpaid_debt_disqualify(self):
        features = pair.PairFeatures(fixture(24, constant=True))
        base = self.run_pair(features, {s: [] for s in pair.SYMBOLS})
        stressed = copy.deepcopy(base)
        stressed["metrics"].update(liquidation_count=1, unfunded_isolated_deficit=1)
        assessed = driver.evaluate(base, stressed, ["2024-01-01", "2024-01-02"], "training", 42)
        self.assertFalse(assessed["checks"]["no_proxy_liquidation"])
        self.assertFalse(assessed["checks"]["no_unfunded_margin_deficit"])
        self.assertFalse(assessed["passed"])
        self.assertEqual(assessed["status"], "not_qualified")


if __name__ == "__main__":
    unittest.main()
