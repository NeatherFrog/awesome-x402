"""Publish a tested Windows artifact from this repository's own GitHub runner."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "NeatherFrog/awesome-x402"


def git(*arguments, input=None, cwd=ROOT):
    result = subprocess.run(["git", *arguments], cwd=cwd, input=input,
                            capture_output=True)
    if result.returncode:
        raise RuntimeError("Git publication failed (exit " + str(result.returncode) + ")")
    return result.stdout.decode().strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--run-url", required=True)
    args = parser.parse_args()
    if (os.environ.get("GITHUB_ACTIONS") != "true" or
            os.environ.get("GITHUB_REPOSITORY") != REPOSITORY or
            os.environ.get("GITHUB_REF") != "refs/heads/main"):
        raise ValueError("Publication is limited to the repository's main-branch GitHub runner")
    if not re.fullmatch(r"[0-9a-f]{40}", args.source_commit) or git("rev-parse", "HEAD") != args.source_commit:
        raise ValueError("Source identity does not match this checked-out workflow")
    expected_url = "https://github.com/" + REPOSITORY + "/actions/runs/" + os.environ.get("GITHUB_RUN_ID", "")
    if args.run_url != expected_url:
        raise ValueError("Run provenance does not match this GitHub runner")
    validation = ROOT / "dist" / "windows-validation.json"
    record = json.loads(validation.read_text(encoding="utf-8"))
    if record.get("status") != "passed" or record.get("source_commit") != args.source_commit:
        raise ValueError("The exact source package has not passed native Windows validation")
    archive = ROOT / "dist" / record["archive_name"]
    if (archive.parent != ROOT / "dist" or not archive.is_file() or
            not re.fullmatch(r"PROP-LAB-Windows-x64-[0-9.]+\.zip", archive.name)):
        raise ValueError("Invalid Windows artifact")
    checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
    if checksum != record.get("archive_sha256"):
        raise ValueError("Validated Windows artifact has changed")
    sidecar = archive.with_name(archive.name + ".sha256")
    if sidecar.read_text(encoding="ascii").split()[0] != checksum:
        raise ValueError("Windows checksum sidecar does not match")
    current = git("ls-remote", "origin", "refs/heads/main").split()[0]
    if current != args.source_commit:
        print("SKIP: a newer main commit superseded this tested artifact")
        return
    with tempfile.TemporaryDirectory(prefix="prop-windows-publish-") as temporary:
        work = Path(temporary)
        git("fetch", "origin", "distribution")
        git("worktree", "add", "--detach", str(work / "publication"), "FETCH_HEAD")
        target = work / "publication"
        try:
            for source in (archive, sidecar, validation):
                (target / source.name).write_bytes(source.read_bytes())
            filename = "Windows-" + record["version"] + "-README.md"
            (target / filename).write_text(
                "# Trading / PROP LAB for Windows x64\n\n"
                "Download " + archive.name + ", extract it completely, and open START-WINDOWS.bat. "
                "Official CPython is bundled; no separate Python installation is needed.\n\n"
                "Source: `" + args.source_commit + "`\n\nNative Windows validation: " + args.run_url + "\n\n"
                "Research and paper planning only; no proven future profitability is claimed.\n", encoding="utf-8")
            git("config", "user.name", "github-actions[bot]", cwd=target)
            git("config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com", cwd=target)
            git("add", "--", archive.name, sidecar.name, validation.name, filename, cwd=target)
            changed = git("diff", "--cached", "--name-only", cwd=target)
            if changed:
                git("commit", "-m", "Publish tested Windows package " + record["version"], cwd=target)
                git("push", "origin", "HEAD:refs/heads/distribution", cwd=target)
        finally:
            git("worktree", "remove", "--force", str(target))
    print(json.dumps({"status": "published", "source_commit": args.source_commit,
                      "url": "https://github.com/" + REPOSITORY + "/raw/refs/heads/distribution/" + archive.name,
                      "sha256": checksum, "run_url": args.run_url}))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
