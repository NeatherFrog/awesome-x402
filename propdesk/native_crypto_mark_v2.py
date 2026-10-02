"""Known-opening reservations before every old outcome: native mark96 v2.

Same frozen alpha/risk/cost grid. All new plans reserve positive free cash and
old exposure before any old exit, current funding/mark or whole-bar volume.
Computed-mark source primitives are imported from the immutable v1 producer.
"""
from __future__ import annotations
from bisect import bisect_left
from datetime import timedelta
import math
from propdesk import market
from propdesk.native_crypto_mark import MarkBars, MarkFeatures
from propdesk.native_crypto_trend import NativeFeatures, PackedBars, grid, prepare_funding, SYMBOLS


def simulate(features, observations, settlements, variant, start_date, end_date, *,
             initial=100000, cost_multiplier=1, funding_stress=False, keep_native_curve=False):
    if not math.isfinite(initial) or initial <= 0 or cost_multiplier <= 0:
        raise ValueError("Positive account capital and friction required")
    start = bisect_left(features.times, start_date+"T00:00:00Z")
    end = bisect_left(features.times, end_date+"T00:00:00Z")
    if not 0 <= start < end <= len(features.times) or (end-start) % 288:
        raise ValueError("Complete registered UTC days required")
    if features.times[start] != start_date+"T00:00:00Z":
        raise ValueError("Window starts outside native history")
    if end == len(features.times) and features.epochs[-1]+300 != market.utc_datetime(end_date+"T00:00:00Z").timestamp():
        raise ValueError("Window ends outside native history")
    fee, adverse = .0005*cost_multiplier, .00025*cost_multiplier
    maintenance, liquidation_fee = .005, .005
    cash = float(initial)
    positions, trades, ledger, daily, native_curve = {}, [], [], [], []
    total_funding = fees_paid = adverse_cost = turnover = 0.0
    liquidations = liquidation_triggers = opening_mark_gap_liquidations = 0
    zero_volume_marked_bars = reopening_unknown_fills = delayed_stop_count = 0
    source_sparse_held_bars = source_sparse_opening_intents = 0
    opening_gross_cap_breaches = 0
    max_opening_gross_cap_excess = 0.0
    unfunded_possible_funding = 0.0
    unresolved_execution_bars = skipped_zero_volume_entries = 0
    gross_ratio_sum = exposure_bars = 0.0
    minimum_cash = cash
    decision_size = 12 if variant["decision_resolution"] == "hourly" else 288
    raw = {s: features.bars[s].values for s in SYMBOLS}
    computed = {s: features.marks[s].values for s in SYMBOLS}

    def wallet(p, price):
        return p["margin"]+p["funding"]+p["direction"]*p["quantity"]*(price-p["entry_price"])

    def equity(prices):
        # A possible automatic mark liquidation forfeits the isolated wallet
        # immediately. Later mark recovery cannot restore collateral or size
        # another position while the genuine trade exit remains unresolved.
        return cash+math.fsum(0 if p["liquidation_latched"] else max(0, wallet(p, prices[s])) for s, p in positions.items())

    def close(symbol, price, i, reason, *, liquidating=False, timing="open"):
        nonlocal cash, fees_paid, adverse_cost, turnover, liquidations, reopening_unknown_fills
        p = positions[symbol]
        fill = price*(1-adverse*p["direction"])
        charge = p["quantity"]*fill*fee
        liquidation_charge = p["quantity"]*price*liquidation_fee if liquidating else 0
        value = wallet(p, fill)-charge-liquidation_charge
        recover = 0.0 if liquidating else max(0, value)
        cash += recover
        fees_paid += charge+liquidation_charge
        adverse_cost += p["quantity"]*abs(fill-price)
        turnover += p["quantity"]*fill
        liquidations += int(liquidating)
        uncertain_reopening = p.get("pending_through_zero_volume", False) or p.get("reopening_uncertain_this_bar", False)
        reopening_unknown_fills += int(uncertain_reopening)
        stamp = features.times[i]
        close_stamp = (market.utc_datetime(stamp)+timedelta(minutes=5)).isoformat().replace("+00:00", "Z") if timing == "close" else stamp
        trades.append({**p, "symbol": symbol, "exit_time": close_stamp, "exit_bar_time": stamp,
                       "exit_timing": timing, "exit_raw_price": price, "exit_price": fill,
                       "exit_fee": charge, "liquidation_fee": liquidation_charge, "recovered_margin": recover,
                       "pnl": recover-p["margin"]-p["entry_fee"], "reason": reason,
                       "boundary_liquidation": reason == "sample_boundary", "liquidation_proxy": liquidating,
                       "unfunded_isolated_deficit": max(-value, p.get("worst_mark_deficit", 0), 0),
                       "reopening_execution_time_unknown": uncertain_reopening})
        if uncertain_reopening:
            reopening_records.append(trades[-1])
        del positions[symbol]

    def funding_charge(symbol, i, open_price, *, exact, ambiguous, boundary=False):
        nonlocal total_funding
        if symbol not in positions:
            return
        p = positions[symbol]
        epoch = features.epochs[i] if i < len(features.times) else features.epochs[-1]+300
        for event in settlements[symbol].get(i, ()):
            if (event["epoch"] == epoch) != exact:
                continue
            age = event["epoch"]-p["entry_epoch"]
            if age < 60:
                continue
            original = -p["direction"]*p["quantity"]*open_price*event["rate"]
            # Even an exact-T mark point/entitlement cannot be proved at
            # millisecond resolution. Never finance orders with that credit.
            amount = 0 if (ambiguous or exact) and original > 0 else original
            if funding_stress:
                amount *= .5 if amount > 0 else 2
            p["funding"] += amount
            total_funding += amount
            slot = features.times[i] if i < len(features.times) else event["time"]
            ledger.append({"symbol": symbol, "time": event["time"], "bar_slot": slot,
                           "rate": event["rate"], "pnl": amount, "unstressed_amount": original,
                           "price_proxy": open_price, "actual_mark_unavailable": False,
                           "settlement_point_mark_unavailable": True,
                           "mark_proxy": "prior_completed_mark" if exact else "computed_mark_bar_open",
                           "exact_time_positive_credit_omitted": exact and original > 0,
                           "held_seconds": age, "intrabar_entitlement_ambiguous": ambiguous,
                           "sample_boundary_entitlement_tie": boundary})

    day_worst, day_best = initial, initial
    for i in range(start, end):
        opens = {s: raw[s]["open"][i] for s in SYMBOLS}
        known_marks = {s: computed[s]["close"][i-1] if i else computed[s]["open"][i] for s in SYMBOLS}
        opening = equity(known_marks)
        worst = best = opening
        exited = set()
        j = i//decision_size-1
        decision = i % decision_size == 0 and j >= 0
        reopening_records = []
        account = opening
        cap_equity = min(initial, account)
        daily_index = i//288-1
        plans = {}
        old_opening_snapshot = {s:p['quantity'] for s,p in positions.items()}
        if decision and i < end-1 and daily_index >= 0 and account > 0:
            plan_cash = cash
            plan_gross = math.fsum(p["quantity"]*known_marks[s] for s, p in positions.items())
            reserved_opening_cash, reserved_old_gross = plan_cash, plan_gross
            # Reserve from positive opening free cash, marked total equity
            # and ALL old exposure before any old-close/funding/mark outcome.
            # Released old margin cannot finance another asset in this decision.
            for symbol in SYMBOLS:
                if symbol in positions:
                    continue
                side = observations[symbol]["entry"][j]
                atr = features.atr[symbol][daily_index]
                if not side or atr is None or atr <= 0:
                    continue
                if i and features.marks[symbol].auxiliary_counts[i-1] <= 2:
                    source_sparse_opening_intents += 1
                fill = opens[symbol]*(1+adverse*side)
                distance = atr*variant["stop_daily_atr"]
                stop = fill-side*distance
                if stop <= 0 or side*(known_marks[symbol]-stop) <= 0:
                    continue
                gross_room = max(0, variant["max_entry_gross"]*cap_equity-plan_gross)
                risk = account*variant["risk_fraction"]
                quantity = min(risk/distance, gross_room/fill,
                               variant["max_entry_asset_gross"]*cap_equity/fill,
                               plan_cash/(fill*(1/variant["isolated_leverage"]+fee)))
                step = variant["quantity_steps"][symbol]
                quantity = math.floor(quantity/step)*step
                margin = quantity*fill/variant["isolated_leverage"]
                entry_fee = quantity*fill*fee
                if quantity <= 0 or margin+entry_fee > plan_cash+1e-8:
                    continue
                plan_cash -= margin+entry_fee
                plan_gross += quantity*fill
                plans[symbol] = {"fill": fill, "side": side, "quantity": quantity, "margin": margin,
                                 "entry_fee": entry_fee, "stop": stop, "risk": risk, "distance": distance}
        # Alpha and discretionary order intents use completed observations.
        # The current mark OPEN has unknown ordering relative to a native
        # opening execution: conservatively forfeit an OLD isolated wallet
        # if that observed point crosses maintenance, before allowing recovery.
        # This is a retrospective automatic-liquidation ambiguity bound, never
        # an available strategy feature or a fabricated executable mark fill.
        for symbol in tuple(positions):
            p = positions[symbol]
            liquid_volume = raw[symbol]["volume"][i] > 0
            p["reopening_uncertain_this_bar"] = liquid_volume and p.get("previous_bar_zero_trade", False)
            p["previous_bar_zero_trade"] = not liquid_volume
            if not liquid_volume:
                zero_volume_marked_bars += 1
            opening_mark = computed[symbol]["open"][i]
            opening_wallet = wallet(p, opening_mark)
            if opening_wallet <= maintenance*p["quantity"]*opening_mark and not p["liquidation_latched"]:
                p.update(pending_reason="opening_mark_liquidation_ambiguity", pending_known_at=None,
                         liquidation_latched=True,
                         worst_mark_deficit=max(p["worst_mark_deficit"], -opening_wallet, 0),
                         opening_mark_observation_bar=features.times[i],
                         opening_mark_observation_known_at=features.marks[symbol].known_at[i],
                         simultaneous_opening_mark_order_ordering_unverified=True)
                liquidation_triggers += 1
                opening_mark_gap_liquidations += 1
            if wallet(p, known_marks[symbol]) <= maintenance*p["quantity"]*known_marks[symbol] and not p["liquidation_latched"]:
                p.update(pending_reason="mark_liquidation_proxy", pending_known_at=features.times[i], liquidation_latched=True)
                liquidation_triggers += 1
            funding_charge(symbol, i, known_marks[symbol], exact=True, ambiguous=bool(p["pending_reason"]))
            if wallet(p, known_marks[symbol]) <= maintenance*p["quantity"]*known_marks[symbol] and not p["liquidation_latched"]:
                p.update(pending_reason="mark_liquidation_proxy", pending_known_at=features.times[i], liquidation_latched=True)
                liquidation_triggers += 1
            if not p["pending_reason"] and decision and observations[symbol]["exit_long" if p["direction"] > 0 else "exit_short"][j]:
                p.update(pending_reason="prior_close_indicator_exit", pending_known_at=features.times[i])
            if p["pending_reason"] and not liquid_volume:
                p["pending_through_zero_volume"] = True
            if p["pending_reason"] and liquid_volume:
                reason = p["pending_reason"]
                close(symbol, opens[symbol], i, reason, liquidating=p["liquidation_latched"])
                exited.add(symbol)
            elif liquid_volume and p["target_price"] is not None and p["direction"]*(opens[symbol]-p["target_price"]) >= 0:
                # Limit target receives no favorable gap price improvement.
                close(symbol, p["target_price"], i, "gap_target")
                exited.add(symbol)
        worst, best = min(worst, equity(known_marks)), max(best, equity(known_marks))
        actually_opened_gross = 0.0
        if plans:
            for symbol, plan in plans.items():
                if raw[symbol]["volume"][i] <= 0:
                    skipped_zero_volume_entries += 1
                    continue
                fill, side, quantity, margin, entry_fee, stop, risk, distance = (plan[k] for k in
                    ("fill", "side", "quantity", "margin", "entry_fee", "stop", "risk", "distance"))
                cash -= margin+entry_fee
                fees_paid += entry_fee
                adverse_cost += quantity*abs(fill-opens[symbol])
                turnover += quantity*fill
                actually_opened_gross += quantity*fill
                signal_bar = features.aggregate[symbol, variant["decision_resolution"]]["times"][j]
                positions[symbol] = {"entry_time": features.times[i], "entry_epoch": features.epochs[i],
                                     "signal_time": signal_bar, "signal_known_at": features.times[i],
                                     "atr_known_at": features.times[(daily_index+1)*288], "direction": side,
                                     "entry_price": fill, "entry_raw_price": opens[symbol], "quantity": quantity,
                                     "margin": margin, "entry_fee": entry_fee, "funding": 0.0,
                                     "stop_price": stop, "target_price": fill+side*distance*variant["target_r"] if variant.get("target_r") else None,
                                     "risk_budget": risk, "risk_at_stop_before_costs": quantity*distance,
                                     "opening_free_cash_before_old_outcomes": reserved_opening_cash,
                                     "opening_reserved_old_gross": reserved_old_gross,
                                     "opening_plan_excludes_old_exit_recovery": True,
                                     "entry_equity_mark_known_at": features.times[i], "pending_reason": None,
                                     "pending_known_at": None, "pending_through_zero_volume": False,
                                     "previous_bar_zero_trade": False, "reopening_uncertain_this_bar": False,
                                     "liquidation_latched": False, "worst_mark_deficit": 0.0}
        if actually_opened_gross:
            # Retrospective risk evidence ONLY. An old first-print price may
            # occur after another asset's order. Retain the OLD snapshot even
            # if it exited; never use this unknown point to resize new plans.
            observed_opening_gross = math.fsum(q*opens[s] for s,q in old_opening_snapshot.items())+actually_opened_gross
            cap_excess = max(0, observed_opening_gross-variant['max_entry_gross']*cap_equity)
            opening_gross_cap_breaches += cap_excess>1e-6
            max_opening_gross_cap_excess = max(max_opening_gross_cap_excess,cap_excess)
        # Mark OHLC becomes known only at the end of this interval. It never
        # sizes or finances an earlier opening order.
        adverse_prices = {s: computed[s]["low" if positions[s]["direction"] > 0 else "high"][i] if s in positions else known_marks[s] for s in SYMBOLS}
        favorable_prices = {s: computed[s]["high" if positions[s]["direction"] > 0 else "low"][i] if s in positions else known_marks[s] for s in SYMBOLS}
        worst, best = min(worst, equity(adverse_prices)), max(best, equity(favorable_prices))
        for symbol in tuple(positions):
            p = positions[symbol]
            # Preserve sparse source observations and their modeled economics.
            # They cannot establish the full intrabar mark risk envelope; do
            # not skip them retrospectively or fabricate missing mark paths.
            source_sparse_held_bars += features.marks[symbol].auxiliary_counts[i] <= 2
            adverse_price, favorable_price = adverse_prices[symbol], favorable_prices[symbol]
            pre_liq = wallet(p, adverse_price) <= maintenance*p["quantity"]*adverse_price
            stop_touch = p["direction"]*(adverse_price-p["stop_price"]) <= 0
            trade_favorable = raw[symbol]["high" if p["direction"] > 0 else "low"][i]
            target_touch = raw[symbol]["volume"][i] > 0 and p["target_price"] is not None and p["direction"]*(trade_favorable-p["target_price"]) >= 0
            funding_charge(symbol, i, computed[symbol]["open"][i], exact=False, ambiguous=pre_liq or stop_touch or target_touch or bool(p["pending_reason"]))
        # A reopening bar's first trade can occur after its opening label.
        # Retain possible late settlement debits on that just-closed old
        # position, omit credits, and flag unknown execution; never finance
        # the already locked new opening orders with a later observation.
        for record in reopening_records:
            symbol = record["symbol"]
            for event in settlements[symbol].get(i, ()):
                if event["epoch"] == features.epochs[i] or event["epoch"]-record["entry_epoch"] < 60:
                    continue
                amount = min(0, -record["direction"]*record["quantity"]*computed[symbol]["open"][i]*event["rate"])
                if funding_stress:
                    amount *= 2
                paid = min(cash, -amount)
                cash -= paid
                shortage = -amount-paid
                unfunded_possible_funding += shortage
                record["funding"] -= paid
                record["pnl"] -= paid
                total_funding -= paid
                ledger.append({"symbol": symbol, "time": event["time"], "bar_slot": features.times[i],
                               "rate": event["rate"], "pnl": -paid, "possible_debit_due": amount,
                               "unfunded_possible_debit": shortage, "reopening_execution_time_unknown": True,
                               "mark_proxy": "computed_mark_bar_open", "settlement_point_mark_unavailable": True})
        worst, best = min(worst, equity(adverse_prices)), max(best, equity(favorable_prices))
        for symbol in tuple(positions):
            p = positions[symbol]
            adverse_price, favorable_price = adverse_prices[symbol], favorable_prices[symbol]
            known_at = features.marks[symbol].known_at[i]
            p["worst_mark_deficit"] = max(p["worst_mark_deficit"], -wallet(p, adverse_price), 0)
            if wallet(p, adverse_price) <= maintenance*p["quantity"]*adverse_price and not p["liquidation_latched"]:
                p.update(pending_reason="mark_liquidation_proxy", pending_known_at=known_at, liquidation_latched=True)
                liquidation_triggers += 1
            elif p["direction"]*(adverse_price-p["stop_price"]) <= 0 and not p["pending_reason"]:
                p.update(pending_reason="completed_mark_stop", pending_known_at=known_at)
                delayed_stop_count += 1
            if p["pending_reason"] and raw[symbol]["volume"][i] <= 0:
                p["pending_through_zero_volume"] = True
            trade_favorable = raw[symbol]["high" if p["direction"] > 0 else "low"][i]
            if not p["pending_reason"] and raw[symbol]["volume"][i] > 0 and p["target_price"] is not None and p["direction"]*(trade_favorable-p["target_price"]) >= 0:
                close(symbol, p["target_price"], i, "native_target", timing="intrabar_unobserved")
        closes = {s: raw[s]["close"][i] for s in SYMBOLS}
        mark_closes = {s: computed[s]["close"][i] for s in SYMBOLS}
        if i == end-1:
            for symbol in tuple(positions):
                funding_charge(symbol, end, mark_closes[symbol], exact=True, ambiguous=True, boundary=True)
                if raw[symbol]["volume"][i] > 0 and not positions[symbol]["pending_reason"]:
                    close(symbol, closes[symbol], i, "sample_boundary", timing="close")
        mark = equity(mark_closes)
        minimum_cash = min(minimum_cash, cash)
        gross = math.fsum(p["quantity"]*mark_closes[s] for s, p in positions.items())
        gross_ratio_sum += gross/max(mark, 1e-12)
        exposure_bars += bool(positions)
        worst, best = min(worst, mark), max(best, mark)
        day_worst, day_best = min(day_worst, worst), max(day_best, best)
        if keep_native_curve:
            native_curve.append({"time": features.times[i], "equity": mark, "opening_equity": opening,
                                 "worst_equity": worst, "best_equity": best, "available_cash": cash, "notional": gross})
        if i % 288 == 287:
            daily.append({"time": features.times[i], "equity": mark, "worst_equity": day_worst,
                          "best_equity": day_best, "available_cash": cash, "notional": gross})
            day_worst = day_best = mark
    wins, losses = (math.fsum(t["pnl"] for t in trades if t["pnl"] > 0), -math.fsum(t["pnl"] for t in trades if t["pnl"] < 0))
    peak, close_peak, close_dd, adverse_dd = initial, initial, 0.0, 0.0
    for row in daily:
        peak = max(peak, row["best_equity"])
        adverse_dd = max(adverse_dd, 1-row["worst_equity"]/peak)
        peak = max(peak, row["equity"])
        close_peak = max(close_peak, row["equity"])
        close_dd = max(close_dd, 1-row["equity"]/close_peak)
    final_equity = daily[-1]["equity"]
    metrics = {"initial_equity": initial, "final_equity": final_equity, "final_available_cash": cash,
               "return_pct": (final_equity/initial-1)*100,
               "trade_count": len(trades), "win_rate_pct": 100*sum(t["pnl"] > 0 for t in trades)/len(trades) if trades else 0,
               "profit_factor": wins/losses if losses else None, "max_drawdown_pct": adverse_dd*100,
               "max_close_drawdown_pct": close_dd*100, "fees_paid": fees_paid, "adverse_fill_cost": adverse_cost,
               "funding_pnl": total_funding, "turnover_notional": turnover,
               "liquidation_count": max(liquidations, liquidation_triggers),
               "opening_mark_gap_liquidation_ambiguity_count": opening_mark_gap_liquidations,
               "unfunded_isolated_deficit": math.fsum(t["unfunded_isolated_deficit"] for t in trades)+math.fsum(p["worst_mark_deficit"] for p in positions.values())+unfunded_possible_funding,
               "funding_event_count": len(ledger), "average_gross_equity_ratio": gross_ratio_sum/(end-start),
               "unresolved_zero_volume_exposure_bars": unresolved_execution_bars,
               "zero_volume_held_bars_with_authentic_marks": zero_volume_marked_bars,
               "reopening_execution_time_unknown_count": reopening_unknown_fills,
               "terminal_open_positions": len(positions), "terminal_pending_orders": sum(bool(p["pending_reason"]) for p in positions.values()),
               "closed_mark_stop_queue_count": delayed_stop_count,
               "source_sparse_mark_held_bar_count": source_sparse_held_bars,
               "source_sparse_mark_opening_intent_count": source_sparse_opening_intents,
               "opening_total_gross_cap_breach_count": opening_gross_cap_breaches,
               "max_opening_total_gross_cap_excess": max_opening_gross_cap_excess,
               "skipped_zero_volume_entry_count": skipped_zero_volume_entries,
               "time_in_position_fraction": exposure_bars/(end-start), "minimum_available_cash": minimum_cash,
               "account_insolvent": any(row["equity"] <= 0 for row in daily),
               "execution_provisional": True, "historical_mark_prices_available": True,
               "mark_extrema_observation_status": "Observed computed marks; auxiliary count does not prove continuous sampling",
               "settlement_point_marks_available": False}
    returns, previous = [], initial
    for row in daily:
        # Preserve bankrupt flat dates without dividing byzero. The driver
        # explicitly rejects insolvency; these values never enter inference.
        value = row["equity"]/previous-1 if previous > 0 else 0.0
        returns.append({"date": row["time"][:10], "return": value})
        previous = row["equity"]
    return {"metrics": metrics, "equity_curve": daily, "daily_returns": returns,
            "native_equity_curve": native_curve, "trades": trades, "funding_ledger": ledger,
            "terminal_positions": positions,
            "start": features.times[start], "end": features.times[end-1]}
