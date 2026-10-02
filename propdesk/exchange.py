"""Read-only Binance Spot candles and checksum-verified official archives.

No account credentials or order endpoints are accepted. Spot bars can support
signal research; they do not establish that short or derivative trades are
executable. Source rows are never sorted, deduplicated, filled or repaired.
"""
from __future__ import annotations

import calendar
import csv
import hashlib
import io
import json
import re
import ssl
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener

from .market import data_fingerprint, validate_bars

SYMBOLS = ("BTCUSDT", "ETHUSDT")
INTERVALS = {"5m": 300, "1h": 3600}
API_BASE = "https://data-api.binance.vision"
ARCHIVE_BASE = "https://data.binance.vision/data/spot/monthly/klines"
_HOSTS = {"data-api.binance.vision", "data.binance.vision"}
_MAX_BYTES = 32 * 1024 * 1024


class ExchangeDataError(ValueError):
    """Public data is unavailable or fails validation; there is no fallback."""


def _iso(stamp):
    return stamp.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _clock(now=None):
    now = datetime.now(timezone.utc) if now is None else now
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be a timezone-aware datetime")
    return now.astimezone(timezone.utc)


def _arguments(symbol, interval):
    if not isinstance(symbol, str) or symbol not in SYMBOLS:
        raise ValueError("symbol must be BTCUSDT or ETHUSDT")
    if not isinstance(interval, str) or interval not in INTERVALS:
        raise ValueError("interval must be 5m or 1h")
    return INTERVALS[interval]


def _safe_url(url):
    try:
        parsed = urlsplit(url)
        return (parsed.scheme == "https" and parsed.hostname in _HOSTS
                and parsed.port in (None, 443) and parsed.username is None
                and parsed.password is None)
    except (TypeError, ValueError):
        return False


class _SafeRedirect(HTTPRedirectHandler):
    max_redirections = 3
    max_repeats = 1

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not _safe_url(newurl):
            raise ExchangeDataError("Exchange redirected outside its public HTTPS hosts")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _request_bytes(url, *, max_bytes=_MAX_BYTES):
    if not _safe_url(url):
        raise ExchangeDataError("Only the fixed public Binance HTTPS data hosts are permitted")
    request = Request(url, headers={"User-Agent": "PropDeskPublicResearch/0.5", "Accept": "*/*"})
    opener = build_opener(_SafeRedirect(), HTTPSHandler(context=ssl.create_default_context()))
    try:
        with opener.open(request, timeout=30) as response:
            if not _safe_url(response.geturl()):
                raise ExchangeDataError("Exchange response left the permitted HTTPS hosts")
            content = response.read(max_bytes + 1)
    except HTTPError as exc:
        # Keep the status for archive availability, but never disclose response
        # bodies, headers or proxy credentials in user-facing exceptions.
        raise ExchangeDataError(f"Public Binance request rejected (HTTP {exc.code})") from None
    except (URLError, OSError, TimeoutError):
        raise ExchangeDataError("Public Binance HTTPS data is unavailable; no substitute data used") from None
    if len(content) > max_bytes:
        raise ExchangeDataError("Public Binance response exceeds the bounded size limit")
    return content


def _integer(value, name):
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ExchangeDataError(f"{name} must be an integer")
    if isinstance(value, str) and not re.fullmatch(r"\d+", value):
        raise ExchangeDataError(f"{name} must be an integer")
    return int(value)


def convert_klines(rows, interval="5m", *, timestamp_unit="milliseconds", now=None,
                   closed_only=True):
    """Validate documented 12-column klines; return closed bars and skip count.

    Units are specified by the caller: REST defaults to milliseconds; official
    Spot archives switched to microseconds in January 2025. Millisecond and
    microsecond close labels must be exactly interval-end minus one unit.
    """
    if interval not in INTERVALS:
        raise ValueError("interval must be 5m or 1h")
    if timestamp_unit not in ("milliseconds", "microseconds"):
        raise ValueError("timestamp_unit must be explicit milliseconds or microseconds")
    if not isinstance(rows, (list, tuple)) or not rows:
        raise ExchangeDataError("Expected a nonempty list of public exchange klines")
    scale = 1000 if timestamp_unit == "milliseconds" else 1_000_000
    seconds = INTERVALS[interval]
    step = seconds * scale
    clock_epoch = int(_clock(now).timestamp() * scale)
    bars, previous, skipped = [], None, 0
    for row in rows:
        if not isinstance(row, (list, tuple)) or len(row) != 12:
            raise ExchangeDataError("Binance kline must contain exactly 12 documented columns")
        epoch = _integer(row[0], "open timestamp")
        close = _integer(row[6], "close timestamp")
        if epoch < 1_400_000_000 * scale or epoch > 4_102_444_800 * scale or epoch % step:
            raise ExchangeDataError("Timestamp units or interval alignment are invalid")
        if close != epoch + step - 1:
            raise ExchangeDataError("Kline close timestamp does not match the explicit interval")
        if previous is not None and epoch - previous != step:
            raise ExchangeDataError("Exchange klines must be consecutive, ascending and unique; gaps are not filled")
        previous = epoch
        if closed_only and epoch + step > clock_epoch:
            skipped += 1
            continue
        stamp = _iso(datetime.fromtimestamp(epoch // scale, timezone.utc))
        bars.append({"time": stamp, **dict(zip(("open", "high", "low", "close", "volume"), row[1:6]))})
    if not bars:
        raise ExchangeDataError("The exchange returned no fully closed bars")
    try:
        canonical = validate_bars(bars, max_bars=400_000)
    except ValueError as exc:
        raise ExchangeDataError("Exchange OHLCV is malformed; prices are not repaired") from exc
    return canonical, skipped


def fetch_closed_bars(symbol, interval="5m", limit=1000, *, now=None):
    """Fetch recent public spot bars; local clock determines closed/freshness."""
    seconds = _arguments(symbol, interval)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 2 <= limit <= 1000:
        raise ValueError("limit must be an integer from 2 through 1000")
    clock = _clock(now)
    url = API_BASE + "/api/v3/klines?" + urlencode({"symbol": symbol, "interval": interval, "limit": limit})
    content = _request_bytes(url, max_bytes=2 * 1024 * 1024)
    try:
        rows = json.loads(content.decode("utf-8"), parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError, UnicodeDecodeError, RecursionError):
        raise ExchangeDataError("Public Binance response is not valid finite JSON") from None
    bars, skipped = convert_klines(rows, interval, now=clock)
    last_closed = datetime.fromisoformat(bars[-1]["time"].replace("Z", "+00:00")) + timedelta(seconds=seconds)
    delay = (clock - last_closed).total_seconds()
    return {"bars": bars, "provenance": {
        "provider": "Binance Spot", "venue": "binance_spot", "symbol": symbol,
        "base_currency": symbol[:-4], "quote_currency": "USDT", "interval": interval,
        "source_url": url, "retrieved_at": _iso(clock), "bar_timestamp": "opening time UTC",
        "timestamp_unit": "milliseconds", "bars": len(bars), "skipped_forming_bars": skipped,
        "last_closed_at": _iso(last_closed), "latest_delay_seconds": delay,
        "stale": delay >= 2 * seconds, "data_fingerprint": data_fingerprint(bars),
        "spot_execution_validated": False, "short_execution_validated": False,
        "live_orders_enabled": False,
    }, "warnings": ["Public spot OHLCV is not an executable bid/ask quote or order-fill proof.",
                     "Spot shorting, borrowing, derivatives funding and prop execution are not validated."]}


def archive_urls(symbol, interval, year, month, *, day=None):
    _arguments(symbol, interval)
    if isinstance(year, bool) or not isinstance(year, int) or not 2017 <= year <= 2100:
        raise ValueError("year must be an integer from 2017 through 2100")
    if isinstance(month, bool) or not isinstance(month, int) or not 1 <= month <= 12:
        raise ValueError("month must be an integer from 1 through 12")
    if day is not None and (isinstance(day, bool) or not isinstance(day, int)
                            or not 1 <= day <= calendar.monthrange(year, month)[1]):
        raise ValueError("day must identify a valid calendar day")
    suffix = f"{year:04d}-{month:02d}" + (f"-{day:02d}" if day is not None else "")
    name = f"{symbol}-{interval}-{suffix}.zip"
    base = ARCHIVE_BASE if day is None else ARCHIVE_BASE.replace("/monthly/", "/daily/")
    url = f"{base}/{symbol}/{interval}/{name}"
    return url, url + ".CHECKSUM", name


def parse_archive(content, checksum, symbol, interval, year, month, *, day=None):
    """Verify official checksum then parse one bounded, unextracted CSV member."""
    url, _, name = archive_urls(symbol, interval, year, month, day=day)
    try:
        fields = checksum.decode("ascii").strip().split()
    except (AttributeError, UnicodeDecodeError):
        raise ExchangeDataError("Archive CHECKSUM is not valid ASCII") from None
    if len(fields) != 2 or not re.fullmatch(r"[0-9a-fA-F]{64}", fields[0]) or fields[1].lstrip("*") != name:
        raise ExchangeDataError("Archive CHECKSUM does not identify the requested filename")
    actual = hashlib.sha256(content).hexdigest()
    if actual != fields[0].lower():
        raise ExchangeDataError("Official archive SHA-256 mismatch")
    expected_csv = name[:-4] + ".csv"
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            members = archive.infolist()
            if len(members) != 1 or members[0].filename != expected_csv or members[0].file_size > _MAX_BYTES:
                raise ExchangeDataError("Archive must contain exactly its expected bounded CSV member")
            raw = archive.read(expected_csv)
        rows = list(csv.reader(io.StringIO(raw.decode("utf-8")), strict=True))
    except (zipfile.BadZipFile, UnicodeDecodeError, csv.Error, RuntimeError):
        raise ExchangeDataError("Archive is not a valid documented ZIP/CSV") from None
    unit = "microseconds" if year >= 2025 else "milliseconds"
    bars, _ = convert_klines(rows, interval, timestamp_unit=unit, closed_only=False)
    expected_count = (calendar.monthrange(year, month)[1] if day is None else 1) * 86400 // INTERVALS[interval]
    first = _iso(datetime(year, month, 1 if day is None else day, tzinfo=timezone.utc))
    if len(bars) != expected_count or bars[0]["time"] != first:
        raise ExchangeDataError("Monthly archive is incomplete; missing calendar exposure is not deleted")
    return bars, {"provider": "Binance Spot official archive", "source_url": url,
                  "symbol": symbol, "interval": interval, "year": year, "month": month,
                  "day": day,
                  "timestamp_unit": unit, "zip_sha256": actual,
                  "csv_sha256": hashlib.sha256(raw).hexdigest(), "bars": len(bars),
                  "first_open_at": bars[0]["time"], "last_open_at": bars[-1]["time"],
                  "data_fingerprint": data_fingerprint(bars), "checksum_verified": True}


def fetch_archive(symbol, interval, year, month, cache_dir, *, day=None):
    """Download/revalidate official ZIP+CHECKSUM, storing bytes only in cache."""
    url, checksum_url, name = archive_urls(symbol, interval, year, month, day=day)
    root = Path(cache_dir)
    root.mkdir(parents=True, exist_ok=True)
    zip_path, checksum_path = root / name, root / (name + ".CHECKSUM")
    if zip_path.exists() and checksum_path.exists():
        content, checksum = zip_path.read_bytes(), checksum_path.read_bytes()
    else:
        checksum = _request_bytes(checksum_url, max_bytes=1024)
        content = _request_bytes(url)
    bars, source = parse_archive(content, checksum, symbol, interval, year, month, day=day)
    zip_path.write_bytes(content)
    checksum_path.write_bytes(checksum)
    return bars, source
