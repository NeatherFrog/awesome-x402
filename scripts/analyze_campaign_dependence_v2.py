#!/usr/bin/env python3
"""Versioned descriptive audit of existing TRAIN paths, never a simulator."""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import analyze_campaign_dependence as original
from propdesk import research_campaign as campaign

NEW_STUDIES = ("native_mark", "native_mark_v2", "native_noise", "cross_sectional")
ORIGINAL_SNAPSHOT = ("docs/CAMPAIGN_DEPENDENCE.json", "docs/CAMPAIGN_DEPENDENCE.md")


def _inventory_record(root, study, report, checked):
    spec = campaign.STUDIES[study]
    report_path = Path(root) / "docs" / spec["file"]
    return {"study": study, "report_file": str(report_path.relative_to(root)),
            "report_sha256": original.sha(report_path), "protocol_sha256": report["protocol_sha256"],
            "evaluated_configurations": checked["reported_evaluated_configurations"],
            "retained_configurations": 0, "retained_cost_paths": 0, "unavailable": [],
            "protocol_producer_results_verified": bool(checked["protocol_verified"] and checked["producer_hashes_verified"] and checked["training_results_verified"]),
            "input_hashes_verified": checked["input_hashes_verified"],
            "execution_causality_status": checked["execution_causality_status"],
            "promotion_blocked": checked["promotion_blocked"],
            "causality_audit_receipt_verified": checked["causality_audit_receipt_verified"]}


def primary_evidence(root, study, report):
    """Only the original locked primary; never choose one from correlations."""
    selected = report.get("selected")
    if selected is None:
        return []
    lock = report.get("selection_lock")
    if not isinstance(lock, dict) or lock.get("selected") != selected:
        raise ValueError("Original primary identity not selection-bound")
    row = next((item for item in report.get("training", []) if item.get("id") == selected), None)
    if row is None:
        raise ValueError("Original primary missing from TRAIN results")
    name = "data/" + campaign.STUDIES[study]["directory"] + "/training_primary_evidence.json"
    path = campaign._path(root, name)
    # Full ledgers have no portable-receipt fallback. They are data, not a
    # small protocol or selection receipt.
    evidence = campaign._json(path)
    if not evidence or campaign.digest(evidence) != lock.get("training_primary_evidence_sha256"):
        raise ValueError("Original full primary evidence missing or hash mismatch")
    if evidence.get("protocol_sha256") != report.get("protocol_sha256") or evidence.get("selected") != selected:
        raise ValueError("Full primary evidence belongs to another protocol or selection")
    receipt = {"path": name, "file_sha256": original.sha(path),
               "canonical_sha256": campaign.digest(evidence), "kind": "selection-bound-original-primary-json"}
    return [(row, evidence, receipt)]


def retained_rows(root, study, report):
    if study in ("native_mark", "native_mark_v2"):
        return primary_evidence(root, study, report)
    return [(row, None, None) for row in report.get("training", [])]


def daily_path(root, study, row, scenario, evidence=None, primary_receipt=None):
    variant = row["variant"]
    start, end = row["target"]["period_start"], row["target"]["period_end_exclusive"]
    if study in ("native_mark", "native_mark_v2"):
        raw = evidence[scenario]
        receipt = {**primary_receipt, "scenario": scenario}
        daily = raw["daily_returns"]
        dates, returns = [item["date"] for item in daily], [item["return"] for item in daily]
    elif study == "native_noise":
        receipt = row["base_ledger" if scenario == "base" else "stress_ledger"]
        raw = original.ledger(root, receipt)
        if raw.get("variant_id") != variant["id"] or raw.get("role") != "training" or raw.get("window") != [start, end]:
            raise ValueError("Noise ledger configuration, role or exact TRAIN window differs")
        daily = raw["daily_returns"]
        dates, returns = [item["date"] for item in daily], [item["return"] for item in daily]
    elif study == "cross_sectional":
        receipt = row["ledgers"][scenario]
        raw = original.ledger(root, receipt)
        if raw.get("variant") != variant:
            raise ValueError("Cross-sectional ledger configuration differs")
        daily = raw["daily_curve"]
        dates, returns = [item["time"] for item in daily], [item["return"] for item in daily]
    else:
        raise ValueError("Unknown fixed TRAIN ledger adapter")
    metrics_key = "metrics" if scenario == "base" else "stress_metrics"
    if raw.get("metrics") != row.get(metrics_key):
        raise ValueError("Full ledger metrics differ from the registered TRAIN row")
    values = original.validate_path(dates, returns, start, end)
    return dates, values, receipt


def collect(root):
    inventory, series = original.collect(root)
    for record in inventory:
        record.update(execution_causality_status="not_certified_by_this_diagnostic", promotion_blocked=False)
    for item in series:
        item.update(execution_causality_status="not_certified_by_this_diagnostic", promotion_blocked=False,
                    retention_scope="all_original_retained_rows" if item["study"] in ("fx", "metals") else "original_locked_primary_only")
    for study in NEW_STUDIES:
        report = campaign.read_report(root, study)
        if report is None:
            inventory.append({"study": study, "evaluated_configurations": 0, "retained_configurations": 0,
                              "retained_cost_paths": 0, "promotion_blocked": False,
                              "unavailable_reason": "Report missing; no requested budget counted"})
            continue
        checked = campaign.inspect(root, study, report)
        record = _inventory_record(root, study, report, checked)
        inventory.append(record)
        if not record["protocol_producer_results_verified"]:
            record.update(missing_daily_configurations=record["evaluated_configurations"],
                          unavailable_reason="Report protocol, producer or sealed TRAIN lock failed; partial rows are not promoted to dependence evidence")
            continue
        try:
            retained = retained_rows(root, study, report)
        except (OSError, ValueError, KeyError, TypeError) as error:
            record["unavailable_reason"] = str(error)
            retained = []
        if not retained and "unavailable_reason" not in record:
            record["unavailable_reason"] = "No original locked TRAIN primary with retained full ledger; compact rows are not reconstructed"
        for row, evidence, primary_receipt in retained:
            variant = row["variant"]
            paths = []
            try:
                for scenario in ("base", "double_cost"):
                    dates, values, receipt = daily_path(root, study, row, scenario, evidence, primary_receipt)
                    paths.append({"id": study + ":" + variant["id"] + ":" + scenario,
                                  "study": study, "variant_id": variant["id"], "variant": variant,
                                  "economic_parameters": original.economic_parameters(variant), "scenario": scenario,
                                  "role": "TRAIN", "start": row["target"]["period_start"],
                                  "end_exclusive": row["target"]["period_end_exclusive"], "dates": dates, "returns": values,
                                  "dates_sha256": campaign.digest(dates), "returns_sha256": campaign.digest(values),
                                  "flat_dates": sum(value == 0 for value in values), "ledger_receipt": receipt,
                                  "report_sha256": record["report_sha256"],
                                  "execution_causality_status": record["execution_causality_status"],
                                  "promotion_blocked": record["promotion_blocked"],
                                  "retention_scope": "original_locked_primary_only" if evidence is not None else "all_original_retained_rows"})
            except (OSError, ValueError, KeyError, TypeError) as error:
                record["unavailable"].append({"variant_id": variant["id"], "reason": str(error)})
                continue
            series.extend(paths)
            record["retained_configurations"] += 1
            record["retained_cost_paths"] += len(paths)
        record["missing_daily_configurations"] = record["evaluated_configurations"] - record["retained_configurations"]
    return inventory, series


def interpretation_twins(series):
    """Match pre-existing identities; never deduplicate or pick high profit."""
    pairs = defaultdict(dict)
    for item in series:
        if item["study"] in ("native_mark", "native_mark_v2") and item["scenario"] == "base":
            pairs[(item["variant_id"], tuple(item["dates"]))][item["study"]] = item
    result = []
    for values in pairs.values():
        if set(values) == {"native_mark", "native_mark_v2"}:
            left, right = values["native_mark"], values["native_mark_v2"]
            if left["variant"] != right["variant"]:
                continue
            result.append({"base_ids": [left["id"], right["id"]],
                           "pearson": original.paired_correlation(left["returns"], right["returns"]),
                           "contains_causally_blocked_path": True,
                           "interpretation": "Same registered rule/risk/source; changed execution interpretation. V1 is causally revoked. Neither rank nor correlation validates it."})
    return result


def summarize(inventory, series):
    value = original.summarize(inventory, series)
    value.update(id="retained-campaign-training-dependence-v2", previous_292="Not inspected; absent daily paths never inferred from totals",
                 role="TRAINONLY descriptive diagnostic; no simulation, re-selection or qualification",
                 completed_campaign_evaluations_including_previous_292=292 + value["additional_evaluated_configurations"],
                 blocked_daily_configurations=sum(item.get("promotion_blocked", False) for item in series if item["scenario"] == "base"),
                 execution_interpretation_twins=interpretation_twins(series))
    lookup = {item["id"]: item for item in series}
    for group in value["groups"]:
        members = [lookup[name] for name in group["base_series_ids"]]
        blocked = [item for item in members if item.get("promotion_blocked")]
        regular = [item for item in members if not item.get("promotion_blocked")]
        group["blocked_base_series_ids"] = [item["id"] for item in blocked]
        group["non_revoked_base_series_ids"] = [item["id"] for item in regular]
        group["non_revoked_base"] = original.matrix_statistics([item["returns"] for item in regular]) if regular else None
        group["includes_revoked_execution_diagnostic"] = bool(blocked)
        group["causal_scope"] = "Non-revoked does not mean externally certified, eligible, independent or profitable; blocked V1 is included only in explicitly labeled diagnostic matrices."
    value["limitations"] += [
        "One already selected TRAIN primary is retained per mark interpretation; this audit does not search for a correlated or profitable replacement.",
        "The known mark-V1 causal counterexample invalidates its execution interpretation. Its preserved path is a diagnostic, not causal economic evidence; non-revoked-only matrices are also reported.",
        "The original dependence V1 publication is an immutable earlier snapshot, not overwritten by new coverage."]
    return value


def markdown(value):
    lines = ["# Retained TRAIN campaign dependence — version 2", "",
             f"Retained daily paths: **{value['retained_daily_configurations']}/{value['additional_evaluated_configurations']}** additional configurations; **{value['missing_daily_configurations']}** have no verified retained full daily path. Observed campaign total including the previous292: **{value['completed_campaign_evaluations_including_previous_292']}**.", "",
             "Existing TRAIN artifacts only: no simulation, winning-model selection, independent-trial estimate, p-value correction or trading admission. Cost scenarios are not extra strategies. Every date is exactly retained, including verified flat days; missing dates are never filled. The earlier CAMPAIGN_DEPENDENCE publication remains unchanged.", "",
             "| Study | Evaluated TRAIN | Retained models | Cost paths | Revoked execution |", "|---|---:|---:|---:|---|"]
    for item in value["inventory"]:
        lines.append(f"|{item['study']}|{item['evaluated_configurations']}|{item['retained_configurations']}|{item.get('retained_cost_paths',0)}|{'yes, diagnostic only' if item.get('promotion_blocked') else 'no known revocation in this registry'}|")
    lines += ["", "| Exact TRAIN calendar | Days | Base models | Covariance rank all | Covariance rank excluding revoked |", "|---|---:|---:|---:|---:|"]
    def rank(stat):
        return "undefined" if stat is None or stat["effective_covariance_rank"] is None else f"{stat['effective_covariance_rank']:.6f}"
    for group in value["groups"]:
        lines.append(f"|{group['start']} → {group['end_exclusive']} exclusive|{len(group['calendar_dates'])}|{len(group['base_series_ids'])}|{rank(group['base'])}|{rank(group['non_revoked_base'])}|")
    for group in value["groups"]:
        lines += ["", f"{group['start']}: {group['base']['positive_variance_paths']} varying paths, {group['base']['zero_variance_paths']} constant paths; {len(group['blocked_base_series_ids'])} causal-revoked diagnostic path(s). Constant-path Pearson values are undefined, not zero."]
        for field, label in (("cost_twin_correlation_summary", "base/double-cost"), ("risk_sibling_correlation_summary", "registered risk siblings")):
            median = group[field]["median"]
            if median is not None:
                lines.append(f"Median {label} Pearson: **{median:.6f}**; observed repetition does not measure independent trials.")
    lines += ["", "Effective covariance rank is `trace(C)^2 / trace(C*C)` of centered daily simple total-account returns, sample ddof1. It describes covariance concentration in each exact calendar window and changes with risk, costs and coverage. It is not the number of independent hypotheses, an effective sample size, a multiplicity correction or a profitable allocation.", "",
              "All observed paths are retained without outcome-based deduplication. Risk siblings, identical observed vectors, cost twins and matched mark execution interpretations are labeled in JSON. The mark-V1 path has a known causal failure and appears only as explicitly blocked diagnostic data; the parallel non-revoked matrices exclude it. Other models remain unqualified as well.", "", *value["limitations"], "",
              "JSON binds report, source/producer consistency, original ledger hashes, exact date/return fingerprints and the unchanged V1 snapshot. Full-history and full-ledger availability remain explicit. Monthly totals are never converted into invented daily returns."]
    return "\n".join(lines) + "\n"


def require_complete(inventory):
    records = {item["study"]: item for item in inventory}
    for study in original.STUDIES + NEW_STUDIES:
        item = records.get(study, {})
        if (item.get("evaluated_configurations") != campaign.STUDIES[study]["count"] or
                not item.get("protocol_producer_results_verified")):
            raise ValueError("Await complete sealed TRAIN artifacts before publishing V2: " + study)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    root = args.root.resolve()
    inventory, series = collect(root)
    require_complete(inventory)
    value = summarize(inventory, series)
    value["original_snapshot_sha256"] = {name: original.sha(campaign._path(root, name)) for name in ORIGINAL_SNAPSHOT}
    value["diagnostic_producers"] = {name: original.sha(ROOT / name) for name in
        ("scripts/analyze_campaign_dependence_v2.py", "tests/test_campaign_dependence_v2.py", "scripts/analyze_campaign_dependence.py", "propdesk/research_campaign.py")}
    output = root / "docs/CAMPAIGN_DEPENDENCE_V2.json"
    payload = json.dumps(value, indent=2, allow_nan=False) + "\n"
    description = markdown(value)
    if output.exists() or output.with_suffix(".md").exists():
        raise ValueError("Versioned published diagnostic already exists; create a new version instead of rewriting it")
    with output.open("x") as stream:
        stream.write(payload)
    with output.with_suffix(".md").open("x") as stream:
        stream.write(description)
    print(json.dumps({key: value[key] for key in ("status", "additional_evaluated_configurations", "retained_daily_configurations", "missing_daily_configurations", "cost_paths", "blocked_daily_configurations")}))


if __name__ == "__main__":
    main()
