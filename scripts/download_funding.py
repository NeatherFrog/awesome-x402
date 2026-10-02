#!/usr/bin/env python3
"""Acquire registered official BTC/ETH USD-M history, without trading orders."""
from __future__ import annotations

import argparse
import calendar
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from propdesk.exchange import ExchangeDataError
from propdesk.funding_data import (event_fingerprint, fetch_archive,
                                  fetch_funding_rest_month, validate_events)
from propdesk.market import data_fingerprint, validate_bars

PROTOCOL = {
    "schema": 1, "data_protocol_id": "binance-usdm-btceth-funding-2024-2026-v1",
    "declared_at": "2026-10-02", "symbols": ["BTCUSDT", "ETHUSDT"],
    "start": "2024-01-01T00:00:00Z", "end_exclusive": "2026-10-01T00:00:00Z",
    "provider": "Binance USD-M perpetual official archives and documented funding REST",
    "kline_interval": "1h", "timestamp_unit": "milliseconds",
    "funding_schema": "calc_time,funding_interval_hours,last_funding_rate; preserve individual source intervals and realized UTC event times.",
    "monthly_unavailability": "Only September2026 HTTP404 may fall back: perp klines require all official daily files; funding requires documented fully-paginated official REST. If any source unavailable, record failure and no complete canonical file.",
    "missing_data": "No imputation, sorting, duplicate removal, cross-venue substitution or invented event rates.",
    "funding_knowledge": "Historical realized settlement outcomes are never forecasts; known_at denotes settlement label, not independently verified publication latency. REST historical interval-hours absent=>null.",
    "cost_assumptions_for_later_study": {"spot_fee_bps_per_side": 10, "perp_fee_bps_per_side": 5,
                                        "slippage_bps_per_side_each_leg": 2, "full_spread_bps_each_leg": 1},
    "unverified": ["Actual personal fee tier", "execution", "margin/liquidation", "borrow and funding forecast", "production data permission"],
    "dataset_license": "CC-BY-NC-SA-4.0, Binance Vision dataset terms v1.0; personal non-production historical research",
    "live_orders_enabled": False,
}


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def months():
    return [(year, month) for year in (2024, 2025, 2026)
            for month in range(1, 13 if year < 2026 else 10)]


def chunk(symbol, kind, year, month, cache_dir):
    try:
        values, source = fetch_archive(symbol, kind, year, month, cache_dir)
        return values, [source], []
    except ExchangeDataError as exc:
        error = str(exc)
        if (year, month) != (2026, 9) or "HTTP 404" not in error:
            return [], [], [{"symbol": symbol, "kind": kind, "year": year, "month": month, "error": error}]
    if kind == "fundingRate":
        try:
            values, source = fetch_funding_rest_month(symbol, year, month, cache_dir)
            return values, [source], []
        except ExchangeDataError as exc:
            return [], [], [{"symbol": symbol, "kind": kind, "year": year, "month": month,
                             "archive_error": error, "rest_error": str(exc)}]
    values, sources, failures = [], [], []
    for day in range(1, calendar.monthrange(year, month)[1] + 1):
        try:
            daily, source = fetch_archive(symbol, kind, year, month, cache_dir, day=day)
            values.extend(daily)
            sources.append(source)
        except ExchangeDataError as exc:
            failures.append({"symbol": symbol, "kind": kind, "year": year, "month": month,
                             "day": day, "error": str(exc)})
    return values, sources, failures


def download(data_dir, workers=4):
    root = Path(data_dir)
    root.mkdir(parents=True, exist_ok=True)
    protocol = root / "protocol.json"
    if protocol.exists() and json.loads(protocol.read_text()) != PROTOCOL:
        raise ValueError("Existing funding data protocol differs; preserve the frozen snapshot")
    write_json(protocol, PROTOCOL)
    tasks = [(symbol, kind, year, month) for symbol in PROTOCOL["symbols"]
             for kind in ("klines", "fundingRate") for year, month in months()]
    chunks = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(chunk, *task, root / "raw"): task for task in tasks}
        for future in as_completed(futures):
            task = futures[future]
            chunks[task] = future.result()
            print("funding-data", *task, "rows", len(chunks[task][0]), "failures", len(chunks[task][2]), flush=True)
    datasets = []
    for symbol in PROTOCOL["symbols"]:
        for kind in ("klines", "fundingRate"):
            values, sources, failures = [], [], []
            for year, month in months():
                chunk_values, chunk_sources, chunk_failures = chunks[(symbol, kind, year, month)]
                values.extend(chunk_values)
                sources.extend(chunk_sources)
                failures.extend(chunk_failures)
            entry = {"symbol": symbol, "kind": kind, "sources": sources, "failures": failures,
                     "complete_calendar": not failures, "rows": len(values), "json": None}
            if not failures:
                if kind == "klines":
                    values = validate_bars(values, max_bars=400_000)
                    if len(values) != 24096 or values[0]["time"] != PROTOCOL["start"] or values[-1]["time"] != "2026-09-30T23:00:00Z":
                        raise ValueError("Perpetual snapshot misses full declared calendar exposure")
                    for previous, current in zip(values, values[1:]):
                        left = datetime.fromisoformat(previous["time"].replace("Z", "+00:00"))
                        right = datetime.fromisoformat(current["time"].replace("Z", "+00:00"))
                        if (right - left).total_seconds() != 3600:
                            raise ValueError("Perpetual snapshot has an internal gap")
                    fingerprint = data_fingerprint(values)
                    name = f"{symbol}-1h.json"
                else:
                    validate_events(values)
                    fingerprint = event_fingerprint(values)
                    name = f"{symbol}-funding.json"
                path = root / name
                write_json(path, values)
                entry.update(json=name, json_sha256=digest(path), data_fingerprint=fingerprint,
                             first_at=values[0]["time"], last_at=values[-1]["time"])
            datasets.append(entry)
    manifest = {"schema": 1, "data_protocol_id": PROTOCOL["data_protocol_id"],
                "retrieved_at": datetime.now(timezone.utc).isoformat(), "protocol_sha256": digest(protocol),
                "producer_sha256": digest(__file__), "adapter_sha256": digest(ROOT / "propdesk" / "funding_data.py"),
                "datasets": datasets, "live_orders_enabled": False,
                "data_license": "CC-BY-NC-SA-4.0", "data_attribution": "Binance Vision https://data.binance.vision/"}
    write_json(root / "manifest.json", manifest)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default=str(ROOT / ".local" / "funding-history"))
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    if not 1 <= args.workers <= 8:
        parser.error("workers must be from1 through8")
    manifest = download(args.data_dir, args.workers)
    print("complete", all(entry["complete_calendar"] for entry in manifest["datasets"]))


if __name__ == "__main__":
    main()
