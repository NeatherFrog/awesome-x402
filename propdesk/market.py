"""Canonical OHLCV ingestion and explicitly synthetic demonstration data.

Timestamps identify bar *opening* times and must be timezone-aware UTC; every
supplied bar must already be fully closed. The research engine neither
downloads quotes nor silently sorts malformed input.
"""

from __future__ import annotations

import csv
import hashlib
import io
import math
import random
import re
from datetime import datetime, timedelta, timezone
from numbers import Real

MAX_BARS = 30_000
MAX_CSV_BYTES = 12 * 1024 * 1024
_UTC_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)$")

SYMBOL_SPECS = {
    "EURUSD": {"name": "EUR / USD", "asset_class": "forex", "base_price": 1.085, "volatility": 0.0012, "decimals": 6},
    "XAUUSD": {"name": "Gold / USD", "asset_class": "metal", "base_price": 2300.0, "volatility": 0.0033, "decimals": 3},
    "NAS100": {"name": "Nasdaq 100 CFD", "asset_class": "index", "base_price": 18_000.0, "volatility": 0.004, "decimals": 3},
    "BTCUSD": {"name": "Bitcoin / USD", "asset_class": "crypto", "base_price": 65_000.0, "volatility": 0.007, "decimals": 3},
}


def utc_datetime(value: str) -> datetime:
    """Parse only explicit UTC ISO-8601 timestamps, never local-time guesses."""
    if not isinstance(value, str) or not _UTC_PATTERN.fullmatch(value):
        raise ValueError("time must be an ISO UTC timestamp, e.g. 2025-01-01T00:00:00Z")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"invalid UTC timestamp: {value}") from exc
    return parsed


def _canonical_time(parsed: datetime) -> str:
    return parsed.isoformat(timespec="microseconds" if parsed.microsecond else "seconds").replace("+00:00", "Z")


def _number(value, name: str, row: int) -> float:
    if isinstance(value, bool) or not isinstance(value, (str, Real)):
        raise ValueError(f"row {row}: {name} must be a finite number")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"row {row}: {name} must be a finite number") from exc
    if not math.isfinite(number):
        raise ValueError(f"row {row}: {name} must be a finite number")
    return number


def validate_bars(bars, *, max_bars: int = MAX_BARS) -> list[dict]:
    """Validate and copy bars without changing their chronological order."""
    if not isinstance(bars, (list, tuple)) or not bars:
        raise ValueError("OHLCV data must contain at least one bar")
    if len(bars) > max_bars:
        raise ValueError(f"at most {max_bars:,} bars are supported")
    normalized: list[dict] = []
    previous = None
    for index, bar in enumerate(bars, 1):
        if not isinstance(bar, dict):
            raise ValueError(f"row {index}: expected an OHLCV object")
        missing = [key for key in ("time", "open", "high", "low", "close", "volume") if key not in bar]
        if missing:
            raise ValueError(f"row {index}: missing {', '.join(missing)}")
        try:
            stamp = utc_datetime(bar["time"])
        except ValueError as exc:
            raise ValueError(f"row {index}: {exc}") from exc
        if previous is not None and stamp <= previous:
            raise ValueError(f"row {index}: timestamps must be ascending and unique")
        previous = stamp
        values = {key: _number(bar[key], key, index) for key in ("open", "high", "low", "close", "volume")}
        if any(values[key] <= 0 for key in ("open", "high", "low", "close")):
            raise ValueError(f"row {index}: OHLC prices must be positive")
        if values["volume"] < 0:
            raise ValueError(f"row {index}: volume cannot be negative")
        if values["high"] < max(values["open"], values["close"]) or values["low"] > min(values["open"], values["close"]) or values["high"] < values["low"]:
            raise ValueError(f"row {index}: invalid OHLC high/low envelope")
        normalized.append({"time": _canonical_time(stamp), **values})
    return normalized


def parse_csv(text: str) -> list[dict]:
    """Import time,open,high,low,close,volume CSV; timestamp aliases time.

    Extra explicitly named columns are harmless. Missing columns, malformed
    row widths, ambiguous dates and duplicated timestamps fail with row context.
    """
    if not isinstance(text, str):
        raise ValueError("CSV input must be text")
    if len(text.encode("utf-8")) > MAX_CSV_BYTES:
        raise ValueError("CSV exceeds the 12 MiB limit")
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")), strict=True)
    try:
        if not reader.fieldnames:
            raise ValueError("CSV requires a header")
        headers = [name.strip().lower() for name in reader.fieldnames]
        headers = ["time" if name == "timestamp" else name for name in headers]
        if any(not key for key in headers) or len(set(headers)) != len(headers):
            raise ValueError("CSV column names must be nonempty and unique")
        required = {"time", "open", "high", "low", "close", "volume"}
        if not required.issubset(headers):
            raise ValueError("CSV requires columns: time,open,high,low,close,volume")
        reader.fieldnames = headers
        bars = []
        for row in reader:
            if None in row or any(row[key] is None for key in required):
                raise ValueError(f"CSV line {reader.line_num}: inconsistent column count")
            bars.append({key: row[key].strip() for key in required})
            if len(bars) > MAX_BARS:
                raise ValueError(f"at most {MAX_BARS:,} bars are supported")
    except csv.Error as exc:
        raise ValueError(f"malformed CSV near line {reader.line_num}: {exc}") from exc
    return validate_bars(bars)


def to_csv(bars: list[dict]) -> str:
    """Write canonical CSV suitable for a round trip through parse_csv."""
    canonical = validate_bars(bars)
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=("time", "open", "high", "low", "close", "volume"), lineterminator="\n")
    writer.writeheader()
    writer.writerows(canonical)
    return output.getvalue()


def data_fingerprint(bars: list[dict]) -> str:
    """Stable content digest for experiment provenance, independent of symbol."""
    digest = hashlib.sha256()
    for bar in bars:
        digest.update((bar["time"] + "," + ",".join(format(bar[key], ".17g") for key in ("open", "high", "low", "close", "volume")) + "\n").encode())
    return digest.hexdigest()


def demo_bars(symbol: str = "EURUSD", count: int = 1200, seed: int = 42) -> list[dict]:
    """Generate repeatable DEMO hourly bars, never purported market history.

    Alternating latent trends, ranges, shocks and changing volatility make the
    interface and backtest paths testable. Their returns provide no financial
    evidence. Weekends are skipped for non-crypto instruments; there are no
    exchange calendars or claims that these are tradable sessions.
    """
    if not isinstance(symbol, str) or symbol.upper() not in SYMBOL_SPECS:
        raise ValueError("demo symbol must be EURUSD, XAUUSD, NAS100 or BTCUSD")
    if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= MAX_BARS:
        raise ValueError(f"count must be an integer between 1 and {MAX_BARS}")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("seed must be an integer")
    symbol = symbol.upper()
    spec = SYMBOL_SPECS[symbol]
    rng = random.Random(seed + int(hashlib.sha256(symbol.encode()).hexdigest()[:8], 16))
    price = spec["base_price"]
    anchor = price
    volatility = spec["volatility"]
    stamp = datetime(2025, 1, 6, tzinfo=timezone.utc)
    bars = []
    for index in range(count):
        while symbol != "BTCUSD" and stamp.weekday() >= 5:
            stamp += timedelta(hours=1)
        regime = (index // 150) % 6
        phase = index % 150
        if phase == 0:
            anchor = price
        if regime in (0, 3):
            drift = (1 if regime == 0 else -1) * volatility * 0.15
            shock = rng.gauss(drift, volatility * 0.8)
        elif regime in (1, 4):
            # A bounded stochastic range, not an engineered profitable strategy.
            shock = 0.055 * math.log(anchor / price) + rng.gauss(0, volatility * (0.75 if regime == 1 else 1.0))
        else:
            shock = rng.gauss(0, volatility * (1.8 if regime == 2 else 1.25))
        gap = rng.gauss(0, volatility * 0.08)
        if index and index % 173 == 0:
            gap += rng.choice((-1, 1)) * volatility * 2.0
        opening = price * math.exp(gap)
        closing = opening * math.exp(max(-0.12, min(0.12, shock)))
        wick = abs(rng.gauss(volatility * 0.55, volatility * 0.22))
        high = max(opening, closing) * math.exp(wick)
        low = min(opening, closing) * math.exp(-wick * rng.uniform(0.7, 1.3))
        decimals = spec["decimals"]
        bars.append({"time": _canonical_time(stamp), "open": round(opening, decimals), "high": round(high, decimals), "low": round(low, decimals), "close": round(closing, decimals), "volume": float(round(rng.uniform(500, 6000) * (1.8 if regime == 2 else 1.0)))})
        price = closing
        stamp += timedelta(hours=1)
    return validate_bars(bars)
