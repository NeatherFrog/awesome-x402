#!/usr/bin/env python3
"""Adaptive HALF-active-capital carry study; gates and execution unchanged."""
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
from propdesk import funding_lab, funding_sized as lab
from scripts import research_funding as original

DIRECTORY = ROOT / "data/funding-sized-research"
RAW = ROOT / ".local/funding-sized-research"
OUTPUT = ROOT / "docs/funding-sized-research.json"
MARKDOWN = ROOT / "docs/FUNDING_SIZED_RESEARCH.md"
PROTOCOL_DOC = ROOT / "docs/FUNDING_SIZED_PROTOCOL.md"
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
    lines = ["# Funding carry with half active capital", "", f"Status: **{report['phase']}**.", "",
             "Adaptive risk sizing follows the original seven-variant2024 carry study. The original study is preserved; this adds seven variants for **14 sequential funding trials**, alongside all previous research.2024 is calibration data;2025/2026 funding performance was unopened when this protocol froze. General market periods were already inspected, so no global blind-final claim applies.", "",
             f"Protocol SHA256: `{report['protocol_sha256']}`.", "",
             "Total initial account100,000USD: two25,000USD active BTC/ETH buckets plus50,000USD dormant cash. Each active bucket initially splits12,500USD spot cash and12,500USD isolated derivative collateral. Dormant cash earns zero and never rescues isolated collateral. All equity, daily returns, drawdowns and inference use the total account's actual dollar curve.", "",
             "The original model, costs, causal signals, conservative liquidation ordering and every selection/confirmation gate remain unchanged. Trade-price liquidation and funding-mark proxies, unknown executable tariffs and counterparty/outage risk make every outcome provisional. Personal non-production archive usage only; live/prop qualification is false. No Telegram messages or actual orders.", ""]
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
        lines += [f"The **one** training-locked candidate is `{report['training_selection']['variant_id']}`. Selection was persisted before validation outcomes. A failed candidate cannot be replaced.", ""]
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
    original.verify(source)
    if source["phase"] != "completed_no_training_candidate_final_unopened" or "validation" in source or "final" in source:
        raise ValueError("Original funding study lineage no longer matches unopened validation/final")
    paths = ["propdesk/funding_lab.py", "scripts/research_funding.py", "propdesk/research_stats.py",
             "propdesk/funding_sized.py", "scripts/research_funding_sized.py"]
    protocol = {"version": "funding-half-active-v1", "frozen_at": now(),
                "lineage_protocol_sha256": source["protocol_sha256"],
                "lineage_report_sha256": file_hash(ROOT / "docs/funding-research.json"),
                "producers": {path: file_hash(ROOT / path) for path in paths},
                "windows": WINDOWS, "variants": funding_lab.variants(), "cases": CASES,
                "trial_accounting": "Seven prior funding variants plus seven newly sized variants equals14 sequential funding trials. All other prior trading research remains additional selection history.",
                "calibration": "Original2024 persistence variants earned positive net/stressed returns but exceeded the frozen2.5% daily conservative equity envelope. Halve active capital while leaving the other half dormant.2024 outcomes are known calibration data, never confirmatory evidence.2025/2026 funding performance remains unopened until the one-candidate locks below.",
                "capital": {"total_account": 100000, "btc_active": 25000, "eth_active": 25000,
                            "dormant_cash": 50000, "active_asset_spot_cash": 12500,
                            "active_asset_isolated_derivative_cash": 12500,
                            "dormant_cash_interest": 0, "dormant_cash_can_rescue_margin": False},
                "arithmetic": "At each calendar close and conservative worst mark, total equity is50000 idle cash plus BTC/ETH actual active dollar equity. Compute daily percentage returns from successive TOTAL equity; never halve active percentages or treat dormant cash as profit/collateral. Recompute bootstrap/monthly/concentration/half-period statistics on total equity.",
                "selection": source["protocol"]["selection"],
                "validation_final_gates": source["protocol"]["validation_final_gates"],
                "execution_signals_funding_margin": "Reuse original frozen funding_lab.simulate unchanged, capital25000 per asset only. Every signal, fee, separate wallet, pre-settlement liquidation check,1minute settlement entitlement delay, previous-closed-price mark proxy and sample-boundary hypothetical liquidation remains unchanged.",
                "selection_procedure": "Complete exact seven-variant2024 grid; choose ONE survivor by total return/max(total worst drawdown,.25), lexicographicID ties. Persist immutable training selection hash before ANY2025 simulation. If2025 fails any frozen gate, do not open2026 and never replace the winner. Persist immutable validation confirmation before the single2026 evaluation. No changes to gates after outcomes.",
                "inference": source["protocol"]["inference"], "friction": source["protocol"]["friction"],
                "data": source["protocol"]["data"], "permissions": source["protocol"]["permissions"],
                "limitations": "Adaptive capital calibration, imperfect funding/liquidation marks, actual current/historical account fees and filters unverified, counterparty/default/outage risks not quantified. Passing means a historical provisional candidate for further investigation, not stable future profit, live/prop suitability or Telegram production authorization."}
    immutable_write(DIRECTORY / "protocol.json", protocol)
    report = {"phase": "frozen_before_sized_outcomes", "protocol": protocol,
              "protocol_sha256": digest(protocol), "retrospective_provisional_candidate": False,
              "live_qualified": False, "prop_qualified": False}
    PROTOCOL_DOC.write_text("# Frozen half-active-capital carry protocol\n\nOriginal study and gates preserved. Risk calibration uses known2024 results; later funding performance is not yet evaluated.\n\n```json\n" + json.dumps(protocol, indent=2) + "\n```\n", encoding="utf-8")
    write_report(report)
    return report


def verify(report):
    p = report["protocol"]
    if digest(p) != report["protocol_sha256"] or p["variants"] != funding_lab.variants():
        raise ValueError("Sized protocol/grid changed")
    for path, expected in p["producers"].items():
        if file_hash(ROOT / path) != expected:
            raise ValueError("Producer changed after sizing freeze: " + path)
    if file_hash(ROOT / "docs/funding-research.json") != p["lineage_report_sha256"]:
        raise ValueError("Original funding report changed")
    if json.loads((DIRECTORY / "protocol.json").read_text()) != p:
        raise ValueError("Immutable sized protocol differs from report")


def load_inputs(report):
    original_report = json.loads((ROOT / "docs/funding-research.json").read_text())
    locks = original_report["input_lock"]
    for entry in locks.values():
        path = ROOT / entry["path"]
        if not path.exists() or file_hash(path) != entry["sha256"]:
            raise ValueError("Original input receipt missing or changed: " + entry["path"])
    if report.get("input_lock") and report["input_lock"] != locks:
        raise ValueError("Sized inputs changed")
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
        report.update(phase="completed_training_failed_later_periods_unopened", reason="No sized variant passed unchanged training gates.2025/2026 funding outcomes remain unopened.")
        write_report(report)
        return report
    chosen = sorted(survivors, key=lambda row: (-row["base"]["return_pct"] / max(.25, row["base"]["max_drawdown_pct"]), row["variant"]["id"]))[0]
    selection = {"variant_id": chosen["variant"]["id"], "protocol_sha256": report["protocol_sha256"],
                 "training_results_sha256": digest(report["training"]), "input_lock_sha256": report["input_lock_sha256"]}
    if report.get("training_selection") and report["training_selection"] != selection:
        raise ValueError("Locked sized training selection changed")
    immutable_write(DIRECTORY / "training-selection.json", selection)
    report["training_selection"] = selection
    report["training_selection_sha256"] = digest(selection)
    report.setdefault("training_selection_locked_at", now())
    report["phase"] = "one_sized_candidate_locked_before_validation"
    write_report(report)
    if "validation" not in report:
        report["validation"] = experiment(inputs, chosen["variant"], "validation")
        report["validation"]["checks"] = original.confirm_checks(report["validation"])
        write_report(report)
    if not all(report["validation"]["checks"].values()):
        report.update(phase="completed_validation_failed_final_unopened", reason="The ONE locked sized candidate failed unchanged2025 gates.2026 funding outcomes remain unopened; no winner replacement.")
        write_report(report)
        return report
    confirmation = {"protocol_sha256": report["protocol_sha256"],
                    "training_selection_sha256": report["training_selection_sha256"],
                    "validation_sha256": digest(report["validation"])}
    immutable_write(DIRECTORY / "validation-confirmation.json", confirmation)
    report["validation_confirmation"] = confirmation
    report["validation_confirmation_sha256"] = digest(confirmation)
    report.setdefault("validation_confirmation_locked_at", now())
    report["phase"] = "sized_validation_confirmed_before_final"
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
