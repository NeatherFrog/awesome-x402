"""Causal Asian-range / London hypotheses on FX OHLC research proxies.

Only completed preceding candles create a decision, followed by next open.
These prices are not broker bid/ask and no historical profit is certified.
"""
from __future__ import annotations
from datetime import datetime, timezone, timedelta, date
import math
from collections import defaultdict
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from .timezones import timezone_for

try:
    LONDON = timezone_for("Europe/London")
except ZoneInfoNotFoundError:
    with (Path(__file__).resolve().parent/"tzdata/Europe/London").open("rb") as stream:
        LONDON = ZoneInfo.from_file(stream, key="Europe/London")
SPECS = {
    "EURUSD": {"pip": .0001, "spread_pips": 1.0, "quote": "USD", "leverage": 30},
    "GBPUSD": {"pip": .0001, "spread_pips": 1.5, "quote": "USD", "leverage": 30},
    "USDJPY": {"pip": .01, "spread_pips": 1.0, "quote": "JPY", "leverage": 30},
}


def variants():
    return [{"id": f"{symbol}_{family}_{risk}_{rr}_{hold}", "symbol": symbol,
             "family": family, "risk": risk, "reward_risk": rr, "hold_hours": hold}
            for symbol in SPECS for family in ("asian_breakout", "asian_rejection", "asian_drift")
            for risk in (.005, .01) for rr in (1, 2) for hold in (3, 6)]


def stamp(value):
    d = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if d.tzinfo is None:
        raise ValueError("Timezone-aware bars required")
    return d.astimezone(timezone.utc)


def pnl(quantity, side, entry, exit_price, quote):
    # Quote-JPY CFD profit is converted at the contemporaneous exit/mark price.
    amount = quantity * side * (exit_price - entry)
    return amount / exit_price if quote == "JPY" else amount


def validate(bars):
    last = None
    for b in bars:
        t = stamp(b["time"])
        values = [float(b[k]) for k in ("open", "high", "low", "close")]
        if (last is not None and t <= last) or not all(math.isfinite(v) and v > 0 for v in values):
            raise ValueError("Finite positive strictly ordered OHLC required")
        o,h,l,c = values
        if not l <= min(o,c) <= max(o,c) <= h:
            raise ValueError("Invalid OHLC envelope")
        last = t


def source_coverage(bars, begin, finish):
    """Report unobserved London decision windows, never invent holiday bars."""
    begin, finish = stamp(begin), stamp(finish)
    stamps = [stamp(b['time']) for b in bars]
    by_day = defaultdict(set)
    for t in stamps:
        local = t.astimezone(LONDON)
        if local.minute == 0:
            by_day[local.date().isoformat()].add(local.hour)
    statuses = []
    day = begin.astimezone(LONDON).date()
    while day <= (finish-timedelta(microseconds=1)).astimezone(LONDON).date():
        decision_open = datetime(day.year, day.month, day.day, 8, tzinfo=LONDON).astimezone(timezone.utc)
        if day.weekday() < 5 and begin <= decision_open < finish:
            missing = sorted(set(range(16))-by_day[day.isoformat()])
            statuses.append({'local_date':day.isoformat(), 'missing_hours':missing,
                             'status':'unobserved_or_partial' if missing else 'observed_complete'})
        day += timedelta(days=1)
    return {'source_spans_declared_window':bool(stamps and stamps[0] <= begin and stamps[-1]+timedelta(hours=1) >= finish),
            'broker_calendar_verified':False, 'weekdays':len(statuses),
            'complete_windows':sum(x['status']=='observed_complete' for x in statuses),
            'missing_or_partial_windows':[x for x in statuses if x['status']!='observed_complete'],
            'calendar_dates':statuses}


def decisions(bars, variant):
    """Return decisions keyed by a later execution index; no future prices."""
    validate(bars)
    if variant not in variants():
        raise ValueError("Unregistered FX variant")
    by_day = defaultdict(dict)
    result = {}
    tr = []
    for i,b in enumerate(bars):
        t = stamp(b["time"])
        local = t.astimezone(LONDON)
        if local.minute != 0 or local.second != 0:
            raise ValueError("This frozen study requires whole-hour FX anchors")
        if local.weekday() >= 5:
            continue
        day = local.date().isoformat()
        history = by_day[day]
        previous_atr = sum(tr[-14:])/14 if len(tr) >= 14 else None
        # Asia consists only of six already completed midnight-06:00 local bars.
        complete_asia = all(h in history for h in range(6))
        if previous_atr and complete_asia and local.hour in (7,8,9) and i+1 < len(bars):
            asia = [history[h] for h in range(6)]
            high,low = max(x["high"] for x in asia),min(x["low"] for x in asia)
            # Fixed volatility context excludes both unusually tiny and wide
            # Asian ranges. It is not selected using later London outcomes.
            if .5*previous_atr <= high-low <= 6*previous_atr:
                side = 0
                family = variant["family"]
                if family == "asian_breakout":
                    side = 1 if b["close"] > high else -1 if b["close"] < low else 0
                elif family == "asian_rejection":
                    upper = b["high"] > high+.05*previous_atr and low < b["close"] < high
                    lower = b["low"] < low-.05*previous_atr and low < b["close"] < high
                    side = (-1 if upper else 1 if lower else 0) if not(upper and lower) else 0
                elif local.hour == 7:
                    drift = asia[-1]["close"]-asia[0]["open"]
                    side = 1 if drift > .5*previous_atr else -1 if drift < -.5*previous_atr else 0
                next_t = stamp(bars[i+1]["time"])
                if side and next_t == t+timedelta(hours=1):
                    if family == "asian_breakout":
                        stop = low-.1*previous_atr if side > 0 else high+.1*previous_atr
                    elif family == "asian_rejection":
                        stop = b["low"]-.1*previous_atr if side > 0 else b["high"]+.1*previous_atr
                    else:
                        stop = b["close"]-side*previous_atr
                    result[i+1] = {"side": side, "stop": stop, "known_at": (t+timedelta(hours=1)).isoformat(),
                                   "reference_high": high, "reference_low": low,
                                   "reason": family, "signal_bar": i}
        history[local.hour] = b
        previous_close = bars[i-1]["close"] if i else b["open"]
        tr.append(max(b["high"]-b["low"],abs(b["high"]-previous_close),abs(b["low"]-previous_close)))
    return result


def simulate(bars, variant, begin, finish, *, capital=100000., cost_multiplier=1.):
    if capital <= 0 or cost_multiplier <= 0:
        raise ValueError("Positive initial total capital and costs required")
    spec = SPECS[variant["symbol"]]
    begin,finish = stamp(begin),stamp(finish)
    signals = decisions(bars,variant)
    coverage = source_coverage(bars,begin.isoformat(),finish.isoformat())
    # All model frictions are conservative hypotheses, not verified FTMO tariffs.
    friction = spec["pip"]*(spec["spread_pips"]/2+.5)*cost_multiplier
    fee_unit = 5/100000*cost_multiplier
    cash,position = float(capital),None
    trades,curve,eligibility_gaps = [],[],[]
    used_days = set()
    daily_close,daily_worst,daily_best = {},{},{}

    def price_pnl(price):
        return pnl(position["quantity"],position["side"],position["entry"],price,spec["quote"])

    def close(price,when,reason, *, precision='known_open', bar_start=None):
        nonlocal cash,position
        exit_price = price-position["side"]*friction
        profit = price_pnl(exit_price)
        exit_fee = fee_unit*position["quantity"]
        cash += profit-exit_fee
        trade={**position,"exit":exit_price,"exit_time":when.isoformat(),"exit_reason":reason,
               "exit_time_precision":precision,
               "exit_interval_start":bar_start.isoformat() if bar_start else when.isoformat(),
               "exit_interval_end":when.isoformat(),
               "price_pnl":profit,"exit_fee":exit_fee,"net_pnl":profit-exit_fee-position["entry_fee"]}
        trades.append(trade)
        position=None

    for i,b in enumerate(bars):
        t=stamp(b["time"])
        if t < begin or t >= finish:
            continue
        local=t.astimezone(LONDON)
        before=cash
        best=worst=cash
        if position:
            missing = i>0 and t-stamp(bars[i-1]["time"]) != timedelta(hours=1)
            if missing:
                eligibility_gaps.append(t.isoformat())
                close(b["open"],t,"adverse_gap_exit")
            elif t >= position["expiry"] or local.hour >= 15 or local.date().isoformat()!=position["local_day"]:
                close(b["open"],t,"time_exit")
        signal=signals.get(i)
        if position is None and signal and local.weekday()<5 and local.hour<15 and local.date().isoformat() not in used_days:
            side,stop=signal["side"],signal["stop"]
            entry=b["open"]+side*friction
            if side*(entry-stop)>0 and stop>0:
                loss_unit=abs(pnl(1,side,entry,stop-side*friction,spec["quote"]))+2*fee_unit
                q_risk=cash*variant["risk"]/loss_unit
                notional_per_unit=1 if spec["quote"]=="JPY" else entry
                # Entry commission must be paid as well as reserved initial margin.
                q_margin=cash/(notional_per_unit/spec["leverage"]+fee_unit)
                quantity=math.floor(min(q_risk,q_margin)/1000)*1000
                if quantity>0:
                    entry_fee=fee_unit*quantity
                    cash-=entry_fee
                    position={"quantity":quantity,"side":side,"entry":entry,"stop":stop,
                              "target":entry+side*variant["reward_risk"]*abs(entry-stop),
                              "entry_time":t.isoformat(),"known_at":signal["known_at"],"entry_fee":entry_fee,
                              "initial_margin":quantity*notional_per_unit/spec["leverage"],
                              "expiry":t+timedelta(hours=variant["hold_hours"]),
                              "local_day":local.date().isoformat(),"reason":signal["reason"]}
                    used_days.add(local.date().isoformat())
        if position:
            side=position["side"]
            favorable=b["high"] if side>0 else b["low"]
            adverse=b["low"] if side>0 else b["high"]
            worst=min(worst,cash+price_pnl(adverse)-fee_unit*position["quantity"])
            best=max(best,cash+price_pnl(favorable)-fee_unit*position["quantity"])
            stop_hit = adverse <= position["stop"] if side>0 else adverse >= position["stop"]
            target_hit = favorable >= position["target"] if side>0 else favorable <= position["target"]
            gap_stop = b["open"] <= position["stop"] if side>0 else b["open"] >= position["stop"]
            if stop_hit:
                close(b["open"] if gap_stop else position["stop"],t if gap_stop else t+timedelta(hours=1),
                      "stop_first",precision='known_open' if gap_stop else 'intrabar_unknown',bar_start=t)
            elif target_hit:
                close(position["target"],t+timedelta(hours=1),"target",precision='intrabar_unknown',bar_start=t)
            elif i+1==len(bars) or stamp(bars[i+1]["time"])>=finish:
                close(b["close"],t+timedelta(hours=1),"boundary_close",precision='known_close')
        equity=cash+(price_pnl(b["close"]) if position else 0)
        worst=min(worst,cash,equity);best=max(best,cash,equity,before)
        day=(t+timedelta(hours=1)-timedelta(microseconds=1)).date().isoformat()
        daily_close[day]=equity
        daily_worst[day]=min(daily_worst.get(day,float("inf")),worst)
        daily_best[day]=max(daily_best.get(day,float("-inf")),best)
        curve.append({"time":(t+timedelta(hours=1)).isoformat(),"balance":cash,"equity":equity,
                      "worst_equity":worst,"best_equity":best})
    if position:
        raise ValueError("Open boundary position lacks executable exit data")
    dates,returns,worsts,peaks=[],[],[],[]
    previous=capital
    day=begin.date()
    while day<finish.date():
        key=day.isoformat();closing=daily_close.get(key,previous)
        dates.append(key);returns.append(closing/previous-1 if previous > 0 else None)
        worsts.append(daily_worst.get(key,closing));peaks.append(daily_best.get(key,closing))
        previous=closing;day+=timedelta(days=1)
    net=sum(t["net_pnl"] for t in trades)
    for t in trades:
        t["expiry"]=t["expiry"].isoformat()
    return {"variant":variant,"dates":dates,"daily_returns":returns,
            "source_coverage":coverage,"insolvent":any(x <= 0 for x in worsts) or cash <= 0,
            "daily_worst_equity":worsts,"daily_peak_equity":peaks,
            "final_equity":cash,"trades":trades,"completed_episodes":len(trades),"curve":curve,
            "reconciliation_error":cash-capital-net,"missing_exposure_exits":eligibility_gaps,
            "live_qualified":False,"quote_price_proxy":True}
