#!/usr/bin/env python3
"""Five-minute same-venue perp inputs for separately registered spread studies."""
from __future__ import annotations

import argparse
import calendar
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from propdesk.exchange import ExchangeDataError
from propdesk.market import data_fingerprint, validate_bars
from propdesk.perp_resolution import fetch_archive

PROTOCOL = {
    "schema": 1, "data_protocol_id": "binance-usdm-btceth-five-minute-2024-2026-v1",
    "declared_at": "2026-10-02", "symbols": ["BTCUSDT", "ETHUSDT"],
    "start": "2024-01-01T00:00:00Z", "end_exclusive": "2026-10-01T00:00:00Z",
    "interval": "5m", "interval_seconds": 300, "timestamp_unit": "milliseconds",
    "expected_bars_each": 289152, "quote_currency": "USDT",
    "provider": "Binance USD-M perpetual official checksum-verified archives",
    "missing_data": "No imputation, sorting, duplicate removal, venue substitution or replacement prices.",
    "fallback": "Only September2026 monthlyHTTP404 may use all30official daily archives; otherwise missing exposure blocks complete canonical output.",
    "knowledge": "OHLC known after each bar closes, not at UTC opening label. Five-minute bars improve resolution but do not reveal synchronized intrabar price paths.",
    "alignment": "Both assets' UTC open labels must match each other and the fixed spot calendar; prices must remain independently sourced and are never equated.",
    "data_license": "CC-BY-NC-SA-4.0; Binance Vision Dataset Terms v1.0; personal non-production historical research",
    "not_verified": ["Mark-price path", "maintenance margin/liquidation", "executable bid/ask", "queue/latency", "profitability", "production permissions"],
    "live_orders": False,
}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value, *, compact=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(value, ensure_ascii=False, allow_nan=False,
                     **({"separators": (",", ":")} if compact else {"indent": 2})) + "\n"
    if path.exists() and path.read_text() != raw:
        raise ValueError("Existing canonical snapshot differs; use a new data directory")
    if not path.exists():
        with path.open("x", encoding="utf-8") as stream:
            stream.write(raw)


def months():
    return [(year, month) for year in (2024, 2025, 2026)
            for month in range(1, 13 if year < 2026 else 10)]


def chunk(symbol, year, month, cache_dir):
    try:
        bars, source = fetch_archive(symbol, year, month, cache_dir)
        return bars, [source], []
    except ExchangeDataError as exc:
        original_error = str(exc)
        if (year, month) != (2026, 9) or "HTTP 404" not in original_error:
            return [], [], [{"symbol": symbol, "year": year, "month": month, "error": original_error}]
    bars, sources, errors = [], [], []
    for day in range(1, calendar.monthrange(year, month)[1] + 1):
        try:
            daily, source = fetch_archive(symbol, year, month, cache_dir, day=day)
            bars.extend(daily)
            sources.append(source)
        except ExchangeDataError as exc:
            errors.append({"symbol": symbol, "year": year, "month": month,
                           "day": day, "error": str(exc), "monthly_error": original_error})
    return bars, sources, errors


def download(data_dir, workers=4):
    root = Path(data_dir)
    root.mkdir(parents=True, exist_ok=True)
    protocol = root / "protocol.json"
    write_json(protocol, PROTOCOL)
    chunks = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        jobs = {pool.submit(chunk, symbol, year, month, root / "raw"): (symbol, year, month)
                for symbol in PROTOCOL["symbols"] for year, month in months()}
        for future in as_completed(jobs):
            key = jobs[future]
            chunks[key] = future.result()
            print("perp5m", *key, "bars", len(chunks[key][0]), "failures", len(chunks[key][2]), flush=True)
    datasets, calendars = [], {}
    for symbol in PROTOCOL["symbols"]:
        bars, sources, failures = [], [], []
        for year, month in months():
            data, source, errors = chunks[(symbol, year, month)]
            bars.extend(data)
            sources.extend(source)
            failures.extend(errors)
        entry = {"symbol": symbol, "interval": "5m", "bars": len(bars), "sources": sources,
                 "failures": failures, "complete_calendar": not failures, "json": None}
        if not failures:
            bars = validate_bars(bars, max_bars=400_000)
            if (len(bars) != PROTOCOL["expected_bars_each"] or bars[0]["time"] != PROTOCOL["start"]
                    or bars[-1]["time"] != "2026-09-30T23:55:00Z"):
                raise ValueError("Five-minute perpetual snapshot misses declared calendar exposure")
            # Every chunk is strict-consecutive; verify boundaries again.
            stamps = [datetime.fromisoformat(bar["time"].replace("Z", "+00:00")) for bar in bars]
            if any((right - left).total_seconds() != 300 for left, right in zip(stamps, stamps[1:])):
                raise ValueError("Perpetual snapshot has a month/day boundary gap")
            name = symbol + "-5m.json"
            path = root / name
            write_json(path, bars, compact=True)
            labels = [bar["time"] for bar in bars]
            calendars[symbol] = hashlib.sha256(("\n".join(labels) + "\n").encode()).hexdigest()
            entry.update(json=name, json_sha256=digest(path), data_fingerprint=data_fingerprint(bars),
                         open_labels_sha256=calendars[symbol], first_open_at=bars[0]["time"],
                         last_open_at=bars[-1]["time"], quote_currency="USDT")
        datasets.append(entry)
    if len(calendars) == 2 and len(set(calendars.values())) != 1:
        raise ValueError("BTC and ETH perpetual timestamps do not align")
    producer_paths = ("scripts/download_perp_5m.py", "propdesk/perp_resolution.py", "propdesk/funding_data.py", "propdesk/exchange.py", "propdesk/market.py")
    manifest = {"schema": 1, "data_protocol_id": PROTOCOL["data_protocol_id"],
                "retrieved_at": datetime.now(timezone.utc).isoformat(), "protocol_sha256": digest(protocol),
                "producer_hashes": {name: digest(ROOT / name) for name in producer_paths},
                "datasets": datasets, "assets_open_labels_aligned": len(calendars) == 2 and len(set(calendars.values())) == 1,
                "data_license": "CC-BY-NC-SA-4.0", "data_attribution": "Binance Vision https://data.binance.vision/",
                "live_orders": False, "profitability_verified": False}
    # Manifest records fresh acquisition timing; an existing completed receipt
    # must remain immutable rather than become silently refreshed.
    write_json(root / "manifest.json", manifest)
    return manifest


def publish_ci(data_dir):
    """Publish attributed inputs on a separate branch using runner Git auth."""
    sha = os.environ.get("GITHUB_SHA", "")
    if (os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("GITHUB_REPOSITORY") != "NeatherFrog/awesome-x402"
            or not re.fullmatch(r"[0-9a-f]{40}", sha)):
        raise ValueError("Publication is restricted to this repository's own authorized Actions runner")
    root = Path(data_dir)
    manifest = json.loads((root / "manifest.json").read_text())
    if not all(item["complete_calendar"] for item in manifest["datasets"]) or not manifest["assets_open_labels_aligned"]:
        raise ValueError("Incomplete or misaligned research data cannot be published")
    origin = subprocess.check_output(["git", "remote", "get-url", "origin"], text=True).strip()
    if origin not in ("https://github.com/NeatherFrog/awesome-x402", "https://github.com/NeatherFrog/awesome-x402.git"):
        raise ValueError("Unexpected repository origin")
    attribution = ("Binance Vision public USD-M data, retrieved " + manifest["retrieved_at"] + ".\n"
                   "Original source: https://data.binance.vision/\n"
                   "Canonical OHLCV conversion only; no source prices repaired.\n"
                   "License: CC BY-NC-SA 4.0 https://creativecommons.org/licenses/by-nc-sa/4.0/\n"
                   "Dataset terms: https://github.com/binance/binance-public-data/blob/f446ce3812bd4e5521f21faecd4ae3c6460e49fc/TERMS_AND_CONDITIONS.md\n"
                   "Personal non-production research only; not live execution or production permission.\n")
    write_json(root / "publication.json", {"producer_commit": sha, "manifest_sha256": digest(root / "manifest.json")})
    files = {name: (root / name).read_bytes() for name in ("BTCUSDT-5m.json", "ETHUSDT-5m.json", "manifest.json", "protocol.json", "publication.json")}
    files["ATTRIBUTION.txt"] = attribution.encode()
    files["LICENSE.txt"] = b"CC BY-NC-SA 4.0 International\nhttps://creativecommons.org/licenses/by-nc-sa/4.0/legalcode.en\n"
    records = []
    for name, content in sorted(files.items()):
        if len(content) >= 95 * 1024 * 1024:
            raise ValueError("Research export exceeds the bounded GitHub file size")
        blob = subprocess.check_output(["git", "hash-object", "-w", "--stdin"], input=content).decode().strip()
        records.append("100644 blob " + blob + "\t" + name + "\n")
    tree = subprocess.check_output(["git", "mktree"], input="".join(records).encode()).decode().strip()
    commit = subprocess.check_output(["git", "-c", "user.email=research@users.noreply.github.com", "-c", "user.name=Research inputs", "commit-tree", tree],
                                     input=b"Attributed official five-minute USD-M research inputs\n").decode().strip()
    branch = "perp5m-data-" + sha[:12]
    subprocess.run(["git", "push", "origin", commit + ":refs/heads/" + branch], check=True, capture_output=True)
    print("published research branch", branch, "commit", commit)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default=str(ROOT / ".local" / "perp-5m-history"))
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--publish-ci", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.workers <= 8:
        parser.error("workers must be from1 through8")
    manifest = download(args.data_dir, args.workers)
    print("complete", all(entry["complete_calendar"] for entry in manifest["datasets"]))
    if args.publish_ci:
        publish_ci(args.data_dir)


if __name__ == "__main__":
    main()
