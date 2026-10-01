"""Build a portable Windows ZIP from official, verified embeddable CPython.

Publication requires Windows: the builder downloads the pinned official HTTPS
archive itself, compares any supplied local archive to those authoritative
bytes, and checks Windows Authenticode before assembling a distribution.
There is no caller-supplied checksum or verification-bypass switch.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import struct
import subprocess
import sys
import tempfile
import urllib.request
from urllib.parse import urlparse
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.build_distribution import build as build_application

RUNTIME_VERSION = "3.13.16"
RUNTIME_TAG_COMMIT = "cbc944f4bc59639a444dd971c737788ba2283a91"
RUNTIME_ARCH = "amd64"
RUNTIME_FILENAME = "python-" + RUNTIME_VERSION + "-embed-" + RUNTIME_ARCH + ".zip"
RUNTIME_URL = "https://www.python.org/ftp/python/" + RUNTIME_VERSION + "/" + RUNTIME_FILENAME
RUNTIME_ARCHIVE_SHA256 = "97dae5274cc54867065e8d5a3226e48c35017ed332a0fdb0e27d5b5821961297"
STDLIB_NAME = "python313.zip"
PTH_NAME = "python313._pth"
MAX_ARCHIVE_BYTES = 40 * 1024 * 1024
MAX_EXPANDED_BYTES = 100 * 1024 * 1024
MAX_RUNTIME_FILES = 120
CORE_SIGNED_FILES = frozenset({"python.exe", "python313.dll"})
REQUIRED_RUNTIME_FILES = CORE_SIGNED_FILES | {
    "pythonw.exe", "python3.dll", STDLIB_NAME, PTH_NAME, "LICENSE.txt",
    "_ssl.pyd", "_hashlib.pyd", "_sqlite3.pyd", "_zoneinfo.pyd",
}
_DEVICE = re.compile(r"(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?\Z", re.IGNORECASE)
ISOLATED_PATHS = (STDLIB_NAME + "\n.\n..\n# Isolated runtime: import site remains disabled.\n").encode("ascii")


class WindowsBuildError(ValueError):
    pass


def file_digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


class _OfficialRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urlparse(newurl)
        if (parsed.scheme != "https" or parsed.hostname not in {"www.python.org", "python.org"}
                or parsed.username or parsed.password or parsed.port not in (None, 443)):
            raise WindowsBuildError("Official runtime download redirected outside HTTPS python.org")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _download_official(destination):
    """Get authoritative bytes with default TLS verification, never user hashes."""
    opener = urllib.request.build_opener(_OfficialRedirect())
    request = urllib.request.Request(RUNTIME_URL, headers={"User-Agent": "PROP-LAB-Windows-Builder/1"})
    count = 0
    with opener.open(request, timeout=60) as response, Path(destination).open("wb") as output:
        if response.status != 200:
            raise WindowsBuildError("Official runtime server did not return HTTP 200")
        while chunk := response.read(1024 * 1024):
            count += len(chunk)
            if count > MAX_ARCHIVE_BYTES:
                raise WindowsBuildError("Official runtime archive exceeds the size limit")
            output.write(chunk)
    if count == 0:
        raise WindowsBuildError("Official runtime archive is empty")
    return Path(destination)


def _check_pe(name, body):
    if len(body) < 64 or body[:2] != b"MZ":
        raise WindowsBuildError("Runtime native file is not a PE executable: " + name)
    offset = struct.unpack_from("<I", body, 0x3C)[0]
    if offset > len(body) - 6 or body[offset:offset + 4] != b"PE\x00\x00":
        raise WindowsBuildError("Invalid PE header: " + name)
    if struct.unpack_from("<H", body, offset + 4)[0] != 0x8664:
        raise WindowsBuildError("Runtime architecture must be Windows x64: " + name)


def _runtime_files(path):
    if Path(path).stat().st_size > MAX_ARCHIVE_BYTES:
        raise WindowsBuildError("Runtime archive exceeds the size limit")
    result, seen = {}, set()
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        if len(entries) > MAX_RUNTIME_FILES or sum(info.file_size for info in entries) > MAX_EXPANDED_BYTES:
            raise WindowsBuildError("Runtime expanded size or file count exceeds the limit")
        for info in entries:
            name = info.filename
            mode = info.external_attr >> 16
            if (not re.fullmatch(r"[A-Za-z0-9_.-]+", name) or name in (".", "..")
                    or name.endswith((".", " ")) or _DEVICE.fullmatch(name)
                    or info.is_dir() or stat.S_ISLNK(mode) or info.flag_bits & 1):
                raise WindowsBuildError("Unsafe runtime archive member")
            if name.casefold() in seen:
                raise WindowsBuildError("Duplicate runtime archive member")
            seen.add(name.casefold())
            body = archive.read(info)
            if name.lower().endswith((".exe", ".dll", ".pyd")):
                _check_pe(name, body)
            result[name] = body
    if not REQUIRED_RUNTIME_FILES.issubset(result):
        raise WindowsBuildError("Runtime is incomplete: " + ", ".join(sorted(REQUIRED_RUNTIME_FILES - result.keys())))
    with zipfile.ZipFile(io.BytesIO(result[STDLIB_NAME])) as standard_library:
        names = set(standard_library.namelist())
        if not {"encodings/__init__.pyc", "ssl.pyc", "sqlite3/__init__.pyc", "urllib/request.pyc",
                "zoneinfo/__init__.pyc", "json/__init__.pyc"}.issubset(names):
            raise WindowsBuildError("Runtime standard library lacks required application modules")
    return result


def _authenticode(directory):
    environment = os.environ.copy()
    environment["TRADING_RUNTIME_VERIFY_DIR"] = str(directory)
    script = r'''
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$runtimePath = [Environment]::GetEnvironmentVariable('TRADING_RUNTIME_VERIFY_DIR')
$native = @(Get-ChildItem -LiteralPath $runtimePath -File | Where-Object { $_.Extension -in '.exe','.dll','.pyd' })
$records = @($native | ForEach-Object {
    $signature = Get-AuthenticodeSignature -LiteralPath $_.FullName
    [ordered]@{name=$_.Name; status=$signature.Status.ToString();
               subject=$signature.SignerCertificate.Subject;
               thumbprint=$signature.SignerCertificate.Thumbprint}
})
$version = [Diagnostics.FileVersionInfo]::GetVersionInfo((Join-Path $runtimePath 'python.exe'))
[ordered]@{python_version=$version.FileVersion;
           python_resource_version=@($version.FileMajorPart,$version.FileMinorPart,$version.FileBuildPart,$version.FilePrivatePart);
           records=$records} | ConvertTo-Json -Depth 5 -Compress
'''
    completed = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", "-"],
                               input=script, capture_output=True, text=True, encoding="utf-8",
                               check=True, env=environment, timeout=120)
    return json.loads(completed.stdout.lstrip("\ufeff"))


def _validate_signatures(observed, files):
    if not isinstance(observed, dict) or observed.get("python_version") != RUNTIME_VERSION:
        raise WindowsBuildError("Signed runtime version differs from the pinned Python release")
    # CPython's third Windows resource field encodes micro*1000 +
    # release_level*10 + serial, so 3.13.16 final has 16150, not 16.
    # The human-readable signed FileVersion string above is PY_VERSION.
    major, minor, micro = (int(part) for part in RUNTIME_VERSION.split("."))
    resource = observed.get("python_resource_version")
    if (not isinstance(resource, list) or len(resource) != 4
            or any(type(part) is not int or not 0 <= part <= 65535 for part in resource)
            or resource[:3] != [major, minor, micro * 1000 + 150]):
        raise WindowsBuildError("Signed Windows version resource differs from the pinned final Python release")
    records = observed.get("records")
    native_names = {name for name in files if name.lower().endswith((".exe", ".dll", ".pyd"))}
    if (not isinstance(records, list) or len(records) != len(native_names)
            or any(not isinstance(record, dict) for record in records)
            or {record.get("name") for record in records} != native_names):
        raise WindowsBuildError("Runtime signature inventory is incomplete")
    for record in records:
        name, status = record["name"], record.get("status")
        if name in CORE_SIGNED_FILES:
            if status != "Valid" or "Python Software Foundation" not in str(record.get("subject", "")):
                raise WindowsBuildError("Python core binary lacks a valid PSF Authenticode signature: " + name)
        elif status not in ("Valid", "NotSigned"):
            raise WindowsBuildError("Runtime native signature verification failed: " + name)
    return records


def _verify_runtime(local_archive, directory):
    if sys.platform != "win32":
        raise WindowsBuildError("Verified Windows publishing requires a Windows runner with Authenticode")
    directory = Path(directory)
    official = _download_official(directory / RUNTIME_FILENAME)
    official_hash = file_digest(official)
    if official_hash != RUNTIME_ARCHIVE_SHA256:
        raise WindowsBuildError("Official runtime differs from the version-controlled archive SHA-256 pin")
    if local_archive is not None and file_digest(local_archive) != official_hash:
        raise WindowsBuildError("Supplied runtime differs from the independently downloaded official archive")
    files = _runtime_files(official)
    extracted = directory / "signature-check"
    extracted.mkdir()
    for name, body in files.items():
        (extracted / name).write_bytes(body)
    observed = _authenticode(extracted)
    records = _validate_signatures(observed, files)
    verification = {
        "schema": 1, "python_version": RUNTIME_VERSION, "architecture": "Windows x64",
        "python_resource_version": observed["python_resource_version"],
        "source_url": RUNTIME_URL, "source_archive": RUNTIME_FILENAME, "source_archive_sha256": official_hash,
        "pinned_source_archive_sha256": RUNTIME_ARCHIVE_SHA256,
        "archive_pin_source": "Recorded from verified official HTTPS python.org archive bytes on 2026-10-01",
        "cpython_tag": "v" + RUNTIME_VERSION, "cpython_tag_commit": RUNTIME_TAG_COMMIT,
        "verification_method": "version-controlled archive SHA-256 + independent official HTTPS archive comparison + valid PSF core Authenticode",
        "verified_at_utc": datetime.now(timezone.utc).isoformat(), "native_signatures": records,
        "runner": {name: os.environ.get(name) for name in (
            "GITHUB_ACTIONS", "GITHUB_REPOSITORY", "GITHUB_SHA", "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT", "GITHUB_WORKFLOW_REF",
        )},
        "limitations": [
            "The version-controlled archive pin was recorded from verified official HTTPS bytes; an independently signed publisher archive checksum or manifest was not available.",
            "PSF Authenticode authenticates Python core native binaries. Other native files' statuses are recorded; unsigned files and stdlib ZIP are bound by the whole official HTTPS archive comparison.",
            "GitHub run identifiers are provenance metadata, not a cryptographic artifact attestation; the workflow should publish a GitHub build provenance attestation separately.",
            "Bundled runtime is preserved by application updates; replace the complete Windows package to receive Python security updates.",
        ],
    }
    return files, verification


def _assemble(output_dir, commit, files, verification, root=ROOT):
    """Pure ZIP assembly, used by synthetic tests; not a CLI verification bypass."""
    with tempfile.TemporaryDirectory(prefix="prop-lab-app-package-") as temporary:
        application = build_application(temporary, commit, root=root)
        old_prefix = "PROP-LAB-" + application["version"] + "/"
        with zipfile.ZipFile(application["path"]) as archive:
            contents = {info.filename.removeprefix(old_prefix): archive.read(info) for info in archive.infolist()}
    installed_runtime = dict(files)
    installed_runtime[PTH_NAME] = ISOLATED_PATHS
    metadata = {**verification, "source_commit": commit,
                "installed_files": {name: hashlib.sha256(body).hexdigest() for name, body in sorted(installed_runtime.items())},
                "path_configuration": {"file": PTH_NAME, "entries": [STDLIB_NAME, ".", ".."], "site_enabled": False}}
    for name, body in installed_runtime.items():
        contents["runtime/" + name] = body
    contents["runtime/RUNTIME.json"] = (json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    name = "PROP-LAB-Windows-x64-" + application["version"]
    destination = output_dir / (name + ".zip")
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for relative, body in sorted(contents.items()):
            info = zipfile.ZipInfo(name + "/" + relative, date_time=(2026, 10, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | (0o755 if relative.endswith((".sh", ".command")) else 0o644)) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, body)
    checksum = file_digest(destination)
    destination.with_name(destination.name + ".sha256").write_text(checksum + "  " + destination.name + "\n", encoding="ascii")
    return {"path": str(destination), "bytes": destination.stat().st_size, "sha256": checksum,
            "version": application["version"], "commit": commit, "runtime_version": RUNTIME_VERSION,
            "runtime_archive_sha256": verification["source_archive_sha256"], "files": len(contents)}


def build(output_dir, commit, runtime_zip=None, root=ROOT):
    with tempfile.TemporaryDirectory(prefix="prop-lab-runtime-verify-") as temporary:
        files, verification = _verify_runtime(runtime_zip, temporary)
        return _assemble(output_dir, commit, files, verification, root=root)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-zip", type=Path, help="Optional local official archive; independently compared to python.org")
    parser.add_argument("--commit", required=True, help="Exact GitHub source commit for the application baseline")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    try:
        print(json.dumps(build(args.output_dir, args.commit, args.runtime_zip), ensure_ascii=False))
    except (WindowsBuildError, OSError, ValueError, subprocess.CalledProcessError, subprocess.TimeoutExpired, zipfile.BadZipFile) as exc:
        parser.exit(1, "Windows package error: " + str(exc) + "\n")


if __name__ == "__main__":
    main()
