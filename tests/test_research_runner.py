"""Durability, quota/auth boundaries and real subprocess shutdown behavior."""
from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from propdesk.research_runner import (CodexExecutor, ResearchQueue, ResearchWorker,
                                     MAX_OUTPUT_BYTES, seed_review_jobs, validate_report)


REPORT = {"summary": "Unqualified research review", "hypotheses": [], "sources": [],
          "limitations": ["No evidence of stable profitability"], "next_tests": ["Frozen future validation"]}
FAKE_CLI = r'''
import json,os,sys,time
mode,final=sys.argv[1:]
if mode=='timeout':
 time.sleep(20)
if mode=='quota':
 print(json.dumps({'type':'error','message':'You have hit your usage limit. Please try later.'}),flush=True)
 time.sleep(20)
if mode=='auth':
 print('Authentication failed: token expired',file=sys.stderr,flush=True)
 time.sleep(20)
if mode=='runtime':
 print('Error: failed to initialize in-process app-server client: Read-only file system',file=sys.stderr,flush=True)
 time.sleep(20)
if mode=='overflow':
 sys.stdout.write('x'*2200000)
 sys.stdout.flush()
 time.sleep(20)
if mode=='failure':
 print('Network temporarily unavailable',file=sys.stderr)
 sys.exit(1)
if mode=='redact':
 print('Authorization: Bearer test-secret-value',file=sys.stderr)
 sys.exit(1)
request=sys.stdin.read()
report={'summary':'No API secret inherited' if 'OPENAI_API_KEY' not in os.environ else 'API SECRET PRESENT',
        'hypotheses':[],'sources':[],'limitations':['Unqualified review; rate limits and quota exceeded are concepts'],
        'next_tests':['Future validation']}
if mode=='invalid':report={'summary':'Missing required research fields'}
if mode=='large_final':
 open(final,'w').write('x'*300000)
else:
 open(final,'w').write(json.dumps(report))
print(json.dumps({'type':'item.completed','item':{'type':'agent_message','text':'Discuss quota exceeded as a phrase, not an account error'}}))
print(json.dumps({'type':'turn.completed','usage':{'input_tokens':120,'cached_input_tokens':60,'output_tokens':20}}))
'''


class FixtureExecutor(CodexExecutor):
    def __init__(self, repo, script, mode="success"):
        super().__init__(repo, executable=sys.executable, enable_web=False)
        self.script, self.mode = script, mode

    def preflight(self):
        return {"ready": True, "auth": "ChatGPT"}

    def command(self, artifact):
        return [sys.executable, str(self.script), self.mode, str(artifact / "final.json")]


class QueueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        (self.repo / "docs").mkdir()
        (self.repo / "docs" / "protocol.md").write_text("Frozen original protocol", encoding="utf-8")
        self.queue = ResearchQueue(self.repo)

    def test_dedup_survives_reopen_and_context_is_frozen(self):
        first = self.queue.enqueue("source_audit", "Audit sources", context_files=["docs/protocol.md"], now=100)
        reopened = ResearchQueue(self.repo)
        self.assertEqual(first, reopened.enqueue("source_audit", "Audit sources", context_files=["docs/protocol.md"], now=200))
        (self.repo / "docs" / "protocol.md").write_text("Changed future protocol", encoding="utf-8")
        later = reopened.enqueue("source_audit", "Audit sources", context_files=["docs/protocol.md"], now=300)
        self.assertNotEqual(first, later)
        self.assertEqual(self.queue.get(first)["payload"]["context"]["docs/protocol.md"], "Frozen original protocol")
        self.assertEqual(reopened.status()["counts"], {"queued": 2})

    def test_queue_is_bounded_without_breaking_dedup(self):
        queue = ResearchQueue(self.repo, max_jobs=1)
        first = queue.enqueue("source_audit", "One")
        self.assertEqual(first, queue.enqueue("source_audit", "One"))
        with self.assertRaisesRegex(ValueError, "cap"):
            queue.enqueue("source_audit", "Two")

    def test_credentials_and_external_context_cannot_be_seeded(self):
        for name in (".local/credentials.json", "../secret.md", "/tmp/secret.md", "propdesk/server.py"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.queue.enqueue("source_audit", "Audit", context_files=[name])
        outside = self.repo.parent / (self.repo.name + "-outside.md")
        outside.write_text("outside", encoding="utf-8")
        self.addCleanup(outside.unlink)
        try:
            (self.repo / "docs" / "link.md").symlink_to(outside)
        except OSError:
            return
        with self.assertRaises(ValueError):
            self.queue.enqueue("source_audit", "Audit", context_files=["docs/link.md"])

    def test_expired_worker_and_job_leases_recover_but_stale_finish_fails(self):
        job = self.queue.enqueue("source_audit", "Audit", now=100)
        self.assertTrue(self.queue.acquire_worker("first", now=100))
        self.assertEqual(self.queue.claim("first", now=100)["attempts"], 1)
        self.assertFalse(self.queue.acquire_worker("second", now=110))
        self.assertTrue(self.queue.acquire_worker("second", now=131))
        self.assertEqual(self.queue.claim("second", now=131)["attempts"], 2)
        with self.assertRaises(RuntimeError):
            self.queue.finish(job, "first", {"outcome": "success"}, now=132)
        self.queue.finish(job, "second", {"outcome": "success"}, now=132)
        self.assertEqual(self.queue.get(job)["status"], "completed")

    def test_repeated_crashes_have_three_attempt_cap(self):
        job = self.queue.enqueue("source_audit", "Audit", now=100)
        for attempt in range(3):
            stamp = 100 + attempt * 31
            owner = str(attempt)
            self.assertTrue(self.queue.acquire_worker(owner, now=stamp))
            self.assertEqual(self.queue.claim(owner, now=stamp)["attempts"], attempt + 1)
        self.assertTrue(self.queue.acquire_worker("fourth", now=193))
        self.assertIsNone(self.queue.claim("fourth", now=193))
        self.assertEqual(self.queue.get(job)["status"], "failed")

    def test_quota_latches_all_jobs_and_resume_requires_cooldown(self):
        job = self.queue.enqueue("source_audit", "Audit", now=100)
        self.queue.acquire_worker("owner", now=100)
        self.queue.claim("owner", now=100)
        self.queue.finish(job, "owner", {"outcome": "quota", "error": "quota"}, now=101)
        self.assertEqual(self.queue.status()["pause_reason"], "quota")
        self.assertEqual(self.queue.get(job)["status"], "queued")
        self.assertIsNone(self.queue.claim("owner", now=102))
        with self.assertRaisesRegex(ValueError, "cooldown"):
            self.queue.resume(now=102)
        self.queue.resume(now=3701)
        self.assertIsNone(self.queue.status()["pause_reason"])

    def test_transient_retry_is_delayed_not_busy_loop(self):
        job = self.queue.enqueue("source_audit", "Audit", now=100)
        self.queue.acquire_worker("owner", now=100, lease_seconds=200)
        self.queue.claim("owner", now=100, lease_seconds=200)
        self.queue.finish(job, "owner", {"outcome": "timeout", "error": "timeout"}, now=101)
        self.assertIsNone(self.queue.claim("owner", now=160))
        self.assertEqual(self.queue.claim("owner", now=161)["attempts"], 2)

    def test_seed_reviews_are_useful_finite_and_idempotent(self):
        first, second = seed_review_jobs(self.queue), seed_review_jobs(self.queue)
        self.assertEqual(first, second)
        self.assertEqual(len(first), 6)
        self.assertEqual(self.queue.status()["counts"], {"queued": 6})
        self.assertIsNone(self.queue.export()["status"]["remaining_subscription_tokens"])


class ProcessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        self.script = self.repo / "fake_cli.py"
        self.script.write_text(FAKE_CLI, encoding="utf-8")
        self.queue = ResearchQueue(self.repo)
        self.job_id = self.queue.enqueue("source_audit", "Review the recorded hypothesis")

    def execute(self, mode, timeout=2):
        executor = FixtureExecutor(self.repo, self.script, mode)
        return executor.execute(self.queue.get(self.job_id), self.repo / ("artifact-" + mode), timeout_seconds=timeout)

    def test_real_fake_process_success_records_actual_usage_without_api_secrets(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-sentinel", "OPENAI_BASE_URL": "test-provider"}):
            result = self.execute("success")
        self.assertEqual(result["outcome"], "success")
        self.assertEqual(result["usage"], {"input_tokens": 120, "cached_input_tokens": 60, "output_tokens": 20})
        report = json.loads((Path(result["artifact"]) / "report.json").read_text())
        self.assertEqual(report["report"]["summary"], "No API secret inherited")
        self.assertFalse(report["provenance"]["qualified_for_live_trading"])
        self.assertFalse(report["provenance"]["source_access_independently_verified"])

    def test_quota_error_kills_process_and_pauses_worker_before_next_job(self):
        second = self.queue.enqueue("hypothesis_review", "Another useful job")
        started = time.monotonic()
        result = ResearchWorker(self.queue, executor=FixtureExecutor(self.repo, self.script, "quota")).run(max_jobs=2, task_timeout_seconds=10)
        self.assertLess(time.monotonic() - started, 3)
        self.assertEqual(result, {"processed": 1, "stop_reason": "quota"})
        self.assertEqual(self.queue.get(second)["attempts"], 0)
        self.assertEqual(self.queue.status()["pause_reason"], "quota")
        stopped = ResearchWorker(self.queue, executor=FixtureExecutor(self.repo, self.script)).run(max_jobs=1)
        self.assertEqual(stopped, {"processed": 0, "stop_reason": "quota"})

    def test_timeout_kills_process_and_preserves_retry(self):
        started = time.monotonic()
        result = ResearchWorker(self.queue, executor=FixtureExecutor(self.repo, self.script, "timeout")).run(max_jobs=2, task_timeout_seconds=.2)
        self.assertLess(time.monotonic() - started, 3)
        self.assertEqual(result["processed"], 1)
        row = self.queue.get(self.job_id)
        self.assertEqual((row["status"], row["attempts"], row["error"]), ("queued", 1, "timeout"))
        self.assertGreater(row["available"], row["updated"])

    def test_blocked_prompt_writer_cannot_escape_timeout(self):
        job_id = self.queue.enqueue("hypothesis_review", "x" * 8000)
        started = time.monotonic()
        result = FixtureExecutor(self.repo, self.script, "timeout").execute(self.queue.get(job_id), self.repo / "blocked-stdin", timeout_seconds=.2)
        self.assertEqual(result["outcome"], "timeout")
        self.assertLess(time.monotonic() - started, 3)

    def test_auth_error_stops_instead_of_api_fallback(self):
        self.assertEqual(self.execute("auth")["outcome"], "auth")

    def test_readonly_cli_state_failure_pauses_without_auth_copy_or_retries(self):
        result = ResearchWorker(self.queue, executor=FixtureExecutor(self.repo, self.script, "runtime")).run(max_jobs=2)
        self.assertEqual(result, {"processed": 1, "stop_reason": "runtime_unavailable"})
        self.assertEqual(self.queue.get(self.job_id)["status"], "queued")
        self.assertEqual(self.queue.status()["pause_reason"], "runtime_unavailable")

    def test_output_files_are_bounded(self):
        result = self.execute("overflow")
        self.assertEqual(result["outcome"], "output_limit")
        self.assertLessEqual((Path(result["artifact"]) / "events.jsonl").stat().st_size, MAX_OUTPUT_BYTES)
        final = self.execute("large_final")
        self.assertEqual(final["outcome"], "output_limit")
        self.assertLessEqual((Path(final["artifact"]) / "final.json").stat().st_size, 256000)

    def test_invalid_report_is_terminal_not_a_profitable_signal(self):
        worker = ResearchWorker(self.queue, executor=FixtureExecutor(self.repo, self.script, "invalid"))
        self.assertEqual(worker.run(max_jobs=1)["processed"], 1)
        self.assertEqual(self.queue.get(self.job_id)["status"], "failed")
        self.assertFalse((Path(self.queue.get(self.job_id)["artifact"]) / "report.json").exists())

    def test_credentials_in_cli_errors_are_redacted(self):
        result = self.execute("redact")
        log = (Path(result["artifact"]) / "stderr.txt").read_text()
        self.assertNotIn("test-secret-value", log)
        self.assertIn("[REDACTED]", log)

    def test_worker_cap_keeps_next_job_durable(self):
        second = self.queue.enqueue("result_review", "Second")
        result = ResearchWorker(self.queue, executor=FixtureExecutor(self.repo, self.script)).run(max_jobs=1)
        self.assertEqual(result, {"processed": 1, "stop_reason": "job_cap"})
        self.assertEqual(self.queue.get(second)["status"], "queued")
        reopened = ResearchQueue(self.repo)
        result = ResearchWorker(reopened, executor=FixtureExecutor(self.repo, self.script)).run(max_jobs=1)
        self.assertEqual(result["processed"], 1)
        self.assertEqual(reopened.status()["counts"], {"completed": 2})

    def test_session_and_job_limits_cannot_be_unbounded(self):
        worker = ResearchWorker(self.queue, executor=FixtureExecutor(self.repo, self.script))
        for kwargs in ({"max_jobs": 0}, {"max_jobs": 1001}, {"max_session_hours": 25},
                       {"task_timeout_seconds": 3601}, {"idle_wait_seconds": 61}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                worker.run(**kwargs)


class OfficialInterfaceTests(unittest.TestCase):
    def test_command_has_verified_safe_flags_and_no_policy_bypass(self):
        executor = CodexExecutor(Path.cwd(), executable="codex")
        command = executor.command(Path("/tmp/example-job"))
        self.assertIn("--search", command)
        self.assertEqual(command[command.index("--sandbox") + 1], "read-only")
        self.assertIn("--ignore-user-config", command)
        self.assertIn("--strict-config", command)
        self.assertTrue(any(arg.startswith("sqlite_home=") for arg in command))
        self.assertTrue(any(arg.startswith("log_dir=") for arg in command))
        self.assertIn('history.persistence="none"', command)
        self.assertFalse(any(arg.startswith("codex_home=") for arg in command))
        self.assertNotIn("--add-dir", command)
        self.assertFalse(any("dangerously" in arg for arg in command))
        self.assertNotIn("--ask-for-approval", command)

    def test_preflight_refuses_api_key_authentication(self):
        executor = CodexExecutor(Path.cwd(), executable="codex")
        with patch("propdesk.research_runner.subprocess.run", return_value=subprocess.CompletedProcess([], 0, "Logged in using an API key", "")):
            self.assertFalse(executor.preflight()["ready"])

    def test_reports_need_limits_and_access_attribution(self):
        self.assertEqual(validate_report(REPORT), REPORT)
        invalid = dict(REPORT, limitations=[])
        with self.assertRaises(ValueError):
            validate_report(invalid)
        invalid = dict(REPORT, sources=[{"url": "file:///private/key", "title": "secret", "access_status": "checked"}])
        with self.assertRaises(ValueError):
            validate_report(invalid)


if __name__ == "__main__":
    unittest.main()
