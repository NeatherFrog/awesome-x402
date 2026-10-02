"""Causal futures fills, accounting, source sessions and heldout stopping."""
from copy import deepcopy
from collections import Counter
from datetime import datetime, timedelta, timezone
import json
import random
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from propdesk import session_strategies as engine
from propdesk.timezones import timezone_for
from scripts import research_sessions as driver


ORB = "orb_h1_b0_r1.5_t0"


def bar(date, slot, prices=(100, 101, 99, 100), *, volume=100, marker=False):
    local = datetime.fromisoformat(date + "T" + slot).replace(tzinfo=timezone_for("America/New_York"))
    return {"time": local.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            **dict(zip(("open", "high", "low", "close"), prices)), "volume": volume,
            "session_date": date, "slot": slot, "flatten": "15:00", "marker_only": marker}


def fixture():
    rows = []
    for day in range(6, 11):
        date = f"2025-01-{day:02d}"
        for hour in range(10, 16):
            rows.append(bar(date, f"{hour}:00", marker=hour == 15))
    values = [(100, 101, 99, 100), (100, 105, 99.5, 104), (104, 106, 103, 105),
              (105, 107, 104, 106), (106, 107, 104, 105), (105, 106, 104, 105)]
    for item, prices in zip(rows[-6:], values):
        item.update(dict(zip(("open", "high", "low", "close"), prices)))
    return rows


def mirror(rows):
    result = deepcopy(rows)
    for original, item in zip(rows, result):
        item.update(open=200 - original["open"], close=200 - original["close"],
                    high=200 - original["low"], low=200 - original["high"])
    return result


class SessionEngineTests(unittest.TestCase):
    def test_independent_all144_synthetic_prefix_and_accounting_audit(self):
        # Generator independently supplied by the statistical-audit agent;
        # this seed produces real episodes for every risk/rule/market pair.
        rng = random.Random(731402)
        dates, day = [], datetime(2025, 1, 6).date()
        while len(dates) < 50:
            if day.weekday() < 5:
                dates.append(day.isoformat())
            day += timedelta(days=1)
        rows, price = [], 6000.0
        for date in dates:
            for hour in range(10, 16):
                opening, body = price + rng.gauss(0, 1), rng.gauss(0, 2)
                if hour in (11, 12) and rng.random() < .4:
                    body += rng.choice((-1, 1)) * rng.uniform(8, 18)
                closing = opening + body
                high, low = max(opening, closing) + rng.uniform(.2, 4), min(opening, closing) - rng.uniform(.2, 4)
                rows.append(bar(date, f"{hour}:00", (opening, high, low, closing), marker=hour == 15))
                price = closing
        changed = deepcopy(rows)
        for item in changed[180:]:
            for key in ("open", "high", "low", "close"):
                item[key] *= 1.4
            item["volume"] *= 30
        counts = Counter()
        for variant in driver.portfolio_variants():
            for symbol in engine.SPECS:
                with self.subTest(variant=variant["id"], symbol=symbol):
                    cfg = {"risk_pct": variant["aggregate_risk_pct"]}
                    first = engine.simulate(rows, variant["economic_id"], symbol, config=cfg)
                    second = engine.simulate(changed, variant["economic_id"], symbol, config=cfg)
                    self.assertTrue(first["trades"])
                    self.assertEqual(first["curve"][:180], second["curve"][:180])
                    self.assertAlmostEqual(first["curve"][-1]["balance"], 50000 + sum(t["net_pnl"] for t in first["trades"]), places=7)
                    days = Counter()
                    for trade in first["trades"]:
                        self.assertEqual(trade["quantity"], int(trade["quantity"]))
                        self.assertTrue(1 <= trade["quantity"] <= 10)
                        self.assertLessEqual(trade["planned_risk_amount"], trade["risk_budget"] + 1e-7)
                        self.assertGreater(trade["entry_fee"], 0)
                        self.assertGreater(trade["exit_fee"], 0)
                        self.assertLessEqual(trade["signal_time"], trade["entry_time"])
                        days[trade["entry_time"][:10]] += 1
                    self.assertEqual(max(days.values()), 1)
                    counts[variant["family"]] += len(first["trades"])
        self.assertEqual(counts, {"late_opening_range": 2640, "failed_range_reversion": 849, "volatility_release": 2448})

    def test_catalog_and_registered_risk_budget(self):
        self.assertEqual(len(engine.catalog()), 48)
        self.assertEqual(len({row["id"] for row in engine.catalog()}), 48)
        self.assertEqual(len(driver.portfolio_variants()), 144)
        self.assertEqual({row["aggregate_risk_pct"] for row in driver.portfolio_variants()}, {.5, 1, 1.5})
        self.assertEqual(engine.DEFAULT_CONFIG["fee_per_contract_side"], .61)

    def test_no_signal_until_range_and_confirmation_closed(self):
        rows = fixture()
        decisions = engine.entry_decisions(rows, ORB)
        self.assertFalse(any(item["direction"] for item in decisions[:-4]))
        decision = decisions[-4]
        self.assertEqual(decision["direction"], 1)
        self.assertEqual(decision["signal_time"], rows[-4]["time"])
        self.assertAlmostEqual(decision["stop"], 98.8)
        self.assertEqual((decision["range_low"], decision["range_high"]), (99, 101))

    def test_known_fill_ticks_integer_risk_and_complete_cashflow(self):
        result = engine.simulate(fixture(), ORB, "MES=F")
        self.assertEqual(len(result["trades"]), 1)
        trade = result["trades"][0]
        self.assertEqual(trade["quantity"], 7)
        self.assertEqual(trade["entry_price"], 104.5)
        self.assertEqual(trade["stop"], 98.75)
        self.assertEqual(trade["exit_price"], 104.5)
        self.assertEqual(trade["exit_reason"], "session_flatten")
        self.assertAlmostEqual(trade["entry_fee"], 4.27)
        self.assertAlmostEqual(trade["exit_fee"], 4.27)
        self.assertAlmostEqual(trade["planned_risk_amount"], 227.29)
        self.assertLessEqual(trade["planned_risk_amount"], trade["risk_budget"])
        self.assertAlmostEqual(trade["net_pnl"], -8.54)
        self.assertAlmostEqual(result["curve"][-1]["balance"], 50000 + trade["net_pnl"])
        self.assertAlmostEqual(trade["gross_pnl"] - trade["net_pnl"], trade["costs"])
        self.assertEqual(trade["signal_time"], trade["entry_time"])

    def test_friction_changes_actual_profit_and_not_only_display(self):
        rows = fixture()
        free = engine.simulate(rows, ORB, "MES=F", config={"fee_per_contract_side": 0, "spread_ticks": 0, "slippage_ticks": 0})
        self.assertEqual(free["trades"][0]["quantity"], 9)
        self.assertEqual(free["trades"][0]["net_pnl"], 45)
        stressed = engine.simulate(rows, ORB, "MES=F", config={"cost_multiplier": 2})
        self.assertLess(stressed["trades"][0]["net_pnl"], -8.54)

    def test_entry_bar_stop_target_collision_is_stop(self):
        rows = fixture()
        rows[-4].update(high=112, low=98)
        trade = engine.simulate(rows, ORB, "MES=F")["trades"][0]
        self.assertEqual(trade["exit_reason"], "stop_first_collision")
        self.assertAlmostEqual(trade["net_pnl"], -trade["planned_risk_amount"])
        self.assertEqual(trade["entry_time"], trade["exit_bar_time"])

    def test_entry_at_open_allows_later_entry_bar_target(self):
        rows = fixture()
        rows[-4]["high"] = 112
        trade = engine.simulate(rows, ORB, "MES=F")["trades"][0]
        self.assertEqual(trade["exit_reason"], "target")
        self.assertEqual(trade["target"], 111.75)
        self.assertGreater(trade["net_pnl"], 0)

    def test_adverse_gap_can_exceed_planned_stop_risk(self):
        rows = fixture()
        rows[-3].update(open=95, high=96, low=94, close=95)
        trade = engine.simulate(rows, ORB, "MES=F")["trades"][0]
        self.assertEqual(trade["exit_reason"], "gap_stop")
        self.assertEqual(trade["raw_exit"], 95)
        self.assertLess(trade["net_pnl"], -trade["planned_risk_amount"])

    def test_favorable_gap_only_receives_target(self):
        rows = fixture()
        rows[-3].update(open=120, high=125, low=80, close=90)
        result = engine.simulate(rows, ORB, "MES=F")
        trade = result["trades"][0]
        self.assertEqual(trade["exit_reason"], "gap_target")
        self.assertEqual(trade["raw_exit"], trade["target"])
        # The pre-gap ledger still carries the paid entry fee; the later low80
        # cannot affect a position already exited at the favorable opening.
        self.assertAlmostEqual(result["curve"][-3]["worst_equity"], 50000 - trade["entry_fee"])

    def test_long_short_mirror_and_both_multipliers(self):
        for symbol in engine.SPECS:
            long = engine.simulate(fixture(), ORB, symbol)["trades"][0]
            short = engine.simulate(mirror(fixture()), ORB, symbol)["trades"][0]
            self.assertEqual(short["direction"], -1)
            self.assertEqual(long["quantity"], short["quantity"])
            self.assertAlmostEqual(long["net_pnl"], short["net_pnl"])

    def test_all_variants_prefix_and_future_ohlc_invariance(self):
        rows = fixture()
        changed = deepcopy(rows)
        for item in changed[-3:]:
            item.update(open=130, high=160, low=30, close=140, volume=90000)
        for variant in engine.catalog():
            original = engine.entry_decisions(rows, variant["id"])
            prefix = engine.entry_decisions(rows[:-3], variant["id"])
            future = engine.entry_decisions(changed, variant["id"])
            self.assertEqual(original[:-3], prefix, variant["id"])
            self.assertEqual(original[:-3], future[:-3], variant["id"])
        # Actual ORB trade exists; past cashflow comparison is not vacuous.
        first = engine.simulate(rows, ORB, "MES=F")
        second = engine.simulate(changed, ORB, "MES=F")
        self.assertTrue(first["trades"])
        self.assertEqual(first["curve"][:-3], second["curve"][:-3])

    def test_marker_extremes_and_volume_are_never_features_or_late_exit(self):
        rows = fixture()
        rows += [bar("2025-01-13", f"{hour}:00", marker=hour == 15) for hour in range(10, 16)]
        changed = deepcopy(rows)
        for item in changed:
            if item["marker_only"]:
                item.update(high=10000, low=1, close=9999, volume=1e9)
        for variant in engine.catalog():
            self.assertEqual(engine.entry_decisions(rows, variant["id"]), engine.entry_decisions(changed, variant["id"]))
        first = engine.simulate(rows, ORB, "MES=F")
        second = engine.simulate(changed, ORB, "MES=F")
        self.assertEqual(first["trades"], second["trades"])
        self.assertEqual(first["curve"], second["curve"])

    def test_one_entry_even_after_stop_and_no_overnight_fallback(self):
        rows = fixture()
        rows[-4].update(high=112, low=98)
        result = engine.simulate(rows, ORB, "MES=F")
        self.assertEqual(len(result["trades"]), 1)
        with self.assertRaisesRegex(ValueError, "flatten"):
            engine.simulate(fixture()[:-1], ORB, "MES=F")
        missing = fixture()[:-1] + [bar("2025-01-13", "10:00")]
        with self.assertRaisesRegex(ValueError, "flatten"):
            engine.simulate(missing, ORB, "MES=F")

    def test_quantity_zero_preserves_curve_and_gap_invalidates_entry(self):
        rows = fixture()
        zero = engine.simulate(rows, ORB, "MES=F", config={"risk_pct": .001})
        self.assertFalse(zero["trades"])
        self.assertEqual(len(zero["curve"]), len(rows))
        changed = fixture()
        changed[-4].update(open=98, high=99, low=97, close=98)
        changed[-3].update(open=100, high=101, low=99, close=100)
        changed[-2].update(open=100, high=101, low=99, close=100)
        blocked = engine.simulate(changed, ORB, "MES=F")
        self.assertFalse(blocked["trades"])
        self.assertEqual(len(blocked["curve"]), len(rows))

    def test_futures_notional_is_not_a_fabricated_cash_margin_constraint(self):
        rows = fixture()
        for item in rows:
            for key in ("open", "high", "low", "close"):
                item[key] += 6000
        trade = engine.simulate(rows, ORB, "MES=F")["trades"][0]
        self.assertGreater(trade["entry_notional"], 50000)
        self.assertLessEqual(trade["quantity"], 10)
        self.assertLessEqual(trade["planned_risk_amount"], trade["risk_budget"])

    def test_configuration_rejects_unsupported_and_nonfinite_values(self):
        for cfg in (False, {"risk_pct": 0}, {"risk_pct": 6}, {"max_contracts": 1.5}, {"account_size": float("nan")}, {"leverage": 500}):
            with self.subTest(cfg=cfg), self.assertRaises(ValueError):
                engine.simulate(fixture(), ORB, "MES=F", config=cfg)

    def test_distinct_reversion_and_release_families_generate_actual_trades(self):
        rows = fixture()
        rows[-6].update(open=100, high=105, low=95, close=100)
        rows[-5].update(open=103, high=109, low=100, close=103)
        rows[-4].update(open=104, high=105, low=102, close=103)
        reversion = engine.simulate(rows, "failure_h1_e0_midpoint_t0", "MES=F")
        self.assertEqual(reversion["trades"][0]["direction"], -1)
        self.assertEqual(reversion["trades"][0]["target"], 100)
        release = engine.simulate(fixture(), "release_c4_e0.75_r1.5_t0", "MES=F")
        self.assertTrue(release["trades"])
        self.assertEqual(release["trades"][0]["direction"], 1)

    def test_reversion_both_side_sweep_and_zero_volume_proxy_are_unknown(self):
        rows = fixture()
        rows[-5].update(open=100, high=106, low=94, close=100.5)
        both = engine.entry_decisions(rows, "failure_h1_e0_midpoint_t0")
        self.assertEqual(both[-4]["direction"], 0)
        rows[-5].update(open=100, high=106, low=99.5, close=100.5)
        for item in rows:
            item["volume"] = 0
        decision = engine.entry_decisions(rows, "failure_h1_e0_vwap_proxy_t0")[-4]
        self.assertEqual(decision["direction"], -1)
        self.assertIsNone(decision["target"])
        self.assertIsNone(decision["vwap_proxy"])
        self.assertFalse(engine.simulate(rows, "failure_h1_e0_vwap_proxy_t0", "MES=F")["trades"])

    def test_calendar_anchors_halfday_and_holiday_are_not_inferred_from_prices(self):
        calendar = {"holidays": ["2025-01-09"], "early_close_dates": ["2025-01-10"]}
        raw = [bar("2025-01-09", f"{hour:02d}:00") for hour in range(9, 17)]
        raw += [bar("2025-01-10", slot) for slot in ("09:30", "10:30", "11:30", "12:30", "13:00")]
        selected, audit = engine.prepare_bars(raw, calendar, "2025-01-09", "2025-01-11")
        self.assertEqual([item["slot"] for item in selected], ["09:30", "10:30", "11:30", "12:30"])
        self.assertTrue(selected[-1]["marker_only"])
        self.assertEqual(audit["complete_sessions"], 1)
        with self.assertRaisesRegex(ValueError, "coverage incomplete"):
            engine.prepare_bars(raw[:-2] + raw[-1:], calendar, "2025-01-09", "2025-01-11")

    def test_normal_0900_straddle_excluded_and_ny_dst_preserved(self):
        calendar = {"holidays": [], "early_close_dates": []}
        winter = [bar("2025-01-06", f"{hour:02d}:00") for hour in range(9, 17)]
        summer = [bar("2025-07-07", f"{hour:02d}:00") for hour in range(9, 17)]
        w, _ = engine.prepare_bars(winter, calendar, "2025-01-06", "2025-01-07")
        s, _ = engine.prepare_bars(summer, calendar, "2025-07-07", "2025-07-08")
        self.assertEqual([item["slot"] for item in w], [f"{h}:00" for h in range(10, 16)])
        self.assertIn("T15:00:00Z", w[0]["time"])
        self.assertIn("T14:00:00Z", s[0]["time"])


class SessionDriverTests(unittest.TestCase):
    def test_protocol_freeze_json_roundtrip_and_tamper_detection(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            (root / "docs").mkdir()
            (root / "docs" / "EIGHT_PERCENT_PROTOCOL.json").write_bytes((driver.ROOT / "docs" / "EIGHT_PERCENT_PROTOCOL.json").read_bytes())
            receipts = [{"id": item["id"], "sha256": item["retrieved_sha256"], "body_verified": True}
                        for item in driver.VERIFIED_TOPSTEP_RECEIPTS]
            review = root / "docs" / "high-return-source-review.json"
            review.write_text(json.dumps({"retrievals": receipts}))
            with patch.object(driver, "ROOT", root), patch.object(driver, "OUTPUT", root / "docs" / "report.json"), \
                 patch.object(driver, "LOCKS", root / "locks"), patch.object(driver, "calendar", return_value={"holidays": [], "early_close_dates": []}):
                first = driver.freeze()
                second = driver.freeze()
                self.assertEqual(first, second)
                self.assertEqual(first["protocol"]["portfolio_variants"], 144)
                receipts[0]["sha256"] = "changed"
                review.write_text(json.dumps({"retrievals": receipts}))
                with self.assertRaisesRegex(ValueError, "receipt mismatch"):
                    driver.freeze()

    def test_total_account_sum_and_flat_calendar_days(self):
        def run(symbol, balance, worst, best):
            return {"symbol": symbol, "metrics": {}, "trades": [], "curve": [
                {"time": "2025-01-10T20:00:00Z", "session_date": "2025-01-10", "equity": balance,
                 "balance": balance, "worst_equity": worst, "best_equity": best}]}
        combined = driver.combine([run("MES=F", 51000, 49500, 51500), run("MNQ=F", 49500, 49000, 50500)],
                                  "2025-01-10", "2025-01-13")
        self.assertEqual(combined["dates"], ["2025-01-10", "2025-01-11", "2025-01-12"])
        self.assertAlmostEqual(combined["daily_returns"][0], .005)
        self.assertEqual(combined["daily_returns"][1:], [0, 0])
        self.assertEqual(combined["daily_worst_equity"], [98500, 100500, 100500])
        self.assertEqual(combined["daily_peak_equity"], [102000, 100500, 100500])

    def test_mismatched_market_hour_never_silently_fills_flat(self):
        with self.assertRaisesRegex(ValueError, "identical"):
            driver.combine([{"curve": []}, {"curve": [{"time": "x"}]}], "2025-01-01", "2025-01-02")

    def test_physical_period_truncation_and_registered_bucket_risk(self):
        variants = driver.portfolio_variants()
        chosen = next(item for item in variants if item["aggregate_risk_pct"] == 1.5)
        visible = {symbol: [{"session_date": "2024-12-31"}, {"session_date": "2025-01-01"}] for symbol in driver.SYMBOLS}
        seen = []
        def simulation(rows, variant, symbol, **kwargs):
            seen.append((rows, variant, kwargs["config"]))
            return {"curve": [], "symbol": symbol, "metrics": {}, "trades": []}
        with patch.object(engine, "simulate", side_effect=simulation), patch.object(driver, "evaluate_period", return_value={}):
            driver.run_period(visible, chosen["id"], "training")
        self.assertEqual(len(seen), 4)
        self.assertTrue(all(rows == [{"session_date": "2024-12-31"}] for rows, _, _ in seen))
        self.assertTrue(all(config["risk_pct"] == 1.5 for _, _, config in seen))
        self.assertEqual([config["cost_multiplier"] for _, _, config in seen], [1, 1, 2, 2])

    def scenario(self, train_pass, validation_pass=False):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        directory = Path(temporary.name)
        variants = [{"id": "eligible", "family": "test"}, {"id": "tempting", "family": "test"}]
        protocol = {"variants": variants, "selection": "train only"}
        report = {"phase": "predeclared", "protocol": protocol, "protocol_sha256": driver.digest(protocol)}
        calls = []
        def period(prepared, variant, role):
            calls.append((variant, role))
            if role == "final":
                self.assertTrue((directory / "locks" / "validation-confirmation.json").exists())
            passed = train_pass and variant == "eligible" if role == "training" else validation_pass
            return {"evaluation": {"passed": passed, "selection_score_net_return_over_drawdown": 100 if variant == "tempting" else 1},
                    "base": {}, "double_cost": {}}
        with patch.object(driver, "OUTPUT", directory / "report.json"), patch.object(driver, "LOCKS", directory / "locks"), \
             patch.object(driver, "freeze", return_value=report), patch.object(driver, "load_sources", return_value=({}, {"source": "fixed"})), \
             patch.object(driver, "producer_hashes", return_value={"engine": "fixed"}), patch.object(driver, "run_period", side_effect=period), \
             patch.object(driver, "write_markdown"):
            result = driver.run()
            result_lock = json.loads((directory / "locks" / "result-lock.json").read_text())
            self.assertEqual(result_lock["report_sha256"], driver.file_digest(directory / "report.json"))
        return result, calls

    def test_no_training_pass_no_oos_even_high_diagnostic_score(self):
        result, calls = self.scenario(False)
        self.assertEqual(calls, [("eligible", "training"), ("tempting", "training")])
        self.assertIsNone(result["selected_variant"])
        self.assertEqual(result["training_candidate"], "tempting")
        self.assertFalse(result["historical_reference_passed"])

    def test_failed_validation_stops_final_and_never_substitutes_other_variant(self):
        result, calls = self.scenario(True, False)
        self.assertEqual(calls[-1], ("eligible", "validation"))
        self.assertFalse(any(role == "final" for _, role in calls))
        self.assertEqual(result["selected_variant"], "eligible")
        self.assertEqual(result["primary"]["final"]["status"], "not_evaluated")

    def test_validation_confirmed_before_single_locked_final(self):
        result, calls = self.scenario(True, True)
        self.assertEqual(calls, [("eligible", "training"), ("tempting", "training"), ("eligible", "validation"), ("eligible", "final")])
        self.assertTrue(result["historical_reference_passed"])
        self.assertFalse(result["real_prop_qualified"])
        self.assertFalse(result["telegram_enabled"])
        self.assertFalse(result["live_orders"])


if __name__ == "__main__":
    unittest.main()
