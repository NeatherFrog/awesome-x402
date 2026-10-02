"""Separate official USD-M calculated-mark history; never execution quotes."""
from __future__ import annotations

import calendar
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .exchange import ExchangeDataError
from .funding_data import _finite, _integer, _request, _rows
from .market import validate_bars

SYMBOLS = ("BTCUSDT", "ETHUSDT")
HEADER = ("open_time", "open", "high", "low", "close", "volume", "close_time",
          "quote_volume", "count", "taker_buy_volume", "taker_buy_quote_volume", "ignore")
BASE = "https://data.binance.vision/data/futures/um"


def archive_urls(symbol, year, month, *, day=None):
    if symbol not in SYMBOLS:
        raise ValueError("Only BTCUSDT and ETHUSDT calculated marks are registered")
    if isinstance(year, bool) or not isinstance(year, int) or not 2017 <= year <= 2100:
        raise ValueError("Year must be an integer from 2017 through 2100")
    if isinstance(month, bool) or not isinstance(month, int) or not 1 <= month <= 12:
        raise ValueError("Month must be an integer from 1 through 12")
    if day is not None and (isinstance(day, bool) or not isinstance(day, int)
                            or not 1 <= day <= calendar.monthrange(year, month)[1]):
        raise ValueError("Day must belong to the requested calendar month")
    scope = "monthly" if day is None else "daily"
    suffix = f"{year:04d}-{month:02d}" + (f"-{day:02d}" if day is not None else "")
    name = f"{symbol}-5m-{suffix}.zip"
    url = f"{BASE}/{scope}/markPriceKlines/{symbol}/5m/{name}"
    return url, url + ".CHECKSUM", name


def parse_archive(content, checksum, symbol, year, month, *, day=None):
    url, _, name = archive_urls(symbol, year, month, day=day)
    rows, source = _rows(content, checksum, name)
    if not rows or tuple(rows.pop(0)) != HEADER:
        raise ExchangeDataError("Calculated-mark archive requires its exact twelve-field header")
    first = datetime(year, month, day or 1, tzinfo=timezone.utc)
    days = 1 if day is not None else calendar.monthrange(year, month)[1]
    finish = first + timedelta(days=days)
    expected = int((finish - first).total_seconds()) // 300
    if len(rows) != expected:
        raise ExchangeDataError("Calculated-mark archive misses requested calendar exposure")
    result, counts = [], Counter()
    first_ms = int(first.timestamp() * 1000)
    for index, row in enumerate(rows):
        if len(row) != 12:
            raise ExchangeDataError("Calculated-mark source row must contain exactly twelve fields")
        opened = _integer(row[0], "open_time")
        closed = _integer(row[6], "close_time")
        if opened != first_ms + index * 300000 or closed != opened + 299999:
            raise ExchangeDataError("Calculated marks require consecutive UTC millisecond intervals")
        if any(_finite(row[k], HEADER[k]) != 0 for k in (5, 7, 9, 10, 11)):
            raise ExchangeDataError("Calculated-mark archive unexpectedly contains nonzero trade-volume metadata")
        count = _integer(row[8], "source_auxiliary_count")
        counts[count] += 1
        at = first + timedelta(minutes=5 * index)
        bar = {"time": at.isoformat().replace("+00:00", "Z"),
               **{key: _finite(row[k], key) for k, key in enumerate(("open", "high", "low", "close"), 1)}}
        # Reuse only the immutable OHLC envelope validator. Its temporary zero
        # volume is removed from the output; this is not a traded-price series.
        normalized = validate_bars([{**bar, "volume": 0}])[0]
        normalized.pop("volume")
        result.append({**normalized, "known_at": (at + timedelta(minutes=5)).isoformat().replace("+00:00", "Z"),
                       "source_auxiliary_count": count})
    source.update(provider="Binance USD-M official calculated-mark archive", source_url=url,
                  symbol=symbol, interval="5m", year=year, month=month, day=day,
                  timestamp_unit="milliseconds", header=list(HEADER), bars=len(result),
                  first_open_at=result[0]["time"], last_open_at=result[-1]["time"],
                  quote_currency="USDT", price_kind="computed_mark_price",
                  trade_volume_columns_zero=True,
                  source_auxiliary_count_histogram={str(k): v for k, v in sorted(counts.items())},
                  zero_auxiliary_count_bars=counts.get(0, 0),
                  auxiliary_count_semantics="Retained source metadata; not executed trade count or proof of continuous sampling")
    return result, source


def fetch_archive(symbol, year, month, cache_dir, *, day=None):
    url, sum_url, name = archive_urls(symbol, year, month, day=day)
    root = Path(cache_dir)
    root.mkdir(parents=True, exist_ok=True)
    archive_path, checksum_path = root / name, root / (name + ".CHECKSUM")
    if archive_path.exists() and checksum_path.exists():
        content, checksum = archive_path.read_bytes(), checksum_path.read_bytes()
    else:
        checksum, content = _request(sum_url, 1024), _request(url)
    bars, source = parse_archive(content, checksum, symbol, year, month, day=day)
    for path, value in ((archive_path, content), (checksum_path, checksum)):
        if path.exists() and path.read_bytes() != value:
            raise ExchangeDataError("Calculated-mark acquisition would overwrite different cached bytes")
        if not path.exists():
            with path.open("xb") as stream:
                stream.write(value)
    return bars, source
