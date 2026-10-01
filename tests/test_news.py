import copy
import hashlib
import io
import json
import os
import ssl
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError
from urllib.request import Request

from propdesk.news import (CalendarFeed, MAX_RESPONSE_BYTES, SOURCE_URL, _SafeRedirect, _clock,
                           _decode, _fetch, parse_calendar)
from propdesk.setups import _context


NOW = datetime(2026, 10, 1, 12, 15, tzinfo=timezone.utc)


def fixture():
    return [
        {"title": "Final Manufacturing PMI", "country": "EUR", "date": "2026-10-01T04:00:00-04:00",
         "impact": "Medium", "forecast": "51.0", "previous": "50.7", "actual": "51.2"},
        {"title": "Unemployment Claims", "country": "USD", "date": "2026-10-01T08:30:00-04:00",
         "impact": "High", "forecast": "218K", "previous": "220K"},
    ]


def raw_fixture(rows=None):
    return json.dumps(fixture() if rows is None else rows).encode("utf-8")


class CalendarParsing(unittest.TestCase):
    def test_offsets_normalized_and_knowledge_time_is_actual_retrieval(self):
        calendar = parse_calendar(fixture(), retrieved_at=NOW)
        self.assertEqual(calendar["events"][1]["time"], "2026-10-01T12:30:00Z")
        for event in calendar["events"]:
            self.assertEqual(event["known_at"], "2026-10-01T12:15:00Z")
            self.assertEqual(set(event), {"time", "known_at", "title", "currency", "impact"})
        self.assertEqual(calendar["coverage"]["start"], "2026-09-27T04:00:00Z")
        self.assertEqual(calendar["coverage"]["end_exclusive"], "2026-10-04T04:00:00Z")

    def test_fractional_timestamps_are_chronological_without_string_sort_bias(self):
        rows = fixture()
        rows[0]["date"] = "2026-10-01T08:30:00.100000-04:00"
        events = parse_calendar(rows, retrieved_at=NOW)["events"]
        self.assertEqual(events[0]["time"], "2026-10-01T12:30:00Z")
        self.assertEqual(events[1]["time"], "2026-10-01T12:30:00.100000Z")

    def test_missing_empty_duplicate_oversized_or_mixed_week_never_clear_news(self):
        for rows in (None, {}, [], [None], fixture() * 101, [fixture()[0], fixture()[0]]):
            with self.subTest(rows_type=type(rows).__name__):
                with self.assertRaises(ValueError):
                    parse_calendar(rows, retrieved_at=NOW)
        rows = fixture()
        rows[0]["date"] = "2026-09-24T04:00:00-04:00"
        with self.assertRaisesRegex(ValueError, "смешанные недели"):
            parse_calendar(rows, retrieved_at=NOW)
        rows = fixture()
        for row in rows:
            row["date"] = row["date"].replace("2026-10-01", "2026-09-24")
        with self.assertRaisesRegex(ValueError, "истёкшей неделе"):
            parse_calendar(rows, retrieved_at=NOW)

    def test_ambiguous_dates_unsupported_currency_impact_and_unsafe_titles_fail_closed(self):
        for key, value in (
            ("date", "2026-10-01"), ("date", "2026-10-01T08:30:00"),
            ("date", "2026-10-01T08:30:00-00:00"), ("date", "2026-10-01T08:30:00+01:60"),
            ("date", "2026-10-01T08:30:00+14:30"), ("date", "Tentative"),
            ("date", "0001-01-01T00:00:00+14:00"), ("date", "9999-12-31T23:59:59-14:00"),
            ("date", "2026-10-01T08:30:00Z\n"), ("country", "XXX"), ("country", "USD\n"),
            ("impact", "Unknown"), ("title", ""),
            ("title", "A" * 257), ("title", "<script>x</script>"), ("title", "CPI\u202eevil"),
            ("title", "CPI\x00"), ("title", "\ud800"), ("country", 1),
        ):
            rows = fixture()
            rows[0][key] = value
            with self.subTest(key=key, value=repr(value)):
                with self.assertRaises(ValueError):
                    parse_calendar(rows, retrieved_at=NOW)
        with self.assertRaises(ValueError):
            parse_calendar(fixture(), retrieved_at=NOW.replace(tzinfo=None))

    def test_nonfinite_duplicate_json_fields_and_deep_invalid_json_reject(self):
        for raw in (b'[{"title":"CPI", "forecast":NaN}]', b'[{"forecast":1e500}]',
                    b'[{"title":"one", "title":"two"}]', b'\xff', b'{}' * 2,
                    b'[' * 2000 + b']' * 2000):
            with self.subTest(raw_prefix=raw[:50]):
                with self.assertRaises(ValueError):
                    _decode(raw)
        with self.assertRaises(ValueError):
            _decode(b" " * (MAX_RESPONSE_BYTES + 1))

    def test_known_holiday_rows_are_disclosed_but_not_economic_or_session_signals(self):
        rows = fixture() + [{"title": "Bank Holiday", "country": "CNY",
                             "date": "2026-10-01T00:00:00-04:00", "impact": "Holiday"},
                            {"title": "Informational Event", "country": "All",
                             "date": "2026-10-01T01:00:00-04:00", "impact": "Non-Economic"}]
        calendar = parse_calendar(rows, retrieved_at=NOW)
        self.assertEqual(len(calendar["events"]), 2)
        self.assertEqual(len(calendar["rows"]), 4)
        self.assertTrue(any("Holiday/Non-Economic" in warning for warning in calendar["warnings"]))
        with self.assertRaisesRegex(ValueError, "Нет событий"):
            parse_calendar(rows[2:], retrieved_at=NOW)
        rows[2]["date"] = "All Day"
        with self.assertRaises(ValueError):
            parse_calendar(rows, retrieved_at=NOW)

    def test_week_boundary_and_multiple_explicit_offsets_are_conservative(self):
        rows = fixture()
        rows[0]["date"] = "2026-10-01T04:00:00-05:00"
        coverage = parse_calendar(rows, retrieved_at=NOW)["coverage"]
        self.assertEqual(coverage["start"], "2026-09-27T05:00:00Z")
        self.assertEqual(coverage["end_exclusive"], "2026-10-04T04:00:00Z")
        boundary = datetime(2026, 9, 27, 4, 30, tzinfo=timezone.utc)
        with self.assertRaises(ValueError):
            parse_calendar(rows, retrieved_at=boundary)


class CalendarCache(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name) / "state"
        self.feed = CalendarFeed(self.directory)

    def tearDown(self):
        self.temporary.cleanup()

    def prime(self, now=NOW):
        with patch("propdesk.news._fetch", return_value=raw_fixture()) as fetch:
            status = self.feed.refresh(now)
            fetch.assert_called_once_with()
        self.assertTrue(status["confirmed"])
        return status

    def test_constructor_status_context_are_read_only_no_network_no_empty_confirmation(self):
        with patch("propdesk.news._fetch") as fetch:
            self.assertFalse(self.feed.status(NOW)["confirmed"])
            self.assertFalse(self.feed.context(NOW)["confirmed"])
            fetch.assert_not_called()
        self.assertFalse(self.directory.exists())
        self.assertEqual(self.feed.context(NOW)["events"], [])

    def test_atomic_cache_content_hash_and_reload_retain_full_provenance(self):
        status = self.prime()
        self.assertEqual(status["body_sha256"], hashlib.sha256(raw_fixture()).hexdigest())
        stored = json.loads(self.feed.path.read_text())
        self.assertEqual(stored["retrieved_at"], "2026-10-01T12:15:00Z")
        self.assertEqual(stored["source"], SOURCE_URL)
        self.assertNotIn("forecast", json.dumps(stored["rows"]))
        self.assertEqual(list(self.directory.iterdir()), [self.feed.path])
        reloaded = CalendarFeed(self.directory).context(NOW + timedelta(minutes=3))
        self.assertTrue(reloaded["confirmed"])
        self.assertEqual(len(reloaded["events"]), 2)
        self.assertEqual(reloaded["generation"], "provider")
        self.assertEqual(reloaded["events"][1]["known_at"], stored["retrieved_at"])

    def test_refresh_ttl_skips_network_and_exact_freshness_boundary(self):
        self.prime()
        with patch("propdesk.news._fetch") as fetch:
            self.assertTrue(self.feed.refresh(NOW + timedelta(minutes=59))["confirmed"])
            fetch.assert_not_called()
        self.assertTrue(self.feed.context(NOW + timedelta(hours=6))["confirmed"])
        stale = self.feed.context(NOW + timedelta(hours=6, microseconds=1))
        self.assertFalse(stale["confirmed"])
        self.assertEqual(stale["events"], [])

    def test_failed_fetch_or_malformed_response_preserves_original_cache_age_and_events(self):
        self.prime()
        original_bytes = self.feed.path.read_bytes()
        later = NOW + timedelta(hours=1)
        with patch("propdesk.news._fetch", side_effect=ValueError("Календарь не получен: HTTP 403")):
            status = self.feed.refresh(later)
        self.assertTrue(status["confirmed"])
        self.assertEqual(status["retrieved_at"], "2026-10-01T12:15:00Z")
        self.assertEqual(status["age_seconds"], 3600)
        self.assertIn("HTTP 403", status["last_error"])
        self.assertEqual(self.feed.path.read_bytes(), original_bytes)
        with patch("propdesk.news._fetch", return_value=b"[]"):
            status = self.feed.refresh(NOW + timedelta(hours=2))
        self.assertTrue(status["confirmed"])
        self.assertEqual(self.feed.path.read_bytes(), original_bytes)
        self.assertEqual(self.feed.context(NOW + timedelta(hours=2))["events"][1]["known_at"], "2026-10-01T12:15:00Z")

    def test_failed_empty_first_fetch_has_no_cache_and_is_throttled(self):
        with patch("propdesk.news._fetch", return_value=b"[]") as fetch:
            self.assertFalse(self.feed.refresh(NOW)["confirmed"])
            self.assertFalse(self.feed.refresh(NOW + timedelta(minutes=10))["confirmed"])
            self.assertEqual(fetch.call_count, 1)
        self.assertFalse(self.directory.exists())

    def test_failed_transport_rechecks_freshness_at_completion(self):
        self.prime()
        moments = iter([NOW + timedelta(hours=6, seconds=-1), NOW + timedelta(hours=6, seconds=1)])
        def clock(value):
            return next(moments) if value is None else _clock(value)
        with patch("propdesk.news._clock", side_effect=clock), patch("propdesk.news._fetch", side_effect=ValueError("HTTPS failure")):
            status = self.feed.refresh()
        self.assertFalse(status["confirmed"])
        self.assertEqual(status["state"], "stale")
        self.assertEqual(status["age_seconds"], 21601)

    def test_expired_week_and_future_cache_stamp_fail_closed(self):
        sunday = datetime(2026, 10, 4, 3, 45, tzinfo=timezone.utc)
        self.prime(sunday)
        self.assertTrue(self.feed.context(sunday)["confirmed"])
        self.assertFalse(self.feed.context(sunday + timedelta(minutes=15))["confirmed"])
        self.assertFalse(self.feed.context(sunday - timedelta(seconds=1))["confirmed"])

    def test_corrupt_wrong_source_and_mutated_cache_not_accepted(self):
        self.prime()
        original = json.loads(self.feed.path.read_text())
        for mutation in ("source", "row", "hash", "coverage", "nonfinite"):
            cache = copy.deepcopy(original)
            if mutation == "source":
                cache["source"] = "https://evil.example/"
            elif mutation == "row":
                cache["rows"][0]["date"] = "2026-10-02T04:00:00-04:00"
            elif mutation == "hash":
                cache["body_sha256"] = "bad"
            elif mutation == "coverage":
                cache["coverage"]["end_exclusive"] = "2027-01-01T00:00:00Z"
            else:
                cache["age"] = float("nan")
            self.feed.path.write_text(json.dumps(cache))
            with self.subTest(mutation=mutation):
                self.assertFalse(self.feed.context(NOW)["confirmed"])

    @unittest.skipUnless(hasattr(os, "symlink"), "requires symlinks")
    def test_symlink_cache_is_neither_read_nor_overwritten(self):
        self.directory.mkdir()
        target = Path(self.temporary.name) / "other.json"
        target.write_text("private sentinel")
        self.feed.path.symlink_to(target)
        with patch("propdesk.news._fetch", return_value=raw_fixture()):
            self.assertFalse(self.feed.refresh(NOW)["confirmed"])
        self.assertEqual(target.read_text(), "private sentinel")
        self.assertTrue(self.feed.path.is_symlink())

    def test_context_integrates_known_time_blackout_and_unknown_stale_scope(self):
        self.prime()
        context = _context({"news": self.feed.context(NOW)}, NOW, [])
        self.assertEqual(context["news_state"], "blackout")
        self.assertEqual(context["news_blackout_events"][0]["currency"], "USD")
        decision = NOW + timedelta(hours=7)
        context = _context({"news": self.feed.context(decision)}, decision, [])
        self.assertEqual(context["news_state"], "unknown")


class CalendarTransport(unittest.TestCase):
    @staticmethod
    def response(raw=None, url=SOURCE_URL, code=200):
        response = io.BytesIO(raw_fixture() if raw is None else raw)
        response.geturl = lambda: url
        response.getcode = lambda: code
        return response

    def test_fixed_url_timeout_tls_and_no_secret_headers(self):
        opener = Mock()
        opener.open.return_value = self.response()
        with patch("propdesk.news.build_opener", return_value=opener) as builder:
            self.assertEqual(_fetch(), raw_fixture())
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, SOURCE_URL)
        self.assertEqual(opener.open.call_args.kwargs["timeout"], 10)
        tls = builder.call_args.args[1]._context
        self.assertEqual(tls.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(tls.check_hostname)
        self.assertIsNone(request.get_header("Authorization"))
        self.assertIsNone(request.get_header("Cookie"))

    def test_redirect_final_url_and_response_size_are_bounded(self):
        for url in ("http://nfs.faireconomy.media/x", "https://evil.example/x",
                    "https://nfs.faireconomy.media.evil.example/x", "https://nfs.faireconomy.media:444/x",
                    "https://user:secret@nfs.faireconomy.media/x", "https://nfs.faireconomy.media/x#fragment"):
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    _SafeRedirect().redirect_request(Request(SOURCE_URL), None, 302, "", {}, url)
                opener = Mock()
                opener.open.return_value = self.response(url=url)
                with patch("propdesk.news.build_opener", return_value=opener):
                    with self.assertRaises(ValueError):
                        _fetch()
        opener = Mock()
        opener.open.return_value = self.response(raw=b" " * (MAX_RESPONSE_BYTES + 1))
        with patch("propdesk.news.build_opener", return_value=opener):
            with self.assertRaisesRegex(ValueError, "1 MiB"):
                _fetch()
        opener.open.return_value = self.response(code=204)
        with patch("propdesk.news.build_opener", return_value=opener):
            with self.assertRaises(ValueError):
                _fetch()

    def test_http_tls_timeout_and_network_details_are_redacted(self):
        errors = [HTTPError(SOURCE_URL, 403, "SECRET", {}, None),
                  URLError("Authorization: SECRET"), URLError(ssl.SSLError("SECRET")),
                  URLError(TimeoutError("SECRET")), TimeoutError("SECRET"), OSError("SECRET")]
        for error in errors:
            opener = Mock()
            opener.open.side_effect = error
            with self.subTest(error=type(error).__name__):
                with patch("propdesk.news.build_opener", return_value=opener):
                    with self.assertRaises(ValueError) as caught:
                        _fetch()
                self.assertNotIn("SECRET", str(caught.exception))

    def test_redirects_and_slow_body_share_transport_deadline(self):
        request = Request(SOURCE_URL)
        request.timeout = 10
        redirect = _SafeRedirect(deadline=10)
        with patch("propdesk.news.time.monotonic", return_value=7):
            redirected = redirect.redirect_request(request, None, 302, "", {}, SOURCE_URL)
        self.assertEqual(request.timeout, 3)
        self.assertEqual(redirected.full_url, SOURCE_URL)
        with patch("propdesk.news.time.monotonic", return_value=11):
            with self.assertRaises(TimeoutError):
                redirect.redirect_request(request, None, 302, "", {}, SOURCE_URL)
        clock = [0]
        response = self.response()
        def slow_read(size):
            clock[0] += 4
            return b" "
        response.read1 = slow_read
        opener = Mock()
        opener.open.return_value = response
        with patch("propdesk.news.build_opener", return_value=opener), patch("propdesk.news.time.monotonic", side_effect=lambda: clock[0]):
            with self.assertRaisesRegex(ValueError, "таймаут"):
                _fetch()


class CalendarWorker(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.feed = CalendarFeed(Path(self.temporary.name) / "state")

    def tearDown(self):
        self.assertTrue(self.feed.stop(timeout=1))
        self.temporary.cleanup()

    @staticmethod
    def wait_until(check, seconds=1):
        deadline = time.monotonic() + seconds
        while not check():
            if time.monotonic() >= deadline:
                raise AssertionError("Background calendar condition did not complete")
            threading.Event().wait(.005)

    def test_disabled_worker_is_explicit_non_daemon_and_stops_without_further_callbacks(self):
        checked = threading.Event()
        calls = []
        def enabled():
            calls.append(True)
            checked.set()
            return False
        self.assertIsNone(self.feed._thread)
        with patch("propdesk.news._fetch") as fetch:
            self.assertTrue(self.feed.start(enabled, poll_interval=.02))
            self.assertTrue(checked.wait(1))
            thread = self.feed._thread
            self.assertFalse(thread.daemon)
            self.assertTrue(self.feed.status(NOW)["worker_running"])
            self.assertFalse(self.feed.start(enabled, poll_interval=.02))
            self.assertIs(self.feed._thread, thread)
            self.assertTrue(self.feed.stop(timeout=1))
            before = len(calls)
            threading.Event().wait(.04)
            self.assertEqual(len(calls), before)
            fetch.assert_not_called()
        self.assertFalse(self.feed.status(NOW)["worker_running"])

    def test_enabling_refreshes_once_per_hour_disabling_suspends_network(self):
        active = threading.Event()
        stamp = [NOW]
        checks = []
        def enabled():
            checks.append(True)
            return active.is_set()
        def clock(value):
            return stamp[0] if value is None else _clock(value)
        with patch("propdesk.news._clock", side_effect=clock), patch("propdesk.news._fetch", return_value=raw_fixture()) as fetch:
            self.feed.start(enabled, poll_interval=.02)
            self.wait_until(lambda: len(checks) >= 2)
            fetch.assert_not_called()
            active.set()
            self.wait_until(lambda: fetch.call_count == 1 and self.feed.status()["confirmed"])
            active.clear()
            checked = len(checks)
            stamp[0] = NOW + timedelta(hours=1, seconds=1)
            self.wait_until(lambda: len(checks) >= checked + 3)
            self.assertEqual(fetch.call_count, 1)
            active.set()
            self.wait_until(lambda: fetch.call_count == 2 and self.feed.status()["retrieved_at"] == "2026-10-01T13:15:01Z")
            checked = len(checks)
            self.wait_until(lambda: len(checks) >= checked + 3)
            self.assertEqual(fetch.call_count, 2)
            self.assertTrue(self.feed.stop(timeout=1))

    def test_stop_after_enabled_callback_prevents_refresh_and_can_join_again(self):
        entered, release = threading.Event(), threading.Event()
        def enabled():
            entered.set()
            release.wait(1)
            return True
        with patch("propdesk.news._fetch") as fetch:
            try:
                self.feed.start(enabled, poll_interval=.02)
                self.assertTrue(entered.wait(1))
                self.assertFalse(self.feed.stop(timeout=.01))
                self.assertTrue(self.feed.status(NOW)["worker_stopping"])
            finally:
                release.set()
                self.assertTrue(self.feed.stop(timeout=1))
            fetch.assert_not_called()

    def test_explicit_and_background_refresh_share_mutex_and_one_hour_ttl(self):
        entered, release = threading.Event(), threading.Event()
        errors = []
        def fetch():
            entered.set()
            release.wait(1)
            return raw_fixture()
        def clock(value):
            return NOW if value is None else _clock(value)
        def explicit():
            try:
                self.feed.refresh(NOW)
            except Exception as error:
                errors.append(error)
        with patch("propdesk.news._clock", side_effect=clock), patch("propdesk.news._fetch", side_effect=fetch) as request:
            other = None
            try:
                self.feed.start(lambda: True, poll_interval=.02)
                self.assertTrue(entered.wait(1))
                other = threading.Thread(target=explicit, daemon=False)
                other.start()
            finally:
                release.set()
                if other:
                    other.join(1)
                self.assertTrue(self.feed.stop(timeout=1))
            self.assertFalse(other.is_alive())
            self.assertEqual(errors, [])
            self.assertEqual(request.call_count, 1)
            self.assertTrue(self.feed.status()["confirmed"])

    def test_callback_error_is_redacted_and_invalid_lifecycle_arguments_reject(self):
        def bad_enabled():
            raise RuntimeError("Authorization: SECRET")
        with patch("propdesk.news._fetch") as fetch:
            self.feed.start(bad_enabled, poll_interval=.02)
            self.wait_until(lambda: self.feed.status(NOW)["worker_error"] is not None)
            status = self.feed.status(NOW)
            self.assertFalse(status["confirmed"])
            self.assertNotIn("SECRET", json.dumps(status))
            self.assertTrue(self.feed.stop(timeout=1))
            fetch.assert_not_called()
        for value in (0, -.1, True, "30", float("nan"), float("inf"), 301, 10 ** 500):
            with self.subTest(poll_interval=repr(value)):
                with self.assertRaises(ValueError):
                    self.feed.start(lambda: True, poll_interval=value)
        with self.assertRaises(ValueError):
            self.feed.start(True)
        for value in (-1, True, "12", float("nan"), float("inf"), 31, 10 ** 500):
            with self.subTest(timeout=repr(value)):
                with self.assertRaises(ValueError):
                    self.feed.stop(timeout=value)


if __name__ == "__main__":
    unittest.main()
