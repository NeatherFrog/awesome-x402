#!/usr/bin/env python3
"""Predeclared, sourced daily ETF study; a fixed research experiment only.

Rules and windows are immutable before downloads. One portfolio family is
selected on 2005--2012 training; two later evaluations cannot change it.
No broker orders, source-code copying, adjusted-price fabrication or retries
with new hypotheses are part of this script.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import statistics
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, time as time_of_day
from pathlib import Path
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from propdesk import backtest, compliance, feeds, market, strategies
from propdesk.risk import normalize_profile
from propdesk.timezones import timezone_for

SYMBOLS = ("SPY", "QQQ", "IWM", "TLT", "GLD")
STRATEGY_IDS = ("qc_ema_15_30", "bt_sma_10_30", "faber_sma_10m")
NAMES = {"qc_ema_15_30": "QC EMA15/30 · costed risk adaptation",
         "bt_sma_10_30": "Backtrader 2015 SMA10/30 · costed risk adaptation",
         "faber_sma_10m": "Faber SMA10 months · price-only risk adaptation"}
OUTPUT = ROOT / "docs" / "sourced-strategy-research.json"
SNAPSHOTS = ROOT / "data" / "sourced-history"


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def file_digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def iso(value):
    return value.isoformat(timespec="microseconds" if value.microsecond else "seconds").replace("+00:00", "Z")


def write_report(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".sourced-research-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(canonical(value) + "\n")
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def immutable_write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="") as stream:
        stream.write(value)


def source_records():
    return [
        {"strategy_id": "qc_ema_15_30", "source": "QuantConnect official Lean example",
         "url": "https://raw.githubusercontent.com/QuantConnect/Lean/55a6215da636296df3c7dd7bcf4a141a3838366c/Algorithm.CSharp/MovingAverageCrossAlgorithm.cs",
         "commit": "55a6215da636296df3c7dd7bcf4a141a3838366c", "published_commit_date": "2015-06-17",
         "sha256": "1d9a93ed65c408bcdc40607b774f82099046bfd592a38f14b64a8608c8c2abc5",
         "verified": "Official historical source retrieved by independent source agent; indicator/entry policy only, not a profit claim"},
        {"strategy_id": "bt_sma_10_30", "source": "Backtrader official historical strategy and crossover indicator",
         "url": "https://raw.githubusercontent.com/mementum/backtrader/fa853548c1923452fddab5415dba37e451892a50/backtrader/strategies/sma_crossover.py",
         "indicator_url": "https://raw.githubusercontent.com/mementum/backtrader/fa853548c1923452fddab5415dba37e451892a50/backtrader/indicators/crossover.py",
         "commit": "fa853548c1923452fddab5415dba37e451892a50", "published_commit_date": "2015-08-16",
         "indicator_sha256": "c3d6c771bb363d9307a19a8f6918450288e4a4083e355e67ec5c1e9b5d0c91bc",
         "verified": "Official historical source retrieved; 2015 strict previous-sign crossover, not modern equality memory"},
        {"strategy_id": "faber_sma_10m", "source": "Meb Faber, A Quantitative Approach to Tactical Asset Allocation (original 2006/2007, mirrored 2013 update)",
         "url": "https://raw.githubusercontent.com/nerdfilip/SSNR_962461/main/ssrn-962461.pdf",
         "sha256": "e19667fcad0ed40914512d9dcf3c5f08e5a6329181932626a79dfe9c1eb3ab37",
         "retrieved_at": "2026-10-01T10:30:26.687418Z",
         "verified": "Paper text read from third-party mirror; author-host integrity not independently verified; paper is not copied or redistributed"},
    ]


def make_protocol():
    return {
        "version": "sourced-etf-fixed-three-v1", "frozen_at": iso(datetime.now(timezone.utc)),
        "symbols": list(SYMBOLS), "interval": "1d", "data_start": "2005-01-01", "data_end_exclusive": "2026-10-01",
        "windows": {"training": ["2005-01-01", "2013-01-01"], "warmup_gap": ["2013-01-01", "2017-01-01"],
                    "historical_holdout": ["2017-01-01", "2024-01-01"], "confirmation": ["2024-01-01", "2026-10-01"]},
        "strategy_ids": list(STRATEGY_IDS), "sources": source_records(),
        "rules": {
            "qc_ema_15_30": "Daily EMA15/EMA30 seeded with each period's SMA; flat entry fast>slow*1.00015, long exit fast<slow; equality holds; stop permits next fresh daily level re-entry",
            "bt_sma_10_30": "Daily SMA10/SMA30; enter only previous difference<0 and current difference>0; exit only previous difference>0 and current difference<0; equality breaks a crossover; stop requires a new strict crossover",
            "faber_sma_10m": "Only first new calendar-month session open: use previous completed month close and arithmetic mean of its last10 completed month-end closes; >enter,<exit,=hold; after stop re-entry only at next monthly decision",
        },
        "execution": {"entry_exit": "Closed information only; next session open; never same-close signal fill; long/cash only",
                      "stop": "Fixed3*WilderATR14 from last closed decision bar, relative to adverse entry fill; never trailed; no profit target",
                      "stops": "Opening gap below stop fills at opening; intrabar low<=stop fills stop; indicator exit at opening before later intrabar extremes",
                      "final_close": "Liquidate at final sample close; no opening new positions on final bar",
                      "segment_state": "Every training, validation, historical and confirmation segment starts flat with independent initial cash; causal indicators may use earlier bars; no trade crosses a boundary"},
        "portfolio": {"account_size": 100000, "bucket_fraction": .2, "bucket_account_size": 20000,
                      "bucket_risk_pct": 1.25, "initial_risk_per_constituent": 250,
                      "maximum_initial_aggregate_stop_risk_pct": 1.25, "maximum_gross_notional_fraction": 1.0,
                      "quantity_step": 1, "contract_multiplier": 1, "cash_interest": 0,
                      "cash_reservation": "Equal fixed20% capital buckets, own realized-equity compounding; entry notional plus fee cannot exceed bucket cash equity; no capital transferred between ETFs"},
        "costs": {"fee_bps_per_side": 2, "slippage_bps_per_side": 1, "full_spread_bps": 1,
                  "annual_financing_stress_rates": [.04, .08], "funding_basis": "Previous closed notional for each elapsed UTC calendar date on a carried position, including weekends; debit before next opening exits",
                  "price_basis": "Original Yahoo OHLC quote; adjclose never used; no dividends credited, no future dividend adjustments fabricated; price-only may change signals, not simply conservatively subtract income",
                  "status": "Predeclared research assumptions; not verified broker/CFD tariffs"},
        "selection": {"objective": "Aggregate training net_return_pct-0.7*worst_bar_drawdown_pct; exact ties strategy_id lexical; no parameter fit",
                      "primary": "One family only, across the full fixed five-ETF portfolio; lock before any historical or confirmation performance",
                      "train_validation_windows": [["2007-01-01", "2009-01-01"], ["2009-01-01", "2011-01-01"], ["2011-01-01", "2013-01-01"]]},
        "inference": {"unit": "Synchronized aggregate portfolio calendar-month returns, never independently resampled asset trades",
                      "moving_block_months": 3, "resamples": 5000, "confidence": .99, "seed": 6022017,
                      "minimum_months": 24, "minimum_closed_trades_per_segment": 20,
                      "trade_count": "Aggregate asset trades are descriptive, not20independent portfolio observations"},
        "qualification": {"both_windows_required": True, "net_profit_positive": True, "min_profit_factor": 1.2,
                          "monthly_ci99_lower_above": 0, "max_drawdown_pct": 8,
                          "min_positive_training_validation_fraction": 2/3,
                          "financing4pct_both_positive": True, "financing8pct_report_only": True,
                          "risk_matched_benchmark": "Baseline scale=training portfolio daily-return volatility / same-five-ETF1x buyhold volatility, cap1; freeze before holdouts; baseline rebought flat each segment",
                          "real_prop_fit": "Not established: ETF OHLC is not executable firm CFD/futures; overnight/weekend-forbidden products excluded"},
        "scope": "This project's ETF inputs are new, but common equity factors overlap past stock/index studies. Historical periods and source authors are not globally blind. No new hypotheses, symbols, dates or thresholds after results.",
        "orders": "Research and paper planning only; no live orders, broker login, deposit, purchase, payout promise or verified real firm",
    }


def freeze(output=OUTPUT, snapshots=SNAPSHOTS):
    if output.exists():
        report = json.loads(output.read_text(encoding="utf-8"))
        if digest(report["protocol"]) != report["protocol_sha256"]:
            raise ValueError("Frozen protocol hash mismatch; preserve and investigate")
        return report
    protocol = make_protocol()
    report = {"phase": "predeclared", "protocol": protocol, "protocol_sha256": digest(protocol)}
    immutable_write(snapshots / "protocol.json", canonical(protocol) + "\n")
    write_report(output, report)
    return report


def _sma(values, period):
    result = [None] * len(values)
    for i in range(period-1, len(values)):
        result[i] = sum(values[i-period+1:i+1]) / period
    return result


def _ema(values, period):
    result = [None] * len(values)
    if len(values) >= period:
        current = sum(values[:period]) / period
        result[period-1] = current
        alpha = 2 / (period+1)
        for i in range(period, len(values)):
            current = alpha*values[i] + (1-alpha)*current
            result[i] = current
    return result


def strategy_decisions(bars, strategy_id):
    """Opening decisions at i use prices only through i-1, even for months."""
    if strategy_id not in STRATEGY_IDS:
        raise ValueError("Unknown predeclared family")
    closes = [bar["close"] for bar in bars]
    atr = strategies.atr(bars, 14)
    result = [None] * len(bars)
    if strategy_id != "faber_sma_10m":
        fast = _ema(closes, 15) if strategy_id == "qc_ema_15_30" else _sma(closes, 10)
        slow = _ema(closes, 30) if strategy_id == "qc_ema_15_30" else _sma(closes, 30)
        for i in range(1, len(bars)):
            j = i-1
            if slow[j] is None or atr[j] is None:
                continue
            if strategy_id == "qc_ema_15_30":
                entry, exit_ = fast[j] > slow[j]*1.00015, fast[j] < slow[j]
            else:
                previous = fast[j-1]-slow[j-1] if j > 0 and slow[j-1] is not None else None
                difference = fast[j]-slow[j]
                entry = previous is not None and previous < 0 and difference > 0
                exit_ = previous is not None and previous > 0 and difference < 0
            result[i] = {"entry": entry, "exit": exit_, "atr": atr[j], "signal_time": bars[j]["time"]}
    else:
        month_ends = []
        for i in range(1, len(bars)):
            if bars[i]["time"][:7] == bars[i-1]["time"][:7]:
                continue
            month_ends.append(closes[i-1])
            if len(month_ends) < 10 or atr[i-1] is None:
                continue
            average = sum(month_ends[-10:]) / 10
            price = month_ends[-1]
            result[i] = {"entry": price > average, "exit": price < average,
                         "atr": atr[i-1], "signal_time": bars[i-1]["time"]}
    return result


def _metrics(curve, trades, initial):
    final = curve[-1]["equity"] if curve else initial
    wins = [trade["pnl"] for trade in trades if trade["pnl"] > 0]
    losses = [-trade["pnl"] for trade in trades if trade["pnl"] < 0]
    costs = {key: sum(trade.get(key, 0) for trade in trades) for key in ("fees", "slippage", "spread", "financing_total", "total_costs")}
    return {"initial_equity": initial, "final_equity": round(final, 6), "net_profit": round(final-initial, 6),
            "net_return_pct": round((final/initial-1)*100, 6), "total_trades": len(trades),
            "winning_trades": len(wins), "losing_trades": len(losses),
            "win_rate": round(len(wins)/len(trades)*100, 4) if trades else 0,
            "profit_factor": round(sum(wins)/sum(losses), 6) if losses else None,
            "expectancy_r": round(statistics.mean(trade["return_r"] for trade in trades), 6) if trades else 0,
            "max_drawdown_pct": max((point["drawdown_pct"] for point in curve), default=0),
            "max_drawdown_amount": max((point["drawdown_amount"] for point in curve), default=0),
            "min_equity": min((point["worst_equity"] for point in curve), default=initial),
            "average_hold_bars": round(statistics.mean(trade["bars_held"] for trade in trades), 4) if trades else 0,
            "drawdown_method": "Synchronized sum of OHLC liquidation bounds against prior aggregate closing high water",
            **{key: round(value, 6) for key, value in costs.items()}}


def simulate_asset(bars, decisions, config, *, start=0, end=None, financing_rate=0, baseline_scale=None):
    """Costed fixed-stop long/cash fills, starting flat at each segment.

    balance is realized account equity, not principal-subtracted stock cash.
    Entry cash reservation nevertheless bounds notional+fee to available cash.
    """
    end = len(bars) if end is None else end
    if not 0 <= start < end <= len(bars) or len(decisions) != len(bars):
        raise ValueError("Invalid simulation range/decision count")
    if not math.isfinite(financing_rate) or not 0 <= financing_rate <= 1:
        raise ValueError("Invalid annual financing rate")
    if baseline_scale is not None and (not math.isfinite(baseline_scale) or not 0 <= baseline_scale <= 1):
        raise ValueError("Invalid baseline exposure scale")
    initial, balance, peak = config["account_size"], config["account_size"], config["account_size"]
    position, trades, curve = None, [], []
    friction = backtest._friction_fraction(config)
    params = {"stop_atr": 3, "reward_risk": 2, "max_hold_bars": 100000}
    for i in range(start, end):
        bar, observation = bars[i], decisions[i]
        previous_position = position is not None
        opening_balance = balance
        if position is not None and financing_rate and i > start:
            elapsed_days = (market.utc_datetime(bar["time"]).date()-market.utc_datetime(bars[i-1]["time"]).date()).days
            funding = position["quantity"]*bars[i-1]["close"]*config["contract_multiplier"]*financing_rate*elapsed_days/365
            balance -= funding
            position["financing_total"] += funding
        opening_equity = balance + (position["quantity"]*(bar["open"]-position["entry_price"])*config["contract_multiplier"] if position else 0)
        if not previous_position and i < end-1 and balance > 0:
            entry = baseline_scale is not None and i == start and baseline_scale > 0
            if baseline_scale is None:
                entry = bool(observation and observation.get("entry") and not observation.get("exit"))
            if entry:
                signal = {"direction": 1, "atr": observation["atr"] if observation else 1, "regime": "sourced_fixed_policy"}
                signal_time = observation.get("signal_time", bars[i-1]["time"] if i else bar["time"]) if observation else (bars[i-1]["time"] if i else bar["time"])
                position = backtest._open_position(bar, signal, {**params, "baseline": baseline_scale is not None}, config, balance, i, signal_time)
                if position:
                    cash_unit = position["entry_price"]*config["contract_multiplier"]*(1+config["fee_bps"]/10000)+config["fee_per_unit"]
                    position["quantity"] = min(position["quantity"], balance/cash_unit)
                    if baseline_scale is not None:
                        position["quantity"] *= baseline_scale
                    if config["quantity_step"]:
                        position["quantity"] = math.floor(position["quantity"]/config["quantity_step"]+1e-12)*config["quantity_step"]
                    if position["quantity"] <= 0:
                        position = None
                    else:
                        position["entry_fee"] = backtest._fee(position["entry_price"], position["quantity"], config)
                        position["target"] = None
                        position["financing_total"] = 0.0
                        balance -= position["entry_fee"]
        raw_exit, reason = None, None
        if position:
            stop = position["stop"]
            if stop is not None and bar["open"] <= stop:
                raw_exit, reason = bar["open"], "gap_stop"
                adverse = favorable = bar["open"]
            elif previous_position and baseline_scale is None and observation and observation.get("exit"):
                raw_exit, reason = bar["open"], "signal_exit"
                adverse = favorable = bar["open"]
            elif stop is not None and bar["low"] <= stop:
                raw_exit, reason = stop, "stop"
                adverse, favorable = stop, bar["high"]
            else:
                adverse, favorable = bar["low"], bar["high"]
                if i == end-1:
                    raw_exit, reason = bar["close"], "end_of_sample"
            worst_equity = position["entry_balance"]+backtest._liquidation_pnl(position, adverse, config)-position["financing_total"]
            best_equity = position["entry_balance"]+backtest._liquidation_pnl(position, favorable, config)-position["financing_total"]
            position["mae_r"] = max(position["mae_r"], (position["entry_balance"]-worst_equity)/position["risk_amount"], 0)
            position["mfe_r"] = max(position["mfe_r"], (best_equity-position["entry_balance"])/position["risk_amount"], 0)
            if raw_exit is not None:
                fill = raw_exit*(1-friction)
                exit_fee = backtest._fee(fill, position["quantity"], config)
                gross_filled = (fill-position["entry_price"])*position["quantity"]*config["contract_multiplier"]
                pnl = gross_filled-position["entry_fee"]-exit_fee-position["financing_total"]
                balance += gross_filled-exit_fee
                notional = position["quantity"]*config["contract_multiplier"]*(position["raw_entry"]+raw_exit)
                fees = position["entry_fee"]+exit_fee
                slip, spread = notional*config["slippage_bps"]/10000, notional*config["spread_bps"]/20000
                trades.append({"symbol": config["symbol"], "direction": "long", "entry_time": position["entry_time"],
                               "signal_time": position["signal_time"], "exit_time": bar["time"], "entry_price": position["entry_price"],
                               "exit_price": fill, "raw_entry_price": position["raw_entry"], "raw_exit_price": raw_exit,
                               "quantity": position["quantity"], "contract_multiplier": config["contract_multiplier"], "stop": stop,
                               "risk_amount": position["risk_amount"], "pnl": pnl,
                               "gross_pnl": (raw_exit-position["raw_entry"])*position["quantity"]*config["contract_multiplier"],
                               "return_r": pnl/position["risk_amount"], "net_r": pnl/position["risk_amount"],
                               "fees": fees, "slippage": slip, "spread": spread, "financing_total": position["financing_total"],
                               "total_costs": fees+slip+spread+position["financing_total"],
                               "mae_r": position["mae_r"], "mfe_r": position["mfe_r"], "exit_reason": reason,
                               "bars_held": i-position["entry_index"]+1, "excursion_method": "OHLC bounds; unknown intraday ordering"})
                position = None
                closing = balance
            else:
                closing = balance+(bar["close"]-position["entry_price"])*position["quantity"]*config["contract_multiplier"]
        else:
            worst_equity = best_equity = closing = balance
        amount = max(0, peak-min(worst_equity, closing))
        curve.append({"time": bar["time"], "balance": balance, "equity": closing,
                      "opening_balance": opening_balance, "opening_equity": opening_equity,
                      "worst_equity": min(worst_equity, closing), "best_equity": max(best_equity, closing),
                      "drawdown_amount": amount, "drawdown_pct": amount/peak*100 if peak > 0 else 0})
        peak = max(peak, closing)
    return {"metrics": _metrics(curve, trades, initial), "trades": trades, "equity_curve": curve}


def aggregate_monthly_returns(curve, initial):
    """One synchronized portfolio return per observed calendar month."""
    endpoints = {}
    for point in curve:
        endpoints[point["time"][:7]] = point["equity"]
    previous, returns = initial, []
    for month, equity in endpoints.items():
        returns.append({"month": month, "return": equity/previous-1})
        previous = equity
    return returns


def portfolio_result(datasets, strategy_id, start_date, end_date, *, financing_rate=0, baseline_scale=None):
    if set(datasets) != set(SYMBOLS):
        raise ValueError("All five frozen ETFs are required; no survivor substitution")
    calendars = [[bar["time"] for bar in datasets[symbol]] for symbol in SYMBOLS]
    if any(calendar != calendars[0] for calendar in calendars[1:]):
        raise ValueError("ETFs must have the same source sessions; no imputation/date cherry-picking")
    active = [i for i, stamp in enumerate(calendars[0]) if start_date <= stamp[:10] < end_date]
    if not active:
        raise ValueError("No bars in the declared segment")
    asset_results, all_trades = {}, []
    for symbol in SYMBOLS:
        config = backtest.normalize_config({"symbol": symbol, "source": "csv", "account_size": 20000,
                                            "risk_pct": 1.25, "max_leverage": 1, "quantity_step": 1,
                                            "fee_bps": 2, "slippage_bps": 1, "spread_bps": 1})
        decisions = strategy_decisions(datasets[symbol], strategy_id)
        result = simulate_asset(datasets[symbol], decisions, config, start=active[0], end=active[-1]+1,
                                financing_rate=financing_rate, baseline_scale=baseline_scale)
        asset_results[symbol] = result
        all_trades.extend(result["trades"])
    curve, peak = [], 100000
    for i in range(len(active)):
        points = [asset_results[symbol]["equity_curve"][i] for symbol in SYMBOLS]
        point = {key: sum(row[key] for row in points) for key in ("balance", "equity", "opening_balance", "opening_equity", "worst_equity", "best_equity")}
        amount = max(0, peak-point["worst_equity"])
        point.update({"time": points[0]["time"], "drawdown_amount": amount, "drawdown_pct": amount/peak*100})
        peak = max(peak, point["equity"])
        curve.append(point)
    all_trades.sort(key=lambda trade: (trade["exit_time"], trade["symbol"], trade["entry_time"]))
    metrics = _metrics(curve, all_trades, 100000)
    first, last = market.utc_datetime(curve[0]["time"]), market.utc_datetime(curve[-1]["time"])
    years = max((last-first).days/365.25, 1/365.25)
    metrics["annualized_return_pct"] = ((metrics["final_equity"]/100000)**(1/years)-1)*100 if metrics["final_equity"] > 0 else -100
    monthly = aggregate_monthly_returns(curve, 100000)
    metrics["monthly_observations"] = len(monthly)
    return {"metrics": metrics, "trades": all_trades, "equity_curve": curve,
            "monthly_returns": monthly, "asset_results": asset_results,
            "data": {"start": curve[0]["time"], "end": curve[-1]["time"], "bars": len(curve)}}


def monthly_bootstrap(monthly_returns, *, resamples=5000, confidence=.99, seed=6022017):
    values = [row["return"] for row in monthly_returns]
    if len(values) < 2:
        return {"months": len(values), "mean_monthly_ci_pct": None, "method": "Insufficient synchronized portfolio months"}
    block = min(3, len(values))
    rng, means = random.Random(seed+len(values)), []
    for _ in range(resamples):
        sample = []
        while len(sample) < len(values):
            start = rng.randrange(len(values)-block+1)
            sample.extend(values[start:start+block])
        means.append(statistics.mean(sample[:len(values)])*100)
    means.sort()
    tail = (1-confidence)/2
    return {"months": len(values), "mean_monthly_return_pct": statistics.mean(values)*100,
            "mean_monthly_ci_pct": [means[int(tail*(resamples-1))], means[int((1-tail)*(resamples-1))]],
            "confidence": confidence, "block_months": block, "resamples": resamples,
            "method": "Moving-block bootstrap of synchronized portfolio calendar-month returns; descriptive, not IID trades or a guarantee"}


def _daily_vol(result):
    previous, returns = 100000, []
    for point in result["equity_curve"]:
        returns.append(point["equity"]/previous-1)
        previous = point["equity"]
    return statistics.stdev(returns) if len(returns) > 1 else 0


def _rule_profiles():
    shared = {"account_size": 100000, "daily_loss_pct": 5, "max_loss_pct": 10, "profit_target_pct": 8,
              "min_trading_days": 5, "daily_reset_timezone": "UTC", "status": "illustrative", "quantity_step": 1,
              "max_calendar_days": 60, "overnight_allowed": True, "weekend_allowed": True, "news_allowed": None}
    return [normalize_profile({**shared, "id": "sourced-generic-static", "name": "Illustrative static10/daily5", "drawdown_type": "static"}),
            normalize_profile({**shared, "id": "sourced-generic-eod", "name": "Illustrative trailingEOD5/daily5", "max_loss_pct": 5, "drawdown_type": "trailing_eod"}),
            normalize_profile({**shared, "id": "sourced-generic-intraday", "name": "Illustrative trailing intraday5/daily5", "max_loss_pct": 5, "drawdown_type": "trailing_intraday"})]


def _replays(result):
    return {profile["id"]: compliance.evaluate(result["equity_curve"], profile, result["trades"]) for profile in _rule_profiles()}


def _compact_result(result):
    return {"metrics": result["metrics"], "trades": result["trades"], "equity_curve": result["equity_curve"],
            "monthly_returns": result["monthly_returns"], "data": result["data"],
            "asset_metrics": {symbol: value["metrics"] for symbol, value in result["asset_results"].items()}}


def training_lock(datasets, protocol):
    start, end = protocol["windows"]["training"]
    baseline = portfolio_result(datasets, STRATEGY_IDS[0], start, end, baseline_scale=1)
    baseline_vol = _daily_vol(baseline)
    candidates = []
    for strategy_id in STRATEGY_IDS:
        result = portfolio_result(datasets, strategy_id, start, end)
        ratio = _daily_vol(result)/baseline_vol if baseline_vol else 0
        scale = min(1, ratio)
        matched = portfolio_result(datasets, strategy_id, start, end, baseline_scale=scale)
        folds = []
        for window in protocol["selection"]["train_validation_windows"]:
            fold = portfolio_result(datasets, strategy_id, *window)
            folds.append({"window": window, "metrics": fold["metrics"]})
        candidates.append({"id": strategy_id, "name": NAMES[strategy_id], "train_metrics": result["metrics"],
                           "train_score": result["metrics"]["net_return_pct"]-.7*result["metrics"]["max_drawdown_pct"],
                           "walk_forward": {"folds": folds, "positive_fraction": sum(row["metrics"]["net_profit"] > 0 for row in folds)/len(folds),
                                            "total_trades": sum(row["metrics"]["total_trades"] for row in folds)},
                           "benchmark": {"scale": scale, "uncapped_volatility_ratio": ratio,
                                         "training_strategy_daily_vol": _daily_vol(result), "training_buyhold1x_daily_vol": baseline_vol,
                                         "training_matched_buyhold_daily_vol": _daily_vol(matched), "train_metrics": matched["metrics"],
                                         "matching": "Train-only daily-return volatility ratio, cap1; integer-share rounding means approximate attained match"}})
    winner = sorted(candidates, key=lambda row: (-row["train_score"], row["id"]))[0]
    return {"recorded_at": iso(datetime.now(timezone.utc)), "primary_strategy_id": winner["id"],
            "candidates": candidates, "protocol_sha256": digest(protocol),
            "selection_basis": "Training portfolio score only; benchmark scales fit on training only; no gap or holdout performance"}


def _window_evidence(result, confidence, stress4, replays, protocol):
    metrics, gates = result["metrics"], protocol["qualification"]
    reasons = []
    if metrics["total_trades"] < 20:
        reasons.append("Fewer than20 aggregate closed asset trades; these are not IID independent observations")
    if metrics["net_profit"] <= 0 or metrics["expectancy_r"] <= 0:
        reasons.append("Net profit or mean tradeR is not positive after declared costs")
    if metrics["profit_factor"] is not None and metrics["profit_factor"] < gates["min_profit_factor"]:
        reasons.append("Profit factor below1.20")
    interval = confidence["mean_monthly_ci_pct"]
    if confidence["months"] < 24 or interval is None or interval[0] <= 0:
        reasons.append("Descriptive99% synchronized-month interval includes zero or has fewer than24 months")
    if metrics["max_drawdown_pct"] >= gates["max_drawdown_pct"]:
        reasons.append("Worst-bar aggregate drawdown reaches8%")
    if stress4["metrics"]["net_profit"] <= 0:
        reasons.append("Net profit does not remain positive under4% annual calendar-day carry stress")
    if replays["sourced-generic-static"]["status"] != "pass":
        reasons.append("Illustrative static account-rule replay does not pass")
    return reasons


def evaluate_locked(datasets, lock, protocol):
    results = []
    for candidate in lock["candidates"]:
        strategy_id = candidate["id"]
        windows = {}
        for key in ("historical_holdout", "confirmation"):
            start, end = protocol["windows"][key]
            result = portfolio_result(datasets, strategy_id, start, end)
            baseline = portfolio_result(datasets, strategy_id, start, end, baseline_scale=candidate["benchmark"]["scale"])
            stress4 = portfolio_result(datasets, strategy_id, start, end, financing_rate=.04)
            stress8 = portfolio_result(datasets, strategy_id, start, end, financing_rate=.08)
            confidence, replays = monthly_bootstrap(result["monthly_returns"]), _replays(result)
            paired = [{"month": row["month"], "return": row["return"]-other["return"]}
                      for row, other in zip(result["monthly_returns"], baseline["monthly_returns"])]
            excess = monthly_bootstrap(paired)
            reasons = _window_evidence(result, confidence, stress4, replays, protocol)
            windows[key] = {**_compact_result(result), "confidence": confidence, "rule_replay": replays,
                            "stress4pct": {"metrics": stress4["metrics"], "rule_replay": _replays(stress4)},
                            "stress8pct": {"metrics": stress8["metrics"], "rule_replay": _replays(stress8)},
                            "risk_matched_buyhold": {"frozen_scale": candidate["benchmark"]["scale"], "metrics": baseline["metrics"],
                                                     "monthly_returns": baseline["monthly_returns"], "rule_replay": _replays(baseline)},
                            "excess_over_risk_matched_buyhold_pct": result["metrics"]["net_return_pct"]-baseline["metrics"]["net_return_pct"],
                            "paired_monthly_excess_confidence": excess, "evidence_reasons": reasons, "passes_window": not reasons}
        reasons = [key+": "+reason for key, value in windows.items() for reason in value["evidence_reasons"]]
        if candidate["walk_forward"]["positive_fraction"] < 2/3:
            reasons.append("Training validation is not positive in at least two-thirds of fixed windows")
        if candidate["train_metrics"]["net_profit"] <= 0:
            reasons.append("Training net profit is not positive")
        primary = strategy_id == lock["primary_strategy_id"]
        if not primary:
            reasons.append("Diagnostic family only; cannot replace the family locked on training")
        results.append({"id": strategy_id, "name": candidate["name"], "primary": primary, "eligible_historical_price_model": not reasons,
                        "reasons": reasons, "training": candidate, "windows": windows,
                        "real_prop_qualified": False, "real_prop_reasons": ["ETF source is not firm CFD/futures execution data; asset availability, charges, contract sizes and current rules unverified",
                                                                             "Overnight/weekend-forbidden products cannot use this holding policy",
                                                                             "Generic modeled loss floors do not verify account challenge, news/session compliance or payout"]})
    return results


def run(output=OUTPUT, snapshots=SNAPSHOTS):
    report = freeze(output, snapshots)
    if report["phase"] == "final_review":
        return report
    if report["phase"] == "source_incomplete":
        raise ValueError("Fixed portfolio source incomplete; only the documented parser correction can proceed")
    datasets_raw = snapshot_prices(report, output, snapshots)
    if report["phase"] != "prices_snapshotted":
        raise ValueError("All five immutable sources required before training")
    datasets = {symbol: datasets_raw[symbol]["bars"] for symbol in SYMBOLS}
    report["execution_producer_before_performance"] = {"recorded_at": iso(datetime.now(timezone.utc)), "script_sha256": file_digest(Path(__file__)),
                                                        "core": {name: file_digest(ROOT/"propdesk"/name) for name in report["producer_before_first_fetch"]["core"]},
                                                        "illustrative_rule_profiles": _rule_profiles()}
    write_report(output, report)
    started = time.monotonic()
    lock = training_lock(datasets, report["protocol"])
    immutable_write(snapshots/"training-lock.json", canonical(lock)+"\n")
    report["training_lock"], report["training_lock_sha256"] = lock, digest(lock)
    report["phase"] = "training_locked"
    write_report(output, report)
    print("Training family locked: "+lock["primary_strategy_id"]+"; evaluating the two predeclared windows", flush=True)
    report["strategies"] = evaluate_locked(datasets, lock, report["protocol"])
    primary = next(row for row in report["strategies"] if row["primary"])
    report.update({"phase": "final_review", "finished_at": iso(datetime.now(timezone.utc)), "elapsed_seconds": time.monotonic()-started,
                   "primary_strategy_id": primary["id"], "selected_strategy_id": primary["id"] if primary["eligible_historical_price_model"] else None,
                   "decision": "Qualified historical price-model candidate for prospective paper validation" if primary["eligible_historical_price_model"] else "Primary family does not pass both predeclared evidence windows; no substitution",
                   "live_orders": False, "real_prop_qualified": False,
                   "limitations": ["Price-only OHLC omits dividends and cash interest; that can alter crossings/stop decisions, not simply subtract income",
                                   "Current source receipts are retrospective; vendor split-normalized units are not unadjusted historical integer shares",
                                   "ETF factors overlap previously seen stocks/indexes; no claim of globally independent or blind economic regimes",
                                   "Month bootstrap is descriptive and source/rule-selection uncertainty remains; positive history does not guarantee future profit",
                                   "Seven-year or33-month profit is not a fast challenge/payout result; exact equity reset, news and execution are unverified"]})
    write_report(output, report)
    return report


def _parse_us_etf(payload, symbol, received):
    # Reuse structural/feed validation, then correct only the daily close clock
    # for this explicitly US-listed fixed universe. No price is changed.
    dataset = feeds.parse_chart(payload, symbol, "1d", "max", now=received)
    response = payload["chart"]["result"][0]
    metadata = response["meta"]
    if metadata.get("currency") != "USD" or metadata.get("exchangeTimezoneName") != "America/New_York":
        raise ValueError("US ETF currency/session metadata does not match the frozen universe")
    zone = timezone_for("America/New_York")
    quotes = response["indicators"]["quote"][0]
    bars = []
    for index, epoch in enumerate(response["timestamp"]):
        if epoch is None:
            continue
        stamp = datetime.fromtimestamp(epoch, timezone.utc)
        local_date = stamp.astimezone(zone).date()
        conservative_close = datetime.combine(local_date, time_of_day(16), zone).astimezone(timezone.utc)
        if conservative_close > received or local_date.weekday() >= 5:
            continue
        values = {field: quotes[field][index] if index < len(quotes[field]) else None for field in ("open", "high", "low", "close")}
        if any(value is None for value in values.values()):
            continue
        volume = quotes.get("volume")
        values["volume"] = volume[index] if isinstance(volume, list) and index < len(volume) and volume[index] is not None else 0
        bars.append({"time": iso(stamp), **values})
    dataset["bars"] = market.validate_bars(bars)
    last_open = market.utc_datetime(bars[-1]["time"])
    last_close = datetime.combine(last_open.astimezone(zone).date(), time_of_day(16), zone).astimezone(timezone.utc)
    dataset["provenance"].update({"last_closed_at": iso(last_close), "last_closed_bar_open": bars[-1]["time"],
                                   "daily_close_method": "US ETF America/New_York16:00 conservative session close; earlier half-days accepted only after16:00"})
    return dataset


def _download(symbol, protocol, directory, *, corrected=False):
    if symbol not in SYMBOLS:
        raise ValueError("Undeclared symbol")
    started = datetime.now(timezone.utc)
    start = int(datetime.fromisoformat(protocol["data_start"]).replace(tzinfo=timezone.utc).timestamp())
    end = int(datetime.fromisoformat(protocol["data_end_exclusive"]).replace(tzinfo=timezone.utc).timestamp())
    url = "https://query1.finance.yahoo.com/v8/finance/chart/" + symbol + "?" + urlencode({
        "period1": start, "period2": end, "interval": "1d", "includePrePost": "false", "events": "div,splits",
    })
    payload = feeds._request_json(url)
    received = datetime.now(timezone.utc)
    dataset = _parse_us_etf(payload, symbol, received) if corrected else feeds.parse_chart(payload, symbol, "1d", "max", now=received)
    bars = dataset["bars"]
    if len(bars) < 3000 or any(not protocol["data_start"] <= bar["time"][:10] < protocol["data_end_exclusive"] for bar in bars):
        raise ValueError("History availability/date window does not satisfy the frozen experiment")
    actions = payload["chart"]["result"][0].get("events") or {}
    provenance = dataset["provenance"]
    provenance.update({"source_url": url, "range": "explicit frozen start/end", "requested_at": iso(started),
                       "retrieved_at": iso(received), "period_start": protocol["data_start"],
                       "period_end_exclusive": protocol["data_end_exclusive"], "dividend_policy": "No dividends credited; raw quote price-only, never adjclose",
                       "dividend_events_present": bool(actions.get("dividends")), "split_events_present": bool(actions.get("splits")),
                       "split_events": actions.get("splits") or {}, "quote_units": "Vendor split-normalized price/share units; not literal unadjusted historical shares; no own split applied",
                       "license": "Public accessibility is not a redistribution license; local raw snapshots excluded from Git/packages"})
    suffix = "-1d-close-corrected" if corrected else "-1d"
    json_path, csv_path = directory / (symbol + suffix + ".json"), directory / (symbol + suffix + ".csv")
    immutable_write(json_path, canonical(dataset) + "\n")
    immutable_write(csv_path, market.to_csv(bars))
    receipt_path = directory / (symbol + suffix + "-provider-receipt.json")
    immutable_write(receipt_path, canonical(payload) + "\n")
    return dataset, {"symbol": symbol, "bars": len(bars), "start": bars[0]["time"], "end": bars[-1]["time"],
                     "json_path": str(json_path.relative_to(ROOT)), "json_sha256": file_digest(json_path),
                     "csv_path": str(csv_path.relative_to(ROOT)), "csv_sha256": file_digest(csv_path),
                     "bars_sha256": market.data_fingerprint(bars), "source_url": url,
                     "provider_receipt_path": str(receipt_path.relative_to(ROOT)), "provider_receipt_sha256": file_digest(receipt_path),
                     "provider_receipt_format": "Canonical JSON response content, not original HTTP whitespace bytes",
                     "requested_at": iso(started), "received_at": iso(received), "provenance": provenance}


def snapshot_prices(report, output=OUTPUT, snapshots=SNAPSHOTS):
    if report["phase"] != "predeclared":
        datasets = {}
        for record in report.get("snapshots", []):
            path = ROOT / record["json_path"]
            if file_digest(path) != record["json_sha256"]:
                raise ValueError("Snapshot fingerprint mismatch; no refetch/replacement")
            datasets[record["symbol"]] = json.loads(path.read_text(encoding="utf-8"))
        return datasets
    sources = ("market.py", "strategies.py", "backtest.py", "compliance.py", "risk.py", "feeds.py", "timezones.py")
    report["producer_before_first_fetch"] = {"core": {name: file_digest(ROOT / "propdesk" / name) for name in sources},
                                             "script_sha256": file_digest(Path(__file__)), "recorded_at": iso(datetime.now(timezone.utc))}
    write_report(output, report)
    datasets, records, errors = {}, {}, {}
    with ThreadPoolExecutor(max_workers=2) as executor:
        requests = {executor.submit(_download, symbol, report["protocol"], snapshots): symbol for symbol in SYMBOLS}
        for future in as_completed(requests):
            symbol = requests[future]
            try:
                datasets[symbol], records[symbol] = future.result()
            except (ValueError, OSError) as error:
                errors[symbol] = str(error) if isinstance(error, ValueError) else "Snapshot save/read failed"
    report["snapshots"] = [records[symbol] for symbol in SYMBOLS if symbol in records]
    report["source_errors"] = errors
    report["phase"] = "prices_snapshotted" if not errors else "source_incomplete"
    report["snapshot_finished_at"] = iso(datetime.now(timezone.utc))
    write_report(output, report)
    return datasets


def correct_snapshots(report, output=OUTPUT, snapshots=SNAPSHOTS):
    if report["phase"] != "source_incomplete" or set(report["source_errors"]) != {"IWM"}:
        raise ValueError("Only the documented pre-performance parser correction can recover this attempt")
    report["initial_snapshot_attempt"] = {key: report[key] for key in ("phase", "snapshots", "source_errors", "snapshot_finished_at")}
    report["data_parser_correction"] = {
        "recorded_at": iso(datetime.now(timezone.utc)), "before_any_performance": True,
        "reason": "Vendor IWM2:1 split metadata in2005 is not a universe failure: preserve original quote units, never split prices again. Correct US ETF close clock from open+24h to NY16:00 so an already closedSep30session is retained.",
        "scope": "Rules, portfolio, costs, windows and thresholds unchanged; initial snapshot files/hashes retained; new response/derived files are separate",
    }
    write_report(output, report)
    datasets, records = {}, {}
    with ThreadPoolExecutor(max_workers=2) as executor:
        requests = {executor.submit(_download, symbol, report["protocol"], snapshots, corrected=True): symbol for symbol in SYMBOLS}
        for future in as_completed(requests):
            symbol = requests[future]
            datasets[symbol], records[symbol] = future.result()
    for original in report["initial_snapshot_attempt"]["snapshots"]:
        old = json.loads((ROOT/original["json_path"]).read_text(encoding="utf-8"))
        if datasets[original["symbol"]]["bars"][:len(old["bars"])] != old["bars"]:
            raise ValueError("Provider revised existing snapshot prices during parser correction; investigate without performance testing")
    iwm = datasets["IWM"]
    split = next(iter(iwm["provenance"]["split_events"].values()))
    split_date = datetime.fromtimestamp(split["date"], timezone.utc).date().isoformat()
    index = next(i for i, bar in enumerate(iwm["bars"]) if bar["time"][:10] == split_date)
    ratio = iwm["bars"][index]["open"]/iwm["bars"][index-1]["close"]
    if not .7 < ratio < 1.3:
        raise ValueError("IWM training split shows discontinuous quote units; source conventions need independent audit")
    report["data_parser_correction"]["IWM_training_split_audit"] = {"date": split_date, "provider_split": split,
                                                                      "opening_to_previous_close_ratio": ratio,
                                                                      "interpretation": "Continuous vendor-normalized quote units, not unadjusted2:1 historical prices"}
    report["snapshots"] = [records[symbol] for symbol in SYMBOLS]
    report["source_errors"] = {}
    report["phase"] = "prices_snapshotted"
    report["snapshot_finished_at"] = iso(datetime.now(timezone.utc))
    write_report(output, report)
    return datasets


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--freeze", action="store_true")
    parser.add_argument("--snapshot", action="store_true")
    parser.add_argument("--correct-data-parser", action="store_true")
    arguments = parser.parse_args()
    if arguments.freeze:
        report = freeze()
        print(canonical({"phase": report["phase"], "protocol_sha256": report["protocol_sha256"], "frozen_at": report["protocol"]["frozen_at"]}))
    elif arguments.correct_data_parser:
        report = freeze()
        correct_snapshots(report)
        print(canonical({"phase": report["phase"], "sources": [{"symbol": row["symbol"], "bars": row["bars"], "end": row["end"]} for row in report["snapshots"]], "correction": report["data_parser_correction"]}))
    elif arguments.snapshot:
        report = freeze()
        snapshot_prices(report)
        print(canonical({"phase": report["phase"], "sources": [{"symbol": row["symbol"], "bars": row["bars"], "start": row["start"], "end": row["end"]} for row in report.get("snapshots", [])], "errors": report.get("source_errors")}))
    else:
        report = run()
        print(canonical({"phase": report["phase"], "primary": report.get("primary_strategy_id"), "selected": report.get("selected_strategy_id"),
                         "strategies": [{"id": row["id"], "primary": row["primary"], "eligible": row["eligible_historical_price_model"],
                                         "windows": {name: {"net_return_pct": value["metrics"]["net_return_pct"], "trades": value["metrics"]["total_trades"],
                                                            "profit_factor": value["metrics"]["profit_factor"], "drawdown_pct": value["metrics"]["max_drawdown_pct"],
                                                            "ci99": value["confidence"]["mean_monthly_ci_pct"], "carry4_net": value["stress4pct"]["metrics"]["net_return_pct"],
                                                            "carry8_net": value["stress8pct"]["metrics"]["net_return_pct"]} for name,value in row["windows"].items()},
                                         "reasons": row["reasons"]} for row in report.get("strategies", [])]}))
