"""Separate five-minute official USD-M acquisition; frozen adapters unchanged."""
from __future__ import annotations

import calendar
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .exchange import ExchangeDataError, convert_klines
from .funding_data import _request, _rows
from .market import data_fingerprint

SYMBOLS = ("BTCUSDT", "ETHUSDT")
BASE = "https://data.binance.vision/data/futures/um"


def archive_urls(symbol, year, month, *, day=None):
    if not isinstance(symbol, str) or symbol not in SYMBOLS:
        raise ValueError("symbol must be BTCUSDT or ETHUSDT")
    if isinstance(year, bool) or not isinstance(year, int) or not 2017 <= year <= 2100:
        raise ValueError("year must be an integer from2017 through2100")
    if isinstance(month, bool) or not isinstance(month, int) or not 1 <= month <= 12:
        raise ValueError("month must be an integer from1 through12")
    if day is not None and (isinstance(day, bool) or not isinstance(day, int)
                            or not 1 <= day <= calendar.monthrange(year, month)[1]):
        raise ValueError("day must be a valid calendar day")
    scope = "monthly" if day is None else "daily"
    suffix = f"{year:04d}-{month:02d}" + (f"-{day:02d}" if day is not None else "")
    name = f"{symbol}-5m-{suffix}.zip"
    url = f"{BASE}/{scope}/klines/{symbol}/5m/{name}"
    return url, url + ".CHECKSUM", name


def parse_archive(content, checksum, symbol, year, month, *, day=None):
    url, _, name = archive_urls(symbol, year, month, day=day)
    rows, metadata = _rows(content, checksum, name)
    header = None
    if rows and rows[0] and rows[0][0] in ("open_time", "openTime"):
        header = rows.pop(0)
        if len(header) != 12 or header[1:6] != ["open", "high", "low", "close", "volume"] or header[6] not in ("close_time", "closeTime"):
            raise ExchangeDataError("Five-minute USD-M archive has unexpected OHLCV header")
    bars, _ = convert_klines(rows, "5m", timestamp_unit="milliseconds", closed_only=False)
    first = datetime(year, month, day or 1, tzinfo=timezone.utc)
    days = calendar.monthrange(year, month)[1] if day is None else 1
    end = first + timedelta(days=days)
    expected = int((end - first).total_seconds()) // 300
    if len(bars) != expected or bars[0]["time"] != first.isoformat().replace("+00:00", "Z"):
        raise ExchangeDataError("Five-minute perpetual archive misses requested calendar exposure")
    metadata.update(provider="Binance USD-M perpetual official archive", source_url=url,
                    symbol=symbol, interval="5m", year=year, month=month, day=day,
                    timestamp_unit="milliseconds", header=header, bars=len(bars),
                    first_open_at=bars[0]["time"], last_open_at=bars[-1]["time"],
                    data_fingerprint=data_fingerprint(bars), quote_currency="USDT",
                    price_kind="perpetual trade OHLC; not mark/index price or executable bid/ask")
    return bars, metadata


def fetch_archive(symbol, year, month, cache_dir, *, day=None):
    url, checksum_url, name = archive_urls(symbol, year, month, day=day)
    root = Path(cache_dir)
    root.mkdir(parents=True, exist_ok=True)
    zip_path, sum_path = root / name, root / (name + ".CHECKSUM")
    if zip_path.exists() and sum_path.exists():
        content, checksum = zip_path.read_bytes(), sum_path.read_bytes()
    else:
        checksum, content = _request(checksum_url, 1024), _request(url)
    bars, source = parse_archive(content, checksum, symbol, year, month, day=day)
    if not zip_path.exists():
        zip_path.write_bytes(content)
    if not sum_path.exists():
        sum_path.write_bytes(checksum)
    return bars, source
