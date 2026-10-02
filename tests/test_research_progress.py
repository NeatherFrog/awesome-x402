"""Runtime receipt repair must preserve frozen evidence and known blocks."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from propdesk import research_campaign as archive, research_progress as runtime

ROOT = Path(__file__).resolve().parents[1]


class PortableCampaignTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.spec = archive.STUDIES["native_mark"]
        self.report_path = self.root / "docs" / self.spec["file"]
        self.report_path.parent.mkdir()
        self.report_path.write_bytes((ROOT / "docs" / self.spec["file"]).read_bytes())
        self.name = "data/" + self.spec["directory"] + "/retrospective-causality-audit.json"
        self.audit_path = self.root / self.name
        self.audit_path.parent.mkdir(parents=True)
        self.audit_path.write_bytes((ROOT / self.name).read_bytes())
        self.row = {"id": "native_mark", "promotion_blocked": True,
                    "causality_audit_receipt_verified": False,
                    "eligible_for_paper": False, "live_orders": False, "telegram_enabled": False}

    def test_genuine_receipt_is_checked_with_portable_posix_name_and_no_promotion(self):
        original = archive._hash_matches
        names = []
        def strict_name(root, name, expected):
            names.append(name)
            self.assertNotIn("\\", name)
            return original(root, name, expected)
        with patch.object(archive, "_hash_matches", side_effect=strict_name):
            result = runtime.portable_receipt(self.root, self.row)
        self.assertEqual(names, [self.name])
        self.assertTrue(result["causality_audit_receipt_verified"])
        self.assertTrue(result["promotion_blocked"])
        for field in ("eligible_for_paper", "live_orders", "telegram_enabled"):
            self.assertIs(result[field], False)
        self.assertFalse(self.row["causality_audit_receipt_verified"])

    def test_absent_original_uses_exact_packaged_copy_but_present_damage_cannot_hide(self):
        copy = self.root / "docs/research-receipts" / self.spec["directory"] / self.audit_path.name
        copy.parent.mkdir(parents=True)
        copy.write_bytes(self.audit_path.read_bytes())
        self.audit_path.unlink()
        self.assertTrue(runtime.portable_receipt(self.root, self.row)["causality_audit_receipt_verified"])
        self.audit_path.write_text("{}")
        self.assertFalse(runtime.portable_receipt(self.root, self.row)["causality_audit_receipt_verified"])
        self.assertTrue(runtime.portable_receipt(self.root, self.row)["promotion_blocked"])

    def test_changed_report_or_missing_receipt_does_not_verify(self):
        self.report_path.write_text("{}")
        self.assertFalse(runtime.portable_receipt(self.root, self.row)["causality_audit_receipt_verified"])
        self.report_path.write_bytes((ROOT / "docs" / self.spec["file"]).read_bytes())
        self.audit_path.unlink()
        self.assertFalse(runtime.portable_receipt(self.root, self.row)["causality_audit_receipt_verified"])

    def test_board_and_report_wrappers_leave_counts_permissions_and_history_intact(self):
        board = {"studies": [self.row], "reported_evaluated_configurations": 1388,
                 "eligible_for_paper": False, "live_orders": False, "telegram_enabled": False}
        report = {"verification": self.row, "historical_report": {"immutable": True}, "live_orders": False}
        with patch.object(archive, "board", return_value=board), patch.object(archive, "report", return_value=report):
            result = runtime.board(self.root)
            item = runtime.report(self.root, "native_mark")
        self.assertEqual(result["reported_evaluated_configurations"], 1388)
        self.assertTrue(result["studies"][0]["causality_audit_receipt_verified"])
        self.assertEqual(item["historical_report"], {"immutable": True})
        for field in ("eligible_for_paper", "live_orders", "telegram_enabled"):
            self.assertIs(result[field], False)
        with patch.object(archive, "report", return_value=None):
            self.assertIsNone(runtime.report(self.root, "native_mark"))


if __name__ == "__main__":
    unittest.main()
