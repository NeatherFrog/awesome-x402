"""Calculated-mark source identity, clocks and failure-path tests."""
from datetime import datetime, timezone
import csv
import hashlib
import io
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import zipfile

from propdesk.exchange import ExchangeDataError
from propdesk import mark_data
from scripts import download_mark_5m as downloader


OPEN = int(datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)


def fixture(rows=None, *, header=None, member=None):
    name = "BTCUSDT-5m-2025-01-01.zip"
    source = io.StringIO(newline="")
    writer = csv.writer(source, lineterminator="\n")
    writer.writerow(header or mark_data.HEADER)
    writer.writerows(rows if rows is not None else [row(i) for i in range(288)])
    zipped = io.BytesIO()
    with zipfile.ZipFile(zipped, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(member or name[:-4] + ".csv", source.getvalue())
    payload = zipped.getvalue()
    checksum = (hashlib.sha256(payload).hexdigest() + "  " + name + "\n").encode()
    return payload, checksum


def row(index=0):
    at = OPEN + index * 300000
    return [str(at), "100.00000001", "102.00000001", "99.00000001", "101.00000001",
            "0", str(at + 299999), "0", "300", "0", "0", "0"]


class MarkDataTests(unittest.TestCase):
    def parse(self, rows=None, **kwargs):
        content, checksum = fixture(rows, **kwargs)
        return mark_data.parse_archive(content, checksum, "BTCUSDT", 2025, 1, day=1)

    def test_mark_endpoint_is_distinct_from_trade_klines(self):
        url, checksum, name = mark_data.archive_urls("BTCUSDT", 2024, 10)
        self.assertEqual(url, "https://data.binance.vision/data/futures/um/monthly/markPriceKlines/BTCUSDT/5m/BTCUSDT-5m-2024-10.zip")
        self.assertEqual(checksum, url + ".CHECKSUM")
        self.assertEqual(name, "BTCUSDT-5m-2024-10.zip")
        with self.assertRaises(ValueError):
            mark_data.archive_urls("BTCUSD", 2024, 10)

    def test_zero_volume_computed_marks_are_valid_and_not_execution_records(self):
        records, metadata = self.parse()
        self.assertEqual(len(records), 288)
        self.assertEqual(records[0]["open"], 100.00000001)
        self.assertNotIn("volume", records[0])
        self.assertEqual(metadata["price_kind"], "computed_mark_price")
        self.assertTrue(metadata["trade_volume_columns_zero"])
        self.assertEqual(records[0]["source_auxiliary_count"], 300)

    def test_bar_knowledge_and_millisecond_clock_are_explicit(self):
        records, _ = self.parse()
        self.assertEqual(records[0]["time"], "2025-01-01T00:00:00Z")
        self.assertEqual(records[0]["known_at"], "2025-01-01T00:05:00Z")
        self.assertEqual(records[-1]["known_at"], "2025-01-02T00:00:00Z")
        rows = [row(i) for i in range(288)]
        for record in rows:
            record[0] = str(int(record[0]) * 1000)
            record[6] = str(int(record[0]) + 299999999)
        with self.assertRaises(ExchangeDataError):
            self.parse(rows)

    def test_zero_auxiliary_count_is_preserved_as_source_uncertainty(self):
        rows = [row(i) for i in range(288)]
        rows[0][8] = "0"
        records, metadata = self.parse(rows)
        self.assertEqual(records[0]["source_auxiliary_count"], 0)
        self.assertEqual(metadata["zero_auxiliary_count_bars"], 1)
        self.assertIn("not executed trade count", metadata["auxiliary_count_semantics"])

    def test_trade_metadata_cannot_masquerade_as_computed_mark_history(self):
        for index in (5, 7, 9, 10, 11):
            with self.subTest(index=index):
                rows = [row(i) for i in range(288)]
                rows[0][index] = "1"
                with self.assertRaises(ExchangeDataError):
                    self.parse(rows)

    def test_missing_duplicate_or_wrong_close_interval_is_rejected(self):
        rows = [row(i) for i in range(288)]
        with self.assertRaises(ExchangeDataError):
            self.parse(rows[:-1])
        rows[100] = rows[99][:]
        with self.assertRaises(ExchangeDataError):
            self.parse(rows)
        rows = [row(i) for i in range(288)]
        rows[0][6] = str(OPEN + 300000)
        with self.assertRaises(ExchangeDataError):
            self.parse(rows)

    def test_nonfinite_negative_and_invalid_envelope_are_rejected(self):
        for index, value in ((1, "NaN"), (2, "Infinity"), (1, "-1"), (3, "105"), (8, "300.0")):
            with self.subTest(index=index, value=value):
                rows = [row(i) for i in range(288)]
                rows[0][index] = value
                with self.assertRaises((ExchangeDataError, ValueError)):
                    self.parse(rows)

    def test_header_checksum_and_zip_member_are_strict(self):
        header = list(mark_data.HEADER)
        header[7] = "quoteVolume"
        with self.assertRaises(ExchangeDataError):
            self.parse(header=header)
        with self.assertRaises(ExchangeDataError):
            self.parse(member="other.csv")
        content, checksum = fixture()
        with self.assertRaises(ExchangeDataError):
            mark_data.parse_archive(content + b"x", checksum, "BTCUSDT", 2025, 1, day=1)

    def test_cached_bytes_still_require_valid_adjacent_checksum(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            content, checksum = fixture()
            name = "BTCUSDT-5m-2025-01-01.zip"
            (root / name).write_bytes(content + b"x")
            (root / (name + ".CHECKSUM")).write_bytes(checksum)
            with patch.object(mark_data, "_request") as request:
                with self.assertRaises(ExchangeDataError):
                    mark_data.fetch_archive("BTCUSDT", 2025, 1, root, day=1)
                request.assert_not_called()

    def test_only_unpublished_september_month_may_use_all_daily_sources(self):
        calls = []
        def fetch(symbol, year, month, cache, *, day=None):
            calls.append(day)
            if day is None:
                raise ExchangeDataError("Official request HTTP 404")
            return [{"time": str(day)}], {"day": day}
        with patch.object(downloader, "fetch_archive", side_effect=fetch):
            rows, sources, errors = downloader.chunk("BTCUSDT", 2026, 9, Path("unused"))
        self.assertEqual(calls, [None] + list(range(1, 31)))
        self.assertEqual(len(rows), 30)
        self.assertEqual(len(sources), 30)
        self.assertEqual(errors, [])
        calls.clear()
        with patch.object(downloader, "fetch_archive", side_effect=fetch):
            _, _, errors = downloader.chunk("BTCUSDT", 2025, 9, Path("unused"))
        self.assertEqual(calls, [None])
        self.assertTrue(errors)

    def test_checksum_failure_never_triggers_daily_substitution(self):
        with patch.object(downloader, "fetch_archive", side_effect=ExchangeDataError("SHA-256 mismatch")) as fetch:
            rows, sources, errors = downloader.chunk("BTCUSDT", 2026, 9, Path("unused"))
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual((rows, sources), ([], []))
        self.assertTrue(errors)

    def test_existing_receipt_cannot_be_silently_rewritten(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "protocol.json"
            downloader.write_json(path, {"frozen": True})
            before = path.read_bytes()
            with self.assertRaises(ValueError):
                downloader.write_json(path, {"frozen": False})
            self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
