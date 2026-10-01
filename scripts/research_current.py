#!/usr/bin/env python3
"""One frozen, snapshot-backed current eight-market experiment.

The protocol and cost models are saved before fetching any prices. The global
training lock is saved before any holdout evaluation. Failures never cause a
replacement symbol, parameter search, synthetic fallback or broker order.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from propdesk import feeds, market, scanner  # noqa: E402
from propdesk.risk import default_profiles  # noqa: E402
from propdesk.server import execution_assumptions  # noqa: E402

SYMBOLS = ("EURUSD", "XAUUSD", "NAS100", "BTCUSD", "MES=F", "MNQ=F", "AAPL", "MSFT")
ALIASES = {"EURUSD": "EURUSD=X", "XAUUSD": "GC=F", "NAS100": "^NDX", "BTCUSD": "BTC-USD"}
INTERVAL = "1h"
RANGE = "2y"
DEFAULT_OUTPUT = ROOT / "docs" / "current-research.json"
DEFAULT_SNAPSHOTS = ROOT / "data" / "current-history"


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def file_digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_report(path, report):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, prefix=".current-research-", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(canonical(report) + "\n")
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def immutable_write(path, contents):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="") as handle:
        handle.write(contents)


def engine_sources():
    names = ("market.py", "strategies.py", "backtest.py", "scanner.py", "risk.py", "payout.py", "compliance.py", "feeds.py", "timezones.py")
    values = {f"propdesk/{name}": file_digest(ROOT / "propdesk" / name) for name in names}
    values["scripts/research_current.py"] = file_digest(Path(__file__))
    return values


def freeze_protocol():
    as_of = datetime.now(timezone.utc).replace(microsecond=0)
    profile = default_profiles()[0]
    settings = {"account_size": 100000, "account_currency": "USD", "risk_pct": 0.25,
                "fee_bps": 10, "slippage_bps": 2, "spread_bps": 2, "train_fraction": 0.6,
                "max_leverage": 2, "contract_multiplier": 1, "quantity_step": profile["quantity_step"],
                "max_drawdown_pct": profile["max_loss_pct"] * 0.8, "prop_profile": profile,
                "as_of": as_of.isoformat().replace("+00:00", "Z")}
    models = {symbol: execution_assumptions(symbol, {"provider_symbol": ALIASES.get(symbol, symbol)}) for symbol in SYMBOLS}
    return {"version": "current-eight-markets-v1", "frozen_at": settings["as_of"], "symbols": list(SYMBOLS),
            "interval": INTERVAL, "range": RANGE, "settings": settings, "execution_models": models,
            "cost_status": "Predeclared research assumptions, not independently verified broker tariffs",
            "selection": "All seven fixed families and existing grids on training only; global primary and top-three diagnostics locked before holdouts",
            "qualification": "Existing scanner 99% descriptive bootstrap, minimum20holdouttrades, no primary substitution",
            "firm_rules": "Generic static illustrative profile only. No claim to have verified or selected a real prop firm.",
            "missing_data": "Record failure and proceed only with available originally declared symbols; never replace symbols or impute prices",
            "execution": "Paper research only; no broker authentication, orders, deposits or account purchases"}


def snapshot(symbol, dataset, directory, as_of, requested_at, received_at):
    bars = market.validate_bars(dataset["bars"])
    if any(market.utc_datetime(bar["time"]) >= as_of for bar in bars):
        raise ValueError("History contains a current or future opening timestamp beyond the frozen analysis clock")
    if len(bars) < 300:
        raise ValueError("At least300closedbars required; no shortened or synthetic replacement is used")
    provenance = dataset["provenance"]
    # A supplied feed clock fixes which bars were closed. Preserve that clock
    # separately from the actual time of the HTTP response.
    provenance["analysis_as_of"] = as_of.isoformat().replace("+00:00", "Z")
    provenance["actual_request_started_at"] = requested_at
    provenance["actual_response_received_at"] = received_at
    provenance["retrieved_at"] = received_at
    provenance.setdefault("warnings", []).append("Execution costs and contract assumptions were predeclared; they are not verified broker tariffs.")
    slug = re.sub(r"[^A-Z0-9]+", "_", symbol).strip("_")
    json_path, csv_path = directory / f"{slug}-{INTERVAL}.json", directory / f"{slug}-{INTERVAL}.csv"
    immutable_write(json_path, canonical(dataset) + "\n")
    immutable_write(csv_path, market.to_csv(bars))
    last_closed = market.utc_datetime(provenance["last_closed_at"])
    freshness = (as_of - last_closed).total_seconds() / 3600
    return {"symbol": symbol, "json_path": str(json_path.relative_to(ROOT)), "csv_path": str(csv_path.relative_to(ROOT)),
            "json_sha256": file_digest(json_path), "csv_sha256": file_digest(csv_path),
            "bars_sha256": market.data_fingerprint(bars), "bars": len(bars), "start": bars[0]["time"],
            "end": bars[-1]["time"], "last_closed_at": provenance["last_closed_at"],
            "hours_since_last_closed": round(freshness, 4),
            "freshness": "within72hours" if 0 <= freshness <= 72 else "older_than72hours_or_inconsistent",
            "source_url": provenance["source_url"], "provider": provenance["provider"],
            "provider_symbol": provenance["provider_symbol"], "quote_currency": provenance.get("quote_currency"),
            "snapshot_status": "Canonicalized public feed snapshot, checksum pinned; not audited broker tick history"}


def run(output=DEFAULT_OUTPUT, snapshots=DEFAULT_SNAPSHOTS):
    if output.exists():
        existing = json.loads(output.read_text(encoding="utf-8"))
        if existing.get("phase") == "final_review":
            print("Frozen current experiment already exists; returning it without a new download or selection", flush=True)
            return existing
        raise ValueError("An incomplete predeclared experiment already exists. Preserve it; do not silently replace its protocol.")
    began = time.monotonic()
    protocol = freeze_protocol()
    source_hashes = engine_sources()
    report = {"schema": "propdesk-current-research-v1", "phase": "protocol_frozen", "protocol": protocol,
              "protocol_sha256": digest(protocol), "engine_sources": source_hashes,
              "engine_sha256": digest(source_hashes), "snapshots": [], "fetch_errors": [], "reports": [],
              "planning_only": True, "live_orders": False, "live_orders_enabled": False,
              "warnings": ["Yahoo is an unofficial public history endpoint, not executable broker quotes.",
                           "Index and continuous-futures proxies are not interchangeable with a firm's tradable contracts.",
                           "The public source does not grant a verified redistribution license; snapshots are for this user's local research.",
                           "Generic static rules are illustrative; no actual firm is recommended or guaranteed to pay.",
                           "No holdout winner substitution or synthetic fallback is permitted."]}
    write_report(output, report)
    print(f"PROTOCOL FROZEN before prices: {report['protocol_sha256']} / {','.join(SYMBOLS)} / 1h2y", flush=True)
    as_of = market.utc_datetime(protocol["frozen_at"])
    directory = snapshots / protocol["frozen_at"].replace(":", "-")
    directory.mkdir(parents=True, exist_ok=False)
    datasets = {}

    def load(symbol):
        requested_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        dataset = feeds.get_history(symbol, interval=INTERVAL, range_=RANGE, now=as_of)
        received_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        dataset["execution_model"] = protocol["execution_models"][symbol]
        manifest = snapshot(symbol, dataset, directory, as_of, requested_at, received_at)
        return dataset, manifest

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(load, symbol): symbol for symbol in SYMBOLS}
        for future in as_completed(futures):
            symbol = futures[future]
            try:
                dataset, manifest = future.result()
                datasets[symbol] = dataset
                report["snapshots"].append(manifest)
                print(f"Source validated: {symbol}; {manifest['bars']} closed bars; {manifest['start']} → {manifest['end']}", flush=True)
            except Exception as exc:
                report["fetch_errors"].append({"symbol": symbol, "reason": str(exc) if isinstance(exc, (ValueError, OSError)) else type(exc).__name__})
                print(f"Source unavailable: {symbol}; recorded without replacement", flush=True)
            report["phase"] = "loading"
            write_report(output, report)
    report["snapshots"].sort(key=lambda item: item["symbol"])
    report["fetch_errors"].sort(key=lambda item: item["symbol"])
    if not datasets:
        report.update(phase="source_unavailable", decision="No genuine datasets were retrieved. No research or profit claim is produced.")
        write_report(output, report)
        return report

    def locked(event):
        report["phase"] = "training_locked"
        report["training_lock"] = event["training_lock"]
        report["training_lock_sha256"] = event["training_lock_sha256"]
        report["training_locked_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        write_report(output, report)
        print(f"GLOBAL TRAINING LOCK SAVED before any holdout: {event['training_lock']['primary_symbol']} / {event['training_lock_sha256']}", flush=True)

    def progress(event):
        if event["phase"] in ("training", "holdout"):
            print(f"{event['phase']}: {event.get('symbol')} / {event.get('completed')}/{event.get('total')}", flush=True)

    result = scanner.scan(datasets, settings=protocol["settings"], profiles=[protocol["settings"]["prop_profile"]],
                          on_lock=locked, progress=progress)
    if engine_sources() != source_hashes:
        raise ValueError("Research source code changed during the experiment; preserve the original snapshot/lock and review the drift")
    report.update(phase="final_review", result=result, primary_symbol=result["primary_symbol"],
                  selected_symbol=result["selected_symbol"], selected_profile_id=result["selected_profile_id"],
                  reports=[outcome["report"] for outcome in result["markets"]], elapsed_seconds=round(time.monotonic() - began, 3),
                  completed_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
    report["decision"] = "Conditional paper research candidate; current broker prices and verified firm rules still required" if result["selected_symbol"] else "The predeclared global training primary did not qualify. No diagnostic holdout is substituted."
    write_report(output, report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--snapshots", type=Path, default=DEFAULT_SNAPSHOTS)
    args = parser.parse_args()
    try:
        report = run(args.output, args.snapshots)
    except (ValueError, OSError) as exc:
        print(f"Current experiment stopped: {exc}", file=sys.stderr)
        return 1
    print(report.get("decision", report["phase"]), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
