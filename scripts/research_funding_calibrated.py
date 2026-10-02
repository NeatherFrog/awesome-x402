#!/usr/bin/env python3
"""One deterministic TRAIN-calibrated risk budget for the same static alpha."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from propdesk import funding_lab, funding_calibrated as lab
from scripts import research_funding as original, research_funding_sized as sized_original, research_funding_static as static_original

DIRECTORY = ROOT / "data/funding-calibrated-research"
RAW = ROOT / ".local/funding-calibrated-research"
OUTPUT = ROOT / "docs/funding-calibrated-research.json"
MARKDOWN = ROOT / "docs/FUNDING_CALIBRATED_RESEARCH.md"
PROTOCOL_DOC = ROOT / "docs/FUNDING_CALIBRATED_PROTOCOL.md"
WINDOWS = original.WINDOWS
CASES = {"base": (1.0, 1.0), "cost_stress": (2.0, 1.0), "funding_stress": (1.0, .75)}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def immutable_write(path, value):
    text = canonical(value) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_text(encoding="utf-8") != text:
            raise ValueError("Immutable funding research artifact changed: " + str(path))
    else:
        with path.open("x", encoding="utf-8") as stream:
            stream.write(text)


def write_report(report):
    temporary = OUTPUT.with_suffix(".tmp")
    temporary.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(OUTPUT)
    lines = ["# Static funding carry with TRAIN-calibrated risk", "", f"Status: **{report['phase']}**.", "",
             "The SAME static-carry alpha receives ONE deterministic risk allocation from its known2024 training envelope. All three failed studies remain preserved: **16 sequential funding configurations** including this policy, alongside other research. General2025 markets and a different funding strategy were already inspected; STATIC2025 and funding2026 model performance were unopened at freeze. No global blind-final claim applies.", "",
             f"Protocol SHA256: `{report['protocol_sha256']}`.", "",
             f"Total initial account100,000USD: two50,000USD BTC/ETH buckets. Spot fraction is fixed at {lab.SPOT_FRACTION:.17g}: `min(.2, .2*(1.5/3.0186020214986176))`, chosen BEFORE static2025 performance. Each bucket initially has {50000*lab.SPOT_FRACTION:.8f}USD spot cash and {50000*(1-lab.SPOT_FRACTION):.8f}USD isolated derivative cash. The target1.5% TRAIN envelope is a calibration objective; all confirmation gates including2.5% daily risk remain unchanged.", "",
             "Equal base units long spot/short perpetual are held after the next known closed-hour decision until the fixed boundary or modeled liquidation. No persistence switches, defensive reductions, transfers, borrow, fabricated cash or collateral. Finite isolated collateral can still liquidate. The literal frozen static engine changes only the fixed allocation/budget constants, with no post-validation correction.", "",
             "All original cost, risk,99% block-confidence, concentration and half-period gates remain unchanged. Trade-price funding/liquidation proxies, executable tariffs/filters and venue default/outage risk are unverified. Personal non-production archive use only; passing is a historical provisional candidate, never stable future profit or live/prop qualification. No Telegram messages or actual orders.", ""]
    if report.get("reason"):
        lines += [report["reason"], ""]
    if report.get("training"):
        lines += ["| Variant |2024 net | Double costs |75% positive funding | Daily risk envelope | Liquidations |",
                  "| --- | ---: | ---: | ---: | ---: | ---: |"]
        for row in report["training"]:
            b = row["base"]
            lines.append(f"|{row['variant']['id']}|{b['return_pct']:+.4f}%|{row['cost_stress']['return_pct']:+.4f}%|{row['funding_stress']['return_pct']:+.4f}%|{b['max_daily_drawdown_pct']:.4f}%|{b['liquidations']}|")
        lines += [""]
    if report.get("training_selection"):
        lines += [f"The **one** locked alpha/risk construction is `{report['training_selection']['variant_id']}`. Selection was persisted before static2025 model outcomes; neither exposure nor candidate can be replaced.", ""]
    for phase in ("validation", "final"):
        if report.get(phase):
            row = report[phase]
            b, ci = row["base"], row["base"]["block_mean_ci99"]
            lines += [f"## {phase.title()}", "",
                      f"Total-account net **{b['return_pct']:+.6f}%**, annualized {b['annualized_return_pct']:+.6f}%; doubled costs {row['cost_stress']['return_pct']:+.6f}%;25% haircut to positive funding {row['funding_stress']['return_pct']:+.6f}%.", "",
                      f"Conservative maximum drawdown {b['max_drawdown_pct']:.6f}%, daily envelope {b['max_daily_drawdown_pct']:.6f}%, credited settlements {b['settlements']}, modeled liquidations {b['liquidations']}.", "",
                      f"99%7-day circular-block interval for mean total-account daily return: [{ci['lower']*100:+.8f}%, {ci['upper']*100:+.8f}%]. Conditional approximate inference cannot certify future profit.", "",
                      f"Funding income {b['funding_received']:.6f}USD, paired price PnL {b['paired_price_pnl']:.6f}USD, fees {b['fees']:.6f}USD, fills {b['fills']}. Accounting error {b['accounting_reconciliation_error']:.12f}USD.", "",
                      "| Frozen check | Passed |", "| --- | --- |"]
            for check, passed in row["checks"].items():
                lines.append(f"|{check}|{passed}|")
            lines += ["", "| Month | Total-account net return |", "| --- | ---: |"]
            for month, value in b["monthly"]["monthly_returns"].items():
                lines.append(f"|{month}|{value*100:+.6f}%|")
            lines += [""]
    lines += [f"Retrospective **provisional** candidate: {report.get('retrospective_provisional_candidate', False)}. Live/prop qualification remains false. Every failed trial is retained in the record; no failed trade alerts are sent.", "",
              "Full execution/accounting ledgers are retained locally with exact raw/compressed hashes. Compact public summaries retain daily total-account curves and monthly results; they do not redistribute the archival input data.", ""]
    MARKDOWN.write_text("\n".join(lines), encoding="utf-8")


def freeze():
    if OUTPUT.exists():
        report = json.loads(OUTPUT.read_text())
        verify(report)
        return report
    source = json.loads((ROOT / "docs/funding-research.json").read_text())
    second = json.loads((ROOT / "docs/funding-sized-research.json").read_text())
    third_path = ROOT / "docs/funding-static-research.json"
    third = json.loads(third_path.read_text())
    original.verify(source)
    sized_original.verify(second)
    static_original.verify(third)
    if (third["phase"] != "completed_training_failed_later_periods_unopened"
            or "validation" in third or "final" in third):
        raise ValueError("Static lineage no longer matches unopened static2025/funding2026")
    envelope = third["training"][0]["base"]["max_daily_drawdown_pct"]
    if (file_hash(third_path) != lab.SOURCE_TRAIN_REPORT_SHA256
            or envelope != lab.TRAIN_MAX_DAILY_ENVELOPE_PCT
            or lab.SPOT_FRACTION != min(.2, .2 * (1.5 / envelope))):
        raise ValueError("Risk policy is not the exact single TRAIN-derived allocation")
    paths = ["propdesk/funding_lab.py", "scripts/research_funding.py", "propdesk/research_stats.py",
             "propdesk/funding_sized.py", "scripts/research_funding_sized.py",
             "propdesk/funding_static.py", "scripts/research_funding_static.py",
             "propdesk/funding_calibrated.py", "scripts/research_funding_calibrated.py"]
    protocol = {"version": "funding-static-train-risk-v1", "frozen_at": now(),
                "lineage_protocol_sha256": source["protocol_sha256"],
                "lineage_report_sha256": file_hash(ROOT / "docs/funding-research.json"),
                "lineage_sized_protocol_sha256": second["protocol_sha256"],
                "lineage_sized_report_sha256": file_hash(ROOT / "docs/funding-sized-research.json"),
                "lineage_static_protocol_sha256": third["protocol_sha256"],
                "lineage_static_report_sha256": file_hash(third_path),
                "producers": {path: file_hash(ROOT / path) for path in paths},
                "windows": WINDOWS, "variants": lab.variants(), "cases": CASES,
                "trial_accounting": "Seven original funding variants plus seven half-active variants plus one static allocation plus this ONE TRAIN-calibrated risk construction equals16 sequential funding configurations. The underlying static alpha is unchanged; all earlier research remains selection history.",
                "calibration": "V3 static TRAIN2024 had positive base/stressed cashflow but conservative daily envelope3.0186020214986176%, above unchanged2.5% gate. Risk manager uses only that2024 input to allocate spotfraction=min(.2,.2*(1.5/TRAINenvelope)); remaining physical cash is isolated derivative collateral. Allocation frozen before FIRST static2025 evaluation;2026 funding also unopened. Prior2025 other-strategy outcome is known, so no global blind claim. Never retry or change allocation after validation/final.",
                "risk_calibration": {"input_report_sha256": file_hash(third_path),
                                     "input_metric": "training[0].base.max_daily_drawdown_pct",
                                     "input_value_pct": envelope, "target_pct": 1.5,
                                     "formula": "min(.2, .2*(1.5/input_value_pct))",
                                     "fixed_spot_fraction": lab.SPOT_FRACTION,
                                     "fixed_derivative_fraction": 1-lab.SPOT_FRACTION,
                                     "target_is_not_a_relaxed_gate": True},
                "capital": {"total_account": 100000, "btc_bucket": 50000, "eth_bucket": 50000,
                            "spot_fraction_per_bucket": lab.SPOT_FRACTION, "derivative_fraction_per_bucket": 1-lab.SPOT_FRACTION,
                            "spot_cash_per_asset": 50000*lab.SPOT_FRACTION,
                            "isolated_derivative_cash_per_asset": 50000*(1-lab.SPOT_FRACTION),
                            "idle_external_cash": 0, "cash_interest": 0,
                            "cross_wallet_transfers": False, "spot_profit_can_rescue_margin": False},
                "arithmetic": "At each calendar close and conservative worst mark, total equity is the sum of two physical50k asset buckets. Spotcash+derivativecash+spot market value+short unrealized PnL, with fees and actual settled funding. No extra idle capital or synthetic collateral. Compute daily/account risk/inference from successive total dollar equity.",
                "original_selection_rules_reference": source["protocol"]["selection"],
                "validation_final_gates": source["protocol"]["validation_final_gates"],
                "execution_signals_funding_margin": "Literal copy of frozen funding_static.simulate: only fixed SPOT_FRACTION replaces.2, remaining collateral1-SPOT_FRACTION replaces.8, and entrybudgetusesSPOT_FRACTION. Constant equalbase units from next known hour; no rate exits or defensive reductions. Negative funding fully charged; both-leg fees, isolated wallets, conservative liquidation before funding,1minute settlement entitlement, previous trade-close funding mark proxy and hypothetical boundary close unchanged.",
                "selection_procedure": "EXACTLY ONE alpha/risk construction. Require original TRAIN basic gates, persist immutable one-candidate/derivedallocation before FIRST static2025 evaluation. If2025 fails any original confirmation gate STOP without2026. Ifpasses, immutable confirm hash BEFORE ONE2026 final. No candidate/exposure/gate changes after outcomes; no further risk-calibration retries.",
                "inference": source["protocol"]["inference"], "friction": source["protocol"]["friction"],
                "data": source["protocol"]["data"], "permissions": source["protocol"]["permissions"],
                "limitations": "TRAIN-based risk allocation is adaptive after16 sequential funding configurations and inspected2025 other-strategy failure. Static2025 and funding2026 outcome vectors were not computed at freeze;2026 market periods were inspected elsewhere. Proxy marks, executable tariffs/filters, finite margin and venue default/outages unverified. Passing requires fresh prospective evidence and does not certify stable profit/live/prop suitability."}
    immutable_write(DIRECTORY / "protocol.json", protocol)
    report = {"phase": "frozen_before_static_outcomes", "protocol": protocol,
              "protocol_sha256": digest(protocol), "retrospective_provisional_candidate": False,
              "live_qualified": False, "prop_qualified": False}
    PROTOCOL_DOC.write_text("# Frozen TRAIN-calibrated static carry protocol\n\nSame static alpha, ONE risk allocation from known2024 only. Old studies and all gates preserved; static2025 and funding2026 outcomes remain unopened.\n\n```json\n" + json.dumps(protocol, indent=2) + "\n```\n", encoding="utf-8")
    write_report(report)
    return report


def verify(report):
    p = report["protocol"]
    if digest(p) != report["protocol_sha256"] or p["variants"] != lab.variants():
        raise ValueError("Static protocol/grid changed")
    for path, expected in p["producers"].items():
        if file_hash(ROOT / path) != expected:
            raise ValueError("Producer changed after sizing freeze: " + path)
    if file_hash(ROOT / "docs/funding-research.json") != p["lineage_report_sha256"]:
        raise ValueError("Original funding report changed")
    if file_hash(ROOT / "docs/funding-sized-research.json") != p["lineage_sized_report_sha256"]:
        raise ValueError("Half-active funding report changed")
    if file_hash(ROOT / "docs/funding-static-research.json") != p["lineage_static_report_sha256"]:
        raise ValueError("Source static training report changed")
    if json.loads((DIRECTORY / "protocol.json").read_text()) != p:
        raise ValueError("Immutable static protocol differs from report")


def load_inputs(report):
    original_report = json.loads((ROOT / "docs/funding-research.json").read_text())
    locks = original_report["input_lock"]
    for entry in locks.values():
        path = ROOT / entry["path"]
        if not path.exists() or file_hash(path) != entry["sha256"]:
            raise ValueError("Original input receipt missing or changed: " + entry["path"])
    if report.get("input_lock") and report["input_lock"] != locks:
        raise ValueError("Static inputs changed")
    manifest = json.loads((ROOT / locks["funding_manifest"]["path"]).read_text())
    report["input_lock"] = locks
    report["input_lock_sha256"] = digest(locks)
    immutable_write(DIRECTORY / "input-lock.json", locks)
    write_report(report)
    inputs = {key: json.loads((ROOT / entry["path"]).read_text()) for key, entry in locks.items() if not key.endswith("manifest")}
    for symbol in ("BTCUSDT", "ETHUSDT"):
        entry = next(row for row in manifest["datasets"] if Path(row["json"]).name == symbol + "-funding.json")
        inputs[symbol + "_allow_unknown_intervals"] = bool(entry.get("exhaustive_pagination_verified"))
    return inputs


def compact(result, phase, variant_id, case):
    raw = canonical(result).encode()
    path = RAW / f"{phase}-{variant_id}-{case}.json.gz"
    compressed = gzip.compress(raw, mtime=0)
    RAW.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if gzip.decompress(path.read_bytes()) != raw:
            raise ValueError("Immutable local execution ledger changed")
    else:
        with path.open("xb") as stream:
            stream.write(compressed)
    keep = {key: value for key, value in result.items() if key != "assets"}
    keep["assets"] = [{key: value for key, value in asset.items() if key not in ("daily_rows", "records", "daily_equity", "daily_returns", "dates")}
                      for asset in result["assets"]]
    keep["raw_ledger"] = {"path": str(path.relative_to(ROOT)), "sha256": file_hash(path),
                          "raw_sha256": hashlib.sha256(raw).hexdigest(), "bytes": path.stat().st_size,
                          "accounting_legs": len(result["assets"])}
    return keep


def experiment(inputs, variant, phase):
    start, end = WINDOWS[phase]
    row = {"variant": variant}
    for case, (friction, funding_multiplier) in CASES.items():
        result = lab.simulate_portfolio(inputs, variant, start, end, friction=friction,
                                        positive_funding_multiplier=funding_multiplier)
        row[case] = compact(result, phase, variant["id"], case)
    return row


def verify_ledgers(report):
    trials = report.get("training", []) + [report[phase] for phase in ("validation", "final") if phase in report]
    for trial in trials:
        for case in CASES:
            receipt = trial[case]["raw_ledger"]
            path = ROOT / receipt["path"]
            if not path.exists() or file_hash(path) != receipt["sha256"]:
                raise ValueError("Recorded local ledger missing or changed: " + receipt["path"])


def run(report):
    verify(report)
    verify_ledgers(report)
    inputs = load_inputs(report)
    registered = report["protocol"]["variants"]
    report.setdefault("training", [])
    evaluated = [row["variant"] for row in report["training"]]
    if len(evaluated) > len(registered) or evaluated != registered[:len(evaluated)]:
        raise ValueError("Training resume must be exact registered ordered prefix")
    for variant in registered[len(evaluated):]:
        row = experiment(inputs, variant, "training")
        row["checks"] = original.basic_checks(row)
        report["training"].append(row)
        write_report(report)
    survivors = [row for row in report["training"] if all(row["checks"].values())]
    if not survivors:
        report.update(phase="completed_training_failed_later_periods_unopened", reason="No static variant passed unchanged training gates.2025/2026 funding outcomes remain unopened.")
        write_report(report)
        return report
    chosen = sorted(survivors, key=lambda row: (-row["base"]["return_pct"] / max(.25, row["base"]["max_drawdown_pct"]), row["variant"]["id"]))[0]
    selection = {"variant_id": chosen["variant"]["id"], "protocol_sha256": report["protocol_sha256"],
                 "training_results_sha256": digest(report["training"]), "input_lock_sha256": report["input_lock_sha256"]}
    if report.get("training_selection") and report["training_selection"] != selection:
        raise ValueError("Locked static training selection changed")
    immutable_write(DIRECTORY / "training-selection.json", selection)
    report["training_selection"] = selection
    report["training_selection_sha256"] = digest(selection)
    report.setdefault("training_selection_locked_at", now())
    report["phase"] = "one_static_candidate_locked_before_validation"
    write_report(report)
    if "validation" not in report:
        report["validation"] = experiment(inputs, chosen["variant"], "validation")
        report["validation"]["checks"] = original.confirm_checks(report["validation"])
        write_report(report)
    if not all(report["validation"]["checks"].values()):
        report.update(phase="completed_validation_failed_final_unopened", reason="The ONE locked static candidate failed unchanged2025 gates.2026 funding outcomes remain unopened; no winner replacement.")
        write_report(report)
        return report
    confirmation = {"protocol_sha256": report["protocol_sha256"],
                    "training_selection_sha256": report["training_selection_sha256"],
                    "validation_sha256": digest(report["validation"])}
    immutable_write(DIRECTORY / "validation-confirmation.json", confirmation)
    report["validation_confirmation"] = confirmation
    report["validation_confirmation_sha256"] = digest(confirmation)
    report.setdefault("validation_confirmation_locked_at", now())
    report["phase"] = "static_validation_confirmed_before_final"
    write_report(report)
    if "final" not in report:
        report["final"] = experiment(inputs, chosen["variant"], "final")
        report["final"]["checks"] = original.confirm_checks(report["final"])
    report["retrospective_provisional_candidate"] = all(report["final"]["checks"].values())
    report["phase"] = "completed_provisional_candidate" if report["retrospective_provisional_candidate"] else "completed_final_failed"
    report["reason"] = "One fixed candidate; original risk/cost/causality gates preserved. Historical proxies and adaptive sizing prevent a stable-profit/live/prop certification. Forward evidence required."
    write_report(report)
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--freeze", action="store_true")
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()
    if not (args.freeze or args.run):
        parser.error("Use--freeze before--run")
    report = freeze()
    if args.run:
        report = run(report)
    print(json.dumps({"phase": report["phase"], "protocol_sha256": report["protocol_sha256"],
                      "selected": report.get("training_selection", {}).get("variant_id"),
                      "retrospective_provisional_candidate": report.get("retrospective_provisional_candidate", False)}))


if __name__ == "__main__":
    main()
