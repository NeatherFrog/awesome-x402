#!/usr/bin/env python3
"""Acquire separate fixed-cohort TRAIN sources only; no strategy performance."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from propdesk.cross_sectional_data import SYMBOLS, KINDS, digest, fetch_archive, validate_funding
from propdesk.exchange import ExchangeDataError

PROTOCOL = {
    "data_protocol_id": "binance-usdm-current-ftmo-eleven-cohort-hourly-training-v1",
    "symbols": list(SYMBOLS), "source_kinds": list(KINDS),
    "start": "2023-12-01T00:00:00Z", "end_exclusive": "2025-01-01T00:00:00Z",
    "scored_training_start": "2024-01-01T00:00:00Z", "expected_hourly_rows_each": 9528,
    "survivorship_conditioned": True, "historical_ftmo_eligibility_verified": False,
    "official_listing_dates_verified": False, "strategy_outcomes_inspected": False,
    "missing_policy": "Reject incomplete requested monthly source; no prefix performance, invented bars, current-winner removal or silent alternate source.",
    "funding": "Actual millisecond settlement outcomes/source intervals; not forecast or FTMO swap tariff.",
    "mark": "Computed mark1h OHLC for floating-risk bounds, never execution quotes; preserve auxiliary count without calling it trade volume.",
    "live_orders": False,
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    content = (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()
    if path.exists():
        if path.read_bytes() != content:
            raise ValueError(f"Refusing to overwrite different acquisition bytes: {path.name}")
    else:
        with path.open("xb") as stream:
            stream.write(content)


def months():
    return [(2023, 12)] + [(2024, m) for m in range(1, 13)]


def chunk(symbol, kind, year, month, root):
    try:
        rows, receipt = fetch_archive(symbol, kind, year, month, root / "raw")
        return rows, receipt, None
    except (ExchangeDataError, OSError, ValueError) as exc:
        return [], None, {"symbol": symbol, "kind": kind, "year": year, "month": month,
                          "error": str(exc)}


def download(data_dir, workers=6):
    root = Path(data_dir)
    root.mkdir(parents=True, exist_ok=True)
    if (root / "manifest.json").exists():
        raise ValueError("A completed/blocked acquisition manifest already exists; preserve this revision")
    write_json(root / "protocol.json", PROTOCOL)
    chunks = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        jobs = {pool.submit(chunk, s, k, y, m, root): (s, k, y, m)
                for s in SYMBOLS for k in KINDS for y, m in months()}
        for future in as_completed(jobs):
            key = jobs[future]
            chunks[key] = future.result()
            if chunks[key][2]:
                print("cross-source failure", *key, chunks[key][2]["error"], flush=True)
    datasets = []
    for symbol in SYMBOLS:
        for kind in KINDS:
            values, receipts, failures = [], [], []
            for year, month in months():
                rows, receipt, error = chunks[(symbol, kind, year, month)]
                values.extend(rows)
                if receipt:
                    receipts.append(receipt)
                if error:
                    failures.append(error)
            entry = {"symbol": symbol, "kind": kind, "sources": receipts,
                     "failures": failures, "rows": len(values), "complete_calendar": False,
                     "json": None, "observed_first_at": values[0]["time"] if values else None,
                     "observed_last_at": values[-1]["time"] if values else None}
            if not failures:
                if kind == "fundingRate":
                    validate_funding(values)
                else:
                    if (len(values) != PROTOCOL["expected_hourly_rows_each"]
                            or values[0]["time"] != PROTOCOL["start"]
                            or values[-1]["known_at"] != PROTOCOL["end_exclusive"]):
                        raise ValueError("Source lacks the complete registered stage calendar")
                    if any((datetime.fromisoformat(b["time"].replace("Z", "+00:00"))
                            - datetime.fromisoformat(a["time"].replace("Z", "+00:00"))).total_seconds() != 3600
                           for a, b in zip(values, values[1:])):
                        raise ValueError("Source has a cross-month hourly gap")
                filename = f"{symbol}-{kind}.json"
                write_json(root / filename, values)
                entry.update(json=filename, json_sha256=sha(root / filename),
                             data_fingerprint=digest(values), complete_calendar=True)
            datasets.append(entry)
    producers = ("scripts/download_cross_sectional.py", "propdesk/cross_sectional_data.py",
                 "propdesk/funding_data.py", "propdesk/market.py")
    manifest = {"schema": 1, "data_protocol_id": PROTOCOL["data_protocol_id"],
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "protocol_sha256": sha(root / "protocol.json"),
                "producer_hashes": {p: sha(ROOT / p) for p in producers}, "datasets": datasets,
                "all_requested_sources_complete": all(d["complete_calendar"] for d in datasets),
                "data_license": "CC-BY-NC-SA-4.0", "attribution": "Binance Vision https://data.binance.vision/",
                "survivorship_conditioned": True, "prop_execution_verified": False,
                "live_orders": False, "strategy_outcomes_inspected": False}
    write_json(root / "manifest.json", manifest)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT / ".local/cross-sectional-training-v1")
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()
    if not 1 <= args.workers <= 8:
        parser.error("Workers must be between 1 and 8")
    result = download(args.data_dir, args.workers)
    print(json.dumps({"all_requested_sources_complete": result["all_requested_sources_complete"],
                      "datasets": len(result["datasets"]), "strategy_outcomes_inspected": False}))
    if not result["all_requested_sources_complete"]:
        raise SystemExit("Incomplete fixed cohort/source calendar; no prefix performance permitted")


if __name__ == "__main__":
    main()
