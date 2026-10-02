#!/usr/bin/env python3
"""Frozen BTC/ETH Binance-Spot archive study; no order or Telegram API calls.

--download-only is independent of the strategy engine and usable on a GitHub
runner when the development proxy cannot reach Binance public archives.
"""
from __future__ import annotations

import argparse
import calendar
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from propdesk.exchange import ExchangeDataError, fetch_archive
from propdesk.market import data_fingerprint, validate_bars

PLAN = {
    "schema": 1, "study_id": "binance-spot-btceth-liquidity-fixed-v1",
    "declared_at": "2026-10-02", "provider": "Binance Spot official archive",
    "symbols": ["BTCUSDT", "ETHUSDT"], "intervals": ["5m", "1h"],
    "train": ["2024-01-01T00:00:00Z", "2025-01-01T00:00:00Z"],
    "validation": ["2025-01-01T00:00:00Z", "2026-01-01T00:00:00Z"],
    "final": ["2026-01-01T00:00:00Z", "2026-10-01T00:00:00Z"],
    "variants": ["sweep_all", "mss_all", "sweep_lunch", "mss_lunch"],
    "selection": "Highest positive 2024 train net_profit aggregated equally across BTC/ETH; otherwise none. No replacement using validation/final outcomes.",
    "costs": {"fee_bps": 10, "slippage_bps": 2, "spread_bps": 1},
    "execution_model": "Theoretical long/short OHLC limit-touch study; spot short borrowing/execution unverified. No qualified live strategy regardless of positive returns.",
    "missing_data_policy": "No imputation or deletion of unavailable exposure; any missing calendar chunk makes that symbol/timeframe ineligible. For September2026 only, missing monthly HTTP404 may be replaced by all official daily ZIPs for same venue.",
    "rejected": "Retain every variant and period; final inspection never makes a failed variant a new winner.",
    "live_orders_enabled": False,
}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def months():
    return [(year, month) for year in (2024, 2025, 2026)
            for month in range(1, 13 if year < 2026 else 10)]


def _download_chunk(symbol, interval, year, month, cache_dir):
    try:
        bars, source = fetch_archive(symbol, interval, year, month, cache_dir)
        return bars, [source], []
    except ExchangeDataError as exc:
        # September's monthly file normally appears only on the first Monday
        # of October; all 30 daily files are equivalent complete venue exposure.
        if (year, month) != (2026, 9) or "HTTP 404" not in str(exc):
            return [], [], [{"symbol": symbol, "interval": interval, "year": year,
                             "month": month, "error": str(exc)}]
    bars, sources, failures = [], [], []
    for day in range(1, calendar.monthrange(year, month)[1] + 1):
        try:
            daily, source = fetch_archive(symbol, interval, year, month, cache_dir, day=day)
            bars.extend(daily)
            sources.append(source)
        except ExchangeDataError as exc:
            failures.append({"symbol": symbol, "interval": interval, "year": year,
                             "month": month, "day": day, "error": str(exc)})
    return bars, sources, failures


def download(data_dir, intervals=("5m", "1h"), workers=4, smc_start_month="2024-01"):
    """Snapshot the immutable plan before any download or return calculation."""
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    protocol = data_dir / "protocol.json"
    if protocol.exists() and json.loads(protocol.read_text()) != PLAN:
        raise ValueError("Existing protocol differs; do not change a frozen experiment")
    write_json(protocol, PLAN)
    if smc_start_month not in {f"{year:04d}-{month:02d}" for year, month in months()}:
        raise ValueError("5m start month must be within the frozen calendar")
    chunks = {}
    tasks = [(symbol, interval, year, month) for symbol in PLAN["symbols"]
             for interval in intervals for year, month in months()
             if interval != "5m" or f"{year:04d}-{month:02d}" >= smc_start_month]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_download_chunk, *task, data_dir / "raw"): task for task in tasks}
        for future in as_completed(futures):
            task = futures[future]
            chunks[task] = future.result()
            print("archive", *task, "bars", len(chunks[task][0]), "failures", len(chunks[task][2]), flush=True)
    datasets = []
    for symbol in PLAN["symbols"]:
        for interval in intervals:
            bars, sources, failures = [], [], []
            requested_months = [(year, month) for year, month in months()
                                if interval != "5m" or f"{year:04d}-{month:02d}" >= smc_start_month]
            for year, month in requested_months:
                chunk_bars, chunk_sources, chunk_failures = chunks[(symbol, interval, year, month)]
                bars.extend(chunk_bars)
                sources.extend(chunk_sources)
                failures.extend(chunk_failures)
            entry = {"symbol": symbol, "interval": interval, "sources": sources,
                     "failures": failures, "complete_calendar": not failures and requested_months == months(),
                     "requested_calendar_complete": not failures,
                     "requested_start_month": f"{requested_months[0][0]:04d}-{requested_months[0][1]:02d}",
                     "limited_acquisition": requested_months != months(),
                     "bars": len(bars), "csv": None}
            if not failures:
                bars = validate_bars(bars, max_bars=400_000)
                seconds = 300 if interval == "5m" else 3600
                start_year, start_month = requested_months[0]
                expected = int((datetime(2026, 10, 1, tzinfo=timezone.utc)
                                - datetime(start_year, start_month, 1, tzinfo=timezone.utc)).total_seconds()) // seconds
                if len(bars) != expected:
                    raise ValueError("Complete source chunks do not cover the frozen calendar")
                path = data_dir / f"{symbol}-{interval}.csv"
                with path.open("w", encoding="utf-8", newline="") as stream:
                    writer = csv.DictWriter(stream, fieldnames=("time", "open", "high", "low", "close", "volume"), lineterminator="\n")
                    writer.writeheader()
                    writer.writerows(bars)
                entry.update(csv=path.name, csv_sha256=digest(path),
                             data_fingerprint=data_fingerprint(bars),
                             first_open_at=bars[0]["time"], last_open_at=bars[-1]["time"])
                json_path = data_dir / f"{symbol}-{interval}.json"
                write_json(json_path, bars)
                entry.update(json=json_path.name, json_sha256=digest(json_path))
            datasets.append(entry)
    manifest = {"schema": 1, "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "protocol_sha256": digest(protocol), "datasets": datasets,
                "spot_execution_validated": False, "live_orders_enabled": False}
    write_json(data_dir / "manifest.json", manifest)
    return manifest


def load_dataset(data_dir, entry):
    if not entry.get("complete_calendar") or not entry.get("csv"):
        raise ValueError("Incomplete calendar exposure cannot enter a backtest")
    path = Path(data_dir) / entry["csv"]
    if digest(path) != entry["csv_sha256"]:
        raise ValueError("Snapshot CSV hash changed")
    with path.open(encoding="utf-8", newline="") as stream:
        bars = validate_bars(list(csv.DictReader(stream)), max_bars=400_000)
    if data_fingerprint(bars) != entry["data_fingerprint"]:
        raise ValueError("Canonical data fingerprint changed")
    return bars


def research(data_dir, output):
    from propdesk.liquidity import backtest
    data_dir = Path(data_dir)
    if json.loads((data_dir / "protocol.json").read_text()) != PLAN:
        raise ValueError("Frozen protocol mismatch")
    manifest = json.loads((data_dir / "manifest.json").read_text())
    entries = [item for item in manifest["datasets"] if item["interval"] == "5m"]
    base = {"schema": 1, "study_id": PLAN["study_id"], "plan": PLAN,
            "data_manifest_sha256": digest(data_dir / "manifest.json"),
            "engine_sha256": digest(ROOT / "propdesk" / "liquidity.py"),
            "producer_sha256": digest(__file__), "selected": None,
            "qualified": False, "live_orders_enabled": False, "trials": []}
    if len(entries) != 2 or any(not item["complete_calendar"] for item in entries):
        base.update(status="blocked_incomplete_data", source_availability=entries,
                    reason="No complete frozen BTC/ETH 2024-2026 calendar; no backtest fabricated.")
        write_json(output, base)
        return base
    data = {entry["symbol"]: load_dataset(data_dir, entry) for entry in entries}
    config = {**PLAN["costs"], "interval_seconds": 300, "initial_balance": 100_000,
              "risk_pct": .25, "max_gross_leverage": 1, "expiry_bars": 6}
    # Produce training results and seal the winner before viewing later periods.
    train_scores = {}
    for variant in PLAN["variants"]:
        score = 0
        for symbol, bars in data.items():
            subset = [bar for bar in bars if PLAN["train"][0] <= bar["time"] < PLAN["train"][1]]
            result = backtest(subset, symbol=symbol, variant=variant, config=config)
            metrics = result["metrics"]
            base["trials"].append({"variant": variant, "symbol": symbol, "period": "train", "metrics": metrics})
            score += metrics["net_profit"]
        train_scores[variant] = score
    candidate = max(PLAN["variants"], key=lambda variant: train_scores[variant])
    selected = candidate if train_scores[candidate] > 0 else None
    lock = {"study_id": PLAN["study_id"], "train_scores": train_scores,
            "selected": selected, "protocol_sha256": digest(data_dir / "protocol.json"),
            "engine_sha256": base["engine_sha256"], "data_manifest_sha256": base["data_manifest_sha256"]}
    write_json(data_dir / "training-lock.json", lock)
    base["selected"] = selected
    base["training_lock"] = lock
    for period in ("validation", "final"):
        for variant in PLAN["variants"]:
            for symbol, bars in data.items():
                subset = [bar for bar in bars if PLAN[period][0] <= bar["time"] < PLAN[period][1]]
                result = backtest(subset, symbol=symbol, variant=variant, config=config)
                base["trials"].append({"variant": variant, "symbol": symbol, "period": period, "metrics": result["metrics"]})
    base.update(status="completed", trials_count=len(base["trials"]),
                interpretation="Descriptive historical evidence only; ordinary spot shorts and live execution unverified. Inspecting all final variants makes this dataset unavailable as a fresh blind test for future selection.")
    write_json(output, base)
    return base


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default=str(ROOT / ".local" / "exchange-history"))
    parser.add_argument("--output", default=str(ROOT / "docs" / "liquidity-research.json"))
    parser.add_argument("--download-only", action="store_true")
    parser.add_argument("--research-only", action="store_true")
    parser.add_argument("--intervals", choices=("5m", "1h", "both"), default="both")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--5m-start-month", default="2024-01", dest="smc_start_month",
                        help="Limit initial acquisition, e.g.2026-07; cannot qualify the frozen full-calendar SMC study")
    args = parser.parse_args()
    if args.download_only and args.research_only:
        parser.error("Choose download-only or research-only")
    if not 1 <= args.workers <= 8:
        parser.error("workers must be from1 through8")
    if not args.research_only:
        download(args.data_dir, ("5m", "1h") if args.intervals == "both" else (args.intervals,), args.workers, args.smc_start_month)
    if not args.download_only:
        result = research(args.data_dir, args.output)
        print(result["status"], "qualified", result["qualified"], "selected", result["selected"])


if __name__ == "__main__":
    main()
