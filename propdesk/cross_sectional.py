"""Causal current-survivor crypto rotation; physical 1x research account only.

Daily ranks are a new adaptation of weekly momentum research. Computed mark
bars bound risk, never create executable fills. Financing is a perpetual proxy,
not a claimed FTMO swap. No account API or signal delivery is present.
"""
from __future__ import annotations

from array import array
from bisect import bisect_left, bisect_right
from collections import defaultdict
from datetime import timedelta
import math
import statistics

from . import market
from .cross_sectional_data import SYMBOLS, digest


def grid():
    result = []
    for family in ("long_strength", "balanced_momentum", "balanced_financing"):
        for lookback in (7, 14, 28):
            for rebalance in (1, 7):
                for normalized in (False, True):
                    for risk in (.005, .01):
                        v = {"family": family, "lookback_days": lookback, "rebalance_days": rebalance,
                             "volatility_normalized_rank": normalized, "risk_fraction": risk,
                             "portfolio_stop_risk": .03 if risk == .005 else .04,
                             "volatility_days": 28, "liquidity_days": 30,
                             "minimum_median_quote_volume": 20000000, "side_assets": 3,
                             "skip_latest_momentum_day": 1, "funding_history_days": 7,
                             "stop_daily_atr": 2, "gross_cap": 1, "asset_gross_cap": .35,
                             "isolated_leverage": 1, "quantity_step_assumption": .001}
                        v["id"] = "cross_sectional-" + digest(v)[:12]
                        result.append(v)
    return result


def _atr(high, low, close, period=20):
    result = [None] * len(close)
    tr = []
    for i in range(len(close)):
        tr.append(high[i] - low[i] if i == 0 else max(high[i] - low[i],
                  abs(high[i] - close[i-1]), abs(low[i] - close[i-1])))
        if i == period-1:
            result[i] = math.fsum(tr) / period
        elif i >= period:
            result[i] = (result[i-1] * (period-1) + tr[-1]) / period
    return result


class Features:
    def __init__(self, trades, marks, funding):
        if any(set(rows) != set(SYMBOLS) for rows in (trades, marks, funding)):
            raise ValueError("Exact fixed eleven-asset cohort required; no selected subset")
        self.times = [r["time"] for r in trades[SYMBOLS[0]]]
        if not self.times or len(self.times) % 24:
            raise ValueError("Complete UTC hourly days required")
        self.epochs = [market.utc_datetime(t).timestamp() for t in self.times]
        if self.epochs[0] % 86400 or any(e % 3600 for e in self.epochs) or any(b-a != 3600 for a, b in zip(self.epochs, self.epochs[1:])):
            raise ValueError("Hourly calendar cannot be filled or repaired")
        self.raw, self.mark, self.daily, self.funding, self.events = {}, {}, {}, {}, {}
        self.cached = {}
        for s in SYMBOLS:
            if ([r["time"] for r in trades[s]] != self.times or [r["time"] for r in marks[s]] != self.times):
                raise ValueError("Trade/mark clocks must be identical across all eleven assets")
            for rows in (trades[s], marks[s]):
                if any(market.utc_datetime(r["known_at"]).timestamp() != epoch+3600 for r, epoch in zip(rows, self.epochs)):
                    raise ValueError("Only completed hourly source observations are available")
                for r in rows:
                    o, h, lo, c = (float(r[k]) for k in ("open", "high", "low", "close"))
                    if min(o, h, lo, c) <= 0 or any(not math.isfinite(v) for v in (o, h, lo, c)) or lo > min(o, c) or h < max(o, c):
                        raise ValueError("Invalid source OHLC envelope")
            if any(not math.isfinite(float(r.get(k, 0))) or r.get(k, 0) < 0 for r in trades[s] for k in ("volume", "quote_volume")):
                raise ValueError("Invalid trade volume")
            if any(isinstance(r.get("source_auxiliary_count"), bool) or not isinstance(r.get("source_auxiliary_count"), int)
                   or r["source_auxiliary_count"] < 0 for r in marks[s]):
                raise ValueError("Mark auxiliary metadata must be retained as nontrade count")
            self.raw[s] = {k: array("d", (r[k] for r in trades[s]))
                           for k in ("open", "high", "low", "close", "volume", "quote_volume")}
            self.mark[s] = {k: array("d", (r[k] for r in marks[s])) for k in ("open", "high", "low", "close")}
            self.mark[s]["count"] = array("q", (r["source_auxiliary_count"] for r in marks[s]))
            daily = {k: [] for k in ("open", "high", "low", "close", "quote", "valid_close")}
            raw = self.raw[s]
            for i in range(0, len(self.times), 24):
                daily["open"].append(raw["open"][i])
                daily["high"].append(max(raw["high"][i:i+24]))
                daily["low"].append(min(raw["low"][i:i+24]))
                daily["close"].append(raw["close"][i+23])
                daily["quote"].append(math.fsum(raw["quote_volume"][i:i+24]))
                daily["valid_close"].append(raw["volume"][i+23] > 0)
            daily["atr"] = _atr(daily["high"], daily["low"], daily["close"])
            self.daily[s] = daily
            parsed, previous = [], None
            for r in funding[s]:
                epoch = market.utc_datetime(r["time"]).timestamp()
                if market.utc_datetime(r["known_at"]).timestamp() != epoch or r.get("rate_kind") != "realized_settlement_outcome":
                    raise ValueError("Actual funding becomes available at its source settlement timestamp")
                rate = float(r["funding_rate"])
                if not math.isfinite(rate) or abs(rate) > 1 or previous is not None and epoch <= previous:
                    raise ValueError("Funding events must be finite, ascending, and unique")
                previous = epoch
                parsed.append({"epoch": epoch, "time": r["time"], "rate": rate})
            self.events[s] = parsed
            buckets = defaultdict(list)
            for e in parsed:
                i = bisect_right(self.epochs, e["epoch"])-1
                if 0 <= i < len(self.times) and e["epoch"] < self.epochs[i]+3600:
                    buckets[i].append(e)
            self.funding[s] = buckets

    def observations(self, variant):
        key = (variant["family"], variant["lookback_days"], variant["volatility_normalized_rank"])
        if key in self.cached:
            return self.cached[key]
        result = {}
        for d in range(30, len(self.times)//24):
            decision_epoch = self.epochs[d*24]
            eligible = []
            for s in SYMBOLS:
                x = self.daily[s]
                if not all(x["valid_close"][d-30:d]) or statistics.median(x["quote"][d-30:d]) < 20000000:
                    continue
                closes = x["close"]
                volatility = statistics.stdev(math.log(closes[j]/closes[j-1]) for j in range(d-28, d))
                momentum = math.log(closes[d-2]/closes[d-2-variant["lookback_days"]])
                score = momentum
                if variant["family"] == "balanced_financing":
                    recent = [e["rate"] for e in self.events[s] if decision_epoch-7*86400 < e["epoch"] <= decision_epoch]
                    score = momentum/variant["lookback_days"] - math.fsum(recent)/7
                if variant["volatility_normalized_rank"]:
                    score /= max(volatility, .005)
                atr = x["atr"][d-1]
                if atr is not None and atr > 0:
                    eligible.append({"symbol": s, "score": score, "momentum": momentum,
                                     "volatility": max(volatility, .005), "atr": atr})
            eligible.sort(key=lambda r: (-r["score"], r["symbol"]))
            targets = {}
            if variant["family"] == "long_strength":
                groups = [(1, [r for r in eligible if r["momentum"] > 0][:3])]
            elif len(eligible) >= 6:
                groups = [(1, eligible[:3]), (-1, eligible[-3:])]
            else:
                groups = []
            for side, group in groups:
                total = math.fsum(1/r["volatility"] for r in group)
                side_fraction = len(group)/3 if variant["family"] == "long_strength" else .5
                for r in group:
                    targets[r["symbol"]] = {**r, "direction": side,
                                            "weight": side_fraction/r["volatility"]/total,
                                            "known_at": self.times[d*24], "decision_epoch": decision_epoch}
            result[d] = targets
        self.cached[key] = result
        return result


def simulate(features, variant, start_date, end_date, *, initial=100000, cost_multiplier=1):
    if not math.isfinite(initial) or initial <= 0 or cost_multiplier not in (1, 2):
        raise ValueError("Positive physical capital and registered cost scenario required")
    start = bisect_left(features.times, start_date+"T00:00:00Z")
    end = bisect_left(features.times, end_date+"T00:00:00Z")
    if (not 0 <= start < end <= len(features.times) or (end-start) % 24
            or features.times[start] != start_date+"T00:00:00Z"
            or features.epochs[end-1]+3600 != market.utc_datetime(end_date+"T00:00:00Z").timestamp()):
        raise ValueError("Exact complete requested calendar required")
    fee, adverse = .00065*cost_multiplier, .00025*cost_multiplier
    cash = float(initial)
    positions, slices, funding_ledger, order_plans, daily = {}, [], [], [], []
    total_funding = fees_paid = adverse_paid = turnover = 0.0
    liquidations = sparse_held = skipped = zero_trade_held = reopening_unknown = 0
    sparse_opening_intents = 0
    opening_mark_gap_breaches = 0
    retrospective_union_gross_breaches = retrospective_union_risk_breaches = 0
    maximum_entry_union_gross = maximum_entry_union_stop_risk = 0.0
    worst_deficit = 0.0
    minimum_cash = cash
    targets, expiry, blocked = {}, -1, set()
    serial = 0
    observed = features.observations(variant)
    anchor = market.utc_datetime("2024-01-01T00:00:00Z").timestamp()

    def wallet(p, price):
        return p["margin"]+p["funding"]+p["direction"]*p["quantity"]*(price-p["entry_price"])

    def equity(prices):
        return cash+math.fsum(0 if p["liquidation_latched"] else max(0, wallet(p, prices[s])) for s, p in positions.items())

    def held_stop_risk(p, price):
        stop_fill = p["stop_price"]*(1-adverse*p["direction"])
        return p["quantity"]*(max(0, p["direction"]*(price-stop_fill))+stop_fill*fee)

    def close(s, price, i, reason, *, fraction=1, timing="open", liquidating=False):
        nonlocal cash, fees_paid, adverse_paid, turnover, liquidations, worst_deficit, reopening_unknown
        p = positions[s]
        fraction = min(1, max(0, fraction))
        if liquidating:
            fraction = 1
        if fraction < 1:
            kept = math.floor(p["quantity"]*(1-fraction)/.001+1e-10)*.001
            fraction = 1-kept/p["quantity"]
        if fraction <= 0:
            return
        part = {**p, "quantity": p["quantity"]*fraction, "margin": p["margin"]*fraction,
                "funding": p["funding"]*fraction, "entry_fee": p["entry_fee"]*fraction}
        fill = price*(1-adverse*p["direction"])
        exit_fee = part["quantity"]*fill*fee
        liq_fee = part["quantity"]*price*.005 if liquidating else 0
        value = wallet(part, fill)-exit_fee-liq_fee
        recover = 0.0 if liquidating else max(0, value)
        cash += recover
        fees_paid += exit_fee+liq_fee
        adverse_paid += part["quantity"]*abs(fill-price)
        turnover += part["quantity"]*fill
        liquidations += int(liquidating)
        reopening_unknown += int(p.get("previous_zero_trade", False))
        deficit = max(0, -value, part.get("worst_mark_deficit", 0))
        worst_deficit = max(worst_deficit, deficit)
        pnl = recover-part["margin"]-part["entry_fee"]
        ordinary = part["direction"]*part["quantity"]*(fill-part["entry_price"])+part["funding"]-part["entry_fee"]-exit_fee-liq_fee
        slices.append({**part, "symbol": s, "exit_time": (market.utc_datetime(features.times[i])+timedelta(hours=1)).isoformat().replace("+00:00", "Z") if timing=="close" else features.times[i],
                       "exit_raw_price": price, "exit_price": fill, "exit_fee": exit_fee,
                       "liquidation_fee": liq_fee, "recovered_margin": recover, "pnl": pnl,
                       "accounting_adjustment": pnl-ordinary, "reason": reason,
                       "completed_episode": fraction == 1, "partial_fraction": fraction,
                       "intrabar_exit_time_unknown": timing=="close", "unfunded_isolated_deficit": deficit,
                       "exit_time_kind": "hour_end_known_at_upper_bound" if timing=="close" else "opening_model_proxy",
                       "reopening_execution_time_unknown": p.get("previous_zero_trade", False)})
        if fraction == 1:
            del positions[s]
        else:
            for k in ("quantity", "margin", "funding", "entry_fee"):
                p[k] *= 1-fraction

    def funding_charge(s, i, *, exact, ambiguous=False):
        nonlocal total_funding
        if s not in positions:
            return
        p = positions[s]
        for e in features.funding[s].get(i, ()):
            if ((e["epoch"] == features.epochs[i]) != exact or e["epoch"]-p["entry_epoch"] <= 0
                    or e["epoch"] <= p.get("last_funding_epoch", -math.inf)):
                continue
            mark = features.mark[s]["close"][i-1] if exact else features.mark[s]["open"][i]
            amount = -p["direction"]*p["quantity"]*mark*e["rate"]
            original = amount
            # The trade hour cannot prove the first-fill second. Positive
            # income needs a fully older position, no exact-time/exit tie.
            if amount > 0 and (exact or ambiguous or p["liquidation_latched"] or e["epoch"]-p["entry_epoch"] < 3660):
                amount = 0.0
            p["funding"] += amount
            p["last_funding_epoch"] = e["epoch"]
            total_funding += amount
            funding_ledger.append({"symbol": s, "episode_id": p["episode_id"], "time": e["time"],
                                   "rate": e["rate"], "mark_proxy": mark, "pnl": amount,
                                   "unadjusted_amount": original, "held_seconds": e["epoch"]-p["entry_epoch"],
                                   "point_mark_and_entitlement_unverified": True,
                                   "exact_time_credit_omitted": exact and original > 0,
                                   "intrabar_entitlement_ambiguous": ambiguous})

    day_start = day_worst = day_best = initial
    for i in range(start, end):
        raw = {s: features.raw[s]["open"][i] for s in SYMBOLS}
        marks = {s: features.mark[s]["close"][i-1] if i else features.mark[s]["open"][i] for s in SYMBOLS}
        for s, p in positions.items():
            if wallet(p, marks[s]) <= .005*p["quantity"]*marks[s]:
                p.update(liquidation_latched=True, pending_reason="known_mark_liquidation_proxy")
        opening = equity(marks)
        if (i-start) % 24 == 0:
            day_start = daily[-1]["equity"] if daily else initial
            day_worst = min(day_start, opening)
            day_best = max(day_start, opening)
        rebalance = i % 24 == 1 and int((features.epochs[i]-3600-anchor)//86400) % variant["rebalance_days"] == 0
        if rebalance:
            targets = observed.get(i//24, {})
            expiry = features.epochs[i]+7200
            blocked = set()
        gross = math.fsum(p["quantity"]*marks[s] for s, p in positions.items())
        risk_held = math.fsum(held_stop_risk(p, marks[s]) for s, p in positions.items())
        cap = max(0, min(initial, opening))
        # A known-opening defensive reduction never releases funds for an
        # earlier/same-hour new order. All entry plans precede volume checks.
        reduction = max(0, 1-min(1, cap/gross if gross else 1,
                        variant["portfolio_stop_risk"]*max(0, opening)/risk_held if risk_held else 1))
        exits = {}
        for s, p in positions.items():
            target = targets.get(s)
            reason = p.get("pending_reason")
            if i == end-1:
                reason = "predeclared_last_hour_boundary_exit"
            elif rebalance and (target is None or target["direction"] != p["direction"]):
                reason = reason or "closed_daily_rank_rotation"
            if reason:
                exits[s] = (1, reason)
            elif reduction > 1e-12:
                exits[s] = (reduction, "known_open_portfolio_risk_reduction")
        intents = {}
        if features.epochs[i] <= expiry and i < end-2 and opening > 0:
            for s, target in targets.items():
                if s in positions or s in blocked:
                    continue
                side = target["direction"]
                fill = raw[s]*(1+adverse*side)
                distance = target["atr"]*2
                stop = fill-side*distance
                if stop <= 0 or side*(marks[s]-stop) <= 0:
                    continue
                unit_risk = distance+fill*fee+stop*adverse+stop*(1-adverse*side)*fee
                q = min(cap*min(target["weight"], .35)/fill,
                        opening*variant["risk_fraction"]/unit_risk)
                intents[s] = {"quantity": q, "fill": fill, "stop": stop, "unit_risk": unit_risk,
                              "target": target, "direction": side}
        needed = math.fsum(p["quantity"]*p["fill"]*(1+fee) for p in intents.values())
        needed_gross = math.fsum(p["quantity"]*p["fill"] for p in intents.values())
        needed_risk = math.fsum(p["quantity"]*p["unit_risk"] for p in intents.values())
        scale = min(1, max(0, cash)/needed if needed else 1,
                    max(0, cap-gross)/needed_gross if needed_gross else 1,
                    max(0, opening*variant["portfolio_stop_risk"]-risk_held)/needed_risk if needed_risk else 1)
        plans = {}
        for s, p in intents.items():
            q = math.floor(p["quantity"]*scale/.001)*.001
            if q > 0:
                plans[s] = {**p, "quantity": q}
        # Risk and asset caps can otherwise turn an equal-weight signal into
        # very unequal sides. Balance the projected retained+new book after
        # those caps, by reducing new quantities and then old quantities.
        # These plans use known opening inputs; actual unfilled exits remain
        # explicit uncertain exposure, never an atomic-basket assumption.
        if variant["family"] != "long_strength":
            held = {side: math.fsum(p["quantity"]*marks[s]*(1-exits.get(s, (0, ""))[0])
                                   for s, p in positions.items() if p["direction"] == side) for side in (1, -1)}
            added = {side: math.fsum(p["quantity"]*p["fill"] for p in plans.values() if p["direction"] == side) for side in (1, -1)}
            totals = {side: held[side]+added[side] for side in (1, -1)}
            large = 1 if totals[1] > totals[-1] else -1
            gap = totals[large]-totals[-large]
            trim_new = min(gap, added[large])
            factor = max(0, 1-trim_new/added[large]) if added[large] else 1
            for p in plans.values():
                if p["direction"] == large:
                    p["quantity"] = math.floor(p["quantity"]*factor/.001+1e-10)*.001
            remaining_gap = max(0, gap-trim_new)
            held_factor = max(0, 1-remaining_gap/held[large]) if held[large] else 1
            if held_factor < 1:
                for s, p in positions.items():
                    if p["direction"] == large:
                        old_fraction, old_reason = exits.get(s, (0, ""))
                        exits[s] = (1-(1-old_fraction)*held_factor, old_reason or "known_open_side_balance_reduction")
            plans = {s: p for s, p in plans.items() if p["quantity"] > 0}
        planned_sides = {side: math.fsum(p["quantity"]*marks[s]*(1-exits.get(s, (0, ""))[0])
                                           for s, p in positions.items() if p["direction"] == side)
                             + math.fsum(p["quantity"]*p["fill"] for p in plans.values() if p["direction"] == side)
                         for side in (1, -1)}
        for s, p in plans.items():
                q = p["quantity"]
                sparse_opening_intents += features.mark[s]["count"][i-1] <= 2
                order_plans.append({"symbol": s, "time": features.times[i], "direction": p["direction"],
                                    "quantity": q, "opening_total_equity": opening, "opening_free_cash": cash,
                                    "known_mark": marks[s], "gross_before_fills": gross,
                                    "signal_known_at": p["target"]["known_at"], "stop_price": p["stop"],
                                    "planned_long_notional": planned_sides[1], "planned_short_notional": planned_sides[-1],
                                    "joint_reserved_cash": math.fsum(z["quantity"]*z["fill"]*(1+fee) for z in plans.values())})
        # These snapshots bound an old position that may still be held until
        # the hour's first executable trade; they cannot size current orders.
        preclose = {s: dict(p) for s, p in positions.items()}
        preclose_cash = cash
        # Boundary settlement outcomes are not an earlier order-sizing
        # observation. Preserve any debit only after every joint plan is
        # locked, then recheck maintenance before recovering an old wallet.
        for s, p in positions.items():
            funding_charge(s, i, exact=True)
            preclose[s]["funding"] = p["funding"]
            if wallet(p, marks[s]) <= .005*p["quantity"]*marks[s]:
                p.update(liquidation_latched=True, pending_reason="boundary_debit_liquidation_bound")
                preclose[s].update(liquidation_latched=True, pending_reason=p["pending_reason"])
                exits[s] = (1, p["pending_reason"])
        # Current mark OPEN is not an earlier sizing observation. It is used
        # only now as an adverse automatic-liquidation bound before recovering
        # an old wallet or crediting uncertain later settlements.
        for s, p in positions.items():
            gap_mark = features.mark[s]["open"][i]
            if wallet(p, gap_mark) <= .005*p["quantity"]*gap_mark:
                if not p["liquidation_latched"]:
                    opening_mark_gap_breaches += 1
                p.update(liquidation_latched=True, pending_reason="current_mark_open_liquidation_bound")
                exits[s] = (1, p["pending_reason"])
                preclose[s].update(liquidation_latched=True, pending_reason=p["pending_reason"])
        for s, (fraction, reason) in exits.items():
            p = positions[s]
            if features.raw[s]["volume"][i] <= 0:
                p["pending_reason"] = reason
                continue
            # An hourly OPEN is the first trade sometime inside the hour.
            # A debit may precede that trade/reduction. Include it once on
            # the old full position and omit uncertain credits; stamp the
            # exit's known-at at hour end rather than invent its second.
            funding_charge(s, i, exact=False, ambiguous=True)
            preclose[s]["funding"] = p["funding"]
            possible_mark = features.mark[s]["low" if p["direction"]>0 else "high"][i]
            possible_value = wallet(p, possible_mark)
            p["worst_mark_deficit"] = max(p["worst_mark_deficit"], -possible_value, 0)
            if possible_value <= .005*p["quantity"]*possible_mark and not p["liquidation_latched"]:
                p.update(liquidation_latched=True, pending_reason="old_exit_after_debit_liquidation_bound")
                preclose[s]["liquidation_latched"] = True
                reason = p["pending_reason"]
            close(s, raw[s], i, reason, fraction=fraction, timing="close", liquidating=p["liquidation_latched"])
        for s, plan in plans.items():
            if features.raw[s]["volume"][i] <= 0:
                skipped += 1
                continue
            q, fill, side, target = plan["quantity"], plan["fill"], plan["direction"], plan["target"]
            margin, entry_fee = q*fill, q*fill*fee
            if margin+entry_fee > cash+1e-7:
                raise AssertionError("Joint reservations spent unearned or unavailable capital")
            cash -= margin+entry_fee
            fees_paid += entry_fee
            adverse_paid += q*abs(fill-raw[s])
            turnover += q*fill
            serial += 1
            positions[s] = {"episode_id": serial, "quantity": q, "margin": margin, "entry_fee": entry_fee,
                            "entry_time": features.times[i], "entry_epoch": features.epochs[i],
                            "entry_raw_price": raw[s], "entry_price": fill, "direction": side,
                            "stop_price": plan["stop"], "funding": 0.0, "liquidation_latched": False,
                            "pending_reason": None, "worst_mark_deficit": 0.0,
                            "previous_zero_trade": False,
                            "signal_known_at": target["known_at"], "momentum_rank_score": target["score"],
                            "initial_stop_risk_with_costs": q*plan["unit_risk"]}
        old_worst = preclose_cash+math.fsum(0 if p["liquidation_latched"] else max(0, wallet(p, features.mark[s]["low" if p["direction"]>0 else "high"][i]))
                                          for s, p in preclose.items())
        old_best = preclose_cash+math.fsum(0 if p["liquidation_latched"] else max(0, wallet(p, features.mark[s]["high" if p["direction"]>0 else "low"][i]))
                                         for s, p in preclose.items())
        entered = {s: p for s, p in positions.items() if s not in preclose}
        reserve = math.fsum(p["margin"]+p["entry_fee"] for p in entered.values())
        # Current old first prints are retrospective evidence, never earlier
        # quantities. Old exits and new entries can overlap. Flag any actual
        # opening gross/stop-risk breach instead of resizing or dropping the
        # already locked new orders to conceal that uncertainty.
        if entered:
            union_gross = math.fsum(p["quantity"]*raw[s] for s, p in preclose.items())+math.fsum(p["margin"] for p in entered.values())
            union_risk = math.fsum(held_stop_risk(p, raw[s]) for s, p in preclose.items())+math.fsum(p["initial_stop_risk_with_costs"] for p in entered.values())
            maximum_entry_union_gross = max(maximum_entry_union_gross, union_gross)
            maximum_entry_union_stop_risk = max(maximum_entry_union_stop_risk, union_risk)
            retrospective_union_gross_breaches += union_gross > cap+1e-7
            retrospective_union_risk_breaches += union_risk > max(0, opening)*variant["portfolio_stop_risk"]+1e-7
        # Old exits and new fills can overlap inside an hour. Evaluate their
        # union on the original physical cash, rather than min(two separate
        # books), while counting unchanged/partially retained positions once.
        union_worst = old_worst-reserve+math.fsum(max(0, wallet(p, features.mark[s]["low" if p["direction"]>0 else "high"][i])) for s, p in entered.items())
        union_best = old_best-reserve+math.fsum(max(0, wallet(p, features.mark[s]["high" if p["direction"]>0 else "low"][i])) for s, p in entered.items())
        day_worst, day_best = min(day_worst, opening, old_worst, union_worst), max(day_best, opening, old_best, union_best)
        adverse_marks, favorable_marks = {}, {}
        for s, p in positions.items():
            adverse_marks[s] = features.mark[s]["low" if p["direction"]>0 else "high"][i]
            favorable_marks[s] = features.mark[s]["high" if p["direction"]>0 else "low"][i]
            mark_breach = wallet(p, adverse_marks[s]) <= .005*p["quantity"]*adverse_marks[s]
            trade_extreme = features.raw[s]["low" if p["direction"]>0 else "high"][i]
            stop_touch = p["direction"]*(trade_extreme-p["stop_price"]) <= 0
            funding_charge(s, i, exact=False, ambiguous=mark_breach or stop_touch or bool(p["pending_reason"]))
            sparse_held += features.mark[s]["count"][i] <= 2
            zero_trade_held += features.raw[s]["volume"][i] <= 0
            if s in preclose and p["episode_id"] == preclose[s]["episode_id"] and p["quantity"] == preclose[s]["quantity"]:
                preclose[s]["funding"] = p["funding"]
        sparse_held += sum(features.mark[s]["count"][i] <= 2 for s in preclose if s not in positions)
        # Include current negative settlements in the overlapping-book bound
        # as well, after their outcome is known; they do not resize plans.
        funded_old_worst = preclose_cash+math.fsum(0 if p["liquidation_latched"] else max(0, wallet(p, features.mark[s]["low" if p["direction"]>0 else "high"][i])) for s, p in preclose.items())
        funded_old_best = preclose_cash+math.fsum(0 if p["liquidation_latched"] else max(0, wallet(p, features.mark[s]["high" if p["direction"]>0 else "low"][i])) for s, p in preclose.items())
        union_worst = funded_old_worst-reserve+math.fsum(max(0, wallet(p, features.mark[s]["low" if p["direction"]>0 else "high"][i])) for s, p in entered.items())
        union_best = funded_old_best-reserve+math.fsum(max(0, wallet(p, features.mark[s]["high" if p["direction"]>0 else "low"][i])) for s, p in entered.items())
        day_worst, day_best = min(day_worst, union_worst), max(day_best, union_best)
        day_worst, day_best = min(day_worst, equity(adverse_marks)), max(day_best, equity(favorable_marks))
        for s in tuple(positions):
            p = positions[s]
            price = adverse_marks[s]
            value = wallet(p, price)
            p["worst_mark_deficit"] = max(p["worst_mark_deficit"], -value, 0)
            if value <= .005*p["quantity"]*price:
                p.update(liquidation_latched=True, pending_reason="closed_mark_liquidation_proxy")
            if p["liquidation_latched"]:
                p["previous_zero_trade"] = features.raw[s]["volume"][i] <= 0
                continue
            if features.raw[s]["volume"][i] > 0:
                extreme = features.raw[s]["low" if p["direction"]>0 else "high"][i]
                if p["direction"]*(extreme-p["stop_price"]) <= 0:
                    stop_raw = min(raw[s], p["stop_price"]) if p["direction"]>0 else max(raw[s], p["stop_price"])
                    close(s, stop_raw, i, "resting_stop_pessimistic_hour", timing="close")
                    blocked.add(s)
                    continue
            p["previous_zero_trade"] = features.raw[s]["volume"][i] <= 0
        closes = {s: features.mark[s]["close"][i] for s in SYMBOLS}
        end_equity = equity(closes)
        day_worst, day_best = min(day_worst, end_equity), max(day_best, end_equity)
        minimum_cash = min(minimum_cash, cash)
        if (i-start+1) % 24 == 0:
            daily.append({"time": features.times[i][:10], "equity": end_equity,
                          "start_equity": day_start, "worst_equity": day_worst, "best_equity": day_best,
                          "return": end_equity/day_start-1 if day_start > 0 else 0,
                          "cash": cash, "gross_exposure": math.fsum(p["quantity"]*closes[s] for s, p in positions.items()),
                          "long_exposure": math.fsum(p["quantity"]*closes[s] for s, p in positions.items() if p["direction"]>0),
                          "short_exposure": math.fsum(p["quantity"]*closes[s] for s, p in positions.items() if p["direction"]<0)})
    final = daily[-1]["equity"]
    terminal = {r["episode_id"] for r in slices if r["completed_episode"]}
    episodes = [math.fsum(r["pnl"] for r in slices if r["episode_id"]==episode) for episode in sorted(terminal)]
    wins, losses = math.fsum(max(0, p) for p in episodes), -math.fsum(min(0, p) for p in episodes)
    peak, dd = initial, 0.0
    for row in daily:
        peak = max(peak, row["best_equity"])
        dd = max(dd, 1-row["worst_equity"]/peak)
    unrealized = final-cash-math.fsum(p["margin"] for p in positions.values())
    reconciliation = final-initial-math.fsum(r["pnl"] for r in slices)-unrealized-math.fsum(-p["entry_fee"] for p in positions.values())
    # Remaining margin is original contributed cash; open net funding and
    # price movement are in unrealized, so no money is added by this identity.
    metrics = {"initial_equity": initial, "final_equity": final, "return_pct": (final/initial-1)*100,
               "trade_count": len(terminal), "completed_asset_episodes": len(terminal), "close_slice_count": len(slices),
               "win_rate_pct": sum(p>0 for p in episodes)/len(episodes)*100 if episodes else 0,
               "profit_factor": wins/losses if losses else None,
               "max_drawdown_pct": dd*100, "fees_paid": fees_paid, "adverse_fill_cost": adverse_paid,
               "funding_pnl": total_funding, "turnover_notional": turnover,
               "liquidation_count": liquidations+sum(p["liquidation_latched"] for p in positions.values()),
               "unfunded_isolated_deficit": max(worst_deficit, *(p["worst_mark_deficit"] for p in positions.values()), 0),
               "funding_event_count": len(funding_ledger), "minimum_available_cash": minimum_cash,
               "sparse_mark_exposure_bars": sparse_held, "skipped_zero_volume_entry_count": skipped,
               "sparse_known_mark_opening_intents": sparse_opening_intents,
               "unresolved_zero_trade_exposure_bars": zero_trade_held,
               "unknown_reopening_exit_count": reopening_unknown,
               "current_mark_open_gap_breaches": opening_mark_gap_breaches,
               "retrospective_entry_union_gross_breaches": retrospective_union_gross_breaches,
               "retrospective_entry_union_stop_risk_breaches": retrospective_union_risk_breaches,
               "maximum_entry_union_gross_notional": maximum_entry_union_gross,
               "maximum_entry_union_stop_risk": maximum_entry_union_stop_risk,
               "remaining_positions": len(positions), "account_pnl_reconciliation_error": abs(reconciliation),
               "account_insolvent": final <= 0 or any(r["start_equity"]<=0 or r["equity"]<=0 for r in daily),
               "execution_provisional": True, "historical_mark_prices_available": True,
               "survivorship_conditioned": True, "prop_financing_verified": False}
    return {"variant": variant, "metrics": metrics, "daily_curve": daily, "trades": slices,
            "funding_ledger": funding_ledger, "opening_order_plans": order_plans,
            "remaining_positions": positions, "completed_episode_unit": "asset position from entry through full closure; partial slices grouped by episode ID",
            "inference_unit": "aggregate calendar-day portfolio; constituent episodes are correlated, not independent bets"}
