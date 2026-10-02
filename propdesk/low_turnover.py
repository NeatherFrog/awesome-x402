"""Causal, cash-only, low-turnover two-asset research; no order integration.

Calendar-month momentum and portfolio volatility targeting are deliberately
different from the prior hourly single-asset stop engine. Source ideas from
time-series momentum literature do not establish this adaptation's profitability.
"""
from __future__ import annotations

from bisect import bisect_right
from calendar import monthrange
from datetime import timedelta
import math

from propdesk import market, research_lab as lab

RULES = {
    "relative_rotation": "On fixed weekly/monthly dates hold the asset with the highest positive trailing1/3calendar-month return; otherwise cash. Inverse asset-vol exposure targets8/12% annualized, cash capped.",
    "inverse_vol_trend": "On fixed weekly/monthly dates hold each asset with positive trailing1/3calendar-month return in inverse30day-volatility proportions. Portfolio trailing covariance targets8/12% annualized, cash capped.",
    "channel_portfolio": "Per-asset20/60day close breakout above prior highs activates holding; prior10/30day lows deactivate. Weekly/monthly rebalance inversevol active assets to8/12% annualized with covariance, cash capped.",
    "btc_regime_rotation": "On fixed weekly/monthly dates BTC close>SMA60days and positive20dayreturn permit highest-positive1/3calendar-month relative-strength asset; otherwise cash. Allocation targets8/12% annualized using chosen asset30dayvol.",
}


def grid():
    import itertools
    result = []
    for family in RULES:
        periodkey = "channel_days" if family == "channel_portfolio" else "momentum_months"
        periods = [20, 60] if family == "channel_portfolio" else [1, 3]
        for resolution, period, cadence, target in itertools.product([4, 24], periods, ["weekly", "monthly"], [.08, .12]):
            variant = {"family": family, "resolution_hours": resolution, periodkey: period,
                       "cadence": cadence, "annual_vol_target": target,
                       "maximum_gross": 1.0, "volatility_days": 30}
            variant["id"] = family+"-"+lab.digest(variant)[:12]
            result.append(variant)
    return result


def aggregate(hourly, hours):
    if hours not in (4, 24):
        raise ValueError("Only frozen4h/daily causal aggregation supported")
    normalized = market.validate_bars(hourly, max_bars=100_000)
    if len(normalized) % hours:
        raise ValueError("Only complete aggregate candles supported")
    for left, right in zip(normalized, normalized[1:]):
        if market.utc_datetime(right["time"])-market.utc_datetime(left["time"]) != timedelta(hours=1):
            raise ValueError("Missing hourly observations between aggregate groups; no imputation")
    out = []
    for index in range(0, len(normalized), hours):
        rows = normalized[index:index+hours]
        opening = market.utc_datetime(rows[0]["time"])
        if opening.hour % hours or opening.minute or opening.second:
            raise ValueError("UTC aggregate alignment required")
        for offset, row in enumerate(rows):
            if market.utc_datetime(row["time"]) != opening+timedelta(hours=offset):
                raise ValueError("Missing hourly observations; no imputation")
        out.append({"time": rows[0]["time"], "open": rows[0]["open"], "high": max(r["high"] for r in rows),
                    "low": min(r["low"] for r in rows), "close": rows[-1]["close"],
                    "volume": sum(r["volume"] for r in rows)})
    return out


def months_back(stamp, months):
    count = stamp.year*12+stamp.month-1-months
    year, month = divmod(count, 12)
    month += 1
    return stamp.replace(year=year, month=month, day=min(stamp.day, monthrange(year, month)[1]))


class Features:
    def __init__(self, datasets, hours):
        self.hours = hours
        self.bars = {s: aggregate(rows, hours) for s, rows in datasets.items()}
        self.symbols = sorted(self.bars)
        if self.symbols != ["BTCUSDT", "ETHUSDT"]:
            raise ValueError("Fixed two-asset spot universe required")
        self.times = [row["time"] for row in self.bars[self.symbols[0]]]
        if self.times != [row["time"] for row in self.bars[self.symbols[1]]]:
            raise ValueError("Exact synchronized aggregate timestamps required")
        self.closed_at = [market.utc_datetime(t)+timedelta(hours=hours) for t in self.times]
        self.close = {s: [b["close"] for b in rows] for s, rows in self.bars.items()}
        self.high = {s: [b["high"] for b in rows] for s, rows in self.bars.items()}
        self.low = {s: [b["low"] for b in rows] for s, rows in self.bars.items()}
        self.returns = {s: [0.0]+[math.log(c[i]/c[i-1]) for i in range(1, len(c))] for s, c in self.close.items()}
        self.cache = {}

    def momentum(self, symbol, months):
        key = symbol, "calendar", months
        if key not in self.cache:
            out = []
            c = self.close[symbol]
            for j, time in enumerate(self.closed_at):
                before = bisect_right(self.closed_at, months_back(time, months))-1
                out.append(c[j]/c[before]-1 if before >= 0 else None)
            self.cache[key] = out
        return self.cache[key]

    def rolling(self, symbol, kind, days):
        key = symbol, kind, days
        if key not in self.cache:
            n = days*24//self.hours
            source = self.returns[symbol] if kind == "vol" else self.high[symbol] if kind == "high" else self.low[symbol] if kind == "low" else self.close[symbol]
            if kind in ("high", "low"):
                result = lab.extrema(source, n, maximum=kind == "high")
            else:
                result = lab.rolling(source, n, mode="std" if kind == "vol" else "mean")
                if kind == "vol":
                    result = [x*math.sqrt(365*24/self.hours) if x is not None else None for x in result]
            self.cache[key] = result
        return self.cache[key]

    def correlation(self, j, days=30):
        key = "covariance_correlation", days
        if key not in self.cache:
            n = days*24//self.hours
            left, right = (self.returns[s] for s in self.symbols)
            out = [None]*len(left)
            # Rolling O(n) sums avoid repeatedly visiting30days per variant.
            sums = [0.0]*5
            for i, (a, b) in enumerate(zip(left, right)):
                values = [a, b, a*a, b*b, a*b]
                sums = [x+y for x, y in zip(sums, values)]
                if i >= n:
                    a, b = left[i-n], right[i-n]
                    sums = [x-y for x, y in zip(sums, [a, b, a*a, b*b, a*b])]
                if i >= n-1:
                    ma, mb = sums[0]/n, sums[1]/n
                    va, vb = max(0, sums[2]/n-ma*ma), max(0, sums[3]/n-mb*mb)
                    out[i] = max(-1, min(1, (sums[4]/n-ma*mb)/math.sqrt(va*vb))) if va*vb > 0 else 0
            self.cache[key] = out
        return self.cache[key][j]


def target_weights(features, variant):
    result = [None]*len(features.times)
    hours, symbols = features.hours, features.symbols
    family = variant["family"]
    vols = {s: features.rolling(s, "vol", 30) for s in symbols}
    if family == "channel_portfolio":
        channel = variant["channel_days"]
        highs = {s: features.rolling(s, "high", channel) for s in symbols}
        lows = {s: features.rolling(s, "low", channel//2) for s in symbols}
        active = {s: False for s in symbols}
    else:
        moms = {s: features.momentum(s, variant["momentum_months"]) for s in symbols}
    btcavg = features.rolling("BTCUSDT", "mean", 60) if family == "btc_regime_rotation" else None
    for i in range(1, len(result)):
        j = i-1
        if family == "channel_portfolio" and j:
            for symbol in symbols:
                if highs[symbol][j-1] is None or lows[symbol][j-1] is None:
                    continue
                c = features.close[symbol][j]
                if c > highs[symbol][j-1]:
                    active[symbol] = True
                elif c < lows[symbol][j-1]:
                    active[symbol] = False
        stamp = market.utc_datetime(features.times[i])
        due = stamp.hour == 0 and (stamp.weekday() == 0 if variant["cadence"] == "weekly" else stamp.day == 1)
        if not due:
            continue
        if any(vols[s][j] is None or vols[s][j] <= 0 for s in symbols):
            continue
        if family == "channel_portfolio":
            eligible = [s for s in symbols if active[s]]
        else:
            if any(moms[s][j] is None for s in symbols):
                continue
            eligible = [s for s in symbols if moms[s][j] > 0]
            if family == "btc_regime_rotation":
                before = j-20*24//hours
                if btcavg[j] is None or before < 0 or features.close["BTCUSDT"][j] <= btcavg[j] or features.close["BTCUSDT"][j] <= features.close["BTCUSDT"][before]:
                    eligible = []
            if family in ("relative_rotation", "btc_regime_rotation") and eligible:
                eligible = [sorted(eligible, key=lambda s: (-moms[s][j], s))[0]]
        weights = {s: 0.0 for s in symbols}
        if eligible:
            inv = {s: 1/vols[s][j] for s in eligible}
            total = sum(inv.values())
            raw = {s: inv[s]/total for s in eligible}
            if len(eligible) == 1:
                portfolio_vol = vols[eligible[0]][j]
            else:
                a, b = eligible
                correlation = features.correlation(j) or 0
                portfolio_vol = math.sqrt(max(1e-12, raw[a]**2*vols[a][j]**2+raw[b]**2*vols[b][j]**2
                                              +2*raw[a]*raw[b]*vols[a][j]*vols[b][j]*correlation))
            scale = min(variant["maximum_gross"], variant["annual_vol_target"]/portfolio_vol)
            weights.update({s: raw[s]*scale for s in eligible})
        result[i] = {"weights": weights, "signal_time": features.times[j],
                     "asof": features.closed_at[j].isoformat().replace("+00:00", "Z")}
    return result


def simulate(features, observations, start_date, end_date, *, cost_multiplier=1, initial=100_000):
    """Sell-before-buy periodic cash-only rebalance, conservatively costed.

    This is an allocation strategy with modeled rebalance orders, not individual
    stopped setup trades. Closed position episodes are not count-inflated by
    counting every rebalance as a statistically independent trade.
    """
    indices = [i for i, t in enumerate(features.times) if start_date <= t[:10] < end_date]
    if not indices:
        raise ValueError("Empty fixed research window")
    if len(observations) != len(features.times):
        raise ValueError("One observation per aggregate bar required")
    if cost_multiplier <= 0 or initial <= 0:
        raise ValueError("Positive friction multiplier required")
    fee, adverse, step = .001*cost_multiplier, .00025*cost_multiplier, .000001
    cash = float(initial)
    qty = {s: 0.0 for s in features.symbols}
    lots, episodes, fills, curve = {}, [], [], []
    fees = adverse_cost = turnover = 0.0

    def sell(symbol, quantity, rawprice, stamp, reason):
        nonlocal cash, fees, adverse_cost, turnover
        fill = rawprice*(1-adverse)
        charge = quantity*fill*fee
        proceeds = quantity*fill-charge
        cash += proceeds
        qty[symbol] = max(0, qty[symbol]-quantity)
        fees += charge
        adverse_cost += quantity*(rawprice-fill)
        turnover += quantity*fill
        fills.append({"time": stamp, "symbol": symbol, "side": "sell", "quantity": quantity, "price": fill, "fee": charge, "reason": reason})
        if symbol in lots:
            lots[symbol]["net_cashflow"] += proceeds
            if qty[symbol] < step/2:
                episodes.append({"symbol": symbol, **lots.pop(symbol), "exit_time": stamp,
                                 "boundary_liquidation": reason == "sample_boundary"})

    for i in indices:
        bars = {s: features.bars[s][i] for s in features.symbols}
        stamp = features.times[i]
        opening = cash+sum(qty[s]*bars[s]["open"] for s in features.symbols)
        signal = observations[i]
        if signal and i != indices[-1]:
            weights = signal["weights"]
            if any(w < 0 for w in weights.values()) or sum(weights.values()) > 1+1e-12:
                raise ValueError("Cash-only nonnegative gross weights required")
            targets = {s: math.floor((opening*weights[s]/bars[s]["open"])/step)*step for s in features.symbols}
            for symbol in features.symbols:
                if qty[symbol] > targets[symbol]:
                    sell(symbol, qty[symbol]-targets[symbol], bars[symbol]["open"], stamp, "rebalance")
            requested = {s: max(0, targets[s]-qty[s]) for s in features.symbols}
            desired_cash = sum(requested[s]*bars[s]["open"]*(1+adverse)*(1+fee) for s in features.symbols)
            scale = min(1.0, cash/desired_cash) if desired_cash else 1.0
            for symbol in features.symbols:
                quantity = math.floor(requested[symbol]*scale/step)*step
                if quantity <= 0:
                    continue
                fill = bars[symbol]["open"]*(1+adverse)
                charge = quantity*fill*fee
                cost = quantity*fill+charge
                if cost > cash+1e-8:
                    raise ValueError("Rebalance exhausted available cash")
                lots.setdefault(symbol, {"entry_time": stamp, "net_cashflow": 0.0})
                lots[symbol]["net_cashflow"] -= cost
                cash -= cost
                qty[symbol] += quantity
                fees += charge
                adverse_cost += quantity*(fill-bars[symbol]["open"])
                turnover += quantity*fill
                fills.append({"time": stamp, "signal_time": signal["signal_time"], "asof": signal["asof"],
                              "symbol": symbol, "side": "buy", "quantity": quantity, "price": fill, "fee": charge, "reason": "rebalance"})
        worst = min(opening, cash+sum(qty[s]*bars[s]["low"] for s in features.symbols))
        if i == indices[-1]:
            close_time = (market.utc_datetime(stamp)+timedelta(hours=features.hours)).isoformat().replace("+00:00", "Z")
            for symbol in features.symbols:
                if qty[symbol] > 0:
                    sell(symbol, qty[symbol], bars[symbol]["close"], close_time, "sample_boundary")
        notional = sum(qty[s]*bars[s]["close"] for s in features.symbols)
        equity = cash+notional
        curve.append({"time": stamp, "equity": equity, "opening_equity": opening,
                      "worst_equity": min(worst, equity), "notional": notional})
    m = lab.metrics(curve, [], initial)
    gains = sum(max(e["net_cashflow"], 0) for e in episodes)
    losses = sum(max(-e["net_cashflow"], 0) for e in episodes)
    m.update(fees_paid=fees, adverse_fill_cost=adverse_cost, turnover_notional=turnover,
             rebalance_fill_count=len(fills), closed_position_episodes=len(episodes),
             completed_episode_pnl=sum(e["net_cashflow"] for e in episodes),
             trade_count=len(episodes), interval_hours=features.hours,
             profit_factor=gains/losses if losses else None, gross_wins=gains,
             gross_losses=losses, wins=sum(e["net_cashflow"] > 0 for e in episodes),
             marked_hours_in_position=m["marked_hours_in_position"]*features.hours)
    return {"metrics": m, "daily_returns": lab.daily_returns(curve, initial),
            "equity_curve": curve, "fills": fills, "episodes": episodes,
            "start": curve[0]["time"], "end": curve[-1]["time"]}
