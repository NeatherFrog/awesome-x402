import csv
from concurrent.futures import ThreadPoolExecutor
import io
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from propdesk.store import Store

_SQLITE_CONNECT = sqlite3.connect


class TrackedConnection(sqlite3.Connection):
    """Retain real handles so garbage collection cannot mask missing closure."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.close_calls = 0

    def close(self):
        self.close_calls += 1
        return super().close()


class FailedPragmaConnection(TrackedConnection):
    def execute(self, sql, *args, **kwargs):
        if sql == "PRAGMA journal_mode=WAL":
            raise sqlite3.OperationalError("Controlled SQLite setup failure")
        return super().execute(sql, *args, **kwargs)


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


class ConnectionLifetimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.connections = []
        self.connection_patch = patch("propdesk.store.sqlite3.connect", side_effect=self.connect)
        self.connection_patch.start()
        self.store = Store(self.temp.name)

    def tearDown(self):
        self.connection_patch.stop()
        self.temp.cleanup()

    def connect(self, *args, **kwargs):
        kwargs.setdefault("factory", TrackedConnection)
        connection = _SQLITE_CONNECT(*args, **kwargs)
        self.connections.append(connection)
        return connection

    def assert_handles_closed(self):
        self.assertTrue(self.connections)
        for connection in self.connections:
            self.assertEqual(connection.close_calls, 1)
            with self.assertRaisesRegex(sqlite3.ProgrammingError, "closed"):
                _ = connection.in_transaction

    def test_constructor_and_every_store_operation_close_retained_handles(self):
        self.assert_handles_closed()
        self.store.save_profile({"id": "profile", "name": "Example"})
        self.assertEqual(self.store.profiles([])[0]["name"], "Example")
        trade = self.store.add_trade({"symbol": "EURUSD", "side": "long", "entry": 1.1,
                                     "exit": 1.11, "stop": 1.09, "quantity": 1000})
        self.assertEqual(self.store.journal()["stats"]["total_trades"], 1)
        self.assertIn("EURUSD", self.store.export_journal())
        self.assertTrue(self.store.delete_trade(trade["id"]))
        research_id = self.store.save_research({"symbol": "AAPL", "selected_strategy": None})
        self.assertEqual(self.store.latest_research()["research_id"], research_id)
        signal = self.store.add_signal({"symbol": "EURUSD", "side": "long", "price": 1.1})
        self.assertEqual(self.store.signals()[0]["id"], signal["id"])
        self.assert_handles_closed()

    def test_success_commits_before_close_and_exception_rolls_back_before_close(self):
        with self.store.connect() as successful:
            successful.execute("INSERT INTO profiles VALUES (?,?)", ("committed", json.dumps({"id": "committed"})))
        with self.assertRaisesRegex(RuntimeError, "operation failed"):
            with self.store.connect() as failed:
                failed.execute("INSERT INTO profiles VALUES (?,?)", ("rolled-back", json.dumps({"id": "rolled-back"})))
                raise RuntimeError("operation failed")
        self.assertEqual([profile["id"] for profile in self.store.profiles([])], ["committed"])
        self.assert_handles_closed()

    def test_commit_failure_closes_connection_and_rolls_back_deferred_constraint(self):
        with self.assertRaises(sqlite3.IntegrityError):
            with self.store.connect() as connection:
                connection.execute("PRAGMA foreign_keys=ON")
                connection.execute("CREATE TABLE parent (id INTEGER PRIMARY KEY)")
                connection.execute("CREATE TABLE child (parent_id INTEGER REFERENCES parent(id) DEFERRABLE INITIALLY DEFERRED)")
                connection.execute("INSERT INTO child VALUES (99)")
                # The deferred constraint fails at commit, after yield returns.
        with self.store.connect() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM child").fetchone()[0], 0)
        self.assert_handles_closed()

    def test_setup_failure_before_yield_still_releases_real_sqlite_handle(self):
        with patch("propdesk.store.sqlite3.connect",
                   side_effect=lambda *args, **kwargs: self.connect(*args, **kwargs, factory=FailedPragmaConnection)):
            with self.assertRaisesRegex(sqlite3.OperationalError, "setup failure"):
                Store(self.temp.name)
        self.assert_handles_closed()

    def test_serialization_and_read_failure_close_handles_and_preserve_transactions(self):
        with self.assertRaises(ValueError):
            self.store.save_profile({"id": "nonfinite", "value": float("inf")})
        with self.assertRaises(ValueError):
            self.store.save_research({"value": float("nan")})
        self.assertEqual(self.store.profiles([]), [])
        self.assertIsNone(self.store.latest_research())
        with self.store.connect() as connection:
            connection.execute("INSERT INTO profiles VALUES (?,?)", ("corrupt", "{"))
        with self.assertRaises(json.JSONDecodeError):
            self.store.profiles([])
        self.assert_handles_closed()

    def test_database_can_be_renamed_and_deleted_while_closed_connection_objects_are_retained(self):
        self.store.save_profile({"id": "persisted"})
        self.assert_handles_closed()
        self.assertFalse(Path(str(self.store.path) + "-wal").exists())
        self.assertFalse(Path(str(self.store.path) + "-shm").exists())
        renamed = self.store.path.with_name("renamed.sqlite3")
        self.store.path.replace(renamed)
        renamed.unlink()
        self.assertFalse(renamed.exists())

    def test_parallel_operations_keep_independent_transactions_and_close_every_handle(self):
        def write(index):
            self.store.save_profile({"id": f"profile-{index}", "index": index})
            return len(self.store.profiles([]))
        with ThreadPoolExecutor(max_workers=6) as pool:
            observed = list(pool.map(write, range(24)))
        self.assertEqual(len(observed), 24)
        self.assertEqual(len(self.store.profiles([])), 24)
        self.assert_handles_closed()


if __name__ == "__main__":
    unittest.main()
