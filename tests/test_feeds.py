import copy
import io
import json
import math
import ssl
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request

from propdesk.feeds import get_history, parse_chart, _SafeRedirect


NOW = datetime(2026, 1, 5, 12, 30, tzinfo=timezone.utc)


def fixture(symbol="AAPL", stamps=None):
    stamps = stamps or [datetime(2026, 1, 5, hour, tzinfo=timezone.utc) for hour in (9, 10, 11, 12)]
    size = len(stamps)
    return {"chart": {"error": None, "result": [{"meta": {"symbol": symbol},
            "timestamp": [int(stamp.timestamp()) for stamp in stamps],
            "indicators": {"quote": [{"open": [100.0] * size, "high": [102.0] * size,
                                       "low": [99.0] * size, "close": [101.0] * size,
                                       "volume": [1000.0] * size}]}}]}}


class ChartParsing(unittest.TestCase):
    def test_provider_currency_and_instrument_class_are_preserved(self):
        payload = fixture()
        payload["chart"]["result"][0]["meta"].update(currency="GBp", instrumentType="EQUITY")
        provenance = parse_chart(payload, "AAPL", now=NOW)["provenance"]
        self.assertEqual(provenance["quote_currency"], "GBp")
        self.assertEqual(provenance["instrument_type"], "EQUITY")

    def test_only_closed_bars_are_canonical_utc_and_provenance_is_explicit(self):
        result = parse_chart(fixture(), "AAPL", now=NOW)
        self.assertEqual(len(result["bars"]), 3)
        self.assertEqual(result["bars"][0]["time"], "2026-01-05T09:00:00Z")
        self.assertEqual(result["bars"][-1]["time"], "2026-01-05T11:00:00Z")
        metadata = result["provenance"]
        self.assertEqual(metadata["provider"], "Yahoo Chart (public unofficial endpoint)")
        self.assertEqual(metadata["retrieved_at"], "2026-01-05T12:30:00Z")
        self.assertEqual(metadata["last_closed_at"], "2026-01-05T12:00:00Z")
        self.assertEqual(metadata["skipped_rows"], 1)
        self.assertEqual(metadata["skipped_reasons"]["forming"], 1)
        self.assertEqual(metadata["bar_timestamp"], "opening time UTC")

    def test_exact_boundary_bar_is_closed(self):
        result = parse_chart(fixture(), "AAPL", now=NOW.replace(minute=0))
        self.assertEqual(len(result["bars"]), 3)
        self.assertEqual(result["provenance"]["last_closed_at"], "2026-01-05T12:00:00Z")

    def test_missing_ohlc_is_skipped_without_fabricating_prices(self):
        data = fixture()
        data["chart"]["result"][0]["indicators"]["quote"][0]["high"][1] = None
        result = parse_chart(data, "AAPL", now=NOW)
        self.assertEqual([bar["time"] for bar in result["bars"]], ["2026-01-05T09:00:00Z", "2026-01-05T11:00:00Z"])
        self.assertEqual(result["provenance"]["skipped_rows"], 2)
        self.assertEqual(result["provenance"]["skipped_reasons"]["missing_ohlc"], 1)
        self.assertTrue(any("не заполняются" in value for value in result["provenance"]["warnings"]))
        del data["chart"]["result"][0]["indicators"]["quote"][0]["high"]
        with self.assertRaisesRegex(ValueError, "open/high/low/close"):
            parse_chart(data, "AAPL", now=NOW)

    def test_missing_volume_is_zero_only_with_disclosed_warning(self):
        data = fixture()
        data["chart"]["result"][0]["indicators"]["quote"][0]["volume"][1] = None
        result = parse_chart(data, "AAPL", now=NOW)
        self.assertEqual(result["bars"][1]["volume"], 0)
        self.assertEqual(result["provenance"]["missing_volume_rows"], 1)
        self.assertTrue(any("не подтверждённый нулевой" in value for value in result["provenance"]["warnings"]))

    def test_invalid_prices_or_envelopes_reject_without_repairs(self):
        for field, value in (("open", 0), ("close", -1), ("high", 100), ("low", 102),
                             ("volume", -1), ("close", math.inf), ("open", True)):
            with self.subTest(field=field, value=value):
                data = fixture()
                data["chart"]["result"][0]["indicators"]["quote"][0][field][0] = value
                with self.assertRaisesRegex(ValueError, "цены не восстанавливаются"):
                    parse_chart(data, "AAPL", now=NOW)

    def test_duplicates_unordered_nonfinite_fractional_or_huge_epochs_reject(self):
        for value in (math.nan, math.inf, True, "1700000000", 1.25, 10 ** 500):
            data = fixture()
            data["chart"]["result"][0]["timestamp"][1] = value
            with self.subTest(value_type=type(value).__name__):
                with self.assertRaises(ValueError):
                    parse_chart(data, "AAPL", now=NOW)
        for change in ("duplicate", "unordered"):
            data = fixture()
            stamps = data["chart"]["result"][0]["timestamp"]
            stamps[1] = stamps[0] if change == "duplicate" else stamps[0] - 3600
            with self.assertRaisesRegex(ValueError, "возрастать"):
                parse_chart(data, "AAPL", now=NOW)

    def test_missing_timestamp_is_counted_and_no_data_or_wrong_symbol_reject(self):
        data = fixture()
        data["chart"]["result"][0]["timestamp"][1] = None
        result = parse_chart(data, "AAPL", now=NOW)
        self.assertEqual(len(result["bars"]), 2)
        self.assertEqual(result["provenance"]["skipped_reasons"]["missing_timestamp"], 1)
        with self.assertRaisesRegex(ValueError, "другого инструмента"):
            parse_chart(fixture("MSFT"), "AAPL", now=NOW)
        with self.assertRaisesRegex(ValueError, "ни одного"):
            parse_chart(fixture(stamps=[NOW.replace(minute=0)]), "AAPL", now=NOW)
        with self.assertRaises(ValueError):
            parse_chart({"chart": {"result": [], "error": None}}, "AAPL", now=NOW)

    def test_daily_session_filter_is_conservative_and_disclosed(self):
        stamps = [datetime(2026, 1, day, 14, 30, tzinfo=timezone.utc) for day in (3, 4, 5)]
        result = parse_chart(fixture(stamps=stamps), "AAPL", "1d", "1mo", now=NOW)
        self.assertEqual(len(result["bars"]), 1)
        self.assertEqual(result["bars"][0]["time"], "2026-01-03T14:30:00Z")
        self.assertEqual(result["provenance"]["last_closed_at"], "2026-01-04T14:30:00Z")
        self.assertTrue(any("open + 24h" in warning for warning in result["provenance"]["warnings"]))

    def test_aliases_and_nontraded_proxy_warnings_are_visible(self):
        for requested, actual, warning in (("EURUSD", "EURUSD=X", "FX"), ("XAUUSD", "GC=F", "futures"),
                                            ("NAS100", "^NDX", "неторгуемый"), ("BTCUSD", "BTC-USD", "стакан")):
            with self.subTest(requested=requested):
                result = parse_chart(fixture(actual), requested, now=NOW)
                self.assertEqual(result["provenance"]["provider_symbol"], actual)
                self.assertTrue(any(warning in value for value in result["provenance"]["warnings"]))

    def test_range_symbol_clock_and_row_limits_are_validated_before_network(self):
        for symbol in ("", "https://evil.example/a", "AAPL/../secret", "NASDAQ:AAPL", "AAPL\n", ".", "A" * 33, None):
            with patch("propdesk.feeds._request_json") as request:
                with self.assertRaises(ValueError):
                    get_history(symbol, now=NOW)
                request.assert_not_called()
        for interval, range_ in (("2m", "3mo"), ("15m", "3mo"), ("1h", "max"), ("1d", "forever"), ([], "3mo")):
            with self.assertRaises(ValueError):
                parse_chart(fixture(), "AAPL", interval, range_, now=NOW)
        with self.assertRaises(ValueError):
            parse_chart(fixture(), "AAPL", now=NOW.replace(tzinfo=None))
        data = fixture()
        data["chart"]["result"][0]["timestamp"] = [0] * 30001
        with self.assertRaisesRegex(ValueError, "30 000"):
            parse_chart(data, "AAPL", now=NOW)


class HistoryTransport(unittest.TestCase):
    def response(self, payload):
        response = io.BytesIO(json.dumps(payload).encode())
        response.geturl = lambda: "https://query1.finance.yahoo.com/v8/finance/chart/AAPL"
        return response

    def test_fixed_https_host_alias_encoding_timeout_and_tls_verification(self):
        opener = Mock()
        response = self.response(fixture("GC=F"))
        opener.open.return_value = response
        with patch("propdesk.feeds.build_opener", return_value=opener) as builder:
            result = get_history("xauusd", now=NOW)
        request = opener.open.call_args.args[0]
        url = urlsplit(request.full_url)
        self.assertEqual(url.scheme, "https")
        self.assertEqual(url.hostname, "query1.finance.yahoo.com")
        self.assertTrue(url.path.endswith("/GC%3DF"))
        self.assertEqual(parse_qs(url.query)["interval"], ["1h"])
        self.assertEqual(opener.open.call_args.kwargs["timeout"], 15)
        context = builder.call_args.args[1]._context
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)
        self.assertEqual(result["provenance"]["requested_symbol"], "XAUUSD")
        self.assertIsNone(request.get_header("Authorization"))
        self.assertIsNone(request.get_header("Cookie"))

    def test_http_network_and_tls_errors_never_include_sensitive_details(self):
        secret = "super-secret-header proxy://user:password@internal.example"
        cases = [HTTPError("https://query1.finance.yahoo.com", 403, secret, {"Authorization": secret}, io.BytesIO(secret.encode())),
                 HTTPError("https://query1.finance.yahoo.com", 429, secret, {}, io.BytesIO()),
                 URLError(secret), URLError(ssl.SSLError(secret)), TimeoutError(secret)]
        for error in cases:
            with self.subTest(error_type=type(error).__name__):
                opener = Mock()
                opener.open.side_effect = error
                with patch("propdesk.feeds.build_opener", return_value=opener):
                    with self.assertRaises(ValueError) as caught:
                        get_history("AAPL", now=NOW)
                self.assertNotIn(secret, str(caught.exception))
                self.assertNotIn("password", str(caught.exception))

    def test_body_limits_nonjson_and_nonfinite_json_reject(self):
        for raw in (b"x" * (8 * 1024 * 1024 + 1), b"<html>proxy denied</html>", b'{"chart":NaN}', b"\xff"):
            opener = Mock()
            response = io.BytesIO(raw)
            response.geturl = lambda: "https://query1.finance.yahoo.com/v8/finance/chart/AAPL"
            opener.open.return_value = response
            with patch("propdesk.feeds.build_opener", return_value=opener):
                with self.assertRaises(ValueError):
                    get_history("AAPL", now=NOW)

    def test_redirects_allow_only_expected_https_hosts_without_credentials(self):
        redirect = _SafeRedirect()
        request = Request("https://query1.finance.yahoo.com/v8/finance/chart/AAPL")
        good = redirect.redirect_request(request, None, 302, "Found", {}, "https://query2.finance.yahoo.com/v8/finance/chart/AAPL")
        self.assertEqual(urlsplit(good.full_url).hostname, "query2.finance.yahoo.com")
        for target in ("http://query1.finance.yahoo.com/a", "https://evil.example/a", "https://query1.finance.yahoo.com.evil.example/a",
                       "https://secret@query1.finance.yahoo.com/a", "https://query1.finance.yahoo.com:444/a", "https://query1.finance.yahoo.com:bad/a"):
            with self.assertRaisesRegex(ValueError, "разрешённых"):
                redirect.redirect_request(request, None, 302, "Found", {}, target)


if __name__ == "__main__":
    unittest.main()
