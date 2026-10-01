"""Default Windows profiles and IANA DST without a system tz database."""
from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from propdesk import timezones


class TimezoneTests(unittest.TestCase):
    def setUp(self):
        timezones._cached_timezone.cache_clear()
        self.addCleanup(timezones._cached_timezone.cache_clear)

    def test_utc_aliases_work_without_system_data(self):
        with patch.object(timezones, "_system_timezone", side_effect=ZoneInfoNotFoundError):
            for key in ("UTC", "Etc/UTC", "GMT", "Etc/GMT", "Zulu", "Etc/Zulu"):
                resolved = timezones.timezone_for(key)
                self.assertIs(resolved, timezone.utc)
                self.assertEqual(datetime(2026, 1, 1, tzinfo=resolved).utcoffset(), timedelta(0))

    def test_host_timezone_is_preferred_including_other_zones(self):
        available = timezone(timedelta(hours=9))
        with patch.object(timezones, "_system_timezone", return_value=available) as host:
            self.assertIs(timezones.timezone_for("Asia/Tokyo"), available)
            self.assertIs(timezones.timezone_for("Asia/Tokyo"), available)
        host.assert_called_once_with("Asia/Tokyo")

    def test_bundled_zones_preserve_winter_and_summer_offsets(self):
        expected = {"Europe/Prague": (1, 2), "Europe/Kyiv": (2, 3),
                    "Europe/Kiev": (2, 3), "America/New_York": (-5, -4), "America/Chicago": (-6, -5)}
        with patch.object(timezones, "_system_timezone", side_effect=ZoneInfoNotFoundError):
            for key, (winter, summer) in expected.items():
                with self.subTest(zone=key):
                    zone = timezones.timezone_for(key)
                    self.assertIsInstance(zone, ZoneInfo)
                    self.assertEqual(zone.key, key)
                    self.assertEqual(datetime(2026, 1, 15, 12, tzinfo=zone).utcoffset(), timedelta(hours=winter))
                    self.assertEqual(datetime(2026, 7, 15, 12, tzinfo=zone).utcoffset(), timedelta(hours=summer))

    def test_prague_spring_transition_and_new_york_fall_fold(self):
        with patch.object(timezones, "_system_timezone", side_effect=ZoneInfoNotFoundError):
            prague = timezones.timezone_for("Europe/Prague")
            before = datetime(2026, 3, 29, 0, 30, tzinfo=timezone.utc).astimezone(prague)
            after = datetime(2026, 3, 29, 1, 30, tzinfo=timezone.utc).astimezone(prague)
            self.assertEqual((before.hour, before.utcoffset()), (1, timedelta(hours=1)))
            self.assertEqual((after.hour, after.utcoffset()), (3, timedelta(hours=2)))
            new_york = timezones.timezone_for("America/New_York")
            first = datetime(2026, 11, 1, 5, 30, tzinfo=timezone.utc).astimezone(new_york)
            second = datetime(2026, 11, 1, 6, 30, tzinfo=timezone.utc).astimezone(new_york)
            self.assertEqual((first.hour, first.fold, first.utcoffset()), (1, 0, timedelta(hours=-4)))
            self.assertEqual((second.hour, second.fold, second.utcoffset()), (1, 1, timedelta(hours=-5)))

    def test_unknown_key_requires_host_data_without_silent_utc_substitution(self):
        with patch.object(timezones, "_system_timezone", side_effect=ZoneInfoNotFoundError):
            with self.assertRaises(ZoneInfoNotFoundError):
                timezones.timezone_for("Asia/Unlisted")

    def test_invalid_keys_cannot_read_paths(self):
        with patch.object(timezones, "_system_timezone") as host:
            for key in ("../secret", "Europe/../../secret", "/etc/passwd", "Europe\\Prague",
                        "C:/Windows/system.ini", "Europe//Prague", "UTC\x00", "", None, [], "A" * 129):
                with self.subTest(key_type=type(key).__name__):
                    with self.assertRaises(ValueError):
                        timezones.timezone_for(key)
            host.assert_not_called()

    def test_default_rule_profiles_initialize_without_system_timezone_data(self):
        from propdesk.risk import default_profiles, normalize_profile
        with patch.object(timezones, "_system_timezone", side_effect=ZoneInfoNotFoundError) as host:
            profiles = default_profiles()
            self.assertEqual(len(profiles), 3)
            self.assertTrue(all(profile["daily_reset_timezone"] == "UTC" for profile in profiles))
            for key in ("Europe/Prague", "Europe/Kyiv", "America/New_York", "America/Chicago"):
                self.assertEqual(normalize_profile({"daily_reset_timezone": key})["daily_reset_timezone"], key)
            self.assertEqual(host.call_count, 5)

    def test_bundled_timezone_controls_real_daily_limit_reset(self):
        from propdesk.compliance import evaluate
        from propdesk.risk import default_profiles
        curve = [
            {"time": "2026-01-01T21:00:00Z", "equity": 103000, "balance": 103000,
             "worst_equity": 103000, "best_equity": 103000},
            {"time": "2026-01-01T22:00:00Z", "equity": 98500, "balance": 98500,
             "worst_equity": 97999, "best_equity": 103000},
        ]
        with patch.object(timezones, "_system_timezone", side_effect=ZoneInfoNotFoundError) as host:
            profile = {**default_profiles()[0], "daily_reset_timezone": "Europe/Kyiv"}
            result = evaluate(curve, profile)
        self.assertEqual(result["status"], "breach")
        self.assertEqual(result["breaches"][0]["type"], "daily")
        self.assertEqual(result["breaches"][0]["floor"], 98000)
        self.assertEqual(host.call_count, 2)


if __name__ == "__main__":
    unittest.main()
