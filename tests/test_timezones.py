"""Default Windows profiles and IANA DST without a system tz database."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch
import zoneinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from propdesk import timezones
from propdesk import timezone_bootstrap as bootstrap


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


class DirectZoneInfoBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.previous_path = tuple(zoneinfo.TZPATH)
        self.addCleanup(zoneinfo.reset_tzpath, self.previous_path)
        self.addCleanup(ZoneInfo.clear_cache)
        ZoneInfo.clear_cache()

    def empty_host(self):
        zoneinfo.reset_tzpath(())
        ZoneInfo.clear_cache()
        # Force the Windows-without-tzdata case even if the test runner has the
        # optional PyPI database installed. Production uses only public APIs.
        return patch("zoneinfo._common.load_tzdata", side_effect=ZoneInfoNotFoundError)

    def test_existing_host_lookup_preserves_tzpath(self):
        before = tuple(zoneinfo.TZPATH)
        expected = ZoneInfo("America/New_York")
        with patch.object(zoneinfo, "reset_tzpath") as reset:
            self.assertIs(bootstrap.ensure_new_york_timezone(), expected)
        reset.assert_not_called()
        self.assertEqual(tuple(zoneinfo.TZPATH), before)

    def test_missing_host_registers_existing_tzif_once_and_preserves_paths(self):
        zoneinfo.reset_tzpath((str(Path(__file__).resolve().parent / "nonexistent-tz-root"),))
        ZoneInfo.clear_cache()
        prior = tuple(zoneinfo.TZPATH)
        with patch("zoneinfo._common.load_tzdata", side_effect=ZoneInfoNotFoundError):
            first = bootstrap.ensure_new_york_timezone()
            self.assertIs(first, ZoneInfo("America/New_York"))
            self.assertIs(first, bootstrap.ensure_new_york_timezone())
        self.assertEqual(tuple(zoneinfo.TZPATH), (*prior, str(bootstrap._BUNDLED_ROOT)))

    def test_empty_host_resolves_real_2024_2025_2026_dst_transitions(self):
        transitions = ((2024, 3, 10, 11, 3), (2025, 3, 9, 11, 2), (2026, 3, 8, 11, 1))
        with self.empty_host():
            bootstrap.ensure_new_york_timezone()
            ny = ZoneInfo("America/New_York")
            for year, spring_month, spring_day, fall_month, fall_day in transitions:
                with self.subTest(year=year):
                    before = datetime(year, spring_month, spring_day, 6, 59, tzinfo=timezone.utc).astimezone(ny)
                    after = datetime(year, spring_month, spring_day, 7, 0, tzinfo=timezone.utc).astimezone(ny)
                    self.assertEqual((before.hour, before.minute, before.utcoffset()), (1, 59, timedelta(hours=-5)))
                    self.assertEqual((after.hour, after.minute, after.utcoffset()), (3, 0, timedelta(hours=-4)))
                    before = datetime(year, fall_month, fall_day, 5, 59, tzinfo=timezone.utc).astimezone(ny)
                    after = datetime(year, fall_month, fall_day, 6, 0, tzinfo=timezone.utc).astimezone(ny)
                    self.assertEqual((before.hour, before.minute, before.fold, before.utcoffset()), (1, 59, 0, timedelta(hours=-4)))
                    self.assertEqual((after.hour, after.minute, after.fold, after.utcoffset()), (1, 0, 1, timedelta(hours=-5)))

    def test_ny_lunch_boundaries_follow_real_winter_summer_offsets(self):
        with self.empty_host():
            bootstrap.ensure_new_york_timezone()
            ny = ZoneInfo("America/New_York")
            for year in (2024, 2025, 2026):
                for month, opening in ((1, 16), (7, 15)):
                    for hour, minute, expected in ((opening - 1, 59, False), (opening, 0, True),
                                                    (opening + 1, 59, True), (opening + 2, 0, False)):
                        stamp = datetime(year, month, 15, hour, minute, tzinfo=timezone.utc).astimezone(ny)
                        with self.subTest(year=year, month=month, hour=hour, minute=minute):
                            self.assertEqual(11 <= stamp.hour < 13, expected)

    def test_unbundled_unknown_zone_still_fails(self):
        with self.empty_host():
            bootstrap.ensure_new_york_timezone()
            with self.assertRaises(ZoneInfoNotFoundError):
                ZoneInfo("Asia/Unlisted")

    def test_package_bootstrap_precedes_frozen_engine_import_in_fresh_process(self):
        code = """
import json,zoneinfo
from unittest.mock import patch
zoneinfo.reset_tzpath(())
zoneinfo.ZoneInfo.clear_cache()
with patch('zoneinfo._common.load_tzdata',side_effect=zoneinfo.ZoneInfoNotFoundError):
 import propdesk
 import propdesk.liquidity
 from datetime import datetime,timezone
 ny=zoneinfo.ZoneInfo('America/New_York')
 print(json.dumps({'zone':ny.key,'offset':datetime(2026,7,15,tzinfo=timezone.utc).astimezone(ny).utcoffset().total_seconds(),
                  'frozen_engine_zone':propdesk.liquidity._NY.key}))
"""
        process = subprocess.run([sys.executable, "-c", code], cwd=Path(__file__).resolve().parents[1],
                                 capture_output=True, text=True, timeout=20)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(json.loads(process.stdout), {"zone": "America/New_York", "offset": -14400,
                                                      "frozen_engine_zone": "America/New_York"})


if __name__ == "__main__":
    unittest.main()
