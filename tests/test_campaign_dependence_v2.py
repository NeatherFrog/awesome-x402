"""New retained-path adapters cannot invent or admit campaign results."""
import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import analyze_campaign_dependence_v2 as analysis
from propdesk import research_campaign as campaign


def packed(root, name, raw):
    value = json.dumps(raw, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    path = root / name
    path.write_bytes(gzip.compress(value, mtime=0))
    return {"path": name, "gzip_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "raw_sha256": hashlib.sha256(value).hexdigest()}


def row(identity="a"):
    return {"id": identity, "variant": {"id": identity, "risk_fraction": .005, "rule": "fixed"},
            "metrics": {"return_pct": -1}, "stress_metrics": {"return_pct": -2},
            "target": {"period_start": "2024-01-01", "period_end_exclusive": "2024-01-04"}}


def path_series(study, identity, scenario, values, *, blocked=False, start="2024-01-01"):
    end = "2024-01-04" if start == "2024-01-01" else "2024-10-06"
    return {"id": study + ":" + identity + ":" + scenario, "study": study, "variant_id": identity,
            "variant": {"id": identity, "risk_fraction": .005, "rule": "fixed"},
            "economic_parameters": {"rule": "fixed"}, "scenario": scenario,
            "start": start, "end_exclusive": end, "dates": analysis.original.calendar(start, end),
            "returns": values, "promotion_blocked": blocked}


class CampaignDependenceV2Tests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.addCleanup(self.directory.cleanup)

    def test_noise_reads_registered_full_calendar_and_requires_role_identity(self):
        item = row()
        raw = {"variant_id": "a", "role": "training", "window": ["2024-01-01", "2024-01-04"],
               "metrics": item["metrics"], "daily_returns": [
                   {"date": "2024-01-01", "return": .01}, {"date": "2024-01-02", "return": 0}, {"date": "2024-01-03", "return": -.02}]}
        item["base_ledger"] = packed(self.root, "noise.gz", raw)
        dates, values, receipt = analysis.daily_path(self.root, "native_noise", item, "base")
        self.assertEqual(values, [.01, 0, -.02])
        self.assertEqual(dates, [entry["date"] for entry in raw["daily_returns"]])
        self.assertEqual(receipt, item["base_ledger"])
        for key, changed in (("variant_id", "another"), ("role", "validation"), ("window", ["2024-01-01", "2025-01-01"]), ("metrics", {"return_pct": 999})):
            with self.subTest(key=key):
                item["base_ledger"] = packed(self.root, "noise.gz", {**raw, key: changed})
                with self.assertRaises(ValueError):
                    analysis.daily_path(self.root, "native_noise", item, "base")

    def test_missing_flat_day_is_rejected_instead_of_filled(self):
        item = row()
        raw = {"variant_id": "a", "role": "training", "window": ["2024-01-01", "2024-01-04"],
               "metrics": item["metrics"], "daily_returns": [
                   {"date": "2024-01-01", "return": .01}, {"date": "2024-01-03", "return": -.02}]}
        item["base_ledger"] = packed(self.root, "noise.gz", raw)
        with self.assertRaisesRegex(ValueError, "every exact calendar date"):
            analysis.daily_path(self.root, "native_noise", item, "base")

    def test_cross_reads_variant_and_total_account_curve_not_monthly_metrics(self):
        item = row()
        raw = {"variant": item["variant"], "metrics": item["metrics"], "daily_curve": [
            {"time": "2024-01-01", "return": .01}, {"time": "2024-01-02", "return": 0}, {"time": "2024-01-03", "return": -.02}]}
        item["ledgers"] = {"base": packed(self.root, "cross.gz", raw)}
        self.assertEqual(analysis.daily_path(self.root, "cross_sectional", item, "base")[1], [.01, 0, -.02])
        raw["variant"] = {**item["variant"], "risk_fraction": .01}
        item["ledgers"]["base"] = packed(self.root, "cross.gz", raw)
        with self.assertRaisesRegex(ValueError, "configuration differs"):
            analysis.daily_path(self.root, "cross_sectional", item, "base")

    def evidence_report(self):
        selected, unselected = row("already_selected"), row("never_inspect")
        report = {"selected": selected["id"], "protocol_sha256": "p" * 64, "training": [unselected, selected]}
        evidence = {"selected": selected["id"], "protocol_sha256": report["protocol_sha256"],
                    "base": {"metrics": selected["metrics"], "daily_returns": [
                        {"date": "2024-01-01", "return": .01}, {"date": "2024-01-02", "return": 0}, {"date": "2024-01-03", "return": -.02}]}}
        report["selection_lock"] = {"selected": selected["id"], "training_primary_evidence_sha256": campaign.digest(evidence)}
        path = self.root / "data/native-crypto-mark-research/training_primary_evidence.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(evidence))
        return report, evidence, path

    def test_mark_retains_only_original_primary_and_binds_canonical_evidence(self):
        report, evidence, path = self.evidence_report()
        retained = analysis.primary_evidence(self.root, "native_mark", report)
        self.assertEqual(len(retained), 1)
        self.assertEqual(retained[0][0]["id"], "already_selected")
        self.assertEqual(retained[0][1], evidence)
        self.assertEqual(analysis.daily_path(self.root, "native_mark", retained[0][0], "base", retained[0][1], retained[0][2])[1], [.01, 0, -.02])
        evidence["base"]["daily_returns"][0]["return"] = 999
        path.write_text(json.dumps(evidence))
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            analysis.primary_evidence(self.root, "native_mark", report)

    def test_primary_raw_evidence_never_falls_back_to_portable_receipt(self):
        report, _evidence, path = self.evidence_report()
        portable = self.root / "docs/research-receipts/native-crypto-mark-research/training_primary_evidence.json"
        portable.parent.mkdir(parents=True)
        portable.write_bytes(path.read_bytes())
        path.unlink()
        with self.assertRaisesRegex(ValueError, "missing or hash mismatch"):
            analysis.primary_evidence(self.root, "native_mark", report)
        report["selected"] = None
        self.assertEqual(analysis.primary_evidence(self.root, "native_mark", report), [])

    def test_known_revoked_path_is_diagnostic_and_excluded_from_parallel_matrix(self):
        series = []
        for study, identity, values, blocked in (("native_mark", "same", [-1, 0, 1], True), ("native_mark_v2", "same", [-1, 0, 1], False), ("native_noise", "other", [1, -2, 1], False)):
            for scenario in ("base", "double_cost"):
                series.append(path_series(study, identity, scenario, values, blocked=blocked))
        value = analysis.summarize([{"evaluated_configurations": 5, "retained_configurations": 3}], series)
        group = value["groups"][0]
        self.assertEqual(value["blocked_daily_configurations"], 1)
        self.assertEqual(group["blocked_base_series_ids"], ["native_mark:same:base"])
        self.assertEqual(group["non_revoked_base"]["dimensions"], 2)
        self.assertEqual(group["base"]["dimensions"], 3)
        self.assertEqual(len(value["execution_interpretation_twins"]), 1)
        self.assertAlmostEqual(value["execution_interpretation_twins"][0]["pearson"], 1)
        for field in ("selection_performed", "eligible_for_paper", "live_orders", "telegram_enabled"):
            self.assertFalse(value[field])

    def test_different_primary_or_window_is_not_invented_interpretation_pair(self):
        for right in (path_series("native_mark_v2", "different", "base", [1, 0, -1]),
                      path_series("native_mark_v2", "same", "base", [1, 0, -1], start="2024-10-03")):
            self.assertEqual(analysis.interpretation_twins([path_series("native_mark", "same", "base", [1, 0, -1], blocked=True), right]), [])

    def test_all_flat_or_only_revoked_groups_render_without_false_rank(self):
        series = [path_series("native_mark", "a", scenario, [0, 0, 0], blocked=True) for scenario in ("base", "double_cost")]
        value = analysis.summarize([{"study": "native_mark", "evaluated_configurations": 96, "retained_configurations": 1}], series)
        self.assertIsNone(value["groups"][0]["non_revoked_base"])
        self.assertIsNone(value["groups"][0]["base"]["effective_covariance_rank"])
        self.assertIn("undefined", analysis.markdown(value))

    def test_publication_waits_for_all_actual_sealed_configurations(self):
        inventory = [{"study": name, "evaluated_configurations": spec["count"], "protocol_producer_results_verified": True}
                     for name, spec in campaign.STUDIES.items()]
        analysis.require_complete(inventory)
        cross = next(item for item in inventory if item["study"] == "cross_sectional")
        cross["evaluated_configurations"] = 71
        with self.assertRaisesRegex(ValueError, "cross_sectional"):
            analysis.require_complete(inventory)
        cross["evaluated_configurations"] = 72
        cross["protocol_producer_results_verified"] = False
        with self.assertRaises(ValueError):
            analysis.require_complete(inventory)


if __name__ == "__main__":
    unittest.main()
