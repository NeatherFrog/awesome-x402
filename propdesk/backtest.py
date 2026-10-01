"""Causal, cost-aware research with frozen train choices and a final holdout.

This is an OHLC simulator, not a broker. Signals use closed bar i and entries
use open i+1. Stops win ambiguous stop/target collisions; adverse gaps execute
at the opening price. Reported drawdown includes adverse bar marks relative to
closing high-water equity. Synthetic data can never qualify a strategy.
"""

from __future__ import annotations

import math
import random
import statistics
from copy import deepcopy

from . import market, strategies

MIN_RESEARCH_BARS = 300
MIN_HOLDOUT_TRADES = 20


def _rounded(value: float, digits: int = 6) -> float:
    if not math.isfinite(value):
        raise ValueError("numerical overflow: check price scales, multiplier and account configuration")
    value = round(value, digits)
    return value if value else 0.0


def normalize_config(config: dict | None = None) -> dict:
    supplied = config or {}
    if not isinstance(supplied, dict):
        raise ValueError("research config must be an object")
    defaults = {"account_size": 100_000.0, "risk_pct": 0.25, "fee_bps": 0.4, "slippage_bps": 0.3, "spread_bps": 0.8, "train_fraction": 0.6, "max_leverage": 3.0, "contract_multiplier": 1.0, "quantity_step": 0.0, "fee_per_unit": 0.0, "max_drawdown_pct": 8.0}
    bounds = {"account_size": (100.0, 1e9), "risk_pct": (0.001, 5.0), "fee_bps": (0.0, 100.0), "slippage_bps": (0.0, 100.0), "spread_bps": (0.0, 200.0), "train_fraction": (0.5, 0.8), "max_leverage": (0.1, 50.0), "contract_multiplier": (1e-6, 1e9), "quantity_step": (0.0, 1e9), "fee_per_unit": (0.0, 1e6), "max_drawdown_pct": (0.1, 50.0)}
    normalized = {}
    for key, default in defaults.items():
        raw = supplied.get(key, default)
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise ValueError(f"{key} must be a finite number")
        value = float(raw)
        lower, upper = bounds[key]
        if not math.isfinite(value) or not lower <= value <= upper:
            raise ValueError(f"{key} must be between {lower:g} and {upper:g}")
        normalized[key] = value
    symbol = supplied.get("symbol", "EURUSD")
    if not isinstance(symbol, str) or not symbol.strip() or len(symbol) > 40:
        raise ValueError("symbol must be a nonempty string of at most 40 characters")
    normalized["symbol"] = symbol.strip().upper()
    source = supplied.get("source", "unknown")
    if not isinstance(source, str) or source not in ("demo", "csv", "unknown"):
        raise ValueError("source must be demo, csv or unknown")
    normalized["source"] = source
    supplied_ids = supplied.get("strategy_ids")
    allowed_ids = {item["id"] for item in strategies.catalog()}
    if supplied_ids is None:
        selected_ids = [item["id"] for item in strategies.catalog()]
    elif not isinstance(supplied_ids, list) or not supplied_ids or any(not isinstance(item, str) or item not in allowed_ids for item in supplied_ids):
        raise ValueError("strategy_ids must be a nonempty list of known strategy IDs")
    else:
        selected_ids = list(dict.fromkeys(supplied_ids))
        if "buy_hold" not in selected_ids:
            selected_ids.append("buy_hold")
    normalized["strategy_ids"] = selected_ids
    profile = supplied.get("prop_profile")
    if profile is not None and not isinstance(profile, dict):
        raise ValueError("prop_profile must be a rule profile object")
    if profile is not None:
        normalized["prop_profile"] = deepcopy(profile)
    return normalized


def _fee(fill: float, quantity: float, config: dict) -> float:
    return quantity * fill * config["contract_multiplier"] * config["fee_bps"] / 10_000.0 + quantity * config["fee_per_unit"]


def _friction_fraction(config: dict) -> float:
    return (config["slippage_bps"] + config["spread_bps"] / 2.0) / 10_000.0


def _liquidation_pnl(position: dict, raw_exit: float, config: dict) -> float:
    direction = position["direction"]
    fill = raw_exit * (1.0 - direction * _friction_fraction(config))
    return direction * (fill - position["entry_price"]) * position["quantity"] * config["contract_multiplier"] - position["entry_fee"] - _fee(fill, position["quantity"], config)


def _choose_exit(position: dict, bar: dict, index: int, last_index: int, params: dict) -> tuple[float | None, str | None, float, float]:
    """Return raw exit, reason and adverse/favourable raw mark bounds."""
    direction = position["direction"]
    adverse, favorable = (bar["low"], bar["high"]) if direction == 1 else (bar["high"], bar["low"])
    if params.get("baseline"):
        return (bar["close"], "end_of_sample", adverse, favorable) if index == last_index else (None, None, adverse, favorable)
    stop, target = position["stop"], position["target"]
    if (direction == 1 and bar["open"] <= stop) or (direction == -1 and bar["open"] >= stop):
        return bar["open"], "gap_stop", bar["open"], bar["open"]
    if (direction == 1 and bar["open"] >= target) or (direction == -1 and bar["open"] <= target):
        # Do not grant an optimistic price improvement for a favourable gap.
        return target, "gap_target", target, target
    stop_hit = bar["low"] <= stop if direction == 1 else bar["high"] >= stop
    target_hit = bar["high"] >= target if direction == 1 else bar["low"] <= target
    if stop_hit:
        # Once filled at the stop, do not charge the later bar extreme as if
        # still holding; an opening gap was handled separately above. A price
        # just short of target could have preceded the stop, so retain that
        # favourable *bound* for conservative intraday trailing-rule replay.
        favorable_bound = min(favorable, target) if direction == 1 else max(favorable, target)
        return stop, "stop_first_collision" if target_hit else "stop", stop, favorable_bound
    if target_hit:
        return target, "take_profit", adverse, target
    if index == last_index:
        return bar["close"], "end_of_sample", adverse, favorable
    if index - position["entry_index"] >= params["max_hold_bars"]:
        return bar["close"], "time_exit", adverse, favorable
    return None, None, adverse, favorable


def _open_position(bar: dict, observation: dict, params: dict, config: dict, balance: float, index: int, signal_time: str) -> dict | None:
    direction = observation["direction"]
    if direction not in (-1, 1):
        raise ValueError("signal direction must be -1 or 1")
    multiplier = config["contract_multiplier"]
    friction = _friction_fraction(config)
    baseline = params.get("baseline", False)
    entry = bar["open"] * (1.0 + direction * friction)
    notional_cap = balance * (min(1.0, config["max_leverage"]) if baseline else config["max_leverage"])
    if baseline:
        unit_total = entry * multiplier * (1 + config["fee_bps"] / 10_000.0) + config["fee_per_unit"]
        quantity = min(notional_cap / (entry * multiplier), balance / unit_total)
        stop = target = None
        risk_amount = balance
    else:
        signal_atr = observation.get("atr")
        if signal_atr is None or not math.isfinite(signal_atr) or signal_atr <= 0:
            return None
        stop_distance = signal_atr * params["stop_atr"]
        stop = entry - direction * stop_distance
        target = entry + direction * stop_distance * params["reward_risk"]
        if stop <= 0 or target <= 0:
            return None
        risk_amount = balance * config["risk_pct"] / 100.0
        cost_per_unit = 2.0 * entry * multiplier * (friction + config["fee_bps"] / 10_000.0) + 2.0 * config["fee_per_unit"]
        quantity = min(risk_amount / (stop_distance * multiplier + cost_per_unit), notional_cap / (entry * multiplier))
    if config["quantity_step"]:
        quantity = math.floor(quantity / config["quantity_step"] + 1e-12) * config["quantity_step"]
    if not math.isfinite(quantity) or quantity <= 0:
        return None
    entry_fee = _fee(entry, quantity, config)
    return {"direction": direction, "entry_index": index, "entry_time": bar["time"], "signal_time": signal_time, "entry_price": entry, "raw_entry": bar["open"], "quantity": quantity, "entry_fee": entry_fee, "entry_balance": balance, "stop": stop, "target": target, "risk_amount": risk_amount, "regime": observation.get("regime", "unknown"), "mae_r": 0.0, "mfe_r": 0.0}


def simulate(bars: list[dict], signals: list[dict | None], params: dict, config: dict, *, start: int = 0, end: int | None = None, strategy_id: str = "custom", split: str = "research") -> dict:
    """Low-level OHLC execution, exposed for deterministic regression tests.

    Callers supply validated bars and normalized config. Sizing includes the
    anticipated round-trip friction, and leverage includes contract multiplier.
    Position quantities are theoretical unless an actual quantity_step is set.
    """
    end = len(bars) if end is None else end
    if not 0 <= start < end <= len(bars) or len(signals) != len(bars):
        raise ValueError("invalid simulation range or signal count")
    initial = config["account_size"]
    balance = initial
    peak = initial
    maximum_drawdown = 0.0
    maximum_drawdown_amount = 0.0
    minimum_equity = initial
    trades, curve = [], []
    position = None
    exposure_bars = 0
    multiplier = config["contract_multiplier"]
    friction = _friction_fraction(config)
    for i in range(start, end):
        bar = bars[i]
        opening_balance = balance
        opening_equity = balance + (position["direction"] * (bar["open"] - position["entry_price"]) * position["quantity"] * multiplier if position else 0.0)
        if position is None and i > 0 and i < end - 1 and balance > 0:
            observation = signals[i - 1]
            if observation:
                position = _open_position(bar, observation, params, config, balance, i, bars[i - 1]["time"])
                if position:
                    balance -= position["entry_fee"]
        if position is not None:
            exposure_bars += 1
            raw_exit, exit_reason, adverse, favorable = _choose_exit(position, bar, i, end - 1, params)
            adverse_pnl = _liquidation_pnl(position, adverse, config)
            favorable_pnl = _liquidation_pnl(position, favorable, config)
            position["mae_r"] = max(position["mae_r"], -adverse_pnl / position["risk_amount"], 0.0)
            position["mfe_r"] = max(position["mfe_r"], favorable_pnl / position["risk_amount"], 0.0)
            worst_equity = position["entry_balance"] + adverse_pnl
            best_equity = position["entry_balance"] + favorable_pnl
            if raw_exit is not None:
                fill = raw_exit * (1.0 - position["direction"] * friction)
                exit_fee = _fee(fill, position["quantity"], config)
                gross_fill_pnl = position["direction"] * (fill - position["entry_price"]) * position["quantity"] * multiplier
                pnl = gross_fill_pnl - position["entry_fee"] - exit_fee
                balance += gross_fill_pnl - exit_fee
                traded_notional = position["quantity"] * multiplier * (position["raw_entry"] + raw_exit)
                trade = {"strategy_id": strategy_id, "split": split, "out_of_sample": split == "oos", "entry_time": position["entry_time"], "signal_time": position["signal_time"], "exit_time": bar["time"], "direction": "long" if position["direction"] == 1 else "short", "entry_price": _rounded(position["entry_price"], 10), "exit_price": _rounded(fill, 10), "raw_entry_price": _rounded(position["raw_entry"], 10), "raw_exit_price": _rounded(raw_exit, 10), "stop": _rounded(position["stop"], 10) if position["stop"] is not None else None, "target": _rounded(position["target"], 10) if position["target"] is not None else None, "quantity": _rounded(position["quantity"], 10), "contract_multiplier": multiplier, "risk_amount": _rounded(position["risk_amount"]), "pnl": _rounded(pnl), "gross_pnl": _rounded(position["direction"] * (raw_exit - position["raw_entry"]) * position["quantity"] * multiplier), "return_r": _rounded(pnl / position["risk_amount"]), "net_r": _rounded(pnl / position["risk_amount"]), "mae_r": _rounded(position["mae_r"]), "mfe_r": _rounded(position["mfe_r"]), "excursion_method": "OHLC bounds; ordering unknown", "fees": _rounded(position["entry_fee"] + exit_fee), "slippage": _rounded(traded_notional * config["slippage_bps"] / 10_000.0), "spread": _rounded(traded_notional * config["spread_bps"] / 20_000.0), "exit_reason": exit_reason, "bars_held": i - position["entry_index"] + 1, "regime": position["regime"]}
                trade["total_costs"] = _rounded(trade["fees"] + trade["slippage"] + trade["spread"])
                trades.append(trade)
                position = None
                closing_equity = balance
            else:
                closing_equity = balance + position["direction"] * (bar["close"] - position["entry_price"]) * position["quantity"] * multiplier
        else:
            worst_equity = best_equity = closing_equity = balance
        minimum_equity = min(minimum_equity, worst_equity, closing_equity)
        drawdown_amount = max(0.0, peak - worst_equity)
        bar_drawdown = drawdown_amount / peak * 100.0 if peak > 0 else 0.0
        maximum_drawdown = max(maximum_drawdown, bar_drawdown)
        maximum_drawdown_amount = max(maximum_drawdown_amount, drawdown_amount)
        peak = max(peak, closing_equity)
        curve.append({"time": bar["time"], "equity": _rounded(closing_equity), "balance": _rounded(balance), "opening_balance": _rounded(opening_balance), "opening_equity": _rounded(opening_equity), "worst_equity": _rounded(min(worst_equity, closing_equity)), "best_equity": _rounded(max(best_equity, closing_equity)), "drawdown_pct": _rounded(bar_drawdown, 4)})
    wins = [trade["pnl"] for trade in trades if trade["pnl"] > 0]
    losses = [-trade["pnl"] for trade in trades if trade["pnl"] < 0]
    gross_profit, gross_loss = sum(wins), sum(losses)
    total_trades = len(trades)
    consecutive_losses = maximum_consecutive_losses = 0
    for trade in trades:
        consecutive_losses = consecutive_losses + 1 if trade["pnl"] < 0 else 0
        maximum_consecutive_losses = max(maximum_consecutive_losses, consecutive_losses)
    metrics = {"initial_equity": initial, "final_equity": _rounded(balance), "net_profit": _rounded(balance - initial), "net_return_pct": _rounded((balance / initial - 1.0) * 100.0, 4), "max_drawdown_pct": _rounded(maximum_drawdown, 4), "max_drawdown_amount": _rounded(maximum_drawdown_amount), "min_equity": _rounded(minimum_equity), "total_trades": total_trades, "winning_trades": len(wins), "losing_trades": len(losses), "win_rate": _rounded(len(wins) / total_trades * 100.0, 2) if total_trades else 0.0, "profit_factor": _rounded(gross_profit / gross_loss, 4) if gross_loss else None, "profit_factor_label": "no_losses" if gross_profit and not gross_loss else "no_trades" if not total_trades else "finite", "expectancy_r": _rounded(statistics.mean(trade["return_r"] for trade in trades)) if trades else 0.0, "average_trade_pnl": _rounded((balance - initial) / total_trades) if total_trades else 0.0, "average_win": _rounded(statistics.mean(wins)) if wins else 0.0, "average_loss": _rounded(statistics.mean(losses)) if losses else 0.0, "fees": _rounded(sum(trade["fees"] for trade in trades)), "slippage": _rounded(sum(trade["slippage"] for trade in trades)), "spread": _rounded(sum(trade["spread"] for trade in trades)), "total_costs": _rounded(sum(trade["total_costs"] for trade in trades)), "max_consecutive_losses": maximum_consecutive_losses, "exposure_pct": _rounded(exposure_bars / (end - start) * 100.0, 2), "average_hold_bars": _rounded(statistics.mean(trade["bars_held"] for trade in trades), 2) if trades else 0.0, "drawdown_method": "worst OHLC liquidation mark versus previous closing high water"}
    return {"metrics": metrics, "trades": trades, "equity_curve": curve}


def _train_score(result: dict) -> float:
    metrics = result["metrics"]
    # A fixed simple objective, not another hyperparameter search. Penalize
    # risk, unobserved setups and isolated wins in small samples.
    return metrics["net_return_pct"] - 0.7 * metrics["max_drawdown_pct"] - max(0, 8 - metrics["total_trades"]) * 0.7


def _choose_candidate(bars: list[dict], candidates: list[dict], config: dict, start: int, end: int, strategy_id: str) -> tuple[int, dict]:
    results = [simulate(bars, item["signals"], item["params"], config, start=start, end=end, strategy_id=strategy_id, split="train") for item in candidates]
    index = max(range(len(results)), key=lambda candidate: (_train_score(results[candidate]), -candidate))
    return index, results[index]


def _walk_forward(bars: list[dict], candidates: list[dict], config: dict, train_end: int, strategy_id: str) -> dict:
    window = max(100, int(train_end * 0.4))
    validation = max(35, int(train_end * 0.2))
    cursor = window
    folds = []
    while cursor + validation <= train_end:
        train_start = max(0, cursor - window)
        chosen, _ = _choose_candidate(bars, candidates, config, train_start, cursor, strategy_id)
        result = simulate(bars, candidates[chosen]["signals"], candidates[chosen]["params"], config, start=cursor, end=cursor + validation, strategy_id=strategy_id, split="walk_forward")
        folds.append({"train_start": bars[train_start]["time"], "train_end": bars[cursor - 1]["time"], "validation_start": bars[cursor]["time"], "validation_end": bars[cursor + validation - 1]["time"], "params": candidates[chosen]["params"].copy(), "metrics": result["metrics"]})
        cursor += validation
    positive = sum(fold["metrics"]["net_profit"] > 0 for fold in folds)
    total_trades = sum(fold["metrics"]["total_trades"] for fold in folds)
    return {"folds": folds, "fold_count": len(folds), "positive_folds": positive, "positive_fraction": _rounded(positive / len(folds), 4) if folds else 0.0, "total_trades": total_trades, "mean_net_return_pct": _rounded(statistics.mean(fold["metrics"]["net_return_pct"] for fold in folds), 4) if folds else 0.0, "max_drawdown_pct": max((fold["metrics"]["max_drawdown_pct"] for fold in folds), default=0.0), "method": "rolling train windows with newly selected parameters; validation precedes final holdout"}


def _confidence(trades: list[dict]) -> dict:
    returns = [trade["return_r"] for trade in trades]
    n = len(returns)
    if n < 2:
        return {"label": "insufficient", "sample_size": n, "mean_r_ci95": None, "method": "moving-block bootstrap; descriptive, no future guarantee"}
    # Moving blocks retain some local dependence. Resampling cannot fix a
    # biased feed, strategy search, nonstationarity or unknown execution.
    block = max(2, min(10, int(math.sqrt(n))))
    rng = random.Random(1729 + n)
    means = []
    for _ in range(300):
        sample = []
        while len(sample) < n:
            index = rng.randrange(0, n - block + 1)
            sample.extend(returns[index:index + block])
        means.append(statistics.mean(sample[:n]))
    means.sort()
    interval = [_rounded(means[int(0.025 * (len(means) - 1))]), _rounded(means[int(0.975 * (len(means) - 1))])]
    label = "supported_sample" if n >= MIN_HOLDOUT_TRADES and interval[0] > 0 else "fragile" if n >= MIN_HOLDOUT_TRADES else "insufficient"
    return {"label": label, "sample_size": n, "mean_r_ci95": interval, "block_length": block, "resamples": 300, "method": "moving-block bootstrap; descriptive, no future guarantee"}


def _evidence_reasons(result: dict, walk_forward: dict, confidence: dict, config: dict, baseline: bool) -> list[str]:
    metrics = result["metrics"]
    reasons = []
    if baseline:
        return ["Baseline is a reference, not a qualified prop strategy."]
    if config["source"] == "demo":
        reasons.append("Synthetic DEMO data cannot establish a trading edge or qualify a strategy.")
    elif config["source"] != "csv":
        reasons.append("Data provenance is unspecified; import actual historical CSV before assessing eligibility.")
    if metrics["total_trades"] < MIN_HOLDOUT_TRADES:
        reasons.append(f"Holdout has {metrics['total_trades']} trades; at least {MIN_HOLDOUT_TRADES} are required.")
    if metrics["net_profit"] <= 0 or metrics["expectancy_r"] <= 0:
        reasons.append("Holdout expectancy is not positive after execution costs.")
    profit_factor = metrics["profit_factor"]
    if profit_factor is not None and profit_factor < 1.2:
        reasons.append("Holdout profit factor is below 1.20.")
    if confidence["mean_r_ci95"] is None or confidence["mean_r_ci95"][0] <= 0:
        reasons.append("The descriptive 95% mean-R interval includes zero or is unavailable.")
    if metrics["max_drawdown_pct"] >= config["max_drawdown_pct"]:
        reasons.append("Worst-bar holdout drawdown reaches the configured account loss limit.")
    if walk_forward["fold_count"] < 2 or walk_forward["total_trades"] < 12:
        reasons.append("Walk-forward validation has insufficient independent windows or trade evidence.")
    if walk_forward["positive_fraction"] < 2 / 3 or walk_forward["mean_net_return_pct"] <= 0:
        reasons.append("Walk-forward results are not positive in at least two-thirds of windows.")
    return reasons


def _thin_curve(curve: list[dict], limit: int = 400) -> list[dict]:
    if len(curve) <= limit:
        return curve
    # Keep adverse marks rather than averaging away a breach. Exact metrics
    # always use every bar, even when the chart is thinned.
    step = math.ceil((len(curve) - 2) / (limit - 2))
    result = [curve[0]]
    for start in range(1, len(curve) - 1, step):
        bucket = curve[start:min(start + step, len(curve) - 1)]
        result.append(max(bucket, key=lambda point: point["drawdown_pct"]))
    result.append(curve[-1])
    return result


def _regime_metrics(trades: list[dict]) -> list[dict]:
    result = []
    for regime in ("trend", "range", "volatile", "transition"):
        sample = [trade for trade in trades if trade["regime"] == regime]
        result.append({"regime": regime, "total_trades": len(sample), "net_profit": _rounded(sum(trade["pnl"] for trade in sample)), "expectancy_r": _rounded(statistics.mean(trade["return_r"] for trade in sample)) if sample else None, "sufficient_sample": len(sample) >= MIN_HOLDOUT_TRADES, "exploratory": True})
    return result


def _latest_signal(bars: list[dict], candidate: dict | None, config: dict, labels: list[str], selected: str | None) -> dict:
    result = {"status": "waiting", "direction": "wait", "strategy_id": candidate["id"] if candidate else None, "symbol": config["symbol"], "reference_time": bars[-1]["time"], "reference_price": bars[-1]["close"], "stop": None, "target": None, "risk_pct": config["risk_pct"], "regime": labels[-1], "planning_only": True, "actionable": False, "reason": "No fresh closed-bar setup. Wait for a new bar; this is not a live quote.", "execution": "next-bar open after a closed-bar signal; actual fills unknown"}
    if candidate is None:
        result["status"] = "no_candidate"
        result["reason"] = "No active strategy was requested; buy-and-hold is only a reference."
        return result
    observation = candidate["signals"][-1]
    if config["source"] == "demo":
        result["status"] = "demo"
        result["reason"] = "Synthetic illustration only; no live order or verified trading edge."
    elif selected is None:
        result["status"] = "research_only"
        result["reason"] = "The training candidate did not pass the evidence gates; this observation is for research only."
    if observation:
        direction = observation["direction"]
        distance = observation["atr"] * candidate["params"]["stop_atr"]
        result.update({"direction": "long" if direction == 1 else "short", "stop": _rounded(bars[-1]["close"] - direction * distance, 10), "target": _rounded(bars[-1]["close"] + direction * distance * candidate["params"]["reward_risk"], 10)})
        if selected:
            result["status"] = "candidate"
            result["reason"] = "Conditional closed-bar plan. Re-check the account rules, live spread, calendar and actual entry before paper execution."
    return result


def run_research(bars: list[dict], config: dict | None = None) -> dict:
    """Research a fixed strategy family without tuning on the final holdout.

    Parameter and strategy winners are chosen exclusively on the initial
    chronological train segment. The untouched tail only gates that winner.
    If it fails, no replacement is chosen from holdout results. This matters:
    selecting whichever holdout happens to look best is another optimization.
    """
    try:
        return _run_research(bars, config)
    except (OverflowError, ZeroDivisionError) as exc:
        raise ValueError("Numerical overflow or underflow: check input prices, contract multiplier and account configuration.") from exc


def _run_research(bars: list[dict], config: dict | None) -> dict:
    bars = market.validate_bars(bars)
    if len(bars) < MIN_RESEARCH_BARS:
        raise ValueError(f"research requires at least {MIN_RESEARCH_BARS} closed bars")
    settings = normalize_config(config)
    train_end = int(len(bars) * settings["train_fraction"])
    labels = strategies.regimes(bars)
    catalog_by_id = {item["id"]: item for item in strategies.catalog()}
    prepared = []
    for strategy_id in settings["strategy_ids"]:
        candidates = [{"params": params, "signals": strategies.signals_for(bars, strategy_id, params, regime_labels=labels)} for params in strategies.parameter_candidates(strategy_id)]
        chosen, train_result = _choose_candidate(bars, candidates, settings, 0, train_end, strategy_id)
        prepared.append({"id": strategy_id, "name": catalog_by_id[strategy_id]["name"], "candidates": candidates, "params": candidates[chosen]["params"], "signals": candidates[chosen]["signals"], "train_result": train_result, "train_score": _train_score(train_result)})
    active = [item for item in prepared if item["id"] != "buy_hold"]
    training_candidate = max(active, key=lambda item: (item["train_score"], -settings["strategy_ids"].index(item["id"]))) if active else None
    outputs = []
    for item in prepared:
        result = simulate(bars, item["signals"], item["params"], settings, start=train_end, end=len(bars), strategy_id=item["id"], split="oos")
        walk_forward = _walk_forward(bars, item["candidates"], settings, train_end, item["id"])
        confidence = _confidence(result["trades"])
        reasons = _evidence_reasons(result, walk_forward, confidence, settings, item["id"] == "buy_hold")
        rule_replay = None
        if settings.get("prop_profile") is not None:
            from .compliance import evaluate
            rule_replay = evaluate(result["equity_curve"], settings["prop_profile"], trades=result["trades"])
            if rule_replay["status"] != "pass" and item["id"] != "buy_hold":
                reasons.append("The full-bar account-rule replay breached a floor or lacks sufficient rule definitions.")
        outputs.append({"id": item["id"], "name": item["name"], "params": item["params"].copy(), "train_metrics": item["train_result"]["metrics"], "test_metrics": result["metrics"], "walk_forward": walk_forward, "eligible": not reasons, "confidence": confidence, "reasons": reasons, "training_score": _rounded(item["train_score"]), "training_winner": training_candidate is item, "equity_curve": _thin_curve(result["equity_curve"]), "equity_curve_thinned": len(result["equity_curve"]) > 400, "trades": result["trades"], "regime_metrics": _regime_metrics(result["trades"]), "baseline": item["id"] == "buy_hold", "rule_replay": rule_replay})
    winner_output = next((item for item in outputs if training_candidate is not None and item["id"] == training_candidate["id"]), None)
    selected = winner_output["id"] if winner_output and winner_output["eligible"] else None
    stamps = [market.utc_datetime(bar["time"]) for bar in bars]
    spacings = [(stamps[i] - stamps[i - 1]).total_seconds() for i in range(1, len(stamps))]
    typical_spacing = statistics.median(spacings)
    irregular = sum(abs(value - typical_spacing) > 1e-6 for value in spacings)
    warnings = ["Seven fixed strategy families are a starting catalog, not an exhaustive search of all strategies or assets.", "OHLC fills, quantities and costs are approximations; exchange calendars, tick paths, financing and live liquidity require separate validation.", "Training searches and exploratory regime comparisons can overfit. The holdout must not be reused to tune parameters.", "Positive historical results and descriptive intervals do not guarantee future profit or prop-firm payouts.", "Timestamps identify bar opens; every input bar, including the final row, must be fully closed. Exit times identify bars, not exact intrabar fill times."]
    if settings["source"] == "demo":
        warnings.insert(0, "DEMO: all OHLCV data are synthetic. Performance is interface validation, not market evidence.")
    else:
        warnings.insert(0, "User-supplied data provenance, corporate actions and survivorship are not independently verified.")
    if irregular:
        warnings.append(f"{irregular} timestamp intervals differ from the median; session closures or missing data may affect results.")
    if settings["quantity_step"] == 0:
        warnings.append("Fractional theoretical quantities are enabled; configure the real contract multiplier, quantity step and broker minimums.")
    if winner_output and not selected:
        warnings.append("The training winner did not pass qualification. No alternate strategy is selected from holdout results.")
    display_metrics = winner_output["test_metrics"] if winner_output else next(item["test_metrics"] for item in outputs if item["baseline"])
    summary = {**display_metrics, "selected_name": winner_output["name"] if selected else None, "training_candidate": training_candidate["id"] if training_candidate else None, "training_candidate_name": training_candidate["name"] if training_candidate else None, "qualified_count": sum(item["eligible"] for item in outputs), "status": "demo" if settings["source"] == "demo" else "qualified_for_paper_review" if selected else "no_qualified_strategy", "account_rule_status": winner_output["rule_replay"]["status"] if winner_output and winner_output["rule_replay"] else "not_evaluated", "warnings": warnings, "performance_basis": "training winner on untouched holdout; research evidence only"}
    return {"summary": summary, "strategies": outputs, "selected_strategy": selected, "training_candidate": training_candidate["id"] if training_candidate else None, "latest_signal": _latest_signal(bars, training_candidate, settings, labels, selected), "data": {"source": settings["source"], "symbol": settings["symbol"], "bars": len(bars), "start": bars[0]["time"], "end": bars[-1]["time"], "train_bars": train_end, "test_bars": len(bars) - train_end, "train_end": bars[train_end - 1]["time"], "holdout_start": bars[train_end]["time"], "timeframe_minutes": _rounded(typical_spacing / 60.0, 4), "irregular_intervals": irregular, "hash": market.data_fingerprint(bars), "warnings": warnings[:2]}, "config": settings, "methodology": {"entry": "signal on closed bar i; order at open i+1; no entry on final bar", "parameter_selection": "fixed grid selected on training only", "strategy_selection": "training winner only; holdout gates, never substitutes a winner", "walk_forward": "train/validation windows entirely precede final holdout", "intrabar": "adverse stop-first collisions; adverse gaps fill at open; favourable gaps at target", "costs": "fees plus adverse slippage and half spread per side; no financing", "qualification": {"min_holdout_trades": MIN_HOLDOUT_TRADES, "min_profit_factor": 1.2, "mean_r_ci95_lower_above": 0, "minimum_positive_walk_forward_fraction": 2 / 3, "min_walk_forward_trades": 12, "max_drawdown_pct": settings["max_drawdown_pct"]}, "regime_analysis": "descriptive holdout slices; not a fitted regime-switching allocation"}}
