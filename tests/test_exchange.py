"""Public exchange data integrity, candle causality and snapshot failure tests."""
from datetime import datetime, timedelta, timezone
import hashlib
import io
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from propdesk.exchange import (ExchangeDataError, _SafeRedirect, archive_urls,
                               convert_klines, fetch_archive, fetch_closed_bars,
                               parse_archive)


NOW = datetime(2025, 1, 1, 0, 15, tzinfo=timezone.utc)


def row(stamp, *, unit="milliseconds", interval=300):
    scale = 1000 if unit == "milliseconds" else 1_000_000
    epoch = int(stamp.timestamp()) * scale
    return [epoch, "100", "103", "98", "102", "12", epoch + interval * scale - 1,
            "1200", 10, "6", "600", "0"]


def daily_archive(year=2025, month=1, day=1, *, interval="1h", unit=None, count=24,
                  filename=None):
    unit = unit or ("microseconds" if year >= 2025 else "milliseconds")
    seconds = 3600 if interval == "1h" else 300
    stamp = datetime(year, month, day, tzinfo=timezone.utc)
    name = archive_urls("BTCUSDT", interval, year, month, day=day)[2]
    rows = [row(stamp + timedelta(seconds=i * seconds), unit=unit, interval=seconds)
            for i in range(count)]
    text = "\n".join(",".join(map(str, item)) for item in rows) + "\n"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(filename or name[:-4] + ".csv", text)
    content = buffer.getvalue()
    checksum = (hashlib.sha256(content).hexdigest() + "  " + name + "\n").encode()
    return content, checksum


class ExchangeCandleTests(unittest.TestCase):
    def test_rest_milliseconds_and_archive_microseconds_preserve_ohlcv(self):
        for unit in ("milliseconds", "microseconds"):
            with self.subTest(unit=unit):
                bars, skipped = convert_klines([row(NOW - timedelta(minutes=15), unit=unit)],
                                               timestamp_unit=unit, now=NOW)
                self.assertEqual(bars[0], {"time": "2025-01-01T00:00:00Z", "open": 100.,
                                          "high": 103., "low": 98., "close": 102., "volume": 12.})
                self.assertEqual(skipped, 0)

    def test_forming_bar_is_removed_at_exact_utc_boundary(self):
        rows = [row(NOW - timedelta(minutes=5)), row(NOW)]
        bars, skipped = convert_klines(rows, now=NOW)
        self.assertEqual(len(bars), 1)
        self.assertEqual(bars[0]["time"], "2025-01-01T00:10:00Z")
        self.assertEqual(skipped, 1)
        with self.assertRaisesRegex(ExchangeDataError, "fully closed"):
            convert_klines([row(NOW)], now=NOW)

    def test_wrong_timestamp_units_bool_fraction_and_misalignment_fail(self):
        cases = []
        for value in (True, "1735689600000.0", 1735689600, 1735689600001, 1735689600000000):
            candidate = row(NOW - timedelta(minutes=15))
            candidate[0] = value
            cases.append(candidate)
        for candidate in cases:
            with self.subTest(value=candidate[0]):
                with self.assertRaises(ValueError):
                    convert_klines([candidate], now=NOW)

    def test_close_timestamp_and_documented_width_are_required(self):
        candidate = row(NOW - timedelta(minutes=15))
        for modification in (candidate[:6], candidate + [0], candidate[:6] + [candidate[6] + 1] + candidate[7:]):
            with self.assertRaises(ExchangeDataError):
                convert_klines([modification], now=NOW)

    def test_gap_duplicate_and_unsorted_are_not_repaired(self):
        first = NOW - timedelta(minutes=15)
        for delta in (0, -300, 600):
            with self.subTest(delta=delta):
                with self.assertRaisesRegex(ExchangeDataError, "consecutive"):
                    convert_klines([row(first), row(first + timedelta(seconds=delta))], now=NOW)

    def test_nonfinite_prices_negative_volume_and_wrong_envelope_fail(self):
        for index, value in ((1, True), (1, "0"), (2, "99"), (3, "104"),
                             (4, "NaN"), (4, "inf"), (5, "-1")):
            candidate = row(NOW - timedelta(minutes=15))
            candidate[index] = value
            with self.subTest(index=index, value=value):
                with self.assertRaises(ValueError):
                    convert_klines([candidate], now=NOW)

    def test_recent_fetch_source_closedness_fingerprint_and_staleness(self):
        rows = [row(NOW - timedelta(minutes=10)), row(NOW - timedelta(minutes=5)), row(NOW)]
        with patch("propdesk.exchange._request_bytes", return_value=json.dumps(rows).encode()) as request:
            result = fetch_closed_bars("BTCUSDT", now=NOW)
        self.assertEqual(len(result["bars"]), 2)
        source = result["provenance"]
        self.assertEqual(source["provider"], "Binance Spot")
        self.assertEqual(source["quote_currency"], "USDT")
        self.assertEqual(source["last_closed_at"], "2025-01-01T00:15:00Z")
        self.assertFalse(source["stale"])
        self.assertFalse(source["live_orders_enabled"])
        self.assertEqual(len(source["data_fingerprint"]), 64)
        self.assertIn("/api/v3/klines?", request.call_args.args[0])
        with patch("propdesk.exchange._request_bytes", return_value=json.dumps(rows[:1]).encode()):
            delayed = fetch_closed_bars("BTCUSDT", now=NOW + timedelta(minutes=5))
        self.assertTrue(delayed["provenance"]["stale"])

    def test_argument_injection_and_naive_clock_fail_before_network(self):
        for args, kwargs in [(("BTCUSDT/../../x",), {}), (("btcusdt",), {}),
                             (("BTCUSDT", "1d"), {}), (("BTCUSDT", "5m", True), {}),
                             (("BTCUSDT", "5m", 1001), {}), (("BTCUSDT",), {"now": NOW.replace(tzinfo=None)})]:
            with patch("propdesk.exchange._request_bytes") as request:
                with self.assertRaises(ValueError):
                    fetch_closed_bars(*args, **kwargs)
                request.assert_not_called()

    def test_non_json_error_object_and_nan_json_are_rejected(self):
        for response in (b"html", b"{\"code\":-1}", b"[NaN]", b"[]"):
            with patch("propdesk.exchange._request_bytes", return_value=response):
                with self.assertRaises(ValueError):
                    fetch_closed_bars("BTCUSDT", now=NOW)


class ExchangeArchiveTests(unittest.TestCase):
    def test_official_daily_checksum_and_2025_units_are_verified(self):
        content, checksum = daily_archive()
        bars, source = parse_archive(content, checksum, "BTCUSDT", "1h", 2025, 1, day=1)
        self.assertEqual(len(bars), 24)
        self.assertEqual(bars[-1]["time"], "2025-01-01T23:00:00Z")
        self.assertTrue(source["checksum_verified"])
        self.assertEqual(source["timestamp_unit"], "microseconds")
        self.assertIn("/daily/", source["source_url"])

    def test_pre2025_milliseconds_and_month_boundary(self):
        content, checksum = daily_archive(year=2024, month=12, day=31)
        bars, source = parse_archive(content, checksum, "BTCUSDT", "1h", 2024, 12, day=31)
        self.assertEqual(bars[-1]["time"], "2024-12-31T23:00:00Z")
        self.assertEqual(source["timestamp_unit"], "milliseconds")

    def test_checksum_filename_hash_and_csv_member_tampering_fail(self):
        content, checksum = daily_archive()
        for raw, sum_ in ((content + b"x", checksum), (content, b"0" * 64 + b"  other.zip"),
                          (content, b"0" * 64 + b"  BTCUSDT-1h-2025-01-01.zip")):
            with self.assertRaises(ExchangeDataError):
                parse_archive(raw, sum_, "BTCUSDT", "1h", 2025, 1, day=1)
        content, checksum = daily_archive(filename="../../private.csv")
        with self.assertRaisesRegex(ExchangeDataError, "expected"):
            parse_archive(content, checksum, "BTCUSDT", "1h", 2025, 1, day=1)

    def test_incomplete_calendar_and_wrong_unit_are_rejected(self):
        for options in ({"count": 23}, {"unit": "milliseconds"}):
            content, checksum = daily_archive(**options)
            with self.assertRaises(ExchangeDataError):
                parse_archive(content, checksum, "BTCUSDT", "1h", 2025, 1, day=1)

    def test_fetch_cache_is_revalidated_and_not_a_silent_fallback(self):
        content, checksum = daily_archive()
        with tempfile.TemporaryDirectory() as directory:
            with patch("propdesk.exchange._request_bytes", side_effect=[checksum, content]) as request:
                bars, _ = fetch_archive("BTCUSDT", "1h", 2025, 1, directory, day=1)
            self.assertEqual(request.call_count, 2)
            self.assertEqual(len(bars), 24)
            with patch("propdesk.exchange._request_bytes") as request:
                fetch_archive("BTCUSDT", "1h", 2025, 1, directory, day=1)
                request.assert_not_called()
            path = Path(directory) / "BTCUSDT-1h-2025-01-01.zip"
            path.write_bytes(content + b"tampered")
            with self.assertRaisesRegex(ExchangeDataError, "SHA-256"):
                fetch_archive("BTCUSDT", "1h", 2025, 1, directory, day=1)

    def test_invalid_archival_dates_and_redirect_hosts_fail(self):
        for year, month, day in ((True, 1, None), (2025, 13, None), (2025, 2, 29), (2025, 1, True)):
            with self.assertRaises(ValueError):
                archive_urls("BTCUSDT", "1h", year, month, day=day)
        for url in ("http://data-api.binance.vision/api/v3/klines", "https://evil.example/",
                    "https://username:secret@data-api.binance.vision/api", "https://data-api.binance.vision:444/a"):
            with self.assertRaises(ExchangeDataError):
                _SafeRedirect().redirect_request(None, None, 302, "found", {}, url)


class LiquidityResearchProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        spec = importlib.util.spec_from_file_location("research_liquidity", root / "scripts" / "research_liquidity.py")
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    def test_quarter_registration_is_immutable_and_no_winner_is_selected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "quarter-protocol.json"
            first = self.module.register_quarter(path)
            self.assertEqual(first, self.module.register_quarter(path))
            plan = json.loads(path.read_text())
            self.assertEqual(plan["trials_count"], 8)
            self.assertIsNone(plan["selected"])
            self.assertFalse(plan["qualified"])
            plan["selected"] = "mss_all"
            path.write_text(json.dumps(plan))
            with self.assertRaisesRegex(ValueError, "Existing quarter protocol differs"):
                self.module.register_quarter(path)

    def test_uncertainty_retains_all_calendar_days_and_is_reproducible(self):
        trades = [{"exit_observed_at": "2026-07-05T04:00:00Z", "net_pnl": 12.5},
                  {"exit_observed_at": "2026-10-01T00:00:00Z", "net_pnl": -3.}]
        first = self.module._daily_uncertainty(trades, "BTCUSDT", "mss_all")
        self.assertEqual(first, self.module._daily_uncertainty(trades, "BTCUSDT", "mss_all"))
        self.assertEqual(first["days"], 92)
        self.assertEqual(first["zero_trade_days"], 90)
        self.assertEqual(sum(first["realized_daily_net_pnl"]), 9.5)
        self.assertEqual(first["individual_confidence_pct"], 99.375)
        self.assertLessEqual(first["ci_low"], first["ci_high"])


if __name__ == "__main__":
    unittest.main()
