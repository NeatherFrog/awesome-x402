"""New perp five-minute source integrity; old study adapters stay unchanged."""
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from propdesk.exchange import ExchangeDataError
from propdesk.perp_resolution import archive_urls, fetch_archive, parse_archive


def archive(year=2025, month=1, *, day=1, unit="milliseconds", missing=None, header=True):
    name = archive_urls("BTCUSDT", year, month, day=day)[2]
    scale = 1000 if unit == "milliseconds" else 1_000_000
    start = datetime(year, month, day or 1, tzinfo=timezone.utc)
    count = 288 if day else 31 * 288
    rows = []
    if header:
        rows.append(["open_time", "open", "high", "low", "close", "volume", "close_time", "quote_volume", "count", "taker_buy_volume", "taker_buy_quote_volume", "ignore"])
    for index in range(count):
        if index == missing:
            continue
        epoch = int((start + timedelta(seconds=300 * index)).timestamp()) * scale
        rows.append([epoch, 100, 103, 98, 102, 12, epoch + 300 * scale - 1, 1200, 4, 6, 600, 0])
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zip_:
        zip_.writestr(name[:-4] + ".csv", "\n".join(",".join(map(str, row)) for row in rows) + "\n")
    raw = buffer.getvalue()
    checksum = (hashlib.sha256(raw).hexdigest() + "  " + name).encode()
    return raw, checksum


class PerpetualResolutionTests(unittest.TestCase):
    def test_official_usdm_5m_url_preserves_instrument_identity(self):
        url, checksum, name = archive_urls("BTCUSDT", 2025, 1)
        self.assertEqual(url, "https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/5m/BTCUSDT-5m-2025-01.zip")
        self.assertEqual(checksum, url + ".CHECKSUM")
        self.assertEqual(name, "BTCUSDT-5m-2025-01.zip")

    def test_exact_daily_ohlcv_and_2025_milliseconds_are_preserved(self):
        raw, checksum = archive()
        bars, source = parse_archive(raw, checksum, "BTCUSDT", 2025, 1, day=1)
        self.assertEqual(len(bars), 288)
        self.assertEqual(bars[0], {"time": "2025-01-01T00:00:00Z", "open":100., "high":103., "low":98., "close":102., "volume":12.})
        self.assertEqual(bars[-1]["time"], "2025-01-01T23:55:00Z")
        self.assertEqual(source["timestamp_unit"], "milliseconds")
        self.assertEqual(source["quote_currency"], "USDT")
        self.assertTrue(source["checksum_verified"])

    def test_complete_month_has_no_discarded_calendar_exposure(self):
        raw, checksum = archive(day=None)
        bars, source = parse_archive(raw, checksum, "BTCUSDT", 2025, 1)
        self.assertEqual(len(bars), 8928)
        self.assertEqual(source["last_open_at"], "2025-01-31T23:55:00Z")

    def test_spot_microsecond_rule_is_not_applied_to_perpetuals(self):
        raw, checksum = archive(unit="microseconds")
        with self.assertRaisesRegex(ExchangeDataError, "Timestamp units"):
            parse_archive(raw, checksum, "BTCUSDT", 2025, 1, day=1)

    def test_missing_internal_bar_or_month_boundary_is_rejected(self):
        for missing in (0, 10, 287):
            raw, checksum = archive(missing=missing)
            with self.assertRaises(ExchangeDataError):
                parse_archive(raw, checksum, "BTCUSDT", 2025, 1, day=1)

    def test_changed_zip_or_checksum_filename_fails(self):
        raw, checksum = archive()
        with self.assertRaisesRegex(ExchangeDataError, "SHA-256"):
            parse_archive(raw + b"changed", checksum, "BTCUSDT", 2025, 1, day=1)
        with self.assertRaises(ExchangeDataError):
            parse_archive(raw, checksum.replace(b"BTCUSDT", b"ETHUSDT"), "BTCUSDT", 2025, 1, day=1)

    def test_cached_bytes_are_reverified_without_a_new_network_request(self):
        raw, checksum = archive()
        with tempfile.TemporaryDirectory() as directory:
            with patch("propdesk.perp_resolution._request", side_effect=[checksum, raw]):
                fetch_archive("BTCUSDT", 2025, 1, directory, day=1)
            with patch("propdesk.perp_resolution._request") as request:
                fetch_archive("BTCUSDT", 2025, 1, directory, day=1)
                request.assert_not_called()
            path = Path(directory) / "BTCUSDT-5m-2025-01-01.zip"
            path.write_bytes(raw + b"changed")
            with self.assertRaises(ExchangeDataError):
                fetch_archive("BTCUSDT", 2025, 1, directory, day=1)

    def test_invalid_symbol_date_and_booleans_fail_before_network(self):
        for symbol, year, month, day in (("BTCUSDT/../../secret",2025,1,None), ("BTCUSDT",True,1,None),
                                         ("BTCUSDT",2025,1,True), ("BTCUSDT",2025,2,29)):
            with patch("propdesk.perp_resolution._request") as request:
                with self.assertRaises(ValueError):
                    fetch_archive(symbol,year,month,"/unused",day=day)
                request.assert_not_called()


class PerpetualDownloaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        spec = importlib.util.spec_from_file_location("download_perp_5m", root / "scripts" / "download_perp_5m.py")
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    def test_missing_month_does_not_replace_prices_or_export_a_partial_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(self.module, "fetch_archive", side_effect=ExchangeDataError("Official source HTTP403")):
                values, sources, errors = self.module.chunk("BTCUSDT",2025,1,Path(directory))
            self.assertFalse(values)
            self.assertFalse(sources)
            self.assertEqual(len(errors),1)

    def test_september404_requires_all_official_daily_files(self):
        calls = []
        def fetch(symbol,year,month,root,*,day=None):
            calls.append(day)
            if day is None:
                raise ExchangeDataError("Public source HTTP 404")
            return [{"time":str(day)}],["unused"]
        with patch.object(self.module,"fetch_archive",side_effect=fetch):
            values,sources,errors = self.module.chunk("BTCUSDT",2026,9,Path("/unused"))
        self.assertEqual(calls,[None,*range(1,31)])
        self.assertEqual(len(values),30)
        self.assertFalse(errors)

    def test_immutable_snapshot_refuses_refresh_or_price_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"snapshot.json"
            self.module.write_json(path,[{"close":100}],compact=True)
            self.module.write_json(path,[{"close":100}],compact=True)
            with self.assertRaisesRegex(ValueError,"differs"):
                self.module.write_json(path,[{"close":101}],compact=True)

    def test_publication_is_not_available_outside_this_authorized_ci(self):
        with patch.dict("os.environ",{},clear=True):
            with self.assertRaisesRegex(ValueError,"authorized Actions"):
                self.module.publish_ci("/unused")


if __name__ == "__main__":
    unittest.main()
