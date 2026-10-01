"""Setup-first API: cached reads, causal admission, job reuse and durable audits."""
from copy import deepcopy
from datetime import datetime, timezone
import http.client
import hashlib
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch
from http.server import ThreadingHTTPServer
from uuid import uuid4

from propdesk.server import Application, ROOT, RESEARCH_LOCK, make_handler
from propdesk.trader import Trader

NOW = datetime(2026, 10, 1, 12, 5, tzinfo=timezone.utc)


class TraderAPITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Use an actual scanner-produced artifact so test_metrics/fold schema
        # drift cannot silently erase the strategy ledger.
        cls.actual = json.loads((ROOT / "docs/current-research.json").read_text(encoding="utf-8"))

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.app = Application(self.temp.name)
        self.app.news.refresh = Mock(return_value={"state": "unknown"})
        self.diary_warm = patch("propdesk.diary.warm_diary_quotes", return_value={"state": "unavailable"})
        self.diary_warm.start()
        handler = make_handler(self.app)
        handler.log_message = lambda *_args: None
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": .01}, daemon=True)
        self.thread.start()
        self.releases = []

    def tearDown(self):
        for event in self.releases:
            event.set()
        deadline = time.monotonic() + 5
        while self.app.scanner.busy and time.monotonic() < deadline:
            time.sleep(.01)
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.diary_warm.stop()
        self.temp.cleanup()

    def request(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        supplied = dict(headers or {})
        raw = None if body is None else json.dumps(body).encode()
        if body is not None:
            supplied.setdefault("Content-Type", "application/json")
        try:
            connection.request(method, path, body=raw, headers=supplied)
            response = connection.getresponse()
            return response.status, json.loads(response.read()), dict(response.getheaders())
        finally:
            connection.close()

    def wait(self, identifier):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            record = self.app.scanner.get(identifier)
            if record["state"] not in ("queued", "running"):
                return record
            time.sleep(.01)
        self.fail("Controlled background job did not finish")

    def board_fixture(self, *, qualified=True, diagnostic=False, stale=False, assumed=False):
        report = deepcopy(self.actual["reports"][0])
        candidate = report["strategies"][0]
        candidate.update(id="ema_pullback", eligible=qualified, training_winner=True,
                         rule_replay={"status": "pass"}, baseline=False)
        report.update(selected_strategy="ema_pullback" if qualified else None,
                      strategies=[candidate], archived=False, profile_id="verified")
        opening = "2026-09-30T11:00:00Z" if stale else "2026-10-01T11:00:00Z"
        report["data"] = {"source": "csv", "input_source": "yahoo", "symbol": "EURUSD", "timeframe_minutes": 60}
        report["latest_signal"] = {"direction": "long", "strategy_id": "ema_pullback", "regime": "trend",
                                   "reference_time": opening, "reference_price": 1.1, "stop": 1.0983, "target": 1.10306}
        report["market_context"] = {"last_bar": {"time": opening, "close": 1.1}, "atr14": .001,
                                    "timeframe_minutes": 60, "execution_assumptions": assumed}
        report["profile_rules"] = {"status": "user_verified", "news_allowed": True}
        market = {"symbol": "EURUSD", "primary": not diagnostic, "qualified": qualified,
                  "selected": qualified and not diagnostic, "strategy_id": "ema_pullback", "report": report}
        result = {"primary_symbol": "MES=F" if diagnostic else "EURUSD", "selected_symbol": "EURUSD" if qualified else None,
                  "selected_profile_id": "verified", "markets": [market], "market_count": 1,
                  "fetch_errors": [{"symbol": "XAUUSD", "error": "No quotes"}], "planning_only": True}
        job = {"id": str(uuid4()), "state": "completed", "result": result, "progress": {"stage": "completed"},
               "created_at": "2026-10-01T11:59:00Z", "updated_at": "2026-10-01T12:00:00Z"}
        auto = {"running": False, "settings": {"symbols": ["EURUSD", "XAUUSD"]}, "next_attempt_at": None}
        return job, auto

    def test_cached_get_never_starts_research_network_or_writes_journal(self):
        before = self.app.store.journal()
        with patch("propdesk.feeds.get_history") as prices, patch.object(self.app.autopilot, "run_now") as start:
            status, board, headers = self.request("GET", "/api/trader/board")
        self.assertEqual(status, 200)
        prices.assert_not_called()
        start.assert_not_called()
        self.assertEqual(board["setups"], [])
        self.assertFalse(board["live_orders"])
        self.assertFalse(board["coverage"]["universal"])
        self.assertEqual(len(board["markets"]), 8)
        self.assertEqual(board["attempts"]["count"], 0)
        self.assertEqual(self.app.store.journal(), before)
        self.assertEqual(headers["Cache-Control"], "no-store")

    def test_contract_assumptions_and_stale_prices_block_entry(self):
        for kwargs, expected in (({"assumed": True}, "Спецификация"), ({"stale": True}, "Котировки устарели")):
            job, auto = self.board_fixture(**kwargs)
            board = self.app.trader.board(job, auto, {}, now=NOW)
            self.assertEqual(board["setups"], [])
            self.assertEqual(board["status"], "no_trade")
            self.assertTrue(any(expected in reason for reason in board["markets"][0]["blockers"]))

    def test_qualified_fresh_verified_snapshot_is_paper_only_with_causal_levels(self):
        job, auto = self.board_fixture()
        board = self.app.trader.board(job, auto, {}, now=NOW)
        self.assertEqual(board["status"], "paper_review")
        self.assertEqual(len(board["setups"]), 1)
        plan = board["setups"][0]["setup"]
        self.assertEqual(plan["stop_loss"], 1.0983)
        self.assertEqual(plan["take_profit_zone"]["target"], 1.10306)
        self.assertEqual(plan["reference_close_time"], "2026-10-01T12:00:00Z")
        self.assertEqual(plan["expires_at"], "2026-10-01T13:00:00Z")
        self.assertFalse(plan["can_trade"])
        self.assertTrue(plan["planning_only"])

    def test_good_diagnostic_never_replaces_failed_primary(self):
        job, auto = self.board_fixture(diagnostic=True)
        board = self.app.trader.board(job, auto, {}, now=NOW)
        self.assertTrue(board["markets"][0]["historical_qualified"])
        self.assertFalse(board["markets"][0]["selected"])
        self.assertEqual(board["setups"], [])
        self.assertIn("диагностический", " ".join(board["markets"][0]["blockers"]))

    def test_failed_and_training_only_markets_remain_visible(self):
        job, auto = self.board_fixture(qualified=False)
        job["result"]["training_lock"] = {"training_results": [{"symbol": "EURUSD"}, {"symbol": "MSFT"}]}
        board = self.app.trader.board(job, auto, {}, now=NOW)
        by_symbol = {item["symbol"]: item for item in board["markets"]}
        self.assertEqual(by_symbol["XAUUSD"]["status"], "unavailable")
        self.assertEqual(by_symbol["MSFT"]["status"], "unqualified")
        self.assertIsNone(by_symbol["MSFT"]["setup"])
        self.assertEqual(board["coverage"]["scanned_count"], 2)
        self.assertEqual(board["coverage"]["failed_count"], 1)

    def test_find_button_queues_one_background_job_and_reuses_it(self):
        entered, release = threading.Event(), threading.Event()
        self.releases.append(release)
        calls = []
        def worker(payload, progress):
            calls.append(payload)
            entered.set()
            if not release.wait(5):
                raise ValueError("Controlled worker timed out")
            return {"markets": [], "fetch_errors": [], "live_orders": False}
        self.app.scan_markets = worker
        started = time.monotonic()
        status, first, _ = self.request("POST", "/api/trader/find-setups", {})
        self.assertEqual(status, 202, first)
        self.assertLess(time.monotonic() - started, 2)
        self.assertTrue(entered.wait(2))
        status, second, _ = self.request("POST", "/api/trader/find-setups", {})
        self.assertEqual(status, 202)
        self.assertTrue(second["reused"])
        self.assertEqual(first["job"]["id"], second["job"]["id"])
        self.assertEqual(len(calls), 1)
        release.set()
        self.assertEqual(self.wait(first["job"]["id"])["state"], "completed")
        self.assertEqual(self.app.trader.summary()["count"], 1)

    def test_persisted_automatic_search_warms_diary_before_market_research(self):
        self.app.autopilot.configure({"enabled": True})
        with patch.dict("os.environ", {"TRADING_AUTOPILOT_DEFAULT": "0"}):
            restored = Application(self.temp.name)
        self.assertTrue(restored.autopilot.status()["enabled"])
        self.assertTrue(restored._warm_diary_quotes)
        ordering = []
        restored.scan_markets = lambda *_args: ordering.append("scan") or {"markets": [], "fetch_errors": []}
        with patch("propdesk.diary.warm_diary_quotes", side_effect=lambda *_args, **_kwargs:
                   ordering.append("diary") or {"state": "ready"}) as warm:
            state = restored.autopilot.tick()
            identifier = state["job_id"]
            deadline = time.monotonic() + 5
            while restored.scanner.busy and time.monotonic() < deadline:
                time.sleep(.01)
            self.assertEqual(restored.scanner.get(identifier)["state"], "completed")
            warm.assert_called_once()
        self.assertEqual(ordering, ["diary", "scan"])

    def test_busy_lock_queues_request_without_duplicate_network(self):
        with patch("propdesk.feeds.get_history") as prices:
            RESEARCH_LOCK.acquire()
            try:
                status, response, _ = self.request("POST", "/api/trader/find-setups", {})
            finally:
                RESEARCH_LOCK.release()
        self.assertEqual(status, 202)
        self.assertTrue(response["queued"])
        self.assertTrue(response["automation"]["manual_requested"])
        self.assertIsNone(response["job"])
        prices.assert_not_called()

    def test_foreign_origin_host_and_arbitrary_strategy_inputs_are_rejected(self):
        with patch.object(self.app.autopilot, "run_now") as start:
            for body, headers, expected in (({}, {"Origin": "https://foreign.invalid"}, 403),
                                            ({}, {"Host": "foreign.invalid"}, 403),
                                            ({"symbols": ["../../secret"]}, {}, 400),
                                            ({"token": "do-not-store-me"}, {}, 400)):
                status, response, _ = self.request("POST", "/api/trader/find-setups", body, headers=headers)
                self.assertEqual(status, expected)
                self.assertNotIn("do-not-store-me", json.dumps(response))
            start.assert_not_called()
        self.assertEqual(self.app.trader.summary()["count"], 0)

    def test_update_maintenance_blocks_find_without_touching_ledger(self):
        with patch.object(self.app.updater, "status", return_value={"busy": True}), patch.object(self.app.autopilot, "run_now") as start:
            status, _, _ = self.request("POST", "/api/trader/find-setups", {})
        self.assertEqual(status, 503)
        start.assert_not_called()
        self.assertEqual(self.app.trader.summary()["count"], 0)

    def test_worker_failure_keeps_compact_attempt_without_sensitive_exception_text(self):
        self.app.scan_markets = Mock(side_effect=RuntimeError("secret-password-token=https://user:password@vendor.invalid"))
        status, queued, _ = self.request("POST", "/api/trader/find-setups", {})
        self.assertEqual(status, 202)
        job = self.wait(queued["job"]["id"])
        self.assertEqual(job["state"], "failed")
        audit = self.app.trader.attempt(job["id"])
        self.assertEqual(audit["state"], "failed")
        self.assertEqual(audit["error_type"], "RuntimeError")
        self.assertNotIn("password", json.dumps(audit))

    def test_actual_scanner_families_and_validation_survive_audit_without_raw_quotes(self):
        identifier = str(uuid4())
        request = {"source": "yahoo", "symbols": ["MES=F"], "interval": "1h", "range": "2y",
                   "profile_id": "example", "config": {"risk_pct": .25, "token": "not-persisted"}}
        self.app.trader.begin(identifier, request)
        lock = self.actual["result"]["training_lock"]
        self.app.trader.training_locked(identifier, {"training_lock": {"training_lock": lock,
            "training_lock_sha256": self.actual["training_lock_sha256"]}})
        self.app.trader.finish(identifier, self.actual["result"])
        audit = self.app.trader.attempt(identifier)
        self.assertGreaterEqual(len(audit["training"][0]["families"]), 7)
        self.assertGreaterEqual(len(audit["training"][0]["families"][0]["validation"]["folds"]), 2)
        first_market = self.actual["result"]["markets"][0]
        original = first_market["report"]["strategies"]
        recorded = audit["outcomes"][0]["families"]
        self.assertEqual(len(recorded), len(original))
        self.assertEqual(recorded[0]["metrics"]["net_return_pct"], original[0]["test_metrics"]["net_return_pct"])
        serialized = json.dumps(audit)
        self.assertNotIn("not-persisted", serialized)
        self.assertNotIn('"open"', serialized)
        self.assertNotIn('"trades"', serialized)
        self.assertNotIn('"equity_curve"', serialized)
        self.assertLess(len(serialized.encode()), 512 * 1024)
        with self.assertRaises(ValueError):
            self.app.trader.finish(identifier, {})

    def test_attempt_history_retained_restart_and_path_escape_rejected(self):
        identifiers = []
        for _ in range(3):
            identifier = str(uuid4())
            identifiers.append(identifier)
            self.app.trader.begin(identifier, {"config": {}, "symbols": ["EURUSD"]})
            self.app.trader.finish(identifier, {})
        restored = Trader(self.temp.name, ROOT)
        self.assertEqual(restored.summary()["count"], 3)
        self.assertTrue(all(restored.attempt(identifier)["state"] == "completed" for identifier in identifiers))
        self.assertEqual(len((restored.directory / "attempts.jsonl").read_text().splitlines()), 6)
        with self.assertRaises(ValueError):
            restored.begin("../../outside", {"config": {}})

    def test_restart_marks_abandoned_attempt_interrupted_and_preserves_index(self):
        identifier = str(uuid4())
        self.app.trader.begin(identifier, {"config": {}, "symbols": ["EURUSD"]})
        record = {"schema": 1, "id": identifier, "state": "running", "created_at": "2026-10-01T11:00:00Z",
                  "updated_at": "2026-10-01T11:00:00Z", "progress": {"stage": "loading", "details": {}},
                  "result": None, "error": None}
        self.app.scanner._save(record)
        restored = Application(self.temp.name)
        self.assertEqual(restored.scanner.get(identifier)["state"], "interrupted")
        self.assertEqual(restored.trader.attempt(identifier)["state"], "interrupted")
        self.assertEqual(restored.trader.attempt(identifier)["error_type"], "Interrupted")
        self.assertEqual(len((restored.trader.directory / "attempts.jsonl").read_text().splitlines()), 2)

    def test_local_audit_symlink_cannot_overwrite_another_file(self):
        identifier = str(uuid4())
        outside = Path(self.temp.name) / "preserve.json"
        outside.write_text('{"preserved":true}', encoding="utf-8")
        link = self.app.trader.attempts / (identifier + ".json")
        try:
            link.symlink_to(outside)
        except (OSError, NotImplementedError):
            self.skipTest("This host cannot create a symlink")
        with self.assertRaises(ValueError):
            self.app.trader.begin(identifier, {"config": {}})
        self.assertEqual(outside.read_text(encoding="utf-8"), '{"preserved":true}')

    def test_diary_get_is_read_only_and_unknown_query_is_rejected(self):
        before = self.app.store.journal()
        with patch("propdesk.feeds.get_history") as prices:
            status, diary, _ = self.request("GET", "/api/trader/diary?month=2026-09")
            self.assertEqual(status, 200)
            self.assertEqual(diary["mode"], "historical_replay")
            status, _, _ = self.request("GET", "/api/trader/diary?path=../../secret")
            self.assertEqual(status, 400)
            status, mean, _ = self.request("GET", "/api/trader/diary?study=mean_reversion&month=2026-09")
            self.assertEqual(status, 200)
            self.assertEqual(mean["study"], "mean_reversion")
            self.assertEqual(mean["strategy"]["id"], "rsi2_pullback_5")
            self.assertFalse(mean["live_orders"])
            for query in ("study=best_returns", "study=../../private", "study=mean_reversion&study=sourced_daily",
                          "study=", "study=mean_reversion&month=2026-09&month=2026-08"):
                status, _, _ = self.request("GET", "/api/trader/diary?" + query)
                self.assertEqual(status, 400, query)
            prices.assert_not_called()
        self.assertEqual(self.app.store.journal(), before)

    def test_bounded_attempt_listing_detail_and_download_are_read_only(self):
        identifiers = []
        for _ in range(3):
            identifier = str(uuid4())
            identifiers.append(identifier)
            self.app.trader.begin(identifier, {"source": "yahoo", "symbols": ["EURUSD"], "config": {}})
            self.app.trader.finish(identifier, {})
        before = (self.app.trader.directory / "attempts.jsonl").read_bytes()
        with patch.object(self.app.autopilot, "run_now") as start:
            status, listing, _ = self.request("GET", "/api/trader/attempts?limit=2")
            self.assertEqual(status, 200)
            self.assertEqual(len(listing["records"]), 2)
            self.assertEqual(listing["total_count"], 3)
            status, record, headers = self.request("GET", "/api/trader/attempts/" + identifiers[0] + "?download=1")
            self.assertEqual(status, 200)
            self.assertEqual(record["id"], identifiers[0])
            self.assertEqual(record["state"], "completed")
            self.assertIn(identifiers[0], headers["Content-Disposition"])
            start.assert_not_called()
        self.assertEqual((self.app.trader.directory / "attempts.jsonl").read_bytes(), before)

    def test_audit_api_rejects_unbounded_lists_paths_and_foreign_hosts(self):
        for path in ("/api/trader/attempts?limit=101", "/api/trader/attempts?limit=0",
                     "/api/trader/attempts?limit=-2", "/api/trader/attempts?limit=2&limit=3",
                     "/api/trader/attempts?token=secret", "/api/trader/attempts/../../etc/passwd",
                     "/api/trader/attempts/%2e%2e", "/api/trader/attempts/" + str(uuid4()) + "?path=secret"):
            status, _, _ = self.request("GET", path)
            self.assertEqual(status, 400, path)
        status, _, _ = self.request("GET", "/api/trader/attempts", headers={"Host": "foreign.invalid"})
        self.assertEqual(status, 403)

    def test_tampered_protocol_or_primary_lock_cannot_supply_positive_evidence(self):
        source = json.loads((ROOT / "docs/sourced-strategy-research.json").read_text(encoding="utf-8"))
        docs = Path(self.temp.name) / "evidence/docs"
        docs.mkdir(parents=True)
        path = docs / "sourced-strategy-research.json"
        reader = Trader(self.temp.name, docs.parent)
        for field in ("protocol", "training_lock"):
            damaged = deepcopy(source)
            damaged[field]["changed_after_freeze"] = True
            path.write_text(json.dumps(damaged), encoding="utf-8")
            evidence = reader.evidence()
            self.assertEqual(evidence["state"], "unavailable")
            self.assertIsNone(evidence["primary"])
            self.assertFalse(evidence["live_candidate"])

    def test_separate_studies_do_not_replace_daily_primary_and_reject_tampering(self):
        docs = Path(self.temp.name) / "evidence/docs"
        docs.mkdir(parents=True)
        daily = json.loads((ROOT / "docs/sourced-strategy-research.json").read_text(encoding="utf-8"))
        (docs / "sourced-strategy-research.json").write_text(json.dumps(daily), encoding="utf-8")
        protocol = {"rules": {"intraday_a": "Closed bar; next open; flatten daily"}, "symbols": ["MES=F"], "interval": "1h"}
        lock = {"primary_strategy_id": "intraday_a"}
        digest = lambda value: hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
        intraday = {"phase": "final_review", "protocol": protocol, "protocol_sha256": digest(protocol),
                    "training_lock": lock, "training_lock_sha256": digest(lock), "primary_strategy_id": "intraday_a",
                    "selected_strategy_id": "intraday_a", "strategies": [{"id": "intraday_a", "name": "Intraday fixture", "primary": True,
                    "eligible_historical_price_model": True, "windows": {"holdout": {"metrics": {"net_return_pct": 20},
                    "passes_window": True, "friction_stress": {"metrics": {"net_return_pct": 10}}}}}]}
        (docs / "intraday-research.json").write_text(json.dumps(intraday), encoding="utf-8")
        mean_protocol = {"rules": {"mean_reversion_a": "RSI closed bar; fixed exit; next open"}, "symbols": ["SPY"], "interval": "1d"}
        mean_lock = {"primary_strategy_id": "mean_reversion_a"}
        mean = {"phase": "final_review", "protocol": mean_protocol, "protocol_sha256": digest(mean_protocol),
                "training_lock": mean_lock, "training_lock_sha256": digest(mean_lock), "primary_strategy_id": "mean_reversion_a",
                "selected_strategy_id": "mean_reversion_a", "strategies": [{"id": "mean_reversion_a", "name": "Mean reversion fixture", "primary": True,
                "eligible_historical_price_model": True, "windows": {"historical_holdout": {"metrics": {"net_return_pct": 100}, "passes_window": True},
                "confirmation": {"metrics": {"net_return_pct": 200}, "passes_window": True}}}]}
        mean_path = docs / "mean-reversion-research.json"
        mean_path.write_text(json.dumps(mean), encoding="utf-8")
        reader = Trader(self.temp.name, docs.parent)
        evidence = reader.evidence()
        self.assertEqual(evidence["primary"]["id"], daily["training_lock"]["primary_strategy_id"])
        self.assertEqual(evidence["studies"][1]["primary"]["id"], "intraday_a")
        self.assertEqual(evidence["studies"][1]["primary"]["windows"]["holdout"]["friction_stress"]["net_return_pct"], 10)
        self.assertFalse(evidence["studies"][1]["live_candidate"])
        self.assertFalse(evidence["studies"][1]["primary"]["real_prop_qualified"])
        self.assertEqual(evidence["studies"][2]["id"], "mean_reversion")
        self.assertEqual(evidence["studies"][2]["primary"]["id"], "mean_reversion_a")
        self.assertEqual(set(evidence["studies"][2]["primary"]["windows"]), {"historical_holdout", "confirmation"})
        self.assertFalse(evidence["studies"][2]["live_candidate"])
        self.assertFalse(evidence["studies"][2]["primary"]["real_prop_qualified"])
        for field in ("protocol", "training_lock"):
            damaged = deepcopy(mean)
            damaged[field]["changed_after_freeze"] = True
            mean_path.write_text(json.dumps(damaged), encoding="utf-8")
            evidence = reader.evidence()
            self.assertEqual(evidence["studies"][2]["state"], "unavailable")
            self.assertIsNone(evidence["studies"][2]["primary"])
            self.assertFalse(evidence["studies"][2]["live_candidate"])
            self.assertEqual(evidence["primary"]["id"], daily["training_lock"]["primary_strategy_id"])


if __name__ == "__main__":
    unittest.main()
