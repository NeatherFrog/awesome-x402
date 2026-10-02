#!/usr/bin/env python3
"""Describe retained TRAIN paths; never simulate, select or qualify a model."""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import date, timedelta
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from propdesk import research_campaign as campaign

STUDIES = ("pairs", "pairs_close", "sessions", "fx", "native_fvg", "native_trend", "native_context", "metals", "crypto_flow")
MAX_COMPRESSED = 8 * 1024 * 1024
MAX_RAW = 64 * 1024 * 1024


def sha(path):
    return campaign._file_hash(Path(path))


def calendar(start, end):
    begin, finish = date.fromisoformat(start), date.fromisoformat(end)
    if start != begin.isoformat() or end != finish.isoformat() or begin >= finish or (finish - begin).days > 2000:
        raise ValueError("Invalid bounded calendar window")
    return [(begin + timedelta(days=index)).isoformat() for index in range((finish - begin).days)]


def validate_path(dates, returns, start, end):
    expected = calendar(start, end)
    if dates != expected or not isinstance(returns, list) or len(returns) != len(expected):
        raise ValueError("Retained dates must equal every exact calendar date; never fill a gap")
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) for value in returns):
        raise ValueError("Nonfinite or nonnumeric retained daily return")
    return [float(value) for value in returns]


def ledger(root, receipt):
    if not isinstance(receipt, dict):
        raise ValueError("Missing registered raw ledger")
    path = campaign._path(root, receipt.get("path"))
    if not path.is_file() or path.stat().st_size > MAX_COMPRESSED:
        raise ValueError("Retained compressed ledger absent or exceeds bound")
    expected = receipt.get("compressed_sha256", receipt.get("gzip_sha256"))
    if sha(path) != expected:
        raise ValueError("Compressed ledger hash mismatch")
    with gzip.GzipFile(fileobj=io.BytesIO(path.read_bytes())) as stream:
        raw = stream.read(MAX_RAW + 1)
    if len(raw) > MAX_RAW or hashlib.sha256(raw).hexdigest() != receipt.get("raw_sha256"):
        raise ValueError("Uncompressed ledger exceeds bound or hash mismatch")
    value = json.loads(raw, parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite ledger")))
    if not isinstance(value, dict):
        raise ValueError("Invalid retained ledger format")
    return value


def economic_parameters(variant):
    """Catalogue repetition, not an estimate of statistical independence."""
    return {key: economic_parameters(value) if isinstance(value, dict) else value
            for key, value in variant.items() if key not in ("id", "risk", "risk_fraction", "risk_pct")}


def matrix_statistics(vectors, *, correlations=True):
    if not vectors or len(vectors[0]) < 2 or any(len(vector) != len(vectors[0]) for vector in vectors):
        raise ValueError("Covariance needs equally aligned paths and at least two observations")
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) for vector in vectors for value in vector):
        raise ValueError("Covariance needs finite values")
    n, width = len(vectors[0]), len(vectors)
    centered = []
    for vector in vectors:
        mean = math.fsum(vector) / n
        centered.append([value - mean for value in vector])
    covariance = [[0.0] * width for _ in vectors]
    for i in range(width):
        for j in range(i, width):
            value = math.fsum(left * right for left, right in zip(centered[i], centered[j])) / (n - 1)
            covariance[i][j] = covariance[j][i] = value
    trace = math.fsum(covariance[i][i] for i in range(width))
    squared = math.fsum(value * value for row in covariance for value in row)
    result = {"observations": n, "dimensions": width, "sample_ddof": 1,
              "covariance_trace": trace, "covariance_squared_trace": squared,
              "effective_covariance_rank": trace * trace / squared if squared else None,
              "algebraic_rank_upper_bound": min(sum(covariance[i][i] > 0 for i in range(width)), n - 1),
              "positive_variance_paths": sum(covariance[i][i] > 0 for i in range(width)),
              "zero_variance_paths": sum(covariance[i][i] == 0 for i in range(width)),
              "definition": "trace(C)^2 / trace(C*C), C=sample covariance of exactly aligned DAILY SIMPLE TOTAL ACCOUNT returns",
              "interpretation": "Descriptive spectral concentration; not independent strategies, independent tests, effective sample size or a multiplicity correction."}
    if correlations:
        result["pearson"] = [[max(-1.0, min(1.0, covariance[i][j] / math.sqrt(covariance[i][i] * covariance[j][j])))
                              if covariance[i][i] > 0 and covariance[j][j] > 0 else None
                              for j in range(width)] for i in range(width)]
    return result


def paired_correlation(left, right):
    return matrix_statistics([left, right])["pearson"][0][1]


def correlation_summary(values):
    known = [value for value in values if value is not None]
    return {"known_pairs": len(known), "undefined_pairs": len(values) - len(known),
            "minimum": min(known) if known else None, "median": statistics.median(known) if known else None,
            "maximum": max(known) if known else None}


def collect(root):
    inventory, series = [], []
    for study in STUDIES:
        spec = campaign.STUDIES[study]
        report = campaign.read_report(root, study)
        if report is None:
            inventory.append({"study": study, "evaluated_configurations": 0, "retained_configurations": 0,
                              "unavailable_reason": "Report missing; no budget counted"})
            continue
        checked = campaign.inspect(root, study, report)
        report_path = Path(root) / "docs" / spec["file"]
        record = {"study": study, "report_file": str(report_path.relative_to(root)), "report_sha256": sha(report_path),
                  "protocol_sha256": report["protocol_sha256"], "evaluated_configurations": checked["reported_evaluated_configurations"],
                  "retained_configurations": 0, "retained_cost_paths": 0, "unavailable": [],
                  "protocol_producer_results_verified": checked["protocol_verified"] and checked["producer_hashes_verified"] and checked["training_results_verified"],
                  "input_hashes_verified": checked["input_hashes_verified"]}
        inventory.append(record)
        if not record["protocol_producer_results_verified"]:
            record["unavailable_reason"] = "Report protocol, producer or TRAIN lock consistency failed"
            continue
        rows = report.get("training", [])
        # The native primary was already selected by the original study. No new
        # P&L comparison or alternative inspection chooses it for this script.
        retained = rows if study in ("fx", "metals") else [report["training_primary"]] if study == "native_fvg" and report.get("training_primary") else []
        if not retained:
            record["unavailable_reason"] = "Only compact TRAIN metrics retained; no daily path reconstruction"
        for row in retained:
            variant = row["variant"]
            target = row.get("target", row)
            if study == "native_fvg":
                source_row = next(item for item in rows if item["id"] == variant["id"])
                target = source_row["target"]
            start, end = target["period_start"], target["period_end_exclusive"]
            paths = []
            try:
                for scenario, field in (("base", "base_ledger"), ("double_cost", "stress_ledger")):
                    receipt = row["raw_ledger"][scenario] if study == "native_fvg" else row[field]
                    raw = ledger(root, receipt)
                    if study == "native_fvg":
                        daily = raw["daily"]
                        if daily != row["daily" if scenario == "base" else "stress_daily"]:
                            raise ValueError("Published daily path differs from registered ledger")
                        dates, returns = [item["date"] for item in daily], [item["return"] for item in daily]
                    else:
                        if raw["variant"] != variant:
                            raise ValueError("Retained ledger belongs to another configuration")
                        dates, returns = raw["dates"], raw["daily_returns"]
                        if scenario == "base" and (dates != row["daily_dates"] or returns != row["daily_returns"]):
                            raise ValueError("Published base path differs from registered ledger")
                    returns = validate_path(dates, returns, start, end)
                    paths.append({"id": study + ":" + variant["id"] + ":" + scenario,
                                  "study": study, "variant_id": variant["id"], "variant": variant,
                                  "economic_parameters": economic_parameters(variant), "scenario": scenario,
                                  "role": "TRAIN", "start": start, "end_exclusive": end, "dates": dates,
                                  "returns": returns, "dates_sha256": campaign.digest(dates),
                                  "returns_sha256": campaign.digest(returns), "flat_dates": sum(value == 0 for value in returns),
                                  "ledger_receipt": receipt, "report_sha256": record["report_sha256"]})
            except (OSError, ValueError, KeyError, TypeError, StopIteration) as error:
                record["unavailable"].append({"variant_id": variant["id"], "reason": str(error)})
                continue
            series.extend(paths)
            record["retained_configurations"] += 1
            record["retained_cost_paths"] += len(paths)
        record["missing_daily_configurations"] = record["evaluated_configurations"] - record["retained_configurations"]
    return inventory, series


def summarize(inventory, series):
    buckets = defaultdict(list)
    for item in series:
        buckets[(item["start"], item["end_exclusive"], tuple(item["dates"]))].append(item)
    groups = []
    for (start, end, dates), items in sorted(buckets.items()):
        items.sort(key=lambda item: item["id"])
        base = [item for item in items if item["scenario"] == "base"]
        stress = [item for item in items if item["scenario"] == "double_cost"]
        group = {"start": start, "end_exclusive": end, "calendar_dates": list(dates),
                 "alignment": "Identical complete retained calendar; flats included as observed, no union/interpolation/filled returns",
                 "base_series_ids": [item["id"] for item in base],
                 "base": matrix_statistics([item["returns"] for item in base]),
                 "double_cost": matrix_statistics([item["returns"] for item in stress], correlations=False),
                 "base_plus_double_cost": matrix_statistics([item["returns"] for item in items], correlations=False),
                 "base_to_double_cost": [], "risk_siblings": [], "identical_base_paths": []}
        lookup = {(item["study"], item["variant_id"], item["scenario"]): item for item in items}
        siblings, identical = defaultdict(list), defaultdict(list)
        for item in base:
            counterpart = lookup[(item["study"], item["variant_id"], "double_cost")]
            group["base_to_double_cost"].append({"base_id": item["id"], "double_cost_id": counterpart["id"],
                                                 "pearson": paired_correlation(item["returns"], counterpart["returns"]),
                                                 "same_model_different_costs": True})
            siblings[(item["study"], campaign.digest(item["economic_parameters"]))].append(item)
            identical[tuple(item["returns"])].append(item["id"])
        for values in siblings.values():
            if len(values) > 1:
                group["risk_siblings"].append({"base_ids": [item["id"] for item in values],
                    "economic_parameters": values[0]["economic_parameters"],
                    "pearson": matrix_statistics([item["returns"] for item in values])["pearson"],
                    "interpretation": "Same economic rules/price source; risk versions are not independent discoveries"})
        group["identical_base_paths"] = [names for names in identical.values() if len(names) > 1]
        group["base_pair_correlation_summary"] = correlation_summary([value for i, row in enumerate(group["base"]["pearson"])
                                                                     for j, value in enumerate(row) if j > i])
        group["cost_twin_correlation_summary"] = correlation_summary([item["pearson"] for item in group["base_to_double_cost"]])
        group["risk_sibling_correlation_summary"] = correlation_summary([value for item in group["risk_siblings"]
            for i, row in enumerate(item["pearson"]) for j, value in enumerate(row) if j > i])
        groups.append(group)
    evaluated = sum(item["evaluated_configurations"] for item in inventory)
    retained = sum(item["retained_configurations"] for item in inventory)
    return {"id": "retained-campaign-training-dependence-v1", "status": "descriptive_partial_coverage",
            "additional_evaluated_configurations": evaluated, "retained_daily_configurations": retained,
            "missing_daily_configurations": evaluated - retained, "cost_paths": len(series),
            "previous_292": "Not inspected for daily dependence; no full1100 matrix is claimed",
            "inventory": inventory, "groups": groups,
            "series_receipts": [{key: value for key, value in item.items() if key not in ("returns", "dates")} for item in series],
            "no_fresh_simulations": True, "selection_performed": False, "eligible_for_paper": False,
            "live_orders": False, "telegram_enabled": False,
            "limitations": ["TRAIN paths are adaptive and some were originally selected; this is not independent heldout inference.",
                "Correlation and effective covariance rank do not determine independent trials, adjust p-values or resurrect failed models.",
                "Risk/cost replicas share economic rules and source paths; covariance rank depends on risk scales and the observed window.",
                "Exactly matching windows are separate groups; no nonoverlapping dates, missing compact rows or unknown calendar returns are invented.",
                "Counterfactual doubled costs are scenarios of the same models, not extra strategies.",
                "OHLC/reference execution, missing active marks and source-use restrictions remain unchanged; observed dependence proves neither profit nor payouts."]}


def markdown(value):
    lines = ["# Retained TRAIN campaign dependence", "",
             f"Daily paths are retained for **{value['retained_daily_configurations']}/{value['additional_evaluated_configurations']}** additional configurations; **{value['missing_daily_configurations']}** compact-only configurations cannot enter a correlation matrix.", "",
             "This is a descriptive audit of existing arrays and registered ledger bytes. No new strategy simulation, P&L selection or qualification is performed. The previous292 and missing rows are not assigned invented returns; there is no complete1100 matrix.", "",
             "| Study | Evaluated TRAIN | Retained daily configs | Cost paths |", "|---|---:|---:|---:|"]
    for row in value["inventory"]:
        lines.append(f"|{row['study']}|{row['evaluated_configurations']}|{row['retained_configurations']}|{row.get('retained_cost_paths',0)}|")
    lines += ["", "| Exact calendar | Days | Base configs | Covariance rank: base | Covariance rank: base+doublecost |", "|---|---:|---:|---:|---:|"]
    for group in value["groups"]:
        ranks = ["undefined (zero variance)" if item["effective_covariance_rank"] is None else f"{item['effective_covariance_rank']:.6f}"
                 for item in (group["base"], group["base_plus_double_cost"])]
        lines.append(f"|{group['start']} → {group['end_exclusive']} exclusive|{len(group['calendar_dates'])}|{len(group['base_series_ids'])}|{ranks[0]}|{ranks[1]}|")
    for group in value["groups"]:
        cost = group["cost_twin_correlation_summary"]["median"]
        risk = group["risk_sibling_correlation_summary"]["median"]
        lines += ["", f"{group['start']} window: **{group['base']['positive_variance_paths']}** nonzero-variance base paths, **{group['base']['zero_variance_paths']}** constant paths; **{len(group['risk_siblings'])}** catalogue risk-sibling groups and **{len(group['identical_base_paths'])}** groups of exactly identical observed base-return vectors."]
        if cost is not None:
            lines.append(f"Median base/double-cost Pearson correlation: **{cost:.6f}**; these are scenarios of the same models.")
        if risk is not None:
            lines.append(f"Median risk-sibling Pearson correlation: **{risk:.6f}**. All original paths remain in the matrix; no outcome-based deduplication or profit selection changes the rank.")
    lines += ["", "Effective covariance rank is `trace(C)^2 / trace(C*C)` with sample covariance of daily simple TOTAL-account returns. It measures observed variance concentration and depends on risk size, fees and window. It is not a count of independent strategies/tests, a sample-size estimate, a multiplicity correction or a profitable allocation.", "",
              "Pearson matrices use only identical complete date arrays. Flat days remain exactly as recorded; zero-variance correlations are null. The full2024 crypto primary is kept separate from the90-day FX/goldTRAIN window. No daily returns are recovered from monthly totals. Cost pairs and risk siblings are identified explicitly in JSON.", "",
              "The one crypto daily path is the parent's originally locked TRAIN primary, not a model chosen by this audit. All other crypto/index/pair families retain compact outcome metrics only. FX/gold ledger files supply both actual modeled cost scenarios; those extra paths do not increase the economic trial count.", "",
              *value["limitations"], "",
              "The JSON binds each inspected report and raw/compressed ledger receipt plus daily-array fingerprints. Reproduction requires those original retained inputs; portable receipt files do not substitute raw history or ledgers."]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    root = args.root.resolve()
    inventory, series = collect(root)
    value = summarize(inventory, series)
    value["diagnostic_producers"] = {name: sha(ROOT / name) for name in
        ("scripts/analyze_campaign_dependence.py", "tests/test_campaign_dependence.py", "propdesk/research_campaign.py")}
    output = root / "docs/CAMPAIGN_DEPENDENCE.json"
    output.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    output.with_suffix(".md").write_text(markdown(value))
    print(json.dumps({key: value[key] for key in ("status", "additional_evaluated_configurations", "retained_daily_configurations", "missing_daily_configurations", "cost_paths")}))


if __name__ == "__main__":
    main()
