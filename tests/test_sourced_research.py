"""Synthetic chronology/accounting regressions, never evidence of profitability."""

import copy
from datetime import datetime, timedelta, timezone
import unittest

from propdesk.backtest import normalize_config
from scripts import research_sourced as study


def daily_bars(prices, start=None):
    start = start or datetime(2020, 1, 1, tzinfo=timezone.utc)
    return [
        {"time": (start + timedelta(days=index)).isoformat().replace("+00:00", "Z"),
         "open": float(values[0]), "high": float(values[1]),
         "low": float(values[2]), "close": float(values[3]), "volume": 1000.0}
        for index, values in enumerate(prices)
    ]


def close_bars(closes):
    return daily_bars([(price, price + 0.5, price - 0.5, price) for price in closes])


def month_bars(closes):
    """Two observations per month make the last completed close unambiguous."""
    result = []
    for index, close in enumerate(closes):
        year, month = 2020 + index // 12, index % 12 + 1
        for day in (2, 25):
            result.append({"time": f"{year}-{month:02d}-{day:02d}T00:00:00Z",
                           "open": float(close), "high": float(close + 0.5),
                           "low": float(close - 0.5), "close": float(close), "volume": 1000.0})
    return result


def config(**values):
    return normalize_config({"account_size": 20000, "risk_pct": 1.25,
                             "max_leverage": 1, "quantity_step": 1,
                             "fee_bps": 0, "slippage_bps": 0, "spread_bps": 0,
                             **values})


def decisions(bars, *, entries=(), exits=(), atr=2):
    return [{"entry": index in entries, "exit": index in exits,
             "atr": atr, "signal_time": bars[index - 1]["time"] if index else None}
            for index in range(len(bars))]


class SourcedDecisionTests(unittest.TestCase):
    def test_each_source_strategy_is_invariant_to_future_prices(self):
        bars = month_bars([100, 95, 98, 90, 102, 101, 106, 95, 110, 108,
                           115, 114, 116, 120, 90, 100, 125, 110, 130, 105])
        for strategy_id in ("qc_ema_15_30", "bt_sma_10_30", "faber_sma_10m"):
            with self.subTest(strategy_id=strategy_id):
                original = study.strategy_decisions(bars, strategy_id)
                self.assertTrue(any(original[:35]))
                self.assertEqual(original[:35], study.strategy_decisions(bars[:35], strategy_id))
                changed = copy.deepcopy(bars)
                for bar in changed[35:]:
                    for key in ("open", "high", "low", "close"):
                        bar[key] *= 4
                self.assertEqual(original[:35], study.strategy_decisions(changed, strategy_id)[:35])

    def test_original_sma_cross_requires_a_strict_previous_sign(self):
        # Short/long average difference: negative -> equal -> positive. The
        # published strict crossing cannot manufacture an entry across equality.
        equality_bridge = close_bars([100] * 30 + [99, 101, 102, 102])
        bridge = study.strategy_decisions(equality_bridge, "bt_sma_10_30")
        self.assertFalse(any(item and item["entry"] for item in bridge))
        crossed = close_bars([100] * 30 + [99, 103, 103])
        actual = study.strategy_decisions(crossed, "bt_sma_10_30")
        self.assertTrue(actual[32]["entry"])
        self.assertEqual(actual[32]["signal_time"], crossed[31]["time"])
        self.assertFalse(actual[31]["entry"])

    def test_faber_uses_ten_completed_months_including_latest_and_holds_equality(self):
        entered = month_bars([100] * 9 + [110, 120])
        items = study.strategy_decisions(entered, "faber_sma_10m")
        # November's opening sees October 110 and all ten January–October
        # closes (mean101); it never sees November's future closing120.
        self.assertTrue(items[20]["entry"])
        self.assertEqual(items[20]["signal_time"], entered[19]["time"])
        self.assertIsNone(items[19])
        equal = study.strategy_decisions(month_bars([100] * 12), "faber_sma_10m")
        self.assertFalse(equal[20]["entry"])
        self.assertFalse(equal[20]["exit"])
        self.assertFalse(equal[22]["entry"])
        self.assertFalse(equal[22]["exit"])


class SourcedExecutionTests(unittest.TestCase):
    def test_faber_stop_cannot_reenter_during_the_same_calendar_month(self):
        bars = month_bars([100] * 9 + [110, 120])
        bars[21]["low"] = 90
        for day in (27, 28):
            bars.append({"time": f"2020-11-{day}T00:00:00Z", "open": 120.0,
                         "high": 120.5, "low": 119.5, "close": 120.0, "volume": 1000.0})
        signals = study.strategy_decisions(bars, "faber_sma_10m")
        result = study.simulate_asset(bars, signals, config())
        self.assertEqual(len(result["trades"]), 1)
        self.assertEqual(result["trades"][0]["exit_reason"], "stop")
        self.assertEqual(result["trades"][0]["exit_time"], bars[21]["time"])
        self.assertIsNone(signals[22])

    def test_closed_signal_enters_next_open_at_executable_price(self):
        bars = daily_bars([(90, 96, 89, 95), (101, 102, 100, 101),
                           (101, 102, 100, 101), (103, 104, 102, 103)])
        result = study.simulate_asset(bars, decisions(bars, entries=(1,)), config())
        trade = result["trades"][0]
        self.assertEqual(trade["entry_time"], bars[1]["time"])
        self.assertEqual(trade["signal_time"], bars[0]["time"])
        self.assertEqual(trade["entry_price"], 101)

    def test_opening_gap_stop_wins_coincident_exit_and_ignores_later_bar_extremes(self):
        bars = daily_bars([(100, 101, 99, 100), (100, 101, 99, 100),
                           (93, 200, 1, 150), (150, 151, 149, 150)])
        result = study.simulate_asset(bars, decisions(bars, entries=(1,), exits=(2,)), config())
        trade = result["trades"][0]
        self.assertEqual(trade["stop"], 94)
        self.assertEqual(trade["exit_price"], 93)
        self.assertEqual(trade["exit_reason"], "gap_stop")
        self.assertEqual(result["equity_curve"][2]["worst_equity"], 20000 - 7 * trade["quantity"])

    def test_known_opening_exit_precedes_a_later_intraday_stop(self):
        bars = daily_bars([(100, 101, 99, 100), (100, 101, 99, 100),
                           (101, 105, 90, 92), (92, 93, 91, 92)])
        result = study.simulate_asset(bars, decisions(bars, entries=(1,), exits=(2,)), config())
        trade = result["trades"][0]
        self.assertEqual(trade["exit_time"], bars[2]["time"])
        self.assertEqual(trade["exit_reason"], "signal_exit")
        self.assertEqual(trade["exit_price"], 101)
        self.assertEqual(result["equity_curve"][2]["worst_equity"], 20000 + trade["quantity"])

    def test_fixed_atr_risk_is_250_and_whole_shares_round_down(self):
        bars = daily_bars([(100, 101, 99, 100), (100, 101, 99, 100),
                           (110, 120, 109, 119), (100, 101, 93, 100)])
        signals = decisions(bars, entries=(1,))
        signals[2]["atr"] = 10
        result = study.simulate_asset(bars, signals, config())
        trade = result["trades"][0]
        self.assertEqual(trade["risk_amount"], 250)
        self.assertEqual(trade["stop"], 94)
        self.assertEqual(trade["quantity"], 41)
        self.assertLessEqual(trade["quantity"] * (trade["entry_price"] - trade["stop"]), 250)
        self.assertEqual(trade["exit_price"], 94)
        self.assertEqual(trade["exit_reason"], "stop")

    def test_cash_cap_reserves_entry_fees_and_costs_fit_risk_budget(self):
        bars = daily_bars([(100, 100.00005, 99.99995, 100)] * 4)
        settings = config(fee_bps=1)
        result = study.simulate_asset(bars, decisions(bars, entries=(1,), atr=0.0001), settings)
        trade = result["trades"][0]
        self.assertEqual(trade["quantity"], 199)
        entry_cost = trade["quantity"] * trade["entry_price"] * 1.0001
        self.assertLessEqual(entry_cost, 20000)
        self.assertLessEqual(trade["quantity"] * (trade["entry_price"] - trade["stop"])
                             + trade["total_costs"], 250)
        self.assertLess(result["metrics"]["final_equity"], 20000)

    def test_weekend_financing_uses_three_calendar_days_and_held_notional_only(self):
        bars = daily_bars([(100, 100.2, 99.8, 100)] * 3,
                          datetime(2020, 1, 2, tzinfo=timezone.utc))
        # Thursday is the signal; Friday entry remains open until Monday.
        bars[2]["time"] = "2020-01-06T00:00:00Z"
        result = study.simulate_asset(bars, decisions(bars, entries=(1,), exits=(2,), atr=1),
                                      config(), financing_rate=0.365)
        trade = result["trades"][0]
        expected = trade["quantity"] * 100 * 0.365 * 3 / 365
        self.assertAlmostEqual(trade["financing_total"], expected, places=6)
        self.assertAlmostEqual(result["metrics"]["final_equity"], 20000 - expected, places=6)
        self.assertLess(expected, 20000 * 0.365 * 3 / 365)

    def test_out_of_sample_window_starts_flat_without_inherited_trade_or_cost(self):
        bars = daily_bars([(100, 101, 99, 100), (100, 101, 99, 100),
                           (110, 111, 109, 110), (110, 111, 109, 110),
                           (115, 116, 114, 115), (115, 116, 114, 115)])
        signals = decisions(bars, entries=(1,))
        training = study.simulate_asset(bars, signals, config(), start=0, end=3, financing_rate=.08)
        held_out = study.simulate_asset(bars, signals, config(), start=3, end=6, financing_rate=.08)
        self.assertTrue(training["trades"])
        self.assertEqual(held_out["trades"], [])
        self.assertEqual(held_out["metrics"]["final_equity"], 20000)
        self.assertTrue(all(item["balance"] == 20000 and item["equity"] == 20000
                            for item in held_out["equity_curve"]))


class SourcedPortfolioTests(unittest.TestCase):
    def test_portfolio_months_are_synchronized_observations_and_future_append_is_causal(self):
        # Opposite equal-share price moves cancel at portfolio level. Pooling
        # independent asset returns would create spurious monthly variation.
        datasets = {symbol: month_bars([100] * 36) for symbol in study.SYMBOLS}
        datasets[study.SYMBOLS[0]] = month_bars([100 + index for index in range(36)])
        datasets[study.SYMBOLS[1]] = month_bars([100 - index for index in range(36)])
        result = study.portfolio_result(datasets, "qc_ema_15_30", "2020-01-01", "2023-01-01",
                                        baseline_scale=.5)
        self.assertEqual(result["metrics"]["monthly_observations"], 36)
        self.assertEqual(len(result["monthly_returns"]), 36)
        self.assertEqual(len(result["trades"]), 5)
        for item in result["monthly_returns"][1:-1]:
            self.assertAlmostEqual(item["return"], 0, places=12)
        for index, point in enumerate(result["equity_curve"]):
            self.assertAlmostEqual(point["worst_equity"],
                                   sum(asset["equity_curve"][index]["worst_equity"]
                                       for asset in result["asset_results"].values()), places=8)
        prefix = {symbol: bars[:48] for symbol, bars in datasets.items()}
        earlier = study.portfolio_result(prefix, "qc_ema_15_30", "2020-01-01", "2022-01-01",
                                         baseline_scale=.5)
        # The shorter segment liquidates on its final close, so compare all
        # earlier unchanged account marks and completed earlier months.
        self.assertEqual(result["equity_curve"][:47], earlier["equity_curve"][:-1])
        self.assertEqual(result["monthly_returns"][:23], earlier["monthly_returns"][:-1])
        mismatched = copy.deepcopy(datasets)
        mismatched[study.SYMBOLS[0]].pop(5)
        with self.assertRaisesRegex(ValueError, "same source sessions"):
            study.portfolio_result(mismatched, "qc_ema_15_30", "2020-01-01", "2023-01-01")


if __name__ == "__main__":
    unittest.main()
