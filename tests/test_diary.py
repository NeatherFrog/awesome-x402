"""Diary truthfulness, calendar boundaries and causal explanations."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from propdesk import diary


NOW = datetime(2026, 10, 1, 11, tzinfo=timezone.utc)


def bars():
    start = datetime(2026, 7, 1, 13, 30, tzinfo=timezone.utc)
    return [{"time": (start + timedelta(days=i)).isoformat().replace("+00:00", "Z"),
             "open": 100 + i / 10, "high": 101 + i / 10, "low": 99 + i / 10,
             "close": 100.5 + i / 10, "volume": 1000} for i in range(92)]


def trade(**changes):
    row = {"symbol": "QQQ", "direction": "long", "entry_time": "2026-08-20T13:30:00Z",
           "signal_time": "2026-08-19T13:30:00Z", "exit_time": "2026-09-10T13:30:00Z",
           "entry_price": 110, "raw_entry_price": 109.9835, "exit_price": 112,
           "raw_exit_price": 112.0168, "stop": 104, "risk_amount": 250, "quantity": 30,
           "pnl": 55, "return_r": .22, "fees": 2, "slippage": 2, "spread": 1,
           "financing_total": 0, "total_costs": 5, "exit_reason": "signal_exit"}
    row.update(changes)
    return row


def report(trades=None):
    protocol = {"version": "test-fixed-policy", "rules": {"bt_sma_10_30": "strict crossover"}}
    lock = {"primary_strategy_id": "bt_sma_10_30"}
    return {"phase": "completed", "protocol": protocol, "protocol_sha256": diary._digest(protocol),
            "training_lock": lock, "training_lock_sha256": diary._digest(lock),
            "primary_strategy_id": "bt_sma_10_30", "snapshots": [], "strategies": [
                {"id": "bt_sma_10_30", "name": "SMA10/30", "primary": True,
                 "eligible_historical_price_model": False, "real_prop_qualified": False,
                 "reasons": ["Historical CI includes zero"], "windows": {"confirmation": {
                     "monthly_returns": [{"month": "2026-08", "return": .01}, {"month": "2026-09", "return": -.003}],
                     "metrics": {"initial_equity": 100000},
                     "equity_curve": [
                         {"time": "2026-08-01T13:30:00Z", "equity": 100000},
                         {"time": "2026-08-31T13:30:00Z", "equity": 101000},
                         {"time": "2026-09-01T13:30:00Z", "equity": 101050},
                         {"time": "2026-09-30T13:30:00Z", "equity": 100700}],
                     "trades": [trade()] if trades is None else trades}}}]}


def mean_report(trades=None):
    value = report(trades)
    strategy_id = "rsi2_pullback_5"
    value["protocol"] = {"version": "fixed-mean-test", "inputs": [],
                         "rules": {strategy_id: "RSI2<5 and close>SMA200; exit level close>SMA5"}}
    value["protocol_sha256"] = diary._digest(value["protocol"])
    value["training_lock"] = {"primary_strategy_id": strategy_id}
    value["training_lock_sha256"] = diary._digest(value["training_lock"])
    value["primary_strategy_id"] = strategy_id
    value.pop("snapshots")
    value["strategies"][0].update(id=strategy_id, name="Fixed RSI2 pullback")
    return value


def mean_bars():
    start = datetime(2026, 1, 1, 13, 30, tzinfo=timezone.utc)
    signal_index = (datetime(2026, 8, 19, tzinfo=timezone.utc).date() - start.date()).days
    result = []
    for index in range(273):
        close = 80 + .2 * index
        if signal_index - 3 <= index <= signal_index:
            close -= index - signal_index + 4
        result.append({"time": (start + timedelta(days=index)).isoformat().replace("+00:00", "Z"),
                       "open": close, "high": close + 1, "low": close - 1, "close": close, "volume": 1000})
    return result


class DiaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.path = self.root / "docs/sourced-strategy-research.json"

    def tearDown(self):
        self.temp.cleanup()

    def save(self, value):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(value), encoding="utf-8")

    def snapshot(self, value, rows=None):
        path = self.root / "data/sourced-history/QQQ-1d.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"bars": bars() if rows is None else rows}), encoding="utf-8")
        value["snapshots"] = [{"symbol": "QQQ", "json_path": str(path.relative_to(self.root)),
                               "json_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}]
        return path

    def save_mean(self, value):
        path = self.root / "docs/mean-reversion-research.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")

    def mean_snapshot(self, value, rows=None):
        path = self.snapshot(value, mean_bars() if rows is None else rows)
        value["protocol"]["inputs"] = value.pop("snapshots")
        value["protocol_sha256"] = diary._digest(value["protocol"])
        return path

    def test_missing_report_is_explicit_and_get_has_no_network_or_writes(self):
        journal = self.root / "journal.json"
        journal.write_text('{"real":1}', encoding="utf-8")
        with patch("propdesk.diary.feeds.get_history", side_effect=AssertionError("GET must not request")):
            result = diary.build_diary(self.root, now=NOW)
        self.assertEqual(result["state"], "no_report")
        self.assertEqual(result["trades"], [])
        self.assertFalse(result["live_orders"])
        self.assertEqual(list(self.root.iterdir()), [journal])
        self.assertEqual(journal.read_text(), '{"real":1}')

    def test_report_integrity_and_selection_lock_are_checked(self):
        value = report()
        value["protocol"]["version"] = "changed-after-freeze"
        self.save(value)
        self.assertEqual(diary.build_diary(self.root, now=NOW)["state"], "unavailable")
        value = report()
        value["training_lock"]["primary_strategy_id"] = "qc_ema_15_30"
        self.save(value)
        self.assertEqual(diary.build_diary(self.root, now=NOW)["state"], "unavailable")
        value = report()
        value["primary_strategy_id"] = "qc_ema_15_30"
        self.save(value)
        self.assertEqual(diary.build_diary(self.root, now=NOW)["state"], "unavailable")

    def test_predeclared_report_waits_without_fabricating_a_strategy(self):
        value = report()
        value.pop("primary_strategy_id")
        value.pop("training_lock")
        value.pop("training_lock_sha256")
        value["phase"] = "predeclared"
        self.save(value)
        result = diary.build_diary(self.root, now=NOW)
        self.assertEqual(result["state"], "in_progress")
        self.assertIsNone(result["strategy"])
        value = report()
        value["phase"] = "training_locked"
        value.pop("strategies")
        self.save(value)
        self.assertEqual(diary.build_diary(self.root, now=NOW)["state"], "in_progress")

    def test_latest_completed_month_uses_kyiv_calendar_and_year_rollover(self):
        later = datetime(2026, 9, 30, 21, 5, tzinfo=timezone.utc)
        earlier = datetime(2026, 9, 30, 20, 30, tzinfo=timezone.utc)
        self.assertEqual(diary.build_diary(self.root, now=later)["period"]["month"], "2026-09")
        self.assertEqual(diary.build_diary(self.root, now=earlier)["period"]["month"], "2026-08")
        january = datetime(2027, 1, 1, 12, tzinfo=timezone.utc)
        self.assertEqual(diary.build_diary(self.root, now=january)["period"]["month"], "2026-12")
        with self.assertRaises(ValueError):
            diary.build_diary(self.root, now=NOW.replace(tzinfo=None))
        for invalid in ("2026-10", "2026-13", "../2026-09", "0000-09"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                diary.build_diary(self.root, now=NOW, month=invalid)

    def test_unqualified_primary_still_has_truthful_replay_and_carried_position(self):
        self.save(report())
        result = diary.build_diary(self.root, now=NOW)
        self.assertEqual(result["state"], "ready")
        self.assertFalse(result["qualification"]["real_prop_qualified"])
        self.assertEqual(result["qualification"]["status"], "research_watch_only")
        self.assertTrue(result["trades"][0]["carried_from_previous_month"])
        self.assertEqual(result["summary"]["closed_trade_pnl"], 55)
        self.assertEqual(result["summary"]["month_equity_change"], -300)
        self.assertAlmostEqual(result["summary"]["month_return_pct"], -300 / 101000 * 100)
        self.assertEqual(result["summary"]["entries_in_month"], 0)
        self.assertEqual(result["summary"]["live_executions"], 0)
        self.assertEqual(result["trades"][0]["chart"]["state"], "unavailable")
        self.assertEqual(result["trades"][0]["tradingview_screenshot"]["state"], "not_captured")

    def test_forced_final_liquidation_is_valuation_and_not_a_closed_trade(self):
        self.save(report([trade(exit_time="2026-09-30T13:30:00Z", exit_reason="end_of_sample")]))
        result = diary.build_diary(self.root, now=NOW)
        row = result["trades"][0]
        self.assertEqual(row["status"], "open_at_period_end")
        self.assertIsNone(row["exit_time"])
        self.assertIsNone(row["exit_price"])
        self.assertIsNone(row["pnl"])
        self.assertIsNone(row["costs"])
        self.assertEqual(row["valuation_boundary"]["time"], "2026-09-30T20:00:00Z")
        self.assertEqual(row["valuation_boundary"]["hypothetical_liquidation_pnl"], 55)
        self.assertEqual(result["summary"]["closed_in_month"], 0)
        self.assertEqual(result["summary"]["closed_trade_pnl"], 0)

    def test_later_exit_is_hidden_from_earlier_month_open_position(self):
        self.save(report())
        row = diary.build_diary(self.root, now=NOW, month="2026-08")["trades"][0]
        self.assertEqual(row["status"], "open_at_period_end")
        for field in ("exit_time", "exit_price", "raw_exit_price", "exit_reason", "pnl", "return_r", "costs"):
            self.assertIsNone(row[field], field)
        self.assertNotIn("valuation_boundary", row)
        self.assertFalse(any("пересекла SMA30 вниз" in text for text in row["exit_reasons"]))

    def test_entry_explanations_use_signal_prefix_and_chart_has_no_future_bars(self):
        value = report()
        original = bars()
        self.snapshot(value, original)
        self.save(value)
        first = diary.build_diary(self.root, now=NOW, month="2026-08")["trades"][0]
        changed = deepcopy(original)
        for bar in changed:
            if bar["time"] > "2026-08-19T13:30:00Z":
                for field in ("open", "high", "low", "close"):
                    bar[field] *= 100
        self.snapshot(value, changed)
        self.save(value)
        second = diary.build_diary(self.root, now=NOW, month="2026-08")["trades"][0]
        self.assertEqual(first["entry_reasons"], second["entry_reasons"])
        self.assertEqual(first["entry_indicators"], second["entry_indicators"])
        self.assertEqual(first["signal_known_after"], "2026-08-19T20:00:00Z")
        self.assertTrue(all(row["time"][:7] <= "2026-08" for row in second["chart"]["bars"]))
        self.assertFalse(first["chart"]["is_tradingview_screenshot"])
        self.assertLessEqual(len(first["chart"]["bars"]), 120)

    def test_original_snapshot_hash_failure_does_not_silently_use_other_quotes(self):
        value = report()
        path = self.snapshot(value)
        self.save(value)
        path.write_text('{"bars":[]}', encoding="utf-8")
        row = diary.build_diary(self.root, now=NOW)["trades"][0]
        self.assertEqual(row["chart"]["source"], "snapshot_hash_mismatch")
        self.assertEqual(row["chart"]["bars"], [])

    def test_snapshot_path_cannot_read_arbitrary_local_files(self):
        value = report()
        value["snapshots"] = [{"symbol": "QQQ", "json_path": "../../private.json", "json_sha256": "a" * 64}]
        self.save(value)
        row = diary.build_diary(self.root, now=NOW)["trades"][0]
        self.assertEqual(row["chart"]["source"], "invalid_snapshot_path")
        self.assertEqual(row["chart"]["bars"], [])

    def test_signal_bar_must_have_closed_before_entry_not_merely_opened(self):
        self.save(report([trade(signal_time="2026-08-20T12:30:00Z")]))
        result = diary.build_diary(self.root, now=NOW)
        self.assertEqual(result["state"], "unavailable")
        self.assertEqual(result["trades"], [])

    def test_intrabar_stop_keeps_unknown_fill_time_and_month_without_data_is_explicit(self):
        self.save(report([trade(exit_reason="stop")]))
        result = diary.build_diary(self.root, now=NOW)
        self.assertEqual(result["trades"][0]["exit_time_precision"], "intrabar_time_unknown")
        missing = diary.build_diary(self.root, now=NOW, month="2026-07")
        self.assertEqual(missing["state"], "unavailable")
        self.assertEqual(missing["available_months"], ["2026-08", "2026-09"])
        self.assertEqual(missing["trades"], [])

    def test_warming_fetches_fixed_chart_range_once_and_uses_custom_local_cache(self):
        loader = Mock(return_value={"bars": bars(), "provenance": {"provider": "fixture"}})
        cache = self.root / "runtime/chart-data"
        first = diary.warm_diary_quotes(self.root, now=NOW, history_loader=loader, directory=cache)
        self.assertEqual(loader.call_count, 5)
        self.assertTrue(all(call.args[1:] == ("1d", "5y") for call in loader.call_args_list))
        self.assertTrue(all(row["state"] == "loaded" for row in first["symbols"].values()))
        second = diary.warm_diary_quotes(self.root, now=NOW, history_loader=loader, directory=cache)
        self.assertEqual(loader.call_count, 5)
        self.assertTrue(all(row["state"] == "cached" for row in second["symbols"].values()))
        self.save(report())
        row = diary.build_diary(self.root, now=NOW, directory=cache)["trades"][0]
        self.assertEqual(row["chart"]["source"], "runtime_history_revision_possible")
        self.assertEqual(row["chart"]["state"], "ready")

    def test_warming_failures_are_explicit_and_do_not_create_synthetic_candles(self):
        loader = Mock(side_effect=ValueError("fixture source unavailable"))
        result = diary.warm_diary_quotes(self.root, now=NOW, history_loader=loader)
        self.assertTrue(all(row["state"] == "unavailable" for row in result["symbols"].values()))
        files = list((self.root / ".local/diary-quotes").iterdir())
        self.assertEqual([path.name for path in files], ["status.json"])

    def test_explicit_study_choice_never_selects_another_report_or_unknown_path(self):
        self.save(report())
        result = diary.build_diary(self.root, now=NOW, study="mean_reversion")
        self.assertEqual(result["state"], "no_report")
        self.assertEqual(result["study"], "mean_reversion")
        self.assertEqual(diary.build_diary(self.root, now=NOW)["study"], "sourced_daily")
        for invalid in ("intraday", "best_returns", "../../private", None, {}):
            with self.subTest(study=invalid), self.assertRaises(ValueError):
                diary.build_diary(self.root, now=NOW, study=invalid)

    def test_mean_study_protocol_lock_primary_and_family_guards(self):
        for alteration in ("protocol", "lock", "primary", "family", "diagnostic"):
            value = mean_report()
            if alteration == "protocol":
                value["protocol"]["version"] = "after-freeze"
            elif alteration == "lock":
                value["training_lock"]["primary_strategy_id"] = "another"
            elif alteration == "primary":
                value["primary_strategy_id"] = "another"
            elif alteration == "family":
                value["primary_strategy_id"] = "bt_sma_10_30"
                value["training_lock"]["primary_strategy_id"] = "bt_sma_10_30"
                value["training_lock_sha256"] = diary._digest(value["training_lock"])
                value["strategies"][0]["id"] = "bt_sma_10_30"
            else:
                value["strategies"][0]["primary"] = False
            self.save_mean(value)
            result = diary.build_diary(self.root, now=NOW, study="mean_reversion")
            self.assertEqual(result["state"], "unavailable", alteration)
            self.assertEqual(result["trades"], [], alteration)

    def test_wilder_rsi_seed_and_smoothing_have_independent_hand_computed_values(self):
        self.assertIsNone(diary._rsi2([100, 102]))
        self.assertAlmostEqual(diary._rsi2([100, 102, 101]), 66.66666666666667)
        self.assertAlmostEqual(diary._rsi2([100, 102, 101, 103]), 85.71428571428571)
        self.assertEqual(diary._rsi2([100, 100, 100, 100]), 50)
        self.assertEqual(diary._rsi2([100, 101, 102, 103]), 100)
        self.assertEqual(diary._rsi2([100, 99, 98, 97]), 0)

    def test_mean_explanation_has_exact_rsi_and_only_prior_signal_quotes(self):
        value = mean_report()
        original = mean_bars()
        self.mean_snapshot(value, original)
        self.save_mean(value)
        first = diary.build_diary(self.root, now=NOW, month="2026-08", study="mean_reversion")["trades"][0]
        self.assertAlmostEqual(first["entry_indicators"]["rsi2"], 1.6393442622950811)
        self.assertTrue(first["entry_indicators"]["entry_condition"])
        self.assertEqual(first["entry_indicators"]["calculation_basis"], "frozen_study_snapshot")
        self.assertTrue(any("RSI2 строго < 5" in note for note in first["entry_reasons"]))
        self.assertTrue(any("пересечение SMA5 не требуется" in note for note in first["entry_reasons"]))
        self.assertIsNone(first["take_profit"])
        changed = deepcopy(original)
        for bar in changed:
            if bar["time"] > "2026-08-19T13:30:00Z":
                for field in ("open", "high", "low", "close"):
                    bar[field] *= 100
        self.mean_snapshot(value, changed)
        self.save_mean(value)
        second = diary.build_diary(self.root, now=NOW, month="2026-08", study="mean_reversion")["trades"][0]
        self.assertEqual(first["entry_indicators"], second["entry_indicators"])
        self.assertEqual(first["entry_reasons"], second["entry_reasons"])
        self.assertTrue(all(bar["time"][:7] <= "2026-08" for bar in second["chart"]["bars"]))

    def test_mean_strict_entry_equalities_are_not_admitted(self):
        rows = mean_bars()
        with patch("propdesk.diary._rsi2", return_value=5.0):
            _, indicators = diary._entry_context(trade(), "rsi2_pullback_5", rows, "fixture")
        self.assertFalse(indicators["entry_condition"])
        flat = deepcopy(rows)
        for bar in flat:
            bar.update(open=100, high=101, low=99, close=100)
        with patch("propdesk.diary._rsi2", return_value=0.0):
            _, indicators = diary._entry_context(trade(), "rsi2_pullback_5", flat, "fixture")
        self.assertEqual(indicators["close"], indicators["sma200"])
        self.assertFalse(indicators["entry_condition"])

    def test_mean_input_hash_failure_preserves_replay_without_substituting_quotes(self):
        value = mean_report()
        path = self.mean_snapshot(value)
        self.save_mean(value)
        cache = self.root / ".local/diary-quotes"
        cache.mkdir(parents=True)
        (cache / "QQQ-1d.json").write_text(json.dumps({"symbol": "QQQ", "bars": mean_bars()}), encoding="utf-8")
        path.write_text('{"bars":[]}', encoding="utf-8")
        result = diary.build_diary(self.root, now=NOW, study="mean_reversion")
        self.assertEqual(result["state"], "ready")
        self.assertEqual(result["trades"][0]["chart"]["source"], "snapshot_hash_mismatch")
        self.assertEqual(result["trades"][0]["chart"]["bars"], [])

    def test_mean_exit_is_a_level_and_end_of_sample_remains_a_valuation(self):
        value = mean_report()
        value["strategies"][0]["real_prop_qualified"] = True
        self.save_mean(value)
        result = diary.build_diary(self.root, now=NOW, study="mean_reversion")
        self.assertEqual(result["summary"]["month_equity_change"], -300)
        self.assertFalse(result["qualification"]["real_prop_qualified"])
        self.assertTrue(any("достаточно уровня" in note for note in result["trades"][0]["exit_reasons"]))
        self.save_mean(mean_report([trade(exit_time="2026-09-30T13:30:00Z", exit_reason="end_of_sample")]))
        result = diary.build_diary(self.root, now=NOW, study="mean_reversion")
        self.assertEqual(result["summary"]["closed_in_month"], 0)
        self.assertEqual(result["summary"]["closed_trade_pnl"], 0)
        self.assertIsNone(result["trades"][0]["exit_price"])
        self.assertIn("valuation_boundary", result["trades"][0])

    def test_completed_audit_phase_is_not_described_as_pending_review(self):
        value = report()
        value["phase"] = "final_review"
        self.save(value)
        result = diary.build_diary(self.root, now=NOW)
        self.assertEqual(result["state"], "ready")
        self.assertFalse(any("ожидает завершения технической проверки" in note for note in result["warnings"]))


if __name__ == "__main__":
    unittest.main()
