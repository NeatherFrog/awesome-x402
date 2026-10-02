import csv
from datetime import datetime, timedelta, timezone
import hashlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from propdesk.cross_sectional_data import (HEADER, archive_urls, fetch_archive,
                                          parse_archive, validate_funding)
from propdesk.exchange import ExchangeDataError


def zipped(rows, name):
    text = io.StringIO()
    csv.writer(text, lineterminator="\n").writerows(rows)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as stream:
        stream.writestr(name[:-4] + ".csv", text.getvalue())
    content = buf.getvalue()
    return content, f"{hashlib.sha256(content).hexdigest()}  {name}\n".encode()


def hourly(mark=False):
    opened = int(datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
    return [list(HEADER)] + [
        [str(opened + h * 3600000), "100", "105", "95", "101",
         "0" if mark else "10", str(opened + h * 3600000 + 3599999),
         "0" if mark else "1000", "3600" if mark else "12",
         "0" if mark else "4", "0" if mark else "400", "0"] for h in range(24)]


def funding():
    opened = int(datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
    return [["calc_time", "funding_interval_hours", "last_funding_rate"]] + [
        [str(opened + h * 3600000 + 7), "8", ".0001"] for h in range(0, 31 * 24, 8)]


class CrossSourceTests(unittest.TestCase):
    def parse_hour(self, rows, mark=False):
        kind = "markPriceKlines" if mark else "klines"
        name = archive_urls("SOLUSDT", kind, 2024, 1, day=1)[2]
        return parse_archive(*zipped(rows, name), "SOLUSDT", kind, 2024, 1, day=1)

    def test_trade_units_and_known_close(self):
        bars, source = self.parse_hour(hourly())
        self.assertEqual(len(bars), 24)
        self.assertEqual(bars[0]["known_at"], "2024-01-01T01:00:00Z")
        self.assertEqual(bars[0]["quote_volume"], 1000)
        self.assertEqual(bars[0]["volume"], 10)
        self.assertEqual(bars[0]["trade_count"], 12)
        self.assertEqual(source["price_kind"], "last_trade_price")

    def test_computed_mark_preserves_nontrade_auxiliary_metadata(self):
        bars, source = self.parse_hour(hourly(True), True)
        self.assertEqual(bars[0]["source_auxiliary_count"], 3600)
        self.assertNotIn("volume", bars[0])
        self.assertNotIn("trade_count", bars[0])
        self.assertEqual(source["price_kind"], "computed_mark_price")

    def test_marks_cannot_import_actual_trade_volume(self):
        with self.assertRaises(ExchangeDataError):
            self.parse_hour(hourly(), True)

    def test_zero_traded_volume_remains_absence(self):
        rows = hourly()
        for row in rows[1:]:
            for field in (5, 7, 8, 9, 10):
                row[field] = "0"
        bars, _ = self.parse_hour(rows)
        self.assertEqual(bars[0]["volume"], 0)
        self.assertEqual(bars[0]["trade_count"], 0)
        rows[1][8] = "1"
        with self.assertRaises(ExchangeDataError):
            self.parse_hour(rows)

    def test_missing_duplicate_and_microsecond_timestamps_reject(self):
        for mode in ("missing", "duplicate", "unit", "close"):
            rows = hourly()
            if mode == "missing":
                rows.pop()
            elif mode == "duplicate":
                rows[2][0] = rows[1][0]
            elif mode == "unit":
                rows[1][0] = str(int(rows[1][0]) * 1000)
            else:
                rows[1][6] = str(int(rows[1][6]) + 1)
            with self.subTest(mode=mode), self.assertRaises(ExchangeDataError):
                self.parse_hour(rows)

    def test_buy_excess_and_impossible_quote_average_reject(self):
        for field, value in ((9, "11"), (10, "1001"), (7, "2000"), (8, "1.5"), (2, "NaN")):
            rows = hourly()
            rows[1][field] = value
            with self.subTest(field=field), self.assertRaises(ExchangeDataError):
                self.parse_hour(rows)

    def test_exact_source_header_is_required(self):
        rows = hourly()
        rows[0][7] = "base_volume"
        with self.assertRaises(ExchangeDataError):
            self.parse_hour(rows)

    def test_funding_milliseconds_are_never_earlier_forecasts(self):
        name = archive_urls("SOLUSDT", "fundingRate", 2024, 1)[2]
        values, _ = parse_archive(*zipped(funding(), name), "SOLUSDT", "fundingRate", 2024, 1)
        self.assertEqual(values[0]["time"], "2024-01-01T00:00:00.007Z")
        self.assertEqual(values[0]["known_at"], values[0]["time"])
        self.assertIsNone(values[0]["mark_price"])
        self.assertEqual(values[0]["rate_kind"], "realized_settlement_outcome")

    def test_funding_gaps_and_wrong_units_reject(self):
        name = archive_urls("SOLUSDT", "fundingRate", 2024, 1)[2]
        for mode in ("missing", "seconds", "interval", "duplicate"):
            rows = funding()
            if mode == "missing":
                rows.pop(5)
            elif mode == "seconds":
                rows[1][0] = str(int(rows[1][0]) // 1000)
            elif mode == "interval":
                rows[3][1] = "4"
            else:
                rows[3][0] = rows[2][0]
            with self.subTest(mode=mode), self.assertRaises(ExchangeDataError):
                parse_archive(*zipped(rows, name), "SOLUSDT", "fundingRate", 2024, 1)

    def test_actual_source_interval_change_is_not_imputed_eight_hours(self):
        events = [
            {"time": "2024-01-01T00:00:00Z", "funding_interval_hours": 8},
            {"time": "2024-01-01T08:00:00Z", "funding_interval_hours": 8},
            {"time": "2024-01-01T12:00:00Z", "funding_interval_hours": 4},
            {"time": "2024-01-01T16:00:00Z", "funding_interval_hours": 4}]
        self.assertEqual(validate_funding(events), events)

    def test_source_kind_cache_cannot_mix_identical_zip_names(self):
        name = archive_urls("SOLUSDT", "klines", 2024, 1, day=1)[2]
        trade_zip, trade_sum = zipped(hourly(), name)
        mark_zip, mark_sum = zipped(hourly(True), name)
        def request(url, *_):
            mark = "/markPriceKlines/" in url
            return (mark_sum if mark else trade_sum) if url.endswith(".CHECKSUM") else (mark_zip if mark else trade_zip)
        with tempfile.TemporaryDirectory() as directory, patch("propdesk.cross_sectional_data._request", request):
            trade, _ = fetch_archive("SOLUSDT", "klines", 2024, 1, directory, day=1)
            mark, _ = fetch_archive("SOLUSDT", "markPriceKlines", 2024, 1, directory, day=1)
            self.assertEqual(trade[0]["volume"], 10)
            self.assertNotIn("volume", mark[0])
            self.assertNotEqual((Path(directory) / "klines" / name).read_bytes(),
                                (Path(directory) / "markPriceKlines" / name).read_bytes())

    def test_bad_checksum_and_unregistered_symbols_reject(self):
        name = archive_urls("SOLUSDT", "klines", 2024, 1, day=1)[2]
        content, checksum = zipped(hourly(), name)
        with self.assertRaises(ExchangeDataError):
            parse_archive(content + b"x", checksum, "SOLUSDT", "klines", 2024, 1, day=1)
        with self.assertRaises(ValueError):
            archive_urls("NEWTOKENUSDT", "klines", 2024, 1)
        with self.assertRaises(ValueError):
            archive_urls("BTCUSDT", "fundingRate", 2024, 1, day=1)
