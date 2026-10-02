"""Expose native CI command diagnostics through the GitHub Checks API.

Output is credential-redacted, bounded, and attached only to this workflow's
exact source commit. Check API requests never follow redirects with credentials.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "NeatherFrog/awesome-x402"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


def sanitized(output):
    for name in ("TRADING_CI_TOKEN", "GH_TOKEN", "GITHUB_TOKEN", "TRADING_GITHUB_TOKEN", "TRADING_WEBHOOK_TOKEN"):
        secret = os.environ.get(name)
        if secret:
            output = output.replace(secret, "[redacted]")
    output = re.sub(r"https?://[^\s<>\"']+", "[URL]", output)
    output = re.sub(r"(?i)\bBearer\s+\S+", "Bearer [redacted]", output)
    encoded = output.encode("utf-8")
    if len(encoded) > 50000:
        encoded = encoded[:24000] + b"\n[Middle output truncated]\n" + encoded[-25000:]
    return encoded.decode("utf-8", errors="replace")


def report(stage, output, code, source):
    token = os.environ.get("TRADING_CI_TOKEN")
    if not token:
        print("No Checks API credential; command diagnostics remain in the workflow log")
        return
    payload = {
        "name": "Windows " + stage + " diagnostics", "head_sha": source,
        "status": "completed", "conclusion": "success" if code == 0 else "failure",
        "completed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "output": {"title": "Windows " + stage + ": exit " + str(code),
                   "summary": "Native Windows command result for the exact checked-out source commit.",
                   "text": "```text\n" + output + "\n```"},
    }
    request = urllib.request.Request(
        "https://api.github.com/repos/" + REPOSITORY + "/check-runs",
        data=json.dumps(payload).encode("utf-8"), method="POST",
        headers={"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
                 "Content-Type": "application/json", "User-Agent": "PROP-LAB-CI"})
    try:
        opener = urllib.request.build_opener(NoRedirect())
        with opener.open(request, timeout=15) as response:
            record = json.load(response)
            print(json.dumps({"checks_report": "published", "check_id": record.get("id"), "stage": stage}))
    except urllib.error.HTTPError as error:
        print("Checks API report unavailable (HTTP " + str(error.code) + "); original command result retained")
    except (urllib.error.URLError, TimeoutError, ValueError):
        print("Checks API report unavailable; original command result retained")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=("tests", "build", "smoke", "publish"))
    args = parser.parse_args()
    source = os.environ.get("GITHUB_SHA", "")
    if (os.environ.get("GITHUB_ACTIONS") != "true" or
            os.environ.get("GITHUB_REPOSITORY") != REPOSITORY or
            not re.fullmatch(r"[0-9a-f]{40}", source)):
        parser.error("This diagnostic wrapper is for this repository's own GitHub runner")
    python = [sys.executable, "-X", "utf8"]
    if args.stage == "tests":
        command = python + ["scripts/test_offline.py", "--quiet"]
    elif args.stage == "build":
        command = python + ["scripts/build_windows_distribution.py", "--commit", source, "--output-dir", "dist"]
    elif args.stage == "smoke":
        archives = list((ROOT / "dist").glob("PROP-LAB-Windows-x64-*.zip"))
        if len(archives) != 1:
            parser.error("Native smoke requires exactly one freshly built Windows package")
        command = python + ["scripts/smoke_windows_package.py", "--archive", str(archives[0])]
    else:
        run_url = "https://github.com/" + REPOSITORY + "/actions/runs/" + os.environ.get("GITHUB_RUN_ID", "")
        command = python + ["scripts/publish_windows_package.py", "--source-commit", source, "--run-url", run_url]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    output = sanitized(result.stdout + result.stderr)
    print(output, end="" if output.endswith("\n") else "\n")
    report(args.stage, output, result.returncode, source)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
