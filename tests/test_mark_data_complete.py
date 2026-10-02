"""Separate June source revision cannot hide the original calendar defect."""
from datetime import datetime, timedelta, timezone
import csv
import hashlib
import io
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import zipfile

from propdesk.exchange import ExchangeDataError
from propdesk.mark_data import HEADER
from scripts import download_mark_5m_complete as complete


START = datetime(2026, 6, 1, tzinfo=timezone.utc)


def source_row(day=1, slot=0):
    at = START + timedelta(days=day - 1, minutes=slot * 5)
    ms = int(at.timestamp() * 1000)
    return [str(ms), "100", "102", "99", "101", "0", str(ms + 299999), "0", "300", "0", "0", "0"]


def missing_month(directory, *, missing_day=29):
    name = "BTCUSDT-5m-2026-06.zip"
    csv_stream = io.StringIO(newline="")
    writer = csv.writer(csv_stream, lineterminator="\n")
    writer.writerow(HEADER)
    writer.writerows(source_row(day, slot) for day in range(1, 31) if day != missing_day for slot in range(288))
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(name[:-4] + ".csv", csv_stream.getvalue())
    content = output.getvalue()
    checksum = hashlib.sha256(content).hexdigest()
    root = Path(directory)
    (root / name).write_bytes(content)
    (root / (name + ".CHECKSUM")).write_text(checksum + "  " + name + "\n")
    return checksum


def fake_daily(symbol, year, month, cache, *, day=None):
    at = START + timedelta(days=day - 1)
    row = {"time": at.isoformat().replace("+00:00", "Z"), "open": 100., "high": 102., "low": 99.,
           "close": 101., "source_auxiliary_count": 300}
    return [row], {"day": day, "checksum_verified": True}


class MarkDataCompleteTests(unittest.TestCase):
    def test_exact_registered_monthly_omission_is_preserved_as_unused_witness(self):
        with TemporaryDirectory() as directory:
            checksum = missing_month(directory)
            with patch.dict(complete.REJECTED_JUNE_SHA, {"BTCUSDT": checksum}):
                rows, witness = complete.monthly_witness("BTCUSDT", directory)
        self.assertEqual(len(rows), 8352)
        self.assertEqual(witness["missing_intervals"], 288)
        self.assertFalse(witness["used_for_prices"])
        self.assertTrue(witness["checksum_verified"])

    def test_different_missing_day_cannot_use_the_registered_exception(self):
        with TemporaryDirectory() as directory:
            checksum = missing_month(directory, missing_day=28)
            with patch.dict(complete.REJECTED_JUNE_SHA, {"BTCUSDT": checksum}):
                with self.assertRaises(ExchangeDataError):
                    complete.monthly_witness("BTCUSDT", directory)

    def test_changed_validly_checksummed_month_is_not_silently_a_new_vintage(self):
        with TemporaryDirectory() as directory:
            missing_month(directory)
            with patch.dict(complete.REJECTED_JUNE_SHA, {"BTCUSDT": "0" * 64}):
                with self.assertRaises(ExchangeDataError):
                    complete.monthly_witness("BTCUSDT", directory)

    def test_complete_replacement_requires_all_thirty_daily_sources(self):
        witness = ([source_row(1)], {"used_for_prices": False})
        with patch.object(complete, "monthly_witness", return_value=witness), patch.object(complete, "fetch_archive", side_effect=fake_daily) as fetch:
            rows, sources, failures, rejected = complete.complete_chunk("BTCUSDT", 2026, 6, Path("unused"))
        self.assertEqual([call.kwargs["day"] for call in fetch.call_args_list], list(range(1, 31)))
        self.assertEqual(len(sources), 30)
        self.assertEqual(failures, [])
        self.assertEqual(len(rows), 30)
        self.assertEqual(rejected[0]["daily_overlap_ohlc_difference_rows"], 0)

    def test_missing_daily_source_stays_blocked_without_inserted_prices(self):
        def failed(*args, day=None, **kwargs):
            if day == 29:
                raise ExchangeDataError("HTTP 404")
            return fake_daily(*args, day=day, **kwargs)
        with patch.object(complete, "monthly_witness", return_value=([source_row(1)], {})), patch.object(complete, "fetch_archive", side_effect=failed):
            rows, sources, failures, _ = complete.complete_chunk("BTCUSDT", 2026, 6, Path("unused"))
        self.assertEqual(len(rows), 29)
        self.assertEqual(len(sources), 29)
        self.assertEqual(failures[0]["day"], 29)

    def test_daily_prices_must_agree_with_preserved_monthly_overlap(self):
        original = source_row(1)
        original[1] = "100.5"
        with patch.object(complete, "monthly_witness", return_value=([original], {})), patch.object(complete, "fetch_archive", side_effect=fake_daily):
            _, _, failures, witness = complete.complete_chunk("BTCUSDT", 2026, 6, Path("unused"))
        self.assertTrue(failures)
        self.assertEqual(witness[0]["daily_overlap_ohlc_difference_rows"], 1)

    def test_other_months_and_old_registration_are_unchanged(self):
        old_id = complete.prior.PROTOCOL["data_protocol_id"]
        with patch.object(complete.prior, "chunk", return_value=([], [], [{"error": "blocked"}])) as fetch:
            _, _, failures, rejected = complete.complete_chunk("BTCUSDT", 2025, 6, Path("unused"))
        fetch.assert_called_once()
        self.assertTrue(failures)
        self.assertEqual(rejected, [])
        self.assertEqual(complete.prior.PROTOCOL["data_protocol_id"], old_id)
        self.assertNotEqual(complete.PROTOCOL["data_protocol_id"], old_id)


if __name__ == "__main__":
    unittest.main()
