import csv
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from propdesk.store import Store


class JournalTests(unittest.TestCase):
    def test_blank_optional_data_directory_uses_private_default(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.dict(os.environ, {"TRADING_DATA_DIR": ""}), patch("propdesk.store.ROOT", root):
                store = Store()
            self.assertEqual(store.path, root / ".local" / "propdesk.sqlite3")

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(self.temp.name)
        self.trade = {"symbol": "EURUSD", "side": "long", "entry": 1.1, "exit": 1.11,
                      "stop": 1.09, "quantity": 10000, "contract_multiplier": 1,
                      "fees": 5, "strategy": "=1+1", "notes": "<script>alert(1)</script>",
                      "opened_at": "2026-01-01T10:00:00Z", "closed_at": "2026-01-01T11:00:00Z",
                      "setup_followed": True}

    def tearDown(self):
        self.temp.cleanup()

    def test_long_and_short_net_pnl_and_persistence(self):
        long = self.store.add_trade(self.trade)
        self.assertAlmostEqual(long["pnl"], 95)
        short = self.store.add_trade({**self.trade, "side": "short", "stop": 1.12, "exit": 1.09})
        self.assertAlmostEqual(short["pnl"], 95)
        reopened = Store(self.temp.name).journal()
        self.assertEqual(reopened["stats"]["total_trades"], 2)
        self.assertAlmostEqual(reopened["stats"]["net_pnl"], 190)
        self.assertEqual(reopened["stats"]["discipline_pct"], 100)

    def test_invalid_trade_does_not_write(self):
        for patch in ({"quantity": -1}, {"stop": 1.2}, {"entry": float("nan")},
                      {"fees": -1}, {"opened_at": "2026-01-01"}, {"closed_at": "2025-01-01T00:00:00Z"},
                      {"setup_followed": "true"}, {"quantity": True}):
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                self.store.add_trade({**self.trade, **patch})
        self.assertEqual(self.store.journal()["stats"]["total_trades"], 0)

    def test_csv_escapes_spreadsheet_formulas_and_preserves_notes(self):
        self.store.add_trade(self.trade)
        rows = list(csv.DictReader(io.StringIO(self.store.export_journal())))
        self.assertEqual(rows[0]["strategy"], "'=1+1")
        self.assertEqual(rows[0]["notes"], self.trade["notes"])

    def test_delete_and_stats(self):
        first = self.store.add_trade(self.trade)
        self.store.add_trade({**self.trade, "exit": 1.085, "setup_followed": False})
        stats = self.store.journal()["stats"]
        self.assertEqual(stats["total_trades"], 2)
        self.assertEqual(stats["discipline_pct"], 50)
        self.assertGreater(stats["max_drawdown"], 0)
        self.assertTrue(self.store.delete_trade(first["id"]))
        self.assertFalse(self.store.delete_trade(first["id"]))


if __name__ == "__main__":
    unittest.main()
