"""Preregistered aggressor-volume hypotheses with physically funded execution.

Taker volume is a traded-notional fact, not order-book or liquidation evidence.
Signals use completed5m source fields; reviewed parent execution math is copied
with explicit decision, volatility/metadata, fixed-hold and entry-planning hooks.
"""
from __future__ import annotations

from array import array
from bisect import bisect_left
from datetime import datetime, timedelta, timezone
import itertools
import math

from propdesk import market, research_lab as lab, native_crypto_trend as native

SYMBOLS = native.SYMBOLS
PARENT_ENGINE_SHA256 = "75f43df5e547c3853369e5734d359d07df6409a19bb63939e1da1567a4956d28"
PackedBars = native.PackedBars
prepare_funding = native.prepare_funding


def grid():
    rows = []
    for family, window, threshold, hold, stop, risk in itertools.product(
            ("flow_continuation", "flow_absorption_reversion"), (1, 3), (.15, .30), (1, 3), (1, 2), (.005, .01)):
        row = {"family": family, "flow_window": window, "signed_quote_threshold": threshold,
               "hold_hours": hold, "stop_atr": stop, "risk_fraction": risk,
               "decision_resolution": "native5m", "quote_activity_multiple": 1.25,
               "trade_count_activity_multiple": 1.0, "activity_history": 72,
               "hourly_atr_period": 20, "native_impact_atr_period": 20,
               "continuation_body_atr_min": .5, "absorption_body_atr_max": .25,
               "isolated_leverage": 2, "max_entry_gross": 2, "max_entry_asset_gross": 1,
               "quantity_steps": {"BTCUSDT": .001, "ETHUSDT": .001}}
        row['id'] = 'crypto_flow-'+lab.digest(row)[:12]
        rows.append(row)
    return rows


class FlowFeatures:
    def __init__(self, datasets):
        if set(datasets) != set(SYMBOLS):
            raise ValueError("Exact synchronized BTC/ETH native flow universe required")
        self.bars = {s: PackedBars(rows) for s,rows in datasets.items()}
        self.times = self.bars[SYMBOLS[0]].times
        self.epochs = self.bars[SYMBOLS[0]].epochs
        if any(self.bars[s].times != self.times for s in SYMBOLS) or self.times[0][11:16] != '00:00' or len(self.times)%288:
            raise ValueError("Full synchronized UTC calendar days required")
        self.flow, self.impact_atr, self.atr, self.atr_known_at, self.cache = {}, {}, {}, {}, {}
        for s in SYMBOLS:
            rows,raw=datasets[s],self.bars[s].values
            cols={k:array('d') for k in ('quote_volume','trade_count','taker_buy_base_volume','taker_buy_quote_volume')}
            for i,row in enumerate(rows):
                if market.utc_datetime(row['known_at']).timestamp() != self.epochs[i]+300:
                    raise ValueError("Flow fields become available only at native interval close")
                for k in cols:
                    value=row[k]
                    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value<0:
                        raise ValueError("Flow source quantities/counts must be finite and nonnegative")
                    cols[k].append(value)
                if row['trade_count'] != int(row['trade_count']) or row['taker_buy_base_volume']>row['volume'] or row['taker_buy_quote_volume']>row['quote_volume']:
                    raise ValueError("Flow count/subset domains invalid")
                if row['volume']==0 and any(row[k] for k in cols):
                    raise ValueError("Absent-trade source cannot have flow evidence")
                if row['volume']>0 and (row['quote_volume']<=0 or row['trade_count']<=0):
                    raise ValueError("Tradedsource requires positive quote/count evidence")
            self.flow[s]=cols
            self.impact_atr[s]=native._atr(raw['high'],raw['low'],raw['close'],20)
            highs=[max(raw['high'][j:j+12]) for j in range(0,len(self.times),12)]
            lows=[min(raw['low'][j:j+12]) for j in range(0,len(self.times),12)]
            closes=[raw['close'][j+11] for j in range(0,len(self.times),12)]
            hour_atr=native._atr(highs,lows,closes,20)
            self.atr[s],self.atr_known_at[s]=[],[]
            for j in range(len(self.times)):
                h=(j+1)//12-1
                self.atr[s].append(hour_atr[h] if h>=0 else None)
                known=datetime.fromtimestamp(self.epochs[0]+(h+1)*3600,timezone.utc).isoformat().replace('+00:00','Z')
                self.atr_known_at[s].append(known)

    def observations(self,variant):
        if variant not in grid():
            raise ValueError("Unregistered flow configuration")
        key=lab.digest({k:v for k,v in variant.items() if k not in ('id','risk_fraction','stop_atr','hold_hours')})
        if key in self.cache:
            return self.cache[key]
        out={}
        w,history=variant['flow_window'],variant['activity_history']
        for s in SYMBOLS:
            n=len(self.times)
            entry,exit_long,exit_short=(array('b',[0])*n for _ in range(3))
            flow,raw=self.flow[s],self.bars[s].values
            prefix={k:[0.0] for k in ('quote_volume','trade_count','taker_buy_quote_volume')}
            for k in prefix:
                for value in flow[k]:
                    prefix[k].append(prefix[k][-1]+value)
            for j in range(history+w-1,n):
                first=j-w+1
                if any(raw['volume'][k]<=0 for k in range(first,j+1)):
                    continue
                quote=prefix['quote_volume'][j+1]-prefix['quote_volume'][first]
                count=prefix['trade_count'][j+1]-prefix['trade_count'][first]
                past_quote=(prefix['quote_volume'][first]-prefix['quote_volume'][first-history])/history*w
                past_count=(prefix['trade_count'][first]-prefix['trade_count'][first-history])/history*w
                if quote<=0 or past_quote<=0 or past_count<=0 or quote<variant['quote_activity_multiple']*past_quote or count<variant['trade_count_activity_multiple']*past_count:
                    continue
                buy=prefix['taker_buy_quote_volume'][j+1]-prefix['taker_buy_quote_volume'][first]
                signed=2*buy/quote-1
                if abs(signed)<variant['signed_quote_threshold']:
                    continue
                atr=self.impact_atr[s][first-1]
                if atr is None or atr<=0:
                    continue
                body=raw['close'][j]-raw['open'][first]
                scale=atr*math.sqrt(w)
                direction=1 if signed>0 else -1
                if variant['family']=='flow_continuation':
                    if direction*body>=variant['continuation_body_atr_min']*scale:
                        entry[j]=direction
                elif abs(body)<=variant['absorption_body_atr_max']*scale:
                    entry[j]=-direction
            out[s]={'entry':entry,'exit_long':exit_long,'exit_short':exit_short}
        self.cache[key]=out
        return out


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
    liquidations = 0
    unresolved_execution_bars = skipped_zero_volume_entries = 0
    gross_ratio_sum = exposure_bars = 0.0
    minimum_cash = cash
    decision_size = 1
    raw = {s: features.bars[s].values for s in SYMBOLS}

    def wallet(p, price):
        return p["margin"]+p["funding"]+p["direction"]*p["quantity"]*(price-p["entry_price"])

    def equity(prices):
        return cash+math.fsum(max(0, wallet(p, prices[s])) for s, p in positions.items())

    def close(symbol, price, i, reason, *, liquidating=False, timing="open"):
        nonlocal cash, fees_paid, adverse_cost, turnover, liquidations
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
        stamp = features.times[i]
        close_stamp = (market.utc_datetime(stamp)+timedelta(minutes=5)).isoformat().replace("+00:00", "Z") if timing == "close" else stamp
        trades.append({**p, "symbol": symbol, "exit_time": close_stamp, "exit_bar_time": stamp,
                       "exit_timing": timing, "exit_raw_price": price, "exit_price": fill,
                       "exit_fee": charge, "liquidation_fee": liquidation_charge, "recovered_margin": recover,
                       "pnl": recover-p["margin"]-p["entry_fee"], "reason": reason,
                       "boundary_liquidation": reason == "sample_boundary", "liquidation_proxy": liquidating,
                       "unfunded_isolated_deficit": max(-value, 0)})
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
            amount = 0 if ambiguous and original > 0 else original
            if funding_stress:
                amount *= .5 if amount > 0 else 2
            p["funding"] += amount
            total_funding += amount
            slot = features.times[i] if i < len(features.times) else event["time"]
            ledger.append({"symbol": symbol, "time": event["time"], "bar_slot": slot,
                           "rate": event["rate"], "pnl": amount, "unstressed_amount": original,
                           "price_proxy": open_price, "actual_mark_unavailable": True,
                           "held_seconds": age, "intrabar_entitlement_ambiguous": ambiguous,
                           "sample_boundary_entitlement_tie": boundary})

    day_worst, day_best = initial, initial
    for i in range(start, end):
        opens = {s: raw[s]["open"][i] for s in SYMBOLS}
        opening = equity(opens)
        worst = best = opening
        exited = set()
        j = i//decision_size-1
        decision = i % decision_size == 0 and j >= 0
        # A gap liquidation exists before any exact-time receipt could rescue it.
        for symbol in tuple(positions):
            p = positions[symbol]
            liquid_volume = raw[symbol]["volume"][i] > 0
            if not liquid_volume:
                unresolved_execution_bars += 1
            if wallet(p, opens[symbol]) <= maintenance*p["quantity"]*opens[symbol]:
                close(symbol, opens[symbol], i, "opening_liquidation_proxy", liquidating=True)
                exited.add(symbol)
                continue
            funding_charge(symbol, i, opens[symbol], exact=True, ambiguous=False)
            p = positions[symbol]
            if wallet(p, opens[symbol]) <= maintenance*p["quantity"]*opens[symbol]:
                close(symbol, opens[symbol], i, "opening_liquidation_proxy", liquidating=True)
                exited.add(symbol)
            elif liquid_volume and p["direction"]*(opens[symbol]-p["stop_price"]) <= 0:
                close(symbol, opens[symbol], i, "gap_stop")
                exited.add(symbol)
            elif liquid_volume and p["target_price"] is not None and p["direction"]*(opens[symbol]-p["target_price"]) >= 0:
                # Limit target receives no favorable gap price improvement.
                close(symbol, p["target_price"], i, "gap_target")
                exited.add(symbol)
            elif liquid_volume and features.epochs[i]-p["entry_epoch"] >= variant["hold_hours"]*3600:
                close(symbol, opens[symbol], i, "registered_time_exit")
                exited.add(symbol)
            elif liquid_volume and decision and observations[symbol]["exit_long" if p["direction"] > 0 else "exit_short"][j]:
                close(symbol, opens[symbol], i, "prior_close_indicator_exit")
                exited.add(symbol)
        worst, best = min(worst, equity(opens)), max(best, equity(opens))
        account = equity(opens)
        cap_equity = min(initial, account)
        daily_index = i-1
        if decision and i < end-1 and daily_index >= 0 and account > 0:
            # Both orderplans use known opening account/cash before any current
            # native candle's volume/high/low becomes available. Unexecuted
            # reservations cannot enlarge the other asset's currentbar order.
            planned_cash = cash
            planned_gross = math.fsum(p["quantity"]*opens[s] for s,p in positions.items())
            planned_risk = math.fsum(p["risk_budget"] for p in positions.values())
            plans = {}
            for symbol in SYMBOLS:
                if symbol in positions or symbol in exited:
                    continue
                side = observations[symbol]["entry"][j]
                atr = features.atr[symbol][daily_index]
                if not side or atr is None or atr <= 0:
                    continue
                fill = opens[symbol]*(1+adverse*side)
                distance = atr*variant["stop_atr"]
                stop = fill-side*distance
                if stop <= 0:
                    continue
                stop_fill = stop*(1-adverse*side)
                unit_risk = side*(fill-stop_fill)+fee*(fill+stop_fill)
                gross_room = max(0,variant["max_entry_gross"]*cap_equity-planned_gross)
                risk = max(0,min(account*variant["risk_fraction"],2*account*variant["risk_fraction"]-planned_risk))
                quantity = min(risk/unit_risk,gross_room/fill,
                               variant["max_entry_asset_gross"]*cap_equity/fill,
                               planned_cash/(fill*(1/variant["isolated_leverage"]+fee)))
                step = variant["quantity_steps"][symbol]
                quantity = math.floor(quantity/step)*step
                margin = quantity*fill/variant["isolated_leverage"]
                entry_fee = quantity*fill*fee
                if quantity <= 0 or margin+entry_fee > planned_cash+1e-8:
                    continue
                risk = quantity*unit_risk
                planned_cash -= margin+entry_fee
                planned_gross += quantity*fill
                planned_risk += risk
                plans[symbol] = (side,fill,distance,stop,quantity,margin,entry_fee,risk)
            for symbol,plan in plans.items():
                if raw[symbol]["volume"][i] <= 0:
                    skipped_zero_volume_entries += 1
                    continue
                side,fill,distance,stop,quantity,margin,entry_fee,risk = plan
                cash -= margin+entry_fee
                fees_paid += entry_fee
                adverse_cost += quantity*abs(fill-opens[symbol])
                turnover += quantity*fill
                signal_bar = features.times[j]
                positions[symbol] = {"entry_time": features.times[i], "entry_epoch": features.epochs[i],
                                     "signal_time": signal_bar, "signal_known_at": features.times[i],
                                     "atr_known_at": features.atr_known_at[symbol][daily_index], "direction": side,
                                     "entry_price": fill, "entry_raw_price": opens[symbol], "quantity": quantity,
                                     "margin": margin, "entry_fee": entry_fee, "funding": 0.0,
                                     "stop_price": stop, "target_price": None,
                                     "risk_budget": risk, "risk_at_stop_before_costs": quantity*distance}
        # Preserve conservative pre/post-funding native-bar account envelopes.
        adverse_prices = {s: raw[s]["low" if positions[s]["direction"] > 0 else "high"][i] if s in positions else opens[s] for s in SYMBOLS}
        favorable_prices = {s: raw[s]["high" if positions[s]["direction"] > 0 else "low"][i] if s in positions else opens[s] for s in SYMBOLS}
        worst, best = min(worst, equity(adverse_prices)), max(best, equity(favorable_prices))
        for symbol in tuple(positions):
            p = positions[symbol]
            adverse_price, favorable_price = adverse_prices[symbol], favorable_prices[symbol]
            pre_liq = wallet(p, adverse_price) <= maintenance*p["quantity"]*adverse_price
            stop_touch = p["direction"]*(adverse_price-p["stop_price"]) <= 0
            target_touch = p["target_price"] is not None and p["direction"]*(favorable_price-p["target_price"]) >= 0
            funding_charge(symbol, i, opens[symbol], exact=False, ambiguous=pre_liq or stop_touch or target_touch)
        worst, best = min(worst, equity(adverse_prices)), max(best, equity(favorable_prices))
        for symbol in tuple(positions):
            p = positions[symbol]
            adverse_price, favorable_price = adverse_prices[symbol], favorable_prices[symbol]
            if wallet(p, adverse_price) <= maintenance*p["quantity"]*adverse_price:
                close(symbol, adverse_price, i, "intrabar_liquidation_proxy", liquidating=True, timing="intrabar_unobserved")
            elif raw[symbol]["volume"][i] > 0 and p["direction"]*(adverse_price-p["stop_price"]) <= 0:
                close(symbol, p["stop_price"], i, "native_stop", timing="intrabar_unobserved")
            elif raw[symbol]["volume"][i] > 0 and p["target_price"] is not None and p["direction"]*(favorable_price-p["target_price"]) >= 0:
                close(symbol, p["target_price"], i, "native_target", timing="intrabar_unobserved")
        closes = {s: raw[s]["close"][i] for s in SYMBOLS}
        if i == end-1:
            for symbol in tuple(positions):
                funding_charge(symbol, end, closes[symbol], exact=True, ambiguous=True, boundary=True)
                close(symbol, closes[symbol], i, "sample_boundary", timing="close")
        mark = equity(closes)
        minimum_cash = min(minimum_cash, cash)
        gross = math.fsum(p["quantity"]*closes[s] for s, p in positions.items())
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
    metrics = {"initial_equity": initial, "final_equity": cash, "return_pct": (cash/initial-1)*100,
               "trade_count": len(trades), "win_rate_pct": 100*sum(t["pnl"] > 0 for t in trades)/len(trades) if trades else 0,
               "profit_factor": wins/losses if losses else None, "max_drawdown_pct": adverse_dd*100,
               "max_close_drawdown_pct": close_dd*100, "fees_paid": fees_paid, "adverse_fill_cost": adverse_cost,
               "funding_pnl": total_funding, "turnover_notional": turnover,
               "liquidation_count": liquidations, "unfunded_isolated_deficit": math.fsum(t["unfunded_isolated_deficit"] for t in trades),
               "funding_event_count": len(ledger), "average_gross_equity_ratio": gross_ratio_sum/(end-start),
               "unresolved_zero_volume_exposure_bars": unresolved_execution_bars,
               "skipped_zero_volume_entry_count": skipped_zero_volume_entries,
               "time_in_position_fraction": exposure_bars/(end-start), "minimum_available_cash": minimum_cash,
               "account_insolvent": any(row["equity"] <= 0 for row in daily),
               "execution_provisional": True, "historical_mark_prices_available": False}
    returns, previous = [], initial
    for row in daily:
        # Preserve bankrupt flat dates without dividing byzero. The driver
        # explicitly rejects insolvency; these values never enter inference.
        value = row["equity"]/previous-1 if previous > 0 else 0.0
        returns.append({"date": row["time"][:10], "return": value})
        previous = row["equity"]
    return {"metrics": metrics, "equity_curve": daily, "daily_returns": returns,
            "native_equity_curve": native_curve, "trades": trades, "funding_ledger": ledger,
            "start": features.times[start], "end": features.times[end-1]}
