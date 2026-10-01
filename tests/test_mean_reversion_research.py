"""Independent synthetic RSI/causality/accounting checks, not alpha evidence."""

import copy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from propdesk import backtest, market
from scripts import research_mean_reversion as study


ROOT = Path(__file__).resolve().parents[1]
FROZEN = json.loads((ROOT / "docs" / "mean-reversion-research.json").read_text())


def bars_from_closes(closes, *, start="2020-01-01"):
    first = datetime.fromisoformat(start).replace(tzinfo=timezone.utc)
    return [{"time": (first + timedelta(days=index)).isoformat().replace("+00:00", "Z"),
             "open": float(close), "high": float(close + .5),
             "low": float(close - .5), "close": float(close), "volume": 1000.0}
            for index, close in enumerate(closes)]


def pullback_bars():
    return bars_from_closes([100] * 200 + [120] + list(range(119, 109, -1)) + [112, 114, 116, 118])


def short_protocol():
    protocol = copy.deepcopy(FROZEN["protocol"])
    protocol["windows"]["training"] = ["2020-01-01", "2020-02-01"]
    protocol["selection"]["training_folds"] = [["2020-01-01", "2020-01-11"],
                                                ["2020-01-11", "2020-01-21"],
                                                ["2020-01-21", "2020-02-01"]]
    return protocol


class MeanReversionRsiTests(unittest.TestCase):
    def test_wilder_seed_uses_two_changes_and_recursive_smoothing(self):
        actual = study.wilder_rsi([100, 102, 101, 100, 103])
        self.assertEqual(actual[:2], [None, None])
        self.assertAlmostEqual(actual[2], 100 - 100 / 3, places=12)  # gain1/loss.5
        self.assertAlmostEqual(actual[3], 40, places=12)  # gain.5/loss.75
        self.assertAlmostEqual(actual[4], 100 - 100 / (1 + 1.75 / .375), places=12)

    def test_flat_and_one_sided_changes_have_explicit_finite_conventions(self):
        self.assertEqual(study.wilder_rsi([100] * 5), [None, None, 50, 50, 50])
        self.assertEqual(study.wilder_rsi([100, 101, 102]), [None, None, 100])
        self.assertEqual(study.wilder_rsi([100, 99, 98]), [None, None, 0])
        self.assertEqual(study.wilder_rsi([100, 99]), [None, None])
        with self.assertRaisesRegex(ValueError, "Positive RSI period"):
            study.wilder_rsi([100, 99], period=0)

    def test_entry_threshold_is_strict_five_and_sma200_equality_does_not_enter(self):
        bars = bars_from_closes([100] * 200 + [101, 101])
        for value, expected in ((5, False), (4.999, True), (10, False)):
            with self.subTest(value=value), patch.object(study, "wilder_rsi", return_value=[value] * len(bars)):
                self.assertEqual(study.decisions(bars)[201]["entry"], expected)
        equal = bars_from_closes([100] * 202)
        with patch.object(study, "wilder_rsi", return_value=[4] * len(equal)):
            self.assertFalse(study.decisions(equal)[201]["entry"])

    def test_level_exit_holds_equality_and_does_not_require_fresh_cross(self):
        bars = bars_from_closes([100] * 200 + [101] * 5 + [102, 103, 103])
        observations = study.decisions(bars)
        self.assertEqual(observations[205]["close"], observations[205]["sma5"])
        self.assertFalse(observations[205]["exit"])
        self.assertTrue(observations[206]["exit"])
        self.assertTrue(observations[207]["exit"])
        self.assertGreater(observations[206]["close"], observations[206]["sma5"])

    def test_no_entry_before_two_hundred_closed_prices(self):
        bars = bars_from_closes([100] * 202)
        observations = study.decisions(bars)
        self.assertTrue(all(item is None for item in observations[:200]))
        self.assertIsNotNone(observations[200])
        self.assertEqual(observations[200]["signal_time"], bars[199]["time"])

    def test_decisions_use_only_previous_closed_price_and_are_prefix_causal(self):
        bars = pullback_bars()
        cutoff = 211
        original = study.decisions(bars)
        self.assertTrue(any(item and item["entry"] for item in original[:cutoff]))
        changed = copy.deepcopy(bars)
        for bar in changed[cutoff:]:
            for key in ("open", "high", "low", "close"):
                bar[key] *= 5
        self.assertEqual(original[:cutoff], study.decisions(changed)[:cutoff])
        self.assertEqual(original[:cutoff], study.decisions(bars[:cutoff]))
        for index, item in enumerate(original):
            if item is not None:
                self.assertEqual(item["signal_time"], bars[index - 1]["time"])
                self.assertEqual(item["close"], bars[index - 1]["close"])

    def test_first_pullback_fills_next_open_and_uses_closed_atr(self):
        bars = pullback_bars()
        observations = study.decisions(bars)
        entered = next(index for index, item in enumerate(observations) if item and item["entry"])
        bars[entered]["open"] = 113
        bars[entered]["high"] = max(113.5, bars[entered]["high"])
        observations = study.decisions(bars)
        config = backtest.normalize_config({"account_size": 20000, "risk_pct": 1.25,
                    "fee_bps": 0, "slippage_bps": 0, "spread_bps": 0,
                    "quantity_step": 1, "max_leverage": 1})
        result = study.daily.simulate_asset(bars, observations, config)
        trade = result["trades"][0]
        self.assertEqual(trade["entry_time"], bars[entered]["time"])
        self.assertEqual(trade["signal_time"], bars[entered - 1]["time"])
        self.assertEqual(trade["entry_price"], 113)
        self.assertAlmostEqual(trade["stop"], 113 - 3 * observations[entered]["atr"], places=10)
        self.assertEqual(trade["risk_amount"], 250)


class MeanReversionInputTests(unittest.TestCase):
    def fixture(self, directory):
        root = Path(directory)
        (root / "docs").mkdir()
        audit, parent = root / "docs" / "mean-reversion-sources.json", root / "docs" / "sourced-strategy-research.json"
        audit.write_text('{"source":"synthetic"}')
        parent.write_text('{"provenance":"synthetic"}')
        protocol = {"symbols": list(study.daily.SYMBOLS), "inputs": [],
                    "sources_audit_sha256": study.daily.file_digest(audit),
                    "parent_data_report_sha256": study.daily.file_digest(parent)}
        bars = bars_from_closes([100, 101, 102])
        for symbol in study.daily.SYMBOLS:
            path = root / f"{symbol}.json"
            path.write_text(study.daily.canonical({"bars": bars}))
            csv = root / f"{symbol}.csv"
            csv.write_text("time,open,high,low,close,volume\nfixture\n")
            receipt = root / f"{symbol}-receipt.json"
            receipt.write_text(study.daily.canonical({"provider_fixture": symbol}))
            record = {"symbol": symbol, "bars_sha256": market.data_fingerprint(bars)}
            for key, value in (("json", path), ("csv", csv), ("provider_receipt", receipt)):
                record[key + "_path"] = str(value.relative_to(root))
                record[key + "_sha256"] = study.daily.file_digest(value)
            protocol["inputs"].append(record)
        return root, {"protocol": protocol, "protocol_sha256": study.daily.digest(protocol)}, bars

    def test_all_five_inputs_are_verified_and_keep_exact_same_dates(self):
        with tempfile.TemporaryDirectory() as directory:
            root, report, bars = self.fixture(directory)
            with patch.object(study, "ROOT", root):
                datasets = study.load_inputs(report)
            self.assertEqual(set(datasets), set(study.daily.SYMBOLS))
            self.assertTrue(all(values == bars for values in datasets.values()))

    def test_json_csv_and_provider_tampering_are_rejected(self):
        for kind in ("json", "csv", "provider_receipt"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                root, report, _ = self.fixture(directory)
                record = report["protocol"]["inputs"][0]
                (root / record[kind + "_path"]).write_text('changed')
                with patch.object(study, "ROOT", root):
                    with self.assertRaisesRegex(ValueError, "snapshot/receipt changed"):
                        study.load_inputs(report)

    def test_protocol_source_audit_and_parent_provenance_cannot_change(self):
        for kind in ("protocol", "audit", "parent"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                root, report, _ = self.fixture(directory)
                if kind == "protocol":
                    report["protocol"]["symbols"] = []
                else:
                    name = "mean-reversion-sources.json" if kind == "audit" else "sourced-strategy-research.json"
                    (root / "docs" / name).write_text('{"changed":true}')
                with patch.object(study, "ROOT", root):
                    with self.assertRaisesRegex(ValueError, "changed"):
                        study.load_inputs(report)

    def test_price_fingerprint_and_missing_dates_are_separate_blockers(self):
        for kind in ("price", "date"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                root, report, bars = self.fixture(directory)
                record = report["protocol"]["inputs"][0]
                changed = copy.deepcopy(bars)
                if kind == "price":
                    changed[0]["close"] = 100.25
                else:
                    changed.pop(1)
                    record["bars_sha256"] = market.data_fingerprint(changed)
                path = root / record["json_path"]
                path.write_text(study.daily.canonical({"bars": changed}))
                record["json_sha256"] = study.daily.file_digest(path)
                report["protocol_sha256"] = study.daily.digest(report["protocol"])
                with patch.object(study, "ROOT", root):
                    with self.assertRaisesRegex(ValueError, "price fingerprint" if kind == "price" else "sessions must all match"):
                        study.load_inputs(report)


class MeanReversionTrainingTests(unittest.TestCase):
    def test_training_and_benchmark_receive_physically_truncated_inputs(self):
        bars = bars_from_closes([100] * 65)
        datasets = {symbol: copy.deepcopy(bars) for symbol in study.daily.SYMBOLS}
        protocol = short_protocol()
        report = {"phase": "predeclared", "protocol": protocol, "protocol_sha256": study.daily.digest(protocol)}
        calls = []
        def train_only(values, start, end, **kwargs):
            calls.append((start, end, kwargs))
            self.assertLessEqual(end, protocol["windows"]["training"][1])
            self.assertTrue(all(bar["time"][:10] < "2020-02-01" for rows in values.values() for bar in rows))
            return {"metrics": {"net_profit": 100, "net_return_pct": .1, "max_drawdown_pct": 0},
                    "equity_curve": [{"equity": 100000}, {"equity": 100100}]}
        with tempfile.TemporaryDirectory() as directory:
            output, work = Path(directory) / "report.json", Path(directory) / "state"
            with patch.object(study, "freeze", return_value=report), \
                 patch.object(study, "load_inputs", return_value=datasets), \
                 patch.object(study, "portfolio", side_effect=train_only), \
                 patch.object(study, "evaluate", return_value={"id": study.STRATEGY_ID,
                                                              "eligible_historical_price_model": False}):
                result = study.run(output, work)
            self.assertEqual(len(calls), 5)  # main training, benchmark, three folds
            expected = {symbol: market.data_fingerprint(bars[:31]) for symbol in study.daily.SYMBOLS}
            self.assertEqual(result["training_lock"]["training_bar_sha256"], expected)
            self.assertEqual(result["training_lock"]["benchmark_scale"], 1)
            self.assertIsNone(result["selected_strategy_id"])
            self.assertEqual(json.loads((work / "training-lock.json").read_text()), result["training_lock"])

    def test_changed_protocol_lock_or_training_prices_fail_before_holdouts(self):
        for kind in ("protocol", "lock", "prices"):
            with self.subTest(kind=kind):
                bars = bars_from_closes([100] * 65)
                datasets = {symbol: copy.deepcopy(bars) for symbol in study.daily.SYMBOLS}
                protocol = short_protocol()
                protocol_hash = study.daily.digest(protocol)
                lock = {"protocol_sha256": protocol_hash, "benchmark_scale": .5,
                        "training_bar_sha256": study.training_prefixes(datasets, "2020-02-01")}
                report = {"protocol": protocol, "protocol_sha256": protocol_hash,
                          "training_lock": lock, "training_lock_sha256": study.daily.digest(lock)}
                if kind == "protocol":
                    protocol["windows"]["training"][1] = "2020-02-02"
                elif kind == "lock":
                    lock["benchmark_scale"] = 1
                else:
                    datasets[study.daily.SYMBOLS[0]][0]["close"] = 100.25
                with patch.object(study, "portfolio") as evaluate:
                    with self.assertRaisesRegex(ValueError, "changed"):
                        study.evaluate(datasets, report)
                    evaluate.assert_not_called()


class MeanReversionPortfolioTests(unittest.TestCase):
    def test_joint_capital_is_sum_of_five_cash_buckets_and_returns_use_net_costs(self):
        bars = pullback_bars()
        datasets = {symbol: copy.deepcopy(bars) for symbol in study.daily.SYMBOLS}
        result = study.portfolio(datasets, "2020-01-01", "2021-01-01")
        self.assertTrue(result["trades"])
        net = sum(trade["pnl"] for trade in result["trades"])
        self.assertAlmostEqual(result["metrics"]["net_profit"], net, places=5)
        self.assertAlmostEqual(result["metrics"]["final_equity"], 100000 + net, places=5)
        for index, point in enumerate(result["equity_curve"]):
            for key in ("balance", "equity", "opening_balance", "opening_equity", "worst_equity", "best_equity"):
                self.assertAlmostEqual(point[key], sum(value["equity_curve"][index][key]
                                                       for value in result["asset_results"].values()), places=8)
        for trade in result["trades"]:
            self.assertAlmostEqual(trade["gross_pnl"] - trade["total_costs"], trade["pnl"], places=8)
            self.assertEqual(trade["risk_amount"], 250)
            self.assertIsNone(trade.get("target"))
        self.assertEqual(len(result["monthly_returns"]), result["metrics"]["monthly_observations"])

    def test_window_starts_flat_and_missing_asset_or_date_is_not_substituted(self):
        bars = pullback_bars()
        datasets = {symbol: copy.deepcopy(bars) for symbol in study.daily.SYMBOLS}
        start = bars[211]["time"][:10]
        with patch.object(study, "decisions", return_value=[None] * len(bars)):
            result = study.portfolio(datasets, start, "2021-01-01")
        self.assertEqual(result["trades"], [])
        self.assertEqual(result["metrics"]["final_equity"], 100000)
        self.assertTrue(all(point["equity"] == 100000 for point in result["equity_curve"]))
        missing = copy.deepcopy(datasets)
        missing.pop(study.daily.SYMBOLS[0])
        with self.assertRaisesRegex(ValueError, "All frozen assets"):
            study.portfolio(missing, start, "2021-01-01")
        wrong_dates = copy.deepcopy(datasets)
        wrong_dates[study.daily.SYMBOLS[0]].pop(1)
        with self.assertRaisesRegex(ValueError, "Synchronized sessions"):
            study.portfolio(wrong_dates, start, "2021-01-01")

    def test_actual_frozen_protocol_does_not_claim_exact_or_blind_replication(self):
        self.assertEqual(FROZEN["protocol_sha256"], "1dcbb69943aa83f1aca9ea7aece240d89e1e318fafc901879143d537c389baeb")
        self.assertEqual(study.daily.digest(FROZEN["protocol"]), FROZEN["protocol_sha256"])
        self.assertEqual(FROZEN["protocol"]["strategy_ids"], [study.STRATEGY_ID])
        self.assertIn("already viewed", FROZEN["protocol"]["scope"])
        source = FROZEN["protocol"]["sources"][0]
        self.assertTrue(source["publication_verified"])
        self.assertFalse(source["exact_replication"])
        self.assertFalse(source["source_performance_inherited"])


if __name__ == "__main__":
    unittest.main()
