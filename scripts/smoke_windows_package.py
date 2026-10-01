"""Validate the bundled interpreter and a real supervised update on Windows.

Fixture transport is injected through separate smoke-only wrappers, because the
official isolated interpreter intentionally ignores PYTHONPATH/sitecustomize.
The release archive itself is never modified by this check.
"""
from __future__ import annotations

import argparse
import errno
import hashlib
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


def request(port, method, path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json"} if payload is not None else {}
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    query = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data, headers=headers, method=method)
    try:
        with opener.open(query, timeout=5) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        try:
            message = json.load(exc).get("error", "API error")
        except ValueError:
            message = "Invalid API error"
        raise RuntimeError(f"{method} {path}: HTTP {exc.code}: {message}") from None


def health_until(port, version, commit, process):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("Bundled Windows launcher exited before readiness")
        try:
            health = request(port, "GET", "/api/health")
            if health.get("version") == version and health.get("commit") == commit:
                return health
        except (OSError, urllib.error.URLError, RuntimeError):
            pass
        time.sleep(.1)
    raise RuntimeError("Bundled Windows application did not reach the expected version/commit")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, required=True)
    args = parser.parse_args()
    if sys.platform != "win32":
        parser.error("This check must run on native Windows")
    archive = args.archive.resolve()
    record = {"archive_name": archive.name,
              "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
              "platform": sys.platform, "status": "running"}
    process = None
    with tempfile.TemporaryDirectory(prefix="PROP LAB Windows smoke ") as temporary:
        work = Path(temporary)
        with zipfile.ZipFile(archive) as package:
            assert package.testzip() is None
            package.extractall(work / "installed with spaces")
        children = list((work / "installed with spaces").iterdir())
        assert len(children) == 1 and children[0].is_dir()
        app = children[0]
        assert not any((app / name).exists() for name in (".git", ".env", ".local"))
        baseline = json.loads((app / ".installed.json").read_text(encoding="utf-8"))
        version, commit = baseline["version"], baseline["commit"]
        record.update(version=version, source_commit=commit)
        interpreter = app / "runtime" / "python.exe"
        runtime_check = subprocess.run([str(interpreter), "-X", "utf8", "-c",
            "import json,ssl,sqlite3,zoneinfo,propdesk,sys; "
            "print(json.dumps({'python':sys.version.split()[0], 'isolated':sys.flags.isolated, "
            "'sqlite':sqlite3.sqlite_version,'ssl':ssl.OPENSSL_VERSION}))"],
            cwd=app, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if runtime_check.returncode:
            detail = (runtime_check.stdout + runtime_check.stderr)[-8000:]
            raise RuntimeError(f"Bundled runtime import check failed ({runtime_check.returncode}):\n{detail}")
        record["runtime"] = json.loads(runtime_check.stdout)
        assert record["runtime"]["isolated"] == 1
        match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", version)
        assert match is not None
        future_version = f"{match[1]}.{match[2]}.{int(match[3]) + 1}"
        future_commit = "2" * 40
        incoming = work / "future.zip"
        with zipfile.ZipFile(incoming, "w", compression=zipfile.ZIP_DEFLATED) as future:
            for name in sorted(baseline["files"]):
                content = (app / name).read_bytes()
                if name == "RELEASE.json":
                    metadata = json.loads(content)
                    metadata["version"] = future_version
                    content = (json.dumps(metadata) + "\n").encode()
                info = zipfile.ZipInfo(f"awesome-x402-{future_commit}/{name}")
                info.create_system = 3
                info.external_attr = (stat.S_IFREG | (0o755 if name.endswith((".sh", ".command")) else 0o644)) << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                future.writestr(info, content)
        server_wrapper = app / "_windows_smoke_server.py"
        server_wrapper.write_text(
            "import json,sys\nfrom pathlib import Path\nfrom propdesk.updater import Updater\n"
            "def fixture_fetch(self,url,limit,*,authenticated=False):\n"
            "    if '/commits/' in url:return json.dumps({'sha':" + repr(future_commit) + "}).encode()\n"
            "    if '/zipball/' in url:return Path(" + repr(str(incoming)) + ").read_bytes()\n"
            "    raise ValueError('Unexpected fixture request')\n"
            "Updater._fetch=fixture_fetch\n"
            "from propdesk.__main__ import main\nsys.argv=['propdesk','serve']+sys.argv[1:]\n"
            "raise SystemExit(main())\n", encoding="utf-8")
        supervisor_wrapper = app / "_windows_smoke_supervisor.py"
        supervisor_wrapper.write_text(
            "import subprocess,sys\nfrom pathlib import Path\nimport launch\n"
            "original_popen=subprocess.Popen\n"
            "def fixture_popen(command,*args,**kwargs):\n"
            "    index=command.index('-m') if isinstance(command,list) and '-m' in command else -1\n"
            "    if index>=0 and command[index:index+3]==['-m','propdesk','serve']:\n"
            "        command=command[:index]+[str(Path(__file__).with_name('_windows_smoke_server.py'))]+command[index+3:]\n"
            "    return original_popen(command,*args,**kwargs)\n"
            "subprocess.Popen=fixture_popen\nraise SystemExit(launch.main())\n", encoding="utf-8")
        with socket.socket() as available:
            available.bind(("127.0.0.1", 0))
            port = available.getsockname()[1]
        environment = os.environ.copy()
        environment.pop("TRADING_DATA_DIR", None)
        environment["TRADING_AUTOPILOT_DEFAULT"] = "0"
        runtime_before = {p.relative_to(app).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in (app / "runtime").rglob("*") if p.is_file()}
        with (work / "server.log").open("wb") as output:
            try:
                process = subprocess.Popen([str(interpreter), "-X", "utf8", str(supervisor_wrapper), "--no-browser", "--port", str(port)],
                    cwd=app, env=environment, stdout=output, stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
                health_until(port, version, commit, process)
                bootstrap = request(port, "GET", "/api/bootstrap")
                assert len(bootstrap["strategies"]) == 8 and len(bootstrap["profiles"]) == 3
                board = request(port, "GET", "/api/trader/board")
                assert board["mode"] == "paper" and board["live_orders"] is False
                assert isinstance(board["markets"], list) and isinstance(board["setups"], list)
                studies = {item["id"]: item for item in board["evidence"]["studies"]}
                assert {"sourced_daily", "intraday", "mean_reversion"}.issubset(studies)
                assert studies["sourced_daily"]["primary"]["id"] == "bt_sma_10_30"
                assert studies["mean_reversion"]["primary"]["id"] == "rsi2_pullback_5"
                assert all(studies[name]["live_candidate"] is False for name in ("sourced_daily", "intraday", "mean_reversion"))
                diary = request(port, "GET", "/api/trader/diary")
                assert diary["mode"] == "historical_replay" and diary["live_orders"] is False
                assert isinstance(diary["trades"], list) and diary["manual_journal_unchanged"] is True
                mean_diary = request(port, "GET", "/api/trader/diary?study=mean_reversion&month=2026-09")
                assert mean_diary["state"] == "ready" and len(mean_diary["trades"]) == 2
                assert mean_diary["qualification"]["real_prop_qualified"] is False
                assert mean_diary["summary"]["live_executions"] == 0
                updater = request(port, "GET", "/api/updates/status")
                assert updater["can_apply"] is True and updater["supervised"] is True
                assert request(port, "GET", "/api/autopilot")["enabled"] is False
                journal = request(port, "POST", "/api/journal", {
                    "symbol": "AAPL", "side": "long", "entry": 100, "exit": 101, "stop": 99,
                    "quantity": 10, "fees": 1, "strategy": "Windows package fixture",
                    "opened_at": "2026-10-01T10:00:00Z", "closed_at": "2026-10-01T11:00:00Z"})
                trade_id = journal["trade"]["id"]
                (app / ".env").write_text("local-user-setting\n", encoding="utf-8")
                update = request(port, "POST", "/api/updates/apply", {})
                assert update["updated"] is True and update["restarting"] is True
                health_until(port, future_version, future_commit, process)
                assert request(port, "GET", "/api/journal")["trades"][0]["id"] == trade_id
                assert (app / ".env").read_text(encoding="utf-8") == "local-user-setting\n"
                assert request(port, "POST", "/api/updates/apply", {})["updated"] is False
                runtime_after = {p.relative_to(app).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in (app / "runtime").rglob("*") if p.is_file()}
                assert runtime_before == runtime_after
                record.update(status="passed", checks=["clean_extraction", "isolated_runtime_imports", "path_with_spaces",
                    "health_exact_commit", "bootstrap", "setup_board", "fixed_evidence_reports", "retrospective_diary", "rsi2_diary", "supervised_updater", "real_update_restart",
                    "journal_preserved", "settings_preserved", "runtime_preserved", "update_noop"])
            except Exception as exc:
                detail = (work / "server.log").read_text(encoding="utf-8", errors="replace")[-8000:]
                raise RuntimeError(f"Windows package smoke failed: {exc}\nLauncher log:\n{detail}") from exc
            finally:
                if process is not None and process.poll() is None:
                    try:
                        process.send_signal(signal.CTRL_BREAK_EVENT)
                        process.wait(timeout=10)
                    except (OSError, subprocess.TimeoutExpired):
                        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                                       capture_output=True, timeout=10)
                        process.wait(timeout=10)
        with socket.socket() as stopped:
            # Windows SO_REUSEADDR can bind beside a live listener. An
            # exclusive bind can instead fail solely because of TIME_WAIT.
            # Require an actual refusal of a fresh connection after shutdown.
            # Windows may delay loopback refusal for several SYN attempts.
            # A short timeout returns WSAEWOULDBLOCK without establishing
            # whether a listener exists. Still require an explicit refusal.
            stopped.settimeout(5)
            result = stopped.connect_ex(("127.0.0.1", port))
            if result not in (errno.ECONNREFUSED, getattr(errno, "WSAECONNREFUSED", 10061)):
                raise RuntimeError(f"Stopped Windows server did not refuse a fresh connection: {result}")
    validation = archive.parent / "windows-validation.json"
    validation.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(record))


if __name__ == "__main__":
    main()
