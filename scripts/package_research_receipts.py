"""Copy completed public research locks into the existing managed docs tree.

Raw histories, execution ledgers and user state are never packaged here. Older
installations already update docs, so the first upgrade can retain the actual
protocol/selection locks without expanding ownership over arbitrary data files.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from propdesk.research_campaign import STUDIES, inspect, read_report

RECEIPT_FILES = frozenset({
    "protocol.json", "input-lock.json", "input_lock.json", "source-lock.json",
    "training-lock.json", "result-lock.json", "selection.json",
    "training-selection.json", "training_selection.json", "training_results.json",
    "validation-confirmation.json", "validation_selection.json",
    "pre_outcome_audit.json", "runtime-timezone-audit.json",
    "retrospective-causality-audit.json",
})


def package_receipts(root=ROOT):
    root = Path(root).resolve()
    copied = []
    for study, spec in STUDIES.items():
        report = read_report(root, study)
        if not report or not str(report.get("phase", "")).startswith(("completed", "complete")):
            continue
        status = inspect(root, study, report)
        if not all(status[key] for key in (
            "protocol_verified", "producer_hashes_verified", "training_results_verified"
        )):
            raise ValueError("Unverified completed research receipts: " + study)
        source = root / "data" / spec["directory"]
        if source.is_symlink():
            raise ValueError("Research receipt directory cannot be a link")
        destination = root / "docs" / "research-receipts" / spec["directory"]
        for name in sorted(RECEIPT_FILES):
            path = source / name
            if not path.exists():
                continue
            if not path.is_file() or path.is_symlink():
                raise ValueError("Research receipt must be a regular file")
            raw = path.read_bytes()
            target = destination / name
            if target.is_symlink() or any(parent.is_symlink() for parent in target.parents if parent != root.parent):
                raise ValueError("Packaged receipt path cannot contain a link")
            if target.exists() and target.read_bytes() != raw:
                raise ValueError("Previously packaged frozen receipt changed: " + study + "/" + name)
            destination.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                target.write_bytes(raw)
            copied.append({"path": target.relative_to(root).as_posix(),
                           "sha256": hashlib.sha256(raw).hexdigest()})
    return copied


def main():
    parser = argparse.ArgumentParser(description="Package completed public research receipts")
    parser.add_argument("--root", default=str(ROOT))
    args = parser.parse_args()
    result = package_receipts(args.root)
    print("Packaged " + str(len(result)) + " frozen public receipts; no raw history or user state")


if __name__ == "__main__":
    main()
