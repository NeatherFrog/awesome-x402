"""Portable receipts must preserve exact evidence and exclude execution data."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import package_research_receipts as packager


class PackagedReceiptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "data" / "example-research"
        self.source.mkdir(parents=True)
        self.spec = {"example": {"directory": "example-research"}}
        self.status = {"protocol_verified": True, "producer_hashes_verified": True,
                       "training_results_verified": True}

    def run_packager(self, *, phase="completed_no_training_candidate"):
        with patch.object(packager, "STUDIES", self.spec), \
                patch.object(packager, "read_report", return_value={"phase": phase}), \
                patch.object(packager, "inspect", return_value=self.status):
            return packager.package_receipts(self.root)

    def test_only_exact_public_locks_are_copied_and_can_be_packaged_again(self):
        body = b'{"fixed":true}\n'
        (self.source / "protocol.json").write_bytes(body)
        (self.source / "customer.json").write_bytes(b"private user state")
        (self.source / "execution.json.gz").write_bytes(b"full trade ledger")
        first = self.run_packager()
        self.assertEqual(first, self.run_packager())
        target = self.root / "docs/research-receipts/example-research"
        self.assertEqual([p.name for p in target.iterdir()], ["protocol.json"])
        self.assertEqual((target / "protocol.json").read_bytes(), body)

    def test_partial_or_unverified_studies_cannot_be_presented_as_completed_receipts(self):
        (self.source / "protocol.json").write_bytes(b"{}")
        self.assertEqual(self.run_packager(phase="training"), [])
        self.status["training_results_verified"] = False
        with self.assertRaisesRegex(ValueError, "Unverified completed"):
            self.run_packager()
        self.assertFalse((self.root / "docs/research-receipts").exists())

    def test_changed_packaged_lock_is_not_overwritten(self):
        path = self.source / "protocol.json"
        path.write_bytes(b'{"original":true}')
        self.run_packager()
        path.write_bytes(b'{"changed":true}')
        with self.assertRaisesRegex(ValueError, "frozen receipt changed"):
            self.run_packager()
        self.assertEqual((self.root / "docs/research-receipts/example-research/protocol.json").read_bytes(),
                         b'{"original":true}')


if __name__ == "__main__":
    unittest.main()
