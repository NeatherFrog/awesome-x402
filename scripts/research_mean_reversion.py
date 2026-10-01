#!/usr/bin/env python3
"""One fixed, exploratory daily RSI2 pullback study; no parameter search.

Reuses the already inspected five-ETF source snapshots explicitly. This is
neither a globally blind holdout nor an exact broker/prop account simulation.
The existing independently tested costed daily execution engine is reused;
none of the earlier study's code, rules or selection is modified.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import research_sourced as daily
from propdesk import backtest, market, strategies

OUTPUT = ROOT / "docs/mean-reversion-research.json"
DIRECTORY = ROOT / "data/mean-reversion-history"
STRATEGY_ID = "rsi2_pullback_5"
NAME = "RSI2<5 + SMA200 · fixed-stop costed daily adaptation"


def wilder_rsi(closes, period=2):
    if period < 1:
        raise ValueError("Positive RSI period required")
    result = [None] * len(closes)
    if len(closes) <= period:
        return result
    gains = [max(closes[i]-closes[i-1], 0) for i in range(1, period+1)]
    losses = [max(closes[i-1]-closes[i], 0) for i in range(1, period+1)]
    gain, loss = sum(gains)/period, sum(losses)/period
    for i in range(period, len(closes)):
        if i > period:
            change = closes[i]-closes[i-1]
            gain = ((period-1)*gain+max(change, 0))/period
            loss = ((period-1)*loss+max(-change, 0))/period
        result[i] = 50.0 if gain == loss == 0 else (100.0 if loss == 0 else 100-100/(1+gain/loss))
    return result


def decisions(bars):
    closes = [bar["close"] for bar in bars]
    trend, fast = daily._sma(closes, 200), daily._sma(closes, 5)
    rsi, atr = wilder_rsi(closes), strategies.atr(bars, 14)
    observations = [None] * len(bars)
    for i in range(1, len(bars)):
        j = i-1
        if trend[j] is None or rsi[j] is None or atr[j] is None:
            continue
        observations[i] = {"entry": closes[j] > trend[j] and rsi[j] < 5,
                           "exit": closes[j] > fast[j], "atr": atr[j],
                           "signal_time": bars[j]["time"], "rsi2": rsi[j],
                           "sma200": trend[j], "sma5": fast[j], "close": closes[j]}
    return observations


def load_inputs(report):
    if daily.digest(report["protocol"]) != report["protocol_sha256"]:
        raise ValueError("Frozen protocol changed before source loading")
    if daily.file_digest(ROOT/"docs/mean-reversion-sources.json") != report["protocol"]["sources_audit_sha256"]:
        raise ValueError("Frozen source audit changed")
    if daily.file_digest(ROOT/"docs/sourced-strategy-research.json") != report["protocol"]["parent_data_report_sha256"]:
        raise ValueError("Parent source provenance changed")
    records = report["protocol"]["inputs"]
    if {record["symbol"] for record in records} != set(daily.SYMBOLS):
        raise ValueError("Fixed five-symbol universe required")
    datasets = {}
    for record in records:
        for key in ("json", "csv", "provider_receipt"):
            path = ROOT / record[key+"_path"]
            if path.is_symlink() or daily.file_digest(path) != record[key+"_sha256"]:
                raise ValueError("Frozen source snapshot/receipt changed")
        dataset = json.loads((ROOT/record["json_path"]).read_text(encoding="utf-8"))
        bars = market.validate_bars(dataset["bars"])
        if market.data_fingerprint(bars) != record["bars_sha256"]:
            raise ValueError("Frozen source price fingerprint changed")
        datasets[record["symbol"]] = bars
    clocks = [[row["time"] for row in datasets[symbol]] for symbol in daily.SYMBOLS]
    if any(clock != clocks[0] for clock in clocks[1:]):
        raise ValueError("Fixed source sessions must all match; no dropped dates")
    return datasets


def freeze(output=OUTPUT, directory=DIRECTORY):
    if output.exists():
        report = json.loads(output.read_text(encoding="utf-8"))
        if daily.digest(report["protocol"]) != report["protocol_sha256"]:
            raise ValueError("Fixed protocol changed")
        return report
    source = json.loads((ROOT/"docs/sourced-strategy-research.json").read_text(encoding="utf-8"))
    audit = json.loads((ROOT/"docs/mean-reversion-sources.json").read_text(encoding="utf-8"))
    protocol = {
        "version": "exploratory-rsi2-fixed-v1", "frozen_at": daily.iso(datetime.now(timezone.utc)),
        "symbols": list(daily.SYMBOLS), "interval": "1d", "strategy_ids": [STRATEGY_ID],
        "sources": audit["strategy_sources"], "sources_audit_sha256": daily.file_digest(ROOT/"docs/mean-reversion-sources.json"),
        "inputs": source["snapshots"], "parent_data_report_sha256": daily.file_digest(ROOT/"docs/sourced-strategy-research.json"),
        "scope": "Explicit sequential exploratory test on already viewed ETF history and factors. Not a new independent holdout; no family/threshold/market promotion after outcome. Rules are our fixed hypothesis; source verification limitations are preserved in the source audit.",
        "windows": {"training": ["2005-01-01", "2013-01-01"], "warmup_only": ["2013-01-01", "2017-01-01"],
                    "historical_holdout": ["2017-01-01", "2024-01-01"], "confirmation": ["2024-01-01", "2026-10-01"]},
        "rules": {STRATEGY_ID: "Long/cash only. Prior closed daily close>SMA200 and Wilder RSI2<5 enter next open. Exit next open after prior close>SMA5. Fixed3ATR14 protection added by this project; no TP, no trailing, no short, no same-close fills or averaging down. Equality neither triggers entry nor indicator exit."},
        "execution": {"engine": "Unmodified independently tested scripts/research_sourced.simulate_asset",
                      "stop": "Entry adversefill minus3 prior-closed WilderATR14; opening gap stop first, then already-known indicator exit, then intrabar stop; no same-session reentry",
                      "close": "Final sample forced close is hypothetical valuation only; no final-bar entries",
                      "position": "Each segment starts flat; prior prices warm indicators only; overnight and weekends possible"},
        "portfolio": {"account_size": 100000, "bucket_account_size": 20000, "bucket_risk_pct": 1.25,
                      "initial_risk_budget_per_asset": 250, "initial_aggregate_budget_pct": 1.25,
                      "max_leverage": 1, "quantity_step": 1, "contract_multiplier": 1,
                      "risk_note": "R denominator is allocated budget. Integer quantities and cash cap lower exposure; fees/gaps can exceed allocated stop budget. No literal historical split-adjusted share claim."},
        "costs": {"fee_bps_per_side": 2, "slippage_bps_per_side": 1, "full_spread_bps": 1,
                  "carry_annual_stress": [.04, .08], "double_all_friction_stress": True,
                  "cash_interest": 0, "dividends": 0, "borrow": "No short positions",
                  "status": "Hypotheses, not executable prop broker tariffs"},
        "selection": {"primary": STRATEGY_ID, "basis": "One fixed family and parameters declared before this performance run; no optimization",
                      "training_folds": [["2007-01-01", "2009-01-01"], ["2009-01-01", "2011-01-01"], ["2011-01-01", "2013-01-01"]]},
        "qualification": {"both_windows_required": True, "training_positive": True, "training_fold_positive_fraction": 2/3,
                          "min_trades_each": 60, "min_months_each": 24, "min_profit_factor": 1.2,
                          "max_drawdown_pct": 8, "monthly_ci99_lower_positive": True,
                          "carry4_positive": True, "doubled_friction_positive": True,
                          "carry8_descriptive_only": True, "static_rule_replay": "Descriptive loss floors only; not exact firm and not a payout", "prospective_forward_required": True},
        "inference": {"method": "Synchronized portfolio monthly returns, block3months5000resamples99%; reused-data descriptive only", "seed": 6022017},
        "orders": "Historicalresearch/paper only; no real broker executions, deposits, challenges or payouts",
    }
    report = {"phase": "predeclared", "protocol": protocol, "protocol_sha256": daily.digest(protocol)}
    daily.immutable_write(directory/"protocol.json", daily.canonical(protocol)+"\n")
    daily.write_report(output, report)
    return report


def portfolio(datasets, start_date, end_date, *, financing_rate=0, friction_multiplier=1, baseline_scale=None):
    if set(datasets) != set(daily.SYMBOLS):
        raise ValueError("All frozen assets required")
    clocks = [[row["time"] for row in datasets[symbol]] for symbol in daily.SYMBOLS]
    if any(clock != clocks[0] for clock in clocks[1:]):
        raise ValueError("Synchronized sessions required")
    active = [i for i, stamp in enumerate(clocks[0]) if start_date <= stamp[:10] < end_date]
    if not active:
        raise ValueError("No segment observations")
    assets, trades = {}, []
    for symbol in daily.SYMBOLS:
        config = backtest.normalize_config({"symbol": symbol, "source": "csv", "account_size": 20000,
                    "risk_pct": 1.25, "quantity_step": 1, "max_leverage": 1,
                    "fee_bps": 2*friction_multiplier, "slippage_bps": friction_multiplier, "spread_bps": friction_multiplier})
        assets[symbol] = daily.simulate_asset(datasets[symbol], decisions(datasets[symbol]), config,
                    start=active[0], end=active[-1]+1, financing_rate=financing_rate, baseline_scale=baseline_scale)
        trades.extend(assets[symbol]["trades"])
    curve, peak = [], 100000
    for i in range(len(active)):
        points = [assets[symbol]["equity_curve"][i] for symbol in daily.SYMBOLS]
        point = {key: sum(row[key] for row in points) for key in ("balance", "equity", "opening_balance", "opening_equity", "worst_equity", "best_equity")}
        amount = max(0, peak-point["worst_equity"])
        point.update({"time": points[0]["time"], "drawdown_amount": amount, "drawdown_pct": amount/peak*100})
        peak = max(peak, point["equity"])
        curve.append(point)
    trades.sort(key=lambda trade: (trade["exit_time"], trade["symbol"], trade["entry_time"]))
    metrics = daily._metrics(curve, trades, 100000)
    years = max((market.utc_datetime(curve[-1]["time"])-market.utc_datetime(curve[0]["time"])).days/365.25, 1/365.25)
    metrics["annualized_return_pct"] = ((metrics["final_equity"]/100000)**(1/years)-1)*100
    monthly = daily.aggregate_monthly_returns(curve, 100000)
    metrics["monthly_observations"] = len(monthly)
    return {"metrics": metrics, "trades": trades, "equity_curve": curve, "monthly_returns": monthly,
            "asset_results": assets, "data": {"start": curve[0]["time"], "end": curve[-1]["time"], "bars": len(curve)}}


def training_prefixes(datasets, end):
    return {symbol: market.data_fingerprint([bar for bar in bars if bar["time"][:10] < end]) for symbol, bars in datasets.items()}


def evaluate(datasets, report):
    protocol, lock = report["protocol"], report["training_lock"]
    if daily.digest(protocol) != report["protocol_sha256"]:
        raise ValueError("Frozen protocol changed before historical evaluations")
    if daily.digest(lock) != report["training_lock_sha256"] or lock["protocol_sha256"] != report["protocol_sha256"]:
        raise ValueError("Training lock changed")
    if lock["training_bar_sha256"] != training_prefixes(datasets, protocol["windows"]["training"][1]):
        raise ValueError("Training prefix changed before historical evaluations")
    windows = {}
    gates = protocol["qualification"]
    for name in ("historical_holdout", "confirmation"):
        dates = protocol["windows"][name]
        result = portfolio(datasets, *dates)
        stress4, stress8 = portfolio(datasets, *dates, financing_rate=.04), portfolio(datasets, *dates, financing_rate=.08)
        double = portfolio(datasets, *dates, friction_multiplier=2)
        confidence = daily.monthly_bootstrap(result["monthly_returns"])
        baseline = portfolio(datasets, *dates, baseline_scale=lock["benchmark_scale"])
        reasons = []
        m = result["metrics"]
        if m["net_profit"] <= 0:
            reasons.append("Net profit not positive")
        if m["total_trades"] < gates["min_trades_each"]:
            reasons.append("Fewer than60 aggregate trades")
        if m["profit_factor"] is None or m["profit_factor"] < gates["min_profit_factor"]:
            reasons.append("Profit factor below1.20")
        ci = confidence["mean_monthly_ci_pct"]
        if confidence["months"] < gates["min_months_each"] or ci is None or ci[0] <= 0:
            reasons.append("Descriptive99% monthly interval includeszero or insufficientmonths")
        if m["max_drawdown_pct"] >= gates["max_drawdown_pct"]:
            reasons.append("Aggregate worstbar drawdown reaches8%")
        if stress4["metrics"]["net_profit"] <= 0:
            reasons.append("4% annual carry stress notpositive")
        if double["metrics"]["net_profit"] <= 0:
            reasons.append("Doubledfriction notpositive")
        windows[name] = {**daily._compact_result(result), "confidence": confidence,
                         "stress4pct": {"metrics": stress4["metrics"]}, "stress8pct": {"metrics": stress8["metrics"]},
                         "friction_stress": {"metrics": double["metrics"]}, "rule_replay": daily._replays(result),
                         "risk_matched_buyhold": {"frozen_scale": lock["benchmark_scale"], "metrics": baseline["metrics"]},
                         "excess_over_risk_matched_buyhold_pct": m["net_return_pct"]-baseline["metrics"]["net_return_pct"],
                         "evidence_reasons": reasons, "passes_window": not reasons}
    reasons = [name+": "+reason for name, window in windows.items() for reason in window["evidence_reasons"]]
    if lock["training_metrics"]["net_profit"] <= 0:
        reasons.append("Training netprofit notpositive")
    if lock["positive_training_fold_fraction"] < gates["training_fold_positive_fraction"]:
        reasons.append("Fewer than twoofthree training folds positive")
    return {"id": STRATEGY_ID, "name": NAME, "primary": True, "training": lock, "windows": windows,
            "eligible_historical_price_model": not reasons, "reasons": reasons, "real_prop_qualified": False}


def run(output=OUTPUT, directory=DIRECTORY):
    report = freeze(output, directory)
    if report["phase"] == "complete":
        return report
    if report["phase"] != "predeclared":
        raise ValueError("Incomplete run retained; investigate rather than overwrite its lock")
    datasets = load_inputs(report)
    started = time.monotonic()
    dependencies = ("scripts/research_sourced.py", "propdesk/backtest.py", "propdesk/strategies.py", "propdesk/market.py", "propdesk/risk.py", "propdesk/compliance.py", "propdesk/timezones.py")
    report["execution_producer_before_performance"] = {"recorded_at": daily.iso(datetime.now(timezone.utc)),
            "script_sha256": daily.file_digest(Path(__file__)), "python_version": sys.version.split()[0],
            "dependencies_sha256": {name: daily.file_digest(ROOT/name) for name in dependencies}}
    daily.write_report(output, report)
    dates = report["protocol"]["windows"]["training"]
    # Physically remove all later prices while training; causal warmup retained.
    training_data = {symbol: [bar for bar in bars if bar["time"][:10] < dates[1]] for symbol, bars in datasets.items()}
    training = portfolio(training_data, *dates)
    baseline = portfolio(training_data, *dates, baseline_scale=1)
    baseline_vol = daily._daily_vol(baseline)
    scale = min(1, daily._daily_vol(training)/baseline_vol) if baseline_vol else 0
    folds = [{"dates": dates, "metrics": portfolio(training_data, *dates)["metrics"]}
             for dates in report["protocol"]["selection"]["training_folds"]]
    lock = {"recorded_at": daily.iso(datetime.now(timezone.utc)), "primary_strategy_id": STRATEGY_ID,
            "protocol_sha256": report["protocol_sha256"], "training_metrics": training["metrics"],
            "training_bar_sha256": training_prefixes(training_data, dates[1]), "training_folds": folds,
            "positive_training_fold_fraction": sum(row["metrics"]["net_profit"] > 0 for row in folds)/len(folds),
            "benchmark_scale": scale, "benchmark_note": "Trainingonly dailyvolatility ratio to fixedfiveETF1xbuyhold; integer/cashcaps make match approximate",
            "selection_basis": "One predeclared family; no threshold fit, market selection orholdout read"}
    daily.immutable_write(directory/"training-lock.json", daily.canonical(lock)+"\n")
    report.update({"training_lock": lock, "training_lock_sha256": daily.digest(lock), "phase": "training_locked"})
    daily.write_report(output, report)
    print("Single RSI2 policy locked before historical evaluations", flush=True)
    primary = evaluate(datasets, report)
    report.update({"phase": "complete", "primary_strategy_id": STRATEGY_ID, "strategies": [primary],
            "selected_strategy_id": STRATEGY_ID if primary["eligible_historical_price_model"] else None,
            "real_prop_qualified": False, "live_orders": False, "finished_at": daily.iso(datetime.now(timezone.utc)),
            "elapsed_seconds": time.monotonic()-started,
            "decision": "Historical exploratory candidate only; independent prospective paper validation required" if primary["eligible_historical_price_model"] else "Fixedmeanreversion policy doesnotpass allfrozen requirements; no substitute",
            "limitations": ["Repeated already-inspectedETFhistory: no independent blind confirmation or global multiple-search correction",
                            "Stop/portfolio/nextopen/cost policy is our fixed adaptation; no author performance inherited",
                            "VendorpricesplitnormalizedOHLC not executableCFD quotes; dividends/cashinterest omitted and actualswap/news/sessionrules unverified",
                            "Genericlossfloor replay is descriptive; no actualchallenge/fundedpayout orbrokerorders"]})
    daily.write_report(output, report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--freeze", action="store_true")
    args = parser.parse_args()
    report = freeze() if args.freeze else run()
    print(daily.canonical({"phase": report["phase"], "protocol_sha256": report["protocol_sha256"],
        "primary": report.get("primary_strategy_id"), "selected": report.get("selected_strategy_id"),
        "windows": {name: {"metrics": row["metrics"], "ci99": row["confidence"]["mean_monthly_ci_pct"],
                           "carry4net": row["stress4pct"]["metrics"]["net_return_pct"],
                           "carry8net": row["stress8pct"]["metrics"]["net_return_pct"],
                           "doublecostnet": row["friction_stress"]["metrics"]["net_return_pct"],
                           "reasons": row["evidence_reasons"]}
                    for name, row in (report.get("strategies") or [{}])[0].get("windows", {}).items()}}))
