"""External history follows the real-data engine without synthetic fallback."""
import tempfile
import unittest
from unittest.mock import patch

from propdesk.market import parse_csv
from propdesk.server import Application, ROOT, payout_cadence


class FeedApplicationTests(unittest.TestCase):
    def test_provider_history_persists_provenance_and_closes_snapshot(self):
        bars = parse_csv((ROOT / "data/market-history/AAPL-1d.csv").read_text())
        provenance = {"provider": "fixture-only transport", "retrieved_at": "2026-10-01T00:00:00Z",
                      "warnings": ["Fixture is archived; it is not a live quote"]}
        with tempfile.TemporaryDirectory() as directory:
            app = Application(directory)
            with patch("propdesk.feeds.get_history", return_value={"bars": bars, "provenance": provenance}) as fetch:
                result = app.research({"source": "yahoo", "symbol": "AAPL", "interval": "1d", "range": "5y",
                                       "config": {"strategy_ids": ["ema_pullback", "buy_hold"]}})
            fetch.assert_called_once_with("AAPL", interval="1d", range_="5y")
            self.assertEqual(result["data"]["source"], "csv")
            self.assertEqual(result["data"]["input_source"], "yahoo")
            self.assertEqual(result["data"]["provenance"], provenance)
            self.assertEqual(result["market_context"]["last_bar"], bars[-1])
            self.assertEqual(app.store.latest_research()["data"]["provenance"], provenance)
            self.assertIn(provenance["warnings"][0], result["summary"]["warnings"])
            self.assertEqual(app.setup({})["status"], "blocked")

    def test_provider_denial_never_saves_demo_or_changes_existing_research(self):
        with tempfile.TemporaryDirectory() as directory:
            app = Application(directory)
            with patch("propdesk.feeds.get_history", side_effect=ValueError("Network rejected HTTP 403")):
                with self.assertRaisesRegex(ValueError, "403"):
                    app.research({"source": "yahoo", "symbol": "EURUSD"})
            self.assertIsNone(app.store.latest_research())

    def test_payout_rate_includes_idle_days_at_both_holdout_edges(self):
        research = {"data": {"holdout_start": "2026-01-05T00:00:00Z", "end": "2026-01-16T00:00:00Z"}}
        trades = [{"entry_time": "2026-01-09T00:00:00Z", "exit_time": "2026-01-09T00:00:00Z"}]
        rate = payout_cadence(research, trades)
        self.assertEqual(rate["trades_per_day"], 0.1)
        self.assertEqual(rate["trade_rate_basis"], "oos_closed_trades_per_full_holdout_business_day")
        self.assertEqual(payout_cadence(research, []), {})


if __name__ == "__main__":
    unittest.main()
