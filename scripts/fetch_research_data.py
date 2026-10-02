"""Restore exact public historical research inputs from our runner's export."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import re
from urllib.request import Request, urlopen

BASE = "https://raw.githubusercontent.com/NeatherFrog/awesome-x402/"
ALLOWED = {"manifest.json", "protocol.json", "BTCUSDT-1h.json",
           "ETHUSDT-1h.json", "BTCUSDT-5m.json", "ETHUSDT-5m.json"}


def get(url, limit):
    with urlopen(Request(url, headers={"User-Agent": "trading-historical-research"}), timeout=60) as r:
        if not r.url.startswith(BASE):
            raise ValueError("Unexpected export redirect")
        data = r.read(limit + 1)
    if len(data) > limit:
        raise ValueError("Export exceeds bounded size")
    return data


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--branch", required=True)
    parser.add_argument("--data-dir", default=".local/exchange-history")
    args = parser.parse_args()
    if not re.fullmatch(r"research-data-[0-9a-f]{12}", args.branch):
        raise ValueError("Only immutable research export branches are accepted")
    base = BASE + args.branch + "/research-data/"
    index_raw = get(base + "index.json", 100_000)
    index = json.loads(index_raw)
    if (index.get("schema") != 1 or index.get("branch") != args.branch or
            not re.fullmatch(r"[0-9a-f]{40}", index.get("source_commit", "")) or
            args.branch != "research-data-" + index["source_commit"][:12] or
            index.get("license") != "CC-BY-NC-SA-4.0"):
        raise ValueError("Invalid research export identity/license")
    directory = Path(args.data_dir)
    directory.mkdir(parents=True, exist_ok=True)
    for e in index["exports"]:
        name = e["output"]
        if name not in ALLOWED or e["filename"] != name + ".gz":
            raise ValueError("Unexpected export filename")
        packed = get(base + e["filename"], 32 * 1024 * 1024)
        if hashlib.sha256(packed).hexdigest() != e["compressed_sha256"]:
            raise ValueError("Compressed data checksum mismatch")
        import io
        with gzip.GzipFile(fileobj=io.BytesIO(packed)) as stream:
            data = stream.read(120 * 1024 * 1024 + 1)
        if (len(data) > 120 * 1024 * 1024 or len(data) != e["bytes"] or
                hashlib.sha256(data).hexdigest() != e["sha256"]):
            raise ValueError("Canonical data checksum mismatch")
        dest = directory / name
        if dest.exists() and dest.read_bytes() != data:
            raise ValueError("Refusing to overwrite a different research snapshot")
        dest.write_bytes(data)
        print(name, len(data), e["sha256"])
    (directory / "export-index.json").write_bytes(index_raw)
    (directory / "ATTRIBUTION.md").write_bytes(get(base + "ATTRIBUTION.md", 100_000))


if __name__ == "__main__":
    main()
