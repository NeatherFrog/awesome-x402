"""Read-only, checksum-verified USD-M perp and realized funding data.

Realized funding rates are historical settlement outcomes, never forecasts.
The archive's funding interval is retained per event; no universal eight-hour
schedule, account credentials, order endpoints or derivative eligibility claim.
"""
from __future__ import annotations

import calendar
import csv
import hashlib
import io
import json
import math
import re
import ssl
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener

from .exchange import ExchangeDataError, convert_klines
from .market import data_fingerprint

SYMBOLS = ("BTCUSDT", "ETHUSDT")
ARCHIVE = "https://data.binance.vision/data/futures/um"
REST = "https://fapi.binance.com/fapi/v1/fundingRate"
_HOSTS = {"data.binance.vision", "fapi.binance.com"}
_MAX_BYTES = 32 * 1024 * 1024


def iso(stamp):
    stamp = stamp.astimezone(timezone.utc)
    return stamp.isoformat(timespec="milliseconds" if stamp.microsecond else "seconds").replace("+00:00", "Z")


def _safe(url):
    try:
        parsed = urlsplit(url)
        return (parsed.scheme == "https" and parsed.hostname in _HOSTS
                and parsed.port in (None, 443) and parsed.username is None and parsed.password is None)
    except (ValueError, TypeError):
        return False


class _Redirect(HTTPRedirectHandler):
    max_redirections = 3
    max_repeats = 1

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not _safe(newurl):
            raise ExchangeDataError("Funding data redirect left the permitted public HTTPS hosts")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _request(url, max_bytes=_MAX_BYTES):
    if not _safe(url):
        raise ExchangeDataError("Only fixed official public funding-data HTTPS hosts are allowed")
    opener = build_opener(_Redirect(), HTTPSHandler(context=ssl.create_default_context()))
    try:
        with opener.open(Request(url, headers={"User-Agent": "PropDeskFundingResearch/0.5"}), timeout=30) as response:
            if not _safe(response.geturl()):
                raise ExchangeDataError("Funding response left the permitted public HTTPS hosts")
            content = response.read(max_bytes + 1)
    except HTTPError as exc:
        raise ExchangeDataError(f"Official funding-data request rejected (HTTP {exc.code})") from None
    except (URLError, OSError, TimeoutError):
        raise ExchangeDataError("Official funding-data HTTPS is unavailable; no substitute source used") from None
    if len(content) > max_bytes:
        raise ExchangeDataError("Funding-data response exceeds its bounded size limit")
    return content


def _month(year, month):
    if isinstance(year, bool) or not isinstance(year, int) or not 2017 <= year <= 2100:
        raise ValueError("year must be an integer from2017 through2100")
    if isinstance(month, bool) or not isinstance(month, int) or not 1 <= month <= 12:
        raise ValueError("month must be an integer from1 through12")
    first = datetime(year, month, 1, tzinfo=timezone.utc)
    end = first + timedelta(days=calendar.monthrange(year, month)[1])
    return first, end


def archive_urls(symbol, kind, year, month, *, day=None):
    if symbol not in SYMBOLS:
        raise ValueError("symbol must be BTCUSDT or ETHUSDT")
    first, end = _month(year, month)
    if kind not in ("klines", "fundingRate"):
        raise ValueError("kind must be klines or fundingRate")
    if day is not None and (kind != "klines" or isinstance(day, bool)
                            or not isinstance(day, int) or not 1 <= day <= (end - first).days):
        raise ValueError("Only klines support an explicitly valid daily archive")
    scope = "monthly" if day is None else "daily"
    suffix = f"{year:04d}-{month:02d}" + (f"-{day:02d}" if day is not None else "")
    name = f"{symbol}-{'1h' if kind == 'klines' else 'fundingRate'}-{suffix}.zip"
    folder = f"{symbol}/1h" if kind == "klines" else symbol
    url = f"{ARCHIVE}/{scope}/{kind}/{folder}/{name}"
    return url, url + ".CHECKSUM", name


def _rows(content, checksum, name):
    try:
        fields = checksum.decode("ascii").strip().split()
    except (UnicodeDecodeError, AttributeError):
        raise ExchangeDataError("Funding archive checksum must be ASCII") from None
    if len(fields) != 2 or not re.fullmatch(r"[a-fA-F0-9]{64}", fields[0]) or fields[1].lstrip("*") != name:
        raise ExchangeDataError("Funding archive checksum filename is incorrect")
    sha = hashlib.sha256(content).hexdigest()
    if sha != fields[0].lower():
        raise ExchangeDataError("Funding archive SHA-256 mismatch")
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            members = archive.infolist()
            expected = name[:-4] + ".csv"
            if len(members) != 1 or members[0].filename != expected or members[0].file_size > _MAX_BYTES:
                raise ExchangeDataError("Funding archive must contain its single bounded expected CSV")
            raw = archive.read(expected)
        rows = list(csv.reader(io.StringIO(raw.decode("utf-8")), strict=True))
    except (zipfile.BadZipFile, UnicodeDecodeError, csv.Error, RuntimeError):
        raise ExchangeDataError("Funding archive is not valid ZIP/CSV") from None
    return rows, {"zip_sha256": sha, "csv_sha256": hashlib.sha256(raw).hexdigest(), "checksum_verified": True}


def _integer(value, name):
    if isinstance(value, bool) or not isinstance(value, (str, int)) or (isinstance(value, str) and not re.fullmatch(r"\d+", value)):
        raise ExchangeDataError(f"{name} must be a nonnegative integer")
    return int(value)


def _finite(value, name):
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise ExchangeDataError(f"{name} must be finite")
    try:
        number = float(value)
    except (ValueError, OverflowError):
        raise ExchangeDataError(f"{name} must be finite") from None
    if not math.isfinite(number):
        raise ExchangeDataError(f"{name} must be finite")
    return number


def _event(epoch, rate, interval_hours=None, mark_price=None):
    epoch = _integer(epoch, "funding timestamp milliseconds")
    if not 1_400_000_000_000 <= epoch < 4_102_444_800_000:
        raise ExchangeDataError("Funding timestamps must be explicit Unix milliseconds")
    rate = _finite(rate, "funding rate decimal")
    if abs(rate) > 1:
        raise ExchangeDataError("Funding rate is outside the accepted decimal-unit bound")
    if interval_hours is not None:
        interval_hours = _finite(interval_hours, "funding interval hours")
        if not 0 < interval_hours <= 24:
            raise ExchangeDataError("Funding interval must be a positive source value up to24 hours")
    if mark_price is not None:
        mark_price = _finite(mark_price, "funding mark price")
        if mark_price <= 0:
            raise ExchangeDataError("Funding mark price must be positive")
    return {"time": iso(datetime.fromtimestamp(epoch / 1000, timezone.utc)),
            "funding_rate": rate, "funding_interval_hours": interval_hours,
            "mark_price": mark_price, "known_at": iso(datetime.fromtimestamp(epoch / 1000, timezone.utc)),
            "rate_kind": "realized_settlement_outcome"}


def event_fingerprint(events):
    raw = json.dumps(events, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(raw).hexdigest()


def validate_events(events, *, interval_gap_tolerance_seconds=60):
    """Retain source intervals and millisecond settlement labels without repair."""
    if not events:
        raise ExchangeDataError("No realized funding events supplied")
    previous = None
    for event in events:
        stamp = datetime.fromisoformat(event["time"].replace("Z", "+00:00"))
        if previous is not None:
            gap = (stamp - previous).total_seconds()
            if gap <= 0:
                raise ExchangeDataError("Funding events must be ascending and unique; no sorting or deduplication")
            source_interval = event["funding_interval_hours"]
            if source_interval is not None and abs(gap - source_interval * 3600) > interval_gap_tolerance_seconds:
                raise ExchangeDataError("Funding event gap disagrees with the current event's source interval; no invented events")
        previous = stamp
    return events


def parse_archive(content, checksum, symbol, kind, year, month, *, day=None):
    url, _, name = archive_urls(symbol, kind, year, month, day=day)
    rows, metadata = _rows(content, checksum, name)
    first, end = _month(year, month)
    if day is not None:
        first = first.replace(day=day)
        end = first + timedelta(days=1)
    if kind == "klines":
        header = None
        if rows and rows[0] and rows[0][0] in ("open_time", "openTime"):
            header = rows.pop(0)
            if len(header) != 12 or header[1:6] != ["open", "high", "low", "close", "volume"] or header[6] not in ("close_time", "closeTime"):
                raise ExchangeDataError("USD-M archive kline header is not documented OHLCV order")
        bars, _ = convert_klines(rows, "1h", timestamp_unit="milliseconds", closed_only=False)
        expected = int((end - first).total_seconds()) // 3600
        if len(bars) != expected or bars[0]["time"] != iso(first):
            raise ExchangeDataError("Perpetual archive misses requested calendar exposure")
        values, fingerprint = bars, data_fingerprint(bars)
        metadata.update(header=header, bars=len(bars), first_open_at=bars[0]["time"], last_open_at=bars[-1]["time"])
    else:
        expected_header = ["calc_time", "funding_interval_hours", "last_funding_rate"]
        if not rows or rows.pop(0) != expected_header:
            raise ExchangeDataError("Funding archive must have calc_time,funding_interval_hours,last_funding_rate header")
        values = []
        for row in rows:
            if len(row) != 3:
                raise ExchangeDataError("Funding archive row must contain exactly its three source fields")
            event = _event(row[0], row[2], row[1])
            stamp = datetime.fromisoformat(event["time"].replace("Z", "+00:00"))
            if not first <= stamp < end:
                raise ExchangeDataError("Funding archive event lies outside its requested source month")
            values.append(event)
        validate_events(values)
        # Source intervals can change. Endpoint coverage is checked against each
        # boundary event's actual stated interval, not a fixed event count.
        first_stamp = datetime.fromisoformat(values[0]["time"].replace("Z", "+00:00"))
        last_stamp = datetime.fromisoformat(values[-1]["time"].replace("Z", "+00:00"))
        if ((first_stamp - first).total_seconds() > values[0]["funding_interval_hours"] * 3600 + 60
                or (end - last_stamp).total_seconds() > values[-1]["funding_interval_hours"] * 3600 + 60):
            raise ExchangeDataError("Funding archive lacks requested month boundary coverage")
        fingerprint = event_fingerprint(values)
        metadata.update(header=expected_header, events=len(values), first_event_at=values[0]["time"],
                        last_event_at=values[-1]["time"], observed_source_intervals_hours=sorted({value["funding_interval_hours"] for value in values}),
                        mark_price_available=False)
    metadata.update(provider="Binance USD-M perpetual official archive", source_url=url,
                    symbol=symbol, kind=kind, year=year, month=month, day=day,
                    timestamp_unit="milliseconds", data_fingerprint=fingerprint)
    return values, metadata


def fetch_archive(symbol, kind, year, month, cache_dir, *, day=None):
    url, checksum_url, name = archive_urls(symbol, kind, year, month, day=day)
    root = Path(cache_dir)
    root.mkdir(parents=True, exist_ok=True)
    zip_path, checksum_path = root / name, root / (name + ".CHECKSUM")
    if zip_path.exists() and checksum_path.exists():
        content, checksum = zip_path.read_bytes(), checksum_path.read_bytes()
    else:
        checksum, content = _request(checksum_url, 1024), _request(url)
    values, source = parse_archive(content, checksum, symbol, kind, year, month, day=day)
    zip_path.write_bytes(content)
    checksum_path.write_bytes(checksum)
    return values, source


def fetch_funding_rest_month(symbol, year, month, cache_dir):
    """Fully paginated official REST for unavailable archive; retain raw pages.

    REST does not supply a historical interval-hours field. It is explicitly
    null, never substituted with current fundingInfo or a universal schedule.
    """
    if symbol not in SYMBOLS:
        raise ValueError("symbol must be BTCUSDT or ETHUSDT")
    first, end = _month(year, month)
    cursor, stop = int(first.timestamp() * 1000), int(end.timestamp() * 1000) - 1
    events, pages = [], []
    root = Path(cache_dir)
    root.mkdir(parents=True, exist_ok=True)
    for page_number in range(10):
        url = REST + "?" + urlencode({"symbol": symbol, "startTime": cursor, "endTime": stop, "limit": 1000})
        path = root / f"{symbol}-fundingRate-{year:04d}-{month:02d}-page{page_number}.json"
        raw = path.read_bytes() if path.exists() else _request(url, 2 * 1024 * 1024)
        try:
            rows = json.loads(raw.decode(), parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        except (ValueError, UnicodeDecodeError, RecursionError):
            raise ExchangeDataError("Funding REST returned malformed JSON") from None
        if not isinstance(rows, list) or len(rows) > 1000:
            raise ExchangeDataError("Funding REST did not return its documented bounded event array")
        page_events = []
        for row in rows:
            if not isinstance(row, dict) or row.get("symbol") != symbol:
                raise ExchangeDataError("Funding REST returned the wrong symbol")
            event = _event(row.get("fundingTime"), row.get("fundingRate"), mark_price=row.get("markPrice"))
            epoch = _integer(row["fundingTime"], "funding timestamp")
            if not cursor <= epoch <= stop:
                raise ExchangeDataError("Funding REST event lies outside its requested page bounds")
            page_events.append(event)
        if page_events:
            validate_events(page_events)
        path.write_bytes(raw)
        pages.append({"source_url": url, "raw_file": path.name, "raw_sha256": hashlib.sha256(raw).hexdigest(), "events": len(rows)})
        events.extend(page_events)
        if len(rows) < 1000:
            break
        cursor = _integer(rows[-1]["fundingTime"], "funding timestamp") + 1
    else:
        raise ExchangeDataError("Funding REST exceeded its bounded page limit")
    validate_events(events)
    return events, {"provider": "Binance USD-M official funding REST", "symbol": symbol,
                    "kind": "fundingRate", "year": year, "month": month, "pages": pages,
                    "source_url": REST, "events": len(events), "first_event_at": events[0]["time"],
                    "last_event_at": events[-1]["time"], "timestamp_unit": "milliseconds",
                    "data_fingerprint": event_fingerprint(events), "checksum_verified": False,
                    "archive_replaced_by_rest": True, "historical_interval_hours_available": False,
                    "mark_price_available": all(event["mark_price"] is not None for event in events)}
