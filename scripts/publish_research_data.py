"""Publish checksum-verified historical research inputs from our GitHub runner.

Public Binance historical datasets retain CC BY-NC-SA 4.0 attribution. These
exports are for non-production historical research, not commercial signals.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "NeatherFrog/awesome-x402"


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def main():
    if (os.environ.get("GITHUB_ACTIONS") != "true" or
            os.environ.get("GITHUB_REPOSITORY") != REPOSITORY or
            os.environ.get("GITHUB_REF") != "refs/heads/research-data-acquisition"):
        raise ValueError("Only the dedicated repository research runner may publish")
    source = git("rev-parse", "HEAD")
    original = ROOT / ".local" / "exchange-history"
    manifest = json.loads((original / "manifest.json").read_text())
    hourly = [d for d in manifest["datasets"] if d["interval"] == "1h"]
    if len(hourly) != 2 or not all(d.get("complete_calendar") for d in hourly):
        raise ValueError("Complete official hourly calendars are required")
    target = ROOT / "research-data"
    target.mkdir(exist_ok=True)
    exports = []
    for name in ("manifest.json", "protocol.json", "BTCUSDT-1h.json",
                 "ETHUSDT-1h.json", "BTCUSDT-5m.json", "ETHUSDT-5m.json"):
        p = original / name
        if not p.is_file():
            continue
        data = p.read_bytes()
        packed = gzip.compress(data, mtime=0)
        filename = name + ".gz"
        (target / filename).write_bytes(packed)
        exports.append({"filename": filename, "output": name, "bytes": len(data),
                        "sha256": hashlib.sha256(data).hexdigest(),
                        "compressed_sha256": hashlib.sha256(packed).hexdigest()})
    (target / "ATTRIBUTION.md").write_text(
        "# Binance public historical research data\n\n"
        "Source: https://data.binance.vision/ ; official repository: "
        "https://github.com/binance/binance-public-data .\n\n"
        "Dataset license: CC BY-NC-SA 4.0, "
        "https://creativecommons.org/licenses/by-nc-sa/4.0/ .\n"
        "Terms: https://github.com/binance/binance-public-data/blob/master/"
        "TERMS_AND_CONDITIONS.md .\n\n"
        "These canonical OHLC exports retain attribution and are shared under "
        "the same license for personal non-production historical research. "
        "They do not grant live proprietary execution or commercial signal rights. "
        "The manifests contain individual original archive checksums.\n",
        encoding="utf-8")
    branch = "research-data-" + source[:12]
    index = {"schema": 1, "source_commit": source, "branch": branch,
             "run_url": "https://github.com/" + REPOSITORY + "/actions/runs/" + os.environ["GITHUB_RUN_ID"],
             "purpose": "personal_nonproduction_historical_research",
             "license": "CC-BY-NC-SA-4.0", "exports": exports}
    (target / "index.json").write_text(json.dumps(index, indent=2) + "\n")
    # This is an isolated CI checkout; user workspaces are never switched.
    git("checkout", "--orphan", branch)
    git("rm", "-r", "--cached", "--quiet", ".")
    git("config", "user.name", "github-actions[bot]")
    git("config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
    git("add", "--force", "--", "research-data")
    git("commit", "-m", "Retain attributed official historical research inputs")
    git("push", "origin", "HEAD:refs/heads/" + branch)
    print(json.dumps(index))


if __name__ == "__main__":
    main()
