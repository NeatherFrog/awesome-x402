#!/usr/bin/env python3
"""Preregistered adaptive low-turnover venue-spot study; no orders/alerts."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from propdesk import low_turnover as engine, market, research_lab as lab, research_stats as stats
from scripts import research_broad as first

DIRECTORY = ROOT/"data/low-turnover-research"
OUTPUT = ROOT/"docs/low-turnover-research.json"
MARKDOWN = ROOT/"docs/LOW_TURNOVER_RESEARCH.md"


def write_report(report):
    OUTPUT.write_text(json.dumps(report, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    text = ["# Adaptive low-turnover spot research", "", f"Phase: **{report['phase']}**.", "",
            f"Protocol SHA256: `{report['protocol_sha256']}`.", "",
            "64 fixed parameter variants, four hypothesis families, daily/4h aggregation of the same official two-asset spot archive.", "",
            "This is explicitly adaptive exploratory research:2024/2025 outcomes were inspected in the208-variant predecessor, and2026 calendar/prices overlap other previously viewed studies. No globally blind holdout claim.", "",
            "No live/prop/Telegram qualification. Source archives are CC BY-NC-SA personal non-production research inputs; no commercial redistribution or executable fee tariff is certified.", ""]
    if report.get("reason"):
        text += [report["reason"], ""]
    if report.get("validation"):
        text += ["| Family finalist | Validation return | Double cost | Episodes | Worst DD | Passed research screen |",
                 "| --- | ---: | ---: | ---: | ---: | --- |"]
        variants = {v["id"]: v for v in report["protocol"]["grid"]}
        for row in report["validation"]:
            m = row["metrics"]
            text.append(f"| {variants[row['id']]['family']} | {m['return_pct']:+.4f}% | {row['stress_metrics']['return_pct']:+.4f}% | {m['closed_position_episodes']} | {m['max_drawdown_pct']:.4f}% | {row['passed']} |")
        text += [""]
    if report.get("final"):
        m = report["final"]["metrics"]
        text += [f"Locked final net return: **{m['return_pct']:+.4f}%**; worst intrabar DD **{m['max_drawdown_pct']:.4f}%**; closed episodes **{m['closed_position_episodes']}**; rebalance fills **{m['rebalance_fill_count']}**.", "",
                 f"Strict retrospective qualification: **{report['retrospective_candidate']}**. Filling/rebalancing often does not create independent trade evidence.", ""]
    text += ["Positive retrospective return is not proof of stable future profitability. All failed trials remain in the JSON ledger; no failed signal is pushed to a user.", ""]
    MARKDOWN.write_text("\n".join(text), encoding="utf-8")


def freeze():
    path = DIRECTORY/"protocol.json"
    if path.exists():
        protocol = json.loads(path.read_text())
    else:
        prior = json.loads(first.OUTPUT.read_text())
        first.verify_protocol(prior)
        if prior["phase"] != "completed_no_candidate_final_unopened":
            raise ValueError("Expected preserved completed208-study before adaptive followup")
        producers = ["propdesk/low_turnover.py", "scripts/research_low_turnover.py", "propdesk/research_lab.py", "scripts/research_broad.py", "propdesk/research_stats.py"]
        protocol = {"version": "adaptive-low-turnover-spot-v1", "frozen_at": first.now(),
                    "source": "Same official Binance spot closed-hourly snapshots, exact predecessor input hashes; no source/market substitution",
                    "prior_protocol_sha256": prior["protocol_sha256"], "prior_report_sha256": first.file_hash(first.OUTPUT),
                    "adaptive_scope": "Motivated by observed hourly turnover and cost drag. Training2024 and validation2025 already seen;2026 overlaps other inspected studies. Finalperformance unused in predecessor but not globally blind.64 new variants plus208 prior=272 attempted variants in this sequential venue pool.",
                    "windows": first.WINDOWS, "training_folds": first.FOLDS,
                    "grid": engine.grid(), "family_rules": engine.RULES,
                    "producers": {p: first.file_hash(ROOT/p) for p in producers},
                    "literature": [{"title": "Time series momentum", "authors": "Moskowitz,Ooi,Pedersen", "year": 2012,
                                    "url": "https://www.aqr.com/Insights/Research/Journal-Article/Time-Series-Momentum",
                                    "scope": "Conceptual source; paper monthly1/3/12month futures methodology is not copied hourly. This study uses actual1/3calendar-month spot returns;12month cannot train on2024-only history without unavailable2023 warmup and is excluded before this run."}],
                    "features": "Fullyclosed4h or24h UTC candles. Rolling30day annualizedlogreturnvol and covariance; target weights evaluated previousclosedbar. Calendar-month momentum uses same-asof UTC date shifted1/3calendar-months, clampedday, priorcompleteclose lookup. No hourly reinterpretation of monthly paper rules.",
                    "execution": {"account": 100000, "gross_cap": 1.0, "fees_bps_per_side": 10,
                                  "slippage_bps_per_side": 2, "full_spread_bps": 1, "quantity_step": .000001,
                                  "tariff_status": "Assumed, no executable venue tariff or historical filter verification",
                                  "cash_only": True, "borrow": False, "funding": False,
                                  "rebalance": "Monday00UTC weekly or firstcalendar-day00UTC monthly. Sellreductionsbeforebuyincreases; feeawarecashcap. No intrabarretrospectivefills. No pertradeATRstop: these are risk-scaled allocation hypotheses, not pictured stop-entry setups.",
                                  "boundary": "No finalbarrebalance; liquidate priorpositions atfinalclose timestamp+resolution, labeledsample_boundary",
                                  "precision": "Fractionalstep modeled, venue minnotional/filter not verified",
                                  "risk": "Volatility forecast does not guarantee realized loss cap; gaps/jumps and correlation shifts remain possible. Combinedlowsconservative,notnecessarilysimultaneous."},
                    "selection": {"training": "Netpositive+doublefrictionpositive;>=4completepositionepisodes;DD<=15%;>=2/3fixedfoldspositive;chooseONEperfamily return/max(DD,.25),tiesID.",
                                  "validation": "Only<=4trainfinalists. Positivebase+doublestress;>=2closedepisodes;DD<=12%;Holm-adjusted7dayblocksignflip<=.05 acrosstheentirefixedshortlist;ONEwinnerreturn/DD,tiesID.",
                                  "activity_caveat": "Low research-selection episode thresholds allow measuring long-horizon hypotheses, NOT stableprofit qualification. Strict final activity requirement remains50closedepisodes, not rebalancefillcount. Even positive few-trade performance cannot qualify.",
                                  "lock": "Immutableprimaryselection beforefirst2026performance. No finalfailure winnerreplacement. No survivor means finalunopened.",
                                  "multiplicity": "All64trainingp-values retainedHolmadjusted;272sequentialvariantscount disclosed. Adaptive2025 diagnostics cannot create fresh validation proof."},
                    "strict_final_gates": {"positive_return": True, "double_cost_positive": True, "closed_episodes_minimum": 50,
                                           "days_minimum": 180, "months_minimum": 6, "drawdown_pct_maximum": 10,
                                           "daily_open_to_intrabar_loss_pct_maximum": 2.5,
                                           "mean_daily_ci99_lower_positive": True, "both_halves_positive": True,
                                           "positive_month_maximum_share": .5, "globally_blind": False,
                                           "fresh_forward_paper_required": True, "live_qualified": False, "prop_qualified": False},
                    "inference": {"signflip": "7dayblocks2000resamples one-sided; independent symmetricblock assumption notverified",
                                  "mean_ci": "Circular7daymovingblocks5000resamples99%; conditional approximate, adaptivehistorydoesnotprovefuture", "seed": 20261003},
                    "orders": "UserrequiresONEwell-supportedstrategybeforeTelegram. No Telegram, no exchangeorder, no deposit/payout."}
        first.immutable_write(path, protocol)
    report = {"phase": "frozen_before_outcomes", "protocol": protocol, "protocol_sha256": lab.digest(protocol),
              "retrospective_candidate": False, "live_qualified": False, "prop_qualified": False}
    if not OUTPUT.exists():
        write_report(report)
    return report


def verify(report):
    if lab.digest(report["protocol"]) != report["protocol_sha256"] or report["protocol"]["grid"] != engine.grid():
        raise ValueError("Immutable low-turnover protocol/grid changed")
    for path, expected in report["protocol"]["producers"].items():
        if first.file_hash(ROOT/path) != expected:
            raise ValueError("Frozenproducerchanged: "+path)


def gates(result, stress, minimum_episodes, maximum_dd):
    m = result["metrics"]
    return {"positive_costed_return": m["return_pct"] > 0,
            "positive_double_friction": stress["metrics"]["return_pct"] > 0,
            "minimum_complete_episodes": m["closed_position_episodes"] >= minimum_episodes,
            "drawdown_limit": m["max_drawdown_pct"] <= maximum_dd}


def compact(result):
    return {k: result[k] for k in ("metrics", "daily_returns", "start", "end")}


def run():
    report = freeze()
    verify(report)
    prior = json.loads(first.OUTPUT.read_text())
    if first.file_hash(first.OUTPUT) != report["protocol"]["prior_report_sha256"]:
        raise ValueError("Predecessoroutcomes changed")
    inputs = prior["inputs"]
    for item in inputs["csv"].values():
        if first.file_hash(item["path"]) != item["sha256"]:
            raise ValueError("Originalvenueinputchanged")
    if first.file_hash(inputs["manifest_path"]) != inputs["manifest_sha256"]:
        raise ValueError("Originalvenuemanifestchanged")
    first.immutable_write(DIRECTORY/"input_lock.json", inputs)
    datasets = {s: first.read_csv(item["path"]) for s, item in inputs["csv"].items()}
    features = {hours: engine.Features(datasets, hours) for hours in (4, 24)}
    report["inputs"] = inputs
    baseline_inputs = {s: lab.FeatureCache(rows) for s, rows in datasets.items()}
    report["training_benchmark"] = first.buy_hold_benchmark(baseline_inputs, *first.WINDOWS["training"])
    report["validation_benchmark"] = first.buy_hold_benchmark(baseline_inputs, *first.WINDOWS["validation"])
    training, pvalues, shortlist = [], [], []
    variants = {v["id"]: v for v in report["protocol"]["grid"]}
    for index, variant in enumerate(variants.values()):
        feature = features[variant["resolution_hours"]]
        obs = engine.target_weights(feature, variant)
        result = engine.simulate(feature, obs, *first.WINDOWS["training"])
        stress = engine.simulate(feature, obs, *first.WINDOWS["training"], cost_multiplier=2)
        folds = [engine.simulate(feature, obs, *window)["metrics"] for window in first.FOLDS]
        check = gates(result, stress, 4, 15)
        check["two_of_three_positive_folds"] = sum(f["return_pct"] > 0 for f in folds) >= 2
        pvalue = stats.block_signflip_pvalue([r["return"] for r in result["daily_returns"]], block_length=7, samples=2000, seed=20261003+index)
        pvalues.append(pvalue["p_value"] if pvalue["p_value"] is not None else 1)
        training.append({"id": variant["id"], "variant": variant, "metrics": result["metrics"],
                         "stress_metrics": stress["metrics"], "folds": folds, "gates": check,
                         "passed": all(check.values()), "score": lab.selection_score(result), "signflip": pvalue,
                         "benchmark_relationship": first.benchmark_relationship(result, report["training_benchmark"])})
        print(f"Low-turnovertraining {index+1}/64 {variant['id']} {result['metrics']['return_pct']:+.4f}%", flush=True)
    for row, probability in zip(training, stats.holm_adjust(pvalues)):
        row["holm_adjusted_training_p"] = probability
    for family in sorted(engine.RULES):
        survivors = sorted([r for r in training if r["passed"] and r["variant"]["family"] == family], key=lambda r: (-r["score"], r["id"]))
        if survivors:
            shortlist.append(survivors[0]["id"])
    training_lock = {"protocol_sha256": report["protocol_sha256"], "inputs_sha256": lab.digest(inputs),
                     "training_sha256": lab.digest(training), "shortlist": shortlist}
    first.immutable_write(DIRECTORY/"training_selection.json", training_lock)
    report.update(phase="training_complete", training=training, shortlist=shortlist,
                  training_lock_sha256=lab.digest(training_lock))
    write_report(report)
    validation, pvalues = [], []
    for index, identifier in enumerate(shortlist):
        variant = variants[identifier]
        feature = features[variant["resolution_hours"]]
        obs = engine.target_weights(feature, variant)
        result = engine.simulate(feature, obs, *first.WINDOWS["validation"])
        stress = engine.simulate(feature, obs, *first.WINDOWS["validation"], cost_multiplier=2)
        pvalue = stats.block_signflip_pvalue([r["return"] for r in result["daily_returns"]], block_length=7, samples=2000, seed=20261003+1000+index)
        pvalues.append(pvalue["p_value"] if pvalue["p_value"] is not None else 1)
        validation.append({"id": identifier, **compact(result), "stress_metrics": stress["metrics"],
                           "score": lab.selection_score(result), "gates": gates(result, stress, 2, 12), "signflip": pvalue,
                           "benchmark_relationship": first.benchmark_relationship(result, report["validation_benchmark"])})
    for row, probability in zip(validation, stats.holm_adjust(pvalues)):
        row["holm_adjusted_validation_p"] = probability
        row["gates"]["holm_signflip_05"] = probability <= .05
        row["passed"] = all(row["gates"].values())
    passing = sorted([r for r in validation if r["passed"]], key=lambda r: (-r["score"], r["id"]))
    selected = passing[0]["id"] if passing else None
    lock = {"protocol_sha256": report["protocol_sha256"], "training_lock_sha256": lab.digest(training_lock),
            "validation_sha256": lab.digest(validation), "selected": selected, "locked_at": first.now()}
    path = DIRECTORY/"validation_selection.json"
    if path.exists():
        lock["locked_at"] = json.loads(path.read_text())["locked_at"]
    first.immutable_write(path, lock)
    report.update(phase="validation_complete", validation=validation, selected=selected,
                  validation_lock=lock, validation_lock_sha256=lab.digest(lock))
    write_report(report)
    if selected is None:
        report.update(phase="completed_no_candidate_final_unopened", reason="No low-turnover family finalist passed the fixed exploratory validation screen; no2026performance computed and no substitute selected.")
        write_report(report)
        return report
    variant = variants[selected]
    feature = features[variant["resolution_hours"]]
    obs = engine.target_weights(feature, variant)
    result = engine.simulate(feature, obs, *first.WINDOWS["final"])
    stress = engine.simulate(feature, obs, *first.WINDOWS["final"], cost_multiplier=2)
    halves = [engine.simulate(feature, obs, "2026-01-01", "2026-05-17"), engine.simulate(feature, obs, "2026-05-17", "2026-10-01")]
    check = gates(result, stress, 50, 10)
    ci = stats.bootstrap_mean_ci([r["return"] for r in result["daily_returns"]], confidence=.99, samples=5000, block_length=7, seed=20261003+2000)
    check.update(ci99_lower_positive=ci["lower"] > 0, minimum180days=len(result["daily_returns"]) >= 180,
                 minimum6months=len({r["date"][:7] for r in result["daily_returns"]}) >= 6,
                 both_halves_positive=all(r["metrics"]["return_pct"] > 0 for r in halves))
    monthly = {}
    for row in result["daily_returns"]:
        month = row["date"][:7]
        monthly[month] = monthly.get(month, 1)*(1+row["return"])
    positive = [max(x-1, 0) for x in monthly.values()]
    share = max(positive)/sum(positive) if sum(positive) else None
    check["no_dominant_month"] = share is not None and share <= .5
    opening, daily_loss = {}, 0.0
    for row in result["equity_curve"]:
        day = row["time"][:10]
        opening.setdefault(day, row["opening_equity"])
        daily_loss = max(daily_loss, (opening[day]-row["worst_equity"])/opening[day]*100)
    check["daily_loss_limit"] = daily_loss <= 2.5
    benchmark = first.buy_hold_benchmark(baseline_inputs, *first.WINDOWS["final"])
    result.update(stress_metrics=stress["metrics"], halves=[r["metrics"] for r in halves], mean_daily_ci99=ci,
                  gates=check, monthly_returns={k: v-1 for k, v in monthly.items()},
                  largest_positive_month_share=share, maximum_daily_intrabar_loss_pct=daily_loss,
                  benchmark=benchmark, benchmark_relationship=first.benchmark_relationship(result, benchmark))
    first.immutable_write(DIRECTORY/"final_result.json", result)
    report.update(phase="completed_locked_final", final=result, retrospective_candidate=all(check.values()),
                  reason="One validation-locked low-turnover research primary evaluated. Adaptive inspected history plus limited position episodes cannot establish stablefutureprofit; prospectivepaper and realexecution costs remain required.")
    write_report(report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--freeze", action="store_true")
    args = parser.parse_args()
    report = run() if args.run else freeze()
    print(json.dumps({"phase": report["phase"], "protocol_sha256": report["protocol_sha256"], "variants": len(report["protocol"]["grid"]), "selected": report.get("selected"), "retrospective_candidate": report.get("retrospective_candidate", False)}))


if __name__ == "__main__":
    main()
