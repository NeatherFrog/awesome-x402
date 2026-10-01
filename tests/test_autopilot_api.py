"""Local HTTP integration for autonomous research; no external market requests."""
from __future__ import annotations

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

from propdesk.server import Application, RESEARCH_LOCK, make_handler


class AutopilotAPITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.apps = []
        self.environment = patch.dict(os.environ, {"TRADING_SUPERVISED": "0", "TRADING_AUTOPILOT_DEFAULT": "0"})
        self.environment.start()
        self.calendar_transport = patch("propdesk.news._fetch", side_effect=ValueError("Controlled calendar transport unavailable"))
        self.calendar_transport.start()
        self.app = Application(self.temp.name)
        self.apps.append(self.app)
        handler = make_handler(self.app)
        handler.log_message = lambda *_args: None
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": .01}, daemon=True)
        self.thread.start()
        self.release_events = []

    def tearDown(self):
        for event in self.release_events:
            event.set()
        for app in self.apps:
            app.autopilot.stop()
            deadline = time.monotonic() + 5
            while app.scanner.busy and time.monotonic() < deadline:
                time.sleep(.01)
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.calendar_transport.stop()
        self.environment.stop()
        self.temp.cleanup()

    def request(self, method="GET", payload=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        body = json.dumps(payload).encode() if payload is not None else None
        headers = {"Content-Type": "application/json"} if body is not None else {}
        try:
            connection.request(method, "/api/autopilot", body=body, headers=headers)
            response = connection.getresponse()
            result = json.loads(response.read(), parse_constant=lambda value: self.fail("Nonfinite HTTP result: " + value))
            return response.status, result, dict(response.getheaders())
        finally:
            connection.close()

    def wait_scan(self, identifier):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            job = self.app.scanner.get(identifier)
            if job["state"] in ("completed", "failed", "interrupted"):
                return job
            time.sleep(.01)
        self.fail("Local scanner worker did not complete")

    def test_development_default_get_is_readonly_disabled_and_does_not_start_threads(self):
        before = self.app.autopilot.state_path.read_bytes()
        with patch("propdesk.feeds.get_history") as fetch:
            code, status, headers = self.request()
        self.assertEqual(code, 200)
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertFalse(status["enabled"])
        self.assertFalse(status["thread_active"])
        self.assertFalse(status["running"])
        self.assertFalse(status["live_orders"])
        self.assertTrue(status["planning_only"])
        self.assertEqual(status["settings"]["source"], "yahoo")
        self.assertEqual(self.app.autopilot.state_path.read_bytes(), before)
        fetch.assert_not_called()

    def test_enable_disable_and_settings_persist_without_implicitly_starting_embedded_app(self):
        with patch("propdesk.feeds.get_history") as fetch:
            code, enabled, _ = self.request("POST", {"enabled": True, "settings": {"symbols": ["aapl"], "range": "1y"}})
            self.assertEqual(code, 200, enabled)
            self.assertTrue(enabled["enabled"])
            self.assertFalse(enabled["running"])
            self.assertEqual(enabled["settings"]["symbols"], ["AAPL"])
            code, disabled, _ = self.request("POST", {"enabled": False})
            self.assertEqual(code, 200)
            self.assertFalse(disabled["enabled"])
        persisted = json.loads(self.app.autopilot.state_path.read_text())
        self.assertFalse(persisted["enabled"])
        self.assertEqual(persisted["settings"]["range"], "1y")
        fetch.assert_not_called()

    def test_malformed_requests_and_secret_keys_reject_without_state_changes(self):
        before = self.app.autopilot.state_path.read_bytes()
        invalid = [{"enabled": 1}, {"action": "unknown"}, {"action": "run", "token": "private"},
                   {"settings": {"source": "demo"}}, {"settings": {"symbols": ["https://private.example"]}},
                   {"settings": {"config": {"fee_bps": float("inf")}}},
                   {"settings": {"config": {"password": "private"}}}, {"settings": {"range": "max"}}]
        with patch("propdesk.feeds.get_history") as fetch:
            for payload in invalid:
                with self.subTest(payload=payload):
                    code, result, _ = self.request("POST", payload)
                    self.assertEqual(code, 400, result)
                    self.assertNotIn("private.example", result["error"])
                    self.assertEqual(self.app.autopilot.state_path.read_bytes(), before)
        fetch.assert_not_called()

    def test_manual_run_all_provider_errors_complete_without_demo_or_saved_research(self):
        with patch("propdesk.feeds.get_history", side_effect=ValueError("Controlled HTTP 403")) as fetch:
            code, started, _ = self.request("POST", {"action": "run"})
            self.assertEqual(code, 202, started)
            self.assertIsNotNone(started["job_id"])
            job = self.wait_scan(started["job_id"])
            self.app.autopilot.tick()
        code, status, _ = self.request()
        self.assertEqual(code, 200)
        self.assertFalse(status["enabled"])
        self.assertFalse(status["running"])
        self.assertFalse(status["result_ready"])
        self.assertEqual(status["failure_count"], 1)
        self.assertIn("демо не подставляется", status["last_error"])
        self.assertEqual(fetch.call_count, 8)
        self.assertEqual(job["result"]["markets"], [])
        self.assertEqual(len(job["result"]["fetch_errors"]), 8)
        self.assertIsNone(self.app.store.latest_research())

    def test_busy_research_lock_defers_and_retains_manual_request_without_consuming_attempt(self):
        with patch("propdesk.feeds.get_history", side_effect=ValueError("Controlled provider denial")) as fetch:
            RESEARCH_LOCK.acquire()
            try:
                code, waiting, _ = self.request("POST", {"action": "run"})
                self.assertEqual(code, 202, waiting)
                self.assertEqual(waiting["state"], "waiting_for_idle")
                self.assertTrue(waiting["manual_requested"])
                self.assertIsNone(waiting["last_attempt_at"])
                self.assertIsNone(waiting["job_id"])
                fetch.assert_not_called()
            finally:
                RESEARCH_LOCK.release()
            started = self.app.autopilot.tick()
            self.assertIsNotNone(started["job_id"])
            self.wait_scan(started["job_id"])
            self.app.autopilot.tick()
        self.assertEqual(fetch.call_count, 8)

    def test_busy_race_in_start_adapter_defers_instead_of_consuming_daily_attempt(self):
        RESEARCH_LOCK.acquire()
        try:
            with patch.object(self.app.autopilot, "can_start", return_value=True), patch("propdesk.feeds.get_history") as fetch:
                code, waiting, _ = self.request("POST", {"action": "run"})
                self.assertEqual(code, 202, waiting)
                self.assertEqual(waiting["state"], "waiting_for_idle")
                self.assertIsNone(waiting["last_attempt_at"])
                self.assertTrue(waiting["manual_requested"])
                self.assertEqual(waiting["failure_count"], 0)
                fetch.assert_not_called()
        finally:
            RESEARCH_LOCK.release()

    def test_supervised_package_first_run_defaults_enabled_but_persisted_disable_wins(self):
        directory = Path(self.temp.name) / "packaged"
        with patch.dict(os.environ, {"TRADING_SUPERVISED": "1", "TRADING_AUTOPILOT_DEFAULT": ""}), \
                patch("propdesk.updater.Updater") as updater:
            updater.return_value.status.return_value = {"mode": "package", "current_commit": "f" * 40}
            app = Application(directory)
            self.apps.append(app)
            self.assertTrue(app.autopilot.status()["enabled"])
            self.assertFalse(app.autopilot.status()["thread_active"])
            app.autopilot.configure({"enabled": False})
            restarted = Application(directory)
            self.apps.append(restarted)
            self.assertFalse(restarted.autopilot.status()["enabled"])

    def test_unsupervised_package_default_and_explicit_environment_override(self):
        with patch("propdesk.updater.Updater") as updater:
            updater.return_value.status.return_value = {"mode": "package", "current_commit": "f" * 40}
            with patch.dict(os.environ, {"TRADING_SUPERVISED": "0", "TRADING_AUTOPILOT_DEFAULT": ""}):
                app = Application(Path(self.temp.name) / "unsupervised")
                self.apps.append(app)
                self.assertFalse(app.autopilot.status()["enabled"])
            with patch.dict(os.environ, {"TRADING_SUPERVISED": "1", "TRADING_AUTOPILOT_DEFAULT": "0"}):
                app = Application(Path(self.temp.name) / "override")
                self.apps.append(app)
                self.assertFalse(app.autopilot.status()["enabled"])

    def test_completed_job_adopts_only_primary_report_preserving_no_selected_strategy(self):
        primary_report = {"symbol": "AAPL", "selected_strategy": None, "strategies": [],
                          "data": {"source": "csv"}, "decision": "No qualified primary candidate"}
        diagnostic_report = {"symbol": "MSFT", "selected_strategy": "diagnostic-only", "strategies": []}
        def worker(payload, progress):
            return {"primary_symbol": "AAPL", "selected_symbol": None,
                    "markets": [{"symbol": "AAPL", "primary": True, "qualified": False,
                                 "selected": False, "report": primary_report},
                                {"symbol": "MSFT", "primary": False, "qualified": True,
                                 "selected": False, "report": diagnostic_report}],
                    "planning_only": True, "live_orders": False}
        self.app.scanner.worker = worker
        with patch("propdesk.feeds.get_history") as fetch:
            code, started, _ = self.request("POST", {"action": "run"})
            self.assertEqual(code, 202, started)
            self.wait_scan(started["job_id"])
            completed = self.app.autopilot.tick()
            saved = self.app.store.latest_research()
            self.assertEqual(saved["symbol"], "AAPL")
            self.assertIsNone(saved["selected_strategy"])
            self.assertEqual(saved["autopilot_job_id"], started["job_id"])
            self.assertEqual(saved["automation"], "research_only")
            self.assertIsNone(completed["selected_symbol"])
            self.assertEqual(completed["qualified_count"], 1)
            self.assertTrue(completed["result_ready"])
            saved_id = saved["research_id"]
            self.app.auto_scan_result(started["job_id"])
            self.assertEqual(self.app.store.latest_research()["research_id"], saved_id)
        fetch.assert_not_called()

    def test_active_job_blocks_settings_change_and_repeated_manual_start(self):
        entered, release = threading.Event(), threading.Event()
        self.release_events.append(release)
        def worker(payload, progress):
            entered.set()
            if not release.wait(3):
                raise ValueError("Controlled worker timed out")
            return {"markets": [], "fetch_errors": [], "planning_only": True, "live_orders": False}
        self.app.scanner.worker = worker
        code, first, _ = self.request("POST", {"action": "run"})
        self.assertEqual(code, 202)
        self.assertTrue(entered.wait(1))
        code, second, _ = self.request("POST", {"action": "run"})
        self.assertEqual(code, 202)
        self.assertEqual(second["job_id"], first["job_id"])
        code, error, _ = self.request("POST", {"settings": {"symbols": ["MSFT"]}})
        self.assertEqual(code, 400, error)
        self.assertIn("завершения", error["error"])
        self.assertEqual(self.app.scanner.latest()["id"], first["job_id"])
        release.set()
        self.wait_scan(first["job_id"])
        self.app.autopilot.tick()


if __name__ == "__main__":
    unittest.main()
