"""Actual-epoch OHLC conversion and bundled immutable-source contracts."""
from datetime import date
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("research_crypto", ROOT / "scripts" / "research_crypto.py")
crypto = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(crypto)


class CryptoDataTests(unittest.TestCase):
    def setUp(self):
        self.row = [1515560100000, 0.0984, 0.0994766, 0.09828605, 0.0994766, 1820.54447418]

    def test_epoch_is_utc_and_ohlcv_are_not_invented(self):
        bars = crypto.convert_candles([self.row])
        self.assertEqual(bars[0]["time"], "2018-01-10T04:55:00Z")
        self.assertEqual([bars[0][key] for key in ("open", "high", "low", "close", "volume")], self.row[1:])

    def test_wrong_units_alignment_order_and_gaps_are_rejected(self):
        for epoch in (1515560100, True, 1515560100001, "1515560100000"):
            with self.subTest(epoch_type=type(epoch).__name__):
                with self.assertRaises(ValueError):
                    crypto.convert_candles([[epoch, *self.row[1:]]])
        for shift in (0, -300000, 600000):
            with self.assertRaises(ValueError):
                crypto.convert_candles([self.row, [self.row[0] + shift, *self.row[1:]]])

    def test_malformed_envelopes_and_incomplete_rows_are_rejected(self):
        for row in (self.row[:5], [self.row[0], 0.1, 0.09, 0.08, 0.11, 1],
                    [self.row[0], 0.1, 0.12, 0.09, 0.11, -1]):
            with self.assertRaises(ValueError):
                crypto.convert_candles([row])

    def test_bundled_source_hashes_and_pair_currency_are_explicit(self):
        root = ROOT / "data" / "crypto-history"
        provenance = json.loads((root / "provenance.json").read_text())
        self.assertEqual(provenance["source_commit"], crypto.SOURCE_COMMIT)
        self.assertEqual(crypto.digest(root / crypto.FILENAME), provenance["sha256"])
        self.assertEqual(provenance["quote_currency"], "BTC")
        self.assertFalse(provenance["spot_execution_validated"])
        self.assertTrue((root / "UPSTREAM-LICENSE.txt").is_file())


if __name__ == "__main__":
    unittest.main()
