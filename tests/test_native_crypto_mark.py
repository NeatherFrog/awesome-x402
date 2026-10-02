import copy
from datetime import datetime, timedelta
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from propdesk import native_crypto_mark as engine, native_crypto_trend as parent
from scripts import research_native_crypto_mark as driver
from tests.test_native_crypto_trend import fixture, manual_signals, funding_event


def mark_fixture(trades):
    return {s: [{**{k: row[k] for k in ("time", "open", "high", "low", "close")},
                 "known_at": (datetime.fromisoformat(row["time"].replace("Z", "+00:00"))+timedelta(minutes=5)).isoformat().replace("+00:00", "Z"),
                 "source_auxiliary_count": 300, "price_kind": "computed_mark"} for row in rows] for s, rows in trades.items()}


class MarkInterpreterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = fixture()
        cls.mark_data = mark_fixture(cls.data)
        cls.features = engine.MarkFeatures(cls.data, cls.mark_data)

    def run_trade(self, features=None, observations=None, events=None, variant=None, **kwargs):
        features = features or self.features
        return engine.simulate(features, observations or manual_signals(features),
                               engine.prepare_funding(features, events or {s: [] for s in engine.SYMBOLS}),
                               variant or engine.grid()[0], "2024-01-20", "2024-01-22", keep_native_curve=True, **kwargs)

    def test_same96_alpha_grid_and_observations(self):
        self.assertIs(engine.grid, parent.grid)
        before = parent.NativeFeatures(self.data)
        for variant in engine.grid():
            self.assertEqual(self.features.observations(variant), before.observations(variant))

    def test_mark_is_computed_price_not_execution_volume(self):
        altered = copy.deepcopy(self.mark_data)
        altered["BTCUSDT"][0]["price_kind"] = "spot"
        with self.assertRaisesRegex(ValueError, "Computed mark"):
            engine.MarkFeatures(self.data, altered)

    def test_incomplete_mark_cannot_be_known_early(self):
        altered = copy.deepcopy(self.mark_data)
        altered["BTCUSDT"][0]["known_at"] = altered["BTCUSDT"][0]["time"]
        with self.assertRaisesRegex(ValueError, "known-at"):
            engine.MarkFeatures(self.data, altered)

    def test_missing_mark_cannot_be_substituted(self):
        altered = copy.deepcopy(self.mark_data)
        del altered["BTCUSDT"][100]
        with self.assertRaisesRegex(ValueError, "Missing mark"):
            engine.MarkFeatures(self.data, altered)

    def test_fill_and_cash_accounting_use_trade_prices(self):
        altered = copy.deepcopy(self.mark_data)
        for row in altered["BTCUSDT"][19*288:21*288]:
            row.update(open=100.2, high=100.3, low=100.1, close=100.2)
        features = engine.MarkFeatures(self.data, altered)
        result = self.run_trade(features=features)
        trade = result["trades"][0]
        self.assertEqual(trade["entry_raw_price"], 100)
        self.assertEqual(trade["exit_raw_price"], 100)
        self.assertAlmostEqual(result["metrics"]["final_equity"], 100000+sum(t["pnl"] for t in result["trades"]), places=7)
        self.assertGreater(result["native_equity_curve"][10]["equity"], 100000)
        self.assertLess(result["metrics"]["final_equity"], 100000)

    def test_closed_mark_stop_uses_later_trade_open(self):
        trades, marks = copy.deepcopy(self.data), copy.deepcopy(self.mark_data)
        marks["BTCUSDT"][19*288]["low"] = 98
        trades["BTCUSDT"][19*288+1].update(open=99, high=99.1, low=98.9, close=99)
        features = engine.MarkFeatures(trades, marks)
        trade = self.run_trade(features=features)["trades"][0]
        self.assertEqual(trade["reason"], "completed_mark_stop")
        self.assertEqual(trade["pending_known_at"], features.times[19*288+1])
        self.assertEqual(trade["exit_time"], features.times[19*288+1])
        self.assertEqual(trade["exit_raw_price"], 99)
        self.assertNotEqual(trade["exit_raw_price"], trade["stop_price"])

    def test_halt_stop_latches_until_first_genuine_trade_open(self):
        trades, marks = copy.deepcopy(self.data), copy.deepcopy(self.mark_data)
        for i in range(19*288+1, 19*288+4):
            trades["BTCUSDT"][i]["volume"] = 0
        marks["BTCUSDT"][19*288+1]["low"] = 98
        trades["BTCUSDT"][19*288+4].update(open=97, high=97.1, low=96.9, close=97)
        features = engine.MarkFeatures(trades, marks)
        result = self.run_trade(features=features)
        trade = result["trades"][0]
        self.assertEqual(trade["exit_time"], features.times[19*288+4])
        self.assertEqual(trade["exit_raw_price"], 97)
        self.assertTrue(trade["reopening_execution_time_unknown"])
        self.assertEqual(result["metrics"]["reopening_execution_time_unknown_count"], 1)
        self.assertEqual(result["metrics"]["zero_volume_held_bars_with_authentic_marks"], 3)

    def test_no_entry_fill_during_zero_trade_volume(self):
        altered = copy.deepcopy(self.data)
        altered["BTCUSDT"][19*288]["volume"] = 0
        features = engine.MarkFeatures(altered, self.mark_data)
        result = self.run_trade(features=features)
        self.assertEqual(result["trades"], [])
        self.assertEqual(result["metrics"]["skipped_zero_volume_entry_count"], 1)

    def test_real_marks_resolve_passive_halt_floating_exposure(self):
        altered = copy.deepcopy(self.data)
        altered["BTCUSDT"][19*288+2]["volume"] = 0
        features = engine.MarkFeatures(altered, self.mark_data)
        result = self.run_trade(features=features)
        self.assertEqual(result["metrics"]["zero_volume_held_bars_with_authentic_marks"], 1)
        self.assertEqual(result["metrics"]["unresolved_zero_volume_exposure_bars"], 0)
        self.assertEqual(result["metrics"]["reopening_execution_time_unknown_count"], 0)
        self.assertTrue(result["metrics"]["historical_mark_prices_available"])

    def test_same_interval_mark_stop_precedes_trade_target(self):
        trades, marks = copy.deepcopy(self.data), copy.deepcopy(self.mark_data)
        trades["BTCUSDT"][19*288]["high"] = 103
        marks["BTCUSDT"][19*288]["low"] = 98
        features = engine.MarkFeatures(trades, marks)
        result = self.run_trade(features=features, variant={**engine.grid()[0], "target_r": 2})
        self.assertEqual(result["trades"][0]["reason"], "completed_mark_stop")

    def test_mark_liquidation_latched_and_not_rescued_by_credit(self):
        altered = copy.deepcopy(self.mark_data)
        altered["BTCUSDT"][19*288+12]["low"] = 40
        features = engine.MarkFeatures(self.data, altered)
        events = {"BTCUSDT": [funding_event(features, 19*288+12, rate=-2, milliseconds=2)], "ETHUSDT": []}
        result = self.run_trade(features=features, events=events)
        self.assertEqual(result["metrics"]["liquidation_count"], 1)
        self.assertEqual(result["funding_ledger"][0]["pnl"], 0)
        self.assertEqual(result["trades"][0]["exit_time"], features.times[19*288+13])
        self.assertGreater(result["metrics"]["unfunded_isolated_deficit"], 0)

    def test_exactT_credit_is_omitted_debit_retained_before_orders(self):
        receive = {"BTCUSDT": [funding_event(self.features, 19*288+12, rate=-.01)], "ETHUSDT": []}
        pay = {"BTCUSDT": [funding_event(self.features, 19*288+12, rate=.01)], "ETHUSDT": []}
        a, b = self.run_trade(events=receive), self.run_trade(events=pay)
        self.assertEqual(a["funding_ledger"][0]["pnl"], 0)
        self.assertLess(b["funding_ledger"][0]["pnl"], 0)
        self.assertEqual(b["funding_ledger"][0]["mark_proxy"], "prior_completed_mark")

    def test_later2ms_settlement_does_not_size_prior_orders(self):
        events = {"BTCUSDT": [funding_event(self.features, 19*288, rate=-2, milliseconds=2)], "ETHUSDT": []}
        self.assertEqual(self.run_trade(events=events)["funding_ledger"], [])

    def test_reopening_possible_late_debit_retained_and_never_finances_orders(self):
        trades, marks = copy.deepcopy(self.data), copy.deepcopy(self.mark_data)
        trades["BTCUSDT"][19*288+11]["volume"] = 0
        marks["BTCUSDT"][19*288+11]["low"] = 98
        features = engine.MarkFeatures(trades, marks)
        observations = manual_signals(features)
        observations["ETHUSDT"]["entry"][19*24] = 1
        pay = {"BTCUSDT": [funding_event(features, 19*288+12, rate=.01, milliseconds=2)], "ETHUSDT": []}
        a, b = self.run_trade(features=features, observations=observations), self.run_trade(features=features, observations=observations, events=pay)
        first = lambda r: next(t for t in r["trades"] if t["symbol"] == "ETHUSDT")
        self.assertEqual(first(a)["quantity"], first(b)["quantity"])
        self.assertLess(b["metrics"]["funding_pnl"], 0)
        self.assertTrue(b["funding_ledger"][0]["reopening_execution_time_unknown"])
        self.assertAlmostEqual(b["metrics"]["final_equity"], 100000+sum(t["pnl"] for t in b["trades"]), places=7)

    def test_terminal_unfilled_stop_remains_open_not_fabricated_exit(self):
        trades, marks = copy.deepcopy(self.data), copy.deepcopy(self.mark_data)
        trades["BTCUSDT"][21*288-1]["volume"] = 0
        marks["BTCUSDT"][21*288-1]["low"] = 98
        features = engine.MarkFeatures(trades, marks)
        result = self.run_trade(features=features)
        self.assertEqual(result["trades"], [])
        self.assertEqual(result["metrics"]["terminal_open_positions"], 1)
        self.assertEqual(result["metrics"]["terminal_pending_orders"], 1)

    def test_current_mark_high_low_close_never_affects_earlier_entry(self):
        altered = copy.deepcopy(self.mark_data)
        altered["BTCUSDT"][19*288].update(high=110, low=98, close=109)
        features = engine.MarkFeatures(self.data, altered)
        a, b = self.run_trade(), self.run_trade(features=features)
        self.assertEqual(a["trades"][0]["quantity"], b["trades"][0]["quantity"])
        self.assertEqual(a["trades"][0]["risk_budget"], b["trades"][0]["risk_budget"])

    def test_opening_mark_gap_liquidation_outranks_old_native_indicator_exit(self):
        altered = copy.deepcopy(self.mark_data)
        i = 19*288+12
        altered["BTCUSDT"][i].update(open=40, high=40.1, low=39.9, close=40)
        features = engine.MarkFeatures(self.data, altered)
        signals = manual_signals(features, exit_hour=1)
        events = {"BTCUSDT": [funding_event(features, i, rate=-1)], "ETHUSDT": []}
        result = self.run_trade(features=features, observations=signals, events=events)
        trade = result["trades"][0]
        self.assertEqual(trade["reason"], "opening_mark_liquidation_ambiguity")
        self.assertEqual(trade["exit_raw_price"], 100)
        self.assertEqual(trade["recovered_margin"], 0)
        self.assertTrue(trade["liquidation_proxy"])
        self.assertIsNone(trade["pending_known_at"])
        self.assertEqual(trade["opening_mark_observation_known_at"], features.times[i+1])
        self.assertTrue(trade["simultaneous_opening_mark_order_ordering_unverified"])
        self.assertGreater(trade["unfunded_isolated_deficit"], 0)
        self.assertEqual(result["metrics"]["opening_mark_gap_liquidation_ambiguity_count"], 1)
        self.assertFalse(driver.execution_guards(result)["no_mark_liquidation_or_unfunded_debt"])
        self.assertAlmostEqual(result["metrics"]["final_equity"], 100000+sum(t["pnl"] for t in result["trades"]), places=7)

    def test_current_opening_mark_gap_cannot_resize_first_entry(self):
        altered = copy.deepcopy(self.mark_data)
        altered["BTCUSDT"][19*288].update(open=40, high=40.1, low=39.9, close=40)
        features = engine.MarkFeatures(self.data, altered)
        a, b = self.run_trade(), self.run_trade(features=features)
        self.assertEqual(a["trades"][0]["quantity"], b["trades"][0]["quantity"])
        self.assertEqual(a["trades"][0]["risk_budget"], b["trades"][0]["risk_budget"])
        self.assertEqual(b["metrics"]["opening_mark_gap_liquidation_ambiguity_count"], 0)
        self.assertGreater(b["metrics"]["liquidation_count"], 0)

    def test_future_zero_btc_volume_cannot_enlarge_same_bar_eth_intent(self):
        altered = copy.deepcopy(self.data)
        altered["BTCUSDT"][19*288]["volume"] = 0
        features = engine.MarkFeatures(altered, self.mark_data)
        variant = {**engine.grid()[0], "risk_fraction": .01}
        a = self.run_trade(observations=manual_signals(self.features, both=True), variant=variant)
        b = self.run_trade(features=features, observations=manual_signals(features, both=True), variant=variant)
        eth = lambda r: next(t for t in r["trades"] if t["symbol"] == "ETHUSDT")
        self.assertEqual(eth(a)["quantity"], eth(b)["quantity"])
        self.assertEqual(eth(a)["margin"], eth(b)["margin"])

    def test_sparse_marks_preserved_economics_but_flag_risk_evidence(self):
        altered = copy.deepcopy(self.mark_data)
        altered["BTCUSDT"][19*288+2]["source_auxiliary_count"] = 1
        features = engine.MarkFeatures(self.data, altered)
        a, b = self.run_trade(), self.run_trade(features=features)
        self.assertEqual(a["trades"], b["trades"])
        self.assertEqual(a["metrics"]["final_equity"], b["metrics"]["final_equity"])
        self.assertEqual(b["metrics"]["source_sparse_mark_held_bar_count"], 1)

    def test_passive_halt_then_new_indicator_exit_keeps_possible_late_debit(self):
        trades = copy.deepcopy(self.data)
        trades["BTCUSDT"][19*288+11]["volume"] = 0
        features = engine.MarkFeatures(trades, self.mark_data)
        signals = manual_signals(features, exit_hour=1)
        events = {"BTCUSDT": [funding_event(features, 19*288+12, rate=.01, milliseconds=2)], "ETHUSDT": []}
        result = self.run_trade(features=features, observations=signals, events=events)
        self.assertEqual(result["trades"][0]["reason"], "prior_close_indicator_exit")
        self.assertTrue(result["trades"][0]["reopening_execution_time_unknown"])
        self.assertEqual(result["metrics"]["reopening_execution_time_unknown_count"], 1)
        self.assertLess(result["metrics"]["funding_pnl"], 0)

    def test_preceding_sparse_mark_opening_intent_flagged_without_skipping_trade(self):
        altered = copy.deepcopy(self.mark_data)
        altered["BTCUSDT"][19*288-1]["source_auxiliary_count"] = 1
        features = engine.MarkFeatures(self.data, altered)
        a, b = self.run_trade(), self.run_trade(features=features)
        self.assertEqual(a["trades"], b["trades"])
        self.assertEqual(b["metrics"]["source_sparse_mark_held_bar_count"], 0)
        self.assertEqual(b["metrics"]["source_sparse_mark_opening_intent_count"], 1)

    def test_unknown_sparse_terminal_execution_guards_fail_positive_baseline(self):
        capital, curve, returns = 100000.0, [], []
        for i in range(62):
            date = (datetime(2024, 1, 1)+timedelta(days=i)).date().isoformat()
            capital *= 1.001
            curve.append({"time": date+"T23:55:00Z", "equity": capital, "worst_equity": capital, "best_equity": capital})
            returns.append({"date": date, "return": .001})
        base = {"equity_curve": curve, "daily_returns": returns,
                "trades": [{"pnl": (capital-100000)/30} for _ in range(30)], "metrics":
                {"trade_count": 30, "liquidation_count": 0, "unfunded_isolated_deficit": 0,
                 "initial_equity": 100000, "final_equity": capital, "minimum_available_cash": 0,
                 "unresolved_zero_volume_exposure_bars": 0, "historical_mark_prices_available": True,
                 "terminal_open_positions": 0, "terminal_pending_orders": 0,
                 "reopening_execution_time_unknown_count": 0, "source_sparse_mark_held_bar_count": 0,
                 "source_sparse_mark_opening_intent_count": 0}}
        self.assertTrue(driver.evaluate(base, base, ["2024-01-01", "2024-03-03"], "training", 1)["passed"])
        for field in ("terminal_open_positions", "terminal_pending_orders", "reopening_execution_time_unknown_count",
                      "source_sparse_mark_held_bar_count", "source_sparse_mark_opening_intent_count"):
            stress = copy.deepcopy(base)
            stress["metrics"][field] = 1
            assessed = driver.evaluate(base, stress, ["2024-01-01", "2024-03-03"], "training", 1)
            self.assertFalse(assessed["passed"])
            self.assertEqual(assessed["status"], "not_qualified")
        for corrupted in ("cash", "reconciliation"):
            stress = copy.deepcopy(base)
            if corrupted == "cash":
                stress["metrics"]["minimum_available_cash"] = -1
            else:
                stress["trades"][0]["pnl"] += 1
            assessed = driver.evaluate(base, stress, ["2024-01-01", "2024-03-03"], "training", 1)
            self.assertFalse(assessed["passed"])
            self.assertEqual(assessed["status"], "not_qualified")

    def test_actual_validation_artifact_mutation_blocks_final_even_if_report_unchanged(self):
        evidence={"selected":"fixture-primary","protocol_sha256":"fixture-protocol","base":{},"double_cost":{}}
        record={"target":{"passed":True},"full_evidence_sha256":driver.lab.digest(evidence)}
        report={"protocol_sha256":"fixture-protocol","selection_lock_sha256":"fixture-lock","validation":record}
        confirmation={"selected":"fixture-primary","selection_lock_sha256":"fixture-lock",
                      "validation_result_sha256":driver.lab.digest(record),"validation_passed":True,
                      "protocol_sha256":"fixture-protocol"}
        with tempfile.TemporaryDirectory() as temporary, patch.object(driver,"DIRECTORY",Path(temporary)):
            values={"validation-confirmation.json":confirmation,"validation_result.json":record,"validation_evidence.json":evidence}
            for name,value in values.items():
                (driver.DIRECTORY/name).write_text(json.dumps(value))
            driver.verify_validation_artifacts(report,"fixture-primary")
            for name in ("validation_result.json","validation_evidence.json"):
                changed={**values[name],"unregistered_mutation":True}
                (driver.DIRECTORY/name).write_text(json.dumps(changed))
                with self.assertRaises(ValueError):
                    driver.verify_validation_artifacts(report,"fixture-primary")
                (driver.DIRECTORY/name).write_text(json.dumps(values[name]))


if __name__ == "__main__":
    unittest.main()
