"""An offline skip must never hide public source changes or failing unit tests."""
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import test_offline as runner


class OfflineRunnerTests(unittest.TestCase):
    def test_only_an_entirely_absent_private_input_set_can_be_skipped(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            protocol = {"inputs": {".local/a.json": "1" * 64, ".local/b.json": "2" * 64}}
            self.assertTrue(runner.private_inputs_absent(root, protocol))
            (root / ".local").mkdir()
            (root / ".local/a.json").write_bytes(b"tampered or partial")
            self.assertFalse(runner.private_inputs_absent(root, protocol))

    def test_dangling_path_or_parent_links_are_presence_not_absence(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            protocol = {"inputs": {".local/a.json": "1" * 64}}
            (root / ".local").symlink_to(root / "missing-directory", target_is_directory=True)
            self.assertFalse(runner.private_inputs_absent(root, protocol))
            (root / ".local").unlink()
            (root / ".local").mkdir()
            (root / ".local/a.json").symlink_to(root / "missing-file")
            self.assertFalse(runner.private_inputs_absent(root, protocol))

    def test_public_unsafe_or_malformed_bindings_never_enable_skip(self):
        with tempfile.TemporaryDirectory() as temp:
            for inputs in ({}, {"docs/source.json": "1" * 64},
                           {".local/../outside": "1" * 64}, {".local/a": "invalid"}):
                self.assertFalse(runner.private_inputs_absent(temp, {"inputs": inputs}))

    def test_only_the_explicit_raw_integration_id_is_skipped_and_other_failures_remain(self):
        class Fixture(unittest.TestCase):
            def __init__(self, name, fail=False):
                super().__init__()
                self.name, self.fail = name, fail
            def id(self): return self.name
            def runTest(self):
                if self.fail: self.failTest()
            def failTest(self): self.assertTrue(False, "unrelated failure")
        raw = Fixture(sorted(runner.RAW_INTEGRATION_IDS)[0], fail=True)
        ordinary = Fixture("ordinary.real_failure", fail=True)
        suite = runner.offline_suite(unittest.TestSuite([raw, unittest.TestSuite([ordinary])]), absent=True)
        result = unittest.TextTestRunner(stream=io.StringIO()).run(suite)
        self.assertEqual(len(result.skipped), 1)
        self.assertEqual(len(result.failures), 1)
        self.assertFalse(result.wasSuccessful())
        fresh = Fixture(sorted(runner.RAW_INTEGRATION_IDS)[0], fail=True)
        result = unittest.TextTestRunner(stream=io.StringIO()).run(
            runner.offline_suite(unittest.TestSuite([fresh]), absent=False))
        self.assertFalse(result.skipped)
        self.assertEqual(len(result.failures), 1)

    def test_actual_common_parent_and_frozen_public_producers_remain_exact(self):
        from scripts import research_crypto_flow as flow
        root = runner.ROOT
        parent = json.loads((root / "data/native-crypto-trend-research/protocol.json").read_text())
        canonical = json.dumps(parent, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        self.assertEqual(hashlib.sha256(canonical).hexdigest(), flow.PARENT_PROTOCOL_SHA256)
        self.assertEqual(hashlib.sha256((root / "docs/EIGHT_PERCENT_PROTOCOL.json").read_bytes()).hexdigest(),
                         flow.COMMON_SHA256)
        current = json.loads((root / "data/crypto-flow-research/protocol.json").read_text())
        for protocol in (parent, current):
            for name, expected in protocol["producers"].items():
                self.assertEqual(hashlib.sha256((root / name).read_bytes()).hexdigest(), expected, name)

    def test_production_parent_verifier_still_rejects_unavailable_raw_inputs(self):
        from scripts import research_crypto_flow as flow
        original = flow.shared.file_hash
        def missing_raw(path):
            if ".local" in Path(path).parts:
                raise FileNotFoundError("Synthetic unavailable history")
            return original(path)
        with patch.object(flow.shared, "file_hash", side_effect=missing_raw):
            with self.assertRaisesRegex(FileNotFoundError, "unavailable history"):
                flow.verified_parent()


if __name__ == "__main__":
    unittest.main()
