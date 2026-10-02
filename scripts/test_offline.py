"""Run all unit checks with one explicit immutable raw-input integration skip.

The historical test and production verifiers remain byte-identical. Its full
private-input check runs normally whenever any required raw artifact exists;
only an entirely absent historical input set permits the documented CI skip.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
RAW_INTEGRATION_IDS = frozenset({
    "test_crypto_flow.CryptoFlowTests.test_common_and_reviewed_parent_hashes_are_pinned_before_freeze",
    "tests.test_crypto_flow.CryptoFlowTests.test_common_and_reviewed_parent_hashes_are_pinned_before_freeze",
})


def private_inputs_absent(root, protocol):
    root = Path(root).resolve()
    inputs = protocol.get("inputs", {})
    if not isinstance(inputs, dict) or not inputs:
        return False
    for name, fingerprint in inputs.items():
        if (not isinstance(name, str) or not name.startswith(".local/") or "\\" in name
                or any(part in ("", ".", "..") for part in name.split("/"))
                or not isinstance(fingerprint, str) or len(fingerprint) != 64
                or any(ch not in "0123456789abcdef" for ch in fingerprint)):
            return False
        path = root / name
        if path.exists() or path.is_symlink():
            return False
        for parent in path.parents:
            if parent == root:
                break
            if parent.is_symlink():
                return False
    return True


class MissingHistoricalIntegration(unittest.TestCase):
    def __init__(self, original):
        super().__init__()
        self.original = original

    def id(self):
        return self.original.id()

    def runTest(self):
        self.skipTest("Immutable historical raw inputs are entirely absent; no historical-input replay claimed")


def offline_suite(suite, *, absent):
    result = unittest.TestSuite()
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            result.addTest(offline_suite(item, absent=absent))
        else:
            result.addTest(MissingHistoricalIntegration(item)
                           if absent and item.id() in RAW_INTEGRATION_IDS else item)
    return result


def main():
    parser = argparse.ArgumentParser(description="Run unit checks without copying historical/private inputs")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    protocol_path = ROOT / "data/native-crypto-trend-research/protocol.json"
    # Broken public metadata is never converted into a successful skip.
    protocol = json.loads(protocol_path.read_text())
    absent = private_inputs_absent(ROOT, protocol)
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"))
    result = unittest.TextTestRunner(verbosity=0 if args.quiet else 2).run(
        offline_suite(suite, absent=absent))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
