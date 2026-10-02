#!/usr/bin/env python3
"""Audit frozen prop-market snapshots and acquire distinct read-only receipts.

All original snapshots remain untouched. Yahoo is an unofficial research proxy;
NYSE cash-session checks do not certify CME execution or a prop firm's quotes.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from propdesk.feeds import get_history
from propdesk.market import data_fingerprint, parse_csv, to_csv, utc_datetime, validate_bars

SYMBOLS = ("MES=F", "MNQ=F", "NAS100", "EURUSD", "XAUUSD", "AAPL", "MSFT", "BTCUSD")
CALENDAR_URL = "https://raw.githubusercontent.com/QuantConnect/Lean/41c6e603e5671ca7b5d3de0cbe13b3c4b109bba4/Data/market-hours/market-hours-database.json"
CALENDAR_SHA = "bffec9c2e5efe30c0f21a1af9d1803b2a8e9a1356ac4f7408130693b7261e440"
NY = ZoneInfo("America/New_York")
SOURCES = {
    "cme_mes_contract": "https://www.cmegroup.com/markets/equities/sp/micro-e-mini-sandp-500.contractSpecs.html",
    "cme_mnq_contract": "https://www.cmegroup.com/markets/equities/nasdaq/micro-e-mini-nasdaq-100.contractSpecs.html",
    "ftmo_public_symbols": "https://ftmo.com/wp-json/ftmo/symbols",
    "dukascopy_historical_page": "https://www.dukascopy.com/swiss/english/marketwatch/historical/",
    "dukascopy_terms": "https://www.dukascopy.com/swiss/english/legal/terms-of-use/",
    "dukascopy_hourly_probe": "https://datafeed.dukascopy.com/datafeed/EURUSD/2024/00/02/BID_candles_hour_1.bi5",
    "nasdaq_data_page": "https://data.nasdaq.com/",
}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def immutable_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        stream.write(canonical(value) + "\n")


def fetch(url, path):
    started = datetime.now(timezone.utc).isoformat()
    with urlopen(Request(url, headers={"User-Agent": "Mozilla/5.0 (PropDeskPersonalResearch/0.5)"}), timeout=20) as response:
        raw = response.read(16 * 1024 * 1024 + 1)
        final_url, status = response.geturl(), response.status
    if len(raw) > 16 * 1024 * 1024:
        raise ValueError("Public source exceeds16MiB bound")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(raw)
    return raw, {"source_url": url, "response_url": final_url, "status": status,
                 "request_started_at": started, "received_at": datetime.now(timezone.utc).isoformat(),
                 "raw_path": str(path.relative_to(ROOT)), "raw_sha256": digest(path), "bytes": len(raw)}


def calendar(raw):
    if hashlib.sha256(raw).hexdigest() != CALENDAR_SHA:
        raise ValueError("Pinned US cash-session calendar bytes changed")
    entry = json.loads(raw)["entries"]["Equity-usa-[*]"]
    def day(value):
        return datetime.strptime(value, "%m/%d/%Y").date().isoformat()
    return {"timezone": "America/New_York", "holidays": sorted(day(value) for value in entry["holidays"]),
            "early_closes": {day(key): value for key, value in entry["earlyCloses"].items()},
            "source_url": CALENDAR_URL, "source_sha256": CALENDAR_SHA,
            "scope": "NYSE equity cash-session reference, not CME Globex or broker calendar"}


def session_audit(bars, symbol, reference, *, as_of):
    """Audit every completed cash date; report, never delete missing exposure."""
    by_date = defaultdict(dict)
    for bar in bars:
        stamp = utc_datetime(bar["time"]).astimezone(NY)
        if stamp.weekday() < 5 and 9 <= stamp.hour < 16:
            by_date[stamp.date().isoformat()][stamp.strftime("%H:%M")] = bar
    first = utc_datetime(bars[0]["time"]).astimezone(NY).date()
    last = min(utc_datetime(bars[-1]["time"]).astimezone(NY).date(), as_of.astimezone(NY).date())
    holidays = set(reference["holidays"])
    errors, expected, early_dates, regular_dates = [], [], [], []
    observed_grids = Counter()
    date = first
    while date <= last:
        key = date.isoformat()
        if date.weekday() < 5 and key not in holidays:
            close = reference["early_closes"].get(key, "16:00:00")
            closed_at = datetime.combine(date, datetime.strptime(close, "%H:%M:%S").time(), tzinfo=NY)
            if closed_at <= as_of:
                expected.append(key)
                observed = by_date.get(key, {})
                is_early = key in reference["early_closes"]
                (early_dates if is_early else regular_dates).append(key)
                if symbol in ("MES=F", "MNQ=F"):
                    required = ("09:30", "10:30", "11:30", "12:30") if is_early else ("10:00", "11:00", "12:00", "13:00", "14:00", "15:00")
                else:
                    required = ("09:30", "10:30", "11:30") if is_early else ("09:30", "10:30", "11:30", "12:30", "13:30", "14:30", "15:30")
                missing = [slot for slot in required if slot not in observed]
                if missing:
                    errors.append({"date": key, "missing_slots": missing, "observed_slots": sorted(observed)})
                observed_grids[tuple(sorted(observed))] += 1
        date += timedelta(days=1)
    return {"reference": reference["scope"], "completed_expected_sessions": len(expected),
            "expected_session_dates": expected, "normal_sessions": len(regular_dates),
            "early_close_dates": early_dates, "coverage_errors": errors,
            "late_cash_window_complete": not errors,
            "observed_grids": [{"slots": list(grid), "days": count} for grid, count in observed_grids.most_common()],
            "cash_closed_dates_with_futures_bars": sorted(key for key in by_date if key in holidays),
            "normal_0930_orb_supported": symbol not in ("MES=F", "MNQ=F"),
            "futures_window": "Regular first wholly contained hourly bar10:00–11:00NY; do not rename09:00–10:00 as09:30ORB. Halfday source09:30/10:30/11:30/12:30,13:00closingmarker not a new full hour."}


def existing(reference):
    report = json.loads((ROOT / "docs" / "current-research.json").read_text())
    snapshots, datasets = [], {}
    for item in report["snapshots"]:
        json_path, csv_path = ROOT / item["json_path"], ROOT / item["csv_path"]
        if digest(json_path) != item["json_sha256"] or digest(csv_path) != item["csv_sha256"]:
            raise ValueError("Original frozen Yahoo snapshot hash changed")
        dataset = json.loads(json_path.read_text())
        bars = validate_bars(dataset["bars"])
        if data_fingerprint(bars) != item["bars_sha256"] or parse_csv(csv_path.read_text()) != bars:
            raise ValueError("Original canonical CSV and JSON no longer match")
        row = {**item, "frozen_hashes_verified": True,
               "price_unit": dataset["provenance"].get("quote_currency"),
               "bar_timestamp": dataset["provenance"]["bar_timestamp"],
               "execution_verified": False, "already_inspected": True,
               "data_redistribution_license_verified": False}
        if item["symbol"] in ("MES=F", "MNQ=F", "NAS100", "AAPL", "MSFT"):
            as_of = utc_datetime(dataset["provenance"]["analysis_as_of"])
            row["cash_session_audit"] = session_audit(bars, item["symbol"], reference, as_of=as_of)
        snapshots.append(row)
        datasets[item["symbol"]] = dataset
    return snapshots, datasets


def run(output, receipts, raw_dir, *, refresh=True):
    now = datetime.now(timezone.utc).replace(microsecond=0)
    identifier = now.strftime("%Y-%m-%dT%H-%M-%SZ")
    raw = Path(raw_dir) / identifier
    source_calendar, calendar_receipt = fetch(CALENDAR_URL, raw / "market-hours-database.json")
    reference = calendar(source_calendar)
    old, old_data = existing(reference)
    protocol = {"id": "prop-data-audit-v1", "created_at": now.isoformat(), "symbols": SYMBOLS,
                "new_snapshot_interval": "1h", "new_snapshot_range": "2y", "producer_sha256": digest(__file__),
                "preserve": "All existing study/snapshot bytes immutable; new observations are distinct.",
                "calendar_sha256": CALENDAR_SHA, "research_only": True, "live_orders": False}
    immutable_json(raw / "protocol.json", protocol)
    report = {"schema": 1, "phase": "data_audit", "protocol": protocol,
              "existing": old, "new_snapshots": [], "source_receipts": [calendar_receipt],
              "source_errors": [], "firm_specs": [], "longer_intraday_acquired": False,
              "calendar": reference, "live_orders": False, "prop_execution_verified": False}
    for name, url in SOURCES.items():
        try:
            content, receipt = fetch(url, raw / (name + ".raw"))
            receipt["name"] = name
            report["source_receipts"].append(receipt)
            if name == "ftmo_public_symbols":
                payload = json.loads(content)
                selected_codes = {"US100.cash", "US500.cash", "EUR/USD", "XAU/USD", "BTCUSD"}
                report["firm_specs"] = [item for item in payload["data"]["symbols"] if item["code"] in selected_codes]
                report["firm_spec_limitations"] = ["Public current symbol metadata, not a verified user's account contract or historical tariff.",
                    "Public response has no executable historical bid/ask/spread or lot-step guarantee.",
                    "Commission per-side versus roundtrip semantics are not established by these numeric fields.",
                    "Current swaps, leverage and tradingHours are not a historical policy schedule.",
                    "US100.cash CFD is not Yahoo^NDX, and XAU/USD CFD is not continuous GC=F."]
        except (ValueError, HTTPError, URLError, OSError) as exc:
            report["source_errors"].append({"name": name, "source_url": url,
                "error": str(exc), "checked_at": datetime.now(timezone.utc).isoformat(), "no_substitute": True})
    if refresh:
        def load(symbol):
            dataset = get_history(symbol, interval="1h", range_="2y", now=now)
            bars = validate_bars(dataset["bars"])
            slug = re.sub(r"[^A-Z0-9]+", "_", symbol).strip("_")
            json_path, csv_path = raw / f"{slug}-1h.json", raw / f"{slug}-1h.csv"
            immutable_json(json_path, dataset)
            with csv_path.open("x", encoding="utf-8", newline="") as stream:
                stream.write(to_csv(bars))
            prior = {bar["time"]: bar for bar in old_data[symbol]["bars"]}
            overlap = [bar for bar in bars if bar["time"] in prior]
            row = {"symbol": symbol, "json_path": str(json_path.relative_to(ROOT)), "csv_path": str(csv_path.relative_to(ROOT)),
                   "json_sha256": digest(json_path), "csv_sha256": digest(csv_path), "bars_sha256": data_fingerprint(bars),
                   "bars": len(bars), "start": bars[0]["time"], "end": bars[-1]["time"],
                   "source_url": dataset["provenance"]["source_url"], "provider_symbol": dataset["provenance"]["provider_symbol"],
                   "quote_currency": dataset["provenance"].get("quote_currency"), "bar_timestamp": "opening time UTC",
                   "overlap_with_inspected_bars": len(overlap), "changed_shared_bar_rows": sum(bar != prior[bar["time"]] for bar in overlap),
                   "independent_holdout": False, "execution_verified": False, "data_license_verified": False}
            if symbol in ("MES=F", "MNQ=F", "NAS100", "AAPL", "MSFT"):
                row["cash_session_audit"] = session_audit(bars, symbol, reference, as_of=now)
            return row
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = {pool.submit(load, symbol): symbol for symbol in SYMBOLS}
            for future in as_completed(futures):
                symbol = futures[future]
                try:
                    report["new_snapshots"].append(future.result())
                except (ValueError, OSError) as exc:
                    report["source_errors"].append({"symbol": symbol, "error": str(exc), "no_substitute": True})
    report["new_snapshots"].sort(key=lambda value: value["symbol"])
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    report["decision"] = "Frozen futures proxies support a checked late-hour NY cash-session research model; no guaranteed8%monthly edge or actual prop execution follows. Longer independent intraday data unavailable from probed sources in this runtime."
    immutable_json(Path(receipts) / identifier / "manifest.json", report)
    immutable_json(output, report)
    return report


def fetch_fx(receipts, raw_dir):
    """Distinct new FX/micro-gold acquisition; original audit stays untouched."""
    now = datetime.now(timezone.utc).replace(microsecond=0)
    identifier = "fx-" + now.strftime("%Y-%m-%dT%H-%M-%SZ")
    raw = Path(raw_dir) / identifier
    # Yahoo's canonical USD/JPY ticker is JPY=X. USDJPY=X redirects its symbol
    # identity to JPY=X and was rejected in the earlier preserved receipt.
    mapping = {"EURUSD": "EURUSD", "GBPUSD": "GBPUSD=X", "USDJPY": "JPY=X", "MGC=F": "MGC=F"}
    protocol = {"id": "prop-fx-acquisition-v1", "created_at": now.isoformat(), "provider_requests": mapping,
                "interval": "1h", "range": "2y", "producer_sha256": digest(__file__),
                "timestamp": "UTC bar opening; nominal hourly close, source session details not broker-certified",
                "risk": "Prices and PnL units must use actual quote currency; USDJPY profitJPY requires time-varying JPYUSD conversion.",
                "alias_evidence": "JPY=X actual metadata currencyJPY,longNameUSD/JPY,instrumentTypeCURRENCY; prior failed USDJPY=X receipt preserved. Identity correction before strategy outcomes, not a replacement market.",
                "missing_data": "Do not fill or replace missing bars/symbols; FX weekends and holidays are not a certified broker calendar.",
                "live_orders": False}
    immutable_json(raw / "protocol.json", protocol)
    sources, errors = [], []
    for symbol, provider in mapping.items():
        started = datetime.now(timezone.utc).isoformat()
        try:
            dataset = get_history(provider, interval="1h", range_="2y", now=now)
            bars = validate_bars(dataset["bars"])
            slug = re.sub(r"[^A-Z0-9]+", "_", symbol).strip("_")
            json_path, csv_path = raw / f"{slug}-1h.json", raw / f"{slug}-1h.csv"
            immutable_json(json_path, dataset)
            with csv_path.open("x", encoding="utf-8", newline="") as stream:
                stream.write(to_csv(bars))
            gaps = Counter()
            gap_examples = []
            for previous, current in zip(bars, bars[1:]):
                minutes = (utc_datetime(current["time"]) - utc_datetime(previous["time"])).total_seconds() / 60
                if minutes != 60:
                    gaps[str(minutes)] += 1
                    gap_examples.append({"previous": previous["time"], "current": current["time"], "gap_minutes": minutes})
            days = defaultdict(list)
            for bar in bars:
                stamp = utc_datetime(bar["time"])
                days[stamp.date().isoformat()].append(stamp.strftime("%H:%M"))
            currencies = {"EURUSD": ("EUR", "USD"), "GBPUSD": ("GBP", "USD"), "USDJPY": ("USD", "JPY")}
            base, quote = currencies.get(symbol, (None, dataset["provenance"].get("quote_currency")))
            received_quote = dataset["provenance"].get("quote_currency")
            sources.append({"symbol": symbol, "provider_symbol": dataset["provenance"]["provider_symbol"],
                "source_url": dataset["provenance"]["source_url"], "provider": dataset["provenance"]["provider"],
                "actual_request_started_at": started, "actual_response_received_at": datetime.now(timezone.utc).isoformat(),
                "json_path": str(json_path.relative_to(ROOT)), "csv_path": str(csv_path.relative_to(ROOT)),
                "json_sha256": digest(json_path), "csv_sha256": digest(csv_path), "data_fingerprint": data_fingerprint(bars),
                "bars": len(bars), "first_open_at": bars[0]["time"], "last_open_at": bars[-1]["time"],
                "base_currency": base, "expected_quote_currency": quote, "provider_quote_currency": received_quote,
                "quote_currency_agrees": received_quote == quote, "ohlc_unit": "quote currency per base unit/index point",
                "non_hourly_gaps_count": sum(gaps.values()), "gap_minutes_histogram": dict(gaps),
                "gap_examples": gap_examples[:40], "utc_daily_bar_counts": {date: len(values) for date, values in sorted(days.items())},
                "no_imputation": True, "broker_calendar_verified": False, "execution_verified": False,
                "source_identity": "Continuous micro-gold futures research proxy" if symbol == "MGC=F" else "Public Yahoo FX cross, not verified FTMO executable bid/ask",
                "vendor_warnings": dataset["provenance"]["warnings"]})
        except (ValueError, OSError) as exc:
            errors.append({"symbol": symbol, "provider_symbol": provider, "error": str(exc), "no_substitute": True})
    result = {"schema": 1, "phase": "source_audit", "protocol": protocol, "sources": sources,
              "errors": errors, "live_orders": False, "execution_verified": False,
              "limit": "Two-year rolling intraday window starts in October2024; no invented full2024 or independent forward-test claim."}
    immutable_json(Path(receipts) / identifier / "manifest.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "docs" / "prop-data-audit.json")
    parser.add_argument("--receipts", type=Path, default=ROOT / "data" / "prop-data")
    parser.add_argument("--raw-dir", type=Path, default=ROOT / ".local" / "prop-research")
    parser.add_argument("--no-refresh", action="store_true")
    parser.add_argument("--fx-only", action="store_true")
    args = parser.parse_args()
    if args.fx_only:
        result = fetch_fx(args.receipts, args.raw_dir)
        print("FX sources", len(result["sources"]), "errors", len(result["errors"]))
        for source in result["sources"]:
            print(source["symbol"], source["csv_path"], source["bars"], source["provider_quote_currency"])
        return
    result = run(args.output, args.receipts, args.raw_dir, refresh=not args.no_refresh)
    print("verified existing", len(result["existing"]), "new snapshots", len(result["new_snapshots"]),
          "source errors", len(result["source_errors"]), "prop execution", result["prop_execution_verified"])


if __name__ == "__main__":
    main()
