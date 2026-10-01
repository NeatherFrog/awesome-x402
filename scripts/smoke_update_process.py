"""Exercise a real packaged supervisor update using a local GitHub transport fixture.

No GitHub requests, real orders, or source checkout mutations occur. This checks
actual process restart and data preservation; it does not certify network access.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.build_distribution import build

OLD = "1" * 40
NEW = "2" * 40


class SmokeFailure(RuntimeError):
    pass


def request(port, method, path, payload=None):
    body = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json"} if payload is not None else {}
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=body, headers=headers, method=method)
    try:
        with opener.open(req, timeout=3) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        try:
            error = json.loads(exc.read(8192)).get("error", "Unknown API error")
        except (ValueError, AttributeError):
            error = "API returned an invalid error body"
        # API error messages contain no request body, journal rows, or credentials.
        raise SmokeFailure(f"{method} {path}: HTTP {exc.code}: {error}") from None


def health_until(port, version, commit, child, timeout=15):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        if child.poll() is not None:
            raise SmokeFailure(f"Launcher exited before readiness: {child.returncode}")
        try:
            last = request(port, "GET", "/api/health")
            if last.get("version") == version and last.get("commit") == commit:
                return last
        except (OSError, urllib.error.URLError, SmokeFailure):
            pass
        time.sleep(.1)
    identity = {key: last.get(key) for key in ("version", "commit")} if last else None
    raise SmokeFailure(f"Health did not reach expected identity {version}/{commit}; observed {identity}")


def main():
    process = None
    with tempfile.TemporaryDirectory(prefix="prop-update-smoke-") as temporary:
        work = Path(temporary)
        initial = build(work / "dist", OLD)
        with zipfile.ZipFile(initial["path"]) as package:
            package.extractall(work / "install")
        app = work / "install" / ("PROP-LAB-" + initial["version"])
        baseline = json.loads((app / ".installed.json").read_text())
        match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", initial["version"])
        if match is None:
            raise SmokeFailure("Fixture requires a stable semantic source version")
        updated_version = f"{match[1]}.{match[2]}.{int(match[3]) + 1}"
        incoming = work / "future.zip"
        with zipfile.ZipFile(incoming, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for relative in sorted(baseline["files"]):
                content = (app / relative).read_bytes()
                if relative == "RELEASE.json":
                    metadata = json.loads(content)
                    metadata["version"] = updated_version
                    content = (json.dumps(metadata, indent=2) + "\n").encode()
                info = zipfile.ZipInfo(f"awesome-x402-{NEW}/{relative}")
                info.create_system = 3
                info.external_attr = (stat.S_IFREG | (0o755 if relative.endswith((".sh", ".command")) else 0o644)) << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, content)
        fixture = work / "transport"
        fixture.mkdir()
        (fixture / "sitecustomize.py").write_text(
            "import json\nfrom pathlib import Path\nfrom propdesk.updater import Updater\n"
            "def fixture_fetch(self,url,limit,*,authenticated=False):\n"
            "    if '/commits/' in url: return json.dumps({'sha':" + repr(NEW) + "}).encode()\n"
            "    if '/zipball/' in url: return Path(" + repr(str(incoming)) + ").read_bytes()\n"
            "    raise ValueError('Unexpected fixture network request')\n"
            "Updater._fetch=fixture_fetch\n", encoding="utf-8")
        with socket.socket() as available:
            available.bind(("127.0.0.1", 0))
            port = available.getsockname()[1]
        environment = os.environ.copy()
        environment["PYTHONPATH"] = os.pathsep.join((str(fixture), str(app)))
        # Do not inherit a user's external data directory in this isolated fixture.
        environment.pop("TRADING_DATA_DIR", None)
        log = work / "process.log"
        with log.open("wb") as output:
            try:
                process = subprocess.Popen([sys.executable, "launch.py", "--no-browser", "--port", str(port)],
                                           cwd=app, env=environment, stdout=output, stderr=subprocess.STDOUT)
                health_until(port, initial["version"], OLD, process)
                journal = request(port, "POST", "/api/journal", {
                    "symbol": "AAPL", "side": "long", "entry": 100, "exit": 101, "stop": 99,
                    "quantity": 10, "fees": 1, "strategy": "Update process fixture",
                    "opened_at": "2026-10-01T10:00:00Z", "closed_at": "2026-10-01T11:00:00Z"})
                trade_id = journal["trade"]["id"]
                (app / ".env").write_text("user-local-value\n", encoding="utf-8")
                applied = request(port, "POST", "/api/updates/apply", {})
                if applied.get("updated") is not True or applied.get("restarting") is not True:
                    raise SmokeFailure("Apply did not request the supervised process restart")
                health_until(port, updated_version, NEW, process)
                retained = request(port, "GET", "/api/journal")
                if retained["trades"][0]["id"] != trade_id or (app / ".env").read_text() != "user-local-value\n":
                    raise SmokeFailure("Local journal or configuration changed across update")
                latest = request(port, "POST", "/api/updates/apply", {})
                if latest.get("updated") is not False or latest.get("restarting") is not False:
                    raise SmokeFailure("Second apply was not a no-op")
            finally:
                if process is not None and process.poll() is None:
                    process.send_signal(signal.SIGTERM)
                    try:
                        process.wait(timeout=6)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=3)
        # The supervisor must stop its owned child, so this port is free again.
        with socket.socket() as stopped:
            stopped.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                stopped.bind(("127.0.0.1", port))
            except OSError:
                raise SmokeFailure("Supervisor cleanup left a server on the owned port") from None
        print("PASS: real supervisor restarted to the new version/commit; journal and .env preserved; second update no-op; child stopped.")


if __name__ == "__main__":
    try:
        main()
    except (SmokeFailure, OSError, ValueError) as exc:
        print("FAIL: " + str(exc), file=sys.stderr)
        raise SystemExit(1)
