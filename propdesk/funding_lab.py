"""Personal historical funding-carry research, never executable trading advice.

Separate spot cash and isolated derivative collateral prevent a free-capital
hedge. Rates are realized settlements, not future quotes. Trade-price candles
and prior trade closes are explicitly imperfect proxies for liquidation marks
and settlement marks. Consequently every result remains provisional.
"""
from __future__ import annotations

from collections import defaultdict, deque
from datetime import timedelta
import math

from propdesk import market, research_stats as stats


def variants():
    return [{"id": "static", "lookback": 0, "entry_rate": 0.0,
             "margin_reduction": False}] + [
        {"id": f"persist_{lookback}_{int(threshold * 1e6)}ppm",
         "lookback": lookback, "entry_rate": threshold,
         "margin_reduction": True}
        for lookback in (3, 9, 21) for threshold in (0.0, .00005)]


def validate_events(events, *, allow_unknown_intervals=False):
    if not isinstance(events, list):
        raise ValueError("Funding events must be a list")
    result, previous = [], None
    for event in events:
        stamp = market.utc_datetime(event["time"])
        rate = event["funding_rate"]
        interval = event["funding_interval_hours"]
        if (isinstance(rate, bool) or not isinstance(rate, (int, float))
                or not math.isfinite(rate) or abs(rate) > 1):
            raise ValueError("Invalid funding rate")
        if interval is None and not allow_unknown_intervals:
            raise ValueError("Unknown funding interval requires verified exhaustive pagination receipt")
        if interval is not None and (isinstance(interval, bool) or not isinstance(interval, (int, float)) or not math.isfinite(interval) or interval <= 0):
            raise ValueError("Invalid funding interval")
        if previous is not None:
            if stamp <= previous:
                raise ValueError("Funding events must be unique and ordered")
            # Archive intervals state the just-completed settlement interval.
            # Missing settlements fail; no removal, rate interpolation or zero fill.
            difference = (stamp - previous).total_seconds() / 3600
            if interval is not None and abs(difference - interval) > .001:
                raise ValueError("Funding settlement coverage contains a gap or inconsistent interval")
        mark = event.get("mark_price")
        if mark is not None and (isinstance(mark, bool) or not isinstance(mark, (int, float))
                                 or not math.isfinite(mark) or mark <= 0):
            raise ValueError("Invalid funding mark price")
        result.append({**event, "_stamp": stamp})
        previous = stamp
    return result


def simulate(spot, perpetual, events, variant, start, end, *, capital=50_000.0,
             friction=1.0, positive_funding_multiplier=1.0, allow_unknown_intervals=False):
    """One equal-capital asset bucket; paired fills at next hourly open.

    Each bucket has half capital spot cash, half isolated perpetual collateral.
    A position is long spot/short perpetual with equal fixed base quantity.
    Defensive paired reductions release spot cash without transferring it to
    perpetual collateral. No simultaneous low/high path is asserted.
    """
    if not math.isfinite(capital) or capital <= 0 or friction < 0:
        raise ValueError("Positive capital and nonnegative friction required")
    if not 0 <= positive_funding_multiplier <= 1:
        raise ValueError("Positive-funding stress multiplier must lie in [0,1]")
    if variant not in variants():
        raise ValueError("Variant was not preregistered")
    spot = market.validate_bars(spot, max_bars=100_000)
    perpetual = market.validate_bars(perpetual, max_bars=100_000)
    if [x["time"] for x in spot] != [x["time"] for x in perpetual]:
        raise ValueError("Spot and perpetual timestamps must match exactly")
    for a, b in zip(spot, spot[1:]):
        if market.utc_datetime(b["time"]) - market.utc_datetime(a["time"]) != timedelta(hours=1):
            raise ValueError("Hourly prices contain a gap")
    funding = validate_events(events, allow_unknown_intervals=allow_unknown_intervals)
    begin, finish = market.utc_datetime(start), market.utc_datetime(end)
    selected = [i for i, bar in enumerate(spot) if begin <= market.utc_datetime(bar["time"]) < finish]
    if not selected or market.utc_datetime(spot[selected[0]]["time"]) != begin:
        raise ValueError("Segment lacks exact first bar")
    if market.utc_datetime(spot[selected[-1]]["time"]) + timedelta(hours=1) != finish:
        raise ValueError("Segment lacks exact last closed bar")
    # Full research windows require settlement coverage through both edges.
    if not funding:
        raise ValueError("Funding data is empty")
    first_interval, last_interval = funding[0]["funding_interval_hours"], funding[-1]["funding_interval_hours"]
    if first_interval is not None and funding[0]["_stamp"] > begin + timedelta(hours=first_interval):
        raise ValueError("Funding coverage starts too late")
    if last_interval is not None and funding[-1]["_stamp"] + timedelta(hours=last_interval) < finish:
        raise ValueError("Funding coverage ends too early")
    spot_cash, derivative_cash = capital / 2, capital / 2
    quantity = spot_entry = perp_entry = 0.0
    entered_at = None
    fee_spot, fee_perp = .001 * friction, .0005 * friction
    adverse = .00025 * friction  # 2bp slip + half of full1bp spread.
    fees = financing = price_pnl = liquidation_penalties = 0.0
    liquidation_count = fills = settlements = proxy_settlements = 0
    position_entries = 0
    disabled = False
    history = deque(maxlen=max(21, variant["lookback"]))
    cursor = 0
    while cursor < len(funding) and funding[cursor]["_stamp"] < begin:
        history.append(funding[cursor]["funding_rate"])
        cursor += 1
    daily = {}
    min_equity = peak = capital
    max_drawdown = max_daily_drawdown = 0.0
    day_start_equity = capital
    records = []
    last_day = None

    def close_pair(stamp, spot_price, perp_price, fraction, reason):
        nonlocal quantity, spot_cash, derivative_cash, fees, price_pnl, fills
        nonlocal liquidation_penalties, liquidation_count, disabled
        closed = quantity * fraction
        sell, cover = spot_price * (1 - adverse), perp_price * (1 + adverse)
        costs = closed * (sell * fee_spot + cover * fee_perp)
        pnl = closed * (sell - spot_entry + perp_entry - cover)
        spot_cash += closed * sell * (1 - fee_spot)
        derivative_cash += closed * (perp_entry - cover) - closed * cover * fee_perp
        fees += costs
        price_pnl += pnl
        quantity -= closed
        fills += 2
        if quantity < 1e-12:
            quantity = 0.0
        if reason == "modeled_liquidation":
            penalty = closed * cover * .01
            derivative_cash -= penalty
            liquidation_penalties += penalty
            liquidation_count += 1
            disabled = True
        records.append({"time": stamp, "reason": reason, "quantity": closed,
                        "spot_fill": sell, "perp_fill": cover,
                        "paired_price_pnl": pnl, "fees": costs,
                        "remaining_quantity": quantity})

    for i in selected:
        sb, pb = spot[i], perpetual[i]
        stamp = market.utc_datetime(sb["time"])
        closed_at = stamp + timedelta(hours=1)
        day = stamp.date().isoformat()
        if day != last_day:
            day_start_equity = daily[last_day]["equity"] if last_day else capital
            last_day = day
        # A collateral gap at open has priority over planned exits.
        if quantity and derivative_cash + quantity * (perp_entry - pb["open"]) <= .005 * quantity * pb["open"]:
            close_pair(sb["time"], sb["open"], pb["open"], 1, "modeled_liquidation")
        lookback = variant["lookback"]
        realized_mean = sum(list(history)[-lookback:]) / lookback if lookback and len(history) >= lookback else None
        enter = lookback == 0 or (realized_mean is not None and realized_mean > variant["entry_rate"])
        exit_signal = lookback > 0 and realized_mean is not None and realized_mean <= 0
        if quantity and exit_signal:
            close_pair(sb["time"], sb["open"], pb["open"], 1, "realized_funding_nonpositive")
        elif quantity and variant["margin_reduction"] and i > 0:
            prior = perpetual[i - 1]["close"]
            if derivative_cash + quantity * (perp_entry - prior) < .5 * quantity * prior:
                close_pair(sb["time"], sb["open"], pb["open"], .5, "prior_close_collateral_buffer")
        elif not quantity and enter and not disabled and i > 0 and i != selected[-1]:
            # Historical closed bar required even for constant benchmark.
            buy, sell = sb["open"] * (1 + adverse), pb["open"] * (1 - adverse)
            budget = min(capital / 2, spot_cash)
            affordable = min(budget / (buy * (1 + fee_spot)),
                             max(0, derivative_cash) / (sell * (1 + fee_perp)))
            quantity = math.floor(affordable * 1e6) / 1e6
            if quantity > 0:
                spot_entry, perp_entry, entered_at = buy, sell, stamp
                costs = quantity * (buy * fee_spot + sell * fee_perp)
                spot_cash -= quantity * buy * (1 + fee_spot)
                derivative_cash -= quantity * sell * fee_perp
                fees += costs
                fills += 2
                position_entries += 1
                records.append({"time": sb["time"], "reason": "paired_entry",
                                "quantity": quantity, "spot_fill": buy,
                                "perp_fill": sell, "fees": costs,
                                "known_rate_mean": realized_mean})
        before_funding_worst = spot_cash + derivative_cash + quantity * (sb["low"] + perp_entry - pb["high"])
        # Unknown high/settlement ordering cannot rescue collateral with a
        # later positive receipt. Liquidate conservatively before all intrabar
        # receipts if the pre-settlement collateral fails the high envelope.
        if quantity and derivative_cash + quantity * (perp_entry - pb["high"]) <= .005 * quantity * pb["high"]:
            close_pair(sb["time"], sb["low"], pb["high"], 1, "modeled_liquidation")
        while cursor < len(funding) and funding[cursor]["_stamp"] < closed_at:
            event = funding[cursor]
            # Events at the opening timestamp occur only for older positions;
            # same-time opens/exits receive no assumed settlement entitlement.
            if quantity and entered_at + timedelta(minutes=1) < event["_stamp"]:
                mark = event.get("mark_price")
                if mark is None:
                    if i == 0:
                        raise ValueError("No causal mark proxy exists before first candle")
                    mark = perpetual[i - 1]["close"]
                    proxy_settlements += 1
                rate = event["funding_rate"]
                payment = quantity * mark * rate * (positive_funding_multiplier if rate > 0 else 1)
                derivative_cash += payment
                financing += payment
                settlements += 1
            history.append(event["funding_rate"])
            cursor += 1
        # After negative funding another high-envelope check is conservative.
        # No funding can be booked after the paired liquidation above.
        worst = min(before_funding_worst, spot_cash + derivative_cash + quantity * (sb["low"] + perp_entry - pb["high"]))
        peak = max(peak, spot_cash + derivative_cash + quantity * (sb["open"] + perp_entry - pb["open"]))
        min_equity = min(min_equity, worst)
        max_drawdown = max(max_drawdown, 1 - worst / peak)
        max_daily_drawdown = max(max_daily_drawdown, 1 - worst / day_start_equity)
        if quantity and derivative_cash + quantity * (perp_entry - pb["high"]) <= .005 * quantity * pb["high"]:
            close_pair(sb["time"], sb["low"], pb["high"], 1, "modeled_liquidation")
        if i == selected[-1] and quantity:
            close_pair(closed_at.isoformat().replace("+00:00", "Z"), sb["close"], pb["close"], 1, "hypothetical_sample_boundary")
        equity = spot_cash + derivative_cash + quantity * (sb["close"] + perp_entry - pb["close"])
        if equity <= 0 or not math.isfinite(equity):
            raise ValueError("Account insolvency; cannot present finite return evidence")
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, 1 - equity / peak)
        daily[day] = {"equity": equity, "worst_equity": min(worst, equity, daily.get(day, {}).get("worst_equity", math.inf)),
                      "maximum_close_equity": max(equity, daily.get(day, {}).get("maximum_close_equity", 0)),
                      "spot_close": sb["close"], "perp_close": pb["close"],
                      "residual_base_delta": 0.0, "isolated_collateral": derivative_cash,
                      "spot_cash": spot_cash}
    dates = list(daily)
    equities = [daily[day]["equity"] for day in dates]
    returns = [value / (equities[i - 1] if i else capital) - 1 for i, value in enumerate(equities)]
    spot_returns = [daily[day]["spot_close"] / (daily[dates[i - 1]]["spot_close"] if i else spot[selected[0]]["open"]) - 1
                    for i, day in enumerate(dates)]
    mean_x, mean_y = sum(spot_returns) / len(dates), sum(returns) / len(dates)
    variance = sum((x - mean_x) ** 2 for x in spot_returns)
    beta = sum((x - mean_x) * (y - mean_y) for x, y in zip(spot_returns, returns)) / variance if variance else None
    return {"variant": variant, "start": start, "end": end, "capital": capital,
            "dates": dates, "daily_equity": equities, "daily_returns": returns,
            "daily_rows": daily, "records": records, "return_pct": (equities[-1] / capital - 1) * 100,
            "max_drawdown_pct": max_drawdown * 100, "max_daily_drawdown_pct": max_daily_drawdown * 100,
            "funding_received": financing, "paired_price_pnl": price_pnl,
            "fees": fees, "liquidation_penalties": liquidation_penalties,
            "liquidations": liquidation_count, "settlements": settlements,
            "proxy_mark_settlements": proxy_settlements, "fills": fills, "entries": position_entries,
            "unknown_funding_interval_events": sum(event["funding_interval_hours"] is None for event in funding),
            "annualized_return_pct": ((equities[-1] / capital) ** (365 / len(dates)) - 1) * 100,
            "market_beta": beta, "daily_spot_return_correlation": stats.pearson_correlation(spot_returns, returns),
            "zero_base_delta_is_not_risk_free": True, "provisional_price_marks": True,
            "reconciliation_error": equities[-1] - capital - (financing + price_pnl - fees - liquidation_penalties)}


def portfolio(results, *, samples=2000):
    if not results or any(row["dates"] != results[0]["dates"] for row in results):
        raise ValueError("Asset dates must match exactly")
    dates = results[0]["dates"]
    capital = sum(row["capital"] for row in results)
    equities = [sum(row["daily_equity"][i] for row in results) for i in range(len(dates))]
    returns = [value / (equities[i - 1] if i else capital) - 1 for i, value in enumerate(equities)]
    peak, drawdown, daily_drawdown = capital, 0.0, 0.0
    for i, day in enumerate(dates):
        worst = sum(row["daily_rows"][day]["worst_equity"] for row in results)
        # Sum of separate daily maxima is an intentionally conservative envelope,
        # not a simultaneous path or a claim all maxima preceded the worst mark.
        peak = max(peak, sum(row["daily_rows"][day]["maximum_close_equity"] for row in results))
        drawdown = max(drawdown, 1 - worst / peak)
        daily_drawdown = max(daily_drawdown, 1 - worst / (equities[i - 1] if i else capital))
        peak = max(peak, equities[i])
    return {"dates": dates, "daily_equity": equities, "daily_returns": returns,
            "return_pct": (equities[-1] / capital - 1) * 100,
            "annualized_return_pct": ((equities[-1] / capital) ** (365 / len(dates)) - 1) * 100,
            "max_drawdown_pct": drawdown * 100, "max_daily_drawdown_pct": daily_drawdown * 100,
            "settlements": sum(row["settlements"] for row in results),
            "liquidations": sum(row["liquidations"] for row in results),
            "funding_received": sum(row["funding_received"] for row in results),
            "fees": sum(row["fees"] for row in results),
            "paired_price_pnl": sum(row["paired_price_pnl"] for row in results),
            "fills": sum(row["fills"] for row in results),
            "block_mean_ci99": stats.bootstrap_mean_ci(returns, confidence=.99, samples=samples, block_length=7, seed=20261002) if len(returns) >= 7 else None,
            "monthly": stats.monthly_return_concentration(dates, returns),
            "assets": results, "live_qualified": False, "prop_qualified": False,
            "limitations": "Trade-close funding mark and OHLC liquidation proxies; nonsimultaneous worst envelopes; actual account filters, mark risk, counterparty/default/outages not validated."}
