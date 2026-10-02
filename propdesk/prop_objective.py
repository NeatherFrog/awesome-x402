"""Stage-aware documentary prop-payout scenarios, not a trading-profit forecast.

Public rules do not verify a user's contract. Complete equity envelopes and
reset snapshots are mandatory. Synthetic examples prove arithmetic only;
trade-only source cashflows are separate from modeled payout withdrawals.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import math

from propdesk.market import utc_datetime
from propdesk.timezones import timezone_for


SOURCE_URLS = {
    "ftmo_objectives": "https://ftmo.com/en/trading-objectives/",
    "ftmo_reward": "https://ftmo.com/en/faq/how-do-i-withdraw-my-profits/",
    "ftmo_comparison": "https://ftmo.com/en/comparison-table/",
    "topstep_mll": "https://help.topstep.com/en/articles/8284204-what-is-the-maximum-loss-limit",
    "topstep_payout": "https://help.topstep.com/en/articles/8284233-topstep-payout-policy",
    "topstep_consistency": "https://help.topstep.com/en/articles/8284208-consistency-at-topstep",
    "topstep_hours": "https://help.topstep.com/en/articles/8284206-when-and-what-products-can-i-trade",
    "topstep_pricing": "https://help.topstep.com/en/articles/14289835-topstep-pricing-and-payment-questions",
    "topstep_api": "https://help.topstep.com/en/articles/11187768-topstepx-api-access",
}


def number(value, name, *, minimum=-1e12):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < minimum:
        raise ValueError(name + " must be a finite number in its valid range")
    return float(value)


def reference_rules(stage):
    """Dated public100K reference products; no generic LFA/other-size fallback."""
    common = {"stage": stage, "nominal_size": 100_000.0,
              "public_source_checked_date": "2026-10-02", "user_verified_contract": False,
              "live_execution_authorized": False, "source_urls": SOURCE_URLS}
    if stage in ("ftmo_challenge", "ftmo_verification", "ftmo_funded"):
        return {**common, "firm": "FTMO", "product": "CFD2-Step Swing", "initial_balance": 100_000.0,
                "timezone": "Europe/Prague", "static_floor": 90_000.0, "daily_allowance": 5000.0,
                "target": {"ftmo_challenge": 10000.0, "ftmo_verification": 5000.0, "ftmo_funded": None}[stage],
                "min_opening_days": 0 if stage == "ftmo_funded" else 4,
                "payout_split": .8, "minimum_profit_before_reward": 20.0,
                "earliest_reward_calendar_days": 14, "evaluation_fee": None,
                "cloud_automation_compatibility": "Conditional legitimate EA/VPS permission; account/geolocation/API unverified",
                "assumptions": ["Boundary touch treated conservatively as breach", "Earliest reward requires both14 Prague calendar days and14 full elapsed days conservatively", "Bank-wire20USD profit threshold; actual method/contract unverified", "Reward ends this stage; next account requires a fresh authoritative snapshot"]}
    if stage in ("topstep_combine", "topstep_xfa_standard", "topstep_xfa_consistency"):
        xfa = stage != "topstep_combine"
        return {**common, "firm": "Topstep", "product": "100K TC/XFA", "initial_balance": 0.0 if xfa else 100_000.0,
                "timezone": "America/Chicago", "trailing_allowance": 3000.0,
                "trailing_cap": 0.0 if xfa else 100_000.0,
                "target": None if xfa else 6000.0, "consistency": .4 if stage == "topstep_xfa_consistency" else .55 if not xfa else None,
                "winning_days": 5 if stage == "topstep_xfa_standard" else None,
                "winning_day_minimum": 150.0, "trading_days": 3 if stage == "topstep_xfa_consistency" else None,
                "payout_split": .9, "payout_fraction": .5,
                "payout_cap": 4000.0 if stage == "topstep_xfa_consistency" else 3000.0 if xfa else None,
                "minimum_payout_request": 125.0, "evaluation_subscription_30days": 99.0,
                "standard_activation": 149.0, "no_activation_subscription_30days": 149.0,
                "no_activation_fee": 0.0,
                "cloud_automation_compatibility": "Cloud order transmission/relay prohibited; personal-device SIM API only; LFA API unsupported",
                "assumptions": ["125USD minimum interpreted as gross request; source does not explicitly define gross/net", "EOD ratchet uses explicit session-final point; exact backend MLL clock not verified", "Optional DLL excluded unless configured explicitly", "Generic hours do not verify contract-specific earlier closes or holiday schedules", "XFA new-window consistency excludes retained prior balance; request day excluded from next window"]}
    raise ValueError("Unsupported stage; LFA and FTMO1-Step require separate sourced rules")


def objective_math(nominal=100_000.0, monthly_pct=8.0):
    nominal = number(nominal, "nominal", minimum=.01)
    monthly_pct = number(monthly_pct, "monthly_pct", minimum=0)
    fraction, monthly = monthly_pct / 100, nominal * monthly_pct / 100
    return {"nominal": nominal, "monthly_trading_profit_goal": monthly,
            "compound_annual_return_pct": ((1 + fraction) ** 12 - 1) * 100,
            "fixed_monthly_withdrawal_annual_pct": monthly_pct * 12,
            "ftmo80_received_from_profit_goal": monthly * .8,
            "topstep90_received_before_cap_fees": monthly * .9,
            "gross_profit_for_equal_cash_ftmo80": monthly / .8,
            "gross_profit_for_equal_cash_split90": monthly / .9,
            "profit_goal_over_ftmo_loss_allowance": monthly / (nominal * .1),
            "profit_goal_over_topstep100k_mll": monthly / 3000,
            "topstep_standard_requests_min_before_fees": math.ceil(monthly / 2700),
            "topstep_consistency_requests_min_before_fees": math.ceil(monthly / 3600),
            "limitations": "Arithmetic target, not achievable strategy return or probability; caps, half-balance reserve, eligibility cycles and fees further constrain actual cash."}


def required_expectancy(gross_profit_goal, risk_per_trade, trades_per_month, *, payoff_r=2.0):
    """Target arithmetic only; p/R/cost inputs are not estimated from a strategy."""
    gross_profit_goal = number(gross_profit_goal, "gross_profit_goal", minimum=0)
    risk_per_trade = number(risk_per_trade, "risk_per_trade", minimum=.01)
    if isinstance(trades_per_month, bool) or not isinstance(trades_per_month, int) or trades_per_month < 1:
        raise ValueError("Positive integer trade count required")
    payoff_r = number(payoff_r, "payoff_r", minimum=.001)
    required_r = gross_profit_goal / risk_per_trade
    mean_r = required_r / trades_per_month
    # Illustrative binary payoff: winner+payoffR, loser−1R, already NET costs.
    return {"gross_goal": gross_profit_goal, "risk_per_trade": risk_per_trade,
            "trades_per_month": trades_per_month, "required_monthly_net_r": required_r,
            "required_mean_net_r_per_trade": mean_r,
            "binary_net_payoff_r": payoff_r,
            "implied_win_probability_for_expected_goal": (mean_r+1)/(payoff_r+1),
            "actual_win_probability_known": False,
            "limitations": "Expected-value equation only; net outcomes must be demonstrated, correlated losses/gaps and payout rules remain separate. No win-rate or success-probability estimate."}


def _wall(dt, zone):
    return dt.astimezone(timezone_for(zone))


def _reset_points(start, end, rule):
    """Required interior wall-clock boundaries; real DST offsets, no UTC guess."""
    zone = timezone_for(rule["timezone"])
    local = start.astimezone(zone).date()
    last = end.astimezone(zone).date()
    while local <= last:
        clocks = ((0, 0),) if rule["firm"] == "FTMO" else ((15, 10), (16, 0), (17, 0))
        for hour, minute in clocks:
            if rule["firm"] == "Topstep" and local.weekday() >= 5 and not (local.weekday() == 6 and hour == 17):
                continue
            point = datetime(local.year, local.month, local.day, hour, minute, tzinfo=zone).astimezone(timezone.utc)
            if start < point < end:
                yield point
        local += timedelta(days=1)


def _trade_day(stamp, rule):
    local = _wall(stamp, rule["timezone"])
    return local.date() + timedelta(days=1) if rule["firm"] == "Topstep" and local.hour >= 17 else local.date()


def _topstep_closed(stamp):
    local = _wall(stamp, "America/Chicago")
    clock = (local.hour, local.minute)
    return (local.weekday() == 5 or local.weekday() == 6 and clock < (17, 0)
            or local.weekday() == 4 and clock >= (15, 10)
            or (15, 10) <= clock < (17, 0))


def validate_path(points, rule, metadata):
    if not isinstance(metadata, dict) or metadata.get("complete_equity_envelopes") is not True:
        raise ValueError("Complete intraday equity envelopes must be supplied; closing balances alone cannot verify prop limits")
    if metadata.get("external_cashflows_in_source") is not False:
        raise ValueError("Source path must exclude payouts/deposits; they are modeled separately")
    if metadata.get("source_kind") not in ("synthetic_scenario", "authoritative_account_export"):
        raise ValueError("Source provenance must identify synthetic scenario or authoritative account export")
    if not isinstance(points, list) or len(points) < 2:
        raise ValueError("Initial snapshot and at least one complete interval required")
    result, previous = [], None
    for raw in points:
        stamp = utc_datetime(raw["time"])
        start = utc_datetime(raw["interval_start"])
        if previous is None:
            if start != stamp or raw["balance"] != rule["initial_balance"]:
                raise ValueError("Fresh stage must start at its exact actual balance; evaluation profits cannot transfer")
            local = _wall(stamp, rule["timezone"])
            if (local.hour, local.minute, local.second) != ((0, 0, 0) if rule["firm"] == "FTMO" else (17, 0, 0)):
                raise ValueError("Initial stage snapshot must be at its sourced daily/session reset")
        elif start != previous or stamp <= previous:
            raise ValueError("Equity intervals must be contiguous, unique and ordered")
        if list(_reset_points(start, stamp, rule)):
            raise ValueError("Missing authoritative snapshot at a daily/session boundary")
        values = {key: number(raw[key], key) for key in ("balance", "net_equity", "worst_equity", "best_equity")}
        if not values["worst_equity"] <= values["net_equity"] <= values["best_equity"]:
            raise ValueError("Equity must lie inside the complete worst/best envelope")
        if result and not values["worst_equity"] <= result[-1]["net_equity"] <= values["best_equity"]:
            raise ValueError("Complete interval envelope must include the prior endpoint; gaps cannot be omitted")
        positions, orders = raw["open_positions"], raw["open_orders"]
        if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in (positions, orders)):
            raise ValueError("Position/order counts must be nonnegative integers")
        if previous is None and (positions or orders):
            raise ValueError("Fresh stage cannot hide positions/orders from an earlier account")
        trades = [utc_datetime(value) for value in raw["trade_open_times"]]
        if previous is None and (trades or any(values[key] != rule["initial_balance"] for key in ("net_equity", "worst_equity", "best_equity"))):
            raise ValueError("Fresh initial snapshot must have no floating PnL, hidden earlier range or trade openings")
        if any(not start <= value <= stamp for value in trades):
            raise ValueError("Trade opening times must belong to the covered interval")
        result.append({**raw, **values, "_time": stamp, "_start": start, "_trades": trades})
        previous = stamp
    return result


def replay_stage(points, stage, metadata, *, optional_dll=None, payout_method_fee=0.0):
    """Deterministic path replay. Payout approval and strategy feasibility unknown."""
    rule = reference_rules(stage)
    points = validate_path(points, rule, metadata)
    if optional_dll is not None:
        optional_dll = number(optional_dll, "optional_dll", minimum=.01)
        if rule["firm"] != "Topstep" or optional_dll != 2000:
            raise ValueError("Only sourced optional100K Topstep2000DLL supported")
    payout_method_fee = number(payout_method_fee, "payout_method_fee", minimum=0)
    initial = rule["initial_balance"]
    floor = rule.get("static_floor", initial - rule.get("trailing_allowance", 0))
    daily_reference = initial
    high_eod = initial
    withdrawn = cash = 0.0
    payout_events, breaches, rejected = [], [], []
    opening_days, cycle_traded = set(), set()
    winning_days = cycle_profit = best_day = 0
    day_profit = 0.0
    excluded_day = first_trade = None
    paused_day = None
    snapshots = []
    phase = "incomplete_stage"
    for i, point in enumerate(points):
        stamp, raw_balance = point["_time"], point["balance"]
        balance, equity = raw_balance - withdrawn, point["net_equity"] - withdrawn
        worst, best = point["worst_equity"] - withdrawn, point["best_equity"] - withdrawn
        local, trading_day = _wall(stamp, rule["timezone"]), _trade_day(stamp, rule)
        prior_day = _trade_day(point["_start"], rule)
        if i:
            day_profit += raw_balance - points[i-1]["balance"]
        for trade in point["_trades"]:
            opening_days.add(_trade_day(trade, rule))
            if _trade_day(trade, rule) != excluded_day:
                cycle_traded.add(_trade_day(trade, rule))
            if first_trade is None or trade < first_trade:
                first_trade = trade
            if rule["firm"] == "Topstep" and (_topstep_closed(trade) or paused_day == _trade_day(trade, rule)):
                breaches.append({"time": point["time"], "rule": "trade_during_closed_or_DLL_paused_session"})
        allowance = rule.get("daily_allowance", optional_dll)
        daily_floor = daily_reference - allowance if allowance is not None else None
        if worst <= floor:
            breaches.append({"time": point["time"], "rule": "total_loss_touch", "floor": floor, "worst_equity": worst})
        if daily_floor is not None and worst <= daily_floor:
            if rule["firm"] == "FTMO":
                breaches.append({"time": point["time"], "rule": "daily_loss_touch", "floor": daily_floor, "worst_equity": worst})
            else:
                paused_day = prior_day
                if point["open_positions"] or point["open_orders"]:
                    breaches.append({"time": point["time"], "rule": "DLL_requires_forced_flat_session_pause"})
        if rule["firm"] == "Topstep":
            if _topstep_closed(stamp) and (point["open_positions"] or point["open_orders"]):
                breaches.append({"time": point["time"], "rule": "positions_or_orders_after_session_close"})
            if (local.hour, local.minute) == (15, 10):
                if point.get("session_end") is not True:
                    raise ValueError("Explicit final session balance required for EOD trailing update")
                high_eod = max(high_eod, balance)
                floor = max(floor, min(high_eod - rule["trailing_allowance"], rule["trailing_cap"]))
                if stage == "topstep_combine":
                    cycle_profit += day_profit
                    best_day = max(best_day, day_profit)
                    day_profit = 0.0
            if (local.hour, local.minute) == (16, 0):
                if point.get("day_close") is not True:
                    raise ValueError("Explicit16CT payout-day finalization required")
                if stage != "topstep_combine" and trading_day != excluded_day:
                    cycle_profit += day_profit
                    best_day = max(best_day, day_profit)
                    winning_days += day_profit >= rule["winning_day_minimum"]
                day_profit = 0.0
            if (local.hour, local.minute) == (17, 0):
                daily_reference = balance
                daily_floor = daily_reference - allowance if allowance is not None else None
                if daily_floor is not None and equity <= daily_floor:
                    paused_day = trading_day
                    if point["open_positions"] or point["open_orders"]:
                        breaches.append({"time": point["time"], "rule": "new_session_DLL_requires_forced_flat"})
        elif (local.hour, local.minute, local.second) == (0, 0, 0):
            # Previous interval was checked against its previous midnight floor;
            # floating equity is also checked against the NEW midnight balance.
            daily_reference = balance
            daily_floor = daily_reference - rule["daily_allowance"]
            if equity <= daily_floor:
                breaches.append({"time": point["time"], "rule": "new_midnight_daily_loss", "floor": daily_floor, "equity": equity})
        if equity <= floor and not any(event["time"] == point["time"] and event["rule"] == "total_loss_touch" for event in breaches):
            breaches.append({"time": point["time"], "rule": "new_trailing_floor_touch", "floor": floor, "equity": equity})
        snapshot = {"time": point["time"], "balance": balance, "net_equity": equity,
                    "worst_equity": worst, "best_equity": best, "total_floor": floor,
                    "daily_floor": daily_floor, "daily_reference": daily_reference,
                    "cycle_profit": cycle_profit, "best_day": best_day, "winning_days": winning_days,
                    "cycle_trading_days": len(cycle_traded)}
        snapshots.append(snapshot)
        if breaches:
            phase = "breached_model_rule"
            break
        flat = point["open_positions"] == point["open_orders"] == 0
        if rule["target"] is not None and balance - initial >= rule["target"] and flat:
            consistency_ok = rule["firm"] != "Topstep" or (cycle_profit > 0 and best_day <= rule["consistency"] * cycle_profit)
            if len(opening_days) >= rule.get("min_opening_days", 0) and consistency_ok:
                phase = "evaluation_passed_model"
                break
        requested = point.get("payout_request_gross")
        if requested is not None:
            requested = number(requested, "payout_request_gross", minimum=.01)
            reasons = []
            if rule["target"] is not None:
                reasons.append("evaluation_profit_not_withdrawable")
            if not flat:
                reasons.append("positions_and_orders_must_be_closed")
            if rule["firm"] == "FTMO":
                age = (_wall(stamp, rule["timezone"]).date() - _wall(first_trade, rule["timezone"]).date()).days if first_trade else -1
                elapsed = (stamp-first_trade).total_seconds() if first_trade else -1
                if age < rule["earliest_reward_calendar_days"] or elapsed < 14*24*3600:
                    reasons.append("reward_too_early")
                if balance - initial < rule["minimum_profit_before_reward"] or requested > balance - initial:
                    reasons.append("insufficient_closed_profit")
            else:
                if stage == "topstep_xfa_standard" and winning_days < 5:
                    reasons.append("need_five_150usd_winning_days")
                if stage == "topstep_xfa_consistency" and (len(cycle_traded) < 3 or cycle_profit <= 0 or best_day > .4 * cycle_profit):
                    reasons.append("new_window_three_days_and_40pct_consistency_required")
                if requested < rule["minimum_payout_request"]:
                    reasons.append("below_assumed_gross_minimum125")
                if requested > min(max(0, balance) * .5, rule["payout_cap"] or 0):
                    reasons.append("exceeds_half_balance_or_stage_cap")
            if reasons:
                rejected.append({"time": point["time"], "requested": requested, "reasons": reasons})
            else:
                receive = requested * rule["payout_split"] - payout_method_fee
                if receive < 0:
                    raise ValueError("Payout method fee exceeds modeled reward")
                withdrawn += requested
                cash += receive
                payout_events.append({"time": point["time"], "gross_profit_removed": requested,
                                      "split": rule["payout_split"], "method_fee": payout_method_fee,
                                      "cash_received_model": receive, "remaining_balance": balance-requested,
                                      "approval_guaranteed": False})
                if rule["firm"] == "FTMO":
                    phase = "funded_reward_requested_model_account_boundary"
                    break
                floor = max(floor, 0)
                # A permitted cash withdrawal is not a trading loss. Keep the
                # DLL PnL baseline cashflow-neutral while the MLL locks to zero.
                daily_reference -= requested
                snapshot["post_payout_floor"] = floor
                snapshot["post_payout_balance"] = balance-requested
                if equity-requested <= floor:
                    breaches.append({"time": point["time"], "rule": "post_payout_loss_buffer_exhausted", "floor": floor})
                    phase = "breached_model_rule"
                    break
                excluded_day = trading_day
                winning_days = cycle_profit = best_day = 0
                cycle_traded = set()
                day_profit = 0.0
                phase = "funded_payout_requested_model"
    last = snapshots[-1]
    return {"stage": stage, "rules": rule, "phase": phase, "breaches": breaches,
            "snapshots": snapshots, "payouts": payout_events, "payout_rejections": rejected,
            "gross_trading_profit": points[len(snapshots)-1]["balance"]-initial,
            "gross_withdrawn_model": withdrawn, "cash_received_model": cash,
            "end_balance_model": last["balance"]- (payout_events[-1]["gross_profit_removed"] if payout_events and payout_events[-1]["time"] == last["time"] else 0),
            "authoritative_marks_supplied": metadata["source_kind"] == "authoritative_account_export",
            "DLL_intrabar_ordering_verified": optional_dll is None,
            "user_verified_contract": False, "strategy_profitability_proven": False,
            "live_execution_authorized": False, "full_contract_compliance_proven": False,
            "limitations": "Sourced subset of financial rules only. Brokerage costs must already be net in path. Actual contract, exact backend EOD timing, payout approval, holiday/product closes and connector unverified. No probability/EV claim."}


def replay_lifecycle(stages):
    """Separate stage paths enforce fresh balances; payout never inherits eval PnL."""
    results = []
    for index, item in enumerate(stages):
        if index and results[-1]["phase"] != "evaluation_passed_model":
            raise ValueError("Cannot enter a funded/next evaluation stage without preceding model pass")
        if index:
            expected = {"ftmo_challenge": "ftmo_verification", "ftmo_verification": "ftmo_funded", "topstep_combine": ("topstep_xfa_standard", "topstep_xfa_consistency")}.get(results[-1]["stage"])
            if item["stage"] not in (expected if isinstance(expected, tuple) else (expected,)):
                raise ValueError("Invalid stage transition")
            if utc_datetime(item["points"][0]["time"]) < utc_datetime(results[-1]["snapshots"][-1]["time"]):
                raise ValueError("Next stage cannot begin before the preceding stage completes")
        result = replay_stage(item["points"], item["stage"], item["metadata"], **item.get("options", {}))
        results.append(result)
    return {"stages": results, "cash_received_model": sum(row["cash_received_model"] for row in results),
            "evaluation_profit_withdrawn": False, "live_execution_authorized": False,
            "external_fees_not_included": True, "net_profit_after_challenge_fees": None}
