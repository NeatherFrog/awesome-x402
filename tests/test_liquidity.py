"""Causal pivot/FVG timing and adverse executable-price replay contracts."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import unittest

from propdesk.liquidity import VARIANTS, backtest, detect_setups, normalize_config


def fixture(*, start=None, count=29):
    start = start or datetime(2025, 1, 6, tzinfo=timezone.utc)
    bars = [{"time": (start + timedelta(minutes=index * 5)).isoformat().replace("+00:00", "Z"),
             "open": 100, "high": 101, "low": 99, "close": 100, "volume": 100}
            for index in range(count)]
    changes = {16: (100, 101, 95, 100), 19: (100, 102, 99, 101),
               20: (101, 105, 99, 102), 21: (102, 103, 99, 100),
               22: (100, 102, 99, 101), 23: (104.5, 106, 103, 104),
               24: (104, 104.5, 99, 100), 25: (100, 101, 93, 94),
               26: (96, 102, 95, 100), 27: (99, 103, 98, 102),
               28: (102, 103, 92, 94)}
    for index, values in changes.items():
        if index < count:
            bars[index].update(zip(("open", "high", "low", "close"), values))
    return bars


def mirror(bars):
    result = deepcopy(bars)
    for source, target in zip(bars, result):
        target.update(open=200 - source["open"], high=200 - source["low"],
                      low=200 - source["high"], close=200 - source["close"])
    return result


def replace(bar, opening, high, low, close):
    bar.update(open=opening, high=high, low=low, close=close)


class LiquidityDetectionTests(unittest.TestCase):
    def test_signal_is_third_bar_close_not_open(self):
        bars = fixture()
        self.assertEqual(detect_setups(bars[:25]), [])
        setups = detect_setups(bars[:26])
        self.assertEqual(len(setups), 1)
        setup = setups[0]
        self.assertEqual(setup["signal_time"], "2025-01-06T02:10:00Z")
        self.assertEqual(setup["signal_index"], 25)
        self.assertEqual(setup["status"], "candidate")
        self.assertEqual(setup["reference_available_at"], "2025-01-06T01:55:00Z")
        self.assertLess(setup["reference_available_at"], setup["sweep_time"])
        self.assertEqual(setup["expires_at"], "2025-01-06T02:40:00Z")
        self.assertEqual((setup["entry_low"], setup["entry_high"], setup["entry"]), (101, 103, 102))
        self.assertAlmostEqual(setup["target"], setup["entry"] - 2 * (setup["stop"] - setup["entry"]))
        self.assertFalse(setup["qualified"])

    def test_prefix_invariance_of_all_signal_fields(self):
        bars = fixture(count=50)
        reference = detect_setups(bars[:26])[0]
        immutable = {key: value for key, value in reference.items() if not key.startswith("status")}
        for length in range(26, len(bars) + 1):
            with self.subTest(length=length):
                actual = detect_setups(bars[:length])[0]
                self.assertEqual({key: value for key, value in actual.items() if not key.startswith("status")}, immutable)

    def test_future_price_mutation_cannot_change_earlier_signal(self):
        bars = fixture(count=50)
        reference = detect_setups(bars)[0]
        for bar in bars[26:]:
            replace(bar, 180, 190, 170, 175)
        changed = detect_setups(bars)[0]
        self.assertEqual(changed["id"], reference["id"])
        for key in ("entry", "stop", "target", "reference_price", "atr14_before_signal"):
            self.assertEqual(changed[key], reference[key])

    def test_unconfirmed_pivot_does_not_supply_reference(self):
        bars = fixture()
        bars[20]["high"] = 102
        bars[22]["high"] = 105
        self.assertEqual(detect_setups(bars), [])

    def test_equal_pivot_highs_are_excluded(self):
        bars = fixture()
        bars[19]["high"] = 105
        self.assertEqual(detect_setups(bars), [])

    def test_sweep_requires_rejection_close(self):
        bars = fixture()
        bars[23]["close"] = 105
        self.assertEqual(detect_setups(bars), [])

    def test_mss_uses_opposing_pivot_known_before_sweep(self):
        bars = fixture()
        bars[16]["low"] = 90
        self.assertEqual(detect_setups(bars, variant="mss_all"), [])
        self.assertEqual(len(detect_setups(bars, variant="sweep_all")), 1)

    def test_displacement_cannot_be_the_sweep_bar(self):
        bars = fixture(count=24)
        replace(bars[23], 105, 106, 93, 94)
        self.assertEqual(detect_setups(bars), [])

    def test_bullish_and_bearish_are_exact_mirrors_before_costs(self):
        short = detect_setups(fixture())[0]
        long = detect_setups(mirror(fixture()))[0]
        self.assertEqual(long["side"], "long")
        self.assertAlmostEqual(long["entry"], 200 - short["entry"])
        self.assertAlmostEqual(long["stop"], 200 - short["stop"])
        self.assertAlmostEqual(long["target"], 200 - short["target"])
        config = {"fee_bps": 0, "slippage_bps": 0, "spread_bps": 0}
        self.assertAlmostEqual(backtest(fixture(), config=config)["metrics"]["net_profit"],
                               backtest(mirror(fixture()), config=config)["metrics"]["net_profit"])

    def test_lunch_uses_sweep_close_ny_weekday_and_dst(self):
        winter = fixture(start=datetime(2025, 1, 6, 15, tzinfo=timezone.utc))
        summer = fixture(start=datetime(2025, 7, 7, 15, tzinfo=timezone.utc))
        summer_lunch = fixture(start=datetime(2025, 7, 7, 14, tzinfo=timezone.utc))
        weekend = fixture(start=datetime(2025, 1, 4, 15, tzinfo=timezone.utc))
        self.assertEqual(len(detect_setups(winter, variant="mss_lunch")), 1)
        self.assertEqual(detect_setups(summer, variant="mss_lunch"), [])
        self.assertEqual(len(detect_setups(summer_lunch, variant="mss_lunch")), 1)
        self.assertEqual(detect_setups(weekend, variant="mss_lunch"), [])

    def test_strict_entry_trade_through_not_equal_touch(self):
        bars = fixture(count=27)
        self.assertEqual(detect_setups(bars)[0]["status"], "candidate")
        self.assertEqual(backtest(bars)["metrics"]["total_trades"], 0)
        self.assertEqual(detect_setups(fixture())[0]["status"], "triggered")

    def test_six_bar_expiry_and_no_fill_after_expiry(self):
        bars = fixture(count=34)
        for bar in bars[26:]:
            replace(bar, 100, 101, 99, 100)
        self.assertEqual(detect_setups(bars[:31])[0]["status"], "candidate")
        self.assertEqual(detect_setups(bars[:32])[0]["status"], "expired")
        replace(bars[32], 102, 103, 100, 102)
        self.assertEqual(backtest(bars)["metrics"]["total_trades"], 0)

    def test_immediate_gap_before_order_placement_invalidates(self):
        bars = fixture()
        replace(bars[26], 110, 111, 109, 110)
        self.assertEqual(detect_setups(bars)[0]["status"], "invalidated")
        self.assertEqual(backtest(bars)["metrics"]["total_trades"], 0)

    def test_inputs_not_mutated_and_json_has_no_infinity(self):
        bars = fixture()
        original = deepcopy(bars)
        for variant in VARIANTS:
            json.dumps(backtest(bars, variant=variant), allow_nan=False)
        self.assertEqual(bars, original)

    def test_irregular_times_rejected_instead_of_imputed(self):
        bars = fixture()
        del bars[10]
        with self.assertRaisesRegex(ValueError, "missing or irregular"):
            backtest(bars)


class LiquidityBacktestTests(unittest.TestCase):
    def test_costs_reduce_returns_and_risk_includes_costs(self):
        free = backtest(fixture(), config={"fee_bps": 0, "slippage_bps": 0, "spread_bps": 0})
        paid = backtest(fixture())
        stressed = backtest(fixture(), config={"fee_bps": 20, "slippage_bps": 4, "spread_bps": 2})
        self.assertAlmostEqual(free["metrics"]["net_profit"], 500)
        self.assertGreater(free["metrics"]["net_profit"], paid["metrics"]["net_profit"])
        self.assertGreater(paid["metrics"]["net_profit"], stressed["metrics"]["net_profit"])
        self.assertAlmostEqual(paid["trades"][0]["planned_risk_amount"], 250)
        self.assertAlmostEqual(paid["metrics"]["net_profit"], sum(t["net_pnl"] for t in paid["trades"]))
        self.assertGreater(paid["metrics"]["total_fees"], 0)
        self.assertFalse(paid["metrics"]["qualified"])

    def test_entry_and_stop_collision_is_loss(self):
        bars = fixture(count=28)
        replace(bars[27], 99, 108, 92, 100)
        result = backtest(bars)
        trade = result["trades"][0]
        self.assertEqual(trade["exit_reason"], "entry_stop_ambiguous")
        self.assertLess(trade["net_pnl"], 0)
        self.assertAlmostEqual(trade["net_pnl"], -250)
        self.assertEqual(result["metrics"]["ambiguous_bars"], 1)

    def test_stop_target_collision_after_entry_is_loss(self):
        bars = fixture()
        replace(bars[28], 102, 108, 92, 100)
        trade = backtest(bars)["trades"][0]
        self.assertEqual(trade["exit_reason"], "stop_first_collision")
        self.assertAlmostEqual(trade["net_pnl"], -250)

    def test_resting_order_gap_through_stop_is_adverse(self):
        bars = fixture(count=28)
        replace(bars[27], 110, 111, 109, 110)
        trade = backtest(bars)["trades"][0]
        self.assertEqual(trade["exit_reason"], "gap_stop")
        self.assertEqual(trade["exit_raw"], 110)
        self.assertLess(trade["net_pnl"], -250)

    def test_open_position_gap_stop_uses_opening_price(self):
        bars = fixture()
        replace(bars[28], 110, 111, 109, 110)
        trade = backtest(bars)["trades"][0]
        self.assertEqual(trade["exit_reason"], "gap_stop")
        self.assertGreater(trade["exit_raw"], trade["stop"])
        self.assertLess(trade["net_pnl"], -250)

    def test_entry_bar_target_is_not_credited(self):
        bars = fixture(count=28)
        replace(bars[27], 99, 103, 92, 100)
        trade = backtest(bars)["trades"][0]
        self.assertEqual(trade["exit_reason"], "end_of_data_hypothetical")
        self.assertTrue(trade["hypothetical_boundary_exit"])
        self.assertNotEqual(trade["exit_raw"], trade["target"])

    def test_target_requires_strict_trade_through(self):
        bars = fixture()
        target = detect_setups(bars)[0]["target"]
        replace(bars[28], 100, 102, target, 95)
        trade = backtest(bars)["trades"][0]
        self.assertEqual(trade["exit_reason"], "end_of_data_hypothetical")

    def test_gross_leverage_cap_is_enforced(self):
        result = backtest(fixture(), config={"max_gross_leverage": .01})
        trade = result["trades"][0]
        self.assertLessEqual(trade["quantity"] * trade["entry_price"], 1000 + 1e-10)
        self.assertLess(trade["planned_risk_amount"], 250)

    def test_configs_and_unknown_variants_fail_closed(self):
        for config in ({"fee_bps": True}, {"initial_balance": float("inf")},
                       {"slippage_bps": -1}, {"expiry_bars": 7}, {"fee_typo": 0},
                       {"interval_seconds": True}, {"risk_pct": 0}):
            with self.subTest(config=config), self.assertRaises(ValueError):
                normalize_config(config)
        with self.assertRaises(ValueError):
            backtest(fixture(), variant="best_after_test")

    def test_large_history_validation_exceeds_old_30000_limit(self):
        bars = fixture(count=200001)
        result = backtest(bars)
        self.assertEqual(result["metrics"]["total_setups"], 1)


if __name__ == "__main__":
    unittest.main()
