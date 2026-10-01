"""HTTP updates: managed package files, preserved journal and frozen runtime ID."""
import hashlib
import http.client
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest.mock import patch
import zipfile

from propdesk.server import Application, RESEARCH_LOCK, make_handler
from propdesk.updater import BRANCH, REPOSITORY
from propdesk.version import VERSION

OLD = "a" * 40
NEW = "b" * 40


def release(version):
    return {"schema": 1, "repository": REPOSITORY, "branch": BRANCH, "version": version}


def source(version):
    return {"RELEASE.json": json.dumps(release(version)).encode(),
            "propdesk/server.py": b"# packaged application " + version.encode() + b"\n",
            "static/index.html": b"<html>" + version.encode() + b"</html>"}


def package_zip():
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as output:
        for relative, content in source("0.3.0").items():
            output.writestr(f"NeatherFrog-awesome-x402-{NEW[:7]}/{relative}", content)
    return stream.getvalue()


class UpdateAPITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "trading"
        self.root.mkdir()
        files = source("0.2.0")
        for relative, content in files.items():
            destination = self.root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
        metadata = {**release("0.2.0"), "commit": OLD,
                    "files": {name: hashlib.sha256(content).hexdigest() for name, content in files.items()}}
        (self.root / ".installed.json").write_text(json.dumps(metadata))
        (self.root / ".env").write_text("SECRET=local-only")
        self.app = Application(self.root / ".local", root=self.root)
        self.trade = self.app.store.add_trade({"symbol": "EURUSD", "side": "long", "entry": 1.1,
                                               "exit": 1.11, "stop": 1.09, "quantity": 100,
                                               "strategy": "journal evidence"})
        handler = make_handler(self.app)
        handler.log_message = lambda *_args: None
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": .01}, daemon=True)
        self.thread.start()
        self.supervision = patch.dict(os.environ, {"TRADING_SUPERVISED": "0"})
        self.supervision.start()

    def tearDown(self):
        self.supervision.stop()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temp.cleanup()

    def request(self, method, path, body=None, *, headers=None):
        supplied = dict(headers or {})
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            supplied.setdefault("Content-Type", "application/json")
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=30)
        try:
            connection.request(method, path, body=data, headers=supplied)
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def fetch(self, url, limit, *, authenticated=False):
        if "/commits/" in url:
            self.assertEqual(url, f"https://api.github.com/repos/{REPOSITORY}/commits/{BRANCH}")
            self.assertTrue(authenticated)
            return json.dumps({"sha": NEW}).encode()
        self.assertEqual(url, f"https://api.github.com/repos/{REPOSITORY}/zipball/{NEW}")
        self.assertTrue(authenticated)
        return package_zip()

    def test_status_is_local_and_health_identifies_loaded_runtime(self):
        with patch.object(self.app.updater, "_fetch") as fetch:
            status, update = self.request("GET", "/api/updates/status")
            health_status, health = self.request("GET", "/api/health")
        fetch.assert_not_called()
        self.assertEqual(status, 200)
        self.assertEqual(update["mode"], "package")
        self.assertTrue(update["can_apply"])
        self.assertEqual(update["current_commit"], OLD)
        self.assertEqual(update["running_commit"], OLD)
        self.assertEqual(health_status, 200)
        self.assertEqual(health["commit"], OLD)
        self.assertEqual(health["version"], VERSION)

    def test_check_ignores_untrusted_repository_payload_and_does_not_install(self):
        before = (self.root / "propdesk/server.py").read_bytes()
        with patch.object(self.app.updater, "_fetch", side_effect=self.fetch):
            status, result = self.request("POST", "/api/updates/check", {
                "repository": "attacker/project", "branch": "evil", "url": "https://evil.example/archive"})
        self.assertEqual(status, 200)
        self.assertTrue(result["available"])
        self.assertEqual(result["repository"], REPOSITORY)
        self.assertEqual(result["latest_commit"], NEW)
        self.assertEqual((self.root / "propdesk/server.py").read_bytes(), before)
        self.assertFalse((self.root / ".local/updater/state.json").exists())

    def test_apply_installs_package_and_preserves_journal_and_runtime_identity(self):
        with patch.object(self.app.updater, "_fetch", side_effect=self.fetch):
            status, result = self.request("POST", "/api/updates/apply", {})
        self.assertEqual(status, 200)
        self.assertTrue(result["updated"])
        self.assertTrue(result["restart_required"])
        self.assertFalse(result["restarting"])
        self.assertEqual((self.root / "propdesk/server.py").read_bytes(), source("0.3.0")["propdesk/server.py"])
        self.assertEqual((self.root / ".env").read_text(), "SECRET=local-only")
        self.assertEqual(self.app.store.journal()["trades"][0]["id"], self.trade["id"])
        _, update = self.request("GET", "/api/updates/status")
        _, health = self.request("GET", "/api/health")
        self.assertEqual(update["current_commit"], NEW)
        self.assertEqual(update["running_commit"], OLD)
        self.assertTrue(update["restart_required"])
        self.assertFalse(update["can_apply"])
        self.assertEqual(health["commit"], OLD)
        self.assertEqual(health["version"], VERSION)
        fresh_application = Application(self.root / ".local", root=self.root)
        self.assertEqual(fresh_application.running_commit, NEW)
        self.assertFalse(fresh_application.updater.status()["restart_required"])

    def test_supervised_apply_schedules_shutdown_and_blocks_further_mutations(self):
        scheduled = threading.Event()
        with patch.dict(os.environ, {"TRADING_SUPERVISED": "1"}), \
                patch("propdesk.server.threading.Timer") as timer, \
                patch.object(self.app.updater, "_fetch", side_effect=self.fetch):
            timer.return_value.start.side_effect = scheduled.set
            status, result = self.request("POST", "/api/updates/apply", {})
            self.assertTrue(scheduled.wait(timeout=1), "restart was not scheduled")
            self.assertEqual(status, 200)
            self.assertTrue(result["restarting"])
            self.assertTrue(self.app.restart_requested)
            timer.assert_called_once()
            self.assertEqual(timer.call_args.args[0], 1.0)
            self.assertIs(timer.call_args.args[1].__self__, self.server)
            timer.return_value.start.assert_called_once()
            status, blocked = self.request("POST", "/api/updates/check", {})
            self.assertEqual(status, 503)
            self.assertIn("перезапускается", blocked["error"])
            _, health = self.request("GET", "/api/health")
            self.assertEqual(health["commit"], OLD)

    def test_development_checkout_can_check_but_cannot_apply(self):
        (self.root / ".git").mkdir()
        # The existing server holds the same Application object.
        from propdesk.updater import Updater
        self.app.updater = Updater(self.root, self.root / ".local/updater")
        with patch.object(self.app.updater, "_fetch", side_effect=self.fetch) as fetch:
            status, result = self.request("POST", "/api/updates/check", {})
            self.assertEqual(status, 200)
            self.assertEqual(result["mode"], "development")
            self.assertFalse(result["can_apply"])
            status, blocked = self.request("POST", "/api/updates/apply", {})
            self.assertEqual(status, 400)
            self.assertIn("Git checkout", blocked["error"])
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual((self.root / "propdesk/server.py").read_bytes(), source("0.2.0")["propdesk/server.py"])

    def test_active_research_prevents_install_before_network_request(self):
        acquired = RESEARCH_LOCK.acquire(blocking=False)
        self.assertTrue(acquired)
        try:
            with patch.object(self.app.updater, "_fetch") as fetch:
                status, blocked = self.request("POST", "/api/updates/apply", {})
                fetch.assert_not_called()
            self.assertEqual(status, 409)
            self.assertIn("исследования", blocked["error"])
        finally:
            RESEARCH_LOCK.release()

    def test_busy_updater_blocks_other_write_endpoints(self):
        status_payload = self.app.updater.status()
        with patch.object(self.app.updater, "status", return_value={**status_payload, "busy": True}):
            status, blocked = self.request("POST", "/api/setups", {})
        self.assertEqual(status, 503)
        self.assertIn("обновление", blocked["error"])
        self.assertEqual(self.app.store.journal()["stats"]["total_trades"], 1)

    def test_cross_origin_install_is_rejected_without_contacting_github(self):
        with patch.object(self.app.updater, "_fetch") as fetch:
            status, result = self.request("POST", "/api/updates/apply", {},
                                           headers={"Origin": "https://foreign.example"})
        self.assertEqual(status, 403)
        self.assertIn("error", result)
        fetch.assert_not_called()

    def test_dirty_package_error_does_not_claim_restart_or_change_source(self):
        (self.root / "propdesk/server.py").write_bytes(b"local edits")
        with patch.object(self.app.updater, "_fetch", side_effect=self.fetch):
            status, result = self.request("POST", "/api/updates/apply", {})
        self.assertEqual(status, 400)
        self.assertIn("Локальный исходный файл", result["error"])
        self.assertFalse(self.app.restart_requested)
        self.assertEqual((self.root / "propdesk/server.py").read_bytes(), b"local edits")
        self.assertEqual(self.app.store.journal()["stats"]["total_trades"], 1)


if __name__ == "__main__":
    unittest.main()
