"""Synthetic execution/chronology regressions; never evidence of trading alpha."""

import copy
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from propdesk.backtest import normalize_config
from propdesk.timezones import timezone_for
from scripts import research_intraday as study


ROOT = Path(__file__).resolve().parents[1]
FROZEN = json.loads((ROOT / "docs" / "intraday-source-failure.json").read_text())
CALENDAR = FROZEN["protocol"]["calendar"]
NY = timezone_for("America/New_York")


def session_bars(day, prices=None, *, calendar=CALENDAR):
    """Complete actual-clock NY session, including the last half-hour candle."""
    flatten = calendar["early_flatten"] if day in calendar["early_close_dates"] else calendar["flatten"]
    count = int(flatten[:2]) - 9 + 1
    prices = prices or [(100, 101, 99, 100)] * count
    assert len(prices) == count
    opening = datetime.fromisoformat(day + "T09:30:00").replace(tzinfo=NY)
    return [
        {"time": (opening + timedelta(hours=index)).astimezone(timezone.utc)
         .isoformat().replace("+00:00", "Z"), "open": float(values[0]),
         "high": float(values[1]), "low": float(values[2]),
         "close": float(values[3]), "volume": 1000.0}
        for index, values in enumerate(prices)
    ]


def config(**values):
    return normalize_config({"symbol": "SPY", "source": "csv",
                             "account_size": 10000, "risk_pct": 1,
                             "max_leverage": 1, "quantity_step": 1,
                             "contract_multiplier": 1, "fee_bps": 0,
                             "slippage_bps": 0, "spread_bps": 0, **values})


def manual_decisions(bars, *, entries=None, atr=2, family="hourly_donchian_20", calendar=CALENDAR):
    entries = entries or {}
    result = []
    for index, bar in enumerate(bars):
        stamp = study.market.utc_datetime(bar["time"]).astimezone(NY)
        date, slot = stamp.date().isoformat(), stamp.strftime("%H:%M")
        flatten = calendar["early_flatten"] if date in calendar["early_close_dates"] else calendar["flatten"]
        result.append({"direction": entries.get(index, 0), "exit_long": False,
                       "exit_short": False, "atr": atr, "strategy_id": family,
                       "range_high": 101, "range_low": 99,
                       "session_date": date, "slot": slot,
                       "flatten": slot >= flatten,
                       "signal_time": bars[index - 1]["time"] if index else None})
    return result


def business_dates(start, count):
    result, date = [], datetime.fromisoformat(start).date()
    while len(result) < count:
        text = date.isoformat()
        if date.weekday() < 5 and text not in CALENDAR["holidays"]:
            result.append(text)
        date += timedelta(days=1)
    return result


class IntradayProtocolTests(unittest.TestCase):
    def test_preprice_protocol_fingerprint_is_preserved(self):
        # Exact committed record cannot be silently retuned after quotes/results.
        expected = "a5d58b2801a9fb55743ba28e726473f4b707da49a6d0f603b1ed0d6140b504c8"
        self.assertEqual(FROZEN["protocol_sha256"], expected)
        self.assertEqual(study.digest(FROZEN["protocol"]), expected)
        self.assertEqual(FROZEN["protocol"]["frozen_at"], "2026-10-01T10:55:50.209990Z")


class IntradayCalendarTests(unittest.TestCase):
    def test_session_clock_keeps_ny_slots_across_dst_and_halfday_close(self):
        bars = session_bars("2025-03-07") + session_bars("2025-03-10") + session_bars("2025-07-03")
        self.assertEqual(bars[0]["time"], "2025-03-07T14:30:00Z")
        self.assertEqual(bars[7]["time"], "2025-03-10T13:30:00Z")
        groups = study.session_groups(bars, CALENDAR)
        for day in ("2025-03-07", "2025-03-10"):
            self.assertEqual(groups[day]["slots"][0], "09:30")
            self.assertEqual(groups[day]["flatten"], "15:30")
            self.assertEqual(groups[day]["close"], "16:00")
        self.assertEqual(groups["2025-07-03"]["slots"], ["09:30", "10:30", "11:30", "12:30"])
        self.assertEqual(groups["2025-07-03"]["flatten"], "12:30")
        self.assertEqual(groups["2025-07-03"]["close"], "13:00")

    def test_expected_holiday_is_absent_without_removing_trade_sessions(self):
        bars = session_bars("2025-07-02") + session_bars("2025-07-03")
        coverage = study.validate_sessions(bars, CALENDAR, "2025-07-02", "2025-07-05")
        self.assertEqual(coverage["sessions"], 2)
        self.assertEqual(coverage["bars"], 11)
        with self.assertRaisesRegex(ValueError, "outside declared session"):
            study.session_groups(session_bars("2025-01-09"), CALENDAR)

    def test_missing_day_or_flatten_slot_rejects_instead_of_dropping_it(self):
        with self.assertRaisesRegex(ValueError, "missing session 2025-03-04"):
            study.validate_sessions(session_bars("2025-03-03") + session_bars("2025-03-05"),
                                    CALENDAR, "2025-03-03", "2025-03-06")
        missing = session_bars("2025-03-03")[:-1]
        with self.assertRaisesRegex(ValueError, "expected.*15:30"):
            study.validate_sessions(missing, CALENDAR, "2025-03-03", "2025-03-04")

    def test_provider_close_marker_and_unlisted_shortened_day_cannot_be_fills(self):
        close_marker = session_bars("2025-03-03")[-1].copy()
        close_marker["time"] = "2025-03-03T21:00:00Z"
        close_marker["volume"] = 0
        with self.assertRaisesRegex(ValueError, "Unexpected NY opening slot"):
            study.session_groups(session_bars("2025-03-03") + [close_marker], CALENDAR)
        # This frozen vendor calendar does not list July2 as an earlyclose.
        # Observed short coverage must not be silently used to redefine it.
        self.assertNotIn("2026-07-02", CALENDAR["early_close_dates"])
        with self.assertRaisesRegex(ValueError, "Frozen calendar coverage failed"):
            study.validate_sessions(session_bars("2026-07-02")[:4], CALENDAR,
                                    "2026-07-02", "2026-07-03")


class IntradayDecisionTests(unittest.TestCase):
    def test_orb_never_uses_unclosed_opening_hour_and_fills_later_open(self):
        bars = session_bars("2025-03-03", [(100, 101, 99, 100), (100, 103, 100, 102),
                                         (103, 104, 102, 103)] + [(103, 104, 102, 103)] * 4)
        signals = study.entry_decisions(bars, "hourly_orb_60", CALENDAR)
        self.assertEqual(signals[0]["direction"], 0)
        self.assertEqual(signals[1]["direction"], 0)
        self.assertEqual(signals[2]["direction"], 1)
        self.assertEqual(signals[2]["signal_time"], bars[1]["time"])
        result = study.simulate_asset(bars, signals, config(), calendar=CALENDAR)
        self.assertEqual(result["trades"][0]["entry_time"], bars[2]["time"])
        self.assertEqual(result["trades"][0]["entry_price"], 103)
        self.assertEqual(result["trades"][0]["stop"], 99)

    def test_orb_retraced_next_open_does_not_manufacture_entry(self):
        bars = session_bars("2025-03-03", [(100, 101, 99, 100), (100, 103, 100, 102)]
                            + [(100, 100.5, 99.5, 100)] * 5)
        signals = study.entry_decisions(bars, "hourly_orb_60", CALENDAR)
        self.assertEqual(signals[2]["direction"], 1)
        result = study.simulate_asset(bars, signals, config(), calendar=CALENDAR)
        self.assertEqual(result["trades"], [])

    def test_every_family_is_invariant_to_future_prices_and_partial_prefix(self):
        bars = []
        for day_index, day in enumerate(business_dates("2025-03-03", 22)):
            base = 100 + day_index * 1.5
            slope = 1 if day_index == 16 else .3
            prices = [(base + slot * slope, base + slot * slope + .25,
                       base + slot * slope - .05, base + slot * slope + .2) for slot in range(7)]
            bars.extend(session_bars(day, prices))
        cutoff = 18 * 7 + 3
        changed = copy.deepcopy(bars)
        for bar in changed[cutoff:]:
            for key in ("open", "high", "low", "close"):
                bar[key] *= 4
        for family in study.STRATEGY_IDS:
            with self.subTest(family=family):
                original = study.entry_decisions(bars, family, CALENDAR)
                self.assertTrue(any(item["direction"] for item in original[:cutoff]))
                self.assertEqual(original[:cutoff], study.entry_decisions(changed, family, CALENDAR)[:cutoff])
                self.assertEqual(original[:cutoff], study.entry_decisions(bars[:cutoff], family, CALENDAR))

    def test_noise_gap_anchor_includes_previous_complete_halfday(self):
        dates = business_dates("2025-06-10", 22)
        bars = []
        for day in dates:
            if day == "2025-07-03":
                prices = [(100, 102, 99, 101)] * 3 + [(100, 112, 99, 111)]
            elif day == "2025-07-07":
                prices = [(90, 92, 89, 90.9)] * 7
            else:
                prices = [(100, 102, 99, 101)] * 6 + [(100, 106, 99, 105)]
            bars.extend(session_bars(day, prices))
        signals = study.entry_decisions(bars, "hourly_noise_14", CALENDAR)
        item = next(item for item in signals if item["session_date"] == "2025-07-07" and item["slot"] == "10:30")
        self.assertAlmostEqual(item["sigma"], .01, places=12)
        self.assertAlmostEqual(item["upper_band"], 111 * 1.01, places=10)
        self.assertAlmostEqual(item["lower_band"], 90 * .99, places=10)


class IntradayExecutionTests(unittest.TestCase):
    def test_closed_signal_executes_next_open_and_stop_never_trails(self):
        bars = session_bars("2025-03-03", [(90, 96, 89, 95), (101, 102, 100, 101),
                                         (105, 108, 104, 106), (100, 101, 94, 100)]
                            + [(100, 101, 99, 100)] * 3)
        signals = manual_decisions(bars, entries={1: 1})
        signals[2]["atr"] = 20
        trade = study.simulate_asset(bars, signals, config(), calendar=CALENDAR)["trades"][0]
        self.assertEqual(trade["entry_time"], bars[1]["time"])
        self.assertEqual(trade["signal_time"], bars[0]["time"])
        self.assertEqual(trade["entry_price"], 101)
        self.assertEqual(trade["stop"], 95)
        self.assertEqual(trade["exit_price"], 95)
        self.assertEqual(trade["exit_reason"], "stop")

    def test_long_and_short_same_bar_stop_target_collision_stop_wins(self):
        bars = session_bars("2025-03-03", [(100, 101, 99, 100)] * 2
                            + [(100, 120, 80, 100)] + [(100, 101, 99, 100)] * 4)
        for direction, stop in ((1, 94), (-1, 106)):
            with self.subTest(direction=direction):
                trade = study.simulate_asset(bars, manual_decisions(bars, entries={1: direction}),
                                             config(), calendar=CALENDAR)["trades"][0]
                self.assertEqual(trade["side"], direction)
                self.assertEqual(trade["exit_price"], stop)
                self.assertEqual(trade["exit_reason"], "stop")
                self.assertEqual(trade["pnl"], -96)

    def test_exact_adverse_side_friction_and_fees_fit_actual_stop_budget(self):
        settings = config(fee_bps=2, slippage_bps=1, spread_bps=1)
        bars = session_bars("2025-03-03")
        for direction in (1, -1):
            with self.subTest(direction=direction):
                trade = study.simulate_asset(bars, manual_decisions(bars, entries={1: direction}),
                                             settings, calendar=CALENDAR)["trades"][0]
                entry = 100 * (1 + direction * .00015)
                stop = entry - direction * 6
                stop_fill = stop * (1 - direction * .00015)
                unit_loss = -direction * (stop_fill - entry) + (entry + stop_fill) * .0002
                self.assertAlmostEqual(trade["entry_price"], entry, places=10)
                self.assertAlmostEqual(trade["stop"], stop, places=10)
                self.assertEqual(trade["quantity"], 16)
                self.assertEqual(trade["risk_budget"], 100)
                self.assertAlmostEqual(trade["planned_stop_loss"], 16 * unit_loss, places=9)
                self.assertLessEqual(trade["planned_stop_loss"], trade["risk_budget"])
                self.assertAlmostEqual(trade["gross_pnl"] - trade["total_costs"], trade["pnl"], places=9)

    def test_one_times_cash_cap_reserves_entry_fee_for_both_sides(self):
        bars = session_bars("2025-03-03", [(100, 100.00005, 99.99995, 100)] * 7)
        for direction in (1, -1):
            with self.subTest(direction=direction):
                trade = study.simulate_asset(bars, manual_decisions(bars, entries={1: direction}, atr=.0001),
                                             config(fee_bps=1, max_leverage=10), calendar=CALENDAR)["trades"][0]
                self.assertEqual(trade["quantity"], 99)
                self.assertLessEqual(trade["quantity"] * 100 * 1.0001, 10000)
                self.assertLessEqual(trade["planned_stop_loss"], 100)

    def test_prescribed_flatten_open_precedes_later_extremes(self):
        bars = session_bars("2025-03-03", [(100, 101, 99, 100)] * 6 + [(101, 1000, 1, 50)])
        result = study.simulate_asset(bars, manual_decisions(bars, entries={1: 1}), config(), calendar=CALENDAR)
        trade = result["trades"][0]
        self.assertEqual(trade["exit_time"], bars[-1]["time"])
        self.assertEqual(trade["exit_reason"], "session_flatten")
        self.assertEqual(trade["exit_price"], 101)
        self.assertEqual(result["equity_curve"][-1]["worst_equity"], 10016)

    def test_opening_gap_stop_wins_flatten_and_uses_open_not_stop_or_later_low(self):
        bars = session_bars("2025-03-03", [(100, 101, 99, 100)] * 6 + [(93, 1000, 1, 50)])
        result = study.simulate_asset(bars, manual_decisions(bars, entries={1: 1}), config(), calendar=CALENDAR)
        trade = result["trades"][0]
        self.assertEqual(trade["exit_reason"], "gap_stop")
        self.assertEqual(trade["exit_price"], 93)
        self.assertEqual(trade["pnl"], -112)
        self.assertEqual(result["equity_curve"][-1]["worst_equity"], 9888)

    def test_band_exit_open_precedes_later_intrabar_stop(self):
        bars = session_bars("2025-03-03", [(100, 101, 99, 100)] * 2
                            + [(101, 105, 90, 92)] + [(100, 101, 99, 100)] * 4)
        signals = manual_decisions(bars, entries={1: 1}, family="hourly_noise_14")
        signals[2]["exit_long"] = True
        result = study.simulate_asset(bars, signals, config(), calendar=CALENDAR)
        self.assertEqual(result["trades"][0]["exit_reason"], "band_exit")
        self.assertEqual(result["trades"][0]["exit_price"], 101)
        self.assertEqual(result["equity_curve"][2]["worst_equity"], 10016)

    def test_max_one_actual_entry_per_session_with_next_day_reset(self):
        bars = session_bars("2025-03-03", [(100, 101, 99, 100)] * 2
                            + [(100, 101, 93, 100)] + [(100, 101, 99, 100)] * 4)
        bars += session_bars("2025-03-04")
        signals = manual_decisions(bars, entries={1: 1, 3: 1, 8: -1})
        result = study.simulate_asset(bars, signals, config(), calendar=CALENDAR)
        self.assertEqual(len(result["trades"]), 2)
        self.assertEqual([trade["entry_time"] for trade in result["trades"]], [bars[1]["time"], bars[8]["time"]])
        self.assertTrue(all(trade["entry_time"][:10] == trade["exit_time"][:10] for trade in result["trades"]))

    def test_no_entry_on_flatten_and_missing_flatten_never_creates_overnight_fill(self):
        bars = session_bars("2025-03-03")
        self.assertEqual(study.simulate_asset(bars, manual_decisions(bars, entries={6: 1}),
                                              config(), calendar=CALENDAR)["trades"], [])
        with self.assertRaisesRegex(ValueError, "before prescribed flatten"):
            study.simulate_asset(bars, manual_decisions(bars, entries={1: 1}), config(), end=6, calendar=CALENDAR)
        missing = bars[:-1] + session_bars("2025-03-04")
        with self.assertRaisesRegex(ValueError, "would carry overnight"):
            study.simulate_asset(missing, manual_decisions(missing, entries={1: 1}), config(), calendar=CALENDAR)


class IntradayAmendedFeasibilityTests(unittest.TestCase):
    def test_amendment_fingerprint_preserves_original_failure_before_performance(self):
        amended = json.loads((ROOT / "docs" / "intraday-research.json").read_text())
        expected = "39f5012c4c5bc42d91c5c3cd5679d4e4d4210982c07df05a63e12baa20eec447"
        self.assertEqual(amended["protocol_sha256"], expected)
        self.assertEqual(study.digest(amended["protocol"]), expected)
        self.assertEqual(amended["protocol"]["parent_protocol_sha256"], FROZEN["protocol_sha256"])
        self.assertEqual(amended["protocol"]["calendar"]["early_flatten"], "11:30")
        amendment = amended["feasibility_amendment"]
        self.assertTrue(amendment["before_any_performance"])
        self.assertTrue(amendment["source_receipts_unchanged"])
        self.assertTrue(amendment["no_session_removed"])
        self.assertEqual(amendment["original_failure_sha256"], study.file_digest(ROOT / amendment["original_failure_path"]))
        self.assertEqual(FROZEN["phase"], "source_incomplete")
        self.assertFalse(FROZEN.get("training_lock") or FROZEN.get("strategies"))

    def test_nondegenerate_boundary_row_is_only_a_reference_never_imputed_fill(self):
        # Provider's13:00 row is NOT a zero-duration OHLC tick: it contains
        # different O/H/L/C and its covered interval is unknown. Keep only a
        # next-session close reference, never move it into a12:30 opening.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            snapshots, output = root / "snapshots", root / "docs" / "result.json"
            snapshots.mkdir()
            output.parent.mkdir()
            protocol = copy.deepcopy(FROZEN["protocol"])
            protocol["training"] = ["2025-07-02", "2025-07-03"]
            protocol["holdout"] = ["2025-07-03", "2025-07-04"]
            protocol["calendar"]["early_close_dates"] = ["2025-07-03"]
            report = {"phase": "source_incomplete", "protocol": protocol,
                      "protocol_sha256": study.digest(protocol), "source_errors": {},
                      "coverage_errors": {"SPY": "Missing12:30 executable opening"}, "snapshots": []}
            original_bytes = {}
            for symbol in study.SYMBOLS:
                normal = session_bars("2025-07-02")
                normal.append({"time": "2025-07-02T20:00:00Z", "open": 100, "high": 100,
                               "low": 100, "close": 100, "volume": 0})
                half = session_bars("2025-07-03", [(100, 102, 99, 101)] * 2 + [(100, 106, 99, 105)],
                                    calendar={**CALENDAR, "early_flatten": "11:30"})
                half.append({"time": "2025-07-03T17:00:00Z", "open": 110, "high": 120,
                             "low": 90, "close": 111, "volume": 0})
                path = snapshots / f"{symbol}-original.json"
                receipt = {"synthetic_fixture": symbol}
                (snapshots / f"{symbol}-provider-receipt.json").write_text(study.canonical(receipt))
                path.write_text(study.canonical({"bars": normal + half,
                                                "provenance": {"provider": "Synthetic fixture",
                                                               "provider_payload_sha256": study.digest(receipt)}}))
                original_bytes[symbol] = path.read_bytes()
                report["snapshots"].append({"symbol": symbol, "json_path": str(path.relative_to(root)),
                                             "json_sha256": study.file_digest(path)})
            forbidden = copy.deepcopy(report)
            forbidden["training_lock"] = {"primary_strategy_id": "hourly_orb_60"}
            with patch.object(study, "ROOT", root):
                with self.assertRaisesRegex(ValueError, "before any performance"):
                    study.amend_feasibility(forbidden, output, snapshots)
                datasets = study.amend_feasibility(report, output, snapshots)
            self.assertEqual(report["phase"], "prices_snapshotted")
            for symbol in study.SYMBOLS:
                bars = datasets[symbol]
                self.assertEqual(len(bars), 10)
                self.assertEqual(bars[-1]["time"], "2025-07-03T15:30:00Z")
                self.assertEqual(bars[-1]["close"], 105)
                self.assertEqual(bars[-1]["session_close_reference"]["price"], 111)
                self.assertTrue(bars[-1]["session_close_reference"]["non_executable"])
                self.assertFalse(any(bar["time"] == "2025-07-03T16:30:00Z" for bar in bars))
                self.assertEqual((snapshots / f"{symbol}-original.json").read_bytes(), original_bytes[symbol])
                self.assertEqual(next(row["coverage"]["sessions"] for row in report["snapshots"] if row["symbol"] == symbol), 2)

    def test_explicit_1130_halfday_policy_uses_actual_open_before_unknown_interval(self):
        calendar = {**copy.deepcopy(CALENDAR), "early_flatten": "11:30"}
        bars = session_bars("2025-07-03", [(100, 101, 99, 100)] * 2
                            + [(101, 1000, 1, 50)], calendar=calendar)
        coverage = study.validate_sessions(bars, calendar, "2025-07-03", "2025-07-04")
        self.assertEqual(coverage["bars"], 3)
        result = study.simulate_asset(bars, manual_decisions(bars, entries={1: 1}, calendar=calendar),
                                      config(), calendar=calendar)
        self.assertEqual(result["trades"][0]["exit_time"], "2025-07-03T15:30:00Z")
        self.assertEqual(result["trades"][0]["exit_price"], 101)
        self.assertEqual(result["trades"][0]["exit_reason"], "session_flatten")
        self.assertEqual(result["equity_curve"][-1]["worst_equity"], 10016)
        with self.assertRaisesRegex(ValueError, "expected.*12:30"):
            study.validate_sessions(bars, CALENDAR, "2025-07-03", "2025-07-04")

    def test_future_close_reference_is_not_used_until_next_session(self):
        calendar = {**copy.deepcopy(CALENDAR), "early_flatten": "11:30"}
        bars = []
        for day in business_dates("2025-06-10", 22):
            if day == "2025-07-03":
                prices = [(100, 102, 99, 101)] * 2 + [(100, 106, 99, 105)]
            elif day == "2025-07-07":
                prices = [(90, 92, 89, 90.9)] * 7
            else:
                prices = [(100, 102, 99, 101)] * 6 + [(100, 106, 99, 105)]
            bars.extend(session_bars(day, prices, calendar=calendar))
        last = next(index for index, bar in enumerate(bars) if bar["time"] == "2025-07-03T15:30:00Z")
        bars[last]["session_close_reference"] = {"time": "2025-07-03T17:00:00Z", "price": 111,
                                                 "non_executable": True, "slot": "13:00"}
        reference = study.entry_decisions(bars, "hourly_noise_14", calendar)
        changed = copy.deepcopy(bars)
        changed[last]["session_close_reference"]["price"] = 150
        alternate = study.entry_decisions(changed, "hourly_noise_14", calendar)
        self.assertEqual(reference[:last + 1], alternate[:last + 1])
        item = next(item for item in reference if item["session_date"] == "2025-07-07" and item["slot"] == "10:30")
        self.assertAlmostEqual(item["upper_band"], 111 * 1.01, places=10)
        different = next(item for item in alternate if item["session_date"] == "2025-07-07" and item["slot"] == "10:30")
        self.assertAlmostEqual(different["upper_band"], 150 * 1.01, places=10)
        # An uncertain final11:30 close105 cannot silently replace the13:00
        # reference111. Without one, this next-session noise decision is absent.
        missing = copy.deepcopy(bars)
        missing[last].pop("session_close_reference")
        no_reference = study.entry_decisions(missing, "hourly_noise_14", calendar)
        unavailable = next(item for item in no_reference if item["session_date"] == "2025-07-07" and item["slot"] == "10:30")
        self.assertNotIn("upper_band", unavailable)
        self.assertEqual(unavailable["direction"], 0)


class IntradayInferenceTests(unittest.TestCase):
    def test_changed_training_prefix_is_rejected_before_any_holdout_metrics(self):
        bars = session_bars("2025-03-03") + session_bars("2025-03-04")
        datasets = {symbol: copy.deepcopy(bars) for symbol in study.SYMBOLS}
        protocol = {**copy.deepcopy(FROZEN["protocol"]), "training": ["2025-03-03", "2025-03-04"],
                    "holdout": ["2025-03-04", "2025-03-05"]}
        lock = {"protocol_sha256": study.digest(protocol),
                "training_bar_sha256": {symbol: study.digest(bars[:7]) for symbol in study.SYMBOLS}}
        datasets[study.SYMBOLS[0]][0]["close"] = 101
        with patch.object(study, "portfolio_result") as evaluate:
            with self.assertRaisesRegex(ValueError, "Training prices changed"):
                study.evaluate_locked(datasets, lock, protocol)
            evaluate.assert_not_called()

    def test_snapshot_or_provider_receipt_tampering_blocks_before_training(self):
        for target in ("snapshot", "receipt"):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                snapshots, output = root / "snapshots", root / "result.json"
                snapshots.mkdir()
                receipt = {"provider_fixture": "immutable"}
                receipt_path = snapshots / "provider.json"
                receipt_path.write_text(study.canonical(receipt))
                path = snapshots / "quotes.json"
                quotes = {"bars": session_bars("2025-03-03"),
                          "provenance": {"provider_payload_sha256": study.digest(receipt)}}
                path.write_text(study.canonical(quotes))
                report = {"phase": "prices_snapshotted", "protocol": FROZEN["protocol"],
                          "protocol_sha256": FROZEN["protocol_sha256"],
                          "snapshots": [{"symbol": "SPY", "json_path": str(path.relative_to(root)),
                                         "json_sha256": study.file_digest(path),
                                         "provider_receipt_path": str(receipt_path.relative_to(root)),
                                         "provider_receipt_sha256": study.file_digest(receipt_path),
                                         "provenance": quotes["provenance"]}]}
                output.write_text(study.canonical(report))
                if target == "snapshot":
                    quotes["bars"][0]["close"] = 101
                    path.write_text(study.canonical(quotes))
                else:
                    receipt_path.write_text(study.canonical({"provider_fixture": "changed"}))
                with patch.object(study, "ROOT", root), patch.object(study, "training_lock") as select:
                    with self.assertRaisesRegex(ValueError, "fingerprint mismatch"):
                        study.run(output, snapshots)
                    select.assert_not_called()

    def test_five_session_blocks_are_kept_together_and_not_iid_trades(self):
        values = [{"date": str(index), "return": (index + 1) / 1000} for index in range(20)]
        class FirstBlock:
            def randrange(self, count):
                self.assert_count = count
                return 0
        with patch.object(study.random, "Random", return_value=FirstBlock()):
            result = study.daily_bootstrap(values, resamples=100)
        self.assertEqual(result["sessions"], 20)
        self.assertEqual(result["block_length"], 5)
        self.assertEqual(result["mean_daily_ci_pct"], [.3, .3])
        self.assertAlmostEqual(result["mean_daily_pct"], 1.05, places=12)
        self.assertIn("not pooled trades", result["unit"])

    def test_bootstrap_small_sample_is_unsupported_and_seed_is_deterministic(self):
        self.assertEqual(study.daily_bootstrap([.01] * 19)["status"], "insufficient")
        values = [.02, -.02, .001, -.001, 0] * 8
        self.assertEqual(study.daily_bootstrap(values, resamples=100), study.daily_bootstrap(values, resamples=100))
        with self.assertRaisesRegex(ValueError, "Invalid bootstrap"):
            study.daily_bootstrap([float("nan")] * 20)

    def test_three_assets_produce_one_joint_daily_observation_and_require_same_slots(self):
        bars = session_bars("2025-03-03") + session_bars("2025-03-04")
        datasets = {symbol: copy.deepcopy(bars) for symbol in study.SYMBOLS}
        result = study.portfolio_result(datasets, "hourly_orb_60", "2025-03-03", "2025-03-05", calendar=CALENDAR)
        self.assertEqual(len(result["daily_returns"]), 2)
        self.assertEqual(result["daily_returns"], [{"date": "2025-03-03", "return": 0}, {"date": "2025-03-04", "return": 0}])
        self.assertEqual(result["metrics"]["total_trades"], 0)
        mismatched = copy.deepcopy(datasets)
        mismatched[study.SYMBOLS[1]].pop(2)
        with self.assertRaisesRegex(ValueError, "synchronized slots"):
            study.portfolio_result(mismatched, "hourly_orb_60", "2025-03-03", "2025-03-05", calendar=CALENDAR)

    def test_training_lock_never_passes_future_prices_to_selection(self):
        bars = session_bars("2025-03-03") + session_bars("2025-03-04")
        datasets = {symbol: copy.deepcopy(bars) for symbol in study.SYMBOLS}
        protocol = {**copy.deepcopy(FROZEN["protocol"]), "training": ["2025-03-03", "2025-03-04"],
                    "holdout": ["2025-03-04", "2025-03-05"]}
        seen = []
        def train_only(values, family, start, end, **kwargs):
            seen.append(family)
            self.assertEqual((start, end), tuple(protocol["training"]))
            self.assertTrue(all(bar["time"][:10] < end for data in values.values() for bar in data))
            return {"metrics": {"net_return_pct": 1, "max_drawdown_pct": 0}}
        with patch.object(study, "portfolio_result", side_effect=train_only):
            lock = study.training_lock(datasets, protocol)
        self.assertEqual(set(seen), set(study.STRATEGY_IDS))
        self.assertEqual(lock["primary_strategy_id"], sorted(study.STRATEGY_IDS)[0])
        expected = {symbol: study.digest(bars[:7]) for symbol in study.SYMBOLS}
        self.assertEqual(lock["training_bar_sha256"], expected)


if __name__ == "__main__":
    unittest.main()
