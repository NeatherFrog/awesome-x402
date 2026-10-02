from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from propdesk import metal_sessions as metal
from scripts import research_metal_sessions as driver


def variant(session="london", family="breakout", context="none", risk=.005):
    return next(value for value in metal.variants() if value["session"] == session
                and value["family"] == family and value["context"] == context
                and value["risk"] == risk and value["reward_risk"] == 1 and value["hold_hours"] == 3)


def fixture(session="london", family="breakout"):
    begin = datetime(2024, 1, 1, tzinfo=timezone.utc)
    rows = [{"time": (begin + timedelta(hours=index)).isoformat(),
             "open": 2000.0, "high": 2001.0, "low": 1999.0, "close": 2000.0}
            for index in range(72)]
    zone = metal.LONDON if session == "london" else metal.NEW_YORK
    range_hours = list(range(6)) if session == "london" else [8, 9, 10]
    signal_hour = 7 if session == "london" else 11

    def index(hour):
        time = datetime(2024, 1, 2, hour, tzinfo=zone).astimezone(timezone.utc)
        return int((time - begin).total_seconds() / 3600)

    if family == "drift":
        for number, hour in enumerate(range_hours):
            closing = 2000 + 1.5 * number / (len(range_hours) - 1)
            rows[index(hour)].update(close=closing, high=max(2001, closing + .2))
    before = index(signal_hour - 1)
    if not (family == "drift" and signal_hour - 1 in range_hours):
        rows[before]["close"] = 2000.3
    signal = index(signal_hour)
    if family == "breakout":
        rows[signal].update(open=2000.0, high=2004.0, low=1999.0, close=2003.0)
    elif family == "rejection":
        rows[signal].update(open=2000.0, high=2001.0, low=1998.7, close=2000.0)
    else:
        rows[signal]["close"] = 2000.3
    return rows, signal + 1


class MetalSessionTests(unittest.TestCase):
    def simulate(self, rows, value=None, cost=1, capital=100000):
        return metal.simulate(rows, value or variant(), "2024-01-01T00:00:00Z",
                              "2024-01-04T00:00:00Z", capital=capital, cost_multiplier=cost)

    def test_catalog_units_percent_conversion_and_physical_pnl(self):
        self.assertEqual(len(metal.variants()), 96)
        self.assertEqual(len({value["id"] for value in metal.variants()}), 96)
        self.assertEqual(metal.CONTRACT_OUNCES * metal.LOT_STEP, 1)
        self.assertAlmostEqual(metal.commission(100, 2000), 2.8)
        self.assertAlmostEqual(metal.commission(100, 2000, 2), 5.6)
        self.assertEqual(metal.pnl(100, 1, 2000, 2010), 1000)
        self.assertEqual(metal.pnl(100, -1, 2000, 2010), -1000)

    def test_all_six_families_and_both_contexts_have_nonvacuous_trades(self):
        for session in ("london", "us"):
            for family in ("breakout", "rejection", "drift"):
                for context in ("none", "prior_trend"):
                    with self.subTest(session=session, family=family, context=context):
                        rows, entry_index = fixture(session, family)
                        result = self.simulate(rows, variant(session, family, context))
                        self.assertTrue(result["trades"])
                        self.assertEqual(result["trades"][0]["entry_time"], rows[entry_index]["time"])
                        self.assertEqual(result["trades"][0]["known_at"], rows[entry_index]["time"])
                        self.assertAlmostEqual(result["reconciliation_error"], 0, places=7)

    def test_later_prices_cannot_change_an_earlier_decision(self):
        rows, entry_index = fixture()
        baseline = metal.decisions(rows, variant())
        changed = deepcopy(rows)
        for row in changed[entry_index:]:
            row.update(open=5000, high=6000, low=4000, close=5500)
        later = metal.decisions(changed, variant())
        boundary = metal.stamp(rows[entry_index]["time"])
        self.assertEqual({key: value for key, value in baseline.items() if metal.stamp(key) <= boundary},
                         {key: value for key, value in later.items() if metal.stamp(key) <= boundary})
        # A decision exists independently of whether its future execution quote
        # has arrived, rather than peeking at the next row's timestamp or price.
        prefix = metal.decisions(rows[:entry_index], variant())
        self.assertEqual(prefix[boundary.isoformat()], baseline[boundary.isoformat()])

    def test_cash_both_fill_commissions_margin_and_integer_ounces(self):
        rows, _ = fixture()
        result = self.simulate(rows)
        trade = result["trades"][0]
        self.assertEqual(trade["ounces"], int(trade["ounces"]))
        self.assertAlmostEqual(trade["lots"] * 100, trade["ounces"])
        self.assertAlmostEqual(trade["entry_fee"], metal.commission(trade["ounces"], trade["entry"]))
        self.assertAlmostEqual(trade["exit_fee"], metal.commission(trade["ounces"], trade["exit"]))
        self.assertLessEqual(trade["initial_margin"] + trade["entry_fee"], 100000)
        self.assertLessEqual(trade["modeled_stop_loss"], trade["risk_budget"])
        self.assertAlmostEqual(result["final_equity"], 100000 + sum(t["net_pnl"] for t in result["trades"]))
        self.assertEqual(len(result["dates"]), 3)

    def test_margin_limits_tight_stop_sizing_without_creating_capital(self):
        rows, entry_index = fixture()
        for row in rows:
            row.update(open=2000.0, high=2000.1, low=1999.9, close=2000.0)
        rows[entry_index - 1].update(high=2000.3, close=2000.2)
        result = self.simulate(rows, variant(risk=.01))
        trade = result["trades"][0]
        self.assertLessEqual(trade["initial_margin"] + trade["entry_fee"], 100000)
        self.assertGreater(trade["initial_margin"], 99000)
        self.assertLessEqual(trade["modeled_stop_loss"], 1000)

    def test_stop_first_when_bar_has_unknown_stop_and_target_order(self):
        rows, entry_index = fixture()
        rows[entry_index].update(high=2020, low=1990)
        result = self.simulate(rows)
        self.assertEqual(result["trades"][0]["exit_reason"], "stop_first")
        self.assertEqual(result["trades"][0]["exit_time_precision"], "intrabar_unknown")
        self.assertLess(result["trades"][0]["net_pnl"], 0)

    def test_known_opening_target_precedes_later_unknown_adverse_extreme(self):
        rows, entry_index = fixture()
        rows[entry_index + 1].update(open=2010, high=2020, low=1990, close=2000)
        trade = self.simulate(rows)["trades"][0]
        self.assertEqual(trade["exit_reason"], "target_at_open")
        self.assertEqual(trade["exit_time_precision"], "known_open")
        self.assertLess(trade["exit"], 2010)  # No favorable gap-fill improvement.
        self.assertGreater(trade["net_pnl"], 0)

    def test_known_gap_stop_fills_actual_adverse_open_and_can_exceed_budget(self):
        rows, entry_index = fixture()
        rows[entry_index + 1].update(open=1900, high=1901, low=1899, close=1900)
        trade = self.simulate(rows)["trades"][0]
        self.assertEqual(trade["exit_reason"], "gap_stop")
        self.assertLess(trade["exit"], 1900)
        self.assertGreater(-trade["net_pnl"], trade["risk_budget"])

    def test_nonconsecutive_active_interval_exits_and_blocks_eligibility(self):
        rows, entry_index = fixture()
        del rows[entry_index + 1]
        rows[entry_index + 1].update(open=1900, high=1901, low=1899, close=1900)
        result = self.simulate(rows)
        self.assertTrue(result["missing_exposure_exits"])
        self.assertEqual(result["trades"][0]["exit_reason"], "unobserved_interval_exit")

    def test_later_partial_marker_does_not_suppress_prior_entry(self):
        rows, entry_index = fixture()
        marker_time = metal.stamp(rows[entry_index]["time"]) + timedelta(minutes=30)
        rows.insert(entry_index + 1, {"time": marker_time.isoformat(), "open": 1900,
                                    "high": 1901, "low": 1899, "close": 1900})
        result = self.simulate(rows)
        self.assertTrue(result["trades"])
        self.assertEqual(result["trades"][0]["entry_time"], rows[entry_index]["time"])
        self.assertEqual(result["trades"][0]["exit_reason"], "unobserved_interval_exit")
        self.assertTrue(result["missing_exposure_exits"])
        self.assertIn(marker_time.isoformat(), result["source_coverage"]["nonaligned_quote_times"])

    def test_overlap_is_flagged_even_when_previous_intrabar_trade_already_closed(self):
        rows, entry_index = fixture()
        rows[entry_index].update(high=2020, low=1990)
        marker_time = metal.stamp(rows[entry_index]["time"]) + timedelta(minutes=30)
        rows.insert(entry_index + 1, {"time": marker_time.isoformat(), "open": 2000,
                                    "high": 2001, "low": 1999, "close": 2000})
        result = self.simulate(rows)
        self.assertEqual(result["trades"][0]["exit_reason"], "stop_first")
        self.assertTrue(any(row["reason"] == "overlapping_exposure_interval"
                            for row in result["missing_exposure_exits"]))

    def test_missing_required_range_quote_prevents_that_decision(self):
        for session in ("london", "us"):
            rows, entry_index = fixture(session)
            zone = metal.LONDON if session == "london" else metal.NEW_YORK
            hour = 0 if session == "london" else 8
            missing = datetime(2024, 1, 2, hour, tzinfo=zone).astimezone(timezone.utc)
            rows = [row for row in rows if metal.stamp(row["time"]) != missing]
            entry = datetime(2024, 1, 2, 8 if session == "london" else 12,
                             tzinfo=zone).astimezone(timezone.utc)
            self.assertNotIn(entry.isoformat(), metal.decisions(rows, variant(session)))

    def test_doubled_costs_worsen_same_flat_exit_setup(self):
        rows, _ = fixture(family="drift")
        value = variant(family="drift")
        self.assertLess(self.simulate(rows, value, cost=2)["final_equity"],
                        self.simulate(rows, value)["final_equity"])

    def test_pinned_clocks_and_prescheduled_flat_deadlines(self):
        self.assertEqual(datetime(2026, 1, 15, tzinfo=metal.LONDON).utcoffset(), timedelta(0))
        self.assertEqual(datetime(2026, 7, 15, tzinfo=metal.LONDON).utcoffset(), timedelta(hours=1))
        self.assertEqual(datetime(2026, 1, 15, tzinfo=metal.NEW_YORK).utcoffset(), timedelta(hours=-5))
        self.assertEqual(datetime(2026, 7, 15, tzinfo=metal.NEW_YORK).utcoffset(), timedelta(hours=-4))
        for session in ("london", "us"):
            rows, _ = fixture(session, "drift")
            value = next(v for v in metal.variants() if v["session"] == session
                         and v["family"] == "drift" and v["context"] == "none" and v["hold_hours"] == 6)
            trade = self.simulate(rows, value)["trades"][0]
            zone = metal.LONDON if session == "london" else metal.NEW_YORK
            flat = 15 if session == "london" else 16
            self.assertLessEqual(metal.stamp(trade["exit_time"]).astimezone(zone).hour, flat)

    def test_truncated_source_and_bad_parameters_cannot_silently_qualify(self):
        rows, entry_index = fixture()
        result = self.simulate(rows[:entry_index + 1])
        self.assertFalse(result["source_coverage"]["source_spans_declared_window"])
        self.assertEqual(result["trades"][0]["exit_reason"], "boundary_close")
        with self.assertRaises(ValueError):
            metal.simulate(rows, {**variant(), "risk": .2}, "2024-01-01T00:00:00Z", "2024-01-04T00:00:00Z")
        with self.assertRaises(ValueError):
            metal.simulate(rows, variant(), "2024-01-01T00:01:00Z", "2024-01-04T00:00:00Z")

    def test_validation_failure_never_opens_final_or_replaces_primary(self):
        catalog = metal.variants()[:2]
        calls = []

        def fake_period(rows, value, role):
            calls.append((value["id"], role))
            if role == "final":
                self.fail("Failed validation must leave final unopened")
            return {"variant": value, "passed": role == "training",
                    "selection_score_net_return_over_drawdown": 1.0}

        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch.object(driver, "ROOT", root), patch.object(driver, "OUTPUT", root / "report.json"), \
                    patch.object(driver, "LOCKS", root / "locks"), patch.object(driver, "verify"), \
                    patch.object(driver, "load", return_value=[]), patch.object(driver, "period", side_effect=fake_period), \
                    patch.object(metal, "variants", return_value=catalog):
                report = driver.run({"protocol": {}, "protocol_sha256": "synthetic"})
            expected = sorted(catalog, key=lambda value: value["id"])[0]
            self.assertEqual(report["selected"], expected)
            self.assertEqual(report["phase"], "completed_validation_failed_final_unopened")
            self.assertEqual(calls[-1], (expected["id"], "validation"))
            self.assertEqual(len(calls), 3)
            self.assertNotIn("final", report)
            self.assertTrue((root / "locks/selection.json").exists())
            self.assertEqual(len(report["selection"]["training_identities"]), 2)
            self.assertEqual(report["selection"]["protocol_sha256"], "synthetic")

    def reference_report(self, root):
        """Synthetic administrative fixture; no native market return is opened."""
        original = driver.ROOT
        for path in driver.PRODUCERS:
            target = root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((original / path).read_bytes())
        (root / "source.json").write_text('{"synthetic":true}\n')
        inputs = {"prices": {"file": "source.json", "sha256": driver.sha(root / "source.json")}}
        protocol = {"variants": metal.variants(),
                    "windows": {key: list(value) for key, value in driver.WINDOWS.items()},
                    "producers": {path: driver.sha(root / path) for path in driver.PRODUCERS},
                    "inputs": inputs}
        report = {"protocol": protocol, "protocol_sha256": driver.digest(protocol), "variant_count": 96}
        locks = root / "locks"
        locks.mkdir()
        (locks / "protocol.json").write_text(driver.canonical(protocol) + "\n")
        (locks / "input-lock.json").write_text(driver.canonical(inputs) + "\n")
        return report

    def add_authorized_final(self, root, report):
        ledger = root / "ledger.gz"
        value = {"synthetic": True}
        driver.write_ledger(ledger, value)
        receipt = {"path": "ledger.gz", "raw_sha256": hashlib.sha256(driver.canonical(value).encode()).hexdigest(),
                   "compressed_sha256": driver.sha(ledger)}
        report["training"] = [{"variant": value, "passed": True,
                               "selection_score_net_return_over_drawdown": 1.,
                               "base_ledger": receipt, "stress_ledger": receipt} for value in metal.variants()]
        chosen = sorted(metal.variants(), key=lambda value: value["id"])[0]
        selection = {"variant": chosen, "protocol_sha256": report["protocol_sha256"],
                     "training_sha256": driver.digest(report["training"]),
                     "training_identities": driver.training_identity(report["training"]), "locked_at": "synthetic"}
        report["selected"], report["selection"] = chosen, selection
        report["validation"] = {"variant": chosen, "passed": True,
                                "base_ledger": receipt, "stress_ledger": receipt}
        report["confirmation"] = {"protocol_sha256": report["protocol_sha256"],
                                  "selection_sha256": driver.digest(selection),
                                  "validation_sha256": driver.digest(report["validation"]), "locked_at": "synthetic"}
        for name in ("selection", "confirmation"):
            (root / "locks" / (name + ".json")).write_text(driver.canonical(report[name]) + "\n")

    def test_protocol_grid_common_clock_and_test_producer_bindings_are_enforced(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            report = self.reference_report(root)
            with patch.object(driver, "ROOT", root), patch.object(driver, "LOCKS", root / "locks"):
                driver.verify(report)
                changed = deepcopy(report)
                changed["protocol"]["variants"][0]["risk"] = .9
                changed["protocol_sha256"] = driver.digest(changed["protocol"])
                (root / "locks/protocol.json").write_text(driver.canonical(changed["protocol"]))
                with self.assertRaisesRegex(ValueError, "grid"):
                    driver.verify(changed)
                (root / "locks/protocol.json").write_text(driver.canonical(report["protocol"]))
                (root / "tests/test_metal_sessions.py").write_text("tampered test producer")
                with self.assertRaisesRegex(ValueError, "producer"):
                    driver.verify(report)

    def test_missing_claimed_confirmation_blocks_resume_before_final_execution(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            report = self.reference_report(root)
            self.add_authorized_final(root, report)
            with patch.object(driver, "ROOT", root), patch.object(driver, "LOCKS", root / "locks"), \
                    patch.object(driver, "period") as run_period:
                driver.verify_final_authority(report)
                (root / "locks/confirmation.json").unlink()
                with self.assertRaisesRegex(ValueError, "Missing claimed"):
                    driver.run(report)
                run_period.assert_not_called()

    def test_final_requires_same_sole_primary_and_passing_validation(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            report = self.reference_report(root)
            self.add_authorized_final(root, report)
            with patch.object(driver, "ROOT", root), patch.object(driver, "LOCKS", root / "locks"):
                driver.verify_final_authority(report)
                report["selected"] = metal.variants()[-1]
                with self.assertRaisesRegex(ValueError, "FINAL authorization"):
                    driver.verify_final_authority(report)
                report["selected"] = report["selection"]["variant"]
                report["validation"]["passed"] = False
                report["confirmation"]["validation_sha256"] = driver.digest(report["validation"])
                (root / "locks/confirmation.json").write_text(driver.canonical(report["confirmation"]))
                with self.assertRaisesRegex(ValueError, "FINAL authorization"):
                    driver.verify_final_authority(report)

    def test_compressed_ledger_refuses_changed_bytes_or_changed_results(self):
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "ledger.gz"
            driver.write_ledger(path, {"pnl": 0})
            before = path.read_bytes()
            driver.write_ledger(path, {"pnl": 0})
            self.assertEqual(path.read_bytes(), before)
            with self.assertRaisesRegex(ValueError, "ledger mismatch"):
                driver.write_ledger(path, {"pnl": 1})
            path.write_bytes(before + b"tampered")
            with self.assertRaisesRegex(ValueError, "ledger mismatch"):
                driver.write_ledger(path, {"pnl": 0})


if __name__ == "__main__":
    unittest.main()
