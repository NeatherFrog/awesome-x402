"""Deterministic research scheduling: no market requests or broker orders."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from propdesk.autopilot import Autopilot, DEFAULT_SETTINGS, ResearchDeferred, normalize_settings


class Clock:
    def __init__(self, now=None):
        self.now = now or datetime(2026, 10, 1, 12, tzinfo=timezone.utc)
    def __call__(self):
        return self.now
    def advance(self, **kwargs):
        self.now += timedelta(**kwargs)


class Scanner:
    def __init__(self):
        self.records = {}
        self.calls = []
        self.latest_id = None
    def start(self, settings):
        self.calls.append(deepcopy(settings))
        identifier = str(uuid4())
        self.latest_id = identifier
        record = {"id": identifier, "state": "running", "result": None,
                  "created_at": "2026-10-01T12:00:00Z", "updated_at": "2026-10-01T12:00:00Z"}
        self.records[identifier] = record
        return deepcopy(record)
    def get(self, identifier):
        return deepcopy(self.records[identifier])
    def latest(self):
        return self.get(self.latest_id) if self.latest_id else None
    def finish(self, *, result=None, state="completed"):
        result = result if result is not None else {"markets": [{"symbol": "AAPL", "primary": True,
                    "selected": False, "qualified": False}], "selected_symbol": None, "fetch_errors": []}
        self.records[self.latest_id].update(state=state, result=deepcopy(result))


class AutopilotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "autopilot.json"
        self.clock = Clock()
        self.scanner = Scanner()
        self.controllers = []
    def tearDown(self):
        for controller in self.controllers:
            controller.stop()
        self.temp.cleanup()
    def controller(self, **kwargs):
        options = {"latest_scan": self.scanner.latest, "clock": self.clock}
        options.update(kwargs)
        controller = Autopilot(self.path, self.scanner.start, self.scanner.get, **options)
        self.controllers.append(controller)
        return controller

    def test_default_requires_explicit_enable_and_does_not_start_a_thread(self):
        controller = self.controller()
        status = controller.tick()
        self.assertFalse(status["enabled"])
        self.assertFalse(status["running"])
        self.assertFalse(status["thread_active"])
        self.assertEqual(self.scanner.calls, [])
        self.assertTrue(status["planning_only"])
        self.assertFalse(status["live_orders"])
        self.assertEqual(status["settings"]["source"], "yahoo")
        self.assertEqual(status["settings"]["interval"], "1h")
        self.assertEqual(status["settings"]["range"], "2y")
        self.assertEqual(len(status["settings"]["symbols"]), 8)

    def test_one_automatic_attempt_per_utc_day_and_same_day_restart_reuses_job_id(self):
        controller = self.controller(enabled=True)
        first = controller.tick()
        self.assertEqual(len(self.scanner.calls), 1)
        self.assertTrue(first["running"])
        self.scanner.finish()
        done = controller.tick()
        self.assertTrue(done["result_ready"])
        self.assertEqual(done["qualified_count"], 0)
        self.assertIsNone(done["selected_symbol"])
        controller.tick()
        self.assertEqual(len(self.scanner.calls), 1)
        restarted = self.controller(enabled=True)
        self.assertEqual(restarted.status()["job_id"], first["job_id"])
        restarted.tick()
        self.assertEqual(len(self.scanner.calls), 1)
        self.clock.advance(days=1)
        restarted.tick()
        self.assertEqual(len(self.scanner.calls), 2)

    def test_disabled_preference_survives_desktop_enabled_initializer(self):
        controller = self.controller(enabled=True)
        controller.configure({"enabled": False})
        reloaded = self.controller(enabled=True)
        self.assertFalse(reloaded.status()["enabled"])
        reloaded.tick()
        self.assertEqual(self.scanner.calls, [])

    def test_manual_run_works_while_automatic_mode_disabled_and_avoids_active_duplicate(self):
        controller = self.controller()
        first = controller.run_now()
        self.assertTrue(first["running"])
        self.assertFalse(first["enabled"])
        self.assertEqual(len(self.scanner.calls), 1)
        second = controller.run_now()
        self.assertEqual(second["job_id"], first["job_id"])
        self.assertEqual(len(self.scanner.calls), 1)
        self.scanner.finish()
        controller.tick()
        controller.run_now()
        self.assertEqual(len(self.scanner.calls), 2)

    def test_busy_defers_without_consuming_daily_attempt_and_manual_pending_is_resumed(self):
        busy = {"value": True}
        controller = self.controller(can_start=lambda: {"allowed": not busy["value"]})
        pending = controller.run_now()
        self.assertEqual(pending["state"], "waiting_for_idle")
        self.assertIsNone(pending["last_attempt_at"])
        self.assertEqual(self.scanner.calls, [])
        busy["value"] = False
        started = controller.tick()
        self.assertTrue(started["running"])
        self.assertEqual(len(self.scanner.calls), 1)

    def test_external_active_job_defers_even_without_busy_adapter(self):
        self.scanner.start(DEFAULT_SETTINGS)
        controller = self.controller(enabled=True)
        waiting = controller.tick()
        self.assertEqual(waiting["state"], "waiting_for_idle")
        self.assertEqual(len(self.scanner.calls), 1)
        self.scanner.finish()
        self.clock.advance(seconds=31)
        controller.tick()
        self.assertEqual(len(self.scanner.calls), 2)

    def test_outage_completes_with_backoff_and_no_demo_or_automatic_same_day_retry(self):
        controller = self.controller(enabled=True)
        controller.tick()
        self.scanner.finish(result={"markets": [], "fetch_errors": [{"error": "HTTP 403"}], "market_count": 0})
        failed = controller.tick()
        self.assertFalse(failed["running"])
        self.assertFalse(failed["result_ready"])
        self.assertEqual(failed["failure_count"], 1)
        self.assertIn("демо не подставляется", failed["last_error"])
        self.assertGreater(failed["next_attempt_at"], failed["last_attempt_at"])
        self.clock.advance(hours=1)
        controller.tick()
        self.assertEqual(len(self.scanner.calls), 1)
        self.assertEqual(self.scanner.calls[0]["source"], "yahoo")

    def test_late_outage_exponential_pause_can_extend_past_midnight(self):
        self.clock.now = self.clock.now.replace(hour=23, minute=59)
        controller = self.controller(enabled=True)
        controller.tick()
        self.scanner.finish(state="failed")
        failed = controller.tick()
        self.assertEqual(failed["next_attempt_at"], "2026-10-02T00:04:00Z")
        self.clock.advance(minutes=2)
        controller.tick()
        self.assertEqual(len(self.scanner.calls), 1)
        self.clock.advance(minutes=3)
        controller.tick()
        self.assertEqual(len(self.scanner.calls), 2)

    def test_stalled_or_unknown_active_job_is_preserved_without_new_duplicate(self):
        controller = self.controller(enabled=True)
        initial = controller.tick()
        self.clock.advance(minutes=11)
        stalled = controller.tick()
        self.assertEqual(stalled["state"], "stalled")
        self.assertTrue(stalled["running"])
        self.assertEqual(len(self.scanner.calls), 1)
        with patch.object(controller, "get_scan", side_effect=ValueError("private token=abc")):
            unknown = controller.tick()
        self.assertEqual(unknown["job_id"], initial["job_id"])
        self.assertTrue(unknown["running"])
        self.assertNotIn("abc", unknown["last_error"])
        controller.run_now()
        self.assertEqual(len(self.scanner.calls), 1)

    def test_disabling_does_not_cancel_active_job_but_stops_future_scheduling(self):
        controller = self.controller(enabled=True)
        controller.tick()
        stopped = controller.configure({"enabled": False})
        self.assertFalse(stopped["enabled"])
        self.assertTrue(stopped["running"])
        self.scanner.finish()
        controller.tick()
        self.clock.advance(days=1)
        controller.tick()
        self.assertEqual(len(self.scanner.calls), 1)

    def test_callbacks_errors_are_sanitized_and_attempt_is_reserved_before_start(self):
        controller = self.controller(enabled=True)
        observed = []
        def fail(settings):
            observed.append(json.loads(self.path.read_text()))
            raise RuntimeError("Bearer SUPERSECRET https://user:password@private.example")
        with patch.object(controller, "start_scan", side_effect=fail):
            status = controller.tick()
        self.assertEqual(len(observed), 1)
        self.assertEqual(observed[0]["last_attempt_day"], "2026-10-01")
        self.assertIsNotNone(observed[0]["request_fingerprint"])
        self.assertNotIn("SUPERSECRET", json.dumps(status))
        self.assertNotIn("private.example", self.path.read_text())
        self.assertFalse(status["running"])
        self.assertEqual(status["failure_count"], 1)

    def test_selected_summary_requires_qualified_primary_not_diagnostic(self):
        controller = self.controller(enabled=True)
        controller.tick()
        self.scanner.finish(result={"markets": [{"symbol": "AAPL", "primary": False, "qualified": True, "selected": True}],
                                    "selected_symbol": "AAPL"})
        result = controller.tick()
        self.assertEqual(result["qualified_count"], 1)
        self.assertIsNone(result["selected_symbol"])
        controller.run_now()
        self.scanner.finish(result={"markets": [{"symbol": "MSFT", "primary": True, "qualified": True, "selected": True}],
                                    "selected_symbol": "MSFT"})
        self.assertEqual(controller.tick()["selected_symbol"], "MSFT")

    def test_explicit_fresh_cache_certification_can_reuse_identical_completed_job(self):
        settings = normalize_settings()
        record = self.scanner.start(settings)
        self.scanner.finish()
        fingerprint = hashlib.sha256(json.dumps(settings, sort_keys=True, allow_nan=False, separators=(",", ":")).encode()).hexdigest()
        self.scanner.records[record["id"]].update(reuse_allowed=True, request_fingerprint=fingerprint)
        controller = self.controller(enabled=True)
        reused = controller.tick()
        self.assertEqual(reused["job_id"], record["id"])
        self.assertTrue(reused["result_ready"])
        self.assertEqual(len(self.scanner.calls), 1)

    def test_identical_settings_alone_do_not_assert_cache_is_fresh(self):
        self.scanner.start(DEFAULT_SETTINGS)
        self.scanner.finish()
        controller = self.controller(enabled=True)
        controller.tick()
        self.assertEqual(len(self.scanner.calls), 2)

    def test_invalid_settings_or_secrets_do_not_change_saved_state(self):
        controller = self.controller()
        before = self.path.read_bytes()
        for payload in ({"enabled": "yes"}, {"token": "secret"}, {"settings": {"source": "demo"}},
                        {"settings": {"symbols": ["https://private.example"]}},
                        {"settings": {"config": {"risk_pct": float("inf")}}},
                        {"settings": {"config": {"token": "secret"}}},
                        {"settings": {"config": {"use_market_costs": 1}}},
                        {"settings": {"symbols": []}}, {"settings": {"profile_id": "Bearer secret"}}):
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    controller.configure(payload)
                self.assertEqual(self.path.read_bytes(), before)
        normalized = normalize_settings({"symbols": ["aapl", "AAPL"]})
        self.assertEqual(normalized["symbols"], ["AAPL"])

    def test_settings_cannot_change_under_an_active_job(self):
        controller = self.controller(enabled=True)
        controller.tick()
        before = self.path.read_bytes()
        with self.assertRaisesRegex(ValueError, "завершения"):
            controller.configure({"settings": {"symbols": ["MSFT"]}})
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(controller.status()["settings"]["symbols"], DEFAULT_SETTINGS["symbols"])
        self.scanner.finish()
        controller.tick()
        changed = controller.configure({"settings": {"symbols": ["MSFT"]}})
        self.assertFalse(changed["result_ready"])
        self.assertIsNone(changed["selected_symbol"])

    def test_busy_race_restores_daily_reservation_and_pending_manual_request(self):
        controller = self.controller(enabled=True)
        with patch.object(controller, "start_scan", side_effect=ResearchDeferred("private reason")):
            waiting = controller.tick()
        self.assertEqual(waiting["state"], "waiting_for_idle")
        self.assertIsNone(waiting["last_attempt_at"])
        self.assertEqual(waiting["failure_count"], 0)
        self.assertNotIn("private reason", json.dumps(waiting))
        self.clock.advance(seconds=31)
        self.assertTrue(controller.tick()["running"])
        self.scanner.finish()
        controller.tick()
        with patch.object(controller, "start_scan", side_effect=ResearchDeferred):
            pending = controller.run_now()
        self.assertTrue(pending["manual_requested"])
        controller.tick()
        self.assertEqual(len(self.scanner.calls), 2)

    def test_two_preloaded_controllers_share_persisted_daily_reservation(self):
        first = self.controller(enabled=True, latest_scan=None)
        second = self.controller(enabled=True, latest_scan=None)
        first.tick()
        self.scanner.finish()
        first.tick()
        second.tick()
        self.assertEqual(len(self.scanner.calls), 1)
        self.assertEqual(second.status()["job_id"], first.status()["job_id"])

    def test_concurrent_controllers_launch_only_one_worker(self):
        controllers = [self.controller(enabled=True, latest_scan=None) for _ in range(2)]
        barrier = threading.Barrier(2)
        errors = []
        def run(controller):
            try:
                barrier.wait(timeout=2)
                controller.tick()
            except Exception as exc:
                errors.append(exc)
        threads = [threading.Thread(target=run, args=(controller,)) for controller in controllers]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=2)
            self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(len(self.scanner.calls), 1)

    def test_separate_processes_share_one_automatic_daily_attempt(self):
        self.controller(enabled=True, latest_scan=None)
        marker = self.path.with_name("attempts.txt")
        script = """
from datetime import datetime, timezone
from pathlib import Path
import sys
import time
from uuid import uuid4
from propdesk.autopilot import Autopilot
def start(settings):
    with Path(sys.argv[2]).open('a', encoding='utf-8') as stream:
        stream.write('attempt\\n')
    time.sleep(.05)
    return {'id': str(uuid4()), 'state': 'running'}
def get(identifier):
    return {'id': identifier, 'state': 'completed', 'result': {'markets': [], 'fetch_errors': []}}
controller = Autopilot(sys.argv[1], start, get, enabled=True,
                       clock=lambda: datetime(2026, 10, 1, 12, tzinfo=timezone.utc))
controller.tick()
"""
        command = [sys.executable, "-c", script, str(self.path), str(marker)]
        processes = [subprocess.Popen(command, cwd=Path(__file__).resolve().parents[1],
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE) for _ in range(2)]
        try:
            for process in processes:
                stdout, stderr = process.communicate(timeout=5)
                self.assertEqual(process.returncode, 0, (stdout, stderr))
        finally:
            for process in processes:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=2)
        self.assertEqual(marker.read_text().splitlines(), ["attempt"])

    def test_malformed_persisted_active_state_schema_and_date_are_rejected(self):
        controller = self.controller(enabled=True)
        controller.tick()
        baseline = json.loads(self.path.read_text())
        mutations = [{"job_started_at": None, "last_attempt_at": None}, {"schema": True},
                     {"last_attempt_day": "20261001"}, {"running": "yes"}]
        for change in mutations:
            with self.subTest(change=change):
                damaged = {**baseline, **change}
                original = json.dumps(damaged).encode()
                self.path.write_bytes(original)
                with self.assertRaises(ValueError):
                    self.controller()
                self.assertEqual(self.path.read_bytes(), original)
        self.path.write_text(json.dumps(baseline))

    def test_corrupt_state_is_rejected_and_preserved_and_file_is_atomic(self):
        self.path.write_bytes(b"broken original file")
        original = self.path.read_bytes()
        with self.assertRaises(ValueError):
            self.controller()
        self.assertEqual(self.path.read_bytes(), original)
        self.path.unlink()
        controller = self.controller(enabled=True)
        controller.tick()
        self.assertEqual(list(self.path.parent.glob(".autopilot-*.tmp")), [])
        persisted = json.loads(self.path.read_text())
        self.assertEqual(persisted["job_id"], controller.status()["job_id"])
        self.assertNotIn("token", persisted)

    def test_failed_persistence_does_not_launch_any_scanner_job(self):
        controller = self.controller(enabled=True)
        with patch.object(controller, "_save", side_effect=OSError("secret filesystem detail")):
            with self.assertRaises(OSError):
                controller.tick()
        self.assertEqual(self.scanner.calls, [])

    def test_scheduler_thread_is_explicit_idempotent_and_joined_on_stop(self):
        controller = self.controller(enabled=False, poll_interval=.02)
        self.assertFalse(controller.status()["thread_active"])
        controller.start()
        thread = controller._thread
        self.assertFalse(thread.daemon)
        controller.start()
        self.assertIs(controller._thread, thread)
        controller.stop()
        self.assertFalse(thread.is_alive())
        self.assertFalse(controller.status()["thread_active"])
        self.assertEqual(self.scanner.calls, [])

    def test_readonly_status_is_copied_and_does_not_schedule_or_write(self):
        controller = self.controller(enabled=True)
        before = self.path.read_bytes()
        snapshot = controller.status()
        snapshot["settings"]["symbols"].append("SECRET")
        self.assertNotIn("SECRET", controller.status()["settings"]["symbols"])
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.scanner.calls, [])


if __name__ == "__main__":
    unittest.main()
