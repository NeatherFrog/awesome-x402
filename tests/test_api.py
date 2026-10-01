"""Independent HTTP contract tests using only the Python standard library."""
import csv
import http.client
import io
import json
import os
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from propdesk.server import Application, make_handler
from propdesk.version import VERSION


class APITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.app = Application(self.temp.name)
        handler = make_handler(self.app)
        handler.log_message = lambda *_args: None
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
        self.thread.start()
        self.host = f"127.0.0.1:{self.server.server_port}"
        self.trade = {"symbol": "EURUSD", "side": "long", "entry": 1.1, "exit": 1.11,
                      "stop": 1.09, "quantity": 10000, "fees": 5,
                      "strategy": "=1+1", "notes": " @SUM(1,1)", "emotion": "+calm",
                      "opened_at": "2026-01-01T10:00:00Z", "closed_at": "2026-01-01T11:00:00Z",
                      "setup_followed": True}

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temp.cleanup()

    def request(self, method, path, payload=None, *, raw=None, headers=None):
        supplied_headers = dict(headers or {})
        if payload is not None:
            raw = json.dumps(payload, ensure_ascii=False).encode()
            supplied_headers.setdefault("Content-Type", "application/json")
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=30)
        try:
            connection.request(method, path, body=raw, headers=supplied_headers)
            response = connection.getresponse()
            data = response.read()
            status = response.status
            response_headers = dict(response.getheaders())
        finally:
            connection.close()
        if "application/json" in response_headers.get("Content-Type", ""):
            result = json.loads(data, parse_constant=lambda value: self.fail(f"Nonfinite JSON response: {value}"))
        else:
            result = data.decode("utf-8")
        return status, result, response_headers

    def test_health_bootstrap_and_empty_persistence(self):
        status, health, headers = self.request("GET", "/api/health")
        self.assertEqual(status, 200)
        self.assertTrue(health["ok"])
        self.assertEqual(health["mode"], "paper")
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(headers["X-Frame-Options"], "DENY")
        self.assertIn("default-src 'self'", headers["Content-Security-Policy"])
        with patch.dict(os.environ, {"TRADING_WEBHOOK_TOKEN": ""}):
            status, bootstrap, _ = self.request("GET", "/api/bootstrap")
        self.assertEqual(status, 200)
        self.assertEqual(bootstrap["mode"], "paper")
        self.assertEqual(bootstrap["symbols"], ["EURUSD", "XAUUSD", "NAS100", "BTCUSD"])
        self.assertGreaterEqual(len(bootstrap["strategies"]), 8)
        self.assertGreaterEqual(len(bootstrap["profiles"]), 3)
        self.assertFalse(bootstrap["account"]["confirmed_rules"])
        self.assertFalse(bootstrap["webhook_configured"])
        self.assertIsNone(bootstrap["latest_research"])
        self.assertEqual(bootstrap["version"], VERSION)
        self.assertEqual(bootstrap["journal"]["stats"]["total_trades"], 0)
        self.assertTrue(all(profile["status"] == "illustrative" for profile in bootstrap["profiles"]))

    def test_static_routes_cannot_expose_storage_or_checkout(self):
        for path in ("/.local/propdesk.sqlite3", "/.git/config", "/../propdesk/store.py",
                     "/%2e%2e/propdesk/store.py", "/static/../../.git/config", "/api/unknown"):
            with self.subTest(path=path):
                status, result, _ = self.request("GET", path)
                self.assertEqual(status, 404)
                self.assertIn("error", result)

    def test_foreign_hostname_cannot_read_local_journal(self):
        status, _, _ = self.request("GET", "/api/journal", headers={"Host": "foreign.example"})
        self.assertEqual(status, 403)
        with patch.dict(os.environ, {"TRADING_ALLOWED_HOSTS": "desk.example"}):
            status, data, _ = self.request("GET", "/api/health", headers={"Host": "desk.example"})
            self.assertEqual(status, 200)
            self.assertEqual(data["mode"], "paper")

    def test_reimporting_downloaded_demo_cannot_turn_it_into_market_evidence(self):
        status, csv_text, _ = self.request("GET", "/api/data/example")
        self.assertEqual(status, 200)
        status, result, _ = self.request("POST", "/api/research", {
            "source": "csv", "symbol": "EURUSD", "csv_text": csv_text,
        })
        self.assertEqual(status, 200)
        self.assertEqual(result["data"]["source"], "demo")
        self.assertEqual(result["data"]["input_source"], "csv")
        self.assertIsNone(result["selected_strategy"])
        self.assertTrue(all(not strategy["eligible"] for strategy in result["strategies"]))

    def test_mutations_reject_foreign_origin_and_accept_same_origin(self):
        status, _, _ = self.request("POST", "/api/journal", self.trade,
                                    headers={"Origin": "https://foreign.example"})
        self.assertEqual(status, 403)
        self.assertEqual(self.app.store.journal()["stats"]["total_trades"], 0)
        status, result, _ = self.request("POST", "/api/journal", self.trade,
                                         headers={"Origin": f"http://{self.host}"})
        self.assertEqual(status, 201)
        status, _, _ = self.request("DELETE", f"/api/journal/{result['trade']['id']}",
                                    headers={"Origin": "https://foreign.example"})
        self.assertEqual(status, 403)
        self.assertEqual(self.app.store.journal()["stats"]["total_trades"], 1)

    def test_malformed_json_types_content_type_and_nonfinite_rejected(self):
        for raw, content_type in ((b"{", "application/json"), (b"[]", "application/json"),
                                  (b"null", "application/json"), (b"{}", "text/plain"),
                                  (b'{"entry":NaN}', "application/json"),
                                  (b'{"entry":Infinity}', "application/json"),
                                  (b'{"entry":-Infinity}', "application/json"),
                                  (b"\xff", "application/json")):
            with self.subTest(raw=raw, content_type=content_type):
                status, result, _ = self.request("POST", "/api/journal", raw=raw,
                                                headers={"Content-Type": content_type})
                self.assertEqual(status, 400)
                self.assertIn("error", result)
        self.assertEqual(self.app.store.journal()["stats"]["total_trades"], 0)

    def test_journal_http_lifecycle_computation_provenance_and_safe_export(self):
        status, created, _ = self.request("POST", "/api/journal", self.trade)
        self.assertEqual(status, 201)
        recorded = created["trade"]
        self.assertEqual(recorded["mode"], "manual_journal")
        self.assertAlmostEqual(recorded["pnl"], 95)
        self.assertAlmostEqual(recorded["risk_amount"], 105)
        self.assertAlmostEqual(recorded["return_r"], 95 / 105, places=6)
        status, journal, _ = self.request("GET", "/api/journal")
        self.assertEqual(status, 200)
        self.assertEqual(journal["trades"][0]["id"], recorded["id"])
        self.assertEqual(journal["stats"]["total_trades"], 1)
        self.assertEqual(journal["stats"]["drawdown_basis"], "realized_journal_only")
        status, exported, headers = self.request("GET", "/api/journal/export")
        self.assertEqual(status, 200)
        self.assertIn("attachment", headers["Content-Disposition"])
        row = next(csv.DictReader(io.StringIO(exported)))
        self.assertEqual(row["strategy"], "'=1+1")
        self.assertEqual(row["notes"], "' @SUM(1,1)")
        self.assertEqual(row["emotion"], "'+calm")
        self.assertEqual(Application(self.temp.name).store.journal()["trades"][0]["id"], recorded["id"])
        status, deleted, _ = self.request("DELETE", f"/api/journal/{recorded['id']}")
        self.assertEqual(status, 200)
        self.assertTrue(deleted["ok"])
        self.assertEqual(deleted["stats"]["total_trades"], 0)
        self.assertEqual(self.request("DELETE", f"/api/journal/{recorded['id']}")[0], 404)

    def test_overflowing_derived_trade_values_do_not_poison_journal(self):
        status, result, _ = self.request("POST", "/api/journal", {
            **self.trade, "entry": 1e308, "exit": 1.6e308, "stop": 5e307, "quantity": 1e12})
        self.assertEqual(status, 400)
        self.assertIn("error", result)
        status, journal, _ = self.request("GET", "/api/journal")
        self.assertEqual(status, 200)
        self.assertEqual(journal["stats"]["total_trades"], 0)

    def test_profile_api_validates_and_persists_custom_rule_inputs(self):
        status, result, _ = self.request("POST", "/api/profiles", {
            "name": "My independent rules", "account_size": 20000, "daily_loss_pct": 3,
            "daily_reset_timezone": "Europe/Kyiv", "drawdown_type": "trailing_eod",
            "source_url": "https://example.test/rules", "status": "user_verified",
            "verified_at": "2026-10-01T10:00:00Z"})
        self.assertEqual(status, 200)
        profile = result["profile"]
        self.assertTrue(profile["id"].startswith("custom-"))
        self.assertEqual(profile["account_size"], 20000)
        self.assertEqual(profile["status"], "user_verified")
        status, result, _ = self.request("GET", "/api/profiles")
        self.assertEqual(status, 200)
        self.assertIn(profile, result["profiles"])
        self.assertEqual(Application(self.temp.name).profile(profile["id"]), profile)
        for bad in ({"daily_loss_pct": True}, {"account_size": "nan"},
                    {"daily_reset_timezone": "Missing/Timezone"}, {"ea_allowed": "true"}):
            with self.subTest(bad=bad):
                self.assertEqual(self.request("POST", "/api/profiles", bad)[0], 400)

    def test_checker_allows_sized_paper_proposal_and_blocks_drawdown(self):
        account = {"balance": 100000, "equity": 100000, "day_start_balance": 100000,
                   "day_start_equity": 100000, "high_water_equity": 100000, "confirmed_rules": True}
        trade = {"side": "long", "entry": 100, "stop": 99, "target": 102,
                 "risk_pct": 0.25, "spread_bps": 1, "fee_bps": 0.2, "slippage_bps": 0.5}
        status, result, _ = self.request("POST", "/api/check", {"account": account, "trade": trade})
        self.assertEqual(status, 200)
        self.assertTrue(result["allowed"])
        self.assertEqual(result["decision"], "ALLOW_PAPER")
        self.assertLessEqual(result["risk_amount"], result["effective_budget"])
        self.assertFalse(result["rule_checks"]["live_execution_authorized"])
        status, result, _ = self.request("POST", "/api/check", {
            "account": {**account, "balance": 94999, "equity": 94999}, "trade": trade})
        self.assertEqual(status, 200)
        self.assertFalse(result["allowed"])
        self.assertEqual(result["decision"], "BLOCK")
        self.assertTrue(result["reasons"])
        for invalid in ({"account": [], "trade": trade}, {"account": account, "trade": []}):
            self.assertEqual(self.request("POST", "/api/check", invalid)[0], 400)

    def test_payout_requires_research_and_strict_configuration(self):
        self.assertEqual(self.request("POST", "/api/payout", {})[0], 400)
        self.app.store.save_research({"data": {"source": "demo"}, "strategies": [
            {"id": "ema_pullback", "eligible": False, "trades": []}]})
        self.assertEqual(self.request("POST", "/api/payout", {"strategy_id": "ema_pullback"})[0], 400)
        for config in (None, True, [None], "invalid"):
            with self.subTest(config=config):
                status, result, _ = self.request("POST", "/api/payout", {
                    "strategy_id": "ema_pullback", "config": config})
                self.assertEqual(status, 400)
                self.assertIn("error", result)
        status, result, _ = self.request("POST", "/api/payout", {
            "strategy_id": "ema_pullback", "config": {"allow_illustrative": True}})
        self.assertEqual(status, 200)
        self.assertFalse(result["feasible"])

    def test_webhook_is_disabled_without_secret_and_rejects_wrong_token(self):
        signal = {"symbol": "EURUSD", "side": "long", "price": 1.1, "strategy_id": "ema_pullback"}
        with patch.dict(os.environ, {"TRADING_WEBHOOK_TOKEN": ""}):
            self.assertEqual(self.request("POST", "/api/webhook/tradingview", signal)[0], 503)
        with patch.dict(os.environ, {"TRADING_WEBHOOK_TOKEN": "test-only-not-a-credential"}):
            self.assertEqual(self.request("POST", "/api/webhook/tradingview", {**signal, "token": "incorrect"})[0], 401)
            self.assertEqual(self.request("POST", "/api/webhook/tradingview", {**signal, "token": []})[0], 401)
        status, result, _ = self.request("GET", "/api/signals")
        self.assertEqual(status, 200)
        self.assertFalse(result["execution_enabled"])
        self.assertEqual(result["signals"], [])

    def test_authorized_webhook_stores_planning_signal_and_excludes_secrets(self):
        test_token = "test-only-not-a-credential"
        with patch.dict(os.environ, {"TRADING_WEBHOOK_TOKEN": test_token}):
            status, response, _ = self.request("POST", "/api/webhook/tradingview", {
                "token": test_token, "symbol": "EURUSD", "side": "long", "price": 1.1,
                "strategy_id": "ema_pullback", "notes": "secret-field-discarded"})
            self.assertEqual(status, 202)
            self.assertFalse(response["executed"])
            self.assertEqual(response["signal"]["source"], "tradingview")
            self.assertEqual(response["signal"]["strategy"], "ema_pullback")
            self.assertEqual(response["signal"]["status"], "received_planning_only")
            status, _response, _ = self.request("POST", "/api/webhook/tradingview", {
                "symbol": "XAUUSD", "side": "flat", "price": 2300,
            }, headers={"Authorization": f"Bearer {test_token}"})
            self.assertEqual(status, 202)
        status, signals, _ = self.request("GET", "/api/signals")
        self.assertEqual(status, 200)
        self.assertEqual(len(signals["signals"]), 2)
        self.assertNotIn(test_token, json.dumps(signals))
        self.assertNotIn("secret-field-discarded", json.dumps(signals))
        # Test fixture secrets must not enter SQLite payloads or pages either.
        with self.app.store.connect() as connection:
            payloads = connection.execute("SELECT payload FROM signals").fetchall()
        self.assertTrue(all(test_token not in row[0] for row in payloads))

    def test_research_input_csv_and_configuration_validation(self):
        for payload in ({"source": "csv", "csv_text": "nonsense"},
                        {"source": "csv", "csv_text": "time,open,high,low,close,volume\n2026-01-01,1,2,0.5,1,1"},
                        {"config": []}, {"config": {"risk_pct": True}},
                        {"config": {"fee_bps": "nan"}}, {"config": {"strategy_ids": "ema_pullback"}},
                        {"source": "unknown"}, {"symbol": "UNKNOWN"}):
            with self.subTest(payload=payload):
                status, result, _ = self.request("POST", "/api/research", payload)
                self.assertEqual(status, 400)
                self.assertIn("error", result)
        self.assertIsNone(self.app.store.latest_research())

    def test_demo_research_cannot_claim_eligible_edge_and_preserves_provenance(self):
        status, result, _ = self.request("POST", "/api/research", {
            "source": "demo", "symbol": "EURUSD", "config": {"strategy_ids": ["ema_pullback"]}})
        self.assertEqual(status, 200)
        self.assertEqual(result["mode"], "research_paper_only")
        self.assertEqual(result["data"]["source"], "demo")
        self.assertEqual(result["summary"]["status"], "demo")
        self.assertTrue(result["research_id"])
        self.assertTrue(result["strategies"])
        self.assertTrue(all(not strategy["eligible"] for strategy in result["strategies"]))
        self.assertIsNone(result["selected_strategy"])
        self.assertNotEqual(result["payout"]["status"], "supported")
        status, latest, _ = self.request("GET", "/api/research/latest")
        self.assertEqual(status, 200)
        self.assertEqual(latest["research"]["research_id"], result["research_id"])
        status, exported, headers = self.request("GET", "/api/research/export")
        self.assertEqual(status, 200)
        self.assertEqual(exported["research_id"], result["research_id"])
        self.assertIn("attachment", headers["Content-Disposition"])
        status, payout, _ = self.request("POST", "/api/payout", {
            "strategy_id": result["strategies"][0]["id"], "config": {"allow_illustrative": True}})
        self.assertEqual(status, 200)
        self.assertNotEqual(payout["status"], "supported")

    def test_downloaded_example_is_explicitly_synthetic(self):
        status, csv_text, headers = self.request("GET", "/api/data/example")
        self.assertEqual(status, 200)
        self.assertIn("SYNTHETIC-DEMO", headers["Content-Disposition"])
        rows = list(csv.DictReader(io.StringIO(csv_text)))
        self.assertEqual(len(rows), 1200)
        self.assertEqual(set(rows[0]), {"time", "open", "high", "low", "close", "volume"})
        self.assertTrue(rows[0]["time"].endswith("Z"))

    def test_pine_export_unknown_strategy_is_client_error(self):
        status, script, headers = self.request("GET", "/api/export/pine?strategy_id=ema_pullback")
        self.assertEqual(status, 200)
        self.assertIn("//@version=6", script)
        self.assertIn("attachment", headers["Content-Disposition"])
        self.assertEqual(self.request("GET", "/api/export/pine?strategy_id=unrecognized")[0], 400)


if __name__ == "__main__":
    unittest.main()
