"""Portable startup, process ownership, and requested update restart contracts."""
import contextlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

import launch


RELEASE = {"version": "0.2.0", "commit": "abc123"}
HEALTH = {"ok": True, "status": "ok", "app": "PROP LAB", "version": "0.2.0", "commit": "abc123"}
MANIFEST = {"schema": 1, "version": "0.2.0", "repository": "NeatherFrog/awesome-x402", "branch": "main"}


@contextlib.contextmanager
def health_server(payload, content_type="application/json", status=200):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    try:
        yield server.server_port
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.output = io.StringIO()
        self.stdout = patch("sys.stdout", self.output)
        self.stderr = patch("sys.stderr", self.output)
        self.stdout.start()
        self.stderr.start()
        self.addCleanup(self.stdout.stop)
        self.addCleanup(self.stderr.stop)

    def test_health_matches_app_and_installed_release(self):
        with health_server(HEALTH) as port:
            self.assertTrue(launch.probe_health(port, RELEASE))
            self.assertFalse(launch.probe_health(port, {"version": "0.3.0", "commit": "abc123"}))
            self.assertFalse(launch.probe_health(port, {"version": "0.2.0", "commit": "new-commit"}))
            self.assertTrue(launch.probe_health(port, {"version": "0.2.0", "commit": None}))

    def test_health_does_not_trust_unrelated_or_unbounded_responses(self):
        examples = [
            {**HEALTH, "app": "Other application"},
            {**HEALTH, "ok": "yes"},
            {**HEALTH, "status": "starting"},
            {"ok": True, "mode": "paper", "version": "0.2.0"},
            [], b"not json", b" " * 8193,
        ]
        for payload in examples:
            with self.subTest(payload_type=type(payload).__name__):
                with health_server(payload) as port:
                    self.assertFalse(launch.probe_health(port, RELEASE))
        for content_type, status in [("text/html", 200), ("application/json", 503)]:
            with health_server(HEALTH, content_type, status) as port:
                self.assertFalse(launch.probe_health(port, RELEASE))

    def test_health_bypasses_environment_proxies(self):
        original = launch.urllib.request.ProxyHandler
        arguments = []

        class DirectProxyHandler(original):
            def __init__(self, proxies=None):
                arguments.append(proxies)
                super().__init__(proxies)

        with health_server(HEALTH) as port:
            with patch.dict(os.environ, {"http_proxy": "http://127.0.0.1:1", "no_proxy": ""}):
                with patch.object(launch.urllib.request, "ProxyHandler", DirectProxyHandler):
                    self.assertTrue(launch.probe_health(port, RELEASE))
                    self.assertEqual(arguments, [{}])

    def test_port_reuses_matching_running_application(self):
        with health_server(HEALTH) as port:
            self.assertEqual(launch.select_port(port, RELEASE), (port, True))

    def test_port_skips_unrelated_application_without_stopping_it(self):
        with health_server({**HEALTH, "app": "Someone else's server"}) as occupied:
            port, existing = launch.select_port(occupied, RELEASE)
            self.assertFalse(existing)
            self.assertGreater(port, occupied)
            self.assertLessEqual(port, min(occupied + 10, 65535))
            # The unrelated server still responds after selection.
            opener = launch.urllib.request.build_opener(launch.urllib.request.ProxyHandler({}))
            with opener.open("http://127.0.0.1:{}/api/health".format(occupied), timeout=1) as response:
                self.assertEqual(json.loads(response.read())["app"], "Someone else's server")

    def test_port_exhaustion_is_bounded(self):
        with patch.object(launch.socket, "socket") as socket_factory:
            socket_factory.return_value.__enter__.return_value.bind.side_effect = OSError("busy")
            with patch.object(launch, "probe_health", return_value=False) as probe:
                with self.assertRaises(launch.LaunchError):
                    launch.select_port(8000, RELEASE)
                self.assertEqual(probe.call_count, 11)
                with self.assertRaises(launch.LaunchError):
                    launch.select_port(65535, RELEASE)
                self.assertEqual(probe.call_count, 12)

    def test_release_is_reread_without_importing_backend(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "RELEASE.json"
            path.write_text(json.dumps(MANIFEST), encoding="utf-8")
            self.assertEqual(launch.read_release(directory), {"version": "0.2.0", "commit": None})
            path.write_text(json.dumps({**MANIFEST, "version": "0.3.0"}), encoding="utf-8")
            self.assertEqual(launch.read_release(directory), {"version": "0.3.0", "commit": None})
            for invalid in ({}, {"version": None}, {"version": ""}, [],
                            {**MANIFEST, "repository": "other/project"}, {**MANIFEST, "branch": "other"}):
                path.write_text(json.dumps(invalid), encoding="utf-8")
                with self.assertRaises(launch.LaunchError):
                    launch.read_release(directory)
            path.unlink()
            with self.assertRaises(launch.LaunchError):
                launch.read_release(directory)

    def test_package_commit_then_update_state_are_reread(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "RELEASE.json").write_text(json.dumps(MANIFEST))
            (root / ".installed.json").write_text(json.dumps({**MANIFEST, "commit": "a" * 40}))
            self.assertEqual(launch.read_release(root), {"version": "0.2.0", "commit": "a" * 40})
            state = root / ".local" / "updater" / "state.json"
            state.parent.mkdir(parents=True)
            state.write_text(json.dumps({**MANIFEST, "commit": "b" * 40}))
            self.assertEqual(launch.read_release(root), {"version": "0.2.0", "commit": "b" * 40})
            for invalid in ({**MANIFEST, "commit": "bad"}, {**MANIFEST, "commit": "b" * 40, "version": "0.3.0"},
                            {**MANIFEST, "commit": "b" * 40, "repository": "other/repo"}):
                state.write_text(json.dumps(invalid))
                with self.assertRaises(launch.LaunchError):
                    launch.read_release(root)

    def test_custom_and_environment_data_directories_follow_child_precedence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "RELEASE.json").write_text(json.dumps(MANIFEST))
            (root / ".installed.json").write_text(json.dumps({**MANIFEST, "commit": "a" * 40}))
            for name, commit in (("custom", "b" * 40), ("environment", "c" * 40)):
                state = root / name / "updater" / "state.json"
                state.parent.mkdir(parents=True)
                state.write_text(json.dumps({**MANIFEST, "commit": commit}))
            with patch.dict(os.environ, {"TRADING_DATA_DIR": "environment"}):
                self.assertEqual(launch.read_release(root)["commit"], "c" * 40)
                self.assertEqual(launch.read_release(root, "custom")["commit"], "b" * 40)
                self.assertEqual(launch.read_release(root, root / "custom")["commit"], "b" * 40)
            latest = {**MANIFEST, "version": "0.3.0", "commit": "d" * 40}
            state = root / ".local" / "updater" / "state.json"
            state.parent.mkdir(parents=True)
            state.write_text(json.dumps(latest))
            (root / "RELEASE.json").write_text(json.dumps({**MANIFEST, "version": "0.3.0"}))
            with patch.dict(os.environ, {"TRADING_DATA_DIR": ""}):
                self.assertEqual(launch.read_release(root), {"version": "0.3.0", "commit": "d" * 40})
            (root / ".git").mkdir()
            self.assertIsNone(launch.read_release(root, "custom")["commit"])

    def test_same_version_wrong_package_commit_is_not_reused(self):
        with health_server({**HEALTH, "commit": "a" * 40}) as occupied:
            port, existing = launch.select_port(occupied, {"version": "0.2.0", "commit": "b" * 40})
            self.assertFalse(existing)
            self.assertGreater(port, occupied)

    def test_ready_waits_for_health_and_detects_early_exit(self):
        child = Mock()
        child.poll.return_value = None
        with patch.object(launch, "probe_health", side_effect=[False, True]) as probe:
            with patch.object(launch.time, "sleep"):
                launch.wait_ready(child, 8000, RELEASE)
        self.assertEqual(probe.call_count, 2)
        child.poll.return_value = 2
        with patch.object(launch, "probe_health") as probe:
            with self.assertRaisesRegex(launch.LaunchError, "код 2"):
                launch.wait_ready(child, 8000, RELEASE)
            probe.assert_not_called()

    def test_ready_wait_has_timeout(self):
        child = Mock()
        child.poll.return_value = None
        with patch.object(launch, "probe_health", return_value=False):
            with patch.object(launch.time, "monotonic", side_effect=[0, 0, 16]):
                with patch.object(launch.time, "sleep"):
                    with self.assertRaises(launch.LaunchError):
                        launch.wait_ready(child, 8000, RELEASE)

    def test_update_restarts_fresh_child_and_opens_browser_only_once(self):
        first, second = Mock(), Mock()
        first.wait.return_value = launch.RESTART_EXIT_CODE
        second.wait.return_value = 0
        newer = {"version": "0.3.0", "commit": "new-commit"}
        with patch.object(launch, "read_release", side_effect=[RELEASE, RELEASE, newer]):
            with patch.object(launch, "select_port", return_value=(8002, False)):
                with patch.object(launch, "wait_ready") as ready:
                    with patch.object(launch, "open_browser") as browser:
                        with patch.object(launch.subprocess, "Popen", side_effect=[first, second]) as popen:
                            with patch.dict(os.environ, {"TRADING_SUPERVISED": "original", "TRADING_TEST_BINDING": "test-only"}):
                                self.assertEqual(launch.supervise("/distribution", data_dir="/my journal"), 0)
                                self.assertEqual(os.environ["TRADING_SUPERVISED"], "original")
                        browser.assert_called_once_with("http://127.0.0.1:8002/")
                        self.assertEqual(popen.call_count, 2)
                        arguments, options = popen.call_args
                        self.assertEqual(arguments[0], [launch.sys.executable, "-m", "propdesk", "serve",
                                                       "--host", "127.0.0.1", "--port", "8002",
                                                       "--data-dir", "/my journal"])
                        self.assertEqual(options["cwd"], "/distribution")
                        self.assertEqual(options["env"]["TRADING_SUPERVISED"], "1")
                        self.assertEqual(options["env"]["TRADING_TEST_BINDING"], "test-only")
                        self.assertNotIn("shell", options)
                        self.assertEqual(ready.call_args_list[0].args[2], RELEASE)
                        self.assertEqual(ready.call_args_list[1].args[2], newer)
                        self.assertTrue(all(call.args == ("/distribution", "/my journal")
                                            for call in launch.read_release.call_args_list))

    def test_existing_application_does_not_spawn_a_child(self):
        with patch.object(launch, "read_release", return_value=RELEASE):
            with patch.object(launch, "select_port", return_value=(8000, True)):
                with patch.object(launch, "open_browser") as browser:
                    with patch.object(launch.subprocess, "Popen") as popen:
                        self.assertEqual(launch.supervise("/distribution", no_browser=True), 0)
                        popen.assert_not_called()
                        browser.assert_not_called()

    def test_only_requested_restart_exit_code_restarts(self):
        for code in (0, 1, 43, -15):
            with self.subTest(code=code):
                child = Mock()
                child.wait.return_value = code
                with patch.object(launch, "read_release", return_value=RELEASE):
                    with patch.object(launch, "select_port", return_value=(8000, False)):
                        with patch.object(launch, "wait_ready"):
                            with patch.object(launch.subprocess, "Popen", return_value=child) as popen:
                                self.assertEqual(launch.supervise("/distribution", no_browser=True), code)
                                popen.assert_called_once()

    def test_rapid_restart_loop_stops_after_three_restarts(self):
        child = Mock()
        child.wait.return_value = launch.RESTART_EXIT_CODE
        with patch.object(launch, "read_release", return_value=RELEASE):
            with patch.object(launch, "select_port", return_value=(8000, False)):
                with patch.object(launch, "wait_ready"):
                    with patch.object(launch.time, "monotonic", return_value=1):
                        with patch.object(launch.subprocess, "Popen", return_value=child) as popen:
                            self.assertEqual(launch.supervise("/distribution", no_browser=True), 1)
                            self.assertEqual(popen.call_count, 4)

    def test_startup_failure_stops_only_owned_child(self):
        child = Mock()
        child.poll.return_value = None
        child.wait.return_value = 0
        with patch.object(launch, "read_release", return_value=RELEASE):
            with patch.object(launch, "select_port", return_value=(8000, False)):
                with patch.object(launch, "wait_ready", side_effect=launch.LaunchError("not ready")):
                    with patch.object(launch.subprocess, "Popen", return_value=child):
                        self.assertEqual(launch.supervise("/distribution", no_browser=True), 1)
        child.terminate.assert_called_once()
        child.wait.assert_called_once_with(timeout=3)
        child.kill.assert_not_called()

    def test_ctrl_c_cleans_up_owned_process(self):
        child = Mock()
        child.poll.return_value = None
        child.wait.side_effect = [KeyboardInterrupt, 0]
        with patch.object(launch, "read_release", return_value=RELEASE):
            with patch.object(launch, "select_port", return_value=(8000, False)):
                with patch.object(launch, "wait_ready"):
                    with patch.object(launch.subprocess, "Popen", return_value=child):
                        self.assertEqual(launch.supervise("/distribution", no_browser=True), 0)
        child.terminate.assert_called_once()

    def test_unresponsive_owned_child_is_killed(self):
        child = Mock()
        child.poll.return_value = None
        child.wait.side_effect = [subprocess.TimeoutExpired("child", 3), 0]
        launch.stop_child(child)
        child.terminate.assert_called_once()
        child.kill.assert_called_once()
        self.assertEqual(child.wait.call_count, 2)

    def test_child_exit_race_does_not_break_cleanup(self):
        child = Mock()
        child.poll.return_value = None
        child.terminate.side_effect = ProcessLookupError
        launch.stop_child(child)
        child.kill.assert_not_called()

    def test_main_installs_and_restores_termination_handler(self):
        with patch.object(launch.signal, "signal", return_value="previous handler") as register:
            with patch.object(launch, "supervise", return_value=0) as supervisor:
                self.assertEqual(launch.main(["--no-browser", "--port", "8101", "--data-dir", "my journal"]), 0)
        self.assertEqual(register.call_count, 2)
        termination_handler = register.call_args_list[0].args[1]
        with self.assertRaises(KeyboardInterrupt):
            termination_handler(launch.signal.SIGTERM, None)
        self.assertEqual(register.call_args_list[1].args, (launch.signal.SIGTERM, "previous handler"))
        self.assertEqual(supervisor.call_args.args[1:], (8101, True, "my journal"))

    def test_old_python_gets_actionable_error_before_start(self):
        with patch.object(launch.sys, "version_info", (3, 10, 0)):
            with patch.object(launch, "supervise") as supervisor:
                self.assertEqual(launch.main([]), 1)
                supervisor.assert_not_called()
        self.assertIn("Python 3.11", self.output.getvalue())


if __name__ == "__main__":
    unittest.main()
