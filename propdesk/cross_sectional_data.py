"""Separate checksum-verified 1h research sources for a fixed current-survivor cohort.

Calculated marks are not executable prices; realized funding is not an FTMO swap.
No current exchangeInfo, account credentials, orders, or historical-universe claim.
"""
from __future__ import annotations

import calendar
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path

from .exchange import ExchangeDataError
from .funding_data import _finite, _integer, _request, _rows
from .market import validate_bars

SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT", "DOGEUSDT",
           "LINKUSDT", "LTCUSDT", "BNBUSDT", "BCHUSDT", "DOTUSDT")
KINDS = ("klines", "markPriceKlines", "fundingRate")
HEADER = ("open_time", "open", "high", "low", "close", "volume", "close_time",
          "quote_volume", "count", "taker_buy_volume", "taker_buy_quote_volume", "ignore")
BASE = "https://data.binance.vision/data/futures/um"


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def iso(stamp):
    return stamp.astimezone(timezone.utc).isoformat(
        timespec="milliseconds" if stamp.microsecond else "seconds").replace("+00:00", "Z")


def bounds(year, month, day=None):
    if isinstance(year, bool) or not isinstance(year, int) or not 2017 <= year <= 2100:
        raise ValueError("Year must be an integer from 2017 through 2100")
    if isinstance(month, bool) or not isinstance(month, int) or not 1 <= month <= 12:
        raise ValueError("Month must be an integer from 1 through 12")
    if day is not None and (isinstance(day, bool) or not isinstance(day, int)
                            or not 1 <= day <= calendar.monthrange(year, month)[1]):
        raise ValueError("Day must belong to its requested month")
    start = datetime(year, month, day or 1, tzinfo=timezone.utc)
    return start, start + timedelta(days=1 if day is not None else calendar.monthrange(year, month)[1])


def archive_urls(symbol, kind, year, month, *, day=None):
    if symbol not in SYMBOLS or kind not in KINDS:
        raise ValueError("Only the fixed eleven symbols and three registered source kinds are permitted")
    bounds(year, month, day)
    if kind == "fundingRate" and day is not None:
        raise ValueError("Funding source is a monthly archive")
    scope = "daily" if day is not None else "monthly"
    suffix = f"{year:04d}-{month:02d}" + (f"-{day:02d}" if day is not None else "")
    name = f"{symbol}-{'fundingRate' if kind == 'fundingRate' else '1h'}-{suffix}.zip"
    folder = symbol if kind == "fundingRate" else symbol + "/1h"
    url = f"{BASE}/{scope}/{kind}/{folder}/{name}"
    return url, url + ".CHECKSUM", name


def validate_funding(events):
    if not events:
        raise ExchangeDataError("No realized funding events supplied")
    previous = None
    for event in events:
        stamp = datetime.fromisoformat(event["time"].replace("Z", "+00:00"))
        if previous is not None:
            gap = (stamp - previous).total_seconds()
            if gap <= 0 or abs(gap - event["funding_interval_hours"] * 3600) > 60:
                raise ExchangeDataError("Funding continuity differs from actual current-event source interval")
        previous = stamp
    return events


def parse_archive(content, checksum, symbol, kind, year, month, *, day=None):
    url, _, name = archive_urls(symbol, kind, year, month, day=day)
    raw, source = _rows(content, checksum, name)
    begin, finish = bounds(year, month, day)
    first_ms, finish_ms = int(begin.timestamp() * 1000), int(finish.timestamp() * 1000)
    values = []
    if kind == "fundingRate":
        if not raw or raw.pop(0) != ["calc_time", "funding_interval_hours", "last_funding_rate"]:
            raise ExchangeDataError("Funding archive requires its exact three-field header")
        for row in raw:
            if len(row) != 3:
                raise ExchangeDataError("Funding row requires exactly three source fields")
            stamp = _integer(row[0], "calc_time milliseconds")
            hours = _finite(row[1], "source funding_interval_hours")
            rate = _finite(row[2], "realized funding rate decimal")
            if not first_ms <= stamp < finish_ms or not 0 < hours <= 24 or abs(rate) > 1:
                raise ExchangeDataError("Funding event has invalid source time, interval, or decimal rate")
            time = iso(datetime.fromtimestamp(stamp / 1000, timezone.utc))
            values.append({"time": time, "known_at": time, "funding_rate": rate,
                           "funding_interval_hours": hours, "mark_price": None,
                           "rate_kind": "realized_settlement_outcome"})
        validate_funding(values)
        first_at = datetime.fromisoformat(values[0]["time"].replace("Z", "+00:00"))
        last_at = datetime.fromisoformat(values[-1]["time"].replace("Z", "+00:00"))
        if ((first_at - begin).total_seconds() > values[0]["funding_interval_hours"] * 3600 + 60
                or (finish - last_at).total_seconds() > values[-1]["funding_interval_hours"] * 3600 + 60):
            raise ExchangeDataError("Funding source lacks month boundary exposure")
        source.update(header=["calc_time", "funding_interval_hours", "last_funding_rate"],
                      observed_source_intervals_hours=sorted({e["funding_interval_hours"] for e in values}),
                      funding_mark_price_available=False)
    else:
        if not raw or tuple(raw.pop(0)) != HEADER:
            raise ExchangeDataError("1h source requires the exact documented twelve-field header")
        if len(raw) != (finish_ms - first_ms) // 3600000:
            raise ExchangeDataError("1h source misses requested complete calendar")
        for index, row in enumerate(raw):
            if len(row) != 12:
                raise ExchangeDataError("1h row requires twelve source fields")
            opened, closed = _integer(row[0], "open_time"), _integer(row[6], "close_time")
            if opened != first_ms + index * 3600000 or closed != opened + 3599999:
                raise ExchangeDataError("1h source is not consecutive explicit UTC millisecond intervals")
            prices = {key: _finite(row[k], key) for k, key in enumerate(("open", "high", "low", "close"), 1)}
            volume, quote, buy, buy_quote, ignored = [_finite(row[k], HEADER[k]) for k in (5, 7, 9, 10, 11)]
            count = _integer(row[8], "auxiliary count" if kind == "markPriceKlines" else "trade count")
            if min(volume, quote, buy, buy_quote) < 0 or buy > volume or buy_quote > quote:
                raise ExchangeDataError("Source volumes are negative or taker buys exceed totals")
            if kind == "markPriceKlines" and any(v != 0 for v in (volume, quote, buy, buy_quote, ignored)):
                raise ExchangeDataError("Calculated marks unexpectedly contain traded-volume metadata")
            if kind == "klines":
                if (volume == 0 and (quote != 0 or buy != 0 or buy_quote != 0 or count != 0)):
                    raise ExchangeDataError("Zero traded volume has inconsistent quote/count metadata")
                if volume > 0 and (quote <= 0 or count <= 0):
                    raise ExchangeDataError("Positive traded volume lacks positive quote volume or trade count")
                for base, notion in ((volume, quote), (buy, buy_quote), (volume - buy, quote - buy_quote)):
                    if base == 0:
                        if notion != 0:
                            raise ExchangeDataError("Zero base amount has nonzero quote amount")
                    elif not prices["low"] * (1 - 1e-7) <= notion / base <= prices["high"] * (1 + 1e-7):
                        raise ExchangeDataError("Source base/quote average lies outside its OHLC envelope")
            at = begin + timedelta(hours=index)
            bar = validate_bars([{**prices, "time": iso(at), "volume": volume}])[0]
            bar["known_at"] = iso(at + timedelta(hours=1))
            if kind == "markPriceKlines":
                bar.pop("volume")
                bar["source_auxiliary_count"] = count
            else:
                bar.update(quote_volume=quote, trade_count=count,
                           taker_buy_base=buy, taker_buy_quote=buy_quote)
            values.append(bar)
        source.update(header=list(HEADER), interval="1h", price_kind=(
            "computed_mark_price" if kind == "markPriceKlines" else "last_trade_price"))
    source.update(provider="Binance USD-M official archive", source_url=url, symbol=symbol,
                  kind=kind, year=year, month=month, day=day, timestamp_unit="milliseconds",
                  quote_currency="USDT", rows=len(values), first_at=values[0]["time"],
                  last_at=values[-1]["time"], data_fingerprint=digest(values))
    return values, source


def fetch_archive(symbol, kind, year, month, cache_dir, *, day=None):
    url, sum_url, name = archive_urls(symbol, kind, year, month, day=day)
    # Trade and mark ZIP basenames coincide: their source-kind directories must not.
    root = Path(cache_dir) / kind
    root.mkdir(parents=True, exist_ok=True)
    archive_path, checksum_path = root / name, root / (name + ".CHECKSUM")
    content = archive_path.read_bytes() if archive_path.exists() else _request(url)
    checksum = checksum_path.read_bytes() if checksum_path.exists() else _request(sum_url, 1024)
    values, source = parse_archive(content, checksum, symbol, kind, year, month, day=day)
    for path, data in ((archive_path, content), (checksum_path, checksum)):
        if path.exists() and path.read_bytes() != data:
            raise ExchangeDataError("Acquisition would overwrite different original source bytes")
        if not path.exists():
            with path.open("xb") as stream:
                stream.write(data)
    source.update(raw_file=f"raw/{kind}/{name}", checksum_file=f"raw/{kind}/{name}.CHECKSUM",
                  checksum_sha256=hashlib.sha256(checksum).hexdigest())
    return values, source
