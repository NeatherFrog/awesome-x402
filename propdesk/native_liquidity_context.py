"""Frozen clock-context filters over the immutable native FVG executor.

All price features, setups, fills, funding and risk accounting belong to the
unchanged liquidity_native engine. This module only uses already known clocks.
"""
from __future__ import annotations

from bisect import bisect_left
from functools import lru_cache
import hashlib
from io import BytesIO
from itertools import product
from pathlib import Path
from zoneinfo import ZoneInfo

from . import liquidity_native as parent, market

TZ_ROOT = Path(__file__).resolve().parent / "tzdata"
TZIF_HASHES = {
    "America/New_York": "e9ed07d7bee0c76a9d442d091ef1f01668fee7c4f26014c0a868b19fe6c18a95",
    "Europe/London": "c85495070dca42687df6a1c3ee780a27cbcb82f1844750ea6f642833a44d29b4",
}
CONTEXTS = {"ny_lunch": {"zone": "America/New_York", "sweep_start": 11 * 60,
                          "sweep_end_exclusive": 14 * 60, "confirm_end_exclusive": 17 * 60},
            "london": {"zone": "Europe/London", "sweep_start": 7 * 60,
                       "sweep_end_exclusive": 10 * 60, "confirm_end_exclusive": 13 * 60}}


def grid():
    variants = []
    registered = parent.grid()
    for minutes, liquidity, body, context, risk in product((15, 60), (24, 72), (.6, 1), CONTEXTS, (.0025, .005, .01)):
        base = next(item for item in registered if item["minutes"] == minutes and item["liquidity"] == liquidity
                    and item["body_atr"] == body and item["reward_risk"] == 2.5 and item["expiry"] == 4
                    and item["trend_context"] is False and item["risk_fraction"] == risk)
        variants.append({"id": f"context_{context}_{minutes}_{liquidity}_{body:g}_r{risk:g}",
                         "context": context, "parent_variant": dict(base), "risk_fraction": risk})
    return variants


@lru_cache(maxsize=2)
def pinned_timezone(key):
    if key not in TZIF_HASHES:
        raise ValueError("Unregistered context timezone")
    raw = (TZ_ROOT / key).read_bytes()
    if hashlib.sha256(raw).hexdigest() != TZIF_HASHES[key]:
        raise ValueError("Pinned IANA TZif fingerprint mismatch")
    return ZoneInfo.from_file(BytesIO(raw), key=key)


def accepts_event(event, context):
    """Filter known sweep CLOSE and signal CLOSE, without prices or future bars."""
    if context not in CONTEXTS:
        raise ValueError("Unregistered time context")
    rule = CONTEXTS[context]
    sweep, signal = market.utc_datetime(event["sweep_time"]), market.utc_datetime(event["signal_time"])
    if sweep > signal:
        raise ValueError("A setup cannot know a future sweep")
    zone = pinned_timezone(rule["zone"])
    sweep, signal = sweep.astimezone(zone), signal.astimezone(zone)
    sweep_minutes = sweep.hour * 60 + sweep.minute + sweep.second / 60 + sweep.microsecond / 60_000_000
    signal_minutes = signal.hour * 60 + signal.minute + signal.second / 60 + signal.microsecond / 60_000_000
    return (sweep.weekday() < 5 and signal.weekday() < 5 and sweep.date() == signal.date()
            and rule["sweep_start"] <= sweep_minutes < rule["sweep_end_exclusive"]
            and signal_minutes < rule["confirm_end_exclusive"])


def filter_events(events, context):
    result = {}
    for epoch, assets in events.items():
        accepted = {}
        for symbol, event in assets.items():
            signal = market.utc_datetime(event["signal_time"])
            if int(signal.timestamp()) != epoch or signal.microsecond:
                raise ValueError("Event must be keyed by its known confirmation close")
            if accepts_event(event, context):
                accepted[symbol] = {**event, "clock_context": context,
                                    "reason": event["reason"] + ";known_sweep_and_confirmation_clock_context=" + context}
        if accepted:
            result[epoch] = accepted
    return result


def setups(features, variant):
    if variant not in grid():
        raise ValueError("Unregistered liquidity context variant")
    return filter_events(parent.setups(features, variant["parent_variant"]), variant["context"])


class PrefixFeatures(parent.Features):
    """Physically exclude post-window prices and funding before generating setups."""
    def __init__(self, full, end_date):
        if not isinstance(full, parent.Features):
            raise ValueError("Validated native parent Features required")
        finish = market.utc_datetime(end_date + "T00:00:00Z")
        index = bisect_left(full.stamps, finish)
        if not index or full.stamps[index - 1].timestamp() + parent.SECONDS != finish.timestamp():
            raise ValueError("Exact prefix calendar end required")
        self.bars = {symbol: full.bars[symbol][:index] for symbol in parent.SYMBOLS}
        self.times, self.stamps, self.cache = full.times[:index], full.stamps[:index], {}
        # The parent conservatively debits settlement exactly at the sample
        # boundary; preserve that event, while excluding all later outcomes.
        self.funding = {symbol: {epoch: [event for event in events if event["_stamp"] <= finish]
                                  for epoch, events in full.funding[symbol].items()
                                  if epoch <= int(finish.timestamp())}
                        for symbol in parent.SYMBOLS}
