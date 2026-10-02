#!/usr/bin/env python3
"""Freeze and evaluate one train-selected gold reference hypothesis; no orders."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from propdesk import metal_sessions as engine
from propdesk.market import data_fingerprint, parse_csv
from propdesk.target_evaluation import evaluate_period

OUTPUT = ROOT / "docs/metal-session-research.json"
LOCKS = ROOT / "data/metal-session-research"
WINDOWS = {
    "training": ("2024-10-03", "2025-01-01"),
    "validation": ("2025-01-01", "2026-01-01"),
    "final": ("2026-01-01", "2026-10-01"),
}
PRODUCERS = (
    "propdesk/metal_sessions.py", "scripts/research_metal_sessions.py",
    "propdesk/target_evaluation.py", "propdesk/research_stats.py", "propdesk/market.py",
    "propdesk/tzdata/Europe/London", "propdesk/tzdata/America/New_York",
    "docs/EIGHT_PERCENT_PROTOCOL.json", "tests/test_metal_sessions.py",
)
FIXED_PRODUCERS = {
    "docs/EIGHT_PERCENT_PROTOCOL.json": "5495a0683efeb6da230cf454b71c8e8ae952dc03534d23f3cedbcd9f56e9e839",
    "propdesk/tzdata/Europe/London": "c85495070dca42687df6a1c3ee780a27cbcb82f1844750ea6f642833a44d29b4",
    "propdesk/tzdata/America/New_York": "e9ed07d7bee0c76a9d442d091ef1f01668fee7c4f26014c0a868b19fe6c18a95",
}
SPEC_PATH = ".local/prop-research/2026-10-02T10-37-13Z/ftmo_public_symbols.raw"
SPEC_SHA = "166e40fe629ff0e0d9e32713e3e0cfa09fafe2ae15174763e140dcc6f4d95aea"


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def immutable(name, value):
    path = LOCKS / name
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = canonical(value) + "\n"
    if path.exists():
        if path.read_text() != raw:
            raise ValueError("Immutable metal lock mismatch: " + str(path))
    else:
        with path.open("x") as stream:
            stream.write(raw)


def save(value):
    OUTPUT.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def lock(name):
    path = LOCKS / name
    if not path.exists():
        raise ValueError("Missing claimed immutable metal lock: " + name)
    return json.loads(path.read_text())


def training_identity(rows):
    return [{"id": row["variant"]["id"], "variant_sha256": digest(row["variant"]),
             "result_sha256": digest(row)} for row in rows]


def ledger_bytes(value):
    output = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=output, mtime=0) as stream:
        stream.write(canonical(value).encode())
    return output.getvalue()


def write_ledger(path, value):
    raw = ledger_bytes(value)
    if path.exists():
        if path.read_bytes() != raw:
            raise ValueError("Immutable metal ledger mismatch: " + str(path))
    else:
        with path.open("xb") as stream:
            stream.write(raw)


def verify(value):
    if digest(value["protocol"]) != value["protocol_sha256"]:
        raise ValueError("Metal protocol changed")
    protocol = value["protocol"]
    if lock("protocol.json") != protocol or lock("input-lock.json") != protocol["inputs"]:
        raise ValueError("Metal report differs from immutable protocol/input locks")
    if (protocol["variants"] != engine.variants() or len(protocol["variants"]) != 96 or
            protocol["windows"] != {key: list(window) for key, window in WINDOWS.items()} or
            value["variant_count"] != 96 or set(protocol["producers"]) != set(PRODUCERS)):
        raise ValueError("Metal frozen grid, windows or producer catalog changed")
    if any(protocol["producers"].get(path) != expected
           for path, expected in FIXED_PRODUCERS.items()):
        raise ValueError("Metal common protocol or direct clock pin identity changed")
    for path, expected in value["protocol"]["producers"].items():
        if sha(ROOT / path) != expected:
            raise ValueError("Metal producer changed after freeze: " + path)
    for name, receipt in value["protocol"]["inputs"].items():
        if sha(ROOT / receipt["file"]) != receipt["sha256"]:
            raise ValueError("Metal input changed: " + name)
    if "training" in value:
        if [row["variant"] for row in value["training"]] != protocol["variants"]:
            raise ValueError("Metal TRAIN rows do not match all96 frozen identities")
    for name in ("selection", "confirmation"):
        if name in value and lock(name + ".json") != value[name]:
            raise ValueError("Metal claimed " + name + " lock differs")
    if "final" in value and "confirmation" not in value:
        raise ValueError("Metal FINAL exists without claimed confirmation")
    for role in ("training", "validation", "final"):
        rows = value.get(role, [])
        rows = rows if isinstance(rows, list) else [rows]
        for row in rows:
            for mode in ("base", "stress"):
                receipt = row[mode + "_ledger"]
                path = ROOT / receipt["path"]
                if (sha(path) != receipt["compressed_sha256"] or
                        hashlib.sha256(gzip.decompress(path.read_bytes())).hexdigest() != receipt["raw_sha256"]):
                    raise ValueError("Metal frozen ledger changed: " + str(path))


def verify_final_authority(report):
    verify(report)
    selection, confirmation = lock("selection.json"), lock("confirmation.json")
    if (selection != report["selection"] or selection["protocol_sha256"] != report["protocol_sha256"] or
            selection["training_sha256"] != digest(report["training"]) or
            selection["training_identities"] != training_identity(report["training"]) or
            report["selected"] != selection["variant"] or
            report["validation"]["variant"] != selection["variant"] or
            not report["validation"]["passed"] or confirmation != report["confirmation"] or
            confirmation["protocol_sha256"] != report["protocol_sha256"] or
            confirmation["selection_sha256"] != digest(selection) or
            confirmation["validation_sha256"] != digest(report["validation"])):
        raise ValueError("Metal FINAL authorization does not bind the sole primary and passing validation")


def freeze(data_dir):
    if OUTPUT.exists():
        report = json.loads(OUTPUT.read_text())
        verify(report)
        return report
    if any(sha(ROOT / path) != expected for path, expected in FIXED_PRODUCERS.items()):
        raise ValueError("Metal prefreeze common protocol or direct clock pins changed")
    dataset_path = data_dir / "MGC_F-1h.json"
    csv_path = data_dir / "MGC_F-1h.csv"
    manifest_path = ROOT / "data/prop-data" / data_dir.name / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    if manifest["protocol"]["id"] != "prop-fx-acquisition-v1" or manifest["errors"]:
        raise ValueError("Unverified gold acquisition identity")
    source = next(row for row in manifest["sources"] if row["provider_symbol"] == "MGC=F")
    dataset = json.loads(dataset_path.read_text())
    provenance = dataset["provenance"]
    if (source["json_path"] != str(dataset_path.relative_to(ROOT)) or
            source["json_sha256"] != sha(dataset_path) or
            source["csv_sha256"] != sha(csv_path) or
            source["expected_quote_currency"] != "USD" or
            source["provider_quote_currency"] != "USD" or
            provenance["provider_symbol"] != "MGC=F" or
            provenance["instrument_type"] != "FUTURE" or
            provenance["quote_currency"] != "USD" or provenance["interval"] != "1h" or
            provenance["bar_timestamp"] != "opening time UTC"):
        raise ValueError("Wrong gold provider, currency, interval or file identity")
    bars = dataset["bars"]
    engine.validate(bars)  # Source-quality audit only; no strategy P&L.
    if (source["bars"] != len(bars) or source["first_open_at"] != bars[0]["time"] or
            source["last_open_at"] != bars[-1]["time"] or
            data_fingerprint(bars) != source["data_fingerprint"] or parse_csv(csv_path.read_text()) != bars):
        raise ValueError("Gold canonical prices/dates do not match acquisition receipt")
    spec_path = ROOT / SPEC_PATH
    if sha(spec_path) != SPEC_SHA:
        raise ValueError("Immutable FTMO public symbol body changed")
    symbol = next(row for row in json.loads(spec_path.read_text())["data"]["symbols"]
                  if row["code"] == "XAU/USD")
    expected = {"contractSize": 100, "profitCurrency": "USD", "commission": .0014,
                "commissionType": "percent", "leverageSwing": 15, "maxTradeVolume": 100,
                "digits": 2, "assetClass": "Metals CFD"}
    if any(symbol[key] != value for key, value in expected.items()):
        raise ValueError("Gold model no longer matches audited current CFD metadata")
    inputs = {
        "prices": {"file": str(dataset_path.relative_to(ROOT)), "sha256": sha(dataset_path)},
        "csv": {"file": str(csv_path.relative_to(ROOT)), "sha256": sha(csv_path)},
        "acquisition": {"file": str(manifest_path.relative_to(ROOT)), "sha256": sha(manifest_path)},
        "current_cfd_specs": {"file": SPEC_PATH, "sha256": SPEC_SHA},
    }
    quality = {
        session: {role: engine.source_coverage(bars, {"session": session},
                                              begin + "T00:00:00Z", finish + "T00:00:00Z")
                  for role, (begin, finish) in WINDOWS.items()}
        for session in ("london", "us")
    }
    protocol = {
        "id": "gold-asian-us-session-96-v1", "registered_at": now(),
        "windows": {key: list(window) for key, window in WINDOWS.items()}, "variants": engine.variants(),
        "producers": {path: sha(ROOT / path) for path in PRODUCERS}, "inputs": inputs,
        "acquisition_identity": {key: source[key] for key in (
            "provider_symbol", "provider_quote_currency", "source_identity", "first_open_at",
            "last_open_at", "bars", "data_fingerprint", "source_url")},
        "current_cfd_spec": {"source_url": "https://ftmo.com/wp-json/ftmo/symbols", **expected},
        "source_quality": quality,
        "units": "Research quantity is GOLD OUNCES,100oz per modeled XAU/USD lot; MGC futures contract count is never used. Provider price is a USD/ounce reference assumption, not a verified broker quote.",
        "cash_margin": "Initial TOTAL modeled USD equity100000; initial margin=ounces*filled_price/15 remains reserved within that equity, and entry commission must also fit. Floor to1oz=.01lot, maximum100lots; minimum/lotstep are unverified assumptions absent from official metadata.",
        "costs": "Published commission0.0014PERCENT becomes1.4e-5*fill_notional on EACH SIDE as conservative side/RT ambiguity assumption. Model spread0.40USD/oz total plus0.10USD/oz slippage eachside. Entry+exit commissions charge actual modeled fill notional. Doubled cost stress doubles all fee/spread/slip components and replays sizing/exits.",
        "causality": "London prior00..05completed bars; completed07/08/09signals next hourly open, flat15London. NY prior08/09/10completed bars; completed11/12/13signals next hourly open, flat16NY. Pinned TZif loaded directly. Signals keyed to planned timestamp independent of future row presence; one entry per chosen session date, max3/6hours shortened by known flat clock.",
        "signals": "Range context0.5..6 pre-signalATR14. Breakoutclose outside range, stop opposite range plus0.1ATR. Rejection raid>0.05ATR closing inside, no double raid, stop signal extreme plus0.1ATR. Drift only first signalhour, prior range close-open >0.5ATR, stop signalclose minus side*ATR. Optional prior24-completed-hour-close trend: priorlastclose minus prior24close average must agree with side. RR1/2 uses actual filled entry and fixed stop.",
        "event_order": "Known opening stop gap fills adverse raw open; known favorable opening limit fills target before later unknown OHLC excursions. Otherwise stop-first ifbothhit. Full candle liquidation marks conservatively bound risk, do not imply known chronology after exit. Time exits are scheduled nominal hour closes; intrabar exit intervals remain explicit.",
        "missing_data": "Raw :30 markers preserved; never hourly range/ATR/trend observations. No future date/window completeness entry filter. Active missing/nonaligned/overlapping intervals flag uncertainty and block qualification; current observed marker quote may close/mark exposure. No holiday or missing prices fabricated.",
        "selection": "Unchanged common TRAIN gates then ONE max TRAIN netreturn/max(adverseDD,.0025), deterministicID. Immutable selection before one2025validation; validationfailure stops with final2026unopened. Immutable confirmation before single2026run. No replacement or held-out sizing increase.",
        "limitations": "MGC=F is an unofficial continuous FUTURE researchprice proxy, not XAU/USD broker bid/ask, actual micro contract execution or verified roll schedule. Historical spread/commission/margin/calendar/news execution unavailable. FTMO Swing5daily/10static rules need exact Prague-balance stage replay; generic UTC5/10risk screen is not contract certification. Neverpropqualified or liveeligible on these data.",
        "history": "Additional adaptive metal hypotheses after earlier crypto/index/FX studies; broad2024–2026 markets already inspected. NativeMGC strategyPnL was not opened before proposal, source audit, synthetic tests and freeze. Full source metadata/calendar diagnostics are not globally unseen data.",
    }
    report = {"phase": "frozen_before_outcomes", "protocol": protocol,
              "protocol_sha256": digest(protocol), "variant_count": len(engine.variants()),
              "selected": None, "live_qualified": False, "prop_qualified": False,
              "telegram_enabled": False}
    immutable("protocol.json", protocol)
    immutable("input-lock.json", inputs)
    save(report)
    (ROOT / "docs/METAL_SESSION_PROTOCOL.md").write_text(
        "# Frozen gold-session reference protocol\n\n```json\n" +
        json.dumps(protocol, indent=2) + "\n```\n")
    return report


def load(report):
    verify(report)
    path = ROOT / report["protocol"]["inputs"]["prices"]["file"]
    return json.loads(path.read_text())["bars"]


def period(bars, variant, role):
    begin, finish = WINDOWS[role]
    base = engine.simulate(bars, variant, begin + "T00:00:00Z", finish + "T00:00:00Z")
    stress = engine.simulate(bars, variant, begin + "T00:00:00Z", finish + "T00:00:00Z", cost_multiplier=2)
    if base["insolvent"] or stress["insolvent"]:
        result = {"passed": False, "checks": {"account_remained_solvent": False},
                  "completed_episodes": base["completed_episodes"],
                  "base": {"total_return": base["final_equity"] / 100000 - 1, "geometric_monthly_return": None},
                  "double_cost_stress": {"total_return": stress["final_equity"] / 100000 - 1,
                                         "geometric_monthly_return": None},
                  "risk": {"max_account_drawdown": None},
                  "selection_score_net_return_over_drawdown": -1e30,
                  "status": "insolvent_model_not_eligible_for_geometric_inference"}
    else:
        result = evaluate_period(
            base["dates"], base["daily_returns"], stress["daily_returns"], base["completed_episodes"],
            initial_equity=100000, daily_worst_equity=base["daily_worst_equity"],
            daily_peak_equity=base["daily_peak_equity"], period_start=begin,
            period_end_exclusive=finish, role=role, risk_day_timezone="UTC", samples=5000)
    result["checks"]["no_missing_active_exposure"] = not (
        base["missing_exposure_exits"] or stress["missing_exposure_exits"])
    result["checks"]["source_spans_declared_period"] = base["source_coverage"]["source_spans_declared_window"]
    result["checks"]["cash_reconciliation"] = max(abs(base["reconciliation_error"]),
                                                 abs(stress["reconciliation_error"])) <= 1e-6
    result["passed"] = all(result["checks"].values())
    result["variant"], result["source_coverage"] = variant, base["source_coverage"]
    ledger = ROOT / ".local/metal-session-research"
    ledger.mkdir(parents=True, exist_ok=True)
    for mode, value in (("base", base), ("stress", stress)):
        raw = canonical(value).encode()
        path = ledger / (role + "-" + variant["id"] + "-" + mode + ".json.gz")
        write_ledger(path, value)
        result[mode + "_ledger"] = {"path": str(path.relative_to(ROOT)),
                                   "raw_sha256": hashlib.sha256(raw).hexdigest(),
                                   "compressed_sha256": sha(path)}
    result["daily_dates"], result["daily_returns"] = base["dates"], base["daily_returns"]
    result["reconciliation_error"] = base["reconciliation_error"]
    return result


def run(report):
    verify(report)
    bars = load(report)
    if "training" not in report:
        report["training"] = [period(bars, variant, "training") for variant in engine.variants()]
        save(report)
    if [row["variant"] for row in report["training"]] != engine.variants():
        raise ValueError("Metal selection must cover the exact complete TRAIN grid")
    survivors = [row for row in report["training"] if row["passed"]]
    chosen = sorted(survivors, key=lambda row: (
        -row["selection_score_net_return_over_drawdown"], row["variant"]["id"]))[0] if survivors else None
    existing_selection = (lock("selection.json") if (LOCKS / "selection.json").exists() else {})
    selection = {"variant": chosen["variant"] if chosen else None,
                 "protocol_sha256": report["protocol_sha256"],
                 "training_sha256": digest(report["training"]),
                 "training_identities": training_identity(report["training"]),
                 "locked_at": existing_selection.get("locked_at", now())}
    immutable("selection.json", selection)
    report["selection"], report["selected"] = selection, selection["variant"]
    save(report)
    if chosen is None:
        report["phase"] = "completed_training_failed"
        save(report)
        return report
    if "validation" not in report:
        report["validation"] = period(bars, chosen["variant"], "validation")
        save(report)
    if not report["validation"]["passed"]:
        report["phase"] = "completed_validation_failed_final_unopened"
        save(report)
        return report
    existing_confirmation = (lock("confirmation.json") if (LOCKS / "confirmation.json").exists() else {})
    confirmation = {"protocol_sha256": report["protocol_sha256"],
                    "selection_sha256": digest(selection),
                    "validation_sha256": digest(report["validation"]),
                    "locked_at": existing_confirmation.get("locked_at", now())}
    immutable("confirmation.json", confirmation)
    report["confirmation"] = confirmation
    save(report)
    verify_final_authority(report)
    if "final" not in report:
        report["final"] = period(bars, chosen["variant"], "final")
    report["phase"] = ("completed_historical_target_passed" if report["final"]["passed"]
                       else "completed_final_failed")
    report["historical_target_candidate"] = report["final"]["passed"]
    save(report)
    return report


def markdown(report):
    def percent(value):
        return "undefined" if value is None else f"{value * 100:+.4f}%"
    lines = ["# Gold-session reference research", "", f"Status: **{report['phase']}**;96 configurations.", "",
             "Quantities are modeled XAU/USD ounces, not MGC contracts. Continuous futures prices and assumed costs/lotstep do not certify actual FTMO trading or payouts.", "",
             "| TRAIN variant | Net period | Monthly equivalent | Double-cost monthly | Episodes | Adverse DD |",
             "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for row in sorted(report.get("training", []), key=lambda value: -value["base"]["total_return"])[:5]:
        lines.append(f"|{row['variant']['id']}|{percent(row['base']['total_return'])}|"
                     f"{percent(row['base']['geometric_monthly_return'])}|"
                     f"{percent(row['double_cost_stress']['geometric_monthly_return'])}|"
                     f"{row['completed_episodes']}|{percent(row['risk']['max_account_drawdown'])}|")
    lines.extend(["", "Immutable TRAIN primary: `" + str(report["selected"]) + "`. No alternative replaces it."])
    for role in ("validation", "final"):
        if role in report:
            row = report[role]
            lines.extend(["", f"{role}: net {percent(row['base']['total_return'])}; "
                          f"monthly equivalent {percent(row['base']['geometric_monthly_return'])}; "
                          f"passed {row['passed']}.", "", "```json",
                          json.dumps(row["checks"], indent=2), "```"])
    lines.extend(["", "A positive mean-return99%interval does not prove an8%future monthly expectation. "
                  "Actual executable broker data, exact prop-stage replay and future forward observations remain necessary. "
                  "No orders or Telegram alerts; prop/live qualification remains false."])
    (ROOT / "docs/METAL_SESSION_RESEARCH.md").write_text("\n".join(lines) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--freeze", action="store_true")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--data-dir", default=".local/prop-research/fx-2026-10-02T10-40-40Z")
    args = parser.parse_args()
    if not (args.freeze or args.run):
        parser.error("Freeze before evaluating outcomes")
    report = freeze((ROOT / args.data_dir).resolve())
    if args.run:
        report = run(report)
        markdown(report)
    print(report["phase"], report["protocol_sha256"])


if __name__ == "__main__":
    main()
