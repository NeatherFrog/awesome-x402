"""Known-clock context boundaries, native parent parity and heldout stopping."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from propdesk import native_liquidity_context as context, liquidity_native as parent
from scripts import research_native_liquidity_context as driver


def clock_event(sweep, signal):
    return {"sweep_time": sweep, "signal_time": signal, "reason": "synthetic fixture", "symbol": "BTCUSDT"}


def fixture(minutes=15, name="ny_lunch"):
    base = datetime(2024, 3, 6, tzinfo=timezone.utc)
    rows = [{"time": parent.stamp_text(base + timedelta(minutes=5 * i)), "open": 101,
             "high": 102, "low": 100, "close": 101, "volume": 1} for i in range(6 * 288)]
    zone = context.pinned_timezone(context.CONTEXTS[name]["zone"])
    sweep_close = datetime(2024, 3, 11, 12 if name == "ny_lunch" else 8, tzinfo=zone).astimezone(timezone.utc)
    start = int(((sweep_close - timedelta(minutes=minutes)) - base).total_seconds() / 300)
    count = minutes // 5
    blocks = ((101, 102, 98, 101), (101, 104.1, 101, 104), (104, 104.5, 103, 104))
    for offset, values in enumerate(blocks):
        for index in range(start + offset * count, start + (offset + 1) * count):
            rows[index].update(dict(zip(("open", "high", "low", "close"), values)))
    funding = {symbol: [] for symbol in parent.SYMBOLS}
    return parent.Features({symbol: deepcopy(rows) for symbol in parent.SYMBOLS}, funding)


class LiquidityContextTests(unittest.TestCase):
    def test48_registered_variants_only_fixed_valid_parent_rules(self):
        variants = context.grid()
        self.assertEqual(len(variants), 48)
        self.assertEqual(len({row["id"] for row in variants}), 48)
        self.assertEqual({row["risk_fraction"] for row in variants}, {.0025, .005, .01})
        for row in variants:
            self.assertIn(row["parent_variant"], parent.grid())
            self.assertEqual(row["parent_variant"]["reward_risk"], 2.5)
            self.assertEqual(row["parent_variant"]["expiry"], 4)
            self.assertFalse(row["parent_variant"]["trend_context"])

    def test_new_york_inclusive_start_exclusive_end_and_confirmation_cutoff(self):
        for sweep, signal, expected in (
                ("2024-01-08T16:00:00Z", "2024-01-08T17:00:00Z", True),
                ("2024-01-08T15:59:59Z", "2024-01-08T17:00:00Z", False),
                ("2024-01-08T18:59:59Z", "2024-01-08T21:59:59Z", True),
                ("2024-01-08T19:00:00Z", "2024-01-08T20:00:00Z", False),
                ("2024-01-08T18:00:00Z", "2024-01-08T22:00:00Z", False)):
            with self.subTest(sweep=sweep, signal=signal):
                self.assertEqual(context.accepts_event(clock_event(sweep, signal), "ny_lunch"), expected)

    def test_london_inclusive_start_exclusive_end_and_confirmation_cutoff(self):
        for sweep, signal, expected in (
                ("2024-01-08T07:00:00Z", "2024-01-08T08:00:00Z", True),
                ("2024-01-08T06:59:59Z", "2024-01-08T08:00:00Z", False),
                ("2024-01-08T09:59:59Z", "2024-01-08T12:59:59Z", True),
                ("2024-01-08T10:00:00Z", "2024-01-08T11:00:00Z", False),
                ("2024-01-08T08:00:00Z", "2024-01-08T13:00:00Z", False)):
            self.assertEqual(context.accepts_event(clock_event(sweep, signal), "london"), expected)

    def test_dst_mismatch_weeks_and_2025_2026_summer(self):
        for year in (2024, 2025, 2026):
            # Monday after US spring change but before UK change.
            date = {2024: "03-11", 2025: "03-10", 2026: "03-09"}[year]
            self.assertTrue(context.accepts_event(clock_event(f"{year}-{date}T15:00:00Z", f"{year}-{date}T16:00:00Z"), "ny_lunch"))
            self.assertFalse(context.accepts_event(clock_event(f"{year}-{date}T06:00:00Z", f"{year}-{date}T08:00:00Z"), "london"))
            self.assertTrue(context.accepts_event(clock_event(f"{year}-{date}T07:00:00Z", f"{year}-{date}T08:00:00Z"), "london"))
        self.assertTrue(context.accepts_event(clock_event("2025-07-07T06:00:00Z", "2025-07-07T08:00:00Z"), "london"))
        self.assertFalse(context.accepts_event(clock_event("2025-07-07T09:00:00Z", "2025-07-07T10:00:00Z"), "london"))

    def test_weekends_same_local_date_and_known_sweep_chronology(self):
        self.assertFalse(context.accepts_event(clock_event("2024-01-06T16:00:00Z", "2024-01-06T18:00:00Z"), "ny_lunch"))
        self.assertFalse(context.accepts_event(clock_event("2024-01-08T16:00:00Z", "2024-01-09T16:00:00Z"), "ny_lunch"))
        with self.assertRaisesRegex(ValueError, "future sweep"):
            context.accepts_event(clock_event("2024-01-08T17:00:00Z", "2024-01-08T16:00:00Z"), "ny_lunch")
        with self.assertRaises(ValueError):
            context.accepts_event(clock_event("2024-01-08T16:00:00Z", "2024-01-08T18:00:00Z"), "unknown")

    def test_pinned_tz_ignores_host_database_and_detects_changed_bytes(self):
        context.pinned_timezone.cache_clear()
        zone = Mock(side_effect=AssertionError("Host zone lookup forbidden"))
        zone.from_file.side_effect = context.ZoneInfo.from_file
        with patch.object(context, "ZoneInfo", zone):
            self.assertTrue(context.accepts_event(clock_event("2025-07-07T15:00:00Z", "2025-07-07T16:00:00Z"), "ny_lunch"))
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / "America/New_York"
            path.parent.mkdir(parents=True)
            path.write_bytes(b"wrong bytes")
            context.pinned_timezone.cache_clear()
            with patch.object(context, "TZ_ROOT", Path(name)), self.assertRaisesRegex(ValueError, "fingerprint"):
                context.pinned_timezone("America/New_York")
        context.pinned_timezone.cache_clear()

    def test_event_confirmation_key_and_inputs_never_mutated(self):
        item = clock_event("2024-01-08T16:00:00Z", "2024-01-08T18:00:00Z")
        epoch = int(datetime(2024, 1, 8, 18, tzinfo=timezone.utc).timestamp())
        events = {epoch: {"BTCUSDT": item}}
        original = deepcopy(events)
        result = context.filter_events(events, "ny_lunch")
        self.assertEqual(events, original)
        self.assertEqual(result[epoch]["BTCUSDT"]["clock_context"], "ny_lunch")
        with self.assertRaisesRegex(ValueError, "keyed"):
            context.filter_events({epoch - 300: events[epoch]}, "ny_lunch")

    def test_all48_nonvacuous_parent_prices_fills_costs_and_causality_parity(self):
        fixtures = {(minutes, name): fixture(minutes, name) for minutes in (15, 60) for name in context.CONTEXTS}
        for variant in context.grid():
            with self.subTest(variant=variant["id"]):
                full = fixtures[(variant["parent_variant"]["minutes"], variant["context"])]
                original = parent.setups(full, variant["parent_variant"])
                events = context.setups(full, variant)
                self.assertTrue(events)
                for epoch, assets in events.items():
                    for symbol, event in assets.items():
                        self.assertTrue(context.accepts_event(event, variant["context"]))
                        for key in ("entry", "stop", "target", "entry_zone", "invalidation", "expires_at", "signal_time", "sweep_time"):
                            self.assertEqual(event[key], original[epoch][symbol][key])
                first = parent.simulate(full, events, "2024-03-06", "2024-03-12", risk_fraction=variant["risk_fraction"])
                self.assertTrue(first["trades"])
                self.assertLess(first["metrics"]["equity_pnl_reconciliation_error"], 1e-7)
                self.assertLessEqual(max(point["reserved_margin"] for point in first["equity_curve"]), 100000)
                changed = fixture(variant["parent_variant"]["minutes"], variant["context"])
                cutoff = max(events) + 300
                for symbol in parent.SYMBOLS:
                    for row, stamp in zip(changed.bars[symbol], changed.stamps):
                        if int(stamp.timestamp()) >= cutoff:
                            row.update(open=10, high=1000, low=1, close=20)
                future = context.setups(changed, variant)
                self.assertEqual({t: rows for t, rows in events.items() if t < cutoff}, {t: rows for t, rows in future.items() if t < cutoff})
                second = parent.simulate(changed, future, "2024-03-06", "2024-03-12", risk_fraction=variant["risk_fraction"])
                before = lambda result: [row for row in result["equity_curve"] if int(datetime.fromisoformat(row["time"].replace("Z", "+00:00")).timestamp()) < cutoff]
                self.assertEqual(before(first), before(second))

    def test_physical_prefix_excludes_future_prices_and_late_funding(self):
        full = fixture()
        prefix = context.PrefixFeatures(full, "2024-03-11")
        self.assertEqual(len(prefix.times), 5 * 288)
        self.assertEqual(prefix.times[-1], "2024-03-10T23:55:00Z")
        self.assertFalse(context.setups(prefix, context.grid()[0]))
        before = deepcopy(prefix.signal_features("BTCUSDT", 15))
        for row in full.bars["BTCUSDT"][5 * 288:]:
            row.update(open=1, high=1000, low=.1, close=10)
        self.assertEqual(before, context.PrefixFeatures(full, "2024-03-11").signal_features("BTCUSDT", 15))
        boundary = datetime(2024, 3, 11, tzinfo=timezone.utc)
        full.funding["BTCUSDT"] = {int(boundary.timestamp()): [{"_stamp": boundary}],
                                   int((boundary + timedelta(seconds=1)).timestamp()): [{"_stamp": boundary + timedelta(seconds=1)}]}
        prefix = context.PrefixFeatures(full, "2024-03-11")
        self.assertEqual(sum(len(rows) for rows in prefix.funding["BTCUSDT"].values()), 1)


class LiquidityContextDriverTests(unittest.TestCase):
    def test_freeze_roundtrip_and_producer_tamper_stop_before_execution(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            (root / "docs").mkdir()
            (root / "engine.py").write_text("frozen")
            (root / "docs/objective.json").write_text("objective")
            (root / "docs/protocol.md").write_text("rules")
            sha = lambda name: hashlib.sha256((root / name).read_bytes()).hexdigest()
            protocol = {"grid": context.grid(), "producers": {"engine.py": sha("engine.py")}, "inputs": {},
                        "common_objective_path": "docs/objective.json", "common_objective_sha256": sha("docs/objective.json"),
                        "human_protocol_path": "docs/protocol.md", "human_protocol_sha256": sha("docs/protocol.md")}
            with patch.object(driver, "ROOT", root), patch.object(driver, "DIRECTORY", root / "locks"), \
                 patch.object(driver, "OUTPUT", root / "docs/report.json"), patch.object(driver, "MARKDOWN", root / "docs/report.md"), \
                 patch.object(driver, "make_protocol", return_value=protocol):
                first = driver.freeze()
                self.assertEqual(driver.freeze(), first)
                self.assertFalse(first["live_orders"])
                self.assertFalse(first["telegram_enabled"])
                (root / "engine.py").write_text("changed")
                with patch.object(driver.parent, "load_inputs", side_effect=AssertionError("Must not load prices")), self.assertRaisesRegex(ValueError, "changed"):
                    driver.run()

    def scenario(self, train_pass, validation_pass=False):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self.scenario_root = root
        (root / "docs").mkdir()
        variants = context.grid()[:2]
        report = {"phase": "frozen_before_outcomes", "protocol": {"grid": variants}, "protocol_sha256": "frozen",
                  "training": [], "live_orders": False, "telegram_enabled": False}
        calls = []
        def evaluate(features, variant, role, cache, **kwargs):
            calls.append((variant["id"], role, kwargs.get("ledgers", False)))
            if role == "final":
                self.assertTrue((root / "locks" / "validation-confirmation.json").is_file())
            passed = train_pass and variant == variants[0] if role == "training" else validation_pass
            return {"id": variant["id"], "variant": variant, "passed": passed, "score": 1 if variant == variants[0] else 100,
                    "metrics": {"return_pct": 1, "trade_count": 35}, "stress_metrics": {"return_pct": .5},
                    "target": {"passed": passed, "base": {"geometric_monthly_return": .08}}}
        with patch.object(driver, "DIRECTORY", root / "locks"), patch.object(driver, "OUTPUT", root / "docs/report.json"), \
             patch.object(driver, "MARKDOWN", root / "docs/report.md"), patch.object(driver, "freeze", return_value=report), \
             patch.object(driver, "verify"), patch.object(driver.parent, "load_inputs", return_value=object()), \
             patch.object(context, "PrefixFeatures", return_value=object()), patch.object(driver, "period", side_effect=evaluate), \
             patch("builtins.print"):
            result = driver.run()
        return result, calls

    def test_no_pass_no_oos_even_with_higher_failed_score(self):
        report, calls = self.scenario(False)
        self.assertTrue(all(role == "training" for _, role, _ in calls))
        self.assertIsNone(report["selected"])
        self.assertEqual(report["phase"], "completed_no_training_candidate")

    def test_validation_failure_no_final_or_other_primary(self):
        report, calls = self.scenario(True, False)
        self.assertEqual(report["selected"], context.grid()[0]["id"])
        self.assertFalse(any(role == "final" for _, role, _ in calls))
        self.assertEqual(report["phase"], "completed_validation_failed")
        self.assertFalse(report["live_orders"])
        self.assertFalse(report["telegram_enabled"])

    def test_confirmation_before_one_final_no_live_promotion(self):
        report, calls = self.scenario(True, True)
        self.assertEqual(sum(role == "final" for _, role, _ in calls), 1)
        self.assertTrue(report["retrospective_target_candidate"])
        self.assertFalse(report["live_orders"])
        self.assertFalse(report["telegram_enabled"])

    def test_final_authorization_rejects_mutable_validation_and_missing_confirmation(self):
        report, _ = self.scenario(True, True)
        with patch.object(driver, "DIRECTORY", self.scenario_root / "locks"), patch.object(driver, "verify"):
            driver.verify_final_authorization(report)
            changed = deepcopy(report)
            changed["validation"]["metrics"]["return_pct"] = 1000
            with self.assertRaisesRegex(ValueError, "authorize FINAL"):
                driver.verify_final_authorization(changed)
            (self.scenario_root / "locks/validation-confirmation.json").unlink()
            with self.assertRaises(OSError):
                driver.verify_final_authorization(report)


if __name__ == "__main__":
    unittest.main()
