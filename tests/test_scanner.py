"""Cross-market chronology and firm-model guards independent of the HTTP API."""

import copy
import json
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from propdesk import backtest, market, scanner


def datasets(count=900):
    return {symbol: {"bars": market.demo_bars("EURUSD", count, seed),
                     "provenance": {"source": "csv", "provider": "Unit-test fixture", "quote_currency": "USD"}}
            for symbol, seed in (("ALPHA", 42), ("BETA", 43), ("GAMMA", 44), ("DELTA", 45))}


def primary_fixture(count=35):
    trades = [{"return_r": 0.3, "net_r": 0.3, "mae_r": 0.2, "mfe_r": 0.5,
               "out_of_sample": True, "split": "oos", "entry_time": "2025-02-01T00:00:00Z",
               "exit_time": "2025-02-02T00:00:00Z"} for _ in range(count)]
    return {"strategy_id": "ema_pullback", "report": {"data": {"source": "csv", "holdout_start": "2025-01-01T00:00:00Z", "end": "2025-12-31T00:00:00Z"},
            "config": {"risk_pct": 0.25}, "strategies": [{"id": "ema_pullback", "trades": trades}]}}


def verified_profile(**changes):
    return {"id": "verified", "name": "User rules", "status": "user_verified", "verified_at": "2026-10-01",
            "source_url": "https://example.test/actual-rules", "account_size": 100000, "ea_allowed": True, **changes}


class ScannerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.datasets = datasets()

    def test_training_receives_only_prefix_and_lock_callback_precedes_every_holdout(self):
        prefixes, events = [], []
        real_fit = scanner.train_market
        real_research = backtest.run_research

        def fit(symbol, prefix, config):
            prefixes.append((symbol, len(prefix), prefix[-1]["time"]))
            return real_fit(symbol, prefix, config)

        def lock(event):
            events.append("lock")
            self.assertEqual(event["phase"], "training_locked")
            self.assertEqual(len(event["training_lock"]["candidates"]), 3)
            # The callback cannot mutate the actual lock held by the scanner.
            event["training_lock"]["candidates"].clear()

        def research(bars, config):
            self.assertIn("lock", events)
            events.append("holdout")
            return real_research(bars, config)

        with patch.object(scanner, "train_market", side_effect=fit), patch.object(backtest, "run_research", side_effect=research):
            result = scanner.scan(self.datasets, on_lock=lock)
        self.assertEqual(len(prefixes), 4)
        self.assertTrue(all(length == 540 for _, length, _ in prefixes))
        self.assertEqual(events, ["lock", "holdout", "holdout", "holdout"])
        self.assertEqual(len(result["training_lock"]["candidates"]), 3)
        self.assertTrue(result["planning_only"])
        self.assertFalse(result["live_orders"])
        json.dumps(result, allow_nan=False)

    def test_altered_holdouts_cannot_change_global_ranking_or_parameters(self):
        original = scanner.scan(self.datasets)
        changed = copy.deepcopy(self.datasets)
        for value in changed.values():
            for index, bar in enumerate(value["bars"]):
                if index >= 540:
                    scale = 1 + (index - 540) * 0.015
                    for key in ("open", "high", "low", "close"):
                        bar[key] *= scale
        modified = scanner.scan(changed)
        self.assertEqual(original["training_lock"], modified["training_lock"])
        self.assertEqual(original["training_lock_sha256"], modified["training_lock_sha256"])
        self.assertEqual(original["primary_symbol"], modified["primary_symbol"])

    def test_primary_failure_is_not_replaced_by_better_diagnostic_holdout(self):
        primary = []
        real_research = backtest.run_research

        def lock(event):
            primary.append(event["training_lock"]["primary_symbol"])

        def research(bars, config):
            result = real_research(bars, config)
            selected = next(item for item in result["strategies"] if item["id"] == result["training_candidate"])
            selected["eligible"] = config["symbol"] != primary[0]
            selected["reasons"] = [] if selected["eligible"] else ["Deliberate failed-primary fixture"]
            if selected["eligible"]:
                selected["test_metrics"]["net_return_pct"] = 100.0
            return result

        with patch.object(backtest, "run_research", side_effect=research), patch.object(scanner, "adjusted_confidence", return_value={"lower_above_zero": True}):
            result = scanner.scan(self.datasets, on_lock=lock)
        self.assertIsNone(result["selected_symbol"])
        self.assertIsNone(result["selected_profile_id"])
        self.assertFalse(result["markets"][0]["qualified"])
        self.assertTrue(result["markets"][1]["qualified"])
        self.assertTrue(all(item["report"]["selected_strategy"] is None for item in result["markets"]))
        self.assertTrue(all(item["report"]["summary"]["qualified_count"] == 0 for item in result["markets"]))

    def test_bounded_inputs_and_nonfinite_costs_fail_early(self):
        for value in ({}, {str(i): self.datasets["ALPHA"] for i in range(13)}, {"X": {"bars": self.datasets["ALPHA"]["bars"][:299]}}):
            with self.subTest(value_type=type(value)), self.assertRaises(ValueError):
                scanner.scan(value)
        for settings in ({"fee_bps": float("nan")}, {"risk_pct": True}, {"risk_pct": 2}, {"as_of": "2026-10-01"}):
            with self.subTest(settings=settings), self.assertRaises(ValueError):
                scanner.scan(self.datasets, settings)

    def test_currency_mismatch_is_excluded_without_fake_conversion(self):
        japanese = {"USDJPY": {"bars": self.datasets["ALPHA"]["bars"], "provenance": {"source": "csv", "quote_currency": "JPY"}}}
        result = scanner.scan(japanese)
        self.assertIsNone(result["primary_symbol"])
        self.assertEqual(result["exclusions"][0]["status"], "needs_currency_conversion")
        self.assertEqual(result["markets"], [])
        quote, assumed = scanner._quote_currency("VOD.L", {"quote_currency": "GBp"}, "GBP")
        self.assertEqual(quote, "GBX")
        self.assertFalse(assumed)

    def test_demo_provenance_is_never_selected(self):
        value = copy.deepcopy(self.datasets["ALPHA"])
        value["provenance"]["synthetic"] = True
        result = scanner.scan({"TEST": value})
        self.assertIsNone(result["selected_symbol"])
        self.assertEqual(result["markets"][0]["report"]["data"]["source"], "demo")
        self.assertTrue(all(not strategy["eligible"] for strategy in result["markets"][0]["report"]["strategies"]))

    def test_default_costs_profile_quantity_and_input_profiles_are_preserved(self):
        supplied = {"prop_profile": {"account_size": 50000, "quantity_step": 1, "max_loss_pct": 6}}
        before = copy.deepcopy(supplied)
        config, currency, _, _ = scanner._settings(supplied)
        self.assertEqual(config["account_size"], 50000)
        self.assertEqual(config["prop_profile"]["account_size"], config["account_size"])
        self.assertEqual(config["quantity_step"], 1)
        self.assertEqual((config["fee_bps"], config["slippage_bps"], config["spread_bps"]), (2, 1, 1))
        self.assertEqual(currency, "USD")
        self.assertEqual(supplied, before)

    def test_market_execution_model_is_validated_and_identical_for_train_and_holdout(self):
        value = copy.deepcopy(self.datasets["ALPHA"])
        model = {"fee_bps": 0, "fee_per_unit": 1.25, "spread_bps": 0.5, "slippage_bps": 0.5,
                 "contract_multiplier": 5, "quantity_step": 1, "max_leverage": 2}
        value["execution_model"] = model
        seen = []
        real_train = scanner.train_market
        real_research = backtest.run_research

        def training(symbol, prefix, config):
            seen.append({key: config[key] for key in model})
            return real_train(symbol, prefix, config)

        def research(bars, config):
            seen.append({key: config[key] for key in model})
            return real_research(bars, config)

        with patch.object(scanner, "train_market", side_effect=training), patch.object(backtest, "run_research", side_effect=research):
            result = scanner.scan({"MES=F": value})
        self.assertEqual(seen, [model, model])
        self.assertEqual(result["training_lock"]["execution_models"]["MES=F"], model)
        self.assertEqual(result["markets"][0]["report"]["config"]["contract_multiplier"], 5)
        for bad in ({"account_size": 1000}, {"fee_per_unit": -1}, {"quantity_step": True}, {"spread_bps": float("inf")}):
            value["execution_model"] = bad
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                scanner.scan({"MES=F": value})


class FirmComparisonTests(unittest.TestCase):
    now = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)

    def test_unverified_generic_rules_cannot_produce_recommendation(self):
        with patch.object(scanner.payout, "simulate", side_effect=AssertionError("Generic firm modeled for recommendation")):
            result = scanner.compare_firms(primary_fixture(), [{}], selected=True, now=self.now, account_currency="USD")
        self.assertIsNone(result["recommended_profile_id"])
        self.assertEqual(result["status"], "needs_verified_rules")

    def test_date_only_verification_is_attestation_and_stale_future_naive_values_fail(self):
        self.assertEqual(scanner._verified_rules(scanner.normalize_profile(verified_profile()), self.now), [])
        self.assertEqual(scanner._verified_rules(scanner.normalize_profile(verified_profile(verified_at="2026-10-01T00:00:00Z")), self.now), [])
        for verification in ("2026-01-01", "2026-12-01", "2026-10-01T00:00:00"):
            with self.subTest(verification=verification):
                self.assertTrue(scanner._verified_rules(scanner.normalize_profile(verified_profile(verified_at=verification)), self.now))

    def test_payout_uses_complete_holdout_cadence_and_only_positive_common_currency_ev(self):
        calls = []

        def simulation(_trades, profile, config):
            calls.append(config)
            return {"feasible": True, "status": "supported", "net_expected_value": {"A": 10, "B": 30, "C": -1}[profile["id"]], "reasons": []}

        profiles = [verified_profile(id=name) for name in ("A", "B", "C")]
        with patch.object(scanner.payout, "simulate", side_effect=simulation):
            result = scanner.compare_firms(primary_fixture(), profiles, selected=True, now=self.now, account_currency="USD")
        self.assertEqual(result["recommended_profile_id"], "B")
        self.assertEqual(result["cadence"]["business_days"], 261)
        self.assertTrue(result["cadence"]["includes_inactive_holdout_days"])
        self.assertTrue(all(abs(call["trades_per_day"] - 35 / 261) < 1e-12 for call in calls))
        self.assertTrue(all(call["data_source"] == "csv" and call["returns_are_oos"] for call in calls))
        self.assertTrue(all(call["risk_pct"] == 0.25 for call in calls))

    def test_insufficient_sample_negative_ev_and_other_currency_do_not_recommend(self):
        with patch.object(scanner.payout, "simulate", side_effect=AssertionError("Insufficient sample should not simulate")):
            small = scanner.compare_firms(primary_fixture(29), [verified_profile()], selected=True, now=self.now, account_currency="USD")
            foreign = scanner.compare_firms(primary_fixture(), [verified_profile(account_currency="EUR")], selected=True, now=self.now, account_currency="USD")
        self.assertIsNone(small["recommended_profile_id"])
        self.assertIsNone(foreign["recommended_profile_id"])
        with patch.object(scanner.payout, "simulate", return_value={"feasible": True, "status": "supported", "net_expected_value": -10, "reasons": []}):
            negative = scanner.compare_firms(primary_fixture(), [verified_profile()], selected=True, now=self.now, account_currency="USD")
        self.assertIsNone(negative["recommended_profile_id"])


if __name__ == "__main__":
    unittest.main()
