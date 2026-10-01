"""Economic-calendar HTTP and setup integration using only offline fixtures."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import http.client
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from propdesk.market import parse_csv
from propdesk.news import SOURCE_URL
from propdesk.server import Application, ROOT, make_handler


NOW = datetime(2026, 10, 1, 12, 15, tzinfo=timezone.utc)


class FrozenDateTime(datetime):
    current = NOW

    @classmethod
    def now(cls, tz=None):
        return cls.fromtimestamp(cls.current.timestamp(), tz or timezone.utc)


def calendar_rows(*, impact="High"):
    return [{"title": "Scheduled USD release", "country": "USD", "date": "2026-10-01T12:30:00Z",
             "impact": impact, "forecast": "unused", "actual": "unused"},
            {"title": "EUR survey", "country": "EUR", "date": "2026-10-02T09:00:00Z", "impact": "Low"}]


def snapshot():
    opening = FrozenDateTime.current.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
    stamp = opening.isoformat().replace("+00:00", "Z")
    return {"selected_strategy": "ema_pullback", "training_candidate": "ema_pullback",
            "strategies": [{"id": "ema_pullback", "eligible": True, "training_winner": True,
                            "rule_replay": {"status": "pass"}}],
            "data": {"source": "csv", "symbol": "EURUSD", "timeframe_minutes": 60},
            "config": {"risk_pct": .25}, "summary": {"warnings": []},
            "latest_signal": {"status": "candidate", "direction": "long", "strategy_id": "ema_pullback",
                              "reference_time": stamp, "reference_price": 1.1,
                              "stop": 1.0983, "target": 1.10306, "regime": "trend"},
            "market_context": {"last_bar": {"time": stamp, "close": 1.1},
                               "atr14": .001, "timeframe_minutes": 60},
            "profile_rules": {"news_allowed": False, "status": "user_verified"}}


class NewsAPITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        FrozenDateTime.current = NOW
        self.environment = patch.dict(os.environ, {"TRADING_AUTOPILOT_DEFAULT": "0", "TRADING_SUPERVISED": "0"})
        self.environment.start()
        self.transport_patch = patch("propdesk.news._fetch", side_effect=ValueError("Controlled HTTP 403"))
        self.transport = self.transport_patch.start()
        self.news_clock = patch("propdesk.news._clock", side_effect=lambda now=None: now if now is not None else FrozenDateTime.now(timezone.utc))
        self.news_clock.start()
        self.setup_clock = patch("propdesk.setups.datetime", FrozenDateTime)
        self.setup_clock.start()
        self.app = Application(self.temp.name)
        self.context_path = Path(self.temp.name) / "context.json"
        handler = make_handler(self.app)
        handler.log_message = lambda *_args: None
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": .01}, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.app.autopilot.stop()
        deadline = time.monotonic() + 5
        while self.app.scanner.busy and time.monotonic() < deadline:
            time.sleep(.01)
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.setup_clock.stop()
        self.news_clock.stop()
        self.transport_patch.stop()
        self.environment.stop()
        self.temp.cleanup()

    def request(self, method, path, payload=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        body = json.dumps(payload).encode() if payload is not None else None
        headers = {"Content-Type": "application/json"} if body is not None else {}
        try:
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            result = json.loads(response.read(), parse_constant=lambda value: self.fail("Nonfinite HTTP JSON: " + value))
            return response.status, result, dict(response.getheaders())
        finally:
            connection.close()

    def refresh(self, *, impact="High"):
        self.transport.side_effect = None
        self.transport.return_value = json.dumps(calendar_rows(impact=impact)).encode()
        code, status, _ = self.request("POST", "/api/news/refresh", {})
        self.assertEqual(code, 200, status)
        self.assertTrue(status["confirmed"], status)
        return status

    def setup_plan(self, context=None, *, explicit=False):
        self.app.store.save_research(snapshot())
        payload = {"context": context} if explicit else {}
        code, result, _ = self.request("POST", "/api/setups", payload)
        self.assertEqual(code, 200, result)
        return result

    def wait_job(self, identifier):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            job = self.app.scanner.get(identifier)
            if job["state"] in ("completed", "failed", "interrupted"):
                return job
            time.sleep(.01)
        self.fail("Offline worker exceeded the test deadline")

    def test_status_is_readonly_unknown_without_external_requests_or_empty_confirmation(self):
        code, status, headers = self.request("GET", "/api/news/status")
        self.assertEqual(code, 200)
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(status["state"], "unknown")
        self.assertFalse(status["confirmed"])
        self.assertEqual(status["event_count"], 0)
        self.assertIsNone(status["retrieved_at"])
        self.assertIsNone(status["coverage"])
        self.assertFalse(self.app.news.path.exists())
        self.transport.assert_not_called()

    def test_explicit_refresh_creates_verified_transport_cache_with_known_at_and_no_signal_numbers(self):
        status = self.refresh()
        self.assertEqual(status["state"], "ready")
        self.assertEqual(status["event_count"], 2)
        self.assertEqual(status["retrieved_at"], "2026-10-01T12:15:00Z")
        self.assertEqual(status["source"], SOURCE_URL)
        self.assertEqual(len(status["body_sha256"]), 64)
        self.assertFalse(status["provenance"]["historical_publication_times_verified"])
        self.assertFalse(status["provenance"]["complete_schedule_verified"])
        context = self.app.news.context()
        self.assertEqual(context["events"][0]["known_at"], status["retrieved_at"])
        self.assertNotIn("forecast", context["events"][0])
        self.assertNotIn("actual", context["events"][0])
        before = self.app.news.path.read_bytes()
        code, checked, _ = self.request("GET", "/api/news/status")
        self.assertEqual(code, 200)
        self.assertTrue(checked["confirmed"])
        self.assertEqual(self.app.news.path.read_bytes(), before)
        self.assertEqual(self.transport.call_count, 1)

    def test_refresh_throttle_uses_one_hour_cache_and_retrieval_time_moves_on_new_refresh(self):
        first = self.refresh()
        FrozenDateTime.current += timedelta(minutes=59)
        code, cached, _ = self.request("POST", "/api/news/refresh", {})
        self.assertEqual(code, 200)
        self.assertEqual(cached["retrieved_at"], first["retrieved_at"])
        self.assertEqual(self.transport.call_count, 1)
        FrozenDateTime.current += timedelta(minutes=1)
        code, refreshed, _ = self.request("POST", "/api/news/refresh", {})
        self.assertEqual(code, 200)
        self.assertEqual(self.transport.call_count, 2)
        self.assertEqual(refreshed["retrieved_at"], "2026-10-01T13:15:00Z")
        self.assertEqual(self.app.news.context()["events"][0]["known_at"], refreshed["retrieved_at"])

    def test_high_impact_provider_cache_blocks_setup_without_persisting_injected_context(self):
        self.refresh()
        result = self.setup_plan()
        self.assertEqual(result["context"]["news_state"], "blackout")
        self.assertEqual(result["context"]["sources"]["news"], SOURCE_URL)
        self.assertEqual(result["status"], "blocked")
        self.assertFalse(result["can_trade"])
        self.assertFalse(self.context_path.exists())
        explicit = self.setup_plan({}, explicit=True)
        self.assertEqual(explicit["context"]["news_state"], "blackout")
        self.assertEqual(json.loads(self.context_path.read_text()), {})

    def test_missing_or_failed_calendar_keeps_restricted_setup_unknown_and_blocked(self):
        missing = self.setup_plan()
        self.assertEqual(missing["context"]["news_state"], "unknown")
        self.assertEqual(missing["status"], "blocked")
        self.transport.assert_not_called()
        code, unavailable, _ = self.request("POST", "/api/news/refresh", {})
        self.assertEqual(code, 200)
        self.assertFalse(unavailable["confirmed"])
        self.assertIn("403", unavailable["last_error"])
        result = self.setup_plan({"news": {"confirmed": False, "source": "", "events": []}}, explicit=True)
        self.assertEqual(result["context"]["news_state"], "unknown")
        self.assertEqual(result["status"], "blocked")

    def test_empty_unconfirmed_ui_news_uses_current_provider_snapshot_but_keeps_original_disk_payload(self):
        self.refresh()
        manual = {"macro_cycle": "unknown", "news": {"confirmed": False, "source": "", "observed_at": None, "events": []}}
        result = self.setup_plan(manual, explicit=True)
        self.assertEqual(result["context"]["news_state"], "blackout")
        self.assertEqual(result["context"]["sources"]["news"], SOURCE_URL)
        self.assertEqual(json.loads(self.context_path.read_text()), manual)

    def test_fresh_calendar_without_high_blackout_allows_paper_review_but_never_orders(self):
        self.refresh(impact="Medium")
        result = self.setup_plan()
        self.assertEqual(result["context"]["news_state"], "checked_no_blackout")
        self.assertEqual(result["status"], "paper_review")
        self.assertTrue(result["planning_only"])
        self.assertFalse(result["can_trade"])

    def test_six_hour_ttl_is_exact_and_stale_cache_never_implicitly_clears_news(self):
        self.refresh(impact="Medium")
        FrozenDateTime.current += timedelta(hours=6)
        code, boundary, _ = self.request("GET", "/api/news/status")
        self.assertEqual(code, 200)
        self.assertTrue(boundary["confirmed"])
        FrozenDateTime.current += timedelta(seconds=1)
        before = self.app.news.path.read_bytes()
        code, expired, _ = self.request("GET", "/api/news/status")
        self.assertEqual(code, 200)
        self.assertFalse(expired["confirmed"])
        self.assertEqual(expired["state"], "stale")
        result = self.setup_plan()
        self.assertEqual(result["context"]["news_state"], "unknown")
        self.assertEqual(result["context"]["news_events"], [])
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(self.transport.call_count, 1)
        self.assertEqual(self.app.news.path.read_bytes(), before)

    def test_confirmed_manual_calendar_overrides_provider_and_persists_original_review(self):
        self.refresh()
        manual = {"macro_cycle": "slowdown", "macro_source": "Explicit manual review",
                  "news": {"confirmed": True, "source": "Manual official calendar review",
                           "observed_at": "2026-10-01T12:14:00Z", "events": []}}
        result = self.setup_plan(manual, explicit=True)
        self.assertEqual(result["context"]["news_state"], "checked_no_blackout")
        self.assertEqual(result["context"]["sources"]["news"], manual["news"]["source"])
        self.assertEqual(result["status"], "paper_review")
        self.assertEqual(json.loads(self.context_path.read_text()), manual)
        code, reused, _ = self.request("POST", "/api/setups", {})
        self.assertEqual(code, 200)
        self.assertEqual(reused["context"]["sources"]["news"], manual["news"]["source"])
        self.assertEqual(self.transport.call_count, 1)

    def test_previous_provider_tagged_context_is_replaced_from_cache_and_not_a_permanent_confirmation(self):
        self.refresh(impact="Medium")
        previous = {"news": self.app.news.context()}
        result = self.setup_plan(previous, explicit=True)
        self.assertEqual(result["context"]["news_state"], "checked_no_blackout")
        original = self.context_path.read_bytes()
        FrozenDateTime.current += timedelta(hours=6, seconds=1)
        result = self.setup_plan()
        self.assertEqual(result["context"]["news_state"], "unknown")
        self.assertEqual(result["context"]["news_events"], [])
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(self.context_path.read_bytes(), original)

    def test_malformed_refresh_and_manual_calendar_do_not_fetch_or_overwrite_saved_context(self):
        self.app.store.save_research(snapshot())
        for payload in ({"force": True}, {"url": "https://private.example"}, [], "refresh", None):
            with self.subTest(payload=payload):
                code, error, _ = self.request("POST", "/api/news/refresh", payload)
                self.assertEqual(code, 400, error)
        self.transport.assert_not_called()
        self.context_path.write_text(json.dumps({"macro_cycle": "unknown"}))
        before = self.context_path.read_bytes()
        invalid = [{"news": []}, {"news": {"confirmed": 1}}, {"news": {"confirmed": "yes"}},
                   {"news": {"confirmed": False, "events": "invalid"}},
                   {"news": {"confirmed": False, "source": "", "events": {}}},
                   {"news": {"confirmed": False, "source": [], "events": []}},
                   {"news": {"confirmed": False, "source": "", "events": 0}},
                   {"news": {"confirmed": False, "source": "", "events": [], "observed_at": "bad"}}]
        for context in invalid:
            with self.subTest(context=context):
                code, error, _ = self.request("POST", "/api/setups", {"context": context})
                self.assertEqual(code, 400, error)
                self.assertEqual(self.context_path.read_bytes(), before)
        self.transport.assert_not_called()

    def test_yahoo_quote_loading_and_primary_adoption_continue_when_news_is_unavailable(self):
        bars = parse_csv((ROOT / "data" / "market-history" / "AAPL-1d.csv").read_text())[:320]
        wire_fixture = {"bars": bars, "provenance": {"provider": "Offline transport fixture", "quote_currency": "USD", "warnings": []}}
        report = snapshot()
        report["selected_strategy"] = None
        report["data"].update(symbol="AAPL", timeframe_minutes=1440)
        report["summary"].update(status="no_qualified_strategy")
        result = {"primary_symbol": "AAPL", "selected_symbol": None,
                  "markets": [{"symbol": "AAPL", "primary": True, "qualified": False,
                               "selected": False, "report": report}], "planning_only": True, "live_orders": False}
        with patch("propdesk.feeds.get_history", side_effect=lambda *_args, **_kwargs: deepcopy(wire_fixture)) as quotes, \
                patch("propdesk.scanner.scan", return_value=deepcopy(result)):
            code, started, _ = self.request("POST", "/api/autopilot", {"action": "run"})
            self.assertEqual(code, 202, started)
            job = self.wait_job(started["job_id"])
            self.assertEqual(job["state"], "completed", job)
            completed = self.app.autopilot.tick()
        self.assertEqual(quotes.call_count, 8)
        self.assertEqual(self.transport.call_count, 1)
        self.assertEqual(job["result"]["market_count"], 8)
        self.assertTrue(completed["result_ready"])
        saved = self.app.store.latest_research()
        self.assertEqual(saved["autopilot_job_id"], started["job_id"])
        self.assertIsNone(saved["selected_strategy"])
        code, plan, _ = self.request("POST", "/api/setups", {})
        self.assertEqual(code, 200)
        self.assertEqual(plan["context"]["news_state"], "unknown")
        self.assertEqual(plan["status"], "blocked")
        self.assertFalse(self.app.news.path.exists())

    def test_reference_scanner_does_not_refresh_public_calendar(self):
        with patch("propdesk.scanner.scan", return_value={"primary_symbol": None, "selected_symbol": None, "markets": []}), \
                patch("propdesk.feeds.get_history") as quotes:
            code, started, _ = self.request("POST", "/api/scanner/jobs", {"source": "reference", "symbols": ["AAPL"]})
            self.assertEqual(code, 202, started)
            job = self.wait_job(started["id"])
        self.assertEqual(job["state"], "completed")
        self.assertEqual(job["result"]["source"], "reference")
        self.transport.assert_not_called()
        quotes.assert_not_called()


if __name__ == "__main__":
    unittest.main()
