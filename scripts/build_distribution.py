"""Build a secret-free, Git-free user ZIP with an update integrity baseline."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Only the checked-in public fixtures are shipped; arbitrary user data stays out.
REFERENCE_FILES = tuple("data/market-history/" + name for name in (
    "AAPL-1d.csv", "MSFT-1d.csv", "JPM-1d.csv", "XOM-1d.csv",
    "provenance.json", "PLOTLY-LICENSE.txt")) + tuple("data/independent-history/" + name for name in (
    "GOOG-1d.csv", "provenance.json", "protocol.json", "BACKTESTING-PY-LICENSE.md",
    "original/GOOG.csv", "original/EURUSD.csv")) + tuple("data/crypto-history/" + name for name in (
    "ETHBTC-5m.csv", "provenance.json", "UPSTREAM-LICENSE.txt"))

from propdesk.updater import is_managed_path
from propdesk.version import release_metadata


def source_files(root=ROOT):
    root = Path(root)
    files = []
    for child in sorted(root.iterdir()):
        if child.is_symlink():
            continue
        if child.is_file() and is_managed_path(child.name):
            files.append(child)
        elif child.is_dir() and child.name in ("propdesk", "static", "docs", "scripts", "tests"):
            for file in sorted(child.rglob("*")):
                relative = file.relative_to(root).as_posix()
                if file.is_file() and not file.is_symlink() and is_managed_path(relative):
                    files.append(file)
    return sorted(files, key=lambda p: p.relative_to(root).as_posix())


def build(output_dir, commit, root=ROOT):
    root = Path(root)
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("Для пакета нужен точный 40-символьный SHA commit GitHub")
    metadata = release_metadata(root)
    paths = source_files(root)
    relative = {p.relative_to(root).as_posix(): p for p in paths}
    required = {"RELEASE.json", "launch.py", "START-WINDOWS.bat", "START-MAC.command", "START-LINUX.sh",
                "propdesk/server.py", "propdesk/updater.py", "propdesk/jobs.py", "propdesk/scanner.py",
                "static/index.html", "static/app.js"}
    if not required.issubset(relative):
        raise ValueError("Пакет неполный: " + ", ".join(sorted(required - relative.keys())))
    contents = {name: path.read_bytes() for name, path in relative.items()}
    baseline = {**metadata, "commit": commit,
                "files": {name: hashlib.sha256(data).hexdigest() for name, data in contents.items()}}
    contents[".installed.json"] = (json.dumps(baseline, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
    for name in REFERENCE_FILES:
        fixture = root / name
        if not fixture.is_file() or fixture.is_symlink():
            raise ValueError("Отсутствует закреплённый публичный архив: " + name)
        contents[name] = fixture.read_bytes()
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    archive = output / f"PROP-LAB-{metadata['version']}.zip"
    prefix = f"PROP-LAB-{metadata['version']}/"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as package:
        for name, data in sorted(contents.items()):
            info = zipfile.ZipInfo(prefix + name, date_time=(2026, 10, 1, 0, 0, 0))
            info.create_system = 3
            mode = 0o755 if name.endswith((".sh", ".command")) else 0o644
            info.external_attr = (stat.S_IFREG | mode) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            package.writestr(info, data)
    checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
    (output / (archive.name + ".sha256")).write_text(f"{checksum}  {archive.name}\n", encoding="ascii")
    return {"path": str(archive), "bytes": archive.stat().st_size, "sha256": checksum,
            "files": len(contents), "version": metadata["version"], "commit": commit}


def main():
    parser = argparse.ArgumentParser(description="Собрать готовый ZIP PROP LAB без пользовательских данных")
    parser.add_argument("--output-dir", default=str(ROOT / "dist"))
    parser.add_argument("--commit", help="Точный commit GitHub; по умолчанию текущий Git HEAD")
    args = parser.parse_args()
    commit = args.commit
    if commit is None:
        try:
            commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
                                    capture_output=True, text=True).stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            parser.error("Передайте --commit; Git нужен только сборщику, а не пользователю программы")
    try:
        print(json.dumps(build(args.output_dir, commit), ensure_ascii=False))
    except (ValueError, OSError) as exc:
        parser.exit(2, str(exc) + "\n")


if __name__ == "__main__":
    main()
