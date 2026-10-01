"""The archive search must lock training choices before reading holdout PnL."""

import copy
import csv
import importlib.util
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from propdesk.market import demo_bars

SPEC = importlib.util.spec_from_file_location("propdesk_edge_search", Path(__file__).resolve().parents[1] / "scripts" / "search_edges.py")
search = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = search
SPEC.loader.exec_module(search)


def fixture_universe():
    universe = {}
    stamp = datetime(2015, 1, 1, tzinfo=timezone.utc)
    for index in range(4):
        bars = demo_bars("EURUSD", 900, 42 + index)
        for number, bar in enumerate(bars):
            bar["time"] = (stamp + timedelta(days=number)).isoformat().replace("+00:00", "Z")
        universe[f"TEST{index}"] = bars
    return universe


def fixture_protocol():
    # Small synthetic fixtures test invariants; the production CLI does not
    # expose these weaker gates or use these data to make market claims.
    return search.Protocol(minimum_bars=800, shortlist_size=3, minimum_train_trades=5,
                           minimum_walk_forward_trades=4, minimum_walk_forward_positive_fraction=0.3,
                           minimum_training_profit_factor=1, bootstrap_resamples=200, excluded_symbols=())


def write_fixture_archive(folder, universe):
    source = Path(folder) / "fixture.csv"
    with source.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=("date", "open", "high", "low", "close", "volume", "Name"))
        writer.writeheader()
        for symbol, bars in universe.items():
            for bar in bars:
                writer.writerow({"date": bar["time"][:10], "Name": symbol,
                                 **{key: bar[key] for key in ("open", "high", "low", "close", "volume")}})
    return source


class EdgeSearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.universe = fixture_universe()
        cls.protocol = fixture_protocol()

    def test_final_holdout_perturbation_cannot_change_shortlist_or_locked_training(self):
        original = search.build_training_shortlist(self.universe, self.protocol)
        self.assertGreater(len(original["shortlist"]), 0)
        changed = copy.deepcopy(self.universe)
        for bars in changed.values():
            split = int(len(bars) * self.protocol.train_fraction)
            for index in range(split, len(bars)):
                factor = 1 + 0.002 * (index - split)
                for key in ("open", "high", "low", "close"):
                    bars[index][key] *= factor
        modified = search.build_training_shortlist(changed, self.protocol)
        self.assertEqual(original, modified)
        self.assertEqual(search._fingerprint(original), search._fingerprint(modified))

    def test_training_workers_receive_no_holdout_bars(self):
        tasks = []

        def fake_worker(task):
            tasks.append(task)
            return {"symbol": task[0], "status": "training_evidence_rejected"}

        with patch.object(search, "train_asset", side_effect=fake_worker):
            search.build_training_shortlist(self.universe, self.protocol)
        self.assertEqual(len(tasks), 4)
        self.assertTrue(all(len(task[1]) == 540 for task in tasks))
        self.assertTrue(all(task[1][-1]["time"] == self.universe[task[0]][539]["time"] for task in tasks))

    def test_previously_examined_assets_and_short_histories_are_excluded_before_ranking(self):
        universe = copy.deepcopy(self.universe)
        universe["AAPL"] = universe["TEST0"]
        universe["SHORT"] = universe["TEST0"][:20]
        protocol = search.Protocol(**{**search.asdict(self.protocol), "excluded_symbols": search.PREVIOUSLY_EXAMINED})
        locked = search.build_training_shortlist(universe, protocol)
        excluded = {record["symbol"] for record in locked["availability_exclusions"]}
        self.assertIn("AAPL", excluded)
        self.assertIn("SHORT", excluded)
        self.assertNotIn("AAPL", {record["symbol"] for record in locked["training_results"]})

    def test_training_discontinuity_excludes_asset_but_holdout_discontinuity_cannot_change_lock(self):
        broken_train = copy.deepcopy(self.universe)
        for key in ("open", "high", "low", "close"):
            broken_train["TEST0"][100][key] *= 0.2
        locked = search.build_training_shortlist(broken_train, self.protocol)
        record = next(item for item in locked["training_results"] if item["symbol"] == "TEST0")
        self.assertEqual(record["status"], "training_quality_excluded")

        original = search.build_training_shortlist(self.universe, self.protocol)
        changed = copy.deepcopy(self.universe)
        selected = original["shortlist"][0]["symbol"]
        split = original["shortlist"][0]["training_bars"]
        for key in ("open", "high", "low", "close"):
            changed[selected][split + 5][key] *= 0.2
        self.assertEqual(original, search.build_training_shortlist(changed, self.protocol))
        outcomes = search.evaluate_locked_holdouts(changed, original)
        invalid = next(outcome for outcome in outcomes if outcome["symbol"] == selected)
        self.assertEqual(invalid["status"], "holdout_quality_invalid")
        self.assertFalse(invalid["adjusted_evidence"])
        self.assertEqual([outcome["symbol"] for outcome in outcomes], [candidate["symbol"] for candidate in original["shortlist"]])

    def test_adjusted_bootstrap_rejects_negative_zero_and_small_evidence(self):
        for values in ([-0.2] * 30, [1, -1] * 20, [1] * 5):
            with self.subTest(values=values):
                confidence = search.adjusted_interval([{"return_r": value} for value in values], resamples=200)
                self.assertFalse(confidence["lower_above_zero"])
                self.assertEqual(confidence["interval_confidence_pct"], 99)
        positive = search.adjusted_interval([{"return_r": 0.3}] * 30, resamples=200)
        self.assertTrue(positive["lower_above_zero"])
        self.assertEqual(positive["mean_r_interval"], [0.3, 0.3])

    def test_disk_lock_precedes_holdout_and_identical_rerun_does_not_reopen_it(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "fixture.csv"
            output = Path(folder) / "report.json"
            with source.open("w", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=("date", "open", "high", "low", "close", "volume", "Name"))
                writer.writeheader()
                for symbol, bars in self.universe.items():
                    for bar in bars:
                        writer.writerow({"date": bar["time"][:10], "Name": symbol, **{key: bar[key] for key in ("open", "high", "low", "close", "volume")}})
            real_evaluate = search.evaluate_locked_holdouts
            observed_lock = []

            def guard(universe, lock, *, progress=False):
                saved = json.loads(output.read_text())
                self.assertEqual(saved["phase"], "training_locked")
                self.assertEqual(saved["training_lock_sha256"], search._fingerprint(lock))
                self.assertEqual(saved["holdout_results"], [])
                observed_lock.append(saved)
                return real_evaluate(universe, lock, progress=progress)

            with patch.object(search, "SOURCE_SHA256", search.source_digest(source)), patch.object(search, "evaluate_locked_holdouts", side_effect=guard):
                report = search.run_experiment(source, output, protocol=self.protocol, workers=1, progress=False)
            self.assertEqual(len(observed_lock), 1)
            self.assertEqual(report["phase"], "final_review")
            self.assertEqual(report["training_lock_sha256"], observed_lock[0]["training_lock_sha256"])
            self.assertEqual(report["live_candidates"], 0)
            self.assertEqual(len(report["reports"]), len(report["holdout_results"]))
            for frozen, standard in zip(report["holdout_results"], report["reports"]):
                self.assertEqual(standard["strategies"][0]["test_metrics"], frozen["holdout_metrics"])
                self.assertTrue(standard["historical_only"])
                self.assertTrue(standard["strategies"][0]["training_winner"])
                self.assertFalse(standard["live_orders_enabled"])
            with patch.object(search, "SOURCE_SHA256", search.source_digest(source)), patch.object(search, "evaluate_locked_holdouts", side_effect=AssertionError("Holdout reopened")):
                returned = search.run_experiment(source, output, protocol=self.protocol, workers=1, progress=False)
            self.assertEqual(returned["training_lock_sha256"], report["training_lock_sha256"])

    def test_changed_training_after_lock_is_rejected(self):
        lock = search.build_training_shortlist(self.universe, self.protocol)
        changed = copy.deepcopy(self.universe)
        chosen = lock["shortlist"][0]["symbol"]
        changed[chosen][0]["volume"] += 1
        with self.assertRaisesRegex(ValueError, "Training data changed"):
            search.evaluate_locked_holdouts(changed, lock)

    def test_source_checksum_mismatch_cannot_create_claimed_research(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "incorrect.csv"
            output = Path(folder) / "report.json"
            source.write_text("not the pinned source")
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                search.run_experiment(source, output, progress=False)
            self.assertFalse(output.exists())

    def test_fixed_replay_verifies_portable_engine_without_refitting_or_mutating_lock(self):
        with tempfile.TemporaryDirectory() as folder:
            source = write_fixture_archive(folder, self.universe)
            output = Path(folder) / "report.json"
            digest = search.source_digest(source)
            with patch.object(search, "SOURCE_SHA256", digest), patch.object(search, "engine_fingerprint", return_value="original-engine"):
                original = search.run_experiment(source, output, protocol=self.protocol, workers=1, progress=False)
            original_lock = search._fingerprint(original["locked_training"])
            with patch.object(search, "SOURCE_SHA256", digest), patch.object(search, "engine_fingerprint", return_value="portable-engine"), \
                    patch.object(search.backtest, "_choose_candidate", side_effect=AssertionError("Parameter selection during fixed replay")), \
                    patch.object(search.backtest, "_walk_forward", side_effect=AssertionError("Walk-forward retraining during fixed replay")), \
                    patch.object(search.backtest, "run_research", side_effect=AssertionError("Fresh research during fixed replay")), \
                    patch.object(search, "build_training_shortlist", side_effect=AssertionError("Asset ranking during fixed replay")):
                verified = search.verify_final(source, output, expected_protocol=self.protocol, progress=False)
            self.assertEqual(search._fingerprint(verified["locked_training"]), original_lock)
            self.assertEqual(verified["engine_sha256"], "original-engine")
            self.assertEqual(verified["holdout_results"], original["holdout_results"])
            self.assertEqual(verified["reports"], original["reports"])
            proof = verified["fixed_replay_verifications"][-1]
            self.assertTrue(proof["equivalent"])
            self.assertEqual(proof["current_engine_sha256"], "portable-engine")
            self.assertEqual(proof["candidates_checked"], len(original["locked_training"]["shortlist"]))
            self.assertTrue(all(check["benchmark_equal"] and check["full_curve_bars"] == 360 for check in proof["checks"]))
            with patch.object(search, "SOURCE_SHA256", digest), patch.object(search, "engine_fingerprint", return_value="portable-engine"), \
                    patch.object(search, "evaluate_locked_holdouts", side_effect=AssertionError("Reopened holdout")), \
                    patch.object(search, "build_training_shortlist", side_effect=AssertionError("Repeated search")):
                cached = search.run_experiment(source, output, protocol=self.protocol, progress=False)
            self.assertEqual(cached["training_lock_sha256"], original_lock)

    def test_fixed_replay_refuses_metric_mismatch_and_preserves_existing_file(self):
        with tempfile.TemporaryDirectory() as folder:
            source = write_fixture_archive(folder, self.universe)
            output = Path(folder) / "report.json"
            digest = search.source_digest(source)
            with patch.object(search, "SOURCE_SHA256", digest):
                original = search.run_experiment(source, output, protocol=self.protocol, workers=1, progress=False)
                original["holdout_results"][0]["holdout_metrics"]["net_profit"] += 100
                search.write_json(output, original, compact=True)
                before = search.source_digest(output)
                with self.assertRaisesRegex(ValueError, "holdout_metrics"):
                    search.verify_final(source, output, expected_protocol=self.protocol, progress=False)
                self.assertEqual(search.source_digest(output), before)
                self.assertNotIn("fixed_replay_verifications", json.loads(output.read_text()))

    def test_fixed_replay_refuses_changed_protocol_without_reinterpreting_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            source = write_fixture_archive(folder, self.universe)
            output = Path(folder) / "report.json"
            digest = search.source_digest(source)
            with patch.object(search, "SOURCE_SHA256", digest):
                search.run_experiment(source, output, protocol=self.protocol, workers=1, progress=False)
                before = search.source_digest(output)
                with self.assertRaisesRegex(ValueError, "protocol differs"):
                    search.verify_final(source, output, expected_protocol=search.Protocol(), progress=False)
                self.assertEqual(search.source_digest(output), before)


if __name__ == "__main__":
    unittest.main()
