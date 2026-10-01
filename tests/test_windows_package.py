"""Synthetic portable-package tests; no claim of native Windows execution."""
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import urllib.request
import zipfile

from propdesk.updater import Updater, is_managed_path
from scripts.build_distribution import REFERENCE_FILES
from scripts import build_windows_distribution as windows


def native_bytes(machine=0x8664):
    result = bytearray(256)
    result[:2] = b"MZ"
    struct.pack_into("<I", result, 0x3C, 128)
    result[128:132] = b"PE\x00\x00"
    struct.pack_into("<H", result, 132, machine)
    return bytes(result)


def runtime_members():
    library = io.BytesIO()
    with zipfile.ZipFile(library, "w") as archive:
        for name in ("encodings/__init__.pyc", "ssl.pyc", "sqlite3/__init__.pyc", "urllib/request.pyc",
                     "zoneinfo/__init__.pyc", "json/__init__.pyc"):
            archive.writestr(name, b"synthetic test bytecode, never executed")
    files = {name: native_bytes() for name in windows.REQUIRED_RUNTIME_FILES
             if name.endswith((".exe", ".dll", ".pyd"))}
    files[windows.STDLIB_NAME] = library.getvalue()
    files[windows.PTH_NAME] = b"python313.zip\n.\nimport site\n"
    files["LICENSE.txt"] = b"Synthetic license fixture; not an official runtime"
    return files


def write_runtime(path, members):
    with zipfile.ZipFile(path, "w") as archive:
        for name, body in members.items():
            archive.writestr(name, body)


def signature_records(files):
    major, minor, micro = (int(part) for part in windows.RUNTIME_VERSION.split("."))
    return {"python_version": windows.RUNTIME_VERSION,
            "python_resource_version": [major, minor, micro * 1000 + 150, 1013], "records": [
        {"name": name, "status": "Valid" if name in windows.CORE_SIGNED_FILES else "NotSigned",
         "subject": "CN=Python Software Foundation" if name in windows.CORE_SIGNED_FILES else None,
         "thumbprint": "TEST_ONLY" if name in windows.CORE_SIGNED_FILES else None}
        for name in sorted(files) if name.endswith((".exe", ".dll", ".pyd"))
    ]}


def application_tree(root):
    release = {"schema": 1, "version": "0.2.0", "repository": "NeatherFrog/awesome-x402", "branch": "main"}
    files = {"RELEASE.json": json.dumps(release), "launch.py": "# launcher",
             "START-WINDOWS.bat": "@echo off", "START-MAC.command": "#!/bin/sh",
             "START-LINUX.sh": "#!/bin/sh", "propdesk/server.py": "# server",
             "propdesk/updater.py": "# updater", "propdesk/jobs.py": "# jobs",
             "propdesk/scanner.py": "# scanner", "static/index.html": "<html>", "static/app.js": "// app"}
    files.update({name: "public fixture" for name in REFERENCE_FILES})
    for name, body in files.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")


class WindowsPackageTests(unittest.TestCase):
    def test_runtime_requires_native_x64_and_core_application_modules(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "runtime.zip"
            members = runtime_members()
            write_runtime(archive, members)
            self.assertEqual(windows._runtime_files(archive), members)
            for name in ("_ssl.pyd", windows.PTH_NAME, "LICENSE.txt"):
                write_runtime(archive, {key: value for key, value in members.items() if key != name})
                with self.assertRaises(windows.WindowsBuildError):
                    windows._runtime_files(archive)
            write_runtime(archive, {**members, "python.exe": native_bytes(0x14C)})
            with self.assertRaisesRegex(windows.WindowsBuildError, "x64"):
                windows._runtime_files(archive)

    def test_archive_traversal_windows_devices_and_duplicates_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "runtime.zip"
            for name in ("../escape", "/absolute", "C:/drive", "runtime/python.exe", "CON.dll", "tail.", "bad\\path", "Python.exe"):
                with self.subTest(member=name):
                    write_runtime(archive, {**runtime_members(), name: native_bytes()})
                    with self.assertRaises(windows.WindowsBuildError):
                        windows._runtime_files(archive)
            with zipfile.ZipFile(archive, "w") as package:
                for name, body in runtime_members().items():
                    package.writestr(name, body)
                linked = zipfile.ZipInfo("link.dll")
                linked.create_system = 3
                linked.external_attr = (stat.S_IFLNK | 0o777) << 16
                package.writestr(linked, "outside")
            with self.assertRaises(windows.WindowsBuildError):
                windows._runtime_files(archive)

    def test_size_and_inventory_limits_are_enforced(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "runtime.zip"
            write_runtime(archive, runtime_members())
            for field in ("MAX_ARCHIVE_BYTES", "MAX_EXPANDED_BYTES", "MAX_RUNTIME_FILES"):
                with patch.object(windows, field, 1):
                    with self.assertRaises(windows.WindowsBuildError):
                        windows._runtime_files(archive)

    def test_signed_psf_core_and_exact_version_are_required(self):
        files = runtime_members()
        observed = signature_records(files)
        self.assertEqual(windows._validate_signatures(observed, files), observed["records"])
        with self.assertRaises(windows.WindowsBuildError):
            windows._validate_signatures({**observed, "python_version": "3.13.0"}, files)
        for status, subject in (("NotSigned", "Python Software Foundation"), ("Valid", "Other publisher"), ("HashMismatch", "Python Software Foundation")):
            broken = json.loads(json.dumps(observed))
            record = next(record for record in broken["records"] if record["name"] == "python.exe")
            record.update(status=status, subject=subject)
            with self.assertRaises(windows.WindowsBuildError):
                windows._validate_signatures(broken, files)
        with self.assertRaises(windows.WindowsBuildError):
            windows._validate_signatures({**observed, "records": observed["records"][:-1]}, files)

    def test_signed_file_version_and_encoded_windows_build_agree(self):
        files = runtime_members()
        observed = signature_records(files)
        self.assertEqual(observed["python_version"], "3.13.16")
        self.assertEqual(observed["python_resource_version"], [3, 13, 16150, 1013])
        self.assertEqual(windows._validate_signatures(observed, files), observed["records"])
        for version, resource in (("3.13.16150", [3, 13, 16150, 1013]),
                                  ("3.13.16", [3, 13, 16, 1013]),
                                  ("3.13.16", [3, 13, 16140, 1013])):
            with self.subTest(version=version, resource=resource):
                with self.assertRaises(windows.WindowsBuildError):
                    windows._validate_signatures({**observed, "python_version": version,
                                                  "python_resource_version": resource}, files)

    def test_signature_script_is_executed_whole_without_interactive_stdin(self):
        observed = signature_records(runtime_members())
        completed = subprocess.CompletedProcess([], 0, "\ufeff" + json.dumps(observed), "")
        with patch.dict(os.environ, {"PSModulePath": "C:/PowerShell7/Modules"}):
            with patch.object(windows.subprocess, "run", return_value=completed) as run:
                self.assertEqual(windows._authenticode("C:/path with spaces/runtime"), observed)
            self.assertEqual(os.environ["PSModulePath"], "C:/PowerShell7/Modules")
        command = run.call_args.args[0]
        self.assertEqual(command[:-1], ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-EncodedCommand"])
        script = base64.b64decode(command[-1], validate=True).decode("utf-16-le")
        self.assertIn("Get-AuthenticodeSignature -LiteralPath", script)
        self.assertIn("python_version=$version.FileVersion", script)
        self.assertIn("$version.FileBuildPart", script)
        self.assertIn("[Console]::OutputEncoding", script)
        self.assertIn("$ProgressPreference = 'SilentlyContinue'", script)
        self.assertIn("$env:PSModulePath = [IO.Path]::Combine($PSHOME, 'Modules')", script)
        self.assertIn("Import-Module -Name ([IO.Path]::Combine($PSHOME, 'Modules', 'Microsoft.PowerShell.Security', 'Microsoft.PowerShell.Security.psd1')) -ErrorAction Stop", script)
        self.assertNotIn("input", run.call_args.kwargs)
        self.assertEqual(run.call_args.kwargs["encoding"], "utf-8")
        self.assertEqual(run.call_args.kwargs["env"]["TRADING_RUNTIME_VERIFY_DIR"], "C:/path with spaces/runtime")

    def test_empty_or_malformed_signature_response_has_bounded_safe_diagnostics(self):
        secret = "fixture-ci-secret"
        with patch.dict(os.environ, {"TRADING_CI_TOKEN": secret}):
            for response in ("", "not JSON " + secret + " https://example.invalid/log?sig=fixture " + "x" * 3000):
                with self.subTest(empty=not response):
                    completed = subprocess.CompletedProcess([], 0, response, "")
                    with patch.object(windows.subprocess, "run", return_value=completed):
                        with self.assertRaisesRegex(windows.WindowsBuildError, "did not return valid JSON") as error:
                            windows._authenticode("C:/runtime")
                    message = str(error.exception)
                    self.assertNotIn(secret, message)
                    self.assertNotIn("sig=fixture", message)
                    self.assertLessEqual(len(message), 2100)

    def test_signature_process_failure_redacts_secrets_and_signed_urls(self):
        secret = "fixture-ci-secret"
        completed = subprocess.CompletedProcess([], 1, "", "Bearer " + secret + " https://example.invalid/log?sig=fixture")
        with patch.dict(os.environ, {"TRADING_CI_TOKEN": secret}):
            with patch.object(windows.subprocess, "run", return_value=completed):
                with self.assertRaisesRegex(windows.WindowsBuildError, "failed \\(exit 1\\)") as error:
                    windows._authenticode("C:/runtime")
        self.assertIn("[redacted]", str(error.exception))
        self.assertIn("[URL]", str(error.exception))
        self.assertNotIn(secret, str(error.exception))
        self.assertNotIn("sig=fixture", str(error.exception))

    def test_linux_cannot_claim_verified_windows_publication(self):
        with patch.object(windows.sys, "platform", "linux"):
            with patch.object(windows, "_download_official") as download:
                with self.assertRaisesRegex(windows.WindowsBuildError, "Windows runner"):
                    windows._verify_runtime(None, "/unused")
                download.assert_not_called()

    def test_local_hash_is_compared_to_independent_official_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            official = root / "official.zip"
            supplied = root / "supplied.zip"
            members = runtime_members()
            write_runtime(official, members)
            # Matching signed core binaries alone cannot authenticate modified
            # pure Python: whole-archive official comparison must reject it.
            write_runtime(supplied, {**members, windows.PTH_NAME: b"tampered"})
            with patch.object(windows.sys, "platform", "win32"):
                with patch.object(windows, "_download_official", return_value=official) as download, \
                        patch.object(windows, "RUNTIME_ARCHIVE_SHA256", windows.file_digest(official)):
                    with patch.object(windows, "_authenticode", return_value=signature_records(members)) as signatures:
                        with self.assertRaisesRegex(windows.WindowsBuildError, "independently downloaded"):
                            windows._verify_runtime(supplied, root)
                        signatures.assert_not_called()
                        files, verification = windows._verify_runtime(official, root)
                        self.assertEqual(files, members)
                        self.assertEqual(verification["source_archive_sha256"], windows.file_digest(official))
                        self.assertEqual(verification["pinned_source_archive_sha256"], windows.file_digest(official))
                        self.assertEqual(verification["source_url"], windows.RUNTIME_URL)
                        self.assertEqual(download.call_count, 2)

    def test_changed_official_archive_is_rejected_before_inventory_or_signatures(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            official = root / "official.zip"
            write_runtime(official, runtime_members())
            with patch.object(windows.sys, "platform", "win32"), \
                    patch.object(windows, "_download_official", return_value=official), \
                    patch.object(windows, "_runtime_files") as inventory, \
                    patch.object(windows, "_authenticode") as signatures:
                with self.assertRaisesRegex(windows.WindowsBuildError, "version-controlled archive SHA-256 pin"):
                    windows._verify_runtime(None, root)
            inventory.assert_not_called()
            signatures.assert_not_called()

    def test_official_download_redirects_preserve_https_origin(self):
        handler = windows._OfficialRedirect()
        request = urllib.request.Request(windows.RUNTIME_URL)
        for url in ("http://www.python.org/file.zip", "https://evil.example/file.zip", "https://user@python.org/file.zip"):
            with self.assertRaises(windows.WindowsBuildError):
                handler.redirect_request(request, None, 302, "redirect", {}, url)

    def test_assembly_keeps_runtime_outside_app_update_baseline_and_isolates_imports(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "source"
            root.mkdir()
            application_tree(root)
            (root / ".env").write_text("TEST_PRIVATE_VALUE")
            members = runtime_members()
            verification = {"schema": 1, "source_archive_sha256": "a" * 64,
                            "verification_method": "synthetic fixture only; never published"}
            result = windows._assemble(Path(directory) / "output", "b" * 40, members, verification, root=root)
            self.assertEqual(result["sha256"], windows.file_digest(result["path"]))
            prefix = "PROP-LAB-Windows-x64-0.2.0/"
            with zipfile.ZipFile(result["path"]) as archive:
                names = {info.filename.removeprefix(prefix) for info in archive.infolist()}
                self.assertNotIn(".env", names)
                self.assertEqual(archive.read(prefix + "runtime/" + windows.PTH_NAME), windows.ISOLATED_PATHS)
                baseline = json.loads(archive.read(prefix + ".installed.json"))
                self.assertEqual(baseline["commit"], "b" * 40)
                self.assertTrue(all(not name.startswith("runtime/") for name in baseline["files"]))
                runtime = json.loads(archive.read(prefix + "runtime/RUNTIME.json"))
                self.assertFalse(runtime["path_configuration"]["site_enabled"])
                self.assertEqual(runtime["path_configuration"]["entries"], [windows.STDLIB_NAME, ".", ".."])
                for name, digest in runtime["installed_files"].items():
                    self.assertEqual(hashlib.sha256(archive.read(prefix + "runtime/" + name)).hexdigest(), digest)
                archive.extractall(Path(directory) / "installed")
            self.assertFalse(is_managed_path("runtime/python.exe"))
            self.assertTrue(Updater(Path(directory) / "installed" / prefix.rstrip("/")).status()["can_apply"])

    def test_windows_entry_point_prefers_bundled_python(self):
        command = (windows.ROOT / "START-WINDOWS.bat").read_text()
        self.assertLess(command.index('runtime\\python.exe'), command.index('where py'))
        self.assertIn('"%~dp0runtime\\python.exe" -X utf8 launch.py %*', command)


if __name__ == "__main__":
    unittest.main()
