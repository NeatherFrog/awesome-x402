"""Dependence math cannot supply missing returns or independent-trial claims."""
import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import analyze_campaign_dependence as analysis


class CampaignDependenceTests(unittest.TestCase):
    def test_identical_scaled_and_inverse_paths_have_effective_rank_one(self):
        value = analysis.matrix_statistics([[-1, 1, -1, 1], [-2, 2, -2, 2], [1, -1, 1, -1]])
        self.assertAlmostEqual(value["effective_covariance_rank"], 1)
        self.assertEqual(value["pearson"], [[1, 1, -1], [1, 1, -1], [-1, -1, 1]])

    def test_equal_variance_orthogonal_paths_have_rank_two(self):
        value = analysis.matrix_statistics([[-1, 1, -1, 1], [-1, -1, 1, 1]])
        self.assertAlmostEqual(value["effective_covariance_rank"], 2)
        self.assertEqual(value["pearson"][0][1], 0)
        self.assertEqual(value["sample_ddof"], 1)
        self.assertAlmostEqual(value["covariance_trace"], 8 / 3)
        self.assertAlmostEqual(value["covariance_squared_trace"], 32 / 9)

    def test_unequal_variance_rank_is_covariance_not_correlation_rank(self):
        value = analysis.matrix_statistics([[-1, 1, -1, 1], [-2, -2, 2, 2]])
        self.assertAlmostEqual(value["effective_covariance_rank"], 25 / 17)
        self.assertEqual(value["pearson"][0][1], 0)

    def test_zero_variance_correlations_are_unknown_not_independent(self):
        value = analysis.matrix_statistics([[0, 0, 0], [1, 2, 3]])
        self.assertEqual(value["zero_variance_paths"], 1)
        self.assertEqual(value["positive_variance_paths"], 1)
        self.assertEqual(value["pearson"][0], [None, None])
        self.assertAlmostEqual(value["effective_covariance_rank"], 1)
        self.assertIsNone(analysis.matrix_statistics([[0, 0, 0]])["effective_covariance_rank"])

    def test_summary_keeps_undefined_pairs_and_never_replaces_them_with_zero(self):
        self.assertEqual(analysis.correlation_summary([None, -.5, .25, .75]),
                         {"known_pairs": 3, "undefined_pairs": 1, "minimum": -.5, "median": .25, "maximum": .75})
        self.assertIsNone(analysis.correlation_summary([None])["median"])

    def test_covariance_rejects_single_observation_shape_and_nonfinite(self):
        for values in ([], [[1]], [[1, 2], [3]], [[1, float("nan")]], [[1, float("inf")]], [[True, 2]]):
            with self.subTest(values=values), self.assertRaises(ValueError):
                analysis.matrix_statistics(values)

    def test_calendar_requires_exact_flat_dates_no_fill_or_duplicate(self):
        dates = analysis.calendar("2024-01-05", "2024-01-09")
        self.assertEqual(dates, ["2024-01-05", "2024-01-06", "2024-01-07", "2024-01-08"])
        self.assertEqual(analysis.validate_path(dates, [.1, 0, 0, -.1], dates[0], "2024-01-09"), [.1, 0, 0, -.1])
        for wrong in (dates[:2] + dates[3:], dates[:2] + dates[1:3], list(reversed(dates))):
            with self.subTest(dates=wrong), self.assertRaises(ValueError):
                analysis.validate_path(wrong, [0] * len(wrong), "2024-01-05", "2024-01-09")
        with self.assertRaises(ValueError):
            analysis.validate_path(dates, [0, False, 0, 0], "2024-01-05", "2024-01-09")

    def test_risk_sibling_identity_does_not_remove_economic_parameters(self):
        left = {"id": "a", "risk_fraction": .01, "context": "london", "parent_variant": {"id": "x", "risk": .01, "reward_risk": 2}}
        right = {"id": "b", "risk_fraction": .005, "context": "london", "parent_variant": {"id": "y", "risk": .005, "reward_risk": 2}}
        self.assertEqual(analysis.economic_parameters(left), analysis.economic_parameters(right))
        right["parent_variant"]["reward_risk"] = 3
        self.assertNotEqual(analysis.economic_parameters(left), analysis.economic_parameters(right))

    def test_distinct_windows_are_separate_and_cost_replicas_are_labeled(self):
        series = []
        for start, end in (("2024-01-01", "2024-01-04"), ("2024-10-03", "2024-10-06")):
            for scenario, returns in (("base", [0, .1, -.1]), ("double_cost", [0, .09, -.11])):
                series.append({"id": start + scenario, "study": "fixture", "variant_id": start,
                    "economic_parameters": {"rule": "unchanged"}, "scenario": scenario, "start": start,
                    "end_exclusive": end, "dates": analysis.calendar(start, end), "returns": returns})
        value = analysis.summarize([{"evaluated_configurations": 5, "retained_configurations": 2}], series)
        self.assertEqual(len(value["groups"]), 2)
        self.assertEqual(value["missing_daily_configurations"], 3)
        for group in value["groups"]:
            self.assertEqual(group["base"]["observations"], 3)
            self.assertEqual(group["base"]["dimensions"], 1)
            self.assertTrue(group["base_to_double_cost"][0]["same_model_different_costs"])
        self.assertFalse(value["selection_performed"])
        self.assertFalse(value["eligible_for_paper"])
        self.assertFalse(value["live_orders"])
        self.assertFalse(value["telegram_enabled"])

    def test_registered_gzip_raw_and_compressed_hashes_are_both_required(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = json.dumps({"dates": ["2024-01-01"], "daily_returns": [0]}).encode()
            path = root / "ledger.json.gz"
            path.write_bytes(gzip.compress(raw, mtime=0))
            receipt = {"path": path.name, "compressed_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                       "raw_sha256": hashlib.sha256(raw).hexdigest()}
            self.assertEqual(analysis.ledger(root, receipt)["daily_returns"], [0])
            bad = {**receipt, "raw_sha256": "0" * 64}
            with self.assertRaises(ValueError):
                analysis.ledger(root, bad)
            with patch.object(analysis, "MAX_RAW", 4), self.assertRaises(ValueError):
                analysis.ledger(root, receipt)
            path.write_bytes(path.read_bytes() + b"changed")
            with self.assertRaises(ValueError):
                analysis.ledger(root, receipt)

    def test_retained_ledger_paths_cannot_escape_project(self):
        with tempfile.TemporaryDirectory() as directory:
            for name in ("../private", "/etc/passwd", "C:\\private"):
                with self.subTest(name=name), self.assertRaises(ValueError):
                    analysis.ledger(Path(directory), {"path": name})


if __name__ == "__main__":
    unittest.main()
