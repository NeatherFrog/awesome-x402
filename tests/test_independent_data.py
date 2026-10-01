import copy
import csv
from datetime import date
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import tempfile
import unittest
from unittest.mock import patch

from scripts import research_independent as study


DATA = study.ROOT / "data" / "independent-history"


class IndependentArchive(unittest.TestCase):
    def copied_data(self, root):
        target = Path(root) / "copy"
        shutil.copytree(DATA, target)
        return target

    def test_real_snapshot_is_immutable_and_full_daily_prices_are_preserved(self):
        bars, manifest = study.load_data(DATA)
        self.assertRegex(manifest["source_commit"], r"^[0-9a-f]{40}$")
        self.assertEqual(manifest["source_commit"], study.SOURCE_COMMIT)
        self.assertEqual(len(bars), 2148)
        self.assertEqual(bars[0]["time"], "2004-08-19T00:00:00Z")
        self.assertEqual(bars[-1]["time"], "2013-03-01T00:00:00Z")
        original = list(csv.DictReader(io.StringIO((DATA / "original" / "GOOG.csv").read_text())))
        for original_row, canonical in zip(original, bars):
            self.assertEqual(canonical["time"], original_row[""] + "T00:00:00Z")
            for field in ("open", "high", "low", "close", "volume"):
                self.assertEqual(canonical[field], float(original_row[field.title()]))
        self.assertFalse(manifest["datasets"][0]["quality"]["prices_adjusted_or_cleaned"])

    def test_timezone_naive_hourly_fx_is_explicitly_excluded(self):
        _, manifest = study.load_data(DATA)
        excluded = manifest["excluded"]
        self.assertEqual(len(excluded), 1)
        self.assertEqual(excluded[0]["symbol"], "EURUSD")
        self.assertEqual(excluded[0]["status"], "unsupported")
        self.assertEqual(excluded[0]["bars"], 5000)
        self.assertIn("timezone-naive", excluded[0]["reason"])
        self.assertNotIn("Z", excluded[0]["source_first_time"])
        self.assertFalse((DATA / "EURUSD-1h.csv").exists())
        self.assertEqual(study.sha256(DATA / "original" / "EURUSD.csv"), study.SOURCE_BLOBS["backtesting/test/EURUSD.csv"])

    def test_fixed_protocol_covers_seven_families_and_baseline_without_holdout_replacement(self):
        protocol = json.loads((DATA / "protocol.json").read_text())
        self.assertEqual(protocol, study.protocol())
        config = protocol["fixed_config"]
        self.assertEqual(len(config["strategy_ids"]), 8)
        self.assertEqual(config["strategy_ids"][-1], "buy_hold")
        self.assertEqual(config["train_fraction"], .6)
        self.assertEqual(config["fee_bps"], 2)
        self.assertEqual(config["slippage_bps"], 1)
        self.assertEqual(config["spread_bps"], 1)
        self.assertEqual(config["risk_pct"], .25)
        self.assertEqual(config["max_leverage"], 2)
        self.assertEqual(config["quantity_step"], 1)
        self.assertTrue(protocol["registered_before_holdout_evaluation"])
        self.assertFalse(protocol["post_result_grid_changes"])
        self.assertIn("no substitution", protocol["selection"])

    def test_source_head_mismatch_is_rejected_before_reading_blobs(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(study, "_git", return_value=b"0" * 40 + b"\n") as git:
                with self.assertRaisesRegex(ValueError, "immutable"):
                    study.prepare(directory, Path(directory) / "data")
            self.assertEqual(git.call_count, 1)
            self.assertFalse((Path(directory) / "data").exists())

    def test_canonical_tampering_cannot_be_hidden_by_updating_manifest_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            copied = self.copied_data(directory)
            path = copied / "GOOG-1d.csv"
            text = path.read_text()
            path.write_text(text.replace("100.0,104.06", "100.01,104.06", 1))
            manifest_path = copied / "provenance.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["datasets"][0]["sha256"] = study.sha256(path)
            manifest_path.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, "Canonical CSV changed"):
                study.load_data(copied)

    def test_raw_source_and_license_bytes_are_checked_even_for_excluded_fx(self):
        for filename in ("original/GOOG.csv", "original/EURUSD.csv", "BACKTESTING-PY-LICENSE.md"):
            with self.subTest(filename=filename), tempfile.TemporaryDirectory() as directory:
                copied = self.copied_data(directory)
                with (copied / filename).open("ab") as stream:
                    stream.write(b"\nchanged\n")
                with self.assertRaisesRegex(ValueError, "archive or license changed"):
                    study.load_data(copied)

    def test_protocol_and_source_provenance_changes_reject_holdout_reuse(self):
        for filename, mutate in (
            ("protocol.json", lambda payload: payload["fixed_config"].update({"fee_bps": 0})),
            ("provenance.json", lambda payload: payload.update({"source_commit": "a" * 40})),
            ("provenance.json", lambda payload: payload["excluded"][0].update({"status": "supported"})),
        ):
            with self.subTest(filename=filename), tempfile.TemporaryDirectory() as directory:
                copied = self.copied_data(directory)
                path = copied / filename
                payload = json.loads(path.read_text())
                mutate(payload)
                path.write_text(json.dumps(payload))
                with self.assertRaises(ValueError):
                    study.load_data(copied)

    def test_corporate_action_gap_audit_flags_unsupported_without_cleanup(self):
        bars, _ = study.load_data(DATA)
        candidate = copy.deepcopy(bars[:2])
        candidate[1].update({"open": 200, "high": 210, "low": 190, "close": 205})
        before = copy.deepcopy(candidate)
        audit = study.quality_audit(candidate)
        self.assertEqual(audit["status"], "unsupported")
        self.assertEqual(len(audit["flagged_gaps"]), 1)
        self.assertFalse(audit["prices_adjusted_or_cleaned"])
        self.assertEqual(candidate, before)

    def test_report_preserves_negative_training_winner_and_all_results(self):
        report = study.research(DATA, date(2026, 10, 1))
        self.assertEqual(report["counts"]["active_strategy_tests"], 7)
        self.assertEqual(report["counts"]["positive_active_holdouts"], 5)
        self.assertEqual(report["counts"]["qualified_active_holdouts"], 0)
        self.assertEqual(report["counts"]["selected_training_winners"], 0)
        self.assertEqual(report["staleness_days"], 4962)
        result = report["reports"][0]
        self.assertEqual(result["data"]["train_bars"], 1288)
        self.assertEqual(result["data"]["test_bars"], 860)
        self.assertEqual(result["training_candidate"], "ema_pullback")
        self.assertIsNone(result["selected_strategy"])
        self.assertEqual(len(result["strategies"]), 8)
        winner = next(item for item in result["strategies"] if item["training_winner"])
        self.assertEqual(winner["test_metrics"]["total_trades"], 29)
        self.assertLess(winner["test_metrics"]["net_profit"], 0)
        self.assertTrue(winner["reasons"])
        self.assertFalse(report["profit_is_guaranteed"])
        self.assertFalse(report["live_orders_enabled"])
        self.assertFalse(report["actual_payouts_verified"])
        encoded = json.dumps(report, allow_nan=False)
        self.assertNotIn('Infinity', encoded)

    def test_saved_json_and_markdown_match_reproduced_fixed_run(self):
        saved = json.loads((study.ROOT / "docs" / "independent-results.json").read_text())
        reproduced = study.research(DATA, date.fromisoformat(saved["as_of"]))
        self.assertEqual(saved, reproduced)
        markdown = (study.ROOT / "docs" / "INDEPENDENT_RESULTS.md").read_text()
        self.assertEqual(markdown, study.render_markdown(reproduced))


if __name__ == "__main__":
    unittest.main()
