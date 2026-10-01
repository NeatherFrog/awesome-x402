"""HTTP integration: a saved research snapshot and persistent manual context."""
from datetime import datetime, timedelta, timezone
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from propdesk.server import Application, make_handler

NOW = datetime(2026, 10, 1, 12, 5, tzinfo=timezone.utc)


class FrozenDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls.fromtimestamp(NOW.timestamp(), tz or timezone.utc)


def snapshot(source="csv"):
    return {"selected_strategy": "ema_pullback", "training_candidate": "ema_pullback",
            "strategies": [{"id": "ema_pullback", "eligible": True, "training_winner": True,
                            "rule_replay": {"status": "pass"}}],
            "data": {"source": source, "symbol": "EURUSD", "timeframe_minutes": 60},
            "latest_signal": {"status": "candidate", "direction": "long", "strategy_id": "ema_pullback",
                              "reference_time": "2026-10-01T11:00:00Z", "reference_price": 1.1,
                              "stop": 1.0983, "target": 1.10306, "regime": "trend"},
            "market_context": {"last_bar": {"time": "2026-10-01T11:00:00Z", "close": 1.1},
                               "atr14": .001, "timeframe_minutes": 60},
            "profile_rules": {"news_allowed": False, "status": "user_verified"}}


def manual_context():
    return {"macro_cycle": "slowdown", "macro_source": "Manual review",
            "news": {"confirmed": True, "source": "Manual calendar",
                     "observed_at": "2026-10-01T12:00:00Z", "events": []}}


class SetupAPITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.app = Application(self.temp.name)
        handler = make_handler(self.app)
        handler.log_message = lambda *_args: None
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": .01}, daemon=True)
        self.thread.start()
        self.clock = patch("propdesk.setups.datetime", FrozenDateTime)
        self.clock.start()
        self.context_path = Path(self.temp.name) / "context.json"

    def tearDown(self):
        self.clock.stop()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temp.cleanup()

    def request(self, method, path, body=None, *, headers=None, raw=None):
        supplied = dict(headers or {})
        if body is not None:
            raw = json.dumps(body, ensure_ascii=False).encode()
            supplied.setdefault("Content-Type", "application/json")
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=30)
        try:
            connection.request(method, path, body=raw, headers=supplied)
            response = connection.getresponse()
            payload = response.read()
            return response.status, json.loads(payload, parse_constant=lambda value: self.fail(f"Nonfinite response: {value}"))
        finally:
            connection.close()

    def database_counts(self):
        with self.app.store.connect() as connection:
            return {name: connection.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
                    for name in ("profiles", "journal", "signals", "research")}

    def test_setup_requires_research_and_writes_no_context(self):
        status, payload = self.request("POST", "/api/setups", {"context": manual_context()})
        self.assertEqual(status, 400)
        self.assertIn("исследование", payload["error"])
        self.assertFalse(self.context_path.exists())
        self.assertEqual(self.database_counts()["research"], 0)

    def test_saved_research_becomes_paper_plan_and_context_survives_reopening(self):
        rid = self.app.store.save_research(snapshot())
        before = self.database_counts()
        status, plan = self.request("POST", "/api/setups", {"context": manual_context()})
        self.assertEqual(status, 200)
        self.assertEqual(plan["status"], "paper_review")
        self.assertEqual(plan["direction"], "long")
        self.assertEqual(plan["stop_loss"], 1.0983)
        self.assertEqual(plan["take_profit_zone"]["target"], 1.10306)
        self.assertFalse(plan["can_trade"])
        self.assertTrue(plan["planning_only"])
        self.assertEqual(json.loads(self.context_path.read_text()), manual_context())
        restored = Application(self.temp.name)
        resumed = restored.setup({})
        self.assertEqual(resumed["status"], "paper_review")
        self.assertEqual(resumed["context"]["macro_cycle"], "slowdown")
        self.assertEqual(resumed["context"]["news_state"], "checked_no_blackout")
        self.assertEqual(restored.store.latest_research()["research_id"], rid)
        self.assertEqual(self.database_counts(), before)

    def test_omitted_context_reuses_saved_context_explicit_empty_context_resets_it(self):
        self.app.store.save_research(snapshot())
        self.request("POST", "/api/setups", {"context": manual_context()})
        status, resumed = self.request("POST", "/api/setups", {})
        self.assertEqual(status, 200)
        self.assertEqual(resumed["status"], "paper_review")
        status, reset = self.request("POST", "/api/setups", {"context": {}})
        self.assertEqual(status, 200)
        self.assertEqual(reset["status"], "blocked")
        self.assertEqual(reset["context"]["news_state"], "unknown")
        self.assertEqual(json.loads(self.context_path.read_text()), {})

    def test_invalid_context_keeps_previous_context_and_database_unchanged(self):
        self.app.store.save_research(snapshot())
        self.request("POST", "/api/setups", {"context": manual_context()})
        before_file = self.context_path.read_bytes()
        before_counts = self.database_counts()
        invalid = {"macro_cycle": "guaranteed profit"}
        status, payload = self.request("POST", "/api/setups", {"context": invalid})
        self.assertEqual(status, 400)
        self.assertIn("macro_cycle", payload["error"])
        self.assertEqual(self.context_path.read_bytes(), before_file)
        self.assertEqual(self.database_counts(), before_counts)
        self.assertEqual(list(Path(self.temp.name).glob(".context-*")), [])

    def test_nonfinite_or_boolean_score_does_not_write_context(self):
        self.app.store.save_research(snapshot())
        for score in (True, float("nan")):
            payload = {"context": {"sentiment": {"score": score, "source": "Manual",
                                                  "confirmed": True, "observed_at": "2026-10-01T12:00:00Z"}}}
            with self.subTest(score=score):
                status, response = self.request("POST", "/api/setups", payload)
                self.assertEqual(status, 400)
                self.assertIn("error", response)
                self.assertFalse(self.context_path.exists())

    def test_stale_research_snapshot_blocks_new_direction(self):
        research = snapshot()
        research["market_context"]["last_bar"]["time"] = "2026-09-30T11:00:00Z"
        research["latest_signal"]["reference_time"] = "2026-09-30T11:00:00Z"
        self.app.store.save_research(research)
        status, plan = self.request("POST", "/api/setups", {"context": manual_context()})
        self.assertEqual(status, 200)
        self.assertEqual(plan["status"], "blocked")
        self.assertEqual(plan["direction"], "wait")
        self.assertEqual(plan["context"]["price_state"], "stale")
        self.assertIsNone(plan["entry_zone"]["low"])

    def test_demo_fixture_remains_blocked_even_with_good_calendar(self):
        self.app.store.save_research(snapshot("demo"))
        status, plan = self.request("POST", "/api/setups", {"context": manual_context()})
        self.assertEqual(status, 200)
        self.assertEqual(plan["status"], "blocked")
        self.assertEqual(plan["context"]["sources"]["prices"], "synthetic_demo")
        self.assertFalse(plan["can_trade"])
        self.assertIsNone(plan["take_profit_zone"]["target"])

    def test_research_endpoint_persists_causal_snapshot_with_open_and_close_times(self):
        status, research = self.request("POST", "/api/research", {
            "source": "demo", "symbol": "EURUSD", "config": {"strategy_ids": ["ema_pullback"]}})
        self.assertEqual(status, 200)
        market = research["market_context"]
        self.assertIn("last_bar", market)
        self.assertEqual(market["last_bar"]["time"], research["data"]["end"])
        self.assertEqual(market["timeframe_minutes"], research["data"]["timeframe_minutes"])
        self.assertGreater(market["atr14"], 0)
        self.assertEqual(self.app.store.latest_research()["market_context"], market)
        status, plan = self.request("POST", "/api/setups", {"context": manual_context()})
        self.assertEqual(status, 200)
        opening = datetime.fromisoformat(market["last_bar"]["time"].replace("Z", "+00:00"))
        closed = opening + timedelta(minutes=market["timeframe_minutes"])
        self.assertEqual(plan["reference_time"], market["last_bar"]["time"])
        self.assertEqual(plan["reference_close_time"], closed.isoformat().replace("+00:00", "Z"))
        self.assertEqual(plan["status"], "blocked")

    def test_cross_origin_context_write_is_rejected(self):
        self.app.store.save_research(snapshot())
        status, payload = self.request("POST", "/api/setups", {"context": manual_context()},
                                       headers={"Origin": "https://unrelated.example"})
        self.assertEqual(status, 403)
        self.assertIn("error", payload)
        self.assertFalse(self.context_path.exists())


if __name__ == "__main__":
    unittest.main()
