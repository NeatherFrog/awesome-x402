"""Independent source-contract cases; no market outcomes or network calls."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import csv
import hashlib
import io
import unittest
import zipfile

from propdesk import flow_data
from propdesk.exchange import ExchangeDataError


START = datetime(2025, 1, 1, tzinfo=timezone.utc)
START_MS = int(START.timestamp() * 1000)
EXPECTED_HEADER = [
    "open_time", "open", "high", "low", "close", "volume", "close_time",
    "quote_volume", "count", "taker_buy_volume", "taker_buy_quote_volume", "ignore",
]


def raw_row(index=0):
    opening = START_MS + index * 300000
    return [str(opening), "100.00", "110.00", "90.00", "100.00", "10.000",
            str(opening + 299999), "1000.00000", "10", "2.000", "210.00000", "0"]


def canonical_bar():
    return {"time": "2025-01-01T00:00:00Z", "open": 100., "high": 110.,
            "low": 90., "close": 100., "volume": 10.}


def archive(rows=None, header=None):
    name = "BTCUSDT-5m-2025-01-01.zip"
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(header or EXPECTED_HEADER)
    writer.writerows(rows if rows is not None else [raw_row(i) for i in range(288)])
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w", compression=zipfile.ZIP_DEFLATED) as stream:
        stream.writestr(name[:-4] + ".csv", output.getvalue())
    content = payload.getvalue()
    checksum = (hashlib.sha256(content).hexdigest() + "  " + name + "\n").encode()
    return content, checksum


class FlowSourceAuditTests(unittest.TestCase):
    def parse(self, rows=None, header=None):
        content, checksum = archive(rows, header)
        return flow_data.parse_archive(content, checksum, "BTCUSDT", 2025, 1, day=1)

    def test_base_and_quote_fractions_are_distinct_units(self):
        row = flow_data.flow_row(raw_row(), canonical_bar())
        self.assertAlmostEqual(row["taker_buy_base_fraction"], .2)
        self.assertAlmostEqual(row["taker_buy_quote_fraction"], .21)
        self.assertEqual(row["trade_count"], 10)
        self.assertEqual(row["quote_volume"], 1000)

    def test_source_open_does_not_mean_flow_is_known_at_open(self):
        rows, _ = self.parse()
        self.assertEqual(rows[0]["time"], "2025-01-01T00:00:00Z")
        self.assertEqual(rows[0]["known_at"], "2025-01-01T00:05:00Z")
        self.assertEqual(rows[-1]["known_at"], "2025-01-02T00:00:00Z")

    def test_zero_volume_flow_remains_undefined(self):
        raw, bar = raw_row(), canonical_bar()
        for index in (5, 7, 8, 9, 10):
            raw[index] = "0"
        bar["volume"] = 0
        row = flow_data.flow_row(raw, bar)
        self.assertIsNone(row["taker_buy_base_fraction"])
        self.assertIsNone(row["taker_buy_quote_fraction"])
        raw[8] = "1"
        with self.assertRaises(ExchangeDataError):
            flow_data.flow_row(raw, bar)

    def test_taker_buy_excess_is_rejected_without_clipping(self):
        for index, value in ((9, "10.001"), (10, "1000.00001")):
            with self.subTest(index=index):
                raw = raw_row()
                raw[index] = value
                with self.assertRaises(ExchangeDataError):
                    flow_data.flow_row(raw, canonical_bar())

    def test_positive_base_requires_positive_quote_and_integer_trades(self):
        for index, value in ((7, "0"), (8, "0"), (8, "10.0"), (8, "-1")):
            with self.subTest(index=index, value=value):
                raw = raw_row()
                raw[index] = value
                with self.assertRaises(ExchangeDataError):
                    flow_data.flow_row(raw, canonical_bar())

    def test_nonfinite_source_quantities_never_enter_features(self):
        for index in (7, 9, 10):
            for value in ("NaN", "Infinity", "-Infinity"):
                with self.subTest(index=index, value=value):
                    raw = raw_row()
                    raw[index] = value
                    with self.assertRaises(ExchangeDataError):
                        flow_data.flow_row(raw, canonical_bar())

    def test_buy_and_complementary_sell_averages_need_price_envelopes(self):
        for buy_quote in ("240", "10"):
            raw = raw_row()
            raw[10] = buy_quote
            with self.assertRaises(ExchangeDataError):
                flow_data.flow_row(raw, canonical_bar())
        raw = raw_row()
        raw[9] = "0"
        with self.assertRaises(ExchangeDataError):
            flow_data.flow_row(raw, canonical_bar())

    def test_adjacent_checksum_and_filename_bind_source_bytes(self):
        content, checksum = archive()
        with self.assertRaises(ExchangeDataError):
            flow_data.parse_archive(content + b"x", checksum, "BTCUSDT", 2025, 1, day=1)
        wrong_name = checksum.replace(b"BTCUSDT", b"ETHUSDT")
        with self.assertRaises(ExchangeDataError):
            flow_data.parse_archive(content, wrong_name, "BTCUSDT", 2025, 1, day=1)

    def test_swapped_base_quote_header_is_rejected(self):
        header = EXPECTED_HEADER[:]
        header[9], header[10] = header[10], header[9]
        with self.assertRaises(ExchangeDataError):
            self.parse(header=header)

    def test_missing_or_duplicate_native_interval_cannot_be_filled(self):
        rows = [raw_row(i) for i in range(288)]
        with self.assertRaises(ExchangeDataError):
            self.parse(rows[:-1])
        duplicate = deepcopy(rows)
        duplicate[100] = duplicate[99][:]
        with self.assertRaises(ExchangeDataError):
            self.parse(duplicate)

    def test_spot_microsecond_change_is_not_applied_to_usdm(self):
        rows = [raw_row(i) for i in range(288)]
        for row in rows:
            row[0] = str(int(row[0]) * 1000)
            row[6] = str((int(row[0]) + 300000000) - 1)
        with self.assertRaises(ExchangeDataError):
            self.parse(rows)

    def test_last_included_millisecond_is_exact(self):
        rows = [raw_row(i) for i in range(288)]
        rows[0][6] = str(START_MS + 300000)
        with self.assertRaises(ExchangeDataError):
            self.parse(rows)

    def test_later_source_flow_does_not_mutate_earlier_decoded_record(self):
        original, _ = self.parse()
        rows = [raw_row(i) for i in range(288)]
        rows[287][9:11] = ["8.000", "800.00000"]
        changed, _ = self.parse(rows)
        self.assertEqual(original[:287], changed[:287])
        self.assertNotEqual(original[287]["taker_buy_base_fraction"],
                            changed[287]["taker_buy_base_fraction"])


if __name__ == "__main__":
    unittest.main()
