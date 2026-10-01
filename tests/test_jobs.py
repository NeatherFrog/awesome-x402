"""Background scanners: persistent lifecycle, races and credential boundaries."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from uuid import uuid4

from propdesk.jobs import ScannerJobs


class JobTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name) / "scanner"
        self.release = threading.Event()
        self.cleanup_workers = []

    def tearDown(self):
        self.release.set()
        for jobs in self.cleanup_workers:
            with jobs._guard:
                workers = list(jobs._threads.values())
            for worker in workers:
                worker.join(timeout=3)
        self.temp.cleanup()

    def manager(self, worker):
        jobs = ScannerJobs(self.directory, worker)
        self.cleanup_workers.append(jobs)
        return jobs

    def finish(self, jobs, identifier):
        with jobs._guard:
            thread = jobs._threads.get(identifier)
        if thread is not None:
            thread.join(timeout=3)
            self.assertFalse(thread.is_alive(), "worker did not finish")
        self.assertFalse(jobs.busy)
        return jobs.get(identifier)

    def test_initial_state_is_running_even_when_worker_finishes_immediately(self):
        jobs = self.manager(lambda payload, progress: {"symbols": payload["symbols"], "score": 1.2})
        initial = jobs.start({"source": "yahoo", "symbols": ["AAPL"]})
        self.assertEqual(initial["state"], "running")
        finished = self.finish(jobs, initial["id"])
        self.assertEqual(finished["state"], "completed")
        self.assertEqual(finished["result"], {"symbols": ["AAPL"], "score": 1.2})
        self.assertIsNone(finished["error"])
        self.assertEqual(jobs.latest()["id"], initial["id"])
        persisted = json.loads((self.directory / f"{initial['id']}.json").read_text())
        self.assertEqual(persisted, finished)
        self.assertFalse(any(path.name.startswith(".job-") for path in self.directory.iterdir()))

    def test_one_active_worker_and_progress_persisted_before_completion(self):
        observed = threading.Event()

        def worker(payload, progress):
            progress("fetching", {"symbol": "AAPL", "completed": 1, "total": 4})
            observed.set()
            self.release.wait(timeout=3)
            return {"qualified_count": 0}

        jobs = self.manager(worker)
        initial = jobs.start({"symbols": ["AAPL"]})
        self.assertTrue(observed.wait(timeout=2))
        self.assertTrue(jobs.busy)
        running = jobs.get(initial["id"])
        self.assertEqual(running["progress"]["stage"], "fetching")
        self.assertEqual(running["progress"]["details"]["total"], 4)
        with self.assertRaisesRegex(ValueError, "уже выполняется"):
            jobs.start({"symbols": ["MSFT"]})
        self.assertEqual(len(list(self.directory.glob("*.json"))), 1)
        self.release.set()
        self.assertEqual(self.finish(jobs, initial["id"])["state"], "completed")
        next_job = jobs.start({"symbols": ["MSFT"]})
        self.assertNotEqual(next_job["id"], initial["id"])
        self.finish(jobs, next_job["id"])

    def test_worker_inputs_are_copied_and_never_persisted(self):
        observed = []
        entered = threading.Event()

        def worker(payload, progress):
            entered.set()
            self.release.wait(timeout=3)
            observed.append(payload["symbols"][:])
            payload["symbols"].append("MUTATED")
            return {"ok": True}

        payload = {"symbols": ["AAPL"], "config": {"risk_pct": .25}, "GH_TOKEN": "must-not-forward"}
        jobs = self.manager(worker)
        initial = jobs.start(payload)
        self.assertTrue(entered.wait(timeout=2))
        payload["symbols"].append("MSFT")
        self.release.set()
        result = self.finish(jobs, initial["id"])
        self.assertEqual(observed, [["AAPL"]])
        self.assertEqual(payload["symbols"], ["AAPL", "MSFT"])
        serialized = (self.directory / f"{initial['id']}.json").read_text()
        self.assertNotIn("must-not-forward", serialized)
        self.assertNotIn("risk_pct", serialized)
        self.assertNotIn("payload", result)

    def test_completed_results_and_latest_survive_reopening(self):
        jobs = self.manager(lambda payload, progress: {"symbol": payload["symbols"][0]})
        first = jobs.start({"symbols": ["AAPL"]})
        self.finish(jobs, first["id"])
        second = jobs.start({"symbols": ["MSFT"]})
        self.finish(jobs, second["id"])
        reopened = self.manager(lambda *_args: {})
        self.assertFalse(reopened.busy)
        self.assertEqual(reopened.latest()["id"], second["id"])
        self.assertEqual(reopened.get(first["id"])["result"]["symbol"], "AAPL")
        self.assertEqual(reopened.status(second["id"])["result"]["symbol"], "MSFT")

    def test_previous_running_and_queued_jobs_become_interrupted(self):
        self.directory.mkdir()
        ids = []
        for state in ("running", "queued"):
            identifier = str(uuid4())
            ids.append(identifier)
            record = {"id": identifier, "state": state,
                      "created_at": datetime.now(timezone.utc).isoformat(),
                      "updated_at": datetime.now(timezone.utc).isoformat(),
                      "progress": {"stage": state, "details": {}}, "result": None, "error": None}
            (self.directory / f"{identifier}.json").write_text(json.dumps(record))
        jobs = self.manager(lambda *_args: {})
        self.assertFalse(jobs.busy)
        for identifier in ids:
            interrupted = jobs.get(identifier)
            self.assertEqual(interrupted["state"], "interrupted")
            self.assertIn("заново", interrupted["error"])
            self.assertIsNone(interrupted["result"])
            self.assertEqual(json.loads((self.directory / f"{identifier}.json").read_text())["state"], "interrupted")

    def test_value_error_is_actionable_but_sanitized_generic_exception_is_type_only(self):
        for exception in (ValueError("Bad symbol; token=private-secret https://example.com/x?sig=private-secret"),
                          RuntimeError("private-secret https://example.com/credential")):
            def worker(*_args):
                raise exception
            jobs = self.manager(worker)
            initial = jobs.start({})
            failed = self.finish(jobs, initial["id"])
            self.assertEqual(failed["state"], "failed")
            self.assertIsNone(failed["result"])
            self.assertNotIn("private-secret", failed["error"])
            self.assertNotIn("https://", failed["error"])
            self.assertNotIn("Traceback", failed["error"])
            self.assertEqual(failed["error_type"], type(exception).__name__)
            if isinstance(exception, ValueError):
                self.assertIn("Bad symbol", failed["error"])
            else:
                self.assertIn("RuntimeError", failed["error"])

    def test_environment_and_nested_config_credentials_never_escape_progress_or_report(self):
        def worker(payload, progress):
            progress("research", {"token": "secret-env-value", "message": "Bearer secret-env-value"})
            return {"api_key": "secret-env-value", "diagnostic": "secret-env-value secret-input-value",
                    "source_url": "https://query1.finance.yahoo.com/v8/finance/chart/AAPL"}
        with patch.dict(os.environ, {"GH_TOKEN": "secret-env-value"}):
            jobs = self.manager(worker)
            initial = jobs.start({"config": {"api_key": "secret-input-value"}})
            complete = self.finish(jobs, initial["id"])
        encoded = json.dumps(complete)
        self.assertNotIn("secret-env-value", encoded)
        self.assertNotIn("secret-input-value", encoded)
        self.assertNotIn("api_key", complete["result"])
        self.assertEqual(complete["result"]["source_url"], "https://query1.finance.yahoo.com/v8/finance/chart/AAPL")
        self.assertNotIn("secret-env-value", (self.directory / f"{initial['id']}.json").read_text())

    def test_invalid_progress_and_nonfinite_report_fail_cleanly(self):
        def bad_progress(_payload, progress):
            progress("testing", {"score": float("nan")})
            return {}
        for worker in (bad_progress, lambda *_args: {"score": float("inf")}, lambda *_args: ["not a report"]):
            jobs = self.manager(worker)
            initial = jobs.start({})
            failed = self.finish(jobs, initial["id"])
            self.assertEqual(failed["state"], "failed")
            self.assertIsNone(failed["result"])
            json.dumps(failed, allow_nan=False)
            persisted = (self.directory / f"{initial['id']}.json").read_text()
            self.assertNotIn("NaN", persisted)
            self.assertNotIn("Infinity", persisted)

    def test_invalid_inputs_create_no_job_and_unknown_keys_are_not_forwarded(self):
        jobs = self.manager(lambda *_args: {})
        self.assertIsNone(jobs.latest())
        for payload in ([], {"config": {"risk_pct": float("nan")}}):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                jobs.start(payload)
        self.assertEqual(list(self.directory.iterdir()), [])
        received = []
        jobs.worker = lambda payload, _progress: received.append(payload) or {}
        initial = jobs.start({"source": "yahoo", "arbitrary_credential": "hidden"})
        self.finish(jobs, initial["id"])
        self.assertEqual(received, [{"source": "yahoo"}])

    def test_path_traversal_and_malformed_job_ids_are_rejected(self):
        jobs = self.manager(lambda *_args: {})
        initial = jobs.start({})
        self.finish(jobs, initial["id"])
        self.assertEqual(jobs.get(initial["id"].replace("-", ""))["id"], initial["id"])
        for identifier in ("../context", "/etc/passwd", "a/" + initial["id"], "latest", "a" * 31,
                           initial["id"] + ".json", None):
            with self.subTest(identifier=identifier), self.assertRaises(ValueError):
                jobs.get(identifier)
        with self.assertRaisesRegex(ValueError, "не найдено"):
            jobs.get(str(uuid4()))

    def test_mutating_returned_snapshot_cannot_mutate_job(self):
        jobs = self.manager(lambda *_args: {"items": ["AAPL"]})
        initial = jobs.start({})
        complete = self.finish(jobs, initial["id"])
        complete["result"]["items"].append("modified")
        self.assertEqual(jobs.get(initial["id"])["result"]["items"], ["AAPL"])

    def test_persistence_error_releases_busy_and_removes_uncertain_result(self):
        entered = threading.Event()
        def worker(*_args):
            entered.set()
            self.release.wait(timeout=3)
            return {"profit": 42}
        jobs = self.manager(worker)
        initial = jobs.start({})
        self.assertTrue(entered.wait(timeout=2))
        with patch.object(jobs, "_save", side_effect=OSError("disk failure")):
            self.release.set()
            failed = self.finish(jobs, initial["id"])
        self.assertEqual(failed["state"], "failed")
        self.assertEqual(failed["error_type"], "PersistenceError")
        self.assertIsNone(failed["result"])
        reopened = self.manager(lambda *_args: {})
        self.assertEqual(reopened.get(initial["id"])["state"], "interrupted")

    def test_frozen_training_lock_survives_worker_failure_and_reopening(self):
        lock = {"training_candidate": "ema_pullback", "params": {"fast": 12}, "holdout_hash": "frozen"}
        def worker(_payload, progress):
            progress("training_locked", {"lock": lock, "token": "hidden-lock-token"})
            raise ValueError("Later data fetch failed")
        jobs = self.manager(worker)
        initial = jobs.start({})
        failed = self.finish(jobs, initial["id"])
        self.assertEqual(failed["last_progress"]["stage"], "training_locked")
        self.assertEqual(failed["last_progress"]["details"]["lock"], lock)
        self.assertNotIn("token", failed["last_progress"]["details"])
        reopened = self.manager(lambda *_args: {})
        self.assertEqual(reopened.get(initial["id"])["last_progress"], failed["last_progress"])

    def test_frozen_training_lock_survives_crash_interruption(self):
        self.directory.mkdir()
        identifier = str(uuid4())
        progress = {"stage": "training_locked", "details": {"candidate": "ema_pullback", "holdout_hash": "frozen"}}
        record = {"id": identifier, "state": "running", "created_at": "2026-10-01T00:00:00Z",
                  "updated_at": "2026-10-01T00:01:00Z", "progress": progress, "result": None, "error": None}
        (self.directory / f"{identifier}.json").write_text(json.dumps(record))
        jobs = self.manager(lambda *_args: {})
        interrupted = jobs.get(identifier)
        self.assertEqual(interrupted["state"], "interrupted")
        self.assertEqual(interrupted["last_progress"], progress)
        reopened = self.manager(lambda *_args: {})
        self.assertEqual(reopened.get(identifier)["last_progress"], progress)

    def test_deep_inputs_and_oversized_progress_are_bounded(self):
        jobs = self.manager(lambda *_args: {})
        nested = {}
        for _index in range(70):
            nested = {"nested": nested}
        with self.assertRaisesRegex(ValueError, "глубокая"):
            jobs.start({"config": nested})
        def worker(_payload, progress):
            progress("research", {"message": "x" * 1024})
            return {}
        jobs.worker = worker
        with patch("propdesk.jobs._MAX_PROGRESS_BYTES", 100):
            initial = jobs.start({})
            self.assertEqual(self.finish(jobs, initial["id"])["state"], "failed")


if __name__ == "__main__":
    unittest.main()
