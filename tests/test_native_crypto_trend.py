import copy
from datetime import datetime, timedelta, timezone
import math
import unittest

from propdesk import native_crypto_trend as engine
from scripts import research_native_crypto_trend as driver


def fixture(days=85):
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    data = {s: [] for s in engine.SYMBOLS}
    for i in range(days*288):
        stamp = (start+timedelta(minutes=5*i)).isoformat().replace("+00:00", "Z")
        for s, scale in (("BTCUSDT", 100), ("ETHUSDT", 50)):
            data[s].append({"time": stamp, "open": scale, "high": scale*1.001,
                            "low": scale*.999, "close": scale, "volume": 10})
    return data


def manual_signals(features, entry_day=19, *, side=1, exit_hour=None, both=False):
    observations = {s: {"entry": [0]*(len(features.times)//12),
                        "exit_long": [0]*(len(features.times)//12),
                        "exit_short": [0]*(len(features.times)//12)} for s in engine.SYMBOLS}
    for symbol in engine.SYMBOLS if both else ("BTCUSDT",):
        observations[symbol]["entry"][entry_day*24-1] = side
        if exit_hour is not None:
            observations[symbol]["exit_long"][entry_day*24+exit_hour-1] = 1
            observations[symbol]["exit_short"][entry_day*24+exit_hour-1] = 1
    return observations


def funding_event(features, index, *, rate=.001, milliseconds=0):
    stamp = (datetime.fromisoformat(features.times[index].replace("Z", "+00:00"))+
             timedelta(milliseconds=milliseconds)).isoformat().replace("+00:00", "Z")
    return {"time": stamp, "known_at": stamp, "funding_rate": rate,
            "rate_kind": "realized_settlement_outcome"}


class NativeTrendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = fixture()
        cls.features = engine.NativeFeatures(cls.data)

    def run_trade(self, features=None, observations=None, events=None, variant=None, **kwargs):
        features = features or self.features
        return engine.simulate(features, observations or manual_signals(features),
                               engine.prepare_funding(features, events or {s: [] for s in engine.SYMBOLS}),
                               variant or engine.grid()[0], "2024-01-20", "2024-01-22", keep_native_curve=True, **kwargs)

    def test_registered_grid_has96_unique_hierarchical_variants(self):
        variants = engine.grid()
        self.assertEqual(len(variants), 96)
        self.assertEqual(len({v["id"] for v in variants}), 96)
        self.assertEqual({f: sum(v["family"] == f for v in variants) for f in {v["family"] for v in variants}},
                         {"calendar_ema_trend": 36, "calendar_channel_breakout": 36, "fast_reversion_momentum_context": 24})

    def test_missing_native_bar_cannot_be_imputed(self):
        broken = self.data["BTCUSDT"][:100]+self.data["BTCUSDT"][101:]
        with self.assertRaisesRegex(ValueError, "Missing"):
            engine.PackedBars(broken)

    def test_incomplete_utc_day_cannot_supply_features(self):
        with self.assertRaisesRegex(ValueError, "Complete UTC"):
            engine.NativeFeatures({s: self.data[s][:-1] for s in engine.SYMBOLS})

    def test_all96_observations_future_prefix_causal(self):
        changed = copy.deepcopy(self.data)
        boundary = 70*288+144
        for rows in changed.values():
            for row in rows[boundary:]:
                for key in ("open", "high", "low", "close"):
                    row[key] *= 4
        altered = engine.NativeFeatures(changed)
        for variant in engine.grid():
            before, after = self.features.observations(variant), altered.observations(variant)
            size = 12 if variant["decision_resolution"] == "hourly" else 288
            for symbol in engine.SYMBOLS:
                for field in ("entry", "exit_long", "exit_short"):
                    self.assertEqual(before[symbol][field][:boundary//size], after[symbol][field][:boundary//size])

    def test_native_cash_pnl_fees_and_funding_conservation(self):
        events = {s: [] for s in engine.SYMBOLS}
        events["BTCUSDT"] = [funding_event(self.features, 19*288+12, milliseconds=2)]
        result = self.run_trade(events=events)
        self.assertEqual(len(result["trades"]), 1)
        self.assertAlmostEqual(result["metrics"]["final_equity"], 100000+math.fsum(t["pnl"] for t in result["trades"]), places=7)
        self.assertLess(result["metrics"]["funding_pnl"], 0)
        self.assertGreater(result["metrics"]["fees_paid"], 0)
        self.assertGreater(result["metrics"]["adverse_fill_cost"], 0)
        self.assertGreaterEqual(min(r["available_cash"] for r in result["native_equity_curve"]), 0)
        self.assertTrue(all(r["worst_equity"] <= r["equity"] <= r["best_equity"] for r in result["equity_curve"]))

    def test_physical_caps_share_one_account(self):
        result = self.run_trade(observations=manual_signals(self.features, both=True), variant={**engine.grid()[0], "risk_fraction": .1})
        trades = result["trades"]
        self.assertEqual(len(trades), 2)
        self.assertLessEqual(sum(t["margin"]+t["entry_fee"] for t in trades), 100000)
        self.assertTrue(all(t["quantity"]*t["entry_price"] <= 100000 for t in trades))
        self.assertLessEqual(sum(t["quantity"]*t["entry_price"] for t in trades), 200000)

    def test_stop_budget_and_signal_known_before_entry(self):
        trade = self.run_trade()["trades"][0]
        self.assertLessEqual(trade["risk_at_stop_before_costs"], trade["risk_budget"])
        self.assertLess(trade["signal_time"], trade["entry_time"])
        self.assertLessEqual(trade["signal_known_at"], trade["entry_time"])
        self.assertLessEqual(trade["atr_known_at"], trade["entry_time"])
        self.assertTrue(trade["exit_time"].endswith("T00:00:00Z"))
        self.assertEqual(trade["exit_timing"], "close")

    def test_incomplete_daily_atr_never_changes_sizing(self):
        altered = copy.deepcopy(self.data)
        altered["BTCUSDT"][19*288+144]["high"] = 130
        features = engine.NativeFeatures(altered)
        before, after = self.run_trade(), self.run_trade(features=features)
        self.assertEqual(before["trades"][0]["quantity"], after["trades"][0]["quantity"])
        self.assertEqual(before["trades"][0]["stop_price"], after["trades"][0]["stop_price"])

    def test_same_native_bar_stop_prioritized_over_target(self):
        changed = copy.deepcopy(self.data)
        changed["BTCUSDT"][19*288].update(high=103, low=98)
        features = engine.NativeFeatures(changed)
        variant = {**engine.grid()[0], "target_r": 2}
        result = self.run_trade(features=features, variant=variant)
        self.assertEqual(result["trades"][0]["reason"], "native_stop")
        self.assertLess(result["trades"][0]["pnl"], 0)

    def test_open_stop_fills_gap_price(self):
        changed = copy.deepcopy(self.data)
        changed["BTCUSDT"][19*288+1].update(open=98, high=98.1, low=97.9, close=98)
        features = engine.NativeFeatures(changed)
        trade = self.run_trade(features=features)["trades"][0]
        self.assertEqual(trade["reason"], "gap_stop")
        self.assertEqual(trade["exit_raw_price"], 98)

    def test_long_and_short_funding_payments_have_correct_sign(self):
        events = {"BTCUSDT": [funding_event(self.features, 19*288+12, milliseconds=2)], "ETHUSDT": []}
        long = self.run_trade(events=events)
        short = self.run_trade(observations=manual_signals(self.features, side=-1), events=events)
        self.assertLess(long["metrics"]["funding_pnl"], 0)
        self.assertGreater(short["metrics"]["funding_pnl"], 0)
        self.assertTrue(short["funding_ledger"][0]["time"].endswith(".002000Z"))

    def test_new_entry_cannot_capture_settlement2ms_after_open(self):
        events = {"BTCUSDT": [funding_event(self.features, 19*288, rate=-1, milliseconds=2)], "ETHUSDT": []}
        self.assertEqual(self.run_trade(events=events)["funding_ledger"], [])

    def test_open_exit_precedes_future_settlement(self):
        events = {"BTCUSDT": [funding_event(self.features, 19*288+12, milliseconds=2)], "ETHUSDT": []}
        result = self.run_trade(observations=manual_signals(self.features, exit_hour=1), events=events)
        self.assertEqual(result["trades"][0]["reason"], "prior_close_indicator_exit")
        self.assertEqual(result["funding_ledger"], [])

    def test_exact_old_position_settlement_precedes_open_exit(self):
        events = {"BTCUSDT": [funding_event(self.features, 19*288+12)], "ETHUSDT": []}
        result = self.run_trade(observations=manual_signals(self.features, exit_hour=1), events=events)
        self.assertEqual(len(result["funding_ledger"]), 1)

    def test_future_funding_never_finances_earlier_entry(self):
        events = {"BTCUSDT": [funding_event(self.features, 19*288+12, rate=-1, milliseconds=2)], "ETHUSDT": []}
        before, after = self.run_trade(), self.run_trade(events=events)
        self.assertEqual(before["trades"][0]["quantity"], after["trades"][0]["quantity"])

    def test_positive_funding_cannot_rescue_gap_liquidation(self):
        changed = copy.deepcopy(self.data)
        changed["BTCUSDT"][19*288+12].update(open=40, high=40.1, low=39.9, close=40)
        features = engine.NativeFeatures(changed)
        events = {"BTCUSDT": [funding_event(features, 19*288+12, rate=-2)], "ETHUSDT": []}
        result = self.run_trade(features=features, events=events)
        self.assertEqual(result["metrics"]["liquidation_count"], 1)
        self.assertEqual(result["funding_ledger"], [])
        self.assertGreater(result["metrics"]["unfunded_isolated_deficit"], 0)

    def test_possible_intrabar_liquidation_suppresses_positive_funding(self):
        changed = copy.deepcopy(self.data)
        changed["BTCUSDT"][19*288+12]["low"] = 40
        features = engine.NativeFeatures(changed)
        events = {"BTCUSDT": [funding_event(features, 19*288+12, rate=-2, milliseconds=2)], "ETHUSDT": []}
        result = self.run_trade(features=features, events=events)
        self.assertEqual(result["metrics"]["liquidation_count"], 1)
        self.assertEqual(result["funding_ledger"][0]["pnl"], 0)
        self.assertTrue(result["funding_ledger"][0]["intrabar_entitlement_ambiguous"])

    def test_possible_stop_suppresses_receipt_but_keeps_adverse_payment(self):
        changed = copy.deepcopy(self.data)
        changed["BTCUSDT"][19*288+12]["low"] = 98
        features = engine.NativeFeatures(changed)
        receive = {"BTCUSDT": [funding_event(features, 19*288+12, rate=-.01, milliseconds=2)], "ETHUSDT": []}
        pay = {"BTCUSDT": [funding_event(features, 19*288+12, rate=.01, milliseconds=2)], "ETHUSDT": []}
        self.assertEqual(self.run_trade(features=features, events=receive)["funding_ledger"][0]["pnl"], 0)
        self.assertLess(self.run_trade(features=features, events=pay)["funding_ledger"][0]["pnl"], 0)

    def test_flat_price_cost_decomposition_and_stress(self):
        before, stressed = self.run_trade(), self.run_trade(cost_multiplier=2)
        m = before["metrics"]
        self.assertAlmostEqual(m["final_equity"]-100000+m["fees_paid"]+m["adverse_fill_cost"]-m["funding_pnl"], 0, places=7)
        self.assertLess(stressed["metrics"]["return_pct"], m["return_pct"])

    def test_zero_volume_bar_cannot_fill_entry(self):
        changed = copy.deepcopy(self.data)
        changed["BTCUSDT"][19*288]["volume"] = 0
        features = engine.NativeFeatures(changed)
        result = self.run_trade(features=features)
        self.assertEqual(result["trades"], [])
        self.assertEqual(result["metrics"]["skipped_zero_volume_entry_count"], 1)

    def test_zero_volume_held_exposure_is_unresolved(self):
        changed = copy.deepcopy(self.data)
        changed["BTCUSDT"][19*288+12].update(volume=0, low=98)
        features = engine.NativeFeatures(changed)
        result = self.run_trade(features=features)
        self.assertEqual(result["trades"][0]["reason"], "sample_boundary")
        self.assertEqual(result["metrics"]["unresolved_zero_volume_exposure_bars"], 1)

    def test_exact_boundary_funding_tie_keeps_debit_omits_credit(self):
        pay = {"BTCUSDT": [funding_event(self.features, 21*288, rate=.01)], "ETHUSDT": []}
        receive = {"BTCUSDT": [funding_event(self.features, 21*288, rate=-.01)], "ETHUSDT": []}
        a, b = self.run_trade(events=pay), self.run_trade(events=receive)
        self.assertLess(a["funding_ledger"][0]["pnl"], 0)
        self.assertEqual(b["funding_ledger"][0]["pnl"], 0)
        self.assertTrue(a["funding_ledger"][0]["sample_boundary_entitlement_tie"])

    def test_boundary_exit_precedes_later2ms_settlement(self):
        events = {"BTCUSDT": [funding_event(self.features, 21*288, rate=.01, milliseconds=2)], "ETHUSDT": []}
        self.assertEqual(self.run_trade(events=events)["funding_ledger"], [])

    def test_stress_liquidation_debt_and_unresolved_execution_fail_eligibility(self):
        curve, returns = [], []
        capital = 100000.0
        for i in range(62):
            date = (datetime(2024, 1, 1)+timedelta(days=i)).date().isoformat()
            capital *= 1.001
            curve.append({"time": date+"T23:55:00Z", "equity": capital,
                          "worst_equity": capital, "best_equity": capital})
            returns.append({"date": date, "return": .001})
        base = {"equity_curve": curve, "daily_returns": returns,
                "metrics": {"trade_count": 30, "liquidation_count": 0,
                            "unfunded_isolated_deficit": 0, "unresolved_zero_volume_exposure_bars": 0}}
        self.assertTrue(driver.evaluate(base, base, ["2024-01-01", "2024-03-03"], "training", 1)["passed"])
        for field, guard in (("liquidation_count", "no_proxy_liquidation_base_and_stress"),
                             ("unfunded_isolated_deficit", "no_unfunded_deficit_base_and_stress"),
                             ("unresolved_zero_volume_exposure_bars", "no_unresolved_zero_volume_exposure_base_and_stress")):
            stress = copy.deepcopy(base)
            stress["metrics"][field] = 1
            assessed = driver.evaluate(base, stress, ["2024-01-01", "2024-03-03"], "training", 1)
            self.assertFalse(assessed["checks"][guard])
            self.assertFalse(assessed["passed"])
            self.assertEqual(assessed["status"], "not_qualified")

    def test_insolvent_daily_account_is_rejected_without_inference(self):
        result = self.run_trade()
        result["equity_curve"][0]["equity"] = 0
        assessed = driver.evaluate(result, result, ["2024-01-20", "2024-01-22"], "training", 1)
        self.assertFalse(assessed["passed"])
        self.assertIsNone(assessed["daily_mean_ci99"])
        self.assertIsNone(assessed["base"]["geometric_monthly_return"])


if __name__ == "__main__":
    unittest.main()
