#!/usr/bin/env python3
"""Freeze and execute the bounded venue-spot research protocol.

Uses local, independently obtained closed-bar venue CSVs. Never silently
downloads another source, changes the market, or substitutes a failed winner.
No exchange or Telegram orders/messages are produced by this script.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from propdesk import market, research_lab as lab

DIRECTORY = ROOT / "data/broad-research"
OUTPUT = ROOT / "docs/broad-research.json"
MARKDOWN = ROOT / "docs/BROAD_RESEARCH.md"
WINDOWS = {"training": ["2024-01-01", "2025-01-01"],
           "validation": ["2025-01-01", "2026-01-01"],
           "final": ["2026-01-01", "2026-10-01"]}
FOLDS = [["2024-02-01", "2024-05-01"], ["2024-05-01", "2024-09-01"],
         ["2024-09-01", "2025-01-01"]]


def now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def immutable_write(path, value):
    text = lab.canonical(value)+"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_text(encoding="utf-8") != text:
            raise ValueError(f"Refusing to change immutable research artifact: {path}")
    else:
        with path.open("x", encoding="utf-8") as stream:
            stream.write(text)


def write_report(report, output=OUTPUT, markdown=MARKDOWN):
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".tmp")
    temporary.write_text(json.dumps(report, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    temporary.replace(output)
    lines = ["# Bounded broad venue-spot research", "", f"Status: **{report['phase']}**.", "",
             "208 preregistered parameter variants across nine hypothesis families; these are correlated variants, not 208 independent strategies.", "",
             f"Frozen protocol SHA256: `{report['protocol_sha256']}`.", "",
             "BTCUSDT and ETHUSDT spot long/cash only. Training: 2024; validation: 2025; final: January–September 2026.", "",
             "Fees10bps/side + slippage2bps/side + full spread1bp are conservative modeling assumptions, not verified executable venue tariffs. Fractional quantity precision is modeled, not a verified historical filter.", "",
             "No funding, borrowing, short positions, leverage, prop execution, withdrawals or Telegram messages. Rejected experiments remain in the research record; they are not user-facing trade alerts.", ""]
    if report.get("reason"):
        lines += [report["reason"], ""]
    if report.get("training"):
        lines += [f"Training variants evaluated: {len(report['training'])}. Bounded family shortlist: {len(report.get('shortlist', []))}.", ""]
    if "selected" in report:
        lines += [f"Locked candidate: `{report['selected']}`." if report["selected"] else "**No candidate passed the preregistered selection gates.**", ""]
    if report.get("final"):
        m = report["final"]["metrics"]
        lines += [f"Final costed return: {m['return_pct']:.4f}%; worst modeled intrabar drawdown: {m['max_drawdown_pct']:.4f}%; trades: {m['trade_count']}.", "",
                  f"Retrospective qualification: **{report.get('retrospective_candidate', False)}**. Live/prop qualification: **false**. Future paper observations remain required.", ""]
    lines += ["The final candidate cannot be replaced after final outcomes are opened. Historical profitability alone is not proof of stable future profit. No data-source substitution is permitted.", ""]
    markdown.write_text("\n".join(lines), encoding="utf-8")


def freeze(directory=DIRECTORY, output=OUTPUT, markdown=MARKDOWN):
    path = directory/"protocol.json"
    if path.exists():
        protocol = json.loads(path.read_text(encoding="utf-8"))
    else:
        producer_paths = ["propdesk/research_lab.py", "scripts/research_broad.py", "propdesk/research_stats.py"]
        missing = [p for p in producer_paths if not (ROOT/p).exists()]
        if missing:
            raise ValueError("Statistical producer must exist before protocol freeze: "+", ".join(missing))
        protocol = {"version": "bounded-venue-spot-v1", "frozen_at": now(),
                    "source": "Official Binance spot closed-hourly OHLCV; downloaded independently, immutable receipts required",
                    "symbols": ["BTCUSDT", "ETHUSDT"], "interval": "1h", "windows": WINDOWS,
                    "training_folds": FOLDS, "grid": lab.make_grid(), "family_rules": lab.FAMILY_RULES,
                    "producers": {p: file_hash(ROOT/p) for p in producer_paths},
                    "causality": "At bar i open use only decisions from i-1 closed bar. Prior-window prices warm indicators; all segments start cash. Training-only feature/strategy correlations never inspect validation/final.",
                    "execution": {"account": 100000, "equal_asset_cash": 50000, "risk_per_asset": 250,
                                  "risk_note": "Fixed absolute risk budget; realized losses can exceed it on fees/gaps. Spot exposure cash-capped at1x.",
                                  "fee_bps_per_side": 10, "slip_bps_per_side": 2, "full_spread_bps": 1,
                                  "double_friction_stress": True, "quantity_step": .000001,
                                  "cost_status": "Assumed, not verified executable account tariffs or historical venue filters",
                                  "stop": "Fixed prior ATR14 multiple below adverse entry fill. Opening gap stop precedes known indicator/time exit, otherwise low-touch stop. Same-entry-bar protection; no same-bar reentry.",
                                  "boundary": "No final-bar new entry; existing positions force-liquidated at final close, labeled hypothetical sample_boundary.",
                                  "worst_equity": "Sum of per-asset candle lows is conservative and need not be simultaneous. End-close marks do not assert exact intrabar paths.",
                                  "financing": "No funding/borrow/leverage for cash spot; no interest on idle cash"},
                    "selection": {"training": "Positive net and doubled-friction return, >=40 trades, worst drawdown<=15%, >=2/3 chronological training fold returns positive; choose one per family by return/max(drawdown,.25), ties lexicographic ID.",
                                  "validation": "At most nine train-only finalists, positive net and doubled-friction return, >=20 trades, drawdown<=12%; Holm-adjusted block-signflip p<=.05 across the entire fixed validation shortlist; choose ONE by same score, ties lexicographic ID.",
                                  "training_multiplicity": "All208 training block-signflip pvalues Holm-adjusted and retained descriptively; final qualification relies on locked untouched final, not training pvalues.",
                                  "locking": "Persist validation_selection.json hash before first final simulation. If no survivor, never open final performance. No winner substitution after final failure.",
                                  "correlations": "All candidate daily-return correlation summaries and feature/forward-return correlations TRAIN ONLY; descriptive dependence-aware caveat, no independent-trial interpretation."},
                    "final_gates": {"return_positive": True, "min_trades": 50, "max_drawdown_pct": 10,
                                    "minimum_days": 180, "minimum_calendar_months": 6,
                                    "block_mean_ci99_lower_positive": True, "double_friction_positive": True,
                                    "both_halves_positive": True, "largest_positive_month_share_max": .5,
                                    "max_daily_intrabar_drawdown_pct": 2.5,
                                    "forward_paper_required": True, "live_qualified": False, "prop_qualified": False},
                    "inference": {"bootstrap": "Circular moving blocks of7 daily returns, 5000 resamples,99% CI", "block_signflip": "7-day nonoverlapping blocks,2000 random signs,one-sided; independent symmetric block-sign assumption", "seed": 20261002},
                    "orders": "Research only. User requests one qualified strategy before Telegram implementation. No messages or real money execution."}
        immutable_write(path, protocol)
    report = {"phase": "frozen_awaiting_venue_data", "protocol": protocol,
              "protocol_sha256": lab.digest(protocol), "retrospective_candidate": False,
              "live_qualified": False, "prop_qualified": False,
              "reason": "No venue performance has been read or computed by this protocol yet."}
    if not output.exists():
        write_report(report, output, markdown)
    return report


def read_csv(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        fields = {str(x).strip().lower(): x for x in reader.fieldnames or []}
        timefield = next((fields[k] for k in ("time", "timestamp", "open_time") if k in fields), None)
        if timefield is None:
            raise ValueError("Explicit UTC timestamp/open_time/time column required")
        bars = []
        for row in reader:
            stamp = row[timefield]
            if stamp.isdigit():
                numeric = int(stamp)
                divisor = 1_000_000 if numeric > 100_000_000_000_000 else 1000 if numeric > 100_000_000_000 else 1
                stamp = datetime.fromtimestamp(numeric/divisor, timezone.utc).isoformat().replace("+00:00", "Z")
            bars.append({"time": stamp, **{key: float(row[fields[key]]) for key in ("open", "high", "low", "close", "volume")}})
    normalized = market.validate_bars(bars, max_bars=100_000)
    for first, second in zip(normalized, normalized[1:]):
        if (market.utc_datetime(second["time"])-market.utc_datetime(first["time"])).total_seconds() != 3600:
            raise ValueError("Official one-hour dataset contains gaps; no silent imputation or date removal")
    if normalized[0]["time"] != "2024-01-01T00:00:00Z" or normalized[-1]["time"] != "2026-09-30T23:00:00Z":
        raise ValueError("Complete frozen2024-Jan through2026-Sep hourly coverage required")
    return normalized


def verify_protocol(report):
    p = report["protocol"]
    if lab.digest(p) != report["protocol_sha256"]:
        raise ValueError("Protocol hash changed")
    if p["grid"] != lab.make_grid():
        raise ValueError("Registered grid changed")
    for path, expected in p["producers"].items():
        if file_hash(ROOT/path) != expected:
            raise ValueError("Producer changed after freeze: "+path)


def correlation(a, b):
    if len(a) != len(b) or len(a) < 3:
        return None
    ma, mb = sum(a)/len(a), sum(b)/len(b)
    aa, bb = sum((x-ma)**2 for x in a), sum((x-mb)**2 for x in b)
    if aa <= 0 or bb <= 0:
        return None
    return sum((x-ma)*(y-mb) for x, y in zip(a, b))/math.sqrt(aa*bb)


def training_correlations(caches, returns):
    pairs, largest = [], []
    ids = sorted(returns)
    for index, left in enumerate(ids):
        for right in ids[index+1:]:
            coefficient = correlation(returns[left], returns[right])
            if coefficient is not None:
                pairs.append(coefficient)
                largest.append({"left": left, "right": right, "correlation": coefficient})
    largest.sort(key=lambda row: (-abs(row["correlation"]), row["left"], row["right"]))
    features = []
    for symbol, cache in caches.items():
        c = cache.close
        sma, atr, rsi, vol = cache.get("mean", 200), cache.get("atr", 14), cache.get("rsi", 14), cache.get("volume_mean", 24)
        kinds = {"log_return1": cache.returns, "rsi14": rsi,
                 "distance_sma200": [c[i]/x-1 if x else None for i, x in enumerate(sma)],
                 "atr14_fraction": [x/c[i] if x else None for i, x in enumerate(atr)],
                 "volume_ratio24": [cache.volume[i]/x if x else None for i, x in enumerate(vol)],
                 "momentum24": [c[i]/c[i-24]-1 if i >= 24 else None for i in range(len(c))]}
        for name, values in kinds.items():
            for horizon in (1, 6, 24):
                indices = [i for i, x in enumerate(values) if x is not None and i+horizon < len(c)
                           and "2024-01-01" <= cache.bars[i]["time"][:10] < "2025-01-01"
                           and cache.bars[i+horizon]["time"][:10] < "2025-01-01"]
                x = [values[i] for i in indices]
                y = [math.log(c[i+horizon]/c[i]) for i in indices]
                features.append({"symbol": symbol, "feature": name, "forward_hours": horizon,
                                 "observations": len(x), "correlation": correlation(x, y)})
    return {"scope": "Training2024only; descriptive, dependent overlapping observations; no causal or significance claim",
            "candidate_pair_count": len(pairs), "mean_pair_correlation": sum(pairs)/len(pairs) if pairs else None,
            "largest_absolute_candidate_correlations": largest[:30], "feature_forward_correlations": features}


def buy_hold_benchmark(caches, start_date, end_date, *, cost_multiplier=1):
    """Costed equal-cash spot baseline, independently started at each window.

    Descriptive buy/hold is not risk-matched and does not establish statistical
    alpha. Inputs and costs exactly match the strategy's modeled spot universe.
    """
    symbols = sorted(caches)
    indices = [i for i, bar in enumerate(caches[symbols[0]].bars) if start_date <= bar["time"][:10] < end_date]
    fee, adverse = .001*cost_multiplier, .00025*cost_multiplier
    holdings = {}
    for symbol in symbols:
        price = caches[symbol].bars[indices[0]]["open"]*(1+adverse)
        quantity = math.floor((50_000/(price*(1+fee)))/.000001)*.000001
        holdings[symbol] = quantity, 50_000-quantity*price*(1+fee)
    curve = []
    for i in indices:
        equity = opening = worst = notional = 0
        for symbol in symbols:
            bar, (quantity, cash) = caches[symbol].bars[i], holdings[symbol]
            mark = quantity*bar["close"]
            equity += cash+mark*(1-adverse)*(1-fee) if i == indices[-1] else cash+mark
            opening += cash+quantity*bar["open"]
            worst += cash+quantity*bar["low"]
            notional += mark if i != indices[-1] else 0
        curve.append({"time": caches[symbols[0]].bars[i]["time"], "equity": equity,
                      "opening_equity": opening, "worst_equity": min(worst, equity), "notional": notional})
    return {"metrics": lab.metrics(curve, [], 100_000), "daily_returns": lab.daily_returns(curve),
            "scope": "Costed equal-cash buy/hold; baseline not risk-matched, metrics trades/fees are omitted rather than simulated strategy trades"}


def benchmark_relationship(result, benchmark):
    x = [r["return"] for r in benchmark["daily_returns"]]
    y = [r["return"] for r in result["daily_returns"]]
    mx, my = sum(x)/len(x), sum(y)/len(y)
    variance = sum((value-mx)**2 for value in x)
    beta = sum((a-mx)*(b-my) for a, b in zip(x, y))/variance if variance else None
    return {"net_total_return_difference_pct": result["metrics"]["return_pct"]-benchmark["metrics"]["return_pct"],
            "daily_correlation": correlation(x, y), "descriptive_daily_ols_beta": beta,
            "descriptive_daily_ols_intercept": my-beta*mx if beta is not None else None,
            "scope": "Descriptive same-window relationship; no risk-matched alpha or significance assertion"}


def run(paths, manifest, directory=DIRECTORY, output=OUTPUT, markdown=MARKDOWN):
    from propdesk import research_stats as stats
    report = freeze(directory, output, markdown)
    verify_protocol(report)
    if set(paths) != {"BTCUSDT", "ETHUSDT"}:
        raise ValueError("Both preregistered spot symbol paths required")
    if not manifest or not Path(manifest).is_file():
        raise ValueError("Independent venue provenance manifest required before prices are read")
    receipt = json.loads(Path(manifest).read_text(encoding="utf-8"))
    # Exact source proof cannot be inferred from prices or from arbitrary filenames.
    manifesttext = lab.canonical(receipt).lower()
    if "binance" not in manifesttext or not any(x in manifesttext for x in ("data.binance.vision", "api.binance.com")):
        raise ValueError("Manifest does not identify the registered official venue source")
    inputs = {"manifest_path": str(Path(manifest).resolve()), "manifest_sha256": file_hash(manifest),
              "csv": {s: {"path": str(Path(p).resolve()), "sha256": file_hash(p)} for s, p in paths.items()}}
    receipts = {row.get("symbol"): row for row in receipt.get("datasets", []) if row.get("interval") == "1h"}
    for symbol, item in inputs["csv"].items():
        dataset = receipts.get(symbol)
        if not dataset or dataset.get("csv_sha256") != item["sha256"]:
            raise ValueError("Venue manifest does not match exact symbol CSV SHA256: "+symbol)
        if not dataset.get("requested_calendar_complete") or not dataset.get("complete_calendar") or dataset.get("limited_acquisition"):
            raise ValueError("Venue provenance reports incomplete or limited requested calendar")
        if not dataset.get("sources") or any(not str(s.get("source_url", "")).startswith("https://data.binance.vision/data/spot/") for s in dataset["sources"]):
            raise ValueError("Every input source must be the frozen official spot archive")
    immutable_write(directory/"input_lock.json", inputs)
    report["inputs"] = inputs
    # Loading all prices permits causal feature warmup, but future observations are
    # never used in training features, decisions, correlations or selection outcomes.
    caches = {s: lab.FeatureCache(read_csv(p)) for s, p in paths.items()}
    for symbol, cache in caches.items():
        if market.data_fingerprint(cache.bars) != receipts[symbol].get("data_fingerprint"):
            raise ValueError("Canonical venue price fingerprint mismatch: "+symbol)
    clocks = [[b["time"] for b in caches[s].bars] for s in sorted(caches)]
    if clocks[0] != clocks[1]:
        raise ValueError("Venue BTC/ETH clocks differ")
    grid = report["protocol"]["grid"]
    training, candidate_returns, shortlist = [], {}, []
    train_ps = []
    for index, variant in enumerate(grid):
        obs = {s: lab.decisions(cache, variant) for s, cache in caches.items()}
        result = lab.portfolio(caches, obs, variant, *WINDOWS["training"], keep_details=False)
        stress = lab.portfolio(caches, obs, variant, *WINDOWS["training"], cost_multiplier=2, keep_details=False)
        folds = [lab.portfolio(caches, obs, variant, *window, keep_details=False)["metrics"] for window in FOLDS]
        gates = lab.window_gates(result, stress, trades=40, drawdown=15)
        gates["two_of_three_positive_folds"] = sum(f["return_pct"] > 0 for f in folds) >= 2
        daily = [x["return"] for x in result["daily_returns"]]
        candidate_returns[variant["id"]] = daily
        pvalue = stats.block_signflip_pvalue(daily, block_length=7, samples=2000, seed=20261002+index)
        train_ps.append(pvalue["p_value"] if pvalue["p_value"] is not None else 1.0)
        row = {"id": variant["id"], "variant": variant, "metrics": result["metrics"],
               "stress_metrics": stress["metrics"], "folds": folds, "gates": gates,
               "passed": all(gates.values()), "score": lab.selection_score(result), "signflip": pvalue}
        training.append(row)
        print(f"Training {index+1}/{len(grid)} {variant['id']} return={result['metrics']['return_pct']:.3f}%", flush=True)
    adjusted = stats.holm_adjust(train_ps)
    for row, pvalue in zip(training, adjusted):
        row["holm_adjusted_training_p"] = pvalue
    for family in sorted(lab.FAMILY_RULES):
        passing = [r for r in training if r["passed"] and r["variant"]["family"] == family]
        passing.sort(key=lambda r: (-r["score"], r["id"]))
        if passing:
            shortlist.append(passing[0]["id"])
    report.update(phase="training_complete", training=training, shortlist=shortlist,
                  correlations=training_correlations(caches, candidate_returns),
                  training_benchmark=buy_hold_benchmark(caches, *WINDOWS["training"]))
    training_lock = {"protocol_sha256": report["protocol_sha256"], "inputs_sha256": lab.digest(inputs),
                     "training_results_sha256": lab.digest(training), "shortlist": shortlist}
    immutable_write(directory/"training_selection.json", training_lock)
    report["training_lock_sha256"] = lab.digest(training_lock)
    write_report(report, output, markdown)
    validations, val_ps = [], []
    variants = {v["id"]: v for v in grid}
    for index, identifier in enumerate(shortlist):
        variant = variants[identifier]
        obs = {s: lab.decisions(cache, variant) for s, cache in caches.items()}
        result = lab.portfolio(caches, obs, variant, *WINDOWS["validation"], keep_details=False)
        stress = lab.portfolio(caches, obs, variant, *WINDOWS["validation"], cost_multiplier=2, keep_details=False)
        gates = lab.window_gates(result, stress)
        pvalue = stats.block_signflip_pvalue([x["return"] for x in result["daily_returns"]], block_length=7, samples=2000, seed=20261002+1000+index)
        val_ps.append(pvalue["p_value"] if pvalue["p_value"] is not None else 1.0)
        validations.append({"id": identifier, "metrics": result["metrics"], "stress_metrics": stress["metrics"],
                            "daily_returns": result["daily_returns"], "gates": gates,
                            "score": lab.selection_score(result), "signflip": pvalue})
    for row, adjusted in zip(validations, stats.holm_adjust(val_ps)):
        row["holm_adjusted_validation_p"] = adjusted
        row["gates"]["holm_block_signflip_05"] = adjusted <= .05
        row["passed"] = all(row["gates"].values())
    survivors = sorted([row for row in validations if row["passed"]], key=lambda row: (-row["score"], row["id"]))
    selected = survivors[0]["id"] if survivors else None
    lock = {"protocol_sha256": report["protocol_sha256"], "training_lock_sha256": lab.digest(training_lock),
            "validation_results_sha256": lab.digest(validations), "selected": selected, "locked_at": now()}
    # Lock must precede first final simulation. Reruns retain the original clock.
    lockpath = directory/"validation_selection.json"
    if lockpath.exists():
        previous = json.loads(lockpath.read_text(encoding="utf-8"))
        lock["locked_at"] = previous["locked_at"]
    immutable_write(lockpath, lock)
    report.update(phase="validation_complete", validation=validations, selected=selected,
                  validation_lock=lock, validation_lock_sha256=lab.digest(lock))
    write_report(report, output, markdown)
    if selected is None:
        report.update(phase="completed_no_candidate_final_unopened",
                      reason="No train-selected family finalist passed the frozen validation gates. Final2026 performance remains unopened; no winner replacement or source substitution.")
        write_report(report, output, markdown)
        return report
    variant = variants[selected]
    obs = {s: lab.decisions(cache, variant) for s, cache in caches.items()}
    result = lab.portfolio(caches, obs, variant, *WINDOWS["final"])
    benchmark = buy_hold_benchmark(caches, *WINDOWS["final"])
    stress = lab.portfolio(caches, obs, variant, *WINDOWS["final"], cost_multiplier=2, keep_details=False)
    halves = [lab.portfolio(caches, obs, variant, "2026-01-01", "2026-05-17", keep_details=False),
              lab.portfolio(caches, obs, variant, "2026-05-17", "2026-10-01", keep_details=False)]
    ci = stats.bootstrap_mean_ci([x["return"] for x in result["daily_returns"]], confidence=.99, samples=5000, block_length=7, seed=20261002+2000)
    gates = lab.window_gates(result, stress, trades=50, drawdown=10)
    gates.update(ci99_lower_positive=ci["lower"] > 0,
                 minimum180days=len(result["daily_returns"]) >= 180,
                 minimum6months=len({x["date"][:7] for x in result["daily_returns"]}) >= 6,
                 both_halves_positive=all(x["metrics"]["return_pct"] > 0 for x in halves))
    monthly = {}
    for row in result["daily_returns"]:
        month = row["date"][:7]
        monthly[month] = monthly.get(month, 1)*(1+row["return"])
    positive = [max(value-1, 0) for value in monthly.values()]
    share = max(positive)/sum(positive) if sum(positive) else None
    gates["positive_month_not_dominant"] = share is not None and share <= .5
    daily_open, worst_daily = {}, 0.0
    for row in result["equity_curve"]:
        day = row["time"][:10]
        daily_open.setdefault(day, row["opening_equity"])
        worst_daily = max(worst_daily, (daily_open[day]-row["worst_equity"])/daily_open[day]*100)
    gates["maximum_daily_intrabar_drawdown"] = worst_daily <= 2.5
    result.update(stress_metrics=stress["metrics"], halves=[x["metrics"] for x in halves],
                  daily_mean_ci99=ci, gates=gates, monthly_returns={k: v-1 for k, v in monthly.items()},
                  largest_positive_month_share=share, max_daily_intrabar_drawdown_pct=worst_daily,
                  benchmark=benchmark, benchmark_relationship=benchmark_relationship(result, benchmark))
    report.update(phase="completed_locked_final", final=result,
                  retrospective_candidate=all(gates.values()),
                  reason="Exactly one validation-locked candidate evaluated on final2026; live and prop remain disabled pending prospective paper evidence and actual venue execution/cost verification.")
    immutable_write(directory/"final_result.json", result)
    write_report(report, output, markdown)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze", action="store_true")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--data", action="append", default=[], help="SYMBOL=/absolute/CSV")
    parser.add_argument("--manifest", help="Official venue download receipt")
    args = parser.parse_args()
    if args.run:
        paths = dict(item.split("=", 1) for item in args.data)
        report = run(paths, args.manifest)
    else:
        report = freeze()
    print(json.dumps({"phase": report["phase"], "protocol_sha256": report["protocol_sha256"], "variants": len(report["protocol"]["grid"]), "selected": report.get("selected"), "retrospective_candidate": report.get("retrospective_candidate", False)}))


if __name__ == "__main__":
    main()
