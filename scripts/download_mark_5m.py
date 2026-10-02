#!/usr/bin/env python3
"""Acquire separately registered official mark OHLC, never synthetic fills."""
from __future__ import annotations

import argparse
import calendar
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from propdesk.exchange import ExchangeDataError
from propdesk.mark_data import fetch_archive

PROTOCOL = {
    "schema": 1, "data_protocol_id": "binance-usdm-btceth-calculated-mark-five-minute-2024-2026-v1",
    "declared_at": "2026-10-02", "symbols": ["BTCUSDT", "ETHUSDT"],
    "start": "2024-01-01T00:00:00Z", "end_exclusive": "2026-10-01T00:00:00Z",
    "interval": "5m", "interval_seconds": 300, "timestamp_unit": "milliseconds",
    "expected_bars_each": 289152, "quote_currency": "USDT",
    "provider": "Binance USD-M official checksum-verified markPriceKlines archives",
    "price_kind": "computed_mark_price", "trade_execution_evidence": False,
    "missing_data": "No imputation, stale-mark fill-forward, source substitution, sorting or duplicate removal.",
    "fallback": "Only September 2026 monthly HTTP404 may use all 30 official daily mark archives; any missing source blocks a complete output.",
    "knowledge": "UTC opening labels describe complete five-minute marks known no earlier than bar close; actual publication latency is unverified.",
    "permitted_research_role": "Historical computed-mark floating-equity bounds, collateral and provisional liquidation analysis; causal sizing uses preceding completed mark only.",
    "forbidden_inference": "Mark OHLC never establishes executable entry/exit prices, liquidity or queue fills. Zero source volume is normal for marks, not trading evidence.",
    "uncertainty": "Five-minute OHLC and auxiliary source counts do not prove uninterrupted tick sampling or exact account liquidation rules. No live qualification follows.",
    "data_license": "CC-BY-NC-SA-4.0; Binance Vision terms v1.0; personal non-production historical research",
    "live_orders": False, "strategy_outcomes_inspected": False,
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value, *, compact=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, allow_nan=False, **({"separators": (",", ":")} if compact else {"indent": 2})) + "\n"
    if path.exists() and path.read_text() != text:
        raise ValueError("Existing calculated-mark receipt differs; use a new acquisition directory")
    if not path.exists():
        with path.open("x") as stream:
            stream.write(text)


def months():
    return [(y, m) for y in (2024, 2025, 2026) for m in range(1, 13 if y < 2026 else 10)]


def chunk(symbol, year, month, cache):
    try:
        bars, source = fetch_archive(symbol, year, month, cache)
        return bars, [source], []
    except ExchangeDataError as exc:
        error = str(exc)
        if (year, month) != (2026, 9) or "HTTP 404" not in error:
            return [], [], [{"symbol": symbol, "year": year, "month": month, "error": error}]
    bars, sources, failures = [], [], []
    for day in range(1, calendar.monthrange(year, month)[1] + 1):
        try:
            rows, source = fetch_archive(symbol, year, month, cache, day=day)
            bars.extend(rows)
            sources.append(source)
        except ExchangeDataError as exc:
            failures.append({"symbol": symbol, "year": year, "month": month, "day": day,
                             "error": str(exc), "monthly_error": error})
    return bars, sources, failures


def download(data_dir, native_data_dir, workers=6):
    root, native_root = Path(data_dir), Path(native_data_dir)
    root.mkdir(parents=True, exist_ok=True)
    write_json(root / "protocol.json", PROTOCOL)
    native_path = native_root / "manifest.json"
    native = json.loads(native_path.read_text())
    if native["data_protocol_id"] != "binance-usdm-btceth-five-minute-2024-2026-v1":
        raise ValueError("Wrong native trade data protocol")
    native_by_symbol = {r["symbol"]: r for r in native["datasets"]}
    chunks = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        jobs = {pool.submit(chunk, s, y, m, root / "raw"): (s, y, m)
                for s in PROTOCOL["symbols"] for y, m in months()}
        for future in as_completed(jobs):
            key = jobs[future]
            chunks[key] = future.result()
            print("mark5m", *key, "bars", len(chunks[key][0]), "failures", len(chunks[key][2]), flush=True)
    datasets, calendars = [], []
    for symbol in PROTOCOL["symbols"]:
        rows, sources, failures = [], [], []
        for year, month in months():
            bars, receipts, errors = chunks[(symbol, year, month)]
            rows.extend(bars)
            sources.extend(receipts)
            failures.extend(errors)
        entry = {"symbol": symbol, "interval": "5m", "price_kind": "computed_mark_price",
                 "quote_currency": "USDT", "sources": sources, "failures": failures,
                 "bars": len(rows), "complete_calendar": not failures, "json": None}
        if not failures:
            if (len(rows) != PROTOCOL["expected_bars_each"] or rows[0]["time"] != PROTOCOL["start"]
                    or rows[-1]["known_at"] != PROTOCOL["end_exclusive"]):
                raise ValueError("Calculated marks miss the complete declared calendar")
            labels = [bar["time"] for bar in rows]
            clocks = [datetime.fromisoformat(label.replace("Z", "+00:00")) for label in labels]
            if any((b - a).total_seconds() != 300 for a, b in zip(clocks, clocks[1:])):
                raise ValueError("Calculated marks have an archive-boundary calendar gap")
            label_hash = hashlib.sha256(("\n".join(labels) + "\n").encode()).hexdigest()
            original = native_by_symbol[symbol]
            native_json = native_root / original["json"]
            if (original["failures"] or not original["complete_calendar"]
                    or original["bars"] != len(rows) or original["open_labels_sha256"] != label_hash
                    or sha(native_json) != original["json_sha256"]):
                raise ValueError("Calculated marks do not align with immutable native trade input")
            name = symbol + "-mark-5m.json"
            write_json(root / name, rows, compact=True)
            counts = Counter(bar["source_auxiliary_count"] for bar in rows)
            entry.update(json=name, json_sha256=sha(root / name),
                         first_open_at=rows[0]["time"], last_open_at=rows[-1]["time"],
                         last_known_at=rows[-1]["known_at"], open_labels_sha256=label_hash,
                         source_auxiliary_count_histogram={str(k): v for k, v in sorted(counts.items())},
                         zero_auxiliary_count_bars=counts.get(0, 0),
                         native_trade_json_sha256=original["json_sha256"])
            calendars.append(label_hash)
        datasets.append(entry)
    paths = ("scripts/download_mark_5m.py", "propdesk/mark_data.py", "propdesk/funding_data.py", "propdesk/market.py")
    manifest = {"schema": 1, "data_protocol_id": PROTOCOL["data_protocol_id"],
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "protocol_sha256": sha(root / "protocol.json"),
                "producer_hashes": {p: sha(ROOT / p) for p in paths},
                "native_trade_manifest_sha256": sha(native_path), "datasets": datasets,
                "assets_open_labels_aligned": len(calendars) == 2 and len(set(calendars)) == 1,
                "data_license": "CC-BY-NC-SA-4.0", "data_attribution": "Binance Vision https://data.binance.vision/",
                "trade_execution_evidence": False, "live_orders": False, "strategy_outcomes_inspected": False}
    write_json(root / "manifest.json", manifest)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT / ".local/mark-5m-history")
    parser.add_argument("--native-data-dir", type=Path, default=ROOT / ".local/perp-5m-history")
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()
    if not 1 <= args.workers <= 8:
        parser.error("Workers must be between 1 and 8")
    result = download(args.data_dir, args.native_data_dir, args.workers)
    if not result["assets_open_labels_aligned"] or not all(r["complete_calendar"] for r in result["datasets"]):
        raise SystemExit("Calculated-mark acquisition incomplete; keep source failures and do not certify coverage")
    print("complete calculated-mark inputs; no strategy PnL or executable-price claim")


if __name__ == "__main__":
    main()
