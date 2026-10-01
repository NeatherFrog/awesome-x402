"""Behavioral tests for chronology, execution, costs and evidence provenance."""

import copy
import json
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from propdesk import backtest, market, strategies


def bars_from(prices):
    stamp = datetime(2025, 1, 1, tzinfo=timezone.utc)
    return [{"time": (stamp + timedelta(hours=index)).isoformat().replace("+00:00", "Z"), "open": float(values[0]), "high": float(values[1]), "low": float(values[2]), "close": float(values[3]), "volume": 1000.0} for index, values in enumerate(prices)]


def settings(**overrides):
    return backtest.normalize_config({"account_size": 10000, "risk_pct": 1, "fee_bps": 0, "slippage_bps": 0, "spread_bps": 0, **overrides})


PARAMS = {"stop_atr": 1, "reward_risk": 2, "max_hold_bars": 20}


def signal(atr=2, direction=1):
    return {"direction": direction, "atr": atr, "regime": "trend"}


class IngestionTests(unittest.TestCase):
    def test_demo_is_deterministic_valid_and_distinct_for_seed_and_symbol(self):
        for symbol in market.SYMBOL_SPECS:
            with self.subTest(symbol=symbol):
                bars = market.demo_bars(symbol, 1200, 42)
                self.assertEqual(bars, market.demo_bars(symbol, 1200, 42))
                self.assertEqual(len(bars), 1200)
                self.assertEqual(market.validate_bars(bars), bars)
                self.assertNotEqual(bars, market.demo_bars(symbol, 1200, 43))
        self.assertNotEqual(market.demo_bars("EURUSD"), market.demo_bars("BTCUSD"))

    def test_csv_roundtrip_bom_header_whitespace_and_timestamp_alias(self):
        bars = market.demo_bars("XAUUSD", 30)
        exported = market.to_csv(bars)
        self.assertEqual(market.parse_csv(exported), bars)
        self.assertEqual(market.parse_csv("\ufeff" + exported.replace("time,", " Timestamp ,", 1)), bars)

    def test_csv_rejects_incomplete_header_row_width_and_empty_rows(self):
        invalid = ["", "time,open,high,low,close\n2025-01-01T00:00:00Z,1,2,1,1\n", "time,open,high,low,close,volume\n2025-01-01T00:00:00Z,1,2,1,1\n", "time,open,high,low,close,volume\n2025-01-01T00:00:00Z,1,2,1,1,0,extra\n", "time,timestamp,open,high,low,close,volume\n"]
        for text in invalid:
            with self.subTest(text=text), self.assertRaises(ValueError):
                market.parse_csv(text)

    def test_utc_timestamp_is_explicit_and_order_is_not_silently_repaired(self):
        bars = bars_from([(100, 101, 99, 100)] * 2)
        for invalid in ("2025-01-01", "2025-01-01T00:00:00", "2025-01-01T00:00:00+01:00", "2025-13-01T00:00:00Z", "2025-01-01 00:00:00Z"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                market.validate_bars([{**bars[0], "time": invalid}])
        with self.assertRaisesRegex(ValueError, "ascending and unique"):
            market.validate_bars(list(reversed(bars)))
        with self.assertRaisesRegex(ValueError, "ascending and unique"):
            market.validate_bars([bars[0], {**bars[0], "time": bars[0]["time"].replace("Z", "+00:00")}])

    def test_prices_envelope_finiteness_volume_boolean_and_limit(self):
        bar = bars_from([(100, 101, 99, 100)])[0]
        for override in ({"open": 0}, {"close": -1}, {"high": 90}, {"low": 110}, {"volume": -1}, {"open": float("nan")}, {"high": "inf"}, {"close": True}):
            with self.subTest(override=override), self.assertRaises(ValueError):
                market.validate_bars([{**bar, **override}])
        with self.assertRaisesRegex(ValueError, "at most"):
            market.validate_bars([bar] * (market.MAX_BARS + 1))


class ExecutionTests(unittest.TestCase):
    def test_signal_executes_next_open_and_never_signal_close(self):
        bars = bars_from([(90, 96, 89, 95), (101, 102, 100, 101), (101, 102, 100, 101), (101, 102, 100, 101)])
        result = backtest.simulate(bars, [signal(), None, None, None], PARAMS, settings())
        trade = result["trades"][0]
        self.assertEqual(trade["entry_time"], bars[1]["time"])
        self.assertEqual(trade["signal_time"], bars[0]["time"])
        self.assertEqual(trade["entry_price"], 101)
        self.assertEqual(trade["exit_reason"], "end_of_sample")

    def test_no_entry_on_final_bar_and_no_using_its_close(self):
        bars = bars_from([(100, 101, 99, 100)] * 4)
        result = backtest.simulate(bars, [None, None, signal(), signal()], PARAMS, settings())
        self.assertEqual(result["trades"], [])
        self.assertEqual(len(result["equity_curve"]), len(bars))

    def test_both_stop_and_target_hit_loses_for_long_and_short(self):
        for direction in (1, -1):
            with self.subTest(direction=direction):
                bars = bars_from([(100, 101, 99, 100), (100, 106, 94, 100), (100, 101, 99, 100)])
                result = backtest.simulate(bars, [signal(direction=direction), None, None], PARAMS, settings())
                trade = result["trades"][0]
                self.assertEqual(trade["exit_reason"], "stop_first_collision")
                self.assertEqual(trade["exit_price"], 98 if direction == 1 else 102)
                self.assertEqual(trade["pnl"], -100)
                self.assertEqual(trade["return_r"], -1)
                self.assertEqual(result["metrics"]["max_drawdown_pct"], 1)
                self.assertEqual(result["equity_curve"][1]["best_equity"], 10200)

    def test_stop_gap_uses_worse_open_and_does_not_charge_postexit_extreme(self):
        bars = bars_from([(100, 101, 99, 100), (100, 101, 99, 100), (95, 96, 90, 94), (94, 95, 93, 94)])
        result = backtest.simulate(bars, [signal(), None, None, None], PARAMS, settings())
        trade = result["trades"][0]
        self.assertEqual(trade["exit_reason"], "gap_stop")
        self.assertEqual(trade["exit_price"], 95)
        self.assertEqual(trade["return_r"], -2.5)
        self.assertEqual(result["equity_curve"][2]["worst_equity"], 9750)

    def test_favorable_gap_does_not_grant_optimistic_improvement(self):
        bars = bars_from([(100, 101, 99, 100), (100, 101, 99, 100), (110, 112, 109, 111), (111, 112, 110, 111)])
        result = backtest.simulate(bars, [signal(), None, None, None], PARAMS, settings())
        self.assertEqual(result["trades"][0]["exit_reason"], "gap_target")
        self.assertEqual(result["trades"][0]["exit_price"], 104)

    def test_costs_apply_each_side_and_reconcile_net_cash(self):
        bars = bars_from([(100, 100.2, 99.8, 100)] * 4)
        result = backtest.simulate(bars, [signal(3), None, None, None], PARAMS, settings(fee_bps=1, slippage_bps=2, spread_bps=2))
        trade = result["trades"][0]
        self.assertGreater(trade["entry_price"], 100)
        self.assertLess(trade["exit_price"], 100)
        self.assertGreater(trade["fees"], 0)
        self.assertGreater(trade["slippage"], 0)
        self.assertGreater(trade["spread"], 0)
        self.assertAlmostEqual(trade["pnl"], trade["gross_pnl"] - trade["total_costs"], places=5)
        self.assertAlmostEqual(result["metrics"]["final_equity"], 10000 + trade["pnl"], places=5)

    def test_unrealized_adverse_bar_mark_contributes_drawdown(self):
        bars = bars_from([(100, 101, 99, 100), (100, 101, 91, 100), (100, 101, 99, 100), (100, 101, 99, 100)])
        result = backtest.simulate(bars, [signal(10), None, None, None], PARAMS, settings())
        self.assertEqual(result["metrics"]["net_profit"], 0)
        self.assertEqual(result["metrics"]["max_drawdown_pct"], 0.9)
        self.assertEqual(result["equity_curve"][1]["equity"], 10000)
        self.assertEqual(result["equity_curve"][1]["worst_equity"], 9910)
        self.assertEqual(result["equity_curve"][1]["balance"], 10000)

    def test_leverage_cap_and_contract_multiplier_control_notional(self):
        bars = bars_from([(100, 100.5, 99.5, 100)] * 4)
        ordinary = backtest.simulate(bars, [signal(1), None, None, None], PARAMS, settings(risk_pct=5, max_leverage=1))
        contracts = backtest.simulate(bars, [signal(1), None, None, None], PARAMS, settings(risk_pct=5, max_leverage=1, contract_multiplier=10))
        a, b = ordinary["trades"][0], contracts["trades"][0]
        self.assertEqual(a["quantity"], 100)
        self.assertEqual(b["quantity"], 10)
        self.assertEqual(a["quantity"] * a["entry_price"], b["quantity"] * b["entry_price"] * b["contract_multiplier"])
        self.assertEqual(ordinary["metrics"], contracts["metrics"])

    def test_contract_step_can_prevent_entry_without_omitting_curve_bars(self):
        bars = bars_from([(100, 100.5, 99.5, 100)] * 4)
        result = backtest.simulate(bars, [signal(1), None, None, None], PARAMS, settings(max_leverage=0.5, contract_multiplier=100, quantity_step=1))
        self.assertEqual(result["trades"], [])
        self.assertEqual(len(result["equity_curve"]), len(bars))

    def test_gap_can_exceed_budget_and_insolvent_account_does_not_reenter(self):
        bars = bars_from([(100, 100.01, 99.99, 100), (100, 100.01, 99.99, 100), (1, 1.1, 0.9, 1), (1, 1.1, 0.9, 1), (1, 1.1, 0.9, 1)])
        result = backtest.simulate(bars, [signal(0.1), None, signal(0.1), None, None], PARAMS, settings(risk_pct=5, max_leverage=50))
        self.assertEqual(len(result["trades"]), 1)
        self.assertLess(result["metrics"]["final_equity"], 0)
        self.assertGreater(result["metrics"]["max_drawdown_pct"], 100)


class ResearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bars = market.demo_bars("EURUSD", 900, 42)

    def test_every_signal_is_prefix_invariant(self):
        for entry in strategies.catalog():
            for params in strategies.parameter_candidates(entry["id"]):
                with self.subTest(strategy=entry["id"], params=params):
                    full = strategies.signals_for(self.bars, entry["id"], params)
                    prefix = strategies.signals_for(self.bars[:260], entry["id"], params)
                    self.assertEqual(full[:260], prefix)

    def test_modifying_holdout_cannot_change_training_or_walkforward(self):
        config = {"source": "csv"}
        original = backtest.run_research(self.bars, config)
        changed = copy.deepcopy(self.bars)
        split = original["data"]["train_bars"]
        for index in range(split, len(changed)):
            scale = 1 + (index - split) * 0.02
            for key in ("open", "high", "low", "close"):
                changed[index][key] *= scale
        modified = backtest.run_research(changed, config)
        self.assertEqual(original["training_candidate"], modified["training_candidate"])
        self.assertNotEqual(original["data"]["hash"], modified["data"]["hash"])
        for before, after in zip(original["strategies"], modified["strategies"]):
            with self.subTest(strategy=before["id"]):
                self.assertEqual(before["params"], after["params"])
                self.assertEqual(before["train_metrics"], after["train_metrics"])
                self.assertEqual(before["walk_forward"], after["walk_forward"])

    def test_holdout_trades_and_walkforward_windows_have_separate_chronology(self):
        result = backtest.run_research(self.bars, {"source": "csv"})
        split = result["data"]["holdout_start"]
        for strategy in result["strategies"]:
            for trade in strategy["trades"]:
                self.assertGreaterEqual(trade["entry_time"], split)
                self.assertLess(trade["signal_time"], trade["entry_time"])
                self.assertTrue(trade["out_of_sample"])
                self.assertEqual(trade["split"], "oos")
                self.assertNotEqual(trade["entry_time"], self.bars[-1]["time"])
            for fold in strategy["walk_forward"]["folds"]:
                self.assertLess(fold["train_end"], fold["validation_start"])
                self.assertLess(fold["validation_end"], split)

    def test_demo_cannot_qualify_and_json_contains_no_nonfinite_numbers(self):
        result = backtest.run_research(self.bars, {"source": "demo"})
        self.assertIsNone(result["selected_strategy"])
        self.assertEqual(result["summary"]["status"], "demo")
        self.assertEqual(result["latest_signal"]["status"], "demo")
        self.assertFalse(result["latest_signal"]["actionable"])
        self.assertTrue(all(not strategy["eligible"] for strategy in result["strategies"]))
        self.assertIn("DEMO", result["summary"]["warnings"][0])
        json.dumps(result, allow_nan=False)

    def test_only_training_winner_can_be_selected_even_if_all_holdouts_pass(self):
        def evidence(_result, _walk_forward, _confidence, _config, baseline):
            return ["baseline"] if baseline else []

        with patch.object(backtest, "_evidence_reasons", side_effect=evidence):
            result = backtest.run_research(self.bars, {"source": "csv"})
        self.assertEqual(result["selected_strategy"], result["training_candidate"])
        selected = next(strategy for strategy in result["strategies"] if strategy["id"] == result["selected_strategy"])
        self.assertTrue(selected["training_winner"])

    def test_rules_are_checked_on_full_curve_before_chart_thinning(self):
        calls = []

        def replay(curve, _profile, trades=None):
            calls.append((len(curve), curve[0], trades))
            return {"status": "breach", "breaches": [{"type": "total"}], "reasons": ["test floor reached"]}

        def evidence(_result, _walk_forward, _confidence, _config, baseline):
            return ["baseline"] if baseline else []

        bars = market.demo_bars("NAS100", 1500)
        with patch.object(backtest, "_evidence_reasons", side_effect=evidence), patch("propdesk.compliance.evaluate", side_effect=replay):
            result = backtest.run_research(bars, {"source": "csv", "prop_profile": {"account_size": 100000}})
        self.assertTrue(all(call[0] == 600 for call in calls))
        self.assertTrue(all("balance" in call[1] and "best_equity" in call[1] for call in calls))
        self.assertTrue(all(len(strategy["equity_curve"]) <= 400 for strategy in result["strategies"]))
        self.assertTrue(all(not strategy["eligible"] for strategy in result["strategies"]))
        self.assertIsNone(result["selected_strategy"])
        self.assertEqual(result["summary"]["account_rule_status"], "breach")

    def test_baseline_only_is_reference_and_config_inputs_are_not_mutated(self):
        config = {"source": "csv", "strategy_ids": ["buy_hold"]}
        original = copy.deepcopy(config)
        result = backtest.run_research(self.bars, config)
        self.assertEqual(config, original)
        self.assertIsNone(result["training_candidate"])
        self.assertIsNone(result["selected_strategy"])
        self.assertTrue(result["strategies"][0]["baseline"])

    def test_invalid_config_and_short_data_fail_without_defaults_masking_errors(self):
        for config in ({"risk_pct": True}, {"risk_pct": "1"}, {"train_fraction": 0.95}, {"max_leverage": float("inf")}, {"strategy_ids": ["magic"]}, {"symbol": ""}, {"prop_profile": []}):
            with self.subTest(config=config), self.assertRaises(ValueError):
                backtest.run_research(self.bars, config)
        with self.assertRaisesRegex(ValueError, "at least"):
            backtest.run_research(self.bars[:100])

    def test_extreme_finite_prices_raise_validation_error_instead_of_nonfinite_json(self):
        bars = copy.deepcopy(self.bars)
        for bar in bars:
            for key in ("open", "high", "low", "close"):
                bar[key] *= 1e300
        with self.assertRaises(ValueError):
            backtest.run_research(bars, {"source": "csv"})


if __name__ == "__main__":
    unittest.main()
