#!/usr/bin/env python3
"""A predeclared two-stage archive experiment, not a live signal scanner.

Asset and parameter ranking use only each asset's chronological training
prefix. The shortlist is written to disk before its final holdouts are tested.
There is no fallback asset, strategy or parameter when a holdout fails.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import random
import statistics
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
if str(REPOSITORY) not in sys.path:
    sys.path.insert(0, str(REPOSITORY))

from propdesk import backtest, market, strategies  # noqa: E402

SOURCE_COMMIT = "0c447c47b757ad74edecab31f0d72f849d2e67c2"
SOURCE_SHA256 = "6aea253cd19de60b568143991aaf1fa482456565c389205658d236e595e716cf"
SOURCE_URL = f"https://github.com/plotly/datasets/blob/{SOURCE_COMMIT}/all_stocks_5yr.csv"
PREVIOUSLY_EXAMINED = ("AAPL", "JPM", "MSFT", "XOM")


@dataclass(frozen=True)
class Protocol:
    version: str = "archive-train-only-v1"
    window_start: str = "2015-01-01"
    window_end: str = "2018-02-07"
    minimum_bars: int = 750
    train_fraction: float = 0.6
    shortlist_size: int = 5
    gap_threshold: float = 0.4
    minimum_train_trades: int = 12
    minimum_walk_forward_trades: int = 12
    minimum_walk_forward_positive_fraction: float = 2 / 3
    minimum_training_profit_factor: float = 1.2
    maximum_training_drawdown_pct: float = 8.0
    account_size: float = 100000.0
    risk_pct: float = 0.25
    fee_bps: float = 2.0
    slippage_bps: float = 1.0
    spread_bps: float = 1.0
    max_leverage: float = 2.0
    quantity_step: float = 1.0
    contract_multiplier: float = 1.0
    bootstrap_resamples: int = 5000
    excluded_symbols: tuple = PREVIOUSLY_EXAMINED
    max_assets: int | None = None


def _fingerprint(value) -> str:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(text.encode()).hexdigest()


def source_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_archive(path: Path, protocol: Protocol) -> dict[str, list[dict]]:
    """Load date-labelled rows without discarding future rows by their returns.

    Dates and bar counts establish availability. Numeric validation and gap
    checks for selection happen on the training prefix only. A selected asset
    with an invalid holdout is reported invalid and receives no replacement.
    """
    universe = {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"date", "open", "high", "low", "close", "volume", "Name"}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise ValueError("Archive requires date,open,high,low,close,volume,Name columns")
        for row in reader:
            if None in row or any(row[key] is None for key in required):
                raise ValueError(f"Malformed source row at line {reader.line_num}")
            stamp = row["date"].strip()
            try:
                parsed = date.fromisoformat(stamp)
            except ValueError as exc:
                raise ValueError(f"Malformed archive date at line {reader.line_num}") from exc
            if parsed.isoformat() != stamp:
                raise ValueError(f"Ambiguous archive date at line {reader.line_num}")
            if not protocol.window_start <= stamp <= protocol.window_end:
                continue
            symbol = row["Name"].strip().upper()
            if not symbol or len(symbol) > 40:
                raise ValueError(f"Malformed symbol at line {reader.line_num}")
            universe.setdefault(symbol, []).append({"time": stamp + "T00:00:00Z", **{key: row[key].strip() for key in ("open", "high", "low", "close", "volume")}})
    return universe


def price_gap_flags(bars: list[dict], threshold: float, *, start: int = 1) -> list[dict]:
    flags = []
    for index in range(max(1, start), len(bars)):
        previous = bars[index - 1]["close"]
        opening_gap = bars[index]["open"] / previous - 1
        closing_gap = bars[index]["close"] / previous - 1
        if max(abs(opening_gap), abs(closing_gap)) > threshold:
            flags.append({"time": bars[index]["time"], "opening_change_pct": round(opening_gap * 100, 4), "close_change_pct": round(closing_gap * 100, 4), "reason": "Unresolved price discontinuity; possible corporate action or genuine extreme move."})
    return flags


def research_config(symbol: str, protocol: Protocol) -> dict:
    return {"source": "csv", "symbol": symbol, "account_size": protocol.account_size, "risk_pct": protocol.risk_pct, "fee_bps": protocol.fee_bps, "slippage_bps": protocol.slippage_bps, "spread_bps": protocol.spread_bps, "max_leverage": protocol.max_leverage, "quantity_step": protocol.quantity_step, "contract_multiplier": protocol.contract_multiplier, "train_fraction": protocol.train_fraction, "max_drawdown_pct": protocol.maximum_training_drawdown_pct}


def _training_gates(metrics: dict, walk_forward: dict, protocol: Protocol) -> list[str]:
    reasons = []
    if metrics["total_trades"] < protocol.minimum_train_trades:
        reasons.append("Insufficient training trades")
    if metrics["net_profit"] <= 0 or metrics["expectancy_r"] <= 0:
        reasons.append("Nonpositive cost-adjusted training expectancy")
    if metrics["profit_factor"] is not None and metrics["profit_factor"] < protocol.minimum_training_profit_factor:
        reasons.append("Training profit factor below the predeclared threshold")
    if metrics["max_drawdown_pct"] >= protocol.maximum_training_drawdown_pct:
        reasons.append("Training drawdown reaches the fixed loss budget")
    if walk_forward["fold_count"] < 2 or walk_forward["total_trades"] < protocol.minimum_walk_forward_trades:
        reasons.append("Insufficient training-only walk-forward evidence")
    if walk_forward["positive_fraction"] < protocol.minimum_walk_forward_positive_fraction or walk_forward["mean_net_return_pct"] <= 0:
        reasons.append("Training-only walk-forward is not consistently positive")
    return reasons


def train_asset(task: tuple[str, list[dict], dict]) -> dict:
    """Worker receives ONLY the training prefix, never the asset holdout."""
    symbol, raw_prefix, protocol_dict = task
    protocol = Protocol(**protocol_dict)
    try:
        prefix = market.validate_bars(raw_prefix)
        flags = price_gap_flags(prefix, protocol.gap_threshold)
        if flags:
            return {"symbol": symbol, "status": "training_quality_excluded", "reasons": ["Price discontinuity greater than 40% inside training"], "quality_flags": flags}
        config = backtest.normalize_config(research_config(symbol, protocol))
        labels = strategies.regimes(prefix)
        families = []
        for definition in strategies.catalog():
            strategy_id = definition["id"]
            if strategy_id == "buy_hold":
                continue
            candidates = [{"params": params, "signals": strategies.signals_for(prefix, strategy_id, params, regime_labels=labels)} for params in strategies.parameter_candidates(strategy_id)]
            chosen, result = backtest._choose_candidate(prefix, candidates, config, 0, len(prefix), strategy_id)
            walk_forward = backtest._walk_forward(prefix, candidates, config, len(prefix), strategy_id)
            reasons = _training_gates(result["metrics"], walk_forward, protocol)
            families.append({"strategy_id": strategy_id, "name": definition["name"], "params": candidates[chosen]["params"], "training_score": round(backtest._train_score(result), 6), "train_metrics": result["metrics"], "walk_forward": walk_forward, "training_gate_reasons": reasons, "training_gate_pass": not reasons})
        admitted = [family for family in families if family["training_gate_pass"]]
        winner = sorted(admitted, key=lambda family: (-family["training_score"], family["strategy_id"]))[0] if admitted else None
        return {"symbol": symbol, "status": "rankable" if winner else "training_evidence_rejected", "training_start": prefix[0]["time"], "training_end": prefix[-1]["time"], "training_bars": len(prefix), "training_hash": market.data_fingerprint(prefix), "families_tested": len(families), "parameter_combinations_tested": sum(len(strategies.parameter_candidates(family["strategy_id"])) for family in families), "winner": winner, "family_results": families}
    except (ValueError, OverflowError, ZeroDivisionError) as exc:
        return {"symbol": symbol, "status": "training_quality_excluded", "reasons": [str(exc)]}


def build_training_shortlist(universe: dict, protocol: Protocol = Protocol(), *, workers: int = 1, progress: bool = False) -> dict:
    symbols = sorted(universe)
    availability_exclusions = []
    tasks = []
    for symbol in symbols:
        if symbol in protocol.excluded_symbols:
            availability_exclusions.append({"symbol": symbol, "reason": "Previously examined holdout; explicitly excluded before this experiment"})
        elif len(universe[symbol]) < protocol.minimum_bars:
            availability_exclusions.append({"symbol": symbol, "reason": f"Fewer than {protocol.minimum_bars} date-labelled rows in fixed window", "bars": len(universe[symbol])})
        else:
            tasks.append((symbol, universe[symbol][:int(len(universe[symbol]) * protocol.train_fraction)], asdict(protocol)))
    if protocol.max_assets is not None:
        omitted = tasks[protocol.max_assets:]
        availability_exclusions.extend({"symbol": task[0], "reason": "Outside the predeclared alphabetical max-assets limit"} for task in omitted)
        tasks = tasks[:protocol.max_assets]
    if workers not in (1, 2):
        raise ValueError("Use one or two workers")
    results = []
    executor = ProcessPoolExecutor(max_workers=workers) if workers == 2 else None
    try:
        outputs = executor.map(train_asset, tasks, chunksize=4) if executor else map(train_asset, tasks)
        for index, output in enumerate(outputs, 1):
            results.append(output)
            if progress and (index % 25 == 0 or index == len(tasks)):
                print(f"Training only: {index}/{len(tasks)} assets; holdout remains unopened", flush=True)
    finally:
        if executor:
            executor.shutdown(wait=True)
    rankable = sorted((result for result in results if result["status"] == "rankable"), key=lambda result: (-result["winner"]["training_score"], result["symbol"], result["winner"]["strategy_id"]))
    shortlist = [{"rank": index + 1, "symbol": result["symbol"], "strategy_id": result["winner"]["strategy_id"], "name": result["winner"]["name"], "params": result["winner"]["params"], "training_score": result["winner"]["training_score"], "train_metrics": result["winner"]["train_metrics"], "walk_forward": result["winner"]["walk_forward"], "training_start": result["training_start"], "training_end": result["training_end"], "training_bars": result["training_bars"], "training_hash": result["training_hash"]} for index, result in enumerate(rankable[:protocol.shortlist_size])]
    return {"protocol": asdict(protocol), "selection_basis": "Only training price paths and training-only rolling validation; no final holdout strategy or asset ranking", "shortlist": shortlist, "universe_count": len(symbols), "training_assets_tested": len(tasks), "rankable_assets": len(rankable), "families_tested": sum(result.get("families_tested", 0) for result in results), "parameter_combinations_tested": sum(result.get("parameter_combinations_tested", 0) for result in results), "availability_exclusions": availability_exclusions, "training_results": results, "survivorship_warning": "The archive universe and minimum full-window row count condition on historical availability. Delisted securities and original membership are not established."}


def adjusted_interval(trades: list[dict], *, comparisons: int = 5, resamples: int = 5000) -> dict:
    returns = [float(trade["return_r"]) for trade in trades]
    if any(not math.isfinite(value) for value in returns):
        raise ValueError("Trade R values must be finite")
    n = len(returns)
    result = {"sample_size": n, "comparison_budget": comparisons, "nominal_family_confidence_pct": 95, "interval_confidence_pct": round((1 - 0.05 / comparisons) * 100, 4), "mean_r_interval": None, "lower_above_zero": False, "method": "Bonferroni-style descriptive moving-block bootstrap; not a calibrated guarantee of family-wise error", "limitations": ["Resampling cannot remove feed bias, selection overfitting or nonstationarity.", "Dependence across assets and limited trade samples make confidence approximate."]}
    if n < 2:
        result["reason"] = "Insufficient sample"
        return result
    block = max(2, min(10, int(math.sqrt(n))))
    seed = int(_fingerprint(returns)[:16], 16)
    rng = random.Random(seed)
    means = []
    for _ in range(resamples):
        sample = []
        while len(sample) < n:
            begin = rng.randrange(n - block + 1)
            sample.extend(returns[begin:begin + block])
        means.append(statistics.mean(sample[:n]))
    means.sort()
    alpha = 0.05 / (2 * comparisons)
    interval = [round(means[int(alpha * (resamples - 1))], 6), round(means[int((1 - alpha) * (resamples - 1))], 6)]
    result.update({"mean_r_interval": interval, "block_length": block, "resamples": resamples, "lower_above_zero": n >= backtest.MIN_HOLDOUT_TRADES and interval[0] > 0})
    return result


def evaluate_locked_holdouts(universe: dict, lock: dict, *, progress: bool = False) -> list[dict]:
    protocol = Protocol(**lock["protocol"])
    outputs = []
    for chosen in lock["shortlist"]:
        symbol = chosen["symbol"]
        prefix = market.validate_bars(universe[symbol][:chosen["training_bars"]])
        if market.data_fingerprint(prefix) != chosen["training_hash"]:
            raise ValueError(f"Training data changed after locking {symbol}")
        result = {"symbol": symbol, "strategy_id": chosen["strategy_id"], "rank_locked_before_holdout": chosen["rank"], "candidate_selected_before_holdout": True, "params": chosen["params"], "live_candidate": False}
        try:
            bars = market.validate_bars(universe[symbol])
            flags = price_gap_flags(bars, protocol.gap_threshold, start=chosen["training_bars"])
            if flags:
                result.update({"status": "holdout_quality_invalid", "quality_flags": flags, "engine_eligible": False, "adjusted_evidence": False, "reason": "Locked candidate has an unresolved holdout discontinuity; no replacement is selected."})
            else:
                config = research_config(symbol, protocol)
                config["strategy_ids"] = [chosen["strategy_id"]]
                config["prop_profile"] = {"id": "archive-static-model", "name": "Generic static historical model", "status": "illustrative", "account_size": protocol.account_size, "daily_loss_pct": 5, "max_loss_pct": 10, "profit_target_pct": 8, "drawdown_type": "static", "daily_reset_timezone": "UTC", "min_trading_days": 5}
                research = backtest.run_research(bars, config)
                strategy = next(item for item in research["strategies"] if item["id"] == chosen["strategy_id"])
                if strategy["params"] != chosen["params"] or strategy["train_metrics"] != chosen["train_metrics"]:
                    raise ValueError(f"Locked training choice changed for {symbol}; stop rather than retune")
                adjusted = adjusted_interval(strategy["trades"], comparisons=protocol.shortlist_size, resamples=protocol.bootstrap_resamples)
                accepted = strategy["eligible"] and adjusted["lower_above_zero"]
                result.update({"status": "historical_paper_candidate" if accepted else "holdout_rejected", "engine_eligible": strategy["eligible"], "adjusted_evidence": accepted, "holdout_metrics": strategy["test_metrics"], "confidence": strategy["confidence"], "multiple_comparison_interval": adjusted, "reasons": strategy["reasons"] + ([] if adjusted["lower_above_zero"] else ["The stricter five-candidate descriptive mean-R interval includes zero or the sample is too small."]), "rule_replay": strategy["rule_replay"], "regime_metrics": strategy["regime_metrics"], "trades": strategy["trades"], "equity_curve": strategy["equity_curve"], "data": research["data"], "benchmark_holdout": next(item["test_metrics"] for item in research["strategies"] if item["baseline"]), "freshness_warning": "Data end in February 2018. This is historical research, not a current 2026 setup or verified prop-firm execution."})
        except (ValueError, OverflowError, ZeroDivisionError) as exc:
            result.update({"status": "holdout_quality_invalid", "engine_eligible": False, "adjusted_evidence": False, "reason": str(exc)})
        outputs.append(result)
        if progress:
            print(f"Locked holdout: {symbol} / {chosen['strategy_id']} -> {result['status']}; no substitution", flush=True)
    return outputs


def write_json(path: Path, report: dict, *, compact: bool = False) -> None:
    """Atomic replacement keeps the training lock if holdout work is interrupted."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(report, ensure_ascii=False, indent=None if compact else 2,
                      separators=(",", ":") if compact else None, allow_nan=False) + "\n"
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, prefix=".edge-search-", suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(text)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def standard_reports(report: dict) -> list[dict]:
    """Adapt already frozen results for the app without any new backtests.

    Every displayed figure comes from the locked experiment. No synthetic
    live signal or alternative strategy is introduced by this presentation.
    """
    locked = report["locked_training"]
    protocol = Protocol(**locked["protocol"])
    by_symbol = {candidate["symbol"]: candidate for candidate in locked["shortlist"]}
    outputs = []
    for outcome in report["holdout_results"]:
        chosen = by_symbol[outcome["symbol"]]
        if "holdout_metrics" not in outcome:
            continue  # Full invalid outcomes remain in holdout_results.
        eligible = outcome["adjusted_evidence"]
        strategy = {"id": chosen["strategy_id"], "name": chosen["name"], "params": chosen["params"], "train_metrics": chosen["train_metrics"], "test_metrics": outcome["holdout_metrics"], "walk_forward": chosen["walk_forward"], "eligible": eligible, "engine_eligible": outcome["engine_eligible"], "confidence": outcome["confidence"], "multiple_comparison_interval": outcome["multiple_comparison_interval"], "reasons": outcome["reasons"], "training_score": chosen["training_score"], "training_winner": True, "equity_curve": outcome["equity_curve"], "equity_curve_thinned": outcome["data"]["test_bars"] > 400, "trades": outcome["trades"], "regime_metrics": outcome["regime_metrics"], "baseline": False, "rule_replay": outcome["rule_replay"], "candidate_selected_before_holdout": True}
        summary = {**outcome["holdout_metrics"], "selected_name": chosen["name"] if eligible else None, "training_candidate": chosen["strategy_id"], "training_candidate_name": chosen["name"], "qualified_count": int(eligible), "status": "historical_paper_candidate" if eligible else "no_qualified_strategy", "account_rule_status": outcome["rule_replay"]["status"], "warnings": report["warnings"] + [outcome["freshness_warning"]], "performance_basis": "Frozen training-only asset shortlist on chronological final holdout"}
        config = research_config(outcome["symbol"], protocol)
        config["strategy_ids"] = [chosen["strategy_id"]]
        outputs.append({"symbol": outcome["symbol"], "data": outcome["data"], "summary": summary, "training_candidate": chosen["strategy_id"], "selected_strategy": chosen["strategy_id"] if eligible else None, "strategies": [strategy], "benchmark_holdout": outcome["benchmark_holdout"], "config": config, "methodology": {"asset_selection": locked["selection_basis"], "locked_rank": chosen["rank"], "multiple_comparisons": outcome["multiple_comparison_interval"]["method"], "no_substitution": True, "presentation": "Derived from frozen experiment; no holdout recalculation or live signal"}, "provenance": report["source"], "historical_only": True, "live_orders_enabled": False})
    return outputs


def engine_fingerprint() -> str:
    paths = [REPOSITORY / "propdesk" / name for name in ("market.py", "strategies.py", "backtest.py", "compliance.py", "risk.py")]
    paths.append(Path(__file__).resolve())
    return _fingerprint({str(path.relative_to(REPOSITORY)): source_digest(path) for path in paths})


def _equivalence_record_matches(record: dict, *, code_hash: str, digest: str, protocol: Protocol, lock_sha: str) -> bool:
    return (record.get("current_engine_sha256") == code_hash
            and record.get("source_sha256") == digest
            and record.get("protocol_sha256") == _fingerprint(asdict(protocol))
            and record.get("training_lock_sha256") == lock_sha
            and record.get("equivalent") is True
            and record.get("method") == "fixed locked-parameter holdout replay; no retraining or selection")


def verify_final(source: Path, output: Path, *, expected_protocol: Protocol = Protocol(), progress: bool = True) -> dict:
    """Replay exactly the frozen candidates under the current portable engine.

    This is a numerical regression check on already inspected data, not a new
    experiment. No train scorer, parameter selector, walk-forward fit, asset
    ranking or alternative strategy is called. Original evidence is preserved.
    """
    report_file_digest = source_digest(output)
    report = json.loads(output.read_text(encoding="utf-8"))
    if report.get("phase") != "final_review":
        raise ValueError("Fixed replay requires a completed frozen final_review report")
    digest = source_digest(source)
    if (digest != SOURCE_SHA256 or report.get("source", {}).get("sha256") != digest
            or report.get("source", {}).get("commit") != SOURCE_COMMIT):
        raise ValueError("Fixed replay requires the exact pinned source and original source provenance")
    locked = report["locked_training"]
    lock_sha = _fingerprint(locked)
    if lock_sha != report.get("training_lock_sha256"):
        raise ValueError("Frozen training lock is inconsistent; original evidence remains untouched")
    if locked.get("protocol") != json.loads(json.dumps(asdict(expected_protocol))):
        raise ValueError("Fixed replay protocol differs from the frozen predeclaration")
    outcomes = report.get("holdout_results", [])
    if [outcome["symbol"] for outcome in outcomes] != [candidate["symbol"] for candidate in locked["shortlist"]]:
        raise ValueError("Frozen outcomes no longer match the locked shortlist")
    code_hash = engine_fingerprint()
    universe = load_archive(source, expected_protocol)
    checks = []
    from propdesk.compliance import evaluate
    for chosen, outcome in zip(locked["shortlist"], outcomes):
        symbol = chosen["symbol"]
        bars = market.validate_bars(universe[symbol])
        train_end = chosen["training_bars"]
        if train_end != int(len(bars) * expected_protocol.train_fraction):
            raise ValueError(f"Frozen train/holdout boundary changed for {symbol}")
        if market.data_fingerprint(bars[:train_end]) != chosen["training_hash"]:
            raise ValueError(f"Frozen training data changed for {symbol}")
        if outcome.get("params") != chosen["params"] or outcome["strategy_id"] != chosen["strategy_id"]:
            raise ValueError(f"Frozen strategy or parameters changed for {symbol}")
        flags = price_gap_flags(bars, expected_protocol.gap_threshold, start=train_end)
        if flags or "holdout_metrics" not in outcome:
            # The actual archived study has five valid-quality holdouts. Do
            # not invent equivalence for an invalid/absent original result.
            raise ValueError(f"Fixed replay cannot validate an invalid or absent holdout for {symbol}")
        config = backtest.normalize_config(research_config(symbol, expected_protocol))
        observations = strategies.signals_for(bars, chosen["strategy_id"], chosen["params"])
        result = backtest.simulate(bars, observations, chosen["params"], config, start=train_end,
                                   end=len(bars), strategy_id=chosen["strategy_id"], split="oos")
        profile = {"id": "archive-static-model", "name": "Generic static historical model", "status": "illustrative",
                   "account_size": expected_protocol.account_size, "daily_loss_pct": 5, "max_loss_pct": 10,
                   "profit_target_pct": 8, "drawdown_type": "static", "daily_reset_timezone": "UTC", "min_trading_days": 5}
        actual = {"holdout_metrics": result["metrics"], "trades": result["trades"],
                  "confidence": backtest._confidence(result["trades"]),
                  "rule_replay": evaluate(result["equity_curve"], profile, trades=result["trades"]),
                  "multiple_comparison_interval": adjusted_interval(result["trades"], comparisons=expected_protocol.shortlist_size,
                                                                   resamples=expected_protocol.bootstrap_resamples)}
        baseline_signals = strategies.signals_for(bars, "buy_hold", {"baseline": True})
        baseline = backtest.simulate(bars, baseline_signals, {"baseline": True}, config,
                                     start=train_end, end=len(bars), strategy_id="buy_hold", split="oos")
        actual["benchmark_holdout"] = baseline["metrics"]
        for field, value in actual.items():
            if outcome.get(field) != value:
                raise ValueError(f"Fixed replay mismatch for {symbol}: {field}; original report remains untouched")
        checks.append({"symbol": symbol, "strategy_id": chosen["strategy_id"], "params_sha256": _fingerprint(chosen["params"]),
                       "holdout_metrics_equal": True, "trades_equal": True, "rule_replay_equal": True,
                       "confidence_equal": True, "benchmark_equal": True, "full_curve_bars": len(result["equity_curve"]),
                       "data_sha256": market.data_fingerprint(bars)})
        if progress:
            print(f"Fixed replay verified: {symbol} / {chosen['strategy_id']}; parameters, P&L, trades, rules and benchmark unchanged", flush=True)
    if _fingerprint(locked) != lock_sha or source_digest(output) != report_file_digest:
        raise ValueError("Frozen report changed during verification; refusing to overwrite it")
    if engine_fingerprint() != code_hash:
        raise ValueError("Engine source changed during verification; no equivalence record is saved")
    record = {"method": "fixed locked-parameter holdout replay; no retraining or selection", "equivalent": True,
              "original_engine_sha256": report["engine_sha256"], "current_engine_sha256": code_hash,
              "source_sha256": digest, "protocol_sha256": _fingerprint(asdict(expected_protocol)),
              "training_lock_sha256": lock_sha, "candidates_checked": len(checks), "checks": checks,
              "purpose": "Verify portable timezone imports and presentation changes preserve the archived results; not new trading evidence"}
    records = report.setdefault("fixed_replay_verifications", [])
    if not any(_equivalence_record_matches(existing, code_hash=code_hash, digest=digest,
                                           protocol=expected_protocol, lock_sha=lock_sha) for existing in records):
        records.append(record)
    write_json(output, report, compact=True)
    return report


def run_experiment(source: Path, output: Path, *, protocol: Protocol = Protocol(), workers: int = 2, progress: bool = True) -> dict:
    began = time.monotonic()
    digest = source_digest(source)
    if digest != SOURCE_SHA256:
        raise ValueError("Archive SHA-256 does not match the pinned source. The experiment requires the exact documented input.")
    code_hash = engine_fingerprint()
    provenance = {"repository": "https://github.com/plotly/datasets.git", "commit": SOURCE_COMMIT, "url": SOURCE_URL, "sha256": digest, "license": "MIT repository license; original market vendor and adjustment treatment not independently established", "date_timestamp_mapping": "Daily calendar labels mapped to 00:00:00Z, not audited exchange opening or intrabar fill times", "provenance_verified": False}
    if output.exists():
        existing = json.loads(output.read_text(encoding="utf-8"))
        matching_replay = any(_equivalence_record_matches(record, code_hash=code_hash, digest=digest, protocol=protocol,
                                                         lock_sha=existing.get("training_lock_sha256", ""))
                              for record in existing.get("fixed_replay_verifications", []))
        engine_matches = existing.get("engine_sha256") == code_hash or matching_replay
        if (existing.get("source", {}).get("sha256") != digest or not engine_matches
                or existing.get("locked_training", {}).get("protocol") != json.loads(json.dumps(asdict(protocol)))):
            raise ValueError("An existing lock has a different source, protocol or unverified engine. Use --verify-final for a fixed numerical replay; do not retune opened holdouts.")
        if existing.get("training_lock_sha256") != _fingerprint(existing.get("locked_training")):
            raise ValueError("Stored training lock is inconsistent")
        if existing.get("phase") == "final_review":
            if progress:
                print("Identical final experiment already exists; returning its frozen results without opening holdouts again.", flush=True)
            return existing
    universe = load_archive(source, protocol)
    if output.exists():
        locked = existing["locked_training"]
        if existing["training_lock_sha256"] != _fingerprint(locked):
            raise ValueError("Stored training lock is inconsistent")
    else:
        locked = build_training_shortlist(universe, protocol, workers=workers, progress=progress)
    report = {"phase": "training_locked", "source": provenance, "engine_sha256": code_hash, "locked_training": locked, "training_lock_sha256": _fingerprint(locked), "holdout_results": [], "warnings": ["Pre-2018 selected US equities are neither all possible assets nor current live prop-firm instruments.", "Availability and archive membership create survivorship bias; original vendor, splits/dividends and broker-specific feeds are unresolved.", "The universe search contains many training hypotheses. The five final comparisons receive a stricter descriptive interval but cannot prove future profitability.", "Actual prop terms, overnight financing, borrow availability, short restrictions, tick fills and current transaction costs need independent verification.", "Already inspected AAPL/MSFT/JPM/XOM are excluded. No failed holdout is replaced or retuned."]}
    write_json(output, report)
    if progress:
        print(f"Training shortlist LOCKED on disk: {len(locked['shortlist'])} candidates; lock {report['training_lock_sha256']}", flush=True)
    report["holdout_results"] = evaluate_locked_holdouts(universe, locked, progress=progress)
    report["phase"] = "final_review"
    report["accepted_historical_candidates"] = sum(item["adjusted_evidence"] for item in report["holdout_results"])
    report["live_candidates"] = 0
    report["elapsed_seconds"] = round(time.monotonic() - began, 3)
    report["decision"] = "Historical paper candidates require new independent recent data and verified execution" if report["accepted_historical_candidates"] else "No strategy passed this predeclared independent holdout experiment. Stop; do not manufacture an edge by retuning these holdouts."
    if report["training_lock_sha256"] != _fingerprint(locked):
        raise AssertionError("Training lock mutated during final holdout")
    report["reports"] = standard_reports(report)
    write_json(output, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("/tmp/prop-lab-market-source/all_stocks_5yr.csv"))
    parser.add_argument("--output", type=Path, default=REPOSITORY / "docs" / "edge-search.json")
    parser.add_argument("--workers", type=int, choices=(1, 2), default=2)
    parser.add_argument("--verify-final", action="store_true", help="Verify only the frozen candidates with locked parameters; no new search or retraining")
    parser.add_argument("--max-assets", type=int, default=None, help="Optional predeclared alphabetical limit; never selected by returns")
    args = parser.parse_args()
    if args.max_assets is not None and args.max_assets < 1:
        parser.error("--max-assets must be positive")
    try:
        protocol = Protocol(max_assets=args.max_assets)
        if args.verify_final:
            report = verify_final(args.source, args.output, expected_protocol=protocol)
        else:
            report = run_experiment(args.source, args.output, protocol=protocol, workers=args.workers)
    except (ValueError, OSError) as exc:
        print(f"Search stopped: {exc}", file=sys.stderr)
        return 1
    print(report["decision"], flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
