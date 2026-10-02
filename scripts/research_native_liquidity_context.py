#!/usr/bin/env python3
"""Fixed photo-motivated clock contexts, reusing the frozen native FVG executor."""
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
from propdesk import native_liquidity_context as context, liquidity_native as engine, research_lab as lab
from scripts import research_liquidity_native as parent, research_broad as shared

DIRECTORY = ROOT / "data/liquidity-context-research"
OUTPUT = ROOT / "docs/liquidity-context-research.json"
MARKDOWN = ROOT / "docs/LIQUIDITY_CONTEXT_RESEARCH.md"
WINDOWS = parent.WINDOWS
COMMON_SHA256 = "5495a0683efeb6da230cf454b71c8e8ae952dc03534d23f3cedbcd9f56e9e839"
PRODUCERS = ("propdesk/native_liquidity_context.py", "scripts/research_native_liquidity_context.py",
             "tests/test_native_liquidity_context.py", "propdesk/liquidity_native.py",
             "scripts/research_liquidity_native.py", "propdesk/funding_lab.py", "propdesk/market.py",
             "propdesk/research_lab.py", "propdesk/research_stats.py", "propdesk/target_evaluation.py",
             "scripts/research_broad.py", "propdesk/tzdata/America/New_York", "propdesk/tzdata/Europe/London")


def write_report(report):
    raw = json.dumps(report, indent=2, allow_nan=False) + "\n"
    temporary = OUTPUT.with_suffix(".json.tmp")
    temporary.write_text(raw, encoding="utf-8")
    temporary.replace(OUTPUT)
    lines = ["# Native liquidity clock-context research", "", f"Phase: **{report['phase']}**.", "",
             f"Protocol SHA256: `{report['protocol_sha256']}`.", "",
             "48 preregistered configurations over an unchanged native perpetual FVG executor. NY/lunch and London filters use known sweep and confirmation closes, pinned IANA clocks, weekdays and same local date. No hindsight daily range or news labels.", "",
             "Adaptive research: prior native partial TRAIN and broader2024–2026 history already inspected. This is not globally blind, a payout result or proof of future profitability. Trading and Telegram remain disabled.", ""]
    if report.get("training"):
        lines += [f"TRAIN evaluated **{len(report['training'])}/48**; passing **{sum(row['passed'] for row in report['training'])}**.", "",
                  "| TRAIN variant | Net % | Double costs % | Episodes | Passed |", "|---|---:|---:|---:|---|"]
        for row in report["training"]:
            lines.append(f"|{row['id']}|{row['metrics']['return_pct']:+.4f}|{row['stress_metrics']['return_pct']:+.4f}|{row['metrics']['trade_count']}|{row['passed']}|")
    lines += ["", report.get("reason", "No outcome claim before the training screen."), ""]
    for role in ("validation", "final"):
        row = report.get(role)
        if row:
            monthly = row["target"]["base"]["geometric_monthly_return"]
            monthly = "undefined (insolvency)" if monthly is None else f"{monthly * 100:+.4f}%"
            lines += [f"{role}: net **{row['metrics']['return_pct']:+.4f}%**, monthly equivalent **{monthly}**, gate **{row['target']['passed']}**.", ""]
        else:
            lines += [f"{role}: **not evaluated** until the preceding fixed screen passes.", ""]
    lines += ["Source/protocol/producer fingerprints and all rejected TRAIN results remain registered. One primary only, fixed costs, no heldout substitute or risk rescaling. Native trade OHLC/uncertain funding entitlement/historical filters/marks/fees remain provisional; verified broker data, source-use permission, exact prop replay and new forward observation remain prerequisites."]
    MARKDOWN.write_text("\n".join(lines) + "\n", encoding="utf-8")


def make_protocol():
    if shared.file_hash(ROOT / "docs/EIGHT_PERCENT_PROTOCOL.json") != COMMON_SHA256:
        raise ValueError("Common target protocol changed")
    for key, expected in context.TZIF_HASHES.items():
        if shared.file_hash(ROOT / "propdesk/tzdata" / key) != expected:
            raise ValueError("Pinned context TZif changed")
    parent_path = ROOT / "data/liquidity-native-research/protocol.json"
    inherited = json.loads(parent_path.read_text())
    if inherited["grid"] != engine.grid():
        raise ValueError("Original native parent registration changed")
    for namespace in ("inputs", "producers"):
        for name, expected in inherited[namespace].items():
            if shared.file_hash(ROOT / name) != expected:
                raise ValueError("Original native parent input/producer changed")
    inputs = {**inherited["inputs"], "data/liquidity-native-research/protocol.json": shared.file_hash(parent_path)}
    return {"id": "native-perpetual-photo-clock-context-v1", "frozen_at": shared.now(),
            "human_protocol_path": "docs/LIQUIDITY_CONTEXT_PROTOCOL.md",
            "human_protocol_sha256": shared.file_hash(ROOT / "docs/LIQUIDITY_CONTEXT_PROTOCOL.md"),
            "common_objective_path": "docs/EIGHT_PERCENT_PROTOCOL.json", "common_objective_sha256": COMMON_SHA256,
            "parent_protocol_sha256": lab.digest(inherited), "grid": context.grid(), "windows": WINDOWS,
            "producers": {**inherited["producers"], **{name: shared.file_hash(ROOT / name) for name in PRODUCERS}}, "inputs": inputs,
            "context_rules": context.CONTEXTS, "timezone_source": {key: {"path": "propdesk/tzdata/" + key, "sha256": expected}
                                                                      for key, expected in context.TZIF_HASHES.items()},
            "timezone_loading": "ZoneInfo.from_file on exact pinned bundled TZif; never host database or handwritten DST",
            "fixed_parent_parameters": {"reward_risk": 2.5, "expiry": 4, "trend_context": False},
            "trial_budget": "48configs=2resolutions×2priorliquiditywindows×2bodyATRthresholds×2clockcontexts×3registeredrisks;16economic/timecontexts. All prior adaptive trials remain disclosed.",
            "context_known_at": "Onlyconfirmed signal_close event may be admitted; sweep_time is also the completed sweep close. NY[11,14),confirm<17;London[07,10),confirm<13. Sweep andconfirmation on same localweekday/date. Filter only timestamps, no futureprices ornews.",
            "execution": "Unchanged parent Features/setups/simulate andcosts/funding/margin/noabsence/reconciliation gates; context canonlydiscard a parentevent. FixedRR2.5/expiry4/EMAoff; pricelevels/expiry/invalidations remainidentical.",
            "capital": inherited["capital"], "costs": inherited["costs"], "funding": inherited["funding"],
            "missing_execution": inherited["missing_execution"], "inference": inherited["inference"],
            "selection": "All48TRAIN2024base/doublecost+commonrisk/activity+zeroliquidation/deficit/absence+cashreconciliation. OnepassedprimarymaxTRAINscoretielexicalIDlockedbefore2025. NoTRAINpass=>allOOSunopened; validationfailure=>2026unopened. Passingvalidationconfirmationbeforeone2026primary. Noalternatives/postresultscaling.",
            "physical_prefix": "Eachwindowgeneratesparentfeatures/setups frombarsstrictlybeforeend; fundingoutcomeslaterthanend excluded, exactboundaryadversefunding retainedbyunchangedexecutor. No postwindowreturns orsignals reachTRAIN.",
            "motivation": "User supplied liquidity-raid/FVG photos withNYlunch narrative; public FXtime-of-day concepts motivate a distinct clock hypothesis, without assuming transfer toBTC/ETHperpetuals.",
            "adaptive_disclosure": "Originalnative192partialTRAINresults andpriorbroad2024–2026market context alreadyinspected before thisregistration. Existingparentperformance isnotamended; thecontextsareadditionaladaptivehypotheses,notgloballyblind.",
            "qualification": "Historical8%geometricmonthlyreference only. No realorders,TG,paperpromotion,propcontractproof orfutureexpectedprofit claim."}


def verify(report):
    protocol = report["protocol"]
    if (lab.digest(protocol) != report["protocol_sha256"] or
            protocol != json.loads((DIRECTORY / "protocol.json").read_text()) or protocol["grid"] != context.grid()):
        raise ValueError("Frozen context protocol mismatch")
    for namespace in ("producers", "inputs"):
        for name, expected in protocol[namespace].items():
            if shared.file_hash(ROOT / name) != expected:
                raise ValueError("Frozen context producer/source changed: " + name)
    for prefix in ("common_objective", "human_protocol"):
        if shared.file_hash(ROOT / protocol[prefix + "_path"]) != protocol[prefix + "_sha256"]:
            raise ValueError("Frozen context objective/rules changed")


def freeze():
    if OUTPUT.exists():
        report = json.loads(OUTPUT.read_text())
        verify(report)
        return report
    protocol = make_protocol()
    shared.immutable_write(DIRECTORY / "protocol.json", protocol)
    report = {"phase": "frozen_before_outcomes", "protocol": protocol, "protocol_sha256": lab.digest(protocol),
              "training": [], "selected": None, "retrospective_target_candidate": False,
              "live_qualified": False, "prop_qualified": False, "telegram_enabled": False, "live_orders": False}
    write_report(report)
    return report


def verify_final_authorization(report):
    """Require immutable passing validation and primary identities before FINAL."""
    selection = json.loads((DIRECTORY / "training-selection.json").read_text())
    confirmation = json.loads((DIRECTORY / "validation-confirmation.json").read_text())
    validation = report.get("validation", {})
    primary_rows = [row for row in report.get("training", []) if row.get("id") == report.get("selected")]
    if (not isinstance(report.get("selected"), str) or len(primary_rows) != 1 or primary_rows[0].get("passed") is not True
            or primary_rows[0].get("target", {}).get("passed") is not True
            or selection != report.get("selection_lock") or lab.digest(selection) != report.get("selection_lock_sha256")
            or selection.get("protocol_sha256") != report.get("protocol_sha256")
            or selection.get("training_sha256") != lab.digest(report.get("training"))
            or selection.get("selected") != report.get("selected") or selection.get("locked_before_validation") is not True
            or confirmation != report.get("confirmation_lock") or lab.digest(confirmation) != report.get("confirmation_lock_sha256")
            or confirmation.get("protocol_sha256") != report.get("protocol_sha256")
            or confirmation.get("selection_lock_sha256") != report.get("selection_lock_sha256")
            or confirmation.get("validation_sha256") != lab.digest(validation)
            or confirmation.get("selected") != report.get("selected") or confirmation.get("locked_before_final") is not True
            or validation.get("passed") is not True or validation.get("target", {}).get("passed") is not True
            or validation.get("variant", {}).get("id") != report.get("selected")):
        raise ValueError("Frozen selection/validation confirmation does not authorize FINAL")
    verify(report)


def save_ledger(result, role, scenario):
    path = ROOT / ".local/liquidity-context-research" / (role + "-" + scenario + ".json.gz")
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(result, separators=(",", ":"), allow_nan=False).encode()
    compressed = gzip.compress(raw, mtime=0)
    if path.exists() and path.read_bytes() != compressed:
        raise ValueError("Immutable context ledger changed")
    if not path.exists():
        path.write_bytes(compressed)
    return {"path": str(path.relative_to(ROOT)), "gzip_sha256": shared.file_hash(path),
            "raw_sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(compressed)}


def period(features, variant, role, signal_cache, *, ledgers=False, seed=20261002):
    base_variant = variant["parent_variant"]
    key = (role, base_variant["minutes"], base_variant["liquidity"], base_variant["body_atr"], variant["context"])
    if key not in signal_cache:
        signal_cache[key] = context.setups(features, variant)
    signals = signal_cache[key]
    start, end = WINDOWS[role]
    base = engine.simulate(features, signals, start, end, risk_fraction=variant["risk_fraction"])
    stress = engine.simulate(features, signals, start, end, cost_multiplier=2, risk_fraction=variant["risk_fraction"])
    evaluated = parent.assess(base, stress, WINDOWS[role], role, seed)
    row = {"id": variant["id"], "variant": variant, "metrics": base["metrics"], "stress_metrics": stress["metrics"],
           "target": evaluated, "passed": evaluated["passed"], "score": evaluated["selection_score_net_return_over_drawdown"],
           "confirmed_context_events": sum(len(assets) for epoch, assets in signals.items()
                if start <= datetime.fromtimestamp(epoch, timezone.utc).date().isoformat() < end)}
    if ledgers:
        row.update(daily=base["daily"], stress_daily=stress["daily"],
                   raw_ledger={"base": save_ledger(base, role, "base"), "double_cost": save_ledger(stress, role, "double_cost")})
    return row


def run():
    report = freeze()
    verify(report)
    if report["phase"].startswith("completed_"):
        return report
    full = parent.load_inputs()
    features = context.PrefixFeatures(full, WINDOWS["training"][1])
    signals = {}
    variants, training = report["protocol"]["grid"], report["training"]
    if [row["variant"] for row in training] != variants[:len(training)]:
        raise ValueError("Context TRAIN resume must match registered prefix")
    for index in range(len(training), len(variants)):
        row = period(features, variants[index], "training", signals, seed=20261002)
        training.append(row)
        report["phase"] = "training_in_progress"
        write_report(report)
        print(f"Context TRAIN{index+1}/48 {row['id']} net={row['metrics']['return_pct']:+.4f}% double={row['stress_metrics']['return_pct']:+.4f}% episodes={row['metrics']['trade_count']} passed={row['passed']}", flush=True)
    verify(report)
    passing = sorted((row for row in training if row["passed"]), key=lambda row: (-row["score"], row["id"]))
    selected = passing[0]["id"] if passing else None
    lock_path = DIRECTORY / "training-selection.json"
    lock = {"protocol_sha256": report["protocol_sha256"], "training_sha256": lab.digest(training), "selected": selected,
            "locked_before_validation": True, "locked_at": shared.now()}
    if lock_path.exists():
        lock["locked_at"] = json.loads(lock_path.read_text())["locked_at"]
    shared.immutable_write(lock_path, lock)
    report.update(selected=selected, selection_lock=lock, selection_lock_sha256=lab.digest(lock), phase="training_complete")
    write_report(report)
    if selected is None:
        report.update(phase="completed_no_training_candidate", reason="No context candidate passed unchanged TRAIN cost/risk/activity/source gates; all2025/2026strategyperformance remainsunopened. No substitute orrescaling.")
        write_report(report)
        return report
    variant = next(item for item in variants if item["id"] == selected)
    if "training_primary" not in report:
        primary = period(features, variant, "training", signals, ledgers=True)
        previous = next(row for row in training if row["id"] == selected)
        if primary["metrics"] != previous["metrics"] or primary["stress_metrics"] != previous["stress_metrics"]:
            raise ValueError("Selected context TRAIN failed deterministic replay")
        report["training_primary"] = primary
        write_report(report)
    for role in ("validation", "final"):
        if role == "final":
            verify_final_authorization(report)
        if role not in report:
            visible = context.PrefixFeatures(full, WINDOWS[role][1])
            report[role] = period(visible, variant, role, signals, ledgers=True)
            report["phase"] = role + "_complete"
            write_report(report)
        if not report[role]["passed"]:
            report.update(phase="completed_" + role + "_failed", reason="Locked context primary failed " + role + "; no alternatives orresizing. " + ("2026strategyperformance remainsunopened." if role == "validation" else "No historical8%monthlycandidate."))
            write_report(report)
            return report
        if role == "validation":
            if report.get("confirmation_lock") is not None:
                # A resumed claimed confirmation is verified, never repaired
                # from a mutable report when its original file is missing.
                verify_final_authorization(report)
                continue
            path = DIRECTORY / "validation-confirmation.json"
            confirmation = {"protocol_sha256": report["protocol_sha256"], "selection_lock_sha256": report["selection_lock_sha256"],
                            "validation_sha256": lab.digest(report[role]), "selected": selected,
                            "locked_before_final": True, "locked_at": shared.now()}
            if path.exists():
                confirmation["locked_at"] = json.loads(path.read_text())["locked_at"]
            shared.immutable_write(path, confirmation)
            report.update(confirmation_lock=confirmation, confirmation_lock_sha256=lab.digest(confirmation))
            write_report(report)
    verify(report)
    report.update(phase="completed_retrospective_target_candidate", retrospective_target_candidate=True,
                  reason="One context candidate passed historical reference gates; execution/prop/license/forwardproof remainsunverified. Live/TGdisabled.")
    write_report(report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze", action="store_true")
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()
    if not (args.freeze or args.run):
        parser.error("Choose --freeze or --run")
    report = run() if args.run else freeze()
    print(json.dumps({name: report.get(name) for name in ("phase", "protocol_sha256", "selected", "retrospective_target_candidate")}))


if __name__ == "__main__":
    main()
