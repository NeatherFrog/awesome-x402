import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from propdesk import evidence


class EvidenceTests(unittest.TestCase):
    def test_missing_reports_cannot_enable_signals(self):
        with tempfile.TemporaryDirectory() as root:
            b = evidence.board(root)
        self.assertIsNone(b["primary"])
        self.assertFalse(b["live_orders"])
        self.assertFalse(b["telegram_enabled"])
        self.assertEqual(b["variant_count"], 0)

    def test_altered_producer_cannot_promote_claimed_candidate(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            (root / "docs").mkdir()
            (root / "engine.py").write_text("original")
            p = {"producers": {"engine.py": hashlib.sha256(b"original").hexdigest()}}
            ph = hashlib.sha256(json.dumps(p, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            value = {"phase": "completed_provisional_candidate", "protocol": p, "protocol_sha256": ph,
                     "retrospective_provisional_candidate": True,
                     "validation": {"checks": dict.fromkeys(evidence.CARRY_CHECKS, True)},
                     "final": {"checks": dict.fromkeys(evidence.CARRY_CHECKS, True)}}
            (root / "docs" / "funding-calibrated-research.json").write_text(json.dumps(value))
            self.assertEqual(evidence.board(root)["primary"]["mode"], "paper_candidate")
            (root / "engine.py").write_text("modified")
            b = evidence.board(root)
            self.assertIsNone(b["primary"])
            self.assertFalse(b["live_orders"])

    def test_failed_final_check_and_unknown_study_fail_closed(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            (root / "docs").mkdir()
            (root / "engine.py").write_text("original")
            p = {"producers": {"engine.py": hashlib.sha256(b"original").hexdigest()}}
            ph = hashlib.sha256(json.dumps(p, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            v = {"phase": "completed_provisional_candidate", "protocol": p, "protocol_sha256": ph,
                 "retrospective_provisional_candidate": True,
                 "validation": {"checks": dict.fromkeys(evidence.CARRY_CHECKS, True)},
                 "final": {"checks": {**dict.fromkeys(evidence.CARRY_CHECKS, True), "block_ci99_lower_positive": False}},
                 "confirmation": {"checks": dict.fromkeys(evidence.CARRY_CHECKS, True)}}
            (root / "docs" / "funding-calibrated-research.json").write_text(json.dumps(v))
            self.assertIsNone(evidence.board(root)["primary"])
            v["final"]["checks"]["block_ci99_lower_positive"] = True
            v["validation"]["checks"].pop("both_halves_positive")
            (root / "docs" / "funding-calibrated-research.json").write_text(json.dumps(v))
            self.assertIsNone(evidence.board(root)["primary"])
            v["validation"]["checks"]["both_halves_positive"] = True
            v["phase"] = "completed_final_failed"
            (root / "docs" / "funding-calibrated-research.json").write_text(json.dumps(v))
            self.assertIsNone(evidence.board(root)["primary"])
            with self.assertRaises(ValueError):
                evidence.report(root, "../secret")


if __name__ == "__main__":
    unittest.main()
