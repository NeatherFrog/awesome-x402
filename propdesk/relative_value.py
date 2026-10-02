"""BTC/ETH perpetual relative-value research, never exchange execution.

Rolling log-price OLS is causal but does not prove cointegration. Hedge beta is
frozen on entry. Both positions incur costs and actual funding. Trade candles
proxy unavailable historical mark prices, so liquidation is provisional.
"""
from __future__ import annotations

import itertools
import math
from datetime import timedelta

from propdesk import market, research_lab as lab

SYMBOLS = ("BTCUSDT", "ETHUSDT")


def grid():
    rows = []
    for hours, entry, exit_, risk, hold in itertools.product([168, 336, 720], [1.5, 2.0], [0.0, .5], [.0025, .005], [72, 168]):
        row = {"family": "frozen_beta_perpetual_residual", "hedge_hours": hours,
               "entry_z": entry, "exit_z": exit_, "risk_fraction": risk,
               "max_hold_hours": hold, "stop_z": 3.5, "max_gross": 2.0,
               "isolated_leverage": 2.0, "beta_min": .25, "beta_max": 3.0,
               "quantity_steps": {"BTCUSDT": .001, "ETHUSDT": .001}}
        row["id"] = "relative_value-"+lab.digest(row)[:12]
        rows.append(row)
    return rows


class PairFeatures:
    def __init__(self, datasets):
        if set(datasets) != set(SYMBOLS):
            raise ValueError("FixedBTCETHperpetualuniverse required")
        self.bars = {s: market.validate_bars(rows, max_bars=100_000) for s, rows in datasets.items()}
        self.times = [b["time"] for b in self.bars[SYMBOLS[0]]]
        if self.times != [b["time"] for b in self.bars[SYMBOLS[1]]]:
            raise ValueError("Exact synchronized perpetual hourly clocks required")
        for a, b in zip(self.times, self.times[1:]):
            if market.utc_datetime(b)-market.utc_datetime(a) != timedelta(hours=1):
                raise ValueError("Missing perpetual hour; no imputation")
        self.y = [math.log(b["close"]) for b in self.bars["BTCUSDT"]]
        self.x = [math.log(b["close"]) for b in self.bars["ETHUSDT"]]
        self.cache = {}

    def ols(self, hours):
        if hours not in self.cache:
            sums = [0.0]*5
            out = [None]*len(self.times)
            for i, (x, y) in enumerate(zip(self.x, self.y)):
                sums = [a+b for a, b in zip(sums, (x, y, x*x, y*y, x*y))]
                if i >= hours:
                    x, y = self.x[i-hours], self.y[i-hours]
                    sums = [a-b for a, b in zip(sums, (x, y, x*x, y*y, x*y))]
                if i < hours-1:
                    continue
                mx, my = sums[0]/hours, sums[1]/hours
                vx, vy, cov = max(0, sums[2]/hours-mx*mx), max(0, sums[3]/hours-my*my), sums[4]/hours-mx*my
                if vx < 1e-10:
                    continue
                beta = cov/vx
                alpha = my-beta*mx
                sigma = math.sqrt(max(0, vy-cov*cov/vx))
                if sigma < .0001:
                    continue
                residual = self.y[i]-alpha-beta*self.x[i]
                out[i] = {"alpha": alpha, "beta": beta, "sigma": sigma, "z": residual/sigma,
                          "signal_time": self.times[i]}
            self.cache[hours] = out
        return self.cache[hours]


def observations(features, variant):
    source = features.ols(variant["hedge_hours"])
    out = [None]*len(source)
    for i in range(1, len(out)):
        row = source[i-1]
        if row is not None and variant["beta_min"] <= row["beta"] <= variant["beta_max"]:
            out[i] = {**row, "entry": variant["entry_z"] <= abs(row["z"]) < variant["stop_z"]}
    return out


def zscore(prices, model):
    return (math.log(prices["BTCUSDT"])-model["alpha"]-model["beta"]*math.log(prices["ETHUSDT"]))/model["sigma"]


def simulate(features, signal, funding, variant, start_date, end_date, *, initial=100_000,
             cost_multiplier=1, funding_stress=False):
    if len(signal) != len(features.times) or initial <= 0 or cost_multiplier <= 0:
        raise ValueError("Validcapital,friction and synchronoussignals required")
    active = [i for i, t in enumerate(features.times) if start_date <= t[:10] < end_date]
    if not active:
        raise ValueError("Emptyregisteredwindow")
    # Actual settled outcome is only charged to a position already held before
    # settlement. It is never supplied as an entry forecast.
    settlements = {s: {} for s in SYMBOLS}
    for symbol in SYMBOLS:
        previous = None
        for row in funding[symbol]:
            time = market.utc_datetime(row["time"])
            rate = float(row["funding_rate"])
            if not math.isfinite(rate) or previous is not None and time <= previous:
                raise ValueError("Fundingmust befinite,unique,ascending")
            if time.minute or time.second or row.get("rate_kind") != "realized_settlement_outcome":
                raise ValueError("Hourlyrealizedsettlements required")
            if market.utc_datetime(row["known_at"]) != time:
                raise ValueError("Settledfunding known-at must equal recordedsettlement; never a forecast")
            previous = time
            slot = time.replace(microsecond=0).isoformat().replace("+00:00", "Z")
            if slot in settlements[symbol]:
                raise ValueError("Multiplefundingevents inonehourlyslot unsupported")
            settlements[symbol][slot] = {"rate": rate, "actual_time": row["time"]}
    fee, adverse = .0005*cost_multiplier, .00025*cost_multiplier
    maintenance, liquidation_fee = .005, .005
    cash, position, trades, curve, funding_ledger = float(initial), None, [], [], []
    total_funding = total_fees = adverse_cost = turnover = 0.0
    liquidation_count = 0

    def wallet(leg, price):
        return leg["margin"]+leg["funding"]+leg["direction"]*leg["quantity"]*(price-leg["entry_price"])

    def equity(prices):
        return cash+(sum(max(0, wallet(leg, prices[s])) for s, leg in position["legs"].items()) if position else 0)

    def charge_funding(stamp, opens, *, exact_open, ambiguous_stop=False):
        nonlocal total_funding
        if not position:
            return
        for symbol, leg in position["legs"].items():
            event = settlements[symbol].get(stamp)
            if not event:
                continue
            event_time, bar_time = market.utc_datetime(event["actual_time"]), market.utc_datetime(stamp)
            if (event_time == bar_time) != exact_open:
                continue
            # Openingorders occur before a later millisecondsettlement, never
            # finance with it. Newpositions require a fixedone-minutehold age.
            age = (event_time-market.utc_datetime(position["entry_time"])).total_seconds()
            if age < 60:
                continue
            amount = -leg["direction"]*leg["quantity"]*opens[symbol]*event["rate"]
            raw_amount = amount
            # Intrabar stop time is unavailable. Do not credit positive funding
            # that may occur after a stop; retain adverse charges conservatively.
            if ambiguous_stop and amount > 0:
                amount = 0.0
            if funding_stress:
                amount *= .5 if amount > 0 else 2
            leg["funding"] += amount
            total_funding += amount
            funding_ledger.append({"time": event["actual_time"], "bar_slot": stamp, "symbol": symbol,
                                   "rate": event["rate"], "pnl": amount, "unstressed_amount": raw_amount,
                                   "price_proxy": opens[symbol], "actual_mark_unavailable": True,
                                   "held_seconds": age, "intrabar_entitlement_ambiguous": ambiguous_stop})

    def close_pair(prices, stamp, reason, *, liquidating=()):
        nonlocal cash, position, total_fees, adverse_cost, turnover, liquidation_count
        records, recovered, deficit = {}, 0.0, 0.0
        for symbol, leg in position["legs"].items():
            raw = prices[symbol]
            fill = raw*(1-adverse*leg["direction"])
            charge = leg["quantity"]*fill*fee
            liquidation_charge = leg["quantity"]*raw*liquidation_fee if symbol in liquidating else 0
            value = wallet(leg, fill)-charge-liquidation_charge
            # Isolatedcollateral only; deficits are disclosed, never silently
            # funded from fresh capital or turned into negative available cash.
            deficit += max(-value, 0)
            recover = 0.0 if symbol in liquidating else max(value, 0)
            recovered += recover
            total_fees += charge+liquidation_charge
            adverse_cost += abs(raw-fill)*leg["quantity"]
            turnover += fill*leg["quantity"]
            records[symbol] = {**leg, "exit_price": fill, "exit_fee": charge,
                               "liquidation_fee": liquidation_charge, "recovered_margin": recover}
        cash += recovered
        liquidation_count += bool(liquidating)
        profit = recovered-position["reserved_margin"]-position["entry_fees"]
        trades.append({"entry_time": position["entry_time"], "signal_time": position["signal_time"],
                       "exit_time": stamp, "direction": position["direction"], "model": position["model"],
                       "legs": records, "pnl": profit, "risk_budget": position["risk_budget"],
                       "funding_pnl": sum(leg["funding"] for leg in position["legs"].values()),
                       "reason": reason, "boundary_liquidation": reason == "sample_boundary",
                       "liquidation_proxy": bool(liquidating), "unfunded_isolated_deficit": deficit})
        position = None

    for i in active:
        stamp = features.times[i]
        bars = {s: features.bars[s][i] for s in SYMBOLS}
        opens = {s: b["open"] for s, b in bars.items()}
        opening = equity(opens)
        exited = False
        if position:
            pre_funding_liq = [s for s, leg in position["legs"].items()
                               if wallet(leg, opens[s]) <= maintenance*leg["quantity"]*opens[s]]
            if not pre_funding_liq:
                charge_funding(stamp, opens, exact_open=True)
            opening_liq = [s for s, leg in position["legs"].items()
                           if wallet(leg, opens[s]) <= maintenance*leg["quantity"]*opens[s]]
            model, direction = position["model"], position["direction"]
            open_z = zscore(opens, model)
            previous = {s: features.bars[s][i-1]["close"] for s in SYMBOLS} if i else opens
            previous_z = zscore(previous, model)
            if opening_liq:
                close_pair(opens, stamp, "opening_liquidation_proxy", liquidating=opening_liq)
                exited = True
            elif direction*open_z <= -variant["stop_z"]:
                close_pair(opens, stamp, "opening_residual_stop")
                exited = True
            elif direction*previous_z >= -variant["exit_z"]:
                close_pair(opens, stamp, "prior_close_reversion_exit")
                exited = True
            elif i-position["entry_index"] >= variant["max_hold_hours"]:
                close_pair(opens, stamp, "time_exit")
                exited = True
        if not position and not exited and i != active[-1] and signal[i] and signal[i]["entry"]:
            model = signal[i]
            direction = -1 if model["z"] > 0 else 1
            open_z = zscore(opens, model)
            # Entry requires the nextopen still to lie between target and stop.
            if -variant["stop_z"] < direction*open_z < -variant["exit_z"]:
                risk = initial*variant["risk_fraction"]
                distance = (variant["stop_z"]+direction*open_z)*model["sigma"]
                beta = model["beta"]
                btc_notional = min(risk/max(distance, .0001), initial*variant["max_gross"]/(1+beta),
                                   cash/(1+beta)/(1/variant["isolated_leverage"]+fee))
                legs = {}
                for symbol, multiple, side in (("BTCUSDT", 1, direction), ("ETHUSDT", beta, -direction)):
                    fill = opens[symbol]*(1+adverse*side)
                    step = variant["quantity_steps"][symbol]
                    quantity = math.floor((btc_notional*multiple/fill)/step)*step
                    legs[symbol] = {"quantity": quantity, "direction": side, "entry_price": fill,
                                    "margin": quantity*fill/variant["isolated_leverage"], "funding": 0.0,
                                    "entry_fee": quantity*fill*fee}
                reserve = sum(leg["margin"] for leg in legs.values())
                fees = sum(leg["entry_fee"] for leg in legs.values())
                if all(leg["quantity"] > 0 for leg in legs.values()) and reserve+fees <= cash+1e-8:
                    cash -= reserve+fees
                    total_fees += fees
                    turnover += sum(leg["quantity"]*leg["entry_price"] for leg in legs.values())
                    adverse_cost += sum(leg["quantity"]*abs(leg["entry_price"]-opens[s]) for s, leg in legs.items())
                    position = {"legs": legs, "model": {k: model[k] for k in ("alpha", "beta", "sigma")},
                                "direction": direction, "entry_time": stamp, "signal_time": model["signal_time"],
                                "entry_index": i, "risk_budget": risk, "reserved_margin": reserve, "entry_fees": fees}
        worst, notional = min(opening, cash if not position else opening), 0.0
        best = opening
        if position:
            adverse_prices = {s: bars[s]["low"] if leg["direction"] > 0 else bars[s]["high"] for s, leg in position["legs"].items()}
            favorable_prices = {s: bars[s]["high"] if leg["direction"] > 0 else bars[s]["low"] for s, leg in position["legs"].items()}
            best = max(best, equity(favorable_prices))
            worst = min(worst, equity(adverse_prices))
            adverse_z = zscore(adverse_prices, position["model"])
            pre_funding_intrabar_liq = any(wallet(leg, adverse_prices[s]) <= maintenance*leg["quantity"]*adverse_prices[s]
                                          for s, leg in position["legs"].items())
            possibly_stopping = position["direction"]*adverse_z <= -variant["stop_z"] or pre_funding_intrabar_liq
            charge_funding(stamp, opens, exact_open=False, ambiguous_stop=possibly_stopping)
            best = max(best, equity(favorable_prices))
            worst = min(worst, equity(adverse_prices))
            liquidating = [s for s, leg in position["legs"].items()
                           if wallet(leg, adverse_prices[s]) <= maintenance*leg["quantity"]*adverse_prices[s]]
            if liquidating:
                close_pair(adverse_prices, stamp, "intrabar_liquidation_proxy", liquidating=liquidating)
            elif position["direction"]*adverse_z <= -variant["stop_z"]:
                close_pair(adverse_prices, stamp, "conservative_intrabar_spread_stop")
        closes = {s: b["close"] for s, b in bars.items()}
        if i == active[-1] and position:
            close_time = (market.utc_datetime(stamp)+timedelta(hours=1)).isoformat().replace("+00:00", "Z")
            close_pair(closes, close_time, "sample_boundary")
        if position:
            notional = sum(leg["quantity"]*closes[s] for s, leg in position["legs"].items())
        mark = equity(closes)
        curve.append({"time": stamp, "equity": mark, "opening_equity": opening,
                      "worst_equity": min(worst, mark), "best_equity": max(best, mark), "notional": notional,
                      "available_cash": cash})
    # Supply fee fields expected by sharedmetrics; no oldproducer is changed.
    metric_trades = [{**t, "entry_fee": sum(l["entry_fee"] for l in t["legs"].values()),
                      "exit_fee": sum(l["exit_fee"]+l["liquidation_fee"] for l in t["legs"].values()),
                      "quantity": 0, "entry_price": 0, "exit_price": 0} for t in trades]
    metrics = lab.metrics(curve, metric_trades, initial)
    metrics.update(funding_pnl=total_funding, fees_paid=total_fees, adverse_fill_cost=adverse_cost,
                   turnover_notional=turnover, liquidation_count=liquidation_count,
                   unfunded_isolated_deficit=sum(t["unfunded_isolated_deficit"] for t in trades),
                   funding_event_count=len(funding_ledger), execution_provisional=True,
                   historical_mark_prices_available=False)
    return {"metrics": metrics, "equity_curve": curve, "daily_returns": lab.daily_returns(curve, initial),
            "trades": trades, "funding_ledger": funding_ledger,
            "start": curve[0]["time"], "end": curve[-1]["time"]}
