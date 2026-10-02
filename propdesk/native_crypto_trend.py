"""Adaptive BTC/ETH perpetual trend/context research, never order execution.

Completed hourly/daily observations produce next-native-open orders. Native
five-minute trade candles proxy unavailable mark/bid/ask history. All isolated
collateral comes from one physical account; funding retains actual timestamps.
"""
from __future__ import annotations

from array import array
from bisect import bisect_left
from collections import deque
from datetime import timedelta
import itertools
import math

from propdesk import market, research_lab as lab

SYMBOLS = ("BTCUSDT", "ETHUSDT")
FIELDS = ("open", "high", "low", "close", "volume")


def grid():
    economic = []
    for fast, slow in ((5, 20), (10, 40), (20, 60)):
        economic.append({"family": "calendar_ema_trend", "fast_days": fast, "slow_days": slow})
    for entry, exit_ in ((5, 2), (20, 10), (55, 20)):
        economic.append({"family": "calendar_channel_breakout", "entry_days": entry, "exit_days": exit_})
    for threshold in (5, 10):
        economic.append({"family": "fast_reversion_momentum_context", "rsi_period": 2,
                         "rsi_threshold": threshold, "context_days": 63, "target_r": 2})
    rows = []
    for base, resolution, risk, stop in itertools.product(economic, ("hourly", "daily"), (.0025, .005, .01), (2, 3)):
        row = {**base, "decision_resolution": resolution, "risk_fraction": risk, "stop_daily_atr": stop,
               "daily_atr_period": 14, "isolated_leverage": 2, "max_entry_gross": 2,
               "max_entry_asset_gross": 1, "quantity_steps": {"BTCUSDT": .001, "ETHUSDT": .001}}
        row["id"] = "native_trend-" + lab.digest(row)[:12]
        rows.append(row)
    return rows


class PackedBars:
    def __init__(self, rows):
        if not rows:
            raise ValueError("Nonempty native five-minute history required")
        self.times, self.epochs = [], array("d")
        self.values = {key: array("d") for key in FIELDS}
        previous = None
        for row in rows:
            dt = market.utc_datetime(row["time"])
            stamp = dt.isoformat().replace("+00:00", "Z")
            if dt.second or dt.microsecond or dt.minute % 5 or stamp != row["time"]:
                raise ValueError("Canonical UTC five-minute opening labels required")
            if previous is not None and dt - previous != timedelta(minutes=5):
                raise ValueError("Missing, duplicate or unordered native five-minute bar")
            previous = dt
            vals = [float(row[key]) for key in FIELDS]
            o, h, lo, c, volume = vals
            if any(not math.isfinite(x) for x in vals) or min(o, h, lo, c) <= 0 or volume < 0:
                raise ValueError("Finite positive prices and nonnegative volume required")
            if lo > min(o, c) or h < max(o, c) or lo > h:
                raise ValueError("OHLC envelope is inconsistent")
            self.times.append(stamp)
            self.epochs.append(dt.timestamp())
            for key, value in zip(FIELDS, vals):
                self.values[key].append(value)

    def __len__(self):
        return len(self.times)


def _ema(values, period):
    out = [None] * len(values)
    if len(values) < period:
        return out
    current = math.fsum(values[:period]) / period
    out[period - 1] = current
    alpha = 2 / (period + 1)
    for i in range(period, len(values)):
        current += alpha * (values[i] - current)
        out[i] = current
    return out


def _atr(high, low, close, period):
    ranges = [high[0] - low[0]]
    ranges.extend(max(high[i] - low[i], abs(high[i] - close[i-1]), abs(low[i] - close[i-1])) for i in range(1, len(close)))
    out = [None] * len(close)
    if len(close) < period:
        return out
    current = math.fsum(ranges[:period]) / period
    out[period-1] = current
    for i in range(period, len(close)):
        current = (current * (period-1) + ranges[i]) / period
        out[i] = current
    return out


def _rsi(values, period):
    out = [None] * len(values)
    if len(values) <= period:
        return out
    gains = math.fsum(max(values[i] - values[i-1], 0) for i in range(1, period+1)) / period
    losses = math.fsum(max(values[i-1] - values[i], 0) for i in range(1, period+1)) / period
    def reading():
        return 50 if gains == losses == 0 else 100 if losses == 0 else 100 - 100 / (1 + gains / losses)
    out[period] = reading()
    for i in range(period+1, len(values)):
        move = values[i] - values[i-1]
        gains = (gains * (period-1) + max(move, 0)) / period
        losses = (losses * (period-1) + max(-move, 0)) / period
        out[i] = reading()
    return out


def _past_extreme(values, period, *, high):
    """Threshold at i excludes i, using exactly the preceding period bars."""
    out, queue = [None] * len(values), deque()
    for i, value in enumerate(values):
        while queue and queue[0] < i-period:
            queue.popleft()
        if i >= period:
            out[i] = values[queue[0]]
        while queue and (values[queue[-1]] <= value if high else values[queue[-1]] >= value):
            queue.pop()
        queue.append(i)
    return out


class NativeFeatures:
    def __init__(self, datasets):
        if set(datasets) != set(SYMBOLS):
            raise ValueError("Registered BTC/ETH native perpetual universe required")
        self.bars = {s: rows if isinstance(rows, PackedBars) else PackedBars(rows) for s, rows in datasets.items()}
        self.times = self.bars[SYMBOLS[0]].times
        self.epochs = self.bars[SYMBOLS[0]].epochs
        if any(self.bars[s].times != self.times for s in SYMBOLS):
            raise ValueError("Exact synchronized native five-minute clocks required")
        if self.times[0][11:16] != "00:00" or len(self.times) % 288:
            raise ValueError("Complete UTC days required; incomplete aggregate bars cannot be imputed")
        self.aggregate = {}
        self.atr = {}
        self.cache = {}
        for symbol in SYMBOLS:
            raw = self.bars[symbol]
            for resolution, size in (("hourly", 12), ("daily", 288)):
                cols = {key: array("d") for key in FIELDS}
                stamps = []
                for i in range(0, len(raw), size):
                    stamps.append(raw.times[i])
                    cols["open"].append(raw.values["open"][i])
                    cols["close"].append(raw.values["close"][i+size-1])
                    cols["high"].append(max(raw.values["high"][i:i+size]))
                    cols["low"].append(min(raw.values["low"][i:i+size]))
                    cols["volume"].append(math.fsum(raw.values["volume"][i:i+size]))
                self.aggregate[symbol, resolution] = {"times": stamps, **cols}
            daily = self.aggregate[symbol, "daily"]
            self.atr[symbol] = _atr(daily["high"], daily["low"], daily["close"], 14)

    def observations(self, variant):
        economic = {k: v for k, v in variant.items() if k not in
                    ("id", "risk_fraction", "stop_daily_atr", "daily_atr_period", "isolated_leverage",
                     "max_entry_gross", "max_entry_asset_gross", "quantity_steps")}
        key = lab.digest(economic)
        if key in self.cache:
            return self.cache[key]
        out = {}
        resolution = variant["decision_resolution"]
        per_day = 24 if resolution == "hourly" else 1
        for symbol in SYMBOLS:
            bars = self.aggregate[symbol, resolution]
            close = bars["close"]
            n = len(close)
            entry, exit_long, exit_short = (array("b", [0])*n for _ in range(3))
            family = variant["family"]
            if family == "calendar_ema_trend":
                fast = _ema(close, variant["fast_days"]*per_day)
                slow = _ema(close, variant["slow_days"]*per_day)
                for j in range(n):
                    if fast[j] is not None and slow[j] is not None:
                        direction = 1 if fast[j] > slow[j] else -1 if fast[j] < slow[j] else 0
                        entry[j] = direction
                        exit_long[j], exit_short[j] = direction <= 0, direction >= 0
            elif family == "calendar_channel_breakout":
                highs = _past_extreme(bars["high"], variant["entry_days"]*per_day, high=True)
                lows = _past_extreme(bars["low"], variant["entry_days"]*per_day, high=False)
                exit_high = _past_extreme(bars["high"], variant["exit_days"]*per_day, high=True)
                exit_low = _past_extreme(bars["low"], variant["exit_days"]*per_day, high=False)
                for j in range(n):
                    if highs[j] is not None:
                        entry[j] = 1 if close[j] > highs[j] else -1 if close[j] < lows[j] else 0
                    if exit_high[j] is not None:
                        exit_long[j], exit_short[j] = close[j] < exit_low[j], close[j] > exit_high[j]
            elif family == "fast_reversion_momentum_context":
                rsi = _rsi(close, variant["rsi_period"])
                back = variant["context_days"]*per_day
                threshold = variant["rsi_threshold"]
                for j in range(back, n):
                    if rsi[j] is None:
                        continue
                    trend = close[j] / close[j-back] - 1
                    entry[j] = 1 if trend > 0 and rsi[j] <= threshold else -1 if trend < 0 and rsi[j] >= 100-threshold else 0
                    exit_long[j], exit_short[j] = rsi[j] >= 50 or trend <= 0, rsi[j] <= 50 or trend >= 0
            else:
                raise ValueError("Unregistered economic family")
            out[symbol] = {"entry": entry, "exit_long": exit_long, "exit_short": exit_short}
        self.cache[key] = out
        return out


def prepare_funding(features, funding):
    """Map recorded settlements to containing 5m bars without rounding time."""
    events = {s: {} for s in SYMBOLS}
    for symbol in SYMBOLS:
        previous = None
        for row in funding[symbol]:
            time = market.utc_datetime(row["time"])
            epoch = time.timestamp()
            if previous is not None and epoch <= previous:
                raise ValueError("Funding must be unique and ascending")
            previous = epoch
            rate = float(row["funding_rate"])
            if not math.isfinite(rate) or row.get("rate_kind") != "realized_settlement_outcome":
                raise ValueError("Actual finite settled funding required")
            if market.utc_datetime(row["known_at"]) != time:
                raise ValueError("Realized settlement cannot be known before its recorded timestamp")
            index = bisect_left(features.epochs, epoch)
            if index == len(features.epochs) or features.epochs[index] > epoch:
                index -= 1
            if epoch == features.epochs[-1] + 300:
                # Exact sample-end tie may debit the old position before its
                # boundary valuation; never grant an uncertain positive credit.
                events[symbol].setdefault(len(features.times), []).append({"time": row["time"], "epoch": epoch, "rate": rate})
                continue
            if index < 0 or epoch >= features.epochs[index] + 300:
                continue
            events[symbol].setdefault(index, []).append({"time": row["time"], "epoch": epoch, "rate": rate})
    return events


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
    decision_size = 12 if variant["decision_resolution"] == "hourly" else 288
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
            elif liquid_volume and decision and observations[symbol]["exit_long" if p["direction"] > 0 else "exit_short"][j]:
                close(symbol, opens[symbol], i, "prior_close_indicator_exit")
                exited.add(symbol)
        worst, best = min(worst, equity(opens)), max(best, equity(opens))
        account = equity(opens)
        cap_equity = min(initial, account)
        daily_index = i//288-1
        if decision and i < end-1 and daily_index >= 0 and account > 0:
            for symbol in SYMBOLS:
                if symbol in positions or symbol in exited:
                    continue
                side = observations[symbol]["entry"][j]
                atr = features.atr[symbol][daily_index]
                if not side or atr is None or atr <= 0:
                    continue
                if raw[symbol]["volume"][i] <= 0:
                    skipped_zero_volume_entries += 1
                    continue
                fill = opens[symbol]*(1+adverse*side)
                distance = atr*variant["stop_daily_atr"]
                stop = fill-side*distance
                if stop <= 0:
                    continue
                current_gross = math.fsum(p["quantity"]*opens[s] for s, p in positions.items())
                gross_room = max(0, variant["max_entry_gross"]*cap_equity-current_gross)
                risk = account*variant["risk_fraction"]
                quantity = min(risk/distance, gross_room/fill,
                               variant["max_entry_asset_gross"]*cap_equity/fill,
                               cash/(fill*(1/variant["isolated_leverage"]+fee)))
                step = variant["quantity_steps"][symbol]
                quantity = math.floor(quantity/step)*step
                margin = quantity*fill/variant["isolated_leverage"]
                entry_fee = quantity*fill*fee
                if quantity <= 0 or margin+entry_fee > cash+1e-8:
                    continue
                cash -= margin+entry_fee
                fees_paid += entry_fee
                adverse_cost += quantity*abs(fill-opens[symbol])
                turnover += quantity*fill
                signal_bar = features.aggregate[symbol, variant["decision_resolution"]]["times"][j]
                positions[symbol] = {"entry_time": features.times[i], "entry_epoch": features.epochs[i],
                                     "signal_time": signal_bar, "signal_known_at": features.times[i],
                                     "atr_known_at": features.times[(daily_index+1)*288], "direction": side,
                                     "entry_price": fill, "entry_raw_price": opens[symbol], "quantity": quantity,
                                     "margin": margin, "entry_fee": entry_fee, "funding": 0.0,
                                     "stop_price": stop, "target_price": fill+side*distance*variant["target_r"] if variant.get("target_r") else None,
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
