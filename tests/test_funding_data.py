"""Actual funding event labels, intervals, source bytes and causal knowledge."""
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from propdesk.exchange import ExchangeDataError
from propdesk.funding_data import (archive_urls, fetch_archive, fetch_funding_rest_month,
                                   parse_archive, validate_events)


def zipped(kind="fundingRate", year=2025, month=1, *, day=None, rows=None, header=True):
    name = archive_urls("BTCUSDT", kind, year, month, day=day)[2]
    start = datetime(year, month, day or 1, tzinfo=timezone.utc)
    if rows is None and kind == "fundingRate":
        next_month = start.replace(year=year + (month == 12), month=1 if month == 12 else month + 1)
        hours = int((next_month - start).total_seconds() // 3600)
        rows = [[int((start + timedelta(hours=hour)).timestamp() * 1000) + 3, "8", ".0001"]
                for hour in range(0, hours, 8)]
        if header:
            rows.insert(0, ["calc_time", "funding_interval_hours", "last_funding_rate"])
    elif rows is None:
        rows = []
        if header:
            rows.append(["open_time", "open", "high", "low", "close", "volume", "close_time", "quote_volume", "count", "taker_buy_volume", "taker_buy_quote_volume", "ignore"])
        for hour in range(24):
            epoch = int((start + timedelta(hours=hour)).timestamp()) * 1000
            rows.append([epoch, 100, 103, 98, 102, 12, epoch + 3600000 - 1, 1200, 4, 6, 600, 0])
    content = io.BytesIO()
    with zipfile.ZipFile(content, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(name[:-4] + ".csv", "\n".join(",".join(map(str, row)) for row in rows) + "\n")
    content = content.getvalue()
    checksum = (hashlib.sha256(content).hexdigest() + "  " + name).encode()
    return content, checksum


class FundingArchiveTests(unittest.TestCase):
    def test_source_monthly_paths_are_distinct_from_spot_and_usdm_time_stays_ms(self):
        funding = archive_urls("BTCUSDT", "fundingRate", 2025, 1)[0]
        self.assertIn("/data/futures/um/monthly/fundingRate/BTCUSDT/BTCUSDT-fundingRate-2025-01.zip", funding)
        content, checksum = zipped("klines", day=1)
        bars, source = parse_archive(content, checksum, "BTCUSDT", "klines", 2025, 1, day=1)
        self.assertEqual(bars[0]["time"], "2025-01-01T00:00:00Z")
        self.assertEqual(len(bars), 24)
        self.assertEqual(source["timestamp_unit"], "milliseconds")
        self.assertTrue(source["checksum_verified"])

    def test_actual_event_milliseconds_intervals_and_realized_knowledge_retained(self):
        content, checksum = zipped()
        events, source = parse_archive(content, checksum, "BTCUSDT", "fundingRate", 2025, 1)
        self.assertEqual(events[0]["time"], "2025-01-01T00:00:00.003Z")
        self.assertEqual(events[0]["known_at"], events[0]["time"])
        self.assertEqual(events[0]["funding_rate"], .0001)
        self.assertIsNone(events[0]["mark_price"])
        self.assertEqual(events[0]["rate_kind"], "realized_settlement_outcome")
        self.assertEqual(source["events"], 93)
        self.assertFalse(source["mark_price_available"])

    def test_changing_source_intervals_are_not_forced_into_eight_hours(self):
        start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        rows = [["calc_time", "funding_interval_hours", "last_funding_rate"]]
        # Two eight-hour intervals then four-hour settlements through month end.
        for hour in [0, 8, *range(12, 744, 4)]:
            rows.append([int((start + timedelta(hours=hour)).timestamp() * 1000),
                         8 if hour <= 8 else 4, -.00002])
        content, checksum = zipped(rows=rows)
        events, source = parse_archive(content, checksum, "BTCUSDT", "fundingRate", 2025, 1)
        self.assertEqual(source["observed_source_intervals_hours"], [4., 8.])
        self.assertEqual(events[2]["funding_interval_hours"], 4.)
        self.assertLess(events[2]["funding_rate"], 0)

    def test_gap_duplicate_wrong_units_invalid_rates_and_missing_header_fail(self):
        content, checksum = zipped(header=False)
        with self.assertRaisesRegex(ExchangeDataError, "header"):
            parse_archive(content, checksum, "BTCUSDT", "fundingRate", 2025, 1)
        start = int(datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
        for rows in ([ [start, 8, .0001], [start, 8, .0001] ],
                     [ [start, 8, .0001], [start + 16 * 3600000, 8, .0001] ],
                     [ [start * 1000, 8, .0001] ], [ [start, 8, "NaN"] ],
                     [ [start, 0, .0001] ]):
            content, checksum = zipped(rows=[["calc_time", "funding_interval_hours", "last_funding_rate"], *rows])
            with self.assertRaises(ExchangeDataError):
                parse_archive(content, checksum, "BTCUSDT", "fundingRate", 2025, 1)

    def test_tampered_checksum_and_incomplete_month_boundaries_fail(self):
        content, checksum = zipped()
        with self.assertRaisesRegex(ExchangeDataError, "SHA-256"):
            parse_archive(content + b"tampered", checksum, "BTCUSDT", "fundingRate", 2025, 1)
        start = int(datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
        content, checksum = zipped(rows=[["calc_time", "funding_interval_hours", "last_funding_rate"], [start, 8, .0001]])
        with self.assertRaisesRegex(ExchangeDataError, "boundary coverage"):
            parse_archive(content, checksum, "BTCUSDT", "fundingRate", 2025, 1)

    def test_cached_raw_zip_is_reverified(self):
        content, checksum = zipped()
        with tempfile.TemporaryDirectory() as directory:
            with patch("propdesk.funding_data._request", side_effect=[checksum, content]):
                fetch_archive("BTCUSDT", "fundingRate", 2025, 1, directory)
            with patch("propdesk.funding_data._request") as request:
                fetch_archive("BTCUSDT", "fundingRate", 2025, 1, directory)
                request.assert_not_called()
            path = Path(directory) / "BTCUSDT-fundingRate-2025-01.zip"
            path.write_bytes(content + b"changed")
            with self.assertRaises(ExchangeDataError):
                fetch_archive("BTCUSDT", "fundingRate", 2025, 1, directory)


class FundingRestTests(unittest.TestCase):
    def test_fallback_rest_is_realized_only_and_has_no_invented_interval(self):
        start = int(datetime(2026, 9, 1, tzinfo=timezone.utc).timestamp() * 1000)
        rows = [{"symbol": "BTCUSDT", "fundingTime": start + 3, "fundingRate": ".0001", "markPrice": "60123.45"}]
        with tempfile.TemporaryDirectory() as directory:
            with patch("propdesk.funding_data._request", return_value=json.dumps(rows).encode()) as request:
                events, source = fetch_funding_rest_month("BTCUSDT", 2026, 9, directory)
            self.assertIsNone(events[0]["funding_interval_hours"])
            self.assertEqual(events[0]["mark_price"], 60123.45)
            self.assertFalse(source["checksum_verified"])
            self.assertTrue(source["archive_replaced_by_rest"])
            self.assertIn("startTime=", request.call_args.args[0])

    def test_rest_symbol_bounds_bad_json_empty_and_nonfinite_are_rejected(self):
        start = int(datetime(2026, 9, 1, tzinfo=timezone.utc).timestamp() * 1000)
        cases = [b"notJSON", b"[]", b"[NaN]",
                 json.dumps([{"symbol": "ETHUSDT", "fundingTime": start, "fundingRate": ".0001"}]).encode(),
                 json.dumps([{"symbol": "BTCUSDT", "fundingTime": start - 1, "fundingRate": ".0001"}]).encode(),
                 json.dumps([{"symbol": "BTCUSDT", "fundingTime": start, "fundingRate": "NaN"}]).encode()]
        for response in cases:
            with tempfile.TemporaryDirectory() as directory:
                with patch("propdesk.funding_data._request", return_value=response):
                    with self.assertRaises(ExchangeDataError):
                        fetch_funding_rest_month("BTCUSDT", 2026, 9, directory)

    def test_invalid_symbol_dates_and_unsupported_daily_funding_fail(self):
        for symbol, kind, year, month, day in (("BTCUSDT/../../x", "klines", 2025, 1, None),
                                               ("BTCUSDT", "fundingRate", 2025, 1, 1),
                                               ("BTCUSDT", "klines", True, 1, None),
                                               ("BTCUSDT", "klines", 2025, 2, 29)):
            with self.assertRaises(ValueError):
                archive_urls(symbol, kind, year, month, day=day)


if __name__ == "__main__":
    unittest.main()
