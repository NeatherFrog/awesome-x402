"""Independent scanner HTTP integration; offline archives and transport fixtures."""
from __future__ import annotations

import copy
import http.client
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch
from http.server import ThreadingHTTPServer

from propdesk.server import Application, ROOT, RESEARCH_LOCK, make_handler
from propdesk.market import parse_csv


class ScannerAPITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.app = Application(self.temp.name)
        handler = make_handler(self.app)
        handler.log_message = lambda *_args: None
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       kwargs={"poll_interval": .01}, daemon=True)
        self.thread.start()
        self.release_events = []

    def tearDown(self):
        for event in self.release_events:
            event.set()
        deadline = time.monotonic() + 5
        while self.app.scanner.busy and time.monotonic() < deadline:
            time.sleep(.01)
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temp.cleanup()

    def request(self, method, path, payload=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=30)
        body = json.dumps(payload).encode() if payload is not None else None
        supplied = dict(headers or {})
        if body is not None:
            supplied.setdefault("Content-Type", "application/json")
        try:
            connection.request(method, path, body=body, headers=supplied)
            response = connection.getresponse()
            status = response.status
            result = json.loads(response.read(), parse_constant=lambda value: self.fail("Nonfinite API JSON: " + value))
            return status, result, dict(response.getheaders())
        finally:
            connection.close()

    def wait_job(self, identifier, timeout=15):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            status, record, _ = self.request("GET", "/api/scanner/jobs/" + identifier)
            self.assertEqual(status, 200, record)
            if record["state"] in ("completed", "failed", "interrupted"):
                return record
            time.sleep(.01)
        self.fail("Background scanner did not finish within bounded test deadline")

    def run_job(self, payload):
        status, created, headers = self.request("POST", "/api/scanner/jobs", payload)
        self.assertEqual(status, 202, created)
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertIn(created["state"], ("queued", "running"))
        record = self.wait_job(created["id"])
        self.assertEqual(record["state"], "completed", record)
        self.assertIsNone(record["error"])
        return record

    def controlled_worker(self, *, hold_research_lock=False):
        entered, release = threading.Event(), threading.Event()
        self.release_events.append(release)

        def run(payload, progress):
            if hold_research_lock:
                RESEARCH_LOCK.acquire()
            try:
                progress("controlled_running", {"symbols": payload["symbols"]})
                entered.set()
                if not release.wait(5):
                    raise ValueError("Controlled test worker was not released")
                return {"markets": [], "planning_only": True, "live_orders": False}
            finally:
                if hold_research_lock:
                    RESEARCH_LOCK.release()
        self.app.scanner.worker = run
        status, created, _ = self.request("POST", "/api/scanner/jobs", {"source": "reference", "symbols": ["AAPL"]})
        self.assertEqual(status, 202, created)
        self.assertTrue(entered.wait(2))
        return created, release

    def test_empty_latest_invalid_missing_and_pathlike_job_ids(self):
        status, latest, _ = self.request("GET", "/api/scanner/jobs/latest")
        self.assertEqual(status, 200)
        self.assertIsNone(latest["job"])
        for identifier in ("not-a-uuid", "..", "%2e%2e", "a" * 32):
            with self.subTest(identifier=identifier):
                status, result, _ = self.request("GET", "/api/scanner/jobs/" + identifier)
                self.assertEqual(status, 400, result)
                self.assertIn("error", result)
                self.assertNotIn(self.temp.name, result["error"])

    def test_payload_validation_rejects_demo_urls_unknown_archives_and_bad_bounds(self):
        invalid = [
            {"source": "demo"}, {"source": "reference", "symbols": []},
            {"symbols": ["AAPL"] * 13}, {"symbols": "AAPL"},
            {"symbols": ["https://evil.example/secret"]},
            {"source": "reference", "symbols": ["EURUSD"]},
            {"source": "reference", "profile_id": "missing"},
            {"source": "reference", "config": []},
            {"source": "reference", "config": {"risk_pct": 2}},
            {"source": "reference", "config": {"fee_bps": -1}},
            {"interval": "15m", "range": "3mo"},
        ]
        with patch("propdesk.feeds.get_history") as fetch:
            for payload in invalid:
                with self.subTest(payload=payload):
                    status, result, _ = self.request("POST", "/api/scanner/jobs", payload)
                    self.assertEqual(status, 400, result)
            fetch.assert_not_called()
        self.assertFalse(self.app.scanner.busy)
        self.assertIsNone(self.app.scanner.latest())

    def test_default_yahoo_errors_complete_explicitly_without_demo_fallback(self):
        with patch("propdesk.feeds.get_history", side_effect=ValueError("Сеть отклонила историю (HTTP 403)")) as fetch:
            job = self.run_job({})
        result = job["result"]
        self.assertEqual(fetch.call_count, 8)
        self.assertEqual(result["source"], "yahoo")
        self.assertEqual(result["market_count"], 0)
        self.assertEqual(len(result["fetch_errors"]), 8)
        self.assertEqual(result["markets"], [])
        self.assertIsNone(result["primary_symbol"])
        self.assertIsNone(result["selected_symbol"])
        self.assertFalse(result["live_orders"])
        self.assertTrue(result["planning_only"])
        self.assertIsNone(self.app.store.latest_research())
        self.assertTrue(all("403" in item["error"] for item in result["fetch_errors"]))

    def test_reference_default_four_markets_returns_only_train_locked_diagnostics(self):
        with patch("propdesk.feeds.get_history") as fetch:
            job = self.run_job({"source": "reference"})
            fetch.assert_not_called()
        result = job["result"]
        self.assertEqual(result["market_count"], 4)
        self.assertEqual(result["fetch_errors"], [])
        self.assertLessEqual(len(result["markets"]), 3)
        self.assertGreaterEqual(len(result["markets"]), 1)
        self.assertEqual(len(result["training_lock"]["training_results"]), 4)
        self.assertEqual(result["primary_symbol"], result["training_lock"]["primary_symbol"])
        self.assertRegex(result["training_lock_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(result["source"], "reference")
        self.assertTrue(result["planning_only"])
        self.assertFalse(result["live_orders"])
        for market in result["markets"]:
            report = market["report"]
            self.assertTrue(report["archived"])
            self.assertEqual(report["data"]["source"], "csv")
            self.assertEqual(report["data"]["input_source"], "reference")
            self.assertEqual(report["config"]["fee_bps"], 2)
            self.assertEqual(report["config"]["slippage_bps"], 1)
            self.assertEqual(report["config"]["spread_bps"], 1)
            self.assertEqual(report["config"]["train_fraction"], .6)
            self.assertIn("last_bar", report["market_context"])
            self.assertIn("payout", report)
            if not market["primary"]:
                self.assertIsNone(report["selected_strategy"])
                self.assertFalse(market["selected"])
        status, latest, _ = self.request("GET", "/api/scanner/jobs/latest")
        self.assertEqual(status, 200)
        self.assertEqual(latest["job"]["id"], job["id"])
        self.assertEqual(latest["job"]["state"], "completed")

    def test_disjoint_goog_archive_is_excluded_before_ranking_and_can_be_scanned_alone(self):
        job = self.run_job({"source": "reference", "symbols": ["AAPL", "GOOG"]})
        result = job["result"]
        self.assertEqual(result["market_count"], 1)
        self.assertEqual(result["primary_symbol"], "AAPL")
        self.assertEqual([item["symbol"] for item in result["markets"]], ["AAPL"])
        self.assertEqual([item["symbol"] for item in result["training_lock"]["training_results"]], ["AAPL"])
        self.assertEqual(len(result["fetch_errors"]), 1)
        self.assertEqual(result["fetch_errors"][0]["symbol"], "GOOG")
        self.assertIn("2004–2013", result["fetch_errors"][0]["error"])
        self.assertIn("2015–2018", result["fetch_errors"][0]["error"])
        standalone = self.run_job({"source": "reference", "symbols": ["GOOG"]})["result"]
        self.assertEqual(standalone["market_count"], 1)
        self.assertEqual(standalone["primary_symbol"], "GOOG")
        self.assertEqual(standalone["fetch_errors"], [])
        self.assertEqual(standalone["markets"][0]["report"]["data"]["end"], "2013-03-01T00:00:00Z")

    def test_training_lock_is_persisted_before_any_holdout_runner_receives_full_data(self):
        from propdesk import backtest
        original = backtest.run_research
        observed = []

        def check_before_holdout(*args, **kwargs):
            record = self.app.scanner.latest()
            self.assertEqual(record["state"], "running")
            frozen = record["progress"]["details"]["training_lock"]
            lock = frozen.get("training_lock", frozen)
            self.assertLessEqual(len(lock["candidates"]), 3)
            self.assertIn("primary_symbol", lock)
            self.assertNotIn("test_metrics", json.dumps(lock))
            observed.append(copy.deepcopy(lock))
            return original(*args, **kwargs)
        with patch("propdesk.scanner.backtest.run_research", side_effect=check_before_holdout):
            job = self.run_job({"source": "reference"})
        self.assertEqual(len(observed), len(job["result"]["markets"]))
        self.assertTrue(observed)
        self.assertTrue(all(lock == observed[0] for lock in observed))

    def test_using_nonprimary_scan_report_saves_it_as_stale_research_with_currency_context(self):
        job = self.run_job({"source": "reference"})
        nonprimary = next(item for item in job["result"]["markets"] if not item["primary"])
        status, report, _ = self.request("POST", "/api/scanner/use", {"job_id": job["id"], "symbol": nonprimary["symbol"]})
        self.assertEqual(status, 200, report)
        self.assertRegex(report["research_id"], r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
        self.assertIsNone(report["selected_strategy"])
        self.assertEqual(report["market_context"]["quote_currency"], "USD")
        self.assertEqual(report["market_context"]["account_currency"], "USD")
        self.assertIn("last_bar", report["market_context"])
        self.assertTrue(report["archived"])
        status, latest, _ = self.request("GET", "/api/research/latest")
        self.assertEqual(status, 200)
        self.assertEqual(latest["research"]["research_id"], report["research_id"])
        self.assertEqual(latest["research"]["data"]["symbol"], nonprimary["symbol"])
        status, setup, _ = self.request("POST", "/api/setups", {})
        self.assertEqual(status, 200, setup)
        self.assertEqual(setup["status"], "blocked")
        self.assertFalse(setup["can_trade"])

    def test_yahoo_fixture_retains_provenance_and_excludes_incompatible_quote_currency(self):
        bars = parse_csv((ROOT / "data/market-history/AAPL-1d.csv").read_text())

        def history(symbol, **kwargs):
            return {"bars": bars, "provenance": {"provider": "Yahoo Chart fixture", "source": "csv",
                    "quote_currency": "JPY" if symbol == "USDJPY" else "USD", "warnings": ["Fixture-only archived quotes"]}}
        with patch("propdesk.feeds.get_history", side_effect=history) as fetch:
            job = self.run_job({"symbols": ["AAPL", "USDJPY"]})
        result = job["result"]
        self.assertEqual(fetch.call_count, 2)
        self.assertEqual(result["market_count"], 2)
        self.assertEqual(len(result["markets"]), 1)
        self.assertEqual(result["markets"][0]["symbol"], "AAPL")
        exclusion = next(item for item in result["exclusions"] if item["symbol"] == "USDJPY")
        self.assertEqual(exclusion["status"], "needs_currency_conversion")
        report = result["markets"][0]["report"]
        self.assertEqual(report["data"]["input_source"], "yahoo")
        self.assertEqual(report["data"]["provenance"]["quote_currency"], "USD")
        self.assertEqual(report["market_context"]["quote_currency"], "USD")

    def test_use_rejects_unknown_symbol_or_missing_job_and_running_job(self):
        for payload in ({"job_id": "missing", "symbol": "AAPL"}, {"job_id": "a" * 32, "symbol": "AAPL"}):
            status, result, _ = self.request("POST", "/api/scanner/use", payload)
            self.assertEqual(status, 400, result)
        created, release = self.controlled_worker()
        status, result, _ = self.request("POST", "/api/scanner/use", {"job_id": created["id"], "symbol": "AAPL"})
        self.assertEqual(status, 400, result)
        release.set()
        completed = self.wait_job(created["id"])
        self.assertEqual(completed["state"], "completed")
        status, result, _ = self.request("POST", "/api/scanner/use", {"job_id": created["id"], "symbol": "EURUSD"})
        self.assertEqual(status, 400, result)

    def test_active_worker_blocks_other_scans_research_and_update_application(self):
        created, release = self.controlled_worker(hold_research_lock=True)
        status, result, _ = self.request("POST", "/api/scanner/jobs", {"source": "reference"})
        self.assertEqual(status, 429, result)
        status, result, _ = self.request("POST", "/api/research", {"source": "demo"})
        self.assertEqual(status, 429, result)
        with patch.object(self.app.updater, "apply") as apply:
            status, result, _ = self.request("POST", "/api/updates/apply", {})
            self.assertEqual(status, 409, result)
            apply.assert_not_called()
        with patch.object(self.app.updater, "status", return_value={"busy": False, "can_apply": True}):
            status, update_status, _ = self.request("GET", "/api/updates/status")
        self.assertEqual(status, 200)
        self.assertFalse(update_status["can_apply"])
        self.assertIn("исследования", update_status["reason"])
        release.set()
        self.assertEqual(self.wait_job(created["id"])["state"], "completed")

    def test_job_busy_also_blocks_update_when_worker_does_not_hold_research_lock(self):
        created, release = self.controlled_worker()
        with patch.object(self.app.updater, "apply") as apply:
            status, result, _ = self.request("POST", "/api/updates/apply", {})
            self.assertEqual(status, 400, result)
            apply.assert_not_called()
        release.set()
        self.assertEqual(self.wait_job(created["id"])["state"], "completed")

    def test_request_secrets_and_unknown_parameters_are_discarded_before_worker_and_persistence(self):
        captured = []

        def worker(payload, progress):
            captured.append(payload)
            return {"markets": [], "planning_only": True, "live_orders": False}
        self.app.scanner.worker = worker
        secret = "scanner-test-only-secret"
        job = self.run_job({"source": "reference", "symbols": ["aapl", "AAPL"],
                            "token": secret, "password": secret,
                            "config": {"token": secret, "risk_pct": .25, "fee_bps": 10}})
        self.assertEqual(captured[0]["symbols"], ["AAPL"])
        encoded = json.dumps({"job": job, "payload": captured[0]})
        self.assertNotIn(secret, encoded)
        self.assertNotIn("password", encoded)
        for path in (Path(self.temp.name) / "scanner").glob("*.json"):
            self.assertNotIn(secret, path.read_text())


if __name__ == "__main__":
    unittest.main()
