"""A causal BTC/ETH New-York-clock adaptation of original noise-area ideas.

This is not an SPY paper replication. Protective completed-mark stop queues,
monotonic checkpoint ratchets, physical collateral and crypto frictions are
explicit research changes. No order API or live qualification is provided.
"""
from __future__ import annotations

from array import array
from bisect import bisect_left
from collections import deque
from datetime import datetime, timedelta, timezone
import itertools
import math
from pathlib import Path
from zoneinfo import ZoneInfo

from propdesk import market, research_lab as lab
from propdesk.native_crypto_trend import PackedBars, prepare_funding, SYMBOLS
from propdesk.native_crypto_mark import MarkBars

with (Path(__file__).resolve().parent / 'tzdata/America/New_York').open('rb') as stream:
    NEW_YORK = ZoneInfo.from_file(stream, key='America/New_York')

PARENT_MARK_ENGINE_SHA256 = '0d72deb7ae3e8bd75f22472f8533981e502330d52763a76aa20a651aa9d770b2'


def grid():
    result = []
    for scale, interval, exit_mode, risk in itertools.product(
            (.75, 1, 1.25), (15, 30), ('current_band', 'current_band_vwap'), (.005, .01)):
        row = {'family': 'weekday_ny_noise_area', 'lookback_sessions': 14,
               'band_multiplier': scale, 'checkpoint_minutes': interval, 'exit_mode': exit_mode,
               'aggregate_risk_fraction': risk, 'decision_resolution': 'native5m',
               'isolated_leverage': 2, 'max_entry_gross': 2, 'max_entry_asset_gross': 1,
               'quantity_steps': {'BTCUSDT': .001, 'ETHUSDT': .001},
               'first_checkpoint': '10:00', 'last_checkpoint_before': '16:00',
               'session_open': '09:30', 'session_flat': '16:00', 'stop_ratchet': True}
        row['id'] = 'native_noise-' + lab.digest(row)[:12]
        result.append(row)
    return result


class NoiseFeatures:
    def __init__(self, datasets, marks):
        if set(datasets) != set(SYMBOLS) or set(marks) != set(SYMBOLS):
            raise ValueError('Exact native BTC/ETH trade and independently sourced mark universe required')
        self.bars = {s: PackedBars(rows) for s, rows in datasets.items()}
        self.marks = {s: rows if isinstance(rows, MarkBars) else MarkBars(rows) for s, rows in marks.items()}
        self.times, self.epochs = self.bars[SYMBOLS[0]].times, self.bars[SYMBOLS[0]].epochs
        if any(self.bars[s].times != self.times or self.marks[s].times != self.times for s in SYMBOLS):
            raise ValueError('Exact synchronized native trade/mark clocks required; no interpolation')
        # Prefixes are allowed so tests can prove that an earlier decision does
        # not require the current day's as-yet-unobserved16:00/session data.
        local_open = [datetime.fromtimestamp(epoch, timezone.utc).astimezone(NEW_YORK)
                      for epoch in self.epochs]
        local_known = [(value + timedelta(minutes=5)) for value in local_open]
        self.active = array('b', [int(value.weekday() < 5 and 570 <= value.hour*60+value.minute < 960)
                                  for value in local_open])
        self.checkpoint_clock = array('i', [value.hour*60+value.minute if value.weekday() < 5 else -1
                                           for value in local_known])
        self.local_session_dates = [value.date().isoformat() for value in local_known]
        self.cache, self.base = {}, {}
        for symbol in SYMBOLS:
            raw, rows = self.bars[symbol].values, datasets[symbol]
            quotes = array('d')
            for index, row in enumerate(rows):
                if market.utc_datetime(row['known_at']).timestamp() != self.epochs[index] + 300:
                    raise ValueError('Original quote/base volume becomes available only at completed native boundary')
                quote = row['quote_volume']
                if isinstance(quote, bool) or not isinstance(quote, (int, float)) or not math.isfinite(quote) or quote < 0:
                    raise ValueError('Original USDT quote volume must be finite and nonnegative')
                if (raw['volume'][index] == 0) != (quote == 0):
                    raise ValueError('Traded base/quote zero domains differ')
                if raw['volume'][index] > 0:
                    average = quote/raw['volume'][index]
                    tolerance = max(1e-8, raw['high'][index]*1e-7)
                    if not raw['low'][index]-tolerance <= average <= raw['high'][index]+tolerance:
                        raise ValueError('Original quote/base VWAP leaves its trade OHLC envelope')
                quotes.append(quote)
            fields = {key: array('d', [math.nan])*len(self.times)
                      for key in ('sigma', 'upper_anchor', 'lower_anchor', 'vwap')}
            history, current, prior_close = deque(maxlen=14), None, None
            for j, (opened, known) in enumerate(zip(local_open, local_known)):
                minute = opened.hour*60+opened.minute
                if opened.weekday() >= 5:
                    continue
                if minute == 570:
                    current = {'date': opened.date().isoformat(), 'opening': raw['open'][j],
                               'opening_traded': raw['volume'][j] > 0, 'slots': {}, 'quote': 0., 'base': 0.}
                if current is None or current['date'] != opened.date().isoformat() or not 570 <= minute < 960:
                    continue
                slot = known.hour*60+known.minute
                current['quote'] += quotes[j]
                current['base'] += raw['volume'][j]
                if current['base'] > 0:
                    fields['vwap'][j] = current['quote']/current['base']
                if current['opening_traded'] and prior_close is not None and len(history) == 14:
                    previous = [day['slots'].get(slot) for day in history]
                    if all(value is not None for value in previous):
                        fields['sigma'][j] = math.fsum(previous)/14
                        fields['upper_anchor'][j] = max(current['opening'], prior_close)
                        fields['lower_anchor'][j] = min(current['opening'], prior_close)
                # Only actually traded completed slot prices form a previous
                # session's movement. Today's later close never changes earlier
                # band values; incomplete earlier references make a slot unknown.
                current['slots'][slot] = (abs(raw['close'][j]/current['opening']-1)
                                          if current['opening_traded'] and raw['volume'][j] > 0 else None)
                if slot == 960:
                    history.append({'date': current['date'], 'slots': current['slots']})
                    prior_close = raw['close'][j] if raw['volume'][j] > 0 else None
                    current = None
            self.base[symbol] = fields

    def observations(self, variant):
        if variant not in grid():
            raise ValueError('Unregistered noise-area configuration')
        key = lab.digest({k: v for k, v in variant.items() if k not in ('id', 'aggregate_risk_fraction')})
        if key in self.cache:
            return self.cache[key]
        result = {}
        for symbol in SYMBOLS:
            raw, base = self.bars[symbol].values, self.base[symbol]
            n = len(self.times)
            entry, exit_long, exit_short, checkpoint = (array('b', [0])*n for _ in range(4))
            stop_long, stop_short, upper, lower = (array('d', [math.nan])*n for _ in range(4))
            for j, clock in enumerate(self.checkpoint_clock):
                if not 600 <= clock < 960 or (clock-600) % variant['checkpoint_minutes']:
                    continue
                checkpoint[j] = 1
                sigma = base['sigma'][j]
                vwap = base['vwap'][j]
                if not math.isfinite(sigma) or not math.isfinite(vwap) or raw['volume'][j] <= 0:
                    continue
                upper[j] = base['upper_anchor'][j]*(1+variant['band_multiplier']*sigma)
                lower[j] = base['lower_anchor'][j]*(1-variant['band_multiplier']*sigma)
                if not 0 < lower[j] <= upper[j]:
                    continue
                stop_long[j], stop_short[j] = upper[j], lower[j]
                if variant['exit_mode'] == 'current_band_vwap':
                    stop_long[j], stop_short[j] = max(upper[j], vwap), min(lower[j], vwap)
                price = raw['close'][j]
                entry[j] = 1 if price > upper[j] else -1 if price < lower[j] else 0
                exit_long[j], exit_short[j] = price < stop_long[j], price > stop_short[j]
            result[symbol] = {'entry': entry, 'exit_long': exit_long, 'exit_short': exit_short,
                              'checkpoint': checkpoint, 'stop_long': stop_long, 'stop_short': stop_short,
                              'upper': upper, 'lower': lower}
        self.cache[key] = result
        return result

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
    unfunded_possible_funding = 0.0
    unresolved_execution_bars = skipped_zero_volume_entries = 0
    gross_ratio_sum = exposure_bars = 0.0
    minimum_cash = cash
    decision_size = 1
    unknown_checkpoint_updates = 0
    stop_updates = []
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
        # Lock NEW intents before any OLD exit can release cash based on the
        # unknown whole-bar trade-volume outcome. Exact-T old-held debits use
        # completed marks, and positive credits are omitted by funding_charge.
        for symbol in tuple(positions):
            p = positions[symbol]
            if wallet(p, known_marks[symbol]) <= maintenance*p["quantity"]*known_marks[symbol] and not p["liquidation_latched"]:
                p.update(pending_reason="mark_liquidation_proxy", pending_known_at=features.times[i], liquidation_latched=True)
                liquidation_triggers += 1
            funding_charge(symbol, i, known_marks[symbol], exact=True, ambiguous=bool(p["pending_reason"]))
            if wallet(p, known_marks[symbol]) <= maintenance*p["quantity"]*known_marks[symbol] and not p["liquidation_latched"]:
                p.update(pending_reason="mark_liquidation_proxy", pending_known_at=features.times[i], liquidation_latched=True)
                liquidation_triggers += 1
        account = equity(known_marks)
        worst, best = min(worst, account), max(best, account)
        cap_equity = min(initial, account)
        plans = {}
        if decision and i < end-1 and features.active[i] and account > 0:
            plans = {}
            plan_cash = cash
            plan_gross = math.fsum(p["quantity"]*opens[s] for s, p in positions.items())
            plan_risk = math.fsum(p["risk_budget"] for p in positions.values())
            # Reserve both known-opening intents before either future native
            # whole-bar volume outcome is checked. An unfilled BTC intent
            # cannot finance a larger ETH opening in the same interval.
            for symbol in SYMBOLS:
                if symbol in positions or symbol in exited:
                    continue
                side = observations[symbol]["entry"][j]
                stop = observations[symbol]["stop_long" if side > 0 else "stop_short"][j]
                if not side or not math.isfinite(stop) or stop <= 0:
                    continue
                if i and features.marks[symbol].auxiliary_counts[i-1] <= 2:
                    source_sparse_opening_intents += 1
                fill = opens[symbol]*(1+adverse*side)
                distance = side*(fill-stop)
                if (distance <= 0 or side*(opens[symbol]-stop) <= 0 or
                        side*(known_marks[symbol]-stop) <= 0):
                    continue
                stopped_fill = stop*(1-adverse*side)
                loss_per_unit = side*(fill-stopped_fill)+fee*(fill+stopped_fill)
                gross_room = max(0, variant["max_entry_gross"]*cap_equity-plan_gross)
                risk = min(account*variant["aggregate_risk_fraction"]/2,
                           max(0, account*variant["aggregate_risk_fraction"]-plan_risk))
                quantity = min(risk/loss_per_unit, gross_room/fill,
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
                plan_risk += risk
                plans[symbol] = {"fill": fill, "side": side, "quantity": quantity, "margin": margin,
                                 "entry_fee": entry_fee, "stop": stop, "risk": risk, "distance": distance,
                                 "risk_including_costs": quantity*loss_per_unit}
        # Alpha and discretionary order intents use completed observations.
        # An OLD wallet may have been liquidated at the current mark OPEN before
        # a simultaneous native exit. Unknown ordering conservatively forfeits
        # that wallet; current marks never become an alpha or executable fill.
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
            if not p["pending_reason"] and not features.active[i]:
                p.update(pending_reason="registered_session_flat", pending_known_at=features.times[i])
            if not p["pending_reason"] and liquid_volume and p["direction"]*(opens[symbol]-p["stop_price"]) <= 0:
                p.update(pending_reason="known_opening_stop_gap", pending_known_at=features.times[i])
            if not p["pending_reason"] and decision and observations[symbol]["checkpoint"][j]:
                checkpoint = observations[symbol]
                threshold = checkpoint["stop_long" if p["direction"] > 0 else "stop_short"][j]
                if not math.isfinite(threshold):
                    unknown_checkpoint_updates += 1
                else:
                    old_stop = p["stop_price"]
                    p["stop_price"] = max(old_stop, threshold) if p["direction"] > 0 else min(old_stop, threshold)
                    stop_updates.append({"symbol": symbol, "signal_time": features.times[j],
                                         "signal_known_at": features.times[i], "active_at": features.times[i],
                                         "old_stop": old_stop, "new_stop": p["stop_price"],
                                         "checkpoint_threshold": threshold})
                    if checkpoint["exit_long" if p["direction"] > 0 else "exit_short"][j]:
                        p.update(pending_reason="closed_checkpoint_exit", pending_known_at=features.times[i])
                    elif liquid_volume and p["direction"]*(opens[symbol]-p["stop_price"]) <= 0:
                        p.update(pending_reason="new_checkpoint_stop_opening_gap", pending_known_at=features.times[i])
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
            signal_bar = features.times[j]
            positions[symbol] = {"entry_time": features.times[i], "entry_epoch": features.epochs[i],
                                 "signal_time": signal_bar, "signal_known_at": features.times[i],
                                 "noise_reference_known_at": features.times[i], "direction": side,
                                 "entry_price": fill, "entry_raw_price": opens[symbol], "quantity": quantity,
                                 "margin": margin, "entry_fee": entry_fee, "funding": 0.0,
                                 "stop_price": stop, "initial_stop_price": stop, "target_price": None,
                                 "risk_budget": risk, "risk_at_stop_before_costs": quantity*distance,
                                 "risk_at_stop_including_costs": plan["risk_including_costs"],
                                 "noise_upper": observations[symbol]["upper"][j],
                                 "noise_lower": observations[symbol]["lower"][j],
                                 "noise_sigma": features.base[symbol]["sigma"][j],
                                 "session_vwap": features.base[symbol]["vwap"][j],
                                 "session_day": features.local_session_dates[j],
                                 "exit_mode": variant["exit_mode"],
                                 "entry_equity_mark_known_at": features.times[i], "pending_reason": None,
                                 "pending_known_at": None, "pending_through_zero_volume": False,
                                 "previous_bar_zero_trade": False, "reopening_uncertain_this_bar": False,
                                 "liquidation_latched": False, "worst_mark_deficit": 0.0}
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
               "skipped_zero_volume_entry_count": skipped_zero_volume_entries,
               "time_in_position_fraction": exposure_bars/(end-start), "minimum_available_cash": minimum_cash,
               "account_insolvent": any(row["equity"] <= 0 for row in daily),
               "execution_provisional": True, "historical_mark_prices_available": True,
               "mark_extrema_observation_status": "Observed computed marks; auxiliary count does not prove continuous sampling",
               "settlement_point_marks_available": False,
               "unknown_checkpoint_stop_update_count": unknown_checkpoint_updates,
               "checkpoint_stop_update_count": len(stop_updates)}
    returns, previous = [], initial
    for row in daily:
        # Preserve bankrupt flat dates without dividing byzero. The driver
        # explicitly rejects insolvency; these values never enter inference.
        value = row["equity"]/previous-1 if previous > 0 else 0.0
        returns.append({"date": row["time"][:10], "return": value})
        previous = row["equity"]
    return {"metrics": metrics, "equity_curve": daily, "daily_returns": returns,
            "native_equity_curve": native_curve, "trades": trades, "funding_ledger": ledger,
            "terminal_positions": positions, "stop_update_ledger": stop_updates,
            "live_orders": False, "prop_qualified": False, "paper_reproduction": False,
            "start": features.times[start], "end": features.times[end-1]}
