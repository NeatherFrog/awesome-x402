#!/usr/bin/env python3
"""One predeclared hourly intraday adaptation study; never minute replication.

All periods, three rules, calendar, costs and gates are frozen before the first
new hourly request. One training-selected family is locked before the holdout.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone, time as clock_time
from pathlib import Path
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from propdesk import backtest, compliance, feeds, market, strategies
from propdesk.risk import normalize_profile
from propdesk.timezones import timezone_for
from scripts.research_sourced import canonical, digest, file_digest, immutable_write, iso, write_report, _metrics, _ema

SYMBOLS = ("SPY", "QQQ", "IWM")
STRATEGY_IDS = ("hourly_noise_14", "hourly_orb_60", "hourly_donchian_20")
OUTPUT = ROOT/"docs"/"intraday-research.json"
SNAPSHOTS = ROOT/"data"/"intraday-history"
CALENDAR_FILE = Path("/tmp/trading-qc-market-hours.json")
CALENDAR_SHA256 = "bffec9c2e5efe30c0f21a1af9d1803b2a8e9a1356ac4f7408130693b7261e440"
CALENDAR_URL = "https://raw.githubusercontent.com/QuantConnect/Lean/41c6e603e5671ca7b5d3de0cbe13b3c4b109bba4/Data/market-hours/market-hours-database.json"


def freeze_calendar():
    if file_digest(CALENDAR_FILE) != CALENDAR_SHA256:
        raise ValueError("Official source calendar fingerprint mismatch")
    entry = json.loads(CALENDAR_FILE.read_text())["entries"]["Equity-usa-[*]"]
    def dates(values):
        result = []
        for value in values:
            stamp = datetime.strptime(value, "%m/%d/%Y").date().isoformat()
            if "2024-10-01" <= stamp < "2026-10-01":
                result.append(stamp)
        return sorted(result)
    return {"source_url": CALENDAR_URL, "source_sha256": CALENDAR_SHA256,
            "retrieved_at": "2026-10-01T10:50:41.315597Z", "timezone": "America/New_York",
            "open": "09:30", "close": "16:00", "flatten": "15:30",
            "early_close": "13:00", "early_flatten": "12:30",
            "early_close_dates": dates(entry["earlyCloses"]), "holidays": dates(entry["holidays"]),
            "basis": "Pinned official Lean US equity calendar, fixed before prices; not a live broker calendar"}


def make_protocol():
    return {"version": "hourly-three-adaptations-v1", "frozen_at": iso(datetime.now(timezone.utc)),
            "symbols": list(SYMBOLS), "interval": "1h", "data_start": "2024-10-01T13:30:00Z", "data_end_exclusive": "2026-10-01T00:00:00Z",
            "training": ["2024-10-01", "2025-10-01"], "holdout": ["2025-10-01", "2026-10-01"],
            "calendar": freeze_calendar(), "strategy_ids": list(STRATEGY_IDS),
            "sources": [
                {"rule": "hourly_noise_14", "inspiration": "Zarattini intraday momentum third-party reproduction specification",
                 "url": "https://github.com/giovannibrusco/zarattini-2024-momentum-spy/tree/ec10608398b86c1a48d83411ae3e0fc9ab4cbfd1",
                 "limits": "Original author paper not retrieved; hourly/noVWAP/fixedrisk is a new adaptation, not original30-minute/minute replication or reported original returns"},
                {"rule": "hourly_orb_60", "inspiration": "Official QuantConnect opening-range concept",
                 "url": "https://github.com/QuantConnect/Lean/blob/41c6e603e5671ca7b5d3de0cbe13b3c4b109bba4/Algorithm.CSharp/OpeningBreakoutAlgorithm.cs",
                 "limits": "Actual source3-minute/seconddata/PSAR/entrybefore10:00 cannot be replicated on hourly bars; both-direction60-minute model below is independently defined"},
                {"rule": "hourly_donchian_20", "inspiration": "Existing fixed Donchian channel concept plus our EMA50/timeflat policy",
                 "limits": "EMA50 filter and intraday wrapper are our explicit rule, not a claimed published exact strategy"}],
            "rules": {
                "hourly_noise_14": "For each prior closed60-minute slot, sigma=mean(abs(slotclose/sessionopen-1)) from14priorcompleted same-slot observations. Exclude shortened half-hour slots from sigma. upper=max(todayopen,previousfullsessionclose)*(1+sigma),lower=min(...) *(1-sigma). Lastclosedprice>upperlong,<lowershort; long exits back<=upper,short exits>=lower on nextopen. Fixed3ATR14stop,noTP,noVWAP.",
                "hourly_orb_60": "Rangehigh/low=closed09:30–10:30 hour. Laterclosedhourclose>highlong,<lowshort; enter nextopen onlyifopeningfill remainsbeyondrange; stopoppositesideofopeningrange,target2R. Never enter from rangebar itself.",
                "hourly_donchian_20": "Lastclosedhourclose>max(high of20 preceding closedhours) and>EMA50long; belowminlow and<EMA50short. Fixed3ATR14stop,target2R. Channel excludes signalbar.",
            },
            "execution": {"signal": "Only prior closed current-session hour; no first09:30open entry or future dailyclose/volume",
                          "fill": "Next hourly open with adverse friction; gapstop open, favorablegap targetprice, intrabar stopfirst ifstopandTPbothhit",
                          "exit_priority": "Openinggapstop first; existingtargetgap conservatively at target; known bandexit/dayflat atopen beforelaterhour extremes",
                          "entries": "Atmost1actualentry/asset/session; bothdirections; no reentryafterstop; no entryat/afterflatten open",
                          "flatten": "Deterministic15:30open normal session or12:30open predeclaredearlyclose; never infer close from lastobservedbar; noovernight positions",
                          "risk": "Stop fixed from priorclosedATR or openingrange; never trailing; integer normalizedshares; riskbudget and actual plannedstoploss includingfees separately recorded",
                          "segment_state": "Train and holdout startflat at fresh cash; indicators carry only priorclosedprice information"},
            "portfolio": {"account_size": 100000, "bucket_account_size": 100000/3,
                          "bucket_risk_pct": .75, "initial_risk_budget_per_asset": 250,
                          "maximum_initial_aggregate_risk_budget_pct": .75, "max_gross_notional_at_entry": 1,
                          "quantity_step": 1, "contract_multiplier": 1,
                          "shorts": "Hypothetical intraday margin/borrow; stock locate and real CFD availability not verified",
                          "risk_denominator": "PnL/R uses allocatedbudget; actualplannedstoploss can be lower afterwholeunits/cashcap; gaps can exceed it"},
            "costs": {"fee_bps_per_side": 2, "slippage_bps_per_side": 1, "full_spread_bps": 1,
                      "stress_multiplier": 2, "funding": 0, "cash_interest": 0,
                      "dividends": "Noincomecredited; vendorquoteunits retained; no adjclose or fabricatedminuteprices/VWAP",
                      "status": "Research assumptions, not verified broker tariffs"},
            "selection": {"score": "Aggregate training net_return_pct-.7*worstbarDD; lexicalIDtie; onefamilylocked beforeholdout; no grid/fallback",
                          "quarterly_slices": "Fixedcalendarquarter summaries onlydescriptive, never trainseasonalswitch"},
            "qualification": {"min_holdout_trades": 60, "min_holdout_sessions": 120, "min_profit_factor": 1.2,
                              "net_positive": True, "double_friction_positive": True, "max_drawdown_pct": 8,
                              "daily_mean_ci99_lower_above": 0, "bootstrap_blocks_sessions": 5, "bootstrap_resamples": 5000, "seed": 7012026,
                              "static_rule_profile": {"account_size": 100000, "daily_loss_pct": 5, "max_loss_pct": 10, "profit_target_pct": 8,
                                                      "daily_reset_timezone": "Europe/Prague", "drawdown_type": "static", "status": "illustrative"}},
            "data_quality": "Require every expectedcalendar session and observedopening/flatten/allrequiredslots for all3ETFs. Missingdata rejectsstudy rather than deletinglossdays. Officialhalfday exceptions frozen beforeprices; never guess from latermissingbars.",
            "scope": "Newintradaygranularity,butdailyETFpricesandequityfactorspreviouslyseen. Retrospectiveexploratoryvalidation,nopublicationindependent/globalblindclaim. No newparameters/symbols/windows afterresults.",
            "real_prop_qualified": False, "orders": "Paperresearchonly; actualcontracts,fees,newsrules/sessioncalendarunverified; neverbrokerorders/deposits/purchases"}


def freeze(output=OUTPUT, snapshots=SNAPSHOTS):
    if output.exists():
        report = json.loads(output.read_text())
        if digest(report["protocol"]) != report["protocol_sha256"]:
            raise ValueError("Frozen protocol mismatch")
        return report
    protocol = make_protocol()
    report = {"phase": "predeclared", "protocol": protocol, "protocol_sha256": digest(protocol)}
    immutable_write(snapshots/"protocol.json", canonical(protocol)+"\n")
    write_report(output, report)
    return report


def _session_clock(bar, calendar):
    stamp = market.utc_datetime(bar["time"]).astimezone(timezone_for(calendar["timezone"]))
    if stamp.second or stamp.microsecond:
        raise ValueError("Hourly session opening must have exact zero seconds")
    date, slot = stamp.date().isoformat(), stamp.strftime("%H:%M")
    flatten = calendar["early_flatten"] if date in calendar["early_close_dates"] else calendar["flatten"]
    return date, slot, flatten


def session_groups(bars, calendar):
    groups = {}
    for index, bar in enumerate(bars):
        date, slot, flatten = _session_clock(bar, calendar)
        if slot not in ("09:30", "10:30", "11:30", "12:30", "13:30", "14:30", "15:30"):
            raise ValueError(f"Unexpected NY opening slot {date} {slot}")
        if date in calendar["holidays"] or datetime.fromisoformat(date).weekday() >= 5:
            raise ValueError(f"Observed bar outside declared session {date}")
        group = groups.setdefault(date, {"indices": [], "slots": [], "flatten": flatten,
                                          "close": calendar["early_close"] if date in calendar["early_close_dates"] else calendar["close"]})
        if slot in group["slots"] or (group["slots"] and slot < group["slots"][-1]):
            raise ValueError(f"Duplicate or unordered opening slot {date} {slot}")
        if slot > flatten:
            raise ValueError(f"Observed bar past frozen close {date} {slot}")
        group["indices"].append(index)
        group["slots"].append(slot)
    return groups


def validate_sessions(bars, calendar, start_date, end_date):
    groups = session_groups(market.validate_bars(bars), calendar)
    expected, stamp = [], datetime.fromisoformat(start_date).date()
    until = datetime.fromisoformat(end_date).date()
    while stamp < until:
        date = stamp.isoformat()
        if stamp.weekday() < 5 and date not in calendar["holidays"]:
            expected.append(date)
        stamp += timedelta(days=1)
    actual = [date for date in groups if start_date <= date < end_date]
    missing_days, extra_days = sorted(set(expected)-set(actual)), sorted(set(actual)-set(expected))
    failures = [f"missing session {date}" for date in missing_days]+[f"extra session {date}" for date in extra_days]
    all_slots = ["09:30", "10:30", "11:30", "12:30", "13:30", "14:30", "15:30"]
    for date in expected:
        if date not in groups:
            continue
        needed = [slot for slot in all_slots if slot <= groups[date]["flatten"]]
        if groups[date]["slots"] != needed:
            failures.append(f"session {date}: expected {','.join(needed)}; observed {','.join(groups[date]['slots'])}")
    if failures:
        raise ValueError("Frozen calendar coverage failed: "+"; ".join(failures[:15]))
    return {"sessions": len(expected), "bars": sum(len(groups[date]["indices"]) for date in actual),
            "start": actual[0] if actual else None, "end": actual[-1] if actual else None,
            "missing_sessions": [], "required_slots_complete": True, "calendar_sha256": calendar.get("source_sha256")}


def entry_decisions(bars, strategy_id, calendar):
    """Opening decision at i uses closed prices <=i-1 and current session clock.

    Validation of a whole declared window is separate: a prefix can be used in
    causal regression fixtures without looking forward for missing slots.
    """
    if strategy_id not in STRATEGY_IDS:
        raise ValueError("Unknown frozen hourly family")
    groups = session_groups(bars, calendar)
    atr, ema = strategies.atr(bars, 14), _ema([bar["close"] for bar in bars], 50)
    result, history, previous_close = [], {}, None
    previous_group = None
    for date, group in groups.items():
        if previous_group:
            first = previous_group["indices"][0]
            if previous_group["slots"][0] == "09:30" and previous_group["slots"][-1] == previous_group["flatten"]:
                final_bar = bars[previous_group["indices"][-1]]
                reference = final_bar.get("session_close_reference")
                halfday = previous_group["close"] != calendar["close"]
                # The amended Yahoo final halfday11:30 interval is uncertain.
                # Its close is not a substitute for the observed13:00 reference.
                previous_close = reference["price"] if reference else (None if halfday and previous_group["flatten"] == "11:30" else final_bar["close"])
                session_open = bars[first]["open"]
                for index, slot in zip(previous_group["indices"], previous_group["slots"]):
                    if slot < previous_group["flatten"]:
                        history.setdefault(slot, []).append(abs(bars[index]["close"]/session_open-1))
        first = group["indices"][0]
        for index, slot in zip(group["indices"], group["slots"]):
            observation = {"direction": 0, "exit_long": False, "exit_short": False,
                           "session_date": date, "flatten": slot >= group["flatten"], "slot": slot,
                           "strategy_id": strategy_id, "atr": None, "signal_time": None}
            if index > first and group["slots"][0] == "09:30":
                signal = index-1
                observation.update(atr=atr[signal], signal_time=bars[signal]["time"])
                price = bars[signal]["close"]
                if strategy_id == "hourly_orb_60" and signal > first:
                    high, low = bars[first]["high"], bars[first]["low"]
                    observation.update(range_high=high, range_low=low)
                    observation["direction"] = 1 if price > high else -1 if price < low else 0
                elif strategy_id == "hourly_donchian_20" and signal >= 20 and ema[signal] is not None and atr[signal] is not None:
                    high = max(bar["high"] for bar in bars[signal-20:signal])
                    low = min(bar["low"] for bar in bars[signal-20:signal])
                    observation["direction"] = 1 if price > high and price > ema[signal] else -1 if price < low and price < ema[signal] else 0
                elif strategy_id == "hourly_noise_14" and previous_close is not None:
                    _, previous_slot, _ = _session_clock(bars[signal], calendar)
                    observed = history.get(previous_slot, [])
                    if len(observed) >= 14 and atr[signal] is not None:
                        sigma = statistics.mean(observed[-14:])
                        upper = max(bars[first]["open"], previous_close)*(1+sigma)
                        lower = min(bars[first]["open"], previous_close)*(1-sigma)
                        observation.update(upper_band=upper, lower_band=lower, sigma=sigma,
                                           exit_long=price <= upper, exit_short=price >= lower)
                        observation["direction"] = 1 if price > upper else -1 if price < lower else 0
            result.append(observation)
        previous_group = group
    return result


def simulate_asset(bars, decisions, config, *, start=0, end=None, calendar=None, friction_multiplier=1):
    """One intraday position, at most one entry/session, fixed loss stop.

    Stops include round-trip friction in sizing; actual planned loss is distinct
    from the allocated R budget. All open exits precede later hourly extrema.
    """
    end = len(bars) if end is None else end
    if not 0 <= start < end <= len(bars) or len(decisions) != len(bars):
        raise ValueError("Invalid simulation range/decision count")
    if not isinstance(friction_multiplier, (int, float)) or not math.isfinite(friction_multiplier) or not 1 <= friction_multiplier <= 2:
        raise ValueError("Invalid friction multiplier")
    config = backtest.normalize_config(config)
    for key in ("fee_bps", "fee_per_unit", "slippage_bps", "spread_bps"):
        config[key] *= friction_multiplier
    initial = balance = peak = config["account_size"]
    friction, multiplier = backtest._friction_fraction(config), config["contract_multiplier"]
    position, trades, curve, entered, previous_date = None, [], [], set(), None
    for i in range(start, end):
        bar, observation = bars[i], decisions[i] or {}
        date = observation.get("session_date", bar["time"][:10])
        if previous_date is not None and date != previous_date and position:
            raise ValueError("Missing prescribed flatten bar: position would carry overnight")
        previous_date = date
        previous_position = position is not None
        opening_balance = balance
        opening_equity = balance+(position["direction"]*(bar["open"]-position["entry_price"])*position["quantity"]*multiplier if position else 0)
        if not position and not observation.get("flatten") and date not in entered and balance > 0:
            direction = observation.get("direction", 0)
            if direction in (-1, 1):
                entry = bar["open"]*(1+direction*friction)
                orb = observation.get("strategy_id") == "hourly_orb_60"
                beyond = (entry > observation.get("range_high", math.inf) if direction == 1 else entry < observation.get("range_low", -math.inf)) if orb else True
                if orb:
                    stop = observation.get("range_low") if direction == 1 else observation.get("range_high")
                else:
                    stop = entry-direction*3*observation["atr"] if observation.get("atr") else None
                distance = direction*(entry-stop) if stop is not None else -1
                if beyond and stop is not None and stop > 0 and distance > 0:
                    stop_fill = stop*(1-direction*friction)
                    unit_entry_fee = backtest._fee(entry, 1, config)
                    unit_loss = -direction*(stop_fill-entry)*multiplier+unit_entry_fee+backtest._fee(stop_fill, 1, config)
                    budget = balance*config["risk_pct"]/100
                    cash_unit = max(entry, bar["open"])*multiplier+unit_entry_fee
                    quantity = min(budget/unit_loss, balance*min(config["max_leverage"], 1)/cash_unit)
                    if config["quantity_step"]:
                        quantity = math.floor(quantity/config["quantity_step"]+1e-12)*config["quantity_step"]
                    if quantity > 0:
                        fee = backtest._fee(entry, quantity, config)
                        position = {"direction": direction, "entry_price": entry, "raw_entry": bar["open"], "quantity": quantity,
                                    "entry_fee": fee, "entry_balance": balance, "entry_index": i, "entry_time": bar["time"],
                                    "signal_time": observation.get("signal_time"), "stop": stop,
                                    "target": None if observation.get("strategy_id") == "hourly_noise_14" else entry+direction*distance*2,
                                    "risk_amount": budget, "planned_stop_loss": quantity*unit_loss, "mae_r": 0, "mfe_r": 0}
                        balance -= fee
                        entered.add(date)
        raw_exit = reason = None
        if position:
            direction, stop, target = position["direction"], position["stop"], position["target"]
            adverse, favorable = (bar["low"], bar["high"]) if direction == 1 else (bar["high"], bar["low"])
            if direction*(bar["open"]-stop) <= 0:
                raw_exit, reason = bar["open"], "gap_stop"
                adverse = favorable = raw_exit
            elif target is not None and direction*(bar["open"]-target) >= 0:
                raw_exit, reason = target, "gap_target"
                adverse = favorable = target
            elif observation.get("flatten"):
                raw_exit, reason = bar["open"], "session_flatten"
                adverse = favorable = raw_exit
            elif previous_position and observation.get("exit_long" if direction == 1 else "exit_short"):
                raw_exit, reason = bar["open"], "band_exit"
                adverse = favorable = raw_exit
            elif direction*(adverse-stop) <= 0:
                raw_exit, reason, adverse = stop, "stop", stop
            elif target is not None and direction*(favorable-target) >= 0:
                raw_exit, reason, favorable = target, "target", target
            if target is not None:
                favorable = min(favorable, target) if direction == 1 else max(favorable, target)
            worst = position["entry_balance"]+backtest._liquidation_pnl(position, adverse, config)
            best = position["entry_balance"]+backtest._liquidation_pnl(position, favorable, config)
            position["mae_r"] = max(position["mae_r"], (position["entry_balance"]-worst)/position["risk_amount"], 0)
            position["mfe_r"] = max(position["mfe_r"], (best-position["entry_balance"])/position["risk_amount"], 0)
            if raw_exit is not None:
                fill = raw_exit*(1-direction*friction)
                exit_fee = backtest._fee(fill, position["quantity"], config)
                gross_filled = direction*(fill-position["entry_price"])*position["quantity"]*multiplier
                pnl = gross_filled-position["entry_fee"]-exit_fee
                balance += gross_filled-exit_fee
                notional = position["quantity"]*multiplier*(position["raw_entry"]+raw_exit)
                fees = position["entry_fee"]+exit_fee
                slip, spread = notional*config["slippage_bps"]/10000, notional*config["spread_bps"]/20000
                trades.append({"symbol": config["symbol"], "direction": "long" if direction == 1 else "short", "side": direction,
                               "entry_time": position["entry_time"], "signal_time": position["signal_time"], "exit_time": bar["time"],
                               "entry_price": position["entry_price"], "exit_price": fill, "raw_entry_price": position["raw_entry"],
                               "raw_exit_price": raw_exit, "quantity": position["quantity"], "contract_multiplier": multiplier,
                               "stop": stop, "target": target, "risk_amount": position["risk_amount"], "risk_budget": position["risk_amount"],
                               "planned_stop_loss": position["planned_stop_loss"], "pnl": pnl,
                               "gross_pnl": direction*(raw_exit-position["raw_entry"])*position["quantity"]*multiplier,
                               "return_r": pnl/position["risk_amount"], "net_r": pnl/position["risk_amount"],
                               "fees": fees, "slippage": slip, "spread": spread, "financing_total": 0,
                               "total_costs": fees+slip+spread, "mae_r": position["mae_r"], "mfe_r": position["mfe_r"],
                               "exit_reason": reason, "bars_held": i-position["entry_index"]+1,
                               "excursion_method": "OHLC liquidation bounds; unknown intrahour order"})
                position = None
                closing = balance
            else:
                closing = balance+direction*(bar["close"]-position["entry_price"])*position["quantity"]*multiplier
        else:
            worst = best = closing = balance
        amount = max(0, peak-min(worst, closing))
        curve.append({"time": bar["time"], "session_date": date, "balance": balance, "equity": closing,
                      "opening_balance": opening_balance, "opening_equity": opening_equity,
                      "worst_equity": min(worst, closing), "best_equity": max(best, closing),
                      "drawdown_amount": amount, "drawdown_pct": amount/peak*100 if peak > 0 else 0})
        peak = max(peak, closing)
    if position:
        raise ValueError("Simulation ended before prescribed flatten; no invented liquidation")
    return {"metrics": _metrics(curve, trades, initial), "trades": trades, "equity_curve": curve}


def aggregate_daily_returns(curve, initial):
    endpoints = {}
    for point in curve:
        endpoints[point["session_date"]] = point["equity"]
    result, previous = [], initial
    for date, equity in endpoints.items():
        result.append({"date": date, "return": equity/previous-1})
        previous = equity
    return result


def portfolio_result(datasets, strategy_id, start_date, end_date, *, calendar, friction_multiplier=1):
    if set(datasets) != set(SYMBOLS):
        raise ValueError("All three frozen ETFs required; no survivor substitution")
    calendars = [[bar["time"] for bar in datasets[symbol]] for symbol in SYMBOLS]
    if any(values != calendars[0] for values in calendars[1:]):
        raise ValueError("All ETFs must have synchronized slots; no missing-bar imputation")
    coverage = validate_sessions(datasets[SYMBOLS[0]], calendar, start_date, end_date)
    active = [i for i, bar in enumerate(datasets[SYMBOLS[0]]) if start_date <= _session_clock(bar, calendar)[0] < end_date]
    if not active:
        raise ValueError("No bars in declared window")
    assets, trades = {}, []
    for symbol in SYMBOLS:
        config = {"symbol": symbol, "source": "csv", "account_size": 100000/3, "risk_pct": .75,
                  "max_leverage": 1, "quantity_step": 1, "fee_bps": 2, "slippage_bps": 1, "spread_bps": 1}
        assets[symbol] = simulate_asset(datasets[symbol], entry_decisions(datasets[symbol], strategy_id, calendar), config,
                                         start=active[0], end=active[-1]+1, calendar=calendar, friction_multiplier=friction_multiplier)
        trades.extend(assets[symbol]["trades"])
    curve, peak = [], 100000
    for i in range(len(active)):
        points = [assets[symbol]["equity_curve"][i] for symbol in SYMBOLS]
        point = {key: sum(row[key] for row in points) for key in ("balance", "equity", "opening_balance", "opening_equity", "worst_equity", "best_equity")}
        amount = max(0, peak-min(point["worst_equity"], point["equity"]))
        point.update(time=points[0]["time"], session_date=points[0]["session_date"], drawdown_amount=amount,
                     drawdown_pct=amount/peak*100 if peak > 0 else 0)
        curve.append(point)
        peak = max(peak, point["equity"])
    trades.sort(key=lambda trade: (trade["entry_time"], trade["symbol"]))
    return {"metrics": _metrics(curve, trades, 100000), "trades": trades, "equity_curve": curve,
            "daily_returns": aggregate_daily_returns(curve, 100000), "asset_metrics": {symbol: value["metrics"] for symbol, value in assets.items()},
            "data": coverage}


def daily_bootstrap(daily_returns, *, block_length=5, resamples=5000, seed=7012026):
    values = [float(row["return"] if isinstance(row, dict) else row) for row in daily_returns]
    if any(not math.isfinite(value) for value in values) or not isinstance(block_length, int) or block_length < 1 or resamples < 100:
        raise ValueError("Invalid bootstrap inputs")
    if len(values) < block_length*4:
        return {"status": "insufficient", "sessions": len(values), "mean_daily_ci_pct": [None, None], "confidence_level": .99}
    rng, estimates = random.Random(seed), []
    blocks = [values[i:i+block_length] for i in range(len(values)-block_length+1)]
    for _ in range(resamples):
        sample = []
        while len(sample) < len(values):
            sample.extend(blocks[rng.randrange(len(blocks))])
        estimates.append(statistics.mean(sample[:len(values)])*100)
    estimates.sort()
    return {"status": "estimated", "sessions": len(values), "mean_daily_pct": statistics.mean(values)*100,
            "mean_daily_ci_pct": [estimates[int(resamples*.005)], estimates[min(resamples-1, int(resamples*.995))]],
            "confidence_level": .99, "block_length": block_length, "resamples": resamples, "seed": seed,
            "unit": "One synchronized three-ETF portfolio session; not pooled trades",
            "limitations": "Dependence beyond5sessions, structural changes and sequential study reuse can invalidate nominal coverage"}


def _quarterly(curve, initial):
    endpoints, previous, output = {}, initial, []
    for point in curve:
        stamp = point["session_date"]
        endpoints[stamp[:4]+"-Q"+str((int(stamp[5:7])-1)//3+1)] = point["equity"]
    for quarter, equity in endpoints.items():
        output.append({"quarter": quarter, "net_return_pct": (equity/previous-1)*100})
        previous = equity
    return output


def training_lock(datasets, protocol):
    training_data = {symbol: [bar for bar in bars if _session_clock(bar, protocol["calendar"])[0] < protocol["training"][1]]
                     for symbol, bars in datasets.items()}
    candidates = []
    for strategy_id in protocol["strategy_ids"]:
        result = portfolio_result(training_data, strategy_id, *protocol["training"], calendar=protocol["calendar"])
        metrics = result["metrics"]
        candidates.append({"strategy_id": strategy_id, "score": metrics["net_return_pct"]-.7*metrics["max_drawdown_pct"], "training_metrics": metrics})
    candidates.sort(key=lambda row: (-row["score"], row["strategy_id"]))
    prefixes = {symbol: digest(bars) for symbol,bars in training_data.items()}
    return {"locked_at": iso(datetime.now(timezone.utc)), "primary_strategy_id": candidates[0]["strategy_id"],
            "candidates": candidates, "training_bar_sha256": prefixes, "protocol_sha256": digest(protocol),
            "basis": "Training netreturn minus .7 OHLC drawdown; no holdout metrics read; no later substitute"}


def evaluate_locked(datasets, lock, protocol):
    if lock["protocol_sha256"] != digest(protocol):
        raise ValueError("Training lock protocol mismatch")
    prefixes = {symbol: digest([bar for bar in bars if _session_clock(bar, protocol["calendar"])[0] < protocol["training"][1]])
                for symbol, bars in datasets.items()}
    if prefixes != lock["training_bar_sha256"]:
        raise ValueError("Training prices changed after family lock")
    output = []
    profile = normalize_profile(protocol["qualification"]["static_rule_profile"])
    for strategy_id in protocol["strategy_ids"]:
        result = portfolio_result(datasets, strategy_id, *protocol["holdout"], calendar=protocol["calendar"])
        stress = portfolio_result(datasets, strategy_id, *protocol["holdout"], calendar=protocol["calendar"], friction_multiplier=2)
        result["friction_stress"] = {"multiplier": 2, "metrics": stress["metrics"]}
        result["confidence"] = daily_bootstrap(result["daily_returns"])
        result["rule_replay"] = compliance.evaluate(result["equity_curve"], profile, result["trades"])
        result["quarterly_diagnostics"] = _quarterly(result["equity_curve"], 100000)
        metrics, gates, reasons = result["metrics"], protocol["qualification"], []
        if metrics["total_trades"] < gates["min_holdout_trades"]:
            reasons.append("Fewer than60holdouttrades")
        if result["data"]["sessions"] < gates["min_holdout_sessions"]:
            reasons.append("Fewer than120holdoutsessions")
        if metrics["net_return_pct"] <= 0:
            reasons.append("Net holdout return is not positive after assumed costs")
        if metrics["profit_factor"] is None or metrics["profit_factor"] < gates["min_profit_factor"]:
            reasons.append("Profit factor below1.2 or no finite loss sample")
        if stress["metrics"]["net_return_pct"] <= 0:
            reasons.append("Double friction stress is not positive")
        if metrics["max_drawdown_pct"] >= gates["max_drawdown_pct"]:
            reasons.append("Worst-bar drawdown reaches8%")
        lower = result["confidence"]["mean_daily_ci_pct"][0]
        if lower is None or lower <= 0:
            reasons.append("99% synchronized5-session-block confidence lower bound does not exceedzero")
        result["evidence_reasons"], result["passes_window"] = reasons, not reasons
        training = next(row["training_metrics"] for row in lock["candidates"] if row["strategy_id"] == strategy_id)
        output.append({"id": strategy_id, "name": strategy_id.replace("_", " "), "primary": strategy_id == lock["primary_strategy_id"],
                       "training": training, "eligible_historical_price_model": not reasons, "reasons": reasons,
                       "windows": {"holdout": result}})
    return output


def _download(symbol, protocol, snapshots):
    start = int(market.utc_datetime(protocol["data_start"]).timestamp())
    end = int(market.utc_datetime(protocol["data_end_exclusive"]).timestamp())
    url = "https://query1.finance.yahoo.com/v8/finance/chart/"+symbol+"?"+urlencode({"period1": start, "period2": end, "interval": "1h", "includePrePost": "false", "events": "div,splits"})
    requested_at = iso(datetime.now(timezone.utc))
    payload = feeds._request_json(url)
    received = datetime.now(timezone.utc)
    parsed = feeds.parse_chart(payload, symbol, "1h", "2y", now=received)
    metadata = payload["chart"]["result"][0].get("meta", {})
    if metadata.get("currency") != "USD" or metadata.get("exchangeTimezoneName") != "America/New_York" or metadata.get("instrumentType") != "ETF":
        raise ValueError("Provider metadata must identify declared US ETF/USD/New York")
    bars = [bar for bar in parsed["bars"] if protocol["data_start"] <= bar["time"] < protocol["data_end_exclusive"]]
    provenance = {**parsed["provenance"], "source_url": url, "requested_at": requested_at, "received_at": iso(received),
                  "range": None, "period_start": protocol["data_start"], "period_end_exclusive": protocol["data_end_exclusive"],
                  "provider_payload_sha256": digest(payload), "split_events": payload["chart"]["result"][0].get("events", {}).get("splits", {}),
                  "quote_units": "Vendor split-normalized quote OHLC; no adjclose, no own corporate-action multiplication",
                  "coverage_verified": False, "redistribution_license": "Not independently verified; raw snapshots remain ignored local files"}
    snapshot = {"bars": bars, "provenance": provenance}
    path, receipt = snapshots/(symbol+"-1h.json"), snapshots/(symbol+"-provider-receipt.json")
    immutable_write(receipt, canonical(payload)+"\n")
    immutable_write(path, canonical(snapshot)+"\n")
    csv = "time,open,high,low,close,volume\n"+"".join(",".join(str(bar[key]) for key in ("time", "open", "high", "low", "close", "volume"))+"\n" for bar in bars)
    csv_path = snapshots/(symbol+"-1h.csv")
    immutable_write(csv_path, csv)
    return bars, {"symbol": symbol, "bars": len(bars), "start": bars[0]["time"] if bars else None, "end": bars[-1]["time"] if bars else None,
                  "json_path": str(path.relative_to(ROOT)), "json_sha256": file_digest(path), "csv_path": str(csv_path.relative_to(ROOT)),
                  "csv_sha256": file_digest(csv_path), "provenance": provenance}


def snapshot_prices(report, output=OUTPUT, snapshots=SNAPSHOTS):
    if report["phase"] == "complete":
        return {record["symbol"]: json.loads((ROOT/record["json_path"]).read_text())["bars"] for record in report["snapshots"]}
    datasets, records, errors = {}, {}, {}
    report.setdefault("producer_before_first_fetch", {"recorded_at": iso(datetime.now(timezone.utc)), "script_sha256": file_digest(Path(__file__))})
    write_report(output, report)
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {executor.submit(_download, symbol, report["protocol"], snapshots): symbol for symbol in SYMBOLS}
        for future in as_completed(futures):
            symbol = futures[future]
            try:
                datasets[symbol], records[symbol] = future.result()
            except ValueError as error:
                errors[symbol] = str(error)
    report["snapshots"] = [records[symbol] for symbol in SYMBOLS if symbol in records]
    report["source_errors"] = errors
    report["snapshot_finished_at"] = iso(datetime.now(timezone.utc))
    report["phase"] = "source_incomplete" if errors else "prices_snapshotted"
    write_report(output, report)
    if errors:
        return None
    coverage_errors = {}
    for symbol in SYMBOLS:
        try:
            records[symbol]["coverage"] = validate_sessions(datasets[symbol], report["protocol"]["calendar"], report["protocol"]["training"][0], report["protocol"]["holdout"][1])
            records[symbol]["provenance"]["coverage_verified"] = True
        except ValueError as error:
            coverage_errors[symbol] = str(error)
    report["coverage_errors"] = coverage_errors
    if coverage_errors:
        report["phase"] = "source_incomplete"
    write_report(output, report)
    return None if coverage_errors else datasets


def amend_feasibility(report, output=OUTPUT, snapshots=SNAPSHOTS):
    """Explicit execution-policy amendment, not repair of unsupported fills.

    This is permitted only before any training or holdout performance. Original
    protocol, source failure and response bytes remain immutable. New halfday
    flatten11:30 is dictated by observed timestamp availability, not PnL.
    """
    if report["protocol"]["version"] != "hourly-three-adaptations-v1" or report.get("training_lock") or report.get("strategies"):
        raise ValueError("Feasibility amendment requires original protocol before any performance")
    if report["phase"] != "source_incomplete" or report.get("source_errors") or len(report.get("snapshots", [])) != 3:
        raise ValueError("All original source snapshots required for explicit amendment")
    original = json.loads(canonical(report))
    failure_path = output.parent/"intraday-source-failure.json"
    if failure_path.exists():
        if json.loads(failure_path.read_text()) != original:
            raise ValueError("Original source failure record changed")
    else:
        immutable_write(failure_path, canonical(original)+"\n")
    protocol = json.loads(canonical(report["protocol"]))
    amended_at = iso(datetime.now(timezone.utc))
    protocol.update(version="hourly-three-adaptations-v2-halfday-1130", amended_at=amended_at,
                    parent_protocol_sha256=report["protocol_sha256"])
    protocol["calendar"]["early_flatten"] = "11:30"
    protocol["execution"]["flatten"] = "Normal15:30open unchanged; the same five fixed earlyclose dates flatten11:30OPEN. Original12:30policy unsupported by Yahoo; no fills on13:00 closing markers or interpolation"
    protocol["execution"]["source_bar_duration"] = "Vendor hourly labels retained; final halfday11:30bar duration until13:00 uncertain, never used for a same-day decision after11:30flatten. ATR14/Donchian20 count observed vendor bars, not20 literal60minute intervals"
    protocol["rules"]["hourly_noise_14"] += " v2: previous halfday fullsession close from observed13:00 nonexecutable reference, known only after that close; never infer it from11:30bar close. Final11:30halfday bar excluded from60minute sigma histories."
    protocol["data_quality"] += " v2 retains all sessions; only zero-volume exactcalendarclose references removed from executable bars. Each halfday requires observed11:30open and13:00 close reference."
    amendment_path = snapshots/"protocol-v2.json"
    if amendment_path.exists():
        # A failed structural-parser attempt may already have frozen the same
        # policy; retain its timestamp/hash instead of rewriting that lineage.
        existing = json.loads(amendment_path.read_text())
        if existing.get("parent_protocol_sha256") != original["protocol_sha256"] or existing.get("version") != protocol["version"]:
            raise ValueError("Existing feasibility amendment has another parent/policy")
        protocol, amended_at = existing, existing["amended_at"]
    else:
        immutable_write(amendment_path, canonical(protocol)+"\n")
    report["protocol"], report["protocol_sha256"] = protocol, digest(protocol)
    report["feasibility_amendment"] = {"recorded_at": amended_at, "before_any_performance": True,
                                         "original_protocol_sha256": original["protocol_sha256"],
                                         "original_failure_path": str(failure_path.relative_to(ROOT)), "original_failure_sha256": file_digest(failure_path),
                                         "reason": "All original halfday12:30open fills unavailable; newly frozen11:30earlyclose policy before any performance, not an original-policy pass",
                                         "unchanged": "Universe,dates,three families,lookbacks,costs,sizing,normalflatten,trainingselection and evidencegates unchanged",
                                         "source_receipts_unchanged": True, "no_session_removed": True, "new_protocol_path": str((snapshots/"protocol-v2.json").relative_to(ROOT))}
    datasets, records = {}, []
    for old in original["snapshots"]:
        old_path = ROOT/old["json_path"]
        if file_digest(old_path) != old["json_sha256"]:
            raise ValueError("Original snapshot fingerprint changed")
        snapshot = json.loads(old_path.read_text())
        markers, executable, equality_audit = {}, [], {}
        for bar in snapshot["bars"]:
            stamp = market.utc_datetime(bar["time"]).astimezone(timezone_for(protocol["calendar"]["timezone"]))
            date, slot = stamp.date().isoformat(), stamp.strftime("%H:%M")
            close = protocol["calendar"]["early_close"] if date in protocol["calendar"]["early_close_dates"] else protocol["calendar"]["close"]
            if slot == close and bar["volume"] == 0:
                markers[date] = {"time": bar["time"], "price": bar["close"], "slot": slot,
                                 "non_executable": True, "availability": "Only after actual declared session close",
                                 "ohlc_duration_unknown": True,
                                 "ohlc_is_point": len({bar[key] for key in ("open", "high", "low", "close")}) == 1,
                                 "basis": "Vendor boundary row: volume0 and exactfrozencalendarclose; only reportedclose used nextsession, never its OPEN/extrema as executableprices"}
            else:
                executable.append(dict(bar))
        for date in protocol["calendar"]["early_close_dates"]:
            if date not in markers:
                raise ValueError("Missing explicit13:00 halfday closing reference; no inferred replacement")
        for bar in executable:
            date, slot, flatten = _session_clock(bar, protocol["calendar"])
            if slot == flatten and date in markers:
                bar["session_close_reference"] = markers[date]
                equality_audit[date] = bar["close"] == markers[date]["price"]
        coverage = validate_sessions(executable, protocol["calendar"], protocol["training"][0], protocol["holdout"][1])
        path = snapshots/(old["symbol"]+"-1h-v2.json")
        amended_snapshot = {"bars": executable, "provenance": {**snapshot["provenance"], "coverage_verified": True,
                            "original_snapshot_sha256": old["json_sha256"], "close_references": markers,
                            "halfday_barclose_matches_closing_reference": equality_audit,
                            "derivation": "Exclude only explicit zero-volume exactsession-close markers; retain as nonexecutablenext-session references; no prices interpolated or sessionremoved"}}
        immutable_write(path, canonical(amended_snapshot)+"\n")
        datasets[old["symbol"]] = executable
        records.append({"symbol": old["symbol"], "bars": len(executable), "start": executable[0]["time"], "end": executable[-1]["time"],
                        "json_path": str(path.relative_to(ROOT)), "json_sha256": file_digest(path), "coverage": coverage,
                        "provider_receipt_path": str((snapshots/(old["symbol"]+"-provider-receipt.json")).relative_to(ROOT)),
                        "provider_receipt_sha256": file_digest(snapshots/(old["symbol"]+"-provider-receipt.json")),
                        "provenance": amended_snapshot["provenance"]})
    report.update(snapshots=records, phase="prices_snapshotted", source_errors={}, coverage_errors={},
                  decision="Explicit v2 feasibility amendment frozen before performance; original source failure retained; selection still pending")
    write_report(output, report)
    return datasets


def run(output=OUTPUT, snapshots=SNAPSHOTS):
    report = freeze(output, snapshots)
    if report["phase"] == "complete":
        return report
    if report.get("snapshots"):
        if report.get("source_errors") or report.get("coverage_errors"):
            return report
        datasets = {}
        for record in report["snapshots"]:
            path = ROOT/record["json_path"]
            if file_digest(path) != record["json_sha256"]:
                raise ValueError("Snapshot JSON fingerprint mismatch")
            if record.get("csv_path") and file_digest(ROOT/record["csv_path"]) != record["csv_sha256"]:
                raise ValueError("Snapshot CSV fingerprint mismatch")
            if record.get("provider_receipt_path"):
                receipt_path = ROOT/record["provider_receipt_path"]
                if file_digest(receipt_path) != record["provider_receipt_sha256"] or digest(json.loads(receipt_path.read_text())) != record["provenance"]["provider_payload_sha256"]:
                    raise ValueError("Provider receipt fingerprint mismatch")
            datasets[record["symbol"]] = json.loads(path.read_text())["bars"]
    else:
        datasets = snapshot_prices(report, output, snapshots)
    if datasets is None:
        report.update(selected_strategy_id=None, real_prop_qualified=False, live_orders=False,
                      decision="Fixed study blocked by source/calendar coverage; no days removed, no replacement market/family")
        write_report(output, report)
        return report
    started = time.monotonic()
    dependencies = ["scripts/research_sourced.py", "propdesk/backtest.py", "propdesk/strategies.py", "propdesk/market.py",
                    "propdesk/compliance.py", "propdesk/risk.py", "propdesk/timezones.py", "propdesk/feeds.py"]
    report["execution_producer_before_performance"] = {"recorded_at": iso(datetime.now(timezone.utc)), "script_sha256": file_digest(Path(__file__)),
                                                       "dependencies_sha256": {path: file_digest(ROOT/path) for path in dependencies},
                                                       "python_version": sys.version.split()[0]}
    lock = training_lock(datasets, report["protocol"])
    immutable_write(snapshots/"training-lock.json", canonical(lock)+"\n")
    report.update(phase="training_locked", training_lock=lock, training_lock_sha256=digest(lock), primary_strategy_id=lock["primary_strategy_id"])
    write_report(output, report)
    rows = evaluate_locked(datasets, lock, report["protocol"])
    primary = next(row for row in rows if row["primary"])
    report.update(phase="complete", strategies=rows, selected_strategy_id=primary["id"] if primary["eligible_historical_price_model"] else None,
                  real_prop_qualified=False, live_orders=False, finished_at=iso(datetime.now(timezone.utc)), elapsed_seconds=time.monotonic()-started,
                  decision="Primary is only a historical paper candidate" if primary["eligible_historical_price_model"] else "Locked primary failed; diagnostic families cannot replace it",
                  limitations=["Retrospective new hourly granularity reuses ETF/equity factors already inspected in earlier studies; nominal interval is not globally blind confirmation",
                               "Coarse hourly rules are our adaptations, not exact minute-source strategies", "Hypothetical stock borrow/margin and source OHLC are not executable CFD/futures bid/ask",
                               "Static5/10 model is illustrative; actual instrument contract, fees, restricted news and verified firm agreement required"])
    write_report(output, report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--freeze", action="store_true")
    parser.add_argument("--snapshot", action="store_true")
    parser.add_argument("--amend-feasibility", action="store_true")
    args = parser.parse_args()
    if args.freeze:
        report = freeze()
        print(canonical({"phase": report["phase"], "frozen_at": report["protocol"]["frozen_at"], "protocol_sha256": report["protocol_sha256"], "calendar": report["protocol"]["calendar"]}))
    elif args.amend_feasibility:
        report = freeze()
        amend_feasibility(report)
        print(canonical({"phase": report["phase"], "protocol_sha256": report["protocol_sha256"], "amendment": report["feasibility_amendment"], "coverage": [row["coverage"] for row in report["snapshots"]]}))
    elif args.snapshot:
        report = freeze()
        snapshot_prices(report)
        print(canonical({"phase": report["phase"], "snapshots": [{"symbol": row["symbol"], "bars": row["bars"], "start": row["start"], "end": row["end"]} for row in report.get("snapshots", [])], "source_errors": report.get("source_errors"), "coverage_errors": report.get("coverage_errors")}))
    else:
        report = run()
        print(canonical({"phase": report["phase"], "primary": report.get("primary_strategy_id"), "selected": report.get("selected_strategy_id"), "source_errors": report.get("source_errors"), "coverage_errors": report.get("coverage_errors"),
                         "strategies": [{"id": row["id"], "primary": row["primary"], "training": row["training"], "holdout": row["windows"]["holdout"]["metrics"], "ci99": row["windows"]["holdout"]["confidence"]["mean_daily_ci_pct"], "stress": row["windows"]["holdout"]["friction_stress"]["metrics"]["net_return_pct"], "reasons": row["reasons"]} for row in report.get("strategies", [])]}))
