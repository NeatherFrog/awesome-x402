"""Causal sweep/displacement/FVG research on genuine native perpetual candles.

Physical isolated collateral, actual settled funding, conservative unknown
intrabar chronology. All fills/maintenance/marks remain research assumptions.
No order APIs or production signal claims.
"""
from __future__ import annotations

from collections import deque
from datetime import timedelta
from itertools import product
import math

from propdesk import market, research_lab as lab
from propdesk.funding_lab import validate_events

SYMBOLS = ("BTCUSDT", "ETHUSDT")
SECONDS = 300


def grid():
    rows = []
    for minutes, liquidity, body, rr, expiry, trend, risk in product(
            (15, 60), (24, 72), (.6, 1.0), (1.5, 2.5), (4, 12), (False, True), (.0025, .005, .01)):
        rows.append({"id": f"fvg_{minutes}_{liquidity}_{body:g}_{rr:g}_{expiry}_{int(trend)}_r{risk:g}",
                     "minutes": minutes, "liquidity": liquidity, "body_atr": body,
                     "reward_risk": rr, "expiry": expiry, "trend_context": trend, "risk_fraction": risk})
    return rows


def stamp_text(stamp):
    return stamp.isoformat().replace("+00:00", "Z")


def resample(bars, minutes):
    """UTC open labels, full buckets only; missing native bars always reject."""
    if minutes not in (15, 60):
        raise ValueError("Only registered15m/1h complete resamples supported")
    count = minutes // 5
    times = [market.utc_datetime(b["time"]) for b in bars]
    if any((b-a).total_seconds() != SECONDS for a, b in zip(times, times[1:])):
        raise ValueError("Native5m calendar has a gap")
    out = []
    for i in range(0, len(bars), count):
        part = bars[i:i+count]
        if len(part) != count:
            break
        first = times[i]
        if first.second or first.microsecond or first.minute % minutes:
            raise ValueError("Resample starts outside an exact UTC bucket")
        out.append({"time": bars[i]["time"], "open": part[0]["open"],
                    "high": max(b["high"] for b in part), "low": min(b["low"] for b in part),
                    "close": part[-1]["close"], "volume": math.fsum(b["volume"] for b in part),
                    "contains_absent_trade_bar": any(b["volume"] == 0 for b in part),
                    "known_at": stamp_text(first+timedelta(minutes=minutes))})
    return out


def _extremes(bars, lookback, key, high):
    pending, result = deque(), []
    for i, bar in enumerate(bars):
        while pending and pending[0][0] < i-lookback:
            pending.popleft()
        result.append(pending[0][1] if i >= lookback else None)
        value = bar[key]
        while pending and (pending[-1][1] <= value if high else pending[-1][1] >= value):
            pending.pop()
        pending.append((i, value))
    return result


class Features:
    def __init__(self, datasets, funding):
        if set(datasets) != set(SYMBOLS) or set(funding) != set(SYMBOLS):
            raise ValueError("ExactBTC/ETH native perpetual universe required")
        self.bars = {s: market.validate_bars(datasets[s], max_bars=400_000) for s in SYMBOLS}
        clocks = [[r["time"] for r in self.bars[s]] for s in SYMBOLS]
        if clocks[0] != clocks[1]:
            raise ValueError("Both native asset calendars must align exactly")
        self.times = clocks[0]
        self.stamps = [market.utc_datetime(t) for t in self.times]
        if any((b-a).total_seconds() != SECONDS for a, b in zip(self.stamps, self.stamps[1:])):
            raise ValueError("Native5m calendar has a gap")
        if any(t.second or t.microsecond or t.minute % 5 for t in self.stamps):
            raise ValueError("Native times must be exact5minute UTC opens")
        self.funding, self.cache = {}, {}
        for s in SYMBOLS:
            events = validate_events(funding[s])
            slots = {}
            for event in events:
                if event.get("known_at") != event["time"] or event.get("rate_kind") != "realized_settlement_outcome":
                    raise ValueError("Realizedfunding known-at must equal settlement; no forecasts")
                slot = int(event["_stamp"].timestamp()) // SECONDS * SECONDS
                slots.setdefault(slot, []).append(event)
            self.funding[s] = slots

    def signal_features(self, symbol, minutes):
        key = (symbol, minutes)
        if key in self.cache:
            return self.cache[key]
        bars = resample(self.bars[symbol], minutes)
        ranges, atr, fast, slow = [], [], [], []
        average_fast = average_slow = None
        for i, bar in enumerate(bars):
            prior = bars[i-1]["close"] if i else bar["open"]
            ranges.append(max(bar["high"]-bar["low"], abs(bar["high"]-prior), abs(bar["low"]-prior)))
            atr.append(math.fsum(ranges[max(0, i-19):i+1])/20 if i >= 19 else None)
            average_fast = bar["close"] if average_fast is None else average_fast+(bar["close"]-average_fast)*2/25
            average_slow = bar["close"] if average_slow is None else average_slow+(bar["close"]-average_slow)*2/97
            fast.append(average_fast)
            slow.append(average_slow)
        highs = {n: _extremes(bars, n, "high", True) for n in (24, 72)}
        lows = {n: _extremes(bars, n, "low", False) for n in (24, 72)}
        result = {"bars": bars, "atr": atr, "fast": fast, "slow": slow, "highs": highs, "lows": lows}
        self.cache[key] = result
        return result


def setups(features, variant):
    """Events keyed by confirmation CLOSE, never by historical sweep timestamp."""
    if variant not in grid():
        raise ValueError("Unregistered variant")
    events = {}
    for symbol in SYMBOLS:
        f = features.signal_features(symbol, variant["minutes"])
        bars, atr = f["bars"], f["atr"]
        sweeps = {}
        for i, bar in enumerate(bars):
            if i < max(96, variant["liquidity"]):
                continue
            if any(b["contains_absent_trade_bar"] for b in bars[i-2:i+1]):
                continue
            for side in list(sweeps):
                sweep = sweeps[side]
                invalid = sweep["extreme"]-side*.1*sweep["atr"]
                crossed = bar["low"] <= invalid if side > 0 else bar["high"] >= invalid
                if i-sweep["index"] > 6 or crossed:
                    del sweeps[side]
            high, low = f["highs"][variant["liquidity"]][i], f["lows"][variant["liquidity"]][i]
            bull = bar["low"] < low and bar["close"] > low
            bear = bar["high"] > high and bar["close"] < high
            if bull != bear:
                side = 1 if bull else -1
                sweeps[side] = {"index": i, "time": bar["known_at"],
                                "extreme": bar["low"] if bull else bar["high"], "atr": atr[i-1],
                                "liquidity_level": low if bull else high}
            if i < 2 or atr[i-2] is None:
                continue
            middle, left = bars[i-1], bars[i-2]
            side = 1 if middle["close"] > middle["open"] else -1
            sweep = sweeps.get(side)
            if sweep is None or sweep["index"] >= i-1:
                continue
            if abs(middle["close"]-middle["open"]) < variant["body_atr"]*atr[i-2]:
                continue
            gap_low, gap_high = ((left["high"], bar["low"]) if side > 0 else (bar["high"], left["low"]))
            if gap_low >= gap_high:
                continue
            if variant["trend_context"] and side*(f["fast"][i-1]-f["slow"][i-1]) <= 0:
                continue
            entry = (gap_low+gap_high)/2
            stop = sweep["extreme"]-side*.1*sweep["atr"]
            distance = side*(entry-stop)
            if distance <= 0:
                continue
            known = market.utc_datetime(bar["known_at"])
            event = {"symbol": symbol, "direction": side, "entry": entry, "stop": stop,
                     "target": entry+side*variant["reward_risk"]*distance,
                     "entry_zone": [gap_low, gap_high], "invalidation": stop,
                     "signal_time": bar["known_at"], "sweep_time": sweep["time"],
                     "liquidity_level": sweep["liquidity_level"],
                     "expires_at": stamp_text(known+timedelta(minutes=variant["minutes"]*variant["expiry"])),
                     "reason": "Priorliquiditysweep;lateroppositedisplacement;completedthreecandleFVG;subsequentmidpointretest"}
            events.setdefault(int(known.timestamp()), {})[symbol] = event
            del sweeps[side]
    return events


def simulate(features, signals, start_date, end_date, *, initial=100_000.0, cost_multiplier=1.0, risk_fraction=.0025):
    """One physically funded account, at most two separate isolated1x positions."""
    if initial <= 0 or not math.isfinite(initial) or cost_multiplier <= 0 or not math.isfinite(cost_multiplier):
        raise ValueError("Positive finite capital/cost multiplier required")
    if isinstance(risk_fraction, bool) or risk_fraction not in (.0025, .005, .01):
        raise ValueError("Risk must belong to registered.25/.5/1percent catalogue")
    begin, finish = market.utc_datetime(start_date+"T00:00:00Z"), market.utc_datetime(end_date+"T00:00:00Z")
    active = [i for i, t in enumerate(features.stamps) if begin <= t < finish]
    if not active or features.stamps[active[0]] != begin or features.stamps[active[-1]]+timedelta(seconds=SECONDS) != finish:
        raise ValueError("Exact complete requested calendar exposure required")
    fee, adverse = .0005*cost_multiplier, .00025*cost_multiplier
    maintenance, liq_fee = .005, .005
    cash, positions, pending = float(initial), {}, {}
    trades, curve, fund_ledger = [], [], []
    total_funding = total_fees = adverse_cost = 0.0
    liquidation_count = 0
    unresolved_absent_trade_exposure = 0
    prior_traded = {s: features.bars[s][active[0]-1]["close"] if active[0] else features.bars[s][0]["open"] for s in SYMBOLS}

    def wallet(p, price):
        return p["margin"]+p["funding"]+p["direction"]*p["quantity"]*(price-p["entry_price"])

    def equity(prices):
        return cash+math.fsum(wallet(p, prices[s]) for s, p in positions.items())

    def liquidating(p, price):
        return wallet(p, price) <= maintenance*p["quantity"]*price

    def charge(symbol, event, proxy, *, ambiguous_exit=False):
        nonlocal total_funding
        p = positions.get(symbol)
        if p is None or event["_stamp"] <= p["_entry_earliest"]:
            return
        price = event.get("mark_price") or proxy
        amount = -p["direction"]*p["quantity"]*price*event["funding_rate"]
        # Intrabarentry is only certainly present after that interval's close.
        # Credits additionally require60s hold and no possibly earlier exit.
        certain = (event["_stamp"]-p["_entry_latest"]).total_seconds() >= 60
        if amount > 0 and (not certain or ambiguous_exit):
            return
        p["funding"] += amount
        total_funding += amount
        fund_ledger.append({"time": event["time"], "symbol": symbol, "pnl": amount,
                            "rate": event["funding_rate"], "price": price,
                            "mark_proxy": event.get("mark_price") is None,
                            "entry_or_exit_entitlement_ambiguous": not certain or ambiguous_exit})

    def close(symbol, raw, stamp, reason, *, liquidated=False, timing="intrabar_unobserved"):
        nonlocal cash, total_fees, adverse_cost, liquidation_count
        p = positions.pop(symbol)
        fill = max(raw*(1-p["direction"]*adverse), 1e-12)
        exit_fee = p["quantity"]*fill*fee
        penalty = p["quantity"]*raw*liq_fee if liquidated else 0.0
        value = wallet(p, fill)-exit_fee-penalty
        recovery = 0.0 if liquidated else max(value, 0.0)
        deficit = max(-value, 0.0)
        cash += recovery
        total_fees += exit_fee+penalty
        adverse_cost += p["quantity"]*abs(fill-raw)
        liquidation_count += int(liquidated)
        pnl = recovery-p["margin"]-p["entry_fee"]
        public = {k: v for k, v in p.items() if not k.startswith("_")}
        trades.append({**public, "symbol": symbol, "exit_time": stamp_text(stamp),
                       "exit_timing": timing, "exit_price": fill, "exit_fee": exit_fee+penalty,
                       "exit_adverse_cost": p["quantity"]*abs(fill-raw), "pnl": pnl,
                       "funding_pnl": p["funding"], "reason": reason,
                       "liquidation_proxy": liquidated, "unfunded_isolated_deficit": deficit,
                       "boundary_liquidation": reason == "sample_boundary"})

    for i in active:
        t, bar_end = features.stamps[i], features.stamps[i]+timedelta(seconds=SECONDS)
        epoch = int(t.timestamp())
        if not positions and not pending and epoch not in signals:
            # A verified flat account has no order, margin or funding cashflow.
            # Retain every calendar observation rather than omit idle bars.
            curve.append({"time": features.times[i], "equity": cash, "opening_equity": cash,
                          "worst_equity": cash, "best_equity": cash, "available_cash": cash,
                          "reserved_margin": 0.0, "opening_planned_risk": 0.0,
                          "opening_planned_gross": 0.0, "notional": 0.0})
            for s in SYMBOLS:
                if features.bars[s][i]["volume"] > 0:
                    prior_traded[s] = features.bars[s][i]["close"]
            continue
        bars = {s: features.bars[s][i] for s in SYMBOLS}
        absent = {s for s, b in bars.items() if b["volume"] == 0}
        for s in absent:
            # An archive's flat zero-volume price is not an executable quote.
            # Preserve calendar exposure with a preceding-known mark proxy.
            bars[s] = {**bars[s], **{k: prior_traded[s] for k in ("open", "high", "low", "close")}}
            unresolved_absent_trade_exposure += int(s in positions)
        opens = {s: b["open"] for s, b in bars.items()}
        opening = equity(opens)
        worst = best = opening
        exited = set()
        for s in SYMBOLS:
            p = positions.get(s)
            if p is None:
                continue
            gap_stop = p["direction"]*(opens[s]-p["stop"]) <= 0
            gap_target = p["direction"]*(opens[s]-p["target"]) >= 0
            time_exit = (t-p["_entry_latest"]).total_seconds() >= 86400
            open_liq = liquidating(p, opens[s])
            for event in features.funding[s].get(epoch, []):
                if event["_stamp"] == t:
                    charge(s, event, opens[s], ambiguous_exit=gap_stop or gap_target or time_exit or open_liq or s in absent or i == active[-1])
            worst, best = min(worst, equity(opens)), max(best, equity(opens))
            if s in absent:
                continue
            if open_liq or liquidating(p, opens[s]):
                close(s, opens[s], t, "opening_liquidation_proxy", liquidated=True, timing="open")
            elif gap_stop:
                close(s, opens[s], t, "gap_stop", timing="open")
            elif gap_target:
                close(s, p["target"], t, "opening_target", timing="open")
            elif time_exit:
                close(s, opens[s], t, "time_exit", timing="open")
            else:
                continue
            exited.add(s)
        worst, best = min(worst, equity(opens)), max(best, equity(opens))
        for s, event in signals.get(epoch, {}).items():
            if market.utc_datetime(event["signal_time"]) > t or event["symbol"] != s:
                raise ValueError("Setup not yet known or assigned to wrong asset")
            if s not in positions and s not in exited:
                pending[s] = event
        # Every quantity uses the same already-known prefill marked account.
        # The earlier-created intrabar BTC fill must never be valued at this
        # bar's earlier OPEN to finance or enlarge the ETH order.
        sizing_equity = equity(opens)
        new_entries = set()
        plans = {}
        planned_cash = cash
        planned_risk = math.fsum(p["risk_budget"] for p in positions.values())
        planned_gross = math.fsum(p["quantity"]*p["entry_price"] for p in positions.values())
        for s in SYMBOLS:
            event = pending.get(s)
            if event is None or s in positions or s in exited:
                continue
            if t >= market.utc_datetime(event["expires_at"]):
                del pending[s]
                continue
            if i == active[-1]:
                continue
            side, raw = event["direction"], event["entry"]
            fill = raw*(1+side*adverse)
            stop_fill = max(event["stop"]*(1-side*adverse), 1e-12)
            risk_unit = side*(fill-stop_fill)+fee*(fill+stop_fill)
            if risk_unit <= 0:
                del pending[s]
                continue
            eq = sizing_equity
            risk = max(0.0, min(risk_fraction*eq, 2*risk_fraction*eq-planned_risk))
            max_notional = min(max(initial-planned_gross, 0), planned_cash/(1+fee))
            q = math.floor(min(risk/risk_unit, max_notional/fill)/.001)*.001
            if q <= 0:
                continue
            margin, entry_fee = q*fill, q*fill*fee
            plans[s] = {"q": q, "margin": margin, "entry_fee": entry_fee,
                        "fill": fill, "risk_unit": risk_unit}
            planned_cash -= margin+entry_fee
            planned_risk += q*risk_unit
            planned_gross += margin
        # Unfilled reservations are released only after this complete bar.
        # Native future extrema cannot increase a different order's quantity.
        for s, plan in plans.items():
            event = pending[s]
            touched = (bars[s]["low"] <= event["entry"] if event["direction"] > 0 else bars[s]["high"] >= event["entry"])
            if s in absent or not touched:
                continue
            q, margin, entry_fee, fill, risk_unit = (plan[k] for k in ("q", "margin", "entry_fee", "fill", "risk_unit"))
            raw = event["entry"]
            cash -= margin+entry_fee
            if cash < -1e-7:
                raise AssertionError("Entry spent unavailable physical collateral")
            total_fees += entry_fee
            adverse_cost += q*abs(fill-raw)
            positions[s] = {**event, "quantity": q, "entry_price": fill, "margin": margin,
                            "entry_fee": entry_fee, "entry_adverse_cost": q*abs(fill-raw),
                            "funding": 0.0, "risk_budget": q*risk_unit,
                            "entry_time": stamp_text(t), "entry_time_latest": stamp_text(bar_end),
                            "_entry_earliest": t, "_entry_latest": bar_end}
            del pending[s]
            new_entries.add(s)
        adverse_prices = {s: bars[s]["low"] if p["direction"] > 0 else bars[s]["high"] for s, p in positions.items()}
        favorable_prices = {s: bars[s]["high"] if p["direction"] > 0 else bars[s]["low"] for s, p in positions.items()}
        worst, best = min(worst, equity(adverse_prices)), max(best, equity(favorable_prices))
        for s in list(positions):
            p, b = positions[s], bars[s]
            side = p["direction"]
            stop_hit = b["low"] <= p["stop"] if side > 0 else b["high"] >= p["stop"]
            target_hit = b["high"] >= p["target"] if side > 0 else b["low"] <= p["target"]
            pre_liq = liquidating(p, adverse_prices[s])
            for event in features.funding[s].get(epoch, []):
                if event["_stamp"] > t:
                    charge(s, event, opens[s], ambiguous_exit=stop_hit or target_hit or pre_liq or s in new_entries or s in absent or i == active[-1])
            worst, best = min(worst, equity(adverse_prices)), max(best, equity(favorable_prices))
            if s in absent:
                continue
            if pre_liq or liquidating(p, adverse_prices[s]):
                close(s, adverse_prices[s], bar_end, "intrabar_liquidation_proxy", liquidated=True)
            elif stop_hit:
                raw = min(opens[s], p["stop"]) if side > 0 else max(opens[s], p["stop"])
                close(s, raw, bar_end, "stop")
            elif target_hit and s not in new_entries:
                close(s, p["target"], bar_end, "target")
        # Postfunding snapshots include negativecharges before any close, but a
        # conservative lower bound also combines that payment with bar extrema.
        if positions:
            remaining_adverse = {s: bars[s]["low"] if p["direction"] > 0 else bars[s]["high"] for s, p in positions.items()}
            remaining_best = {s: bars[s]["high"] if p["direction"] > 0 else bars[s]["low"] for s, p in positions.items()}
            worst, best = min(worst, equity(remaining_adverse)), max(best, equity(remaining_best))
        closes = {s: b["close"] for s, b in bars.items()}
        if i == active[-1]:
            for s in list(positions):
                if s in absent:
                    raise ValueError("Cannot model boundary liquidation without a traded quote")
                for event in features.funding[s].get(int(finish.timestamp()), []):
                    if event["_stamp"] == finish:
                        # Exit/settlement exactlytied: no favorable exemption
                        # from a possiblyowed payment, no positive credit.
                        charge(s, event, closes[s], ambiguous_exit=True)
                worst = min(worst, equity(closes))
                close(s, closes[s], bar_end, "sample_boundary", timing="close")
        mark = equity(closes)
        worst, best = min(worst, mark), max(best, mark)
        curve.append({"time": features.times[i], "equity": mark, "opening_equity": opening,
                      "worst_equity": worst, "best_equity": best,
                      "available_cash": cash, "reserved_margin": math.fsum(p["margin"] for p in positions.values()),
                      "opening_planned_risk": planned_risk,
                      "opening_planned_gross": planned_gross,
                      "notional": math.fsum(p["quantity"]*closes[s] for s, p in positions.items())})
        for s in SYMBOLS:
            if s not in absent:
                prior_traded[s] = bars[s]["close"]
    metrics = lab.metrics(curve, trades, initial)
    metrics.update(fees_paid=total_fees, adverse_fill_cost=adverse_cost, funding_pnl=total_funding,
                   funding_event_count=len(fund_ledger), liquidation_count=liquidation_count,
                   unfunded_isolated_deficit=math.fsum(t["unfunded_isolated_deficit"] for t in trades),
                   equity_pnl_reconciliation_error=abs(curve[-1]["equity"]-initial-math.fsum(t["pnl"] for t in trades)),
                   unresolved_absent_trade_exposure_bars=unresolved_absent_trade_exposure,
                   execution_provisional=True, actual_mark_prices_available=False,
                   marked_native_bars_in_position=sum(r["notional"] > 0 for r in curve))
    daily, prior = {}, initial
    for row in curve:
        day = row["time"][:10]
        if day not in daily:
            daily[day] = {"date": day, "equity": row["equity"], "worst_equity": row["worst_equity"], "best_equity": row["best_equity"]}
        daily[day].update(equity=row["equity"], worst_equity=min(daily[day]["worst_equity"], row["worst_equity"]),
                          best_equity=max(daily[day]["best_equity"], row["best_equity"]))
    daily_rows = []
    for row in daily.values():
        # An insolvent account is never revived. Its firstzero close is−100%;
        # laterverifiedflat zero days remain explicit rather than dividebyzero.
        value = row["equity"]/prior-1 if prior > 0 else 0.0
        daily_rows.append({**row, "return": value})
        prior = row["equity"]
    return {"metrics": metrics, "equity_curve": curve, "daily": daily_rows,
            "trades": trades, "funding_ledger": fund_ledger,
            "start": curve[0]["time"], "end": stamp_text(finish)}
