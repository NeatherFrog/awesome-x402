#!/usr/bin/env python3
"""Registered mark-source revision: complete June from all official daily ZIPs."""
from __future__ import annotations

import argparse
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
from propdesk.funding_data import _request, _rows
from propdesk.mark_data import HEADER, archive_urls, fetch_archive
from scripts import download_mark_5m as prior

PREDECESSOR = {
    "data_protocol_id": prior.PROTOCOL["data_protocol_id"],
    "manifest_sha256": "3029309a8533141dda91ddc4ade82b3b470d07cdf69552caa75cc367ba7e65fe",
    "protocol_sha256": "252c687ff8cae38ab9a65f3469710794b5dc45f11487e96ca9e7e292deeab250",
    "state": "blocked; both June 2026 monthly ZIPs omit all 288 June29 bars",
}
REJECTED_JUNE_SHA = {
    "BTCUSDT": "e02cf899d32a506fcb3165e795040dadea291989bdd12082bec1a83875d908fc",
    "ETHUSDT": "de38736aea72c09d2802071b7c49bb108557fc5a5c81022bf8d706fd7e42430d",
}
PROTOCOL = {
    **prior.PROTOCOL,
    "data_protocol_id": "binance-usdm-btceth-calculated-mark-five-minute-2024-2026-v2",
    "source_revision": 2, "predecessor": PREDECESSOR,
    "fallback": "Exact documented June2026 omission: replace the entire June container with all30 same-venue official daily mark ZIPs, each checksum/calendar verified. Existing monthly overlap must agree in OHLC; no borrowed/inserted/fill-forward prices. Original blocked revision remains immutable. Other months retain prior strict source policy.",
    "source_revision_selection": "Chosen only from a verified archive-calendar defect before new mark-strategy outcomes; strategy/risk parameters unchanged.",
}


def monthly_witness(symbol, cache):
    url, sum_url, name = archive_urls(symbol, 2026, 6)
    root = Path(cache)
    archive_path, checksum_path = root / name, root / (name + ".CHECKSUM")
    content = archive_path.read_bytes() if archive_path.exists() else _request(url)
    checksum = checksum_path.read_bytes() if checksum_path.exists() else _request(sum_url, 1024)
    rows, source = _rows(content, checksum, name)
    if not rows or tuple(rows.pop(0)) != HEADER or any(len(row) != 12 for row in rows):
        raise ExchangeDataError("Documented incomplete June witness has wrong original format")
    if source["zip_sha256"] != REJECTED_JUNE_SHA[symbol]:
        raise ExchangeDataError("Documented June monthly source bytes changed; acquire a distinct revision")
    begin = int(datetime(2026, 6, 1, tzinfo=timezone.utc).timestamp() * 1000)
    absent = int(datetime(2026, 6, 29, tzinfo=timezone.utc).timestamp() * 1000)
    expected = [t for t in range(begin, begin + 30 * 86400000, 300000)
                if not absent <= t < absent + 86400000]
    if [int(row[0]) for row in rows] != expected:
        raise ExchangeDataError("Monthly witness differs from the exact registered June29 calendar omission")
    for path, value in ((archive_path, content), (checksum_path, checksum)):
        if not path.exists():
            with path.open("xb") as stream:
                stream.write(value)
    source.update(source_url=url, rejected_reason="Missing exactly all288 June29 intervals",
                  original_rows=len(rows), missing_intervals=288, used_for_prices=False)
    return rows, source


def complete_chunk(symbol, year, month, cache):
    if (year, month) != (2026, 6):
        rows, sources, errors = prior.chunk(symbol, year, month, cache)
        return rows, sources, errors, []
    try:
        original, witness = monthly_witness(symbol, cache)
    except (ExchangeDataError, OSError, ValueError) as exc:
        return [], [], [{"symbol": symbol, "year": year, "month": month, "error": str(exc)}], []
    rows, sources, failures = [], [], []
    for day in range(1, 31):
        try:
            daily, source = fetch_archive(symbol, year, month, cache, day=day)
            rows.extend(daily)
            sources.append(source)
        except (ExchangeDataError, OSError) as exc:
            failures.append({"symbol": symbol, "year": year, "month": month,
                             "day": day, "error": str(exc)})
    if not failures:
        by_open = {int(datetime.fromisoformat(row["time"].replace("Z", "+00:00")).timestamp() * 1000): row for row in rows}
        price_differences = auxiliary_differences = 0
        for old in original:
            current = by_open.get(int(old[0]))
            if current is None:
                failures.append({"symbol": symbol, "error": "Official June daily set misses a preserved monthly timestamp"})
                break
            price_differences += any(float(old[k]) != current[field]
                                     for k, field in enumerate(("open", "high", "low", "close"), 1))
            auxiliary_differences += int(old[8]) != current["source_auxiliary_count"]
        witness.update(daily_overlap_ohlc_difference_rows=price_differences,
                       daily_overlap_auxiliary_count_difference_rows=auxiliary_differences,
                       all30_daily_sources_verified=True)
        if price_differences:
            failures.append({"symbol": symbol, "error": "Official June daily OHLC disagrees with preserved monthly overlap"})
    return rows, sources, failures, [witness]


def download(data_dir, native_data_dir, workers=6):
    root, native_root = Path(data_dir), Path(native_data_dir)
    root.mkdir(parents=True, exist_ok=True)
    prior.write_json(root / "protocol.json", PROTOCOL)
    native_path = native_root / "manifest.json"
    native = json.loads(native_path.read_text())
    if native["data_protocol_id"] != "binance-usdm-btceth-five-minute-2024-2026-v1":
        raise ValueError("Wrong native trade protocol")
    originals = {r["symbol"]: r for r in native["datasets"]}
    chunks = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        jobs = {pool.submit(complete_chunk, s, y, m, root / "raw"): (s, y, m)
                for s in PROTOCOL["symbols"] for y, m in prior.months()}
        for future in as_completed(jobs):
            key = jobs[future]
            chunks[key] = future.result()
            print("complete-mark5m", *key, "bars", len(chunks[key][0]), "failures", len(chunks[key][2]), flush=True)
    datasets, calendars = [], []
    for symbol in PROTOCOL["symbols"]:
        rows, sources, failures, rejected = [], [], [], []
        for year, month in prior.months():
            chunk, receipts, errors, witnesses = chunks[(symbol, year, month)]
            rows.extend(chunk); sources.extend(receipts); failures.extend(errors); rejected.extend(witnesses)
        entry = {"symbol": symbol, "interval": "5m", "price_kind": "computed_mark_price",
                 "quote_currency": "USDT", "sources": sources, "rejected_sources": rejected,
                 "failures": failures, "bars": len(rows), "complete_calendar": not failures, "json": None}
        if not failures:
            if (len(rows) != PROTOCOL["expected_bars_each"] or rows[0]["time"] != PROTOCOL["start"]
                    or rows[-1]["known_at"] != PROTOCOL["end_exclusive"]):
                raise ValueError("Calculated marks lack complete registered exposure")
            labels = [bar["time"] for bar in rows]
            clocks = [datetime.fromisoformat(t.replace("Z", "+00:00")) for t in labels]
            if any((b - a).total_seconds() != 300 for a, b in zip(clocks, clocks[1:])):
                raise ValueError("Calculated marks have a calendar boundary gap")
            label_hash = hashlib.sha256(("\n".join(labels) + "\n").encode()).hexdigest()
            original = originals[symbol]
            if (original["failures"] or not original["complete_calendar"] or original["bars"] != len(rows)
                    or original["open_labels_sha256"] != label_hash
                    or prior.sha(native_root / original["json"]) != original["json_sha256"]):
                raise ValueError("Computed marks differ from immutable native trade calendar")
            name = symbol + "-mark-5m.json"
            prior.write_json(root / name, rows, compact=True)
            counts = Counter(row["source_auxiliary_count"] for row in rows)
            entry.update(json=name, json_sha256=prior.sha(root / name), open_labels_sha256=label_hash,
                         first_open_at=rows[0]["time"], last_open_at=rows[-1]["time"],
                         last_known_at=rows[-1]["known_at"], native_trade_json_sha256=original["json_sha256"],
                         source_auxiliary_count_histogram={str(k): v for k, v in sorted(counts.items())},
                         zero_auxiliary_count_bars=counts.get(0, 0))
            calendars.append(label_hash)
        datasets.append(entry)
    producers = ("scripts/download_mark_5m_complete.py", "scripts/download_mark_5m.py",
                 "propdesk/mark_data.py", "propdesk/funding_data.py", "propdesk/market.py")
    manifest = {"schema": 1, "data_protocol_id": PROTOCOL["data_protocol_id"],
                "retrieved_at": datetime.now(timezone.utc).isoformat(), "protocol_sha256": prior.sha(root / "protocol.json"),
                "predecessor": PREDECESSOR, "producer_hashes": {p: prior.sha(ROOT / p) for p in producers},
                "native_trade_manifest_sha256": prior.sha(native_path), "datasets": datasets,
                "assets_open_labels_aligned": len(calendars) == 2 and len(set(calendars)) == 1,
                "data_license": "CC-BY-NC-SA-4.0", "data_attribution": "Binance Vision https://data.binance.vision/",
                "trade_execution_evidence": False, "live_orders": False, "strategy_outcomes_inspected": False}
    prior.write_json(root / "manifest.json", manifest)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT / ".local/mark-5m-complete-history")
    parser.add_argument("--native-data-dir", type=Path, default=ROOT / ".local/perp-5m-history")
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()
    if not 1 <= args.workers <= 8:
        parser.error("Workers must be between 1 and 8")
    result = download(args.data_dir, args.native_data_dir, args.workers)
    if not result["assets_open_labels_aligned"] or not all(r["complete_calendar"] for r in result["datasets"]):
        raise SystemExit("Mark revision remains incomplete; preserve failures, no full-source certification")
    print("complete official calculated-mark source revision; no strategy outcomes")


if __name__ == "__main__":
    main()
