"""The deliverable must start clean, preserve hashes, and omit private state."""
import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from propdesk.updater import Updater
from scripts.build_distribution import REFERENCE_FILES, build


class DistributionTests(unittest.TestCase):
    def test_only_managed_source_and_explicit_public_fixtures_enter_zip(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "source"
            root.mkdir()
            release = {"schema": 1, "version": "0.2.0",
                       "repository": "NeatherFrog/awesome-x402", "branch": "main"}
            files = {"RELEASE.json": json.dumps(release), "launch.py": "# launcher",
                     "START-WINDOWS.bat": "@echo off", "START-MAC.command": "#!/bin/sh",
                     "START-LINUX.sh": "#!/bin/sh", "propdesk/server.py": "# server",
                     "propdesk/updater.py": "# updater", "static/index.html": "<html>",
                     "propdesk/jobs.py": "# jobs", "propdesk/scanner.py": "# scanner",
                     "static/app.js": "// app", "docs/notes.md": "public notes"}
            files.update({name: "public fixture" for name in REFERENCE_FILES})
            private = {".env": "PRIVATE_TOKEN=test-secret", ".local/journal.sqlite": "journal",
                       "data/customer.csv": "customer history", ".git/config": "git config",
                       "propdesk/__pycache__/server.pyc": "bytecode", "dist/stale.zip": "stale"}
            for name, body in {**files, **private}.items():
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(body, encoding="utf-8")
            (root / "static/secret-link").symlink_to(root / ".env")
            result = build(Path(directory) / "out", "1" * 40, root=root)
            self.assertEqual(result["sha256"], hashlib.sha256(Path(result["path"]).read_bytes()).hexdigest())
            with zipfile.ZipFile(result["path"]) as archive:
                prefix = "PROP-LAB-0.2.0/"
                paths = {info.filename.removeprefix(prefix) for info in archive.infolist()}
                self.assertEqual(paths, set(files) | {".installed.json"})
                baseline = json.loads(archive.read(prefix + ".installed.json"))
                self.assertEqual(baseline["commit"], "1" * 40)
                self.assertFalse(set(baseline["files"]) & set(REFERENCE_FILES))
                for name, digest in baseline["files"].items():
                    self.assertEqual(digest, hashlib.sha256(archive.read(prefix + name)).hexdigest())
                for name in ("START-LINUX.sh", "START-MAC.command"):
                    self.assertEqual(archive.getinfo(prefix + name).external_attr >> 16 & 0o777, 0o755)
                archive.extractall(Path(directory) / "installed")
            installed = Path(directory) / "installed/PROP-LAB-0.2.0"
            status = Updater(installed).status()
            self.assertEqual(status["mode"], "package")
            self.assertTrue(status["can_apply"])
            second = build(Path(directory) / "again", "1" * 40, root=root)
            self.assertEqual(second["sha256"], result["sha256"])


if __name__ == "__main__":
    unittest.main()
