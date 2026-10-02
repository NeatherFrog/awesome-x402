"""Bounded durable research jobs through official, subscription-auth Codex CLI.

The model receives a frozen public/project context in a read-only sandbox. Only
the surrounding Python worker writes artifacts. Jobs cannot execute trades,
change source files, reset subscription quotas or silently switch to API billing.
"""
from __future__ import annotations

import hashlib
import json
import os
from contextlib import contextmanager
from pathlib import Path
import re
import shutil
import signal
import sqlite3
import subprocess
import threading
import time
import uuid

KINDS = ("source_audit", "hypothesis_review", "result_review")
RUNNER_VERSION = "subscription-research-v1"
MAX_CONTEXT_BYTES = 96_000
MAX_QUESTION_BYTES = 8_000
MAX_OUTPUT_BYTES = 2_000_000
MAX_STDERR_BYTES = 128_000
_QUOTA = re.compile(r"usage limit|quota exceeded|rate limit|rate_limit|usage_limit|insufficient_quota|too many requests|limit reached", re.I)
_AUTH = re.compile(r"not logged in|authentication failed|unauthorized|invalid api key|token expired|refresh token.*failed", re.I)
_RUNTIME = re.compile(r"Error:.*(?:failed to initialize|read-only file system|permission denied)|unexpected argument", re.I)
_SECRET = re.compile(r"(?i)(authorization\s*:\s*bearer\s+|(?:api[_ -]?key|access[_ -]?token|refresh[_ -]?token|password)\s*[=:]\s*)[^\s,;]+")
REPORT_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["summary", "hypotheses", "sources", "limitations", "next_tests"],
    "properties": {
        "summary": {"type": "string"},
        "hypotheses": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["name", "rules", "why_might_work", "why_might_fail"],
            "properties": {key: {"type": "string"} for key in
                           ("name", "rules", "why_might_work", "why_might_fail")}}},
        "sources": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["url", "title", "access_status"],
            "properties": {"url": {"type": "string"}, "title": {"type": "string"},
                           "access_status": {"type": "string", "enum": ["checked", "unavailable", "unverified"]}}}},
        "limitations": {"type": "array", "items": {"type": "string"}},
        "next_tests": {"type": "array", "items": {"type": "string"}},
    },
}


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _redact(text):
    return _SECRET.sub(lambda match: match.group(1) + "[REDACTED]", text)


def _atomic(path, text):
    path = Path(path)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def _positive_int(value, name, maximum):
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
        raise ValueError(f"{name} must be an integer between 1 and {maximum}")
    return value


class ResearchQueue:
    """Transactional deduplication, recoverable leases, and a global pause latch."""

    def __init__(self, repo_root, *, root=None, max_jobs=1000, max_attempts=3):
        self.repo_root = Path(repo_root).resolve()
        self.root = Path(root).resolve() if root is not None else self.repo_root / ".local" / "research-jobs"
        self.max_jobs = _positive_int(max_jobs, "max_jobs", 10000)
        self.max_attempts = _positive_int(max_attempts, "max_attempts", 3)
        self.root.mkdir(parents=True, exist_ok=True)
        self.database = self.root / "queue.sqlite3"
        with self._db() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS jobs (
                  id TEXT PRIMARY KEY, payload TEXT NOT NULL, status TEXT NOT NULL,
                  created REAL NOT NULL, updated REAL NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
                  available REAL NOT NULL, owner TEXT, lease_until REAL, error TEXT,
                  artifact TEXT, usage TEXT);
                CREATE TABLE IF NOT EXISTS control (
                  singleton INTEGER PRIMARY KEY CHECK(singleton=1), pause_reason TEXT,
                  cooldown_until REAL NOT NULL DEFAULT 0, worker_owner TEXT, worker_lease REAL);
                INSERT OR IGNORE INTO control(singleton) VALUES(1);
            """)

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.database, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def enqueue(self, kind, question, *, context_files=(), now=None):
        if kind not in KINDS:
            raise ValueError("kind must be source_audit, hypothesis_review or result_review")
        if not isinstance(question, str) or not question.strip() or len(question.encode()) > MAX_QUESTION_BYTES:
            raise ValueError("question must be nonempty UTF-8 text of at most 8000 bytes")
        if not isinstance(context_files, (list, tuple)) or len(context_files) > 12:
            raise ValueError("context_files must list at most 12 approved project files")
        context, count = {}, 0
        for name in context_files:
            if not isinstance(name, str):
                raise ValueError("context paths must be relative strings")
            relative = Path(name)
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError("context paths cannot escape the project")
            if not ((relative.parts and relative.parts[0] == "docs" and relative.suffix in (".md", ".json"))
                    or relative.as_posix() == "propdesk/liquidity.py"):
                raise ValueError("only docs/*.md, docs/*.json and propdesk/liquidity.py are approved context")
            path = (self.repo_root / relative).resolve()
            if not path.is_relative_to(self.repo_root) or not path.is_file():
                raise ValueError("context must be an existing project file, without external symlinks")
            # Bound the read itself; a huge local result cannot exhaust memory.
            with path.open("rb") as stream:
                data = stream.read(MAX_CONTEXT_BYTES + 1)
            count += len(data)
            if count > MAX_CONTEXT_BYTES:
                raise ValueError("combined context exceeds 96000 bytes")
            try:
                context[relative.as_posix()] = data.decode("utf-8")
            except UnicodeDecodeError:
                raise ValueError("context must be UTF-8 text") from None
        payload = {"kind": kind, "question": question.strip(), "context": context, "version": RUNNER_VERSION}
        encoded = _json(payload)
        job_id = hashlib.sha256(encoded.encode()).hexdigest()
        stamp = time.time() if now is None else float(now)
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM jobs WHERE id=?", (job_id,)).fetchone():
                return job_id
            if db.execute("SELECT count(*) FROM jobs").fetchone()[0] >= self.max_jobs:
                raise ValueError("durable queue job cap reached")
            db.execute("INSERT INTO jobs(id,payload,status,created,updated,available) VALUES(?,?,?,?,?,?)",
                       (job_id, encoded, "queued", stamp, stamp, stamp))
        return job_id

    def status(self):
        with self._db() as db:
            control = dict(db.execute("SELECT * FROM control WHERE singleton=1").fetchone())
            counts = {row[0]: row[1] for row in db.execute("SELECT status,count(*) FROM jobs GROUP BY status")}
            return {"counts": counts, "pause_reason": control["pause_reason"],
                    "cooldown_until": control["cooldown_until"],
                    "usage_available": False, "remaining_subscription_tokens": None}

    def get(self, job_id):
        with self._db() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            raise KeyError(job_id)
        result = dict(row)
        result["payload"] = json.loads(result["payload"])
        result["usage"] = json.loads(result["usage"]) if result["usage"] else None
        return result

    def pause(self, reason, *, now=None, cooldown_seconds=0):
        stamp = time.time() if now is None else float(now)
        with self._db() as db:
            db.execute("UPDATE control SET pause_reason=?,cooldown_until=? WHERE singleton=1",
                       (reason, stamp + cooldown_seconds))

    def resume(self, *, now=None):
        stamp = time.time() if now is None else float(now)
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT cooldown_until FROM control WHERE singleton=1").fetchone()
            if row[0] > stamp:
                raise ValueError("cooldown has not elapsed; no automatic quota retry/reset")
            db.execute("UPDATE control SET pause_reason=NULL,cooldown_until=0 WHERE singleton=1")

    def acquire_worker(self, owner, *, now=None, lease_seconds=30):
        stamp = time.time() if now is None else float(now)
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM control WHERE singleton=1").fetchone()
            if row["pause_reason"] or (row["worker_owner"] and row["worker_owner"] != owner and row["worker_lease"] > stamp):
                return False
            db.execute("UPDATE control SET worker_owner=?,worker_lease=? WHERE singleton=1", (owner, stamp + lease_seconds))
        return True

    def release_worker(self, owner):
        with self._db() as db:
            db.execute("UPDATE control SET worker_owner=NULL,worker_lease=NULL WHERE singleton=1 AND worker_owner=?", (owner,))

    def claim(self, owner, *, now=None, lease_seconds=30):
        stamp = time.time() if now is None else float(now)
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM control WHERE singleton=1").fetchone()
            if row["pause_reason"] or row["worker_owner"] != owner or row["worker_lease"] <= stamp:
                return None
            db.execute("UPDATE jobs SET status=CASE WHEN attempts>=? THEN 'failed' ELSE 'queued' END,"
                       "owner=NULL,lease_until=NULL,error='worker lease expired',updated=? "
                       "WHERE status='running' AND lease_until<=?", (self.max_attempts, stamp, stamp))
            job = db.execute("SELECT * FROM jobs WHERE status='queued' AND available<=? ORDER BY created,id LIMIT 1", (stamp,)).fetchone()
            if job is None:
                return None
            db.execute("UPDATE jobs SET status='running',owner=?,lease_until=?,attempts=attempts+1,updated=? WHERE id=?",
                       (owner, stamp + lease_seconds, stamp, job["id"]))
        return self.get(job["id"])

    def heartbeat(self, owner, job_id=None, *, now=None, lease_seconds=30):
        stamp = time.time() if now is None else float(now)
        with self._db() as db:
            changed = db.execute("UPDATE control SET worker_lease=? WHERE singleton=1 AND worker_owner=?", (stamp + lease_seconds, owner)).rowcount
            if not changed:
                raise RuntimeError("worker lease ownership lost")
            if job_id is not None:
                changed = db.execute("UPDATE jobs SET lease_until=?,updated=? WHERE id=? AND owner=? AND status='running'",
                                     (stamp + lease_seconds, stamp, job_id, owner)).rowcount
                if not changed:
                    raise RuntimeError("job lease ownership lost")

    def finish(self, job_id, owner, result, *, now=None):
        stamp = time.time() if now is None else float(now)
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT attempts FROM jobs WHERE id=? AND owner=? AND status='running'", (job_id, owner)).fetchone()
            if row is None:
                raise RuntimeError("cannot finish a job without its active lease")
            outcome = result["outcome"]
            retry = outcome in ("timeout", "transient_error") and row["attempts"] < self.max_attempts
            status = "completed" if outcome == "success" else "queued" if retry or outcome in ("quota", "auth", "runtime_unavailable") else "failed"
            available = stamp + min(3600, 60 * 2 ** (row["attempts"] - 1)) if retry else stamp
            db.execute("UPDATE jobs SET status=?,updated=?,available=?,owner=NULL,lease_until=NULL,error=?,artifact=?,usage=? WHERE id=?",
                       (status, stamp, available, result.get("error"), result.get("artifact"),
                        _json(result["usage"]) if result.get("usage") else None, job_id))
            if outcome in ("quota", "auth", "runtime_unavailable"):
                db.execute("UPDATE control SET pause_reason=?,cooldown_until=? WHERE singleton=1",
                           (outcome, stamp + 3600 if outcome == "quota" else stamp))

    def export(self):
        with self._db() as db:
            rows = [dict(row) for row in db.execute("SELECT id,status,created,updated,attempts,error,artifact,usage FROM jobs ORDER BY created,id")]
        for row in rows:
            row["usage"] = json.loads(row["usage"]) if row["usage"] else None
        result = {"version": RUNNER_VERSION, "status": self.status(), "jobs": rows}
        _atomic(self.root / "registry.json", _json(result))
        return result


def validate_report(report):
    if not isinstance(report, dict) or set(report) != set(REPORT_SCHEMA["required"]):
        raise ValueError("report must match the declared research schema")
    if not isinstance(report["summary"], str) or not report["summary"].strip() or len(report["summary"]) > 16000:
        raise ValueError("report summary must contain bounded text")
    for key in ("hypotheses", "sources", "limitations", "next_tests"):
        if not isinstance(report[key], list) or len(report[key]) > 30:
            raise ValueError("report arrays must contain at most 30 entries")
    if not report["limitations"]:
        raise ValueError("research must declare limitations")
    for key in ("limitations", "next_tests"):
        if any(not isinstance(item, str) or len(item) > 8000 for item in report[key]):
            raise ValueError("report text must be bounded")
    required = set(REPORT_SCHEMA["properties"]["hypotheses"]["items"]["required"])
    for item in report["hypotheses"]:
        if not isinstance(item, dict) or set(item) != required or any(not isinstance(value, str) or len(value) > 8000 for value in item.values()):
            raise ValueError("hypothesis schema mismatch")
    for item in report["sources"]:
        if (not isinstance(item, dict) or set(item) != {"url", "title", "access_status"}
                or not isinstance(item["url"], str) or not item["url"].startswith("https://")
                or len(item["url"]) > 2000 or not isinstance(item["title"], str) or len(item["title"]) > 4000
                or item["access_status"] not in ("checked", "unavailable", "unverified")):
            raise ValueError("source schema mismatch; sources require HTTPS and access attribution")
    return report


class CodexExecutor:
    def __init__(self, repo_root, *, executable=None, enable_web=True):
        self.repo_root = Path(repo_root).resolve()
        self.executable = executable or shutil.which("codex")
        self.enable_web = enable_web

    @staticmethod
    def environment():
        # Subscription auth is reused by CLI from its ordinary home. Neither
        # OPENAI_API_KEY nor alternate-provider/billing variables are forwarded.
        approved = ("PATH", "HOME", "CODEX_HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "SYSTEMROOT",
                    "WINDIR", "TEMP", "TMP", "LANG", "LC_ALL", "SSL_CERT_FILE", "SSL_CERT_DIR",
                    "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
                    "http_proxy", "https_proxy", "all_proxy", "no_proxy")
        return {key: os.environ[key] for key in approved if key in os.environ}

    def preflight(self):
        if not self.executable:
            return {"ready": False, "reason": "official Codex CLI is not installed"}
        def read(args):
            return subprocess.run([self.executable, *args], cwd=self.repo_root, env=self.environment(),
                                  capture_output=True, text=True, timeout=15)
        try:
            auth = read(["login", "status"])
            help_result = read(["exec", "--help"])
            version = read(["--version"])
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {"ready": False, "reason": type(exc).__name__}
        auth_text = auth.stdout + auth.stderr
        if auth.returncode or "logged in using chatgpt" not in auth_text.lower():
            return {"ready": False, "reason": "ChatGPT subscription login is required; API-key authentication is refused"}
        required = ("--output-schema", "--output-last-message", "--json", "--ephemeral", "--ignore-user-config", "--strict-config", "read-only")
        if help_result.returncode or any(flag not in help_result.stdout for flag in required):
            return {"ready": False, "reason": "installed Codex CLI lacks required safe noninteractive flags"}
        return {"ready": True, "auth": "ChatGPT", "version": version.stdout.strip(),
                "runtime_execution_verified": False,
                "usage_available": False, "remaining_subscription_tokens": None}

    def command(self, artifact):
        # Official rust-v0.159.0-alpha.3 schema explicitly supports these state
        # paths. Auth stays at the ORIGINAL CODEX_HOME; no credentials are copied.
        command = [self.executable, "--strict-config",
                   "-c", "sqlite_home=" + _json(str(artifact / "runtime" / "sqlite")),
                   "-c", "log_dir=" + _json(str(artifact / "runtime" / "logs")),
                   "-c", 'history.persistence="none"']
        if self.enable_web:
            command.append("--search")
        command += ["exec", "--sandbox", "read-only", "--ephemeral", "--ignore-user-config",
                    "--json", "--color", "never", "--skip-git-repo-check", "--cd", str(artifact / "context"),
                    "--output-schema", str(artifact / "schema.json"),
                    "--output-last-message", str(artifact / "final.json"), "-"]
        return command

    @staticmethod
    def _terminate(process):
        if process.poll() is not None:
            return
        if os.name == "nt":
            try:
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                               capture_output=True, timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                process.kill()
        else:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        process.wait(timeout=5)

    def execute(self, job, artifact, *, timeout_seconds=900, heartbeat=None):
        artifact = Path(artifact)
        artifact.mkdir(parents=True, exist_ok=False)
        context = artifact / "context"
        context.mkdir()
        (artifact / "runtime" / "sqlite").mkdir(parents=True)
        (artifact / "runtime" / "logs").mkdir(parents=True)
        for name, text in job["payload"]["context"].items():
            path = context / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            path.chmod(0o444)
        _atomic(artifact / "schema.json", _json(REPORT_SCHEMA))
        prompt = ("You are a bounded trading-research reviewer. Work in read-only mode. "
                  "Read the supplied frozen context before evaluating this ONE task. "
                  "You may inspect public primary sources via native web search. "
                  "Mark inaccessible or unverified sources honestly; do not claim to have read paid courses. "
                  "Never inspect credentials, private account files or environment secrets. "
                  "Do not change source, place orders, send notifications, deploy, publish, or install tools. "
                  "Do not infer stable profitability from a chart, author claim or retrospective backtest. "
                  "Include causality, costs, selection bias, failure conditions and concrete next tests. "
                  "Source access_status is your attribution, not independent verification. "
                  "Return only the schema-conforming final JSON report.\n"
                  + _json({"kind": job["payload"]["kind"], "question": job["payload"]["question"],
                           "context_files": list(job["payload"]["context"])}))
        _atomic(artifact / "request.json", _json({"id": job["id"], "payload": job["payload"], "sandbox": "read-only"}))
        options = {"start_new_session": True} if os.name != "nt" else {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
        try:
            process = subprocess.Popen(self.command(artifact), cwd=context, env=self.environment(),
                                       stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **options)
        except OSError as exc:
            return {"outcome": "transient_error", "error": type(exc).__name__, "artifact": str(artifact), "usage": None}
        streams = {"stdout": bytearray(), "stderr": bytearray()}
        signals = {"overflow": False, "quota": False, "auth": False, "runtime": False}

        def drain(name, stream, cap):
            pending_line = b""
            while True:
                block = stream.read1(4096) if hasattr(stream, "read1") else stream.read(4096)
                if not block:
                    break
                room = cap - len(streams[name])
                if len(block) > room:
                    signals["overflow"] = True
                streams[name].extend(block[:max(0, room)])
                if name == "stderr":
                    sample = bytes(streams[name][-12000:]).decode("utf-8", "replace")
                    signals["quota"] = signals["quota"] or bool(_QUOTA.search(sample))
                    signals["auth"] = signals["auth"] or bool(_AUTH.search(sample))
                    signals["runtime"] = signals["runtime"] or bool(_RUNTIME.search(sample))
                else:
                    pending_line += block
                    lines = pending_line.split(b"\n")
                    pending_line = lines.pop()[-MAX_OUTPUT_BYTES:]
                    for line in lines:
                        try:
                            event = json.loads(line)
                        except (ValueError, TypeError):
                            continue
                        # Research text about rate limits is not a provider
                        # quota error. Only formal CLI error events pause work.
                        if not isinstance(event, dict):
                            continue
                        item = event.get("item")
                        is_error = (event.get("type") in ("error", "turn.failed")
                                    or "error" in event
                                    or isinstance(item, dict) and item.get("type") == "error")
                        if is_error:
                            sample = _json(event)
                            signals["quota"] = signals["quota"] or bool(_QUOTA.search(sample))
                            signals["auth"] = signals["auth"] or bool(_AUTH.search(sample))

        threads = [threading.Thread(target=drain, args=("stdout", process.stdout, MAX_OUTPUT_BYTES), daemon=True),
                   threading.Thread(target=drain, args=("stderr", process.stderr, MAX_STDERR_BYTES), daemon=True)]
        for thread in threads:
            thread.start()
        def feed_prompt():
            try:
                process.stdin.write(prompt.encode("utf-8"))
            except (BrokenPipeError, OSError):
                pass
            finally:
                try:
                    process.stdin.close()
                except (BrokenPipeError, OSError):
                    pass
        feeder = threading.Thread(target=feed_prompt, daemon=True)
        feeder.start()
        deadline, next_heartbeat = time.monotonic() + timeout_seconds, time.monotonic()
        outcome = None
        try:
            while process.poll() is None:
                final_path = artifact / "final.json"
                if final_path.exists() and final_path.stat().st_size > 256000:
                    signals["overflow"] = True
                if signals["quota"] or signals["auth"] or signals["runtime"] or signals["overflow"]:
                    outcome = "quota" if signals["quota"] else "auth" if signals["auth"] else "runtime_unavailable" if signals["runtime"] else "output_limit"
                    self._terminate(process)
                    break
                if time.monotonic() >= deadline:
                    outcome = "timeout"
                    self._terminate(process)
                    break
                if heartbeat and time.monotonic() >= next_heartbeat:
                    heartbeat()
                    next_heartbeat = time.monotonic() + 5
                time.sleep(.05)
        except BaseException:
            self._terminate(process)
            raise
        finally:
            for thread in threads:
                thread.join(timeout=5)
            feeder.join(timeout=5)
            process.stdout.close()
            process.stderr.close()
        stdout = _redact(bytes(streams["stdout"]).decode("utf-8", "replace")).encode()[:MAX_OUTPUT_BYTES].decode("utf-8", "ignore")
        stderr = _redact(bytes(streams["stderr"]).decode("utf-8", "replace")).encode()[:MAX_STDERR_BYTES].decode("utf-8", "ignore")
        final_path = artifact / "final.json"
        if final_path.exists() and final_path.stat().st_size > 256000:
            with final_path.open("r+b") as stream:
                stream.truncate(256000)
            signals["overflow"] = True
        _atomic(artifact / "events.jsonl", stdout)
        _atomic(artifact / "stderr.txt", stderr)
        usage = None
        for line in stdout.splitlines():
            try:
                event = json.loads(line)
            except (ValueError, TypeError):
                continue
            if isinstance(event, dict) and event.get("type") == "turn.completed" and isinstance(event.get("usage"), dict):
                supplied = event["usage"]
                numeric = {key: value for key, value in supplied.items()
                           if key in ("input_tokens", "cached_input_tokens", "output_tokens")
                           and isinstance(value, int) and not isinstance(value, bool) and value >= 0}
                usage = numeric or None
        if outcome is None:
            outcome = "quota" if signals["quota"] else "auth" if signals["auth"] else "runtime_unavailable" if signals["runtime"] else "output_limit" if signals["overflow"] else "transient_error" if process.returncode else "success"
        error = None if outcome == "success" else outcome
        if outcome == "success":
            try:
                path = artifact / "final.json"
                if path.stat().st_size > 256000:
                    raise ValueError("final report exceeds 256000 bytes")
                report = validate_report(json.loads(path.read_text(encoding="utf-8")))
                _atomic(artifact / "report.json", _json({"job_id": job["id"], "report": report,
                         "provenance": {"auth": "ChatGPT", "sandbox": "read-only", "usage": usage,
                                        "source_access_independently_verified": False,
                                        "qualified_for_live_trading": False}}))
            except (OSError, ValueError, TypeError) as exc:
                outcome, error = "invalid_report", str(exc)[:1000]
        result = {"outcome": outcome, "error": error, "artifact": str(artifact), "usage": usage}
        _atomic(artifact / "result.json", _json(result))
        return result


class ResearchWorker:
    def __init__(self, queue, *, executor=None):
        self.queue = queue
        self.executor = executor or CodexExecutor(queue.repo_root)
        self.owner = str(uuid.uuid4())

    def run(self, *, max_jobs=100, max_session_hours=24, task_timeout_seconds=900,
            idle_wait_seconds=0, stop_event=None):
        max_jobs = _positive_int(max_jobs, "max_jobs", 1000)
        if not isinstance(max_session_hours, (int, float)) or isinstance(max_session_hours, bool) or not 0 < max_session_hours <= 24:
            raise ValueError("max_session_hours must be greater than 0 and at most 24")
        if not isinstance(task_timeout_seconds, (int, float)) or isinstance(task_timeout_seconds, bool) or not 0 < task_timeout_seconds <= 3600:
            raise ValueError("task_timeout_seconds must be greater than 0 and at most 3600")
        if not isinstance(idle_wait_seconds, (int, float)) or isinstance(idle_wait_seconds, bool) or not 0 <= idle_wait_seconds <= 60:
            raise ValueError("idle_wait_seconds must be between 0 and 60")
        state = self.queue.status()
        if state["pause_reason"]:
            return {"processed": 0, "stop_reason": state["pause_reason"]}
        preflight = self.executor.preflight()
        if not preflight.get("ready"):
            self.queue.pause("auth_or_cli_unavailable")
            return {"processed": 0, "stop_reason": "auth_or_cli_unavailable", "detail": preflight["reason"]}
        if not self.queue.acquire_worker(self.owner):
            return {"processed": 0, "stop_reason": "another_worker_or_pause"}
        deadline, processed, reason = time.monotonic() + max_session_hours * 3600, 0, "job_cap"
        try:
            while processed < max_jobs:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    reason = "session_deadline"
                    break
                if stop_event and stop_event.is_set():
                    reason = "requested_stop"
                    break
                self.queue.heartbeat(self.owner)
                job = self.queue.claim(self.owner)
                if job is None:
                    if self.queue.status()["pause_reason"]:
                        reason = self.queue.status()["pause_reason"]
                        break
                    if idle_wait_seconds:
                        wait = min(idle_wait_seconds, remaining, 10)
                        if stop_event:
                            stop_event.wait(wait)
                        else:
                            time.sleep(wait)
                        continue
                    reason = "queue_empty_or_backoff"
                    break
                artifact = self.queue.root / "artifacts" / job["id"] / f"attempt-{job['attempts']}"
                artifact.parent.mkdir(parents=True, exist_ok=True)
                result = self.executor.execute(job, artifact, timeout_seconds=min(task_timeout_seconds, remaining),
                                               heartbeat=lambda: self.queue.heartbeat(self.owner, job["id"]))
                self.queue.finish(job["id"], self.owner, result)
                processed += 1
                self.queue.export()
                if result["outcome"] in ("quota", "auth", "runtime_unavailable"):
                    reason = result["outcome"]
                    break
        finally:
            self.queue.release_worker(self.owner)
            self.queue.export()
        return {"processed": processed, "stop_reason": reason}


def seed_review_jobs(queue):
    """Six useful, deduplicated reviews, without generating infinite variations."""
    available = lambda names: [name for name in names if (queue.repo_root / name).is_file()]
    protocol = available(["docs/LIQUIDITY_PROTOCOL.md", "docs/BROAD_RESEARCH_PROTOCOL.md"])
    source_context = available(["docs/LIQUIDITY_PROTOCOL.md", "docs/EXCHANGE_SOURCES.md"])
    jobs = [queue.enqueue("source_audit",
            "Audit primary-source evidence and executable-market assumptions behind liquidity sweeps, "
            "FVG and MSS. Distinguish mechanical definitions, author claims and independently tested evidence. "
            "Identify inaccessible sources and missing costs; do not claim stable profit.", context_files=source_context)]
    for variant in ("sweep_all", "mss_all", "sweep_lunch", "mss_lunch"):
        jobs.append(queue.enqueue("hypothesis_review",
            f"Review the frozen {variant} hypothesis. Identify causal leakage risks, market mechanisms, "
            "counterexamples, costs and falsification tests. Do not alter parameters or choose a new winner "
            "after seeing outcomes. Propose separate preregistered future experiments only.", context_files=protocol))
    results = available(["docs/LIQUIDITY_RESEARCH.md", "docs/EXPERIMENT_REGISTRY.md", "docs/LIQUIDITY_PROTOCOL.md"])
    jobs.append(queue.enqueue("result_review",
            "Independently review the recorded train/validation/holdout results and selection protocol. "
            "Assess net costs, uncertainty, forced boundary exits, spot-short executability and regime robustness. "
            "State clearly whether any claim of stable profit is supported; no new optimization.", context_files=results))
    queue.export()
    return jobs
