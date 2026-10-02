"""Carry accounting/timing tests use synthetic fixtures, never profit evidence."""
from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

from propdesk import funding_lab as lab


def fixtures(count=48, spot_price=100, perp_price=100, rate=.001):
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    stamps = [(start + timedelta(hours=i)).isoformat().replace("+00:00", "Z") for i in range(count)]
    spot = [{"time": t, "open": spot_price, "high": spot_price,
             "low": spot_price, "close": spot_price, "volume": 1} for t in stamps]
    perp = [{**bar, **{key: perp_price for key in ("open", "high", "low", "close")}} for bar in spot]
    events = [{"time": t, "funding_rate": rate, "funding_interval_hours": 1,
               "mark_price": perp_price} for t in stamps]
    end = (start + timedelta(hours=count)).isoformat().replace("+00:00", "Z")
    return spot, perp, events, stamps[0], end


class FundingLabTests(unittest.TestCase):
    def test_two_wallet_capital_and_same_time_entry_does_not_collect_funding(self):
        spot, perp, events, start, end = fixtures(3)
        result = lab.simulate(spot, perp, events, lab.variants()[0], start, end, capital=1000, friction=0)
        self.assertEqual(result["records"][0]["quantity"], 5)
        self.assertEqual(result["records"][0]["time"], spot[1]["time"])
        self.assertEqual(result["settlements"], 1)
        self.assertAlmostEqual(result["funding_received"], .5)
        self.assertAlmostEqual(result["daily_equity"][-1], 1000.5)
        self.assertAlmostEqual(result["reconciliation_error"], 0)

    def test_fee_both_legs_both_sides_and_price_basis_accounting(self):
        spot, perp, events, start, end = fixtures(4, rate=0)
        result = lab.simulate(spot, perp, events, lab.variants()[0], start, end, capital=1000)
        self.assertEqual(result["fills"], 4)
        self.assertGreater(result["fees"], 1.4)
        self.assertLess(result["paired_price_pnl"], -.4)
        self.assertLess(result["return_pct"], 0)
        self.assertAlmostEqual(result["reconciliation_error"], 0, places=8)

    def test_common_spot_perp_move_cancels_price_delta(self):
        spot, perp, events, start, end = fixtures(4, rate=0)
        for rows in (spot, perp):
            rows[2].update(open=110, high=110, low=110, close=110)
            rows[3].update(open=120, high=120, low=120, close=120)
        result = lab.simulate(spot, perp, events, lab.variants()[0], start, end, capital=1000, friction=0)
        self.assertAlmostEqual(result["paired_price_pnl"], 0)
        self.assertAlmostEqual(result["daily_equity"][-1], 1000)

    def test_adverse_basis_move_is_real_loss(self):
        spot, perp, events, start, end = fixtures(4, rate=0)
        perp[-1].update(open=110, high=110, low=110, close=110)
        result = lab.simulate(spot, perp, events, lab.variants()[0], start, end, capital=1000, friction=0)
        self.assertAlmostEqual(result["paired_price_pnl"], -50)
        self.assertAlmostEqual(result["return_pct"], -5)
        self.assertAlmostEqual(result["reconciliation_error"], 0)

    def test_negative_funding_charged_positive_stress_does_not_discount_losses(self):
        spot, perp, events, start, end = fixtures(4, rate=-.001)
        result = lab.simulate(spot, perp, events, lab.variants()[0], start, end, capital=1000, friction=0,
                              positive_funding_multiplier=.5)
        self.assertAlmostEqual(result["funding_received"], -1)

    def test_missing_mark_uses_previous_closed_perpetual_not_future_close(self):
        spot, perp, events, start, end = fixtures(4)
        for event in events:
            event["mark_price"] = None
        perp[2].update(open=100, low=100, high=120, close=120)
        result = lab.simulate(spot, perp, events, lab.variants()[0], start, end, capital=1000, friction=0)
        self.assertEqual(result["proxy_mark_settlements"], 2)
        self.assertAlmostEqual(result["funding_received"], 1.1)

    def test_no_future_realized_funding_in_entry_decision(self):
        spot, perp, events, start, end = fixtures(9, rate=-.001)
        for event in events[4:]:
            event["funding_rate"] = .001
        result = lab.simulate(spot, perp, events, lab.variants()[1], start, end, capital=1000, friction=0)
        entry = next(record for record in result["records"] if record["reason"] == "paired_entry")
        self.assertEqual(entry["time"], spot[6]["time"])
        self.assertGreater(entry["known_rate_mean"], 0)

    def test_close_at_settlement_does_not_get_payment_after_exit(self):
        spot, perp, events, start, end = fixtures(9, rate=.001)
        for event in events[4:7]:
            event["funding_rate"] = -.01
        result = lab.simulate(spot, perp, events, lab.variants()[1], start, end, capital=1000, friction=0)
        closed = next(record for record in result["records"] if record["reason"] == "realized_funding_nonpositive")
        self.assertEqual(closed["time"], spot[5]["time"])
        self.assertEqual(result["settlements"], 1)
        self.assertAlmostEqual(result["funding_received"], -5)

    def test_spot_unrealized_gain_cannot_rescue_isolated_short_liquidation(self):
        spot, perp, events, start, end = fixtures(5, rate=0)
        for rows in (spot, perp):
            rows[2].update(open=210, high=210, low=210, close=210)
            rows[3].update(open=210, high=210, low=210, close=210)
            rows[4].update(open=210, high=210, low=210, close=210)
        result = lab.simulate(spot, perp, events, lab.variants()[0], start, end, capital=1000, friction=0)
        self.assertEqual(result["liquidations"], 1)
        self.assertAlmostEqual(result["liquidation_penalties"], 10.5)
        self.assertEqual(result["entries"], 1)
        self.assertAlmostEqual(result["reconciliation_error"], 0)

    def test_missing_hour_missing_funding_and_mismatched_assets_fail(self):
        spot, perp, events, start, end = fixtures(8)
        with self.assertRaises(ValueError):
            lab.simulate(spot[:2] + spot[3:], perp[:2] + perp[3:], events, lab.variants()[0], start, end)
        with self.assertRaises(ValueError):
            lab.simulate(spot, perp, events[:2] + events[3:], lab.variants()[0], start, end)
        with self.assertRaises(ValueError):
            lab.simulate(spot, perp[:-1], events, lab.variants()[0], start, end)

    def test_unknown_interval_requires_explicit_verified_pagination_permission(self):
        spot, perp, events, start, end = fixtures(4)
        for event in events:
            event["funding_interval_hours"] = None
        with self.assertRaises(ValueError):
            lab.simulate(spot, perp, events, lab.variants()[0], start, end, friction=0)
        result = lab.simulate(spot, perp, events, lab.variants()[0], start, end,
                              friction=0, allow_unknown_intervals=True)
        self.assertEqual(result["unknown_funding_interval_events"], 4)
        self.assertAlmostEqual(result["funding_received"], 50)

    def test_later_positive_settlement_cannot_rescue_earlier_liquidation(self):
        spot, perp, events, start, end = fixtures(4, rate=0)
        events[2]["time"] = "2024-01-01T02:00:00.001Z"
        events[2]["funding_rate"] = .9
        perp[2].update(open=100, low=100, high=210, close=100)
        result = lab.simulate(spot, perp, events, lab.variants()[0], start, end, capital=1000, friction=0)
        self.assertEqual(result["liquidations"], 1)
        self.assertEqual(result["funding_received"], 0)
        self.assertEqual(result["settlements"], 0)

    def test_defensive_reduction_uses_previous_close_not_future_candle(self):
        spot, perp, events, start, end = fixtures(8)
        for rows in (spot, perp):
            rows[5].update(open=100, high=150, low=100, close=150)
            for i in (6, 7):
                rows[i].update(open=150, high=150, low=150, close=150)
        result = lab.simulate(spot, perp, events, lab.variants()[1], start, end, capital=1000, friction=0)
        reduction = next(record for record in result["records"] if record["reason"] == "prior_close_collateral_buffer")
        self.assertEqual(reduction["time"], spot[6]["time"])
        self.assertAlmostEqual(reduction["remaining_quantity"], 2.5)
        self.assertAlmostEqual(result["reconciliation_error"], 0)

    def test_research_resume_finishes_full_grid_before_any_validation(self):
        path = Path(__file__).resolve().parents[1] / "scripts/research_funding.py"
        spec = importlib.util.spec_from_file_location("funding_research_test", path)
        script = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(script)
        report = {"protocol": {"variants": lab.variants()}, "protocol_sha256": "synthetic",
                  "input_lock_sha256": "synthetic"}
        calls = []
        interrupted = [True]
        def experiment(inputs, variant, phase):
            calls.append((variant["id"], phase))
            if phase == "training" and variant == lab.variants()[3] and interrupted[0]:
                interrupted[0] = False
                raise RuntimeError("Synthetic interrupted process")
            metric = {"return_pct": 1, "max_drawdown_pct": .1,
                      "max_daily_drawdown_pct": .1, "settlements": 500, "liquidations": 0}
            return {"variant": variant, "base": metric,
                    "cost_stress": metric.copy(), "funding_stress": metric.copy()}
        with patch.object(script, "verify"), patch.object(script, "load_inputs", return_value={}), \
                patch.object(script, "write_report"), patch.object(script, "experiment", side_effect=experiment), \
                patch.object(script, "confirm_checks", return_value={"synthetic_failure": False}):
            with self.assertRaises(RuntimeError):
                script.run(report)
            self.assertEqual(len(report["training"]), 3)
            self.assertNotIn("training_selection", report)
            script.run(report)
        self.assertEqual([row["variant"] for row in report["training"]], lab.variants())
        self.assertEqual(sum(phase == "validation" for _, phase in calls), 1)
        self.assertEqual(sum(phase == "final" for _, phase in calls), 0)
        self.assertEqual(report["phase"], "completed_validation_failed_final_unopened")


if __name__ == "__main__":
    unittest.main()
