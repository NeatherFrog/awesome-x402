from copy import deepcopy
from datetime import datetime, timedelta, timezone
import math
import unittest

from propdesk import cross_sectional as engine


def fixture(days=75, funding_rate=.0001):
    start = datetime(2023, 12, 1, tzinfo=timezone.utc)
    trades, marks, funding = {}, {}, {}
    for n, s in enumerate(engine.SYMBOLS):
        prices, computed, events = [], [], []
        for h in range(days*24):
            at = start+timedelta(hours=h)
            # Positive/negative cross-sectional momentum and changing ranks,
            # with liquid real trade placeholders and narrow mark ranges.
            price = 100*math.exp((n-5)*.00003*h+.015*math.sin(h/72+n))
            closed = price*1.00005
            stamp = at.isoformat().replace("+00:00", "Z")
            known = (at+timedelta(hours=1)).isoformat().replace("+00:00", "Z")
            prices.append({"time": stamp, "known_at": known, "open": price, "high": price*1.002,
                           "low": price*.998, "close": closed, "volume": 1000000,
                           "quote_volume": 100000000, "trade_count": 1000})
            computed.append({"time": stamp, "known_at": known, "open": price, "high": price*1.0018,
                             "low": price*.9982, "close": closed, "source_auxiliary_count": 3600})
            if h % 8 == 0:
                events.append({"time": stamp.replace("Z", ".007Z"), "known_at": stamp.replace("Z", ".007Z"),
                               "funding_rate": funding_rate, "funding_interval_hours": 8,
                               "mark_price": None, "rate_kind": "realized_settlement_outcome"})
        trades[s], marks[s], funding[s] = prices, computed, events
    return trades, marks, funding


def run(fixture_values, variant=None, *, costs=1):
    return engine.simulate(engine.Features(*fixture_values), variant or engine.grid()[0],
                           "2024-01-01", "2024-02-01", cost_multiplier=costs)


class CrossSectionalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.values = fixture()
        cls.features = engine.Features(*cls.values)

    def test_exact_grid_and_every_variant_is_nonvacuous(self):
        variants = engine.grid()
        self.assertEqual(len(variants), 72)
        self.assertEqual(len({v["id"] for v in variants}), 72)
        for v in variants:
          for costs in (1, 2):
            with self.subTest(id=v["id"], costs=costs):
                result = engine.simulate(self.features, v, "2024-01-01", "2024-02-01", cost_multiplier=costs)
                self.assertGreater(len(result["opening_order_plans"]), 0)
                self.assertGreater(result["metrics"]["completed_asset_episodes"], 0)
                self.assertEqual(len(result["daily_curve"]), 31)
                self.assertEqual(result["metrics"]["remaining_positions"], 0)
                self.assertLess(result["metrics"]["account_pnl_reconciliation_error"], 1e-7)
                self.assertGreaterEqual(result["metrics"]["minimum_available_cash"], -1e-7)
                self.assertAlmostEqual(result["metrics"]["final_equity"]-100000,
                                       math.fsum(t["pnl"] for t in result["trades"]), places=7)

    def test_future_fields_do_not_change_past_membership_and_orders(self):
        altered = deepcopy(self.values)
        cutoff = (31+15)*24
        for s in engine.SYMBOLS:
            for r in altered[0][s][cutoff:]:
                for k in ("open", "high", "low", "close"):
                    r[k] *= 1.7
                r["quote_volume"] *= .01
            for r in altered[1][s][cutoff:]:
                for k in ("open", "high", "low", "close"):
                    r[k] *= 1.7
            for r in altered[2][s]:
                if r["time"] >= "2024-01-16":
                    r["funding_rate"] *= -7
        other = engine.Features(*altered)
        for v in engine.grid()[::6]:
            a = engine.simulate(self.features, v, "2024-01-01", "2024-02-01")
            b = engine.simulate(other, v, "2024-01-01", "2024-02-01")
            self.assertEqual([p for p in a["opening_order_plans"] if p["time"] < "2024-01-16"],
                             [p for p in b["opening_order_plans"] if p["time"] < "2024-01-16"])
            self.assertEqual(a["daily_curve"][:15], b["daily_curve"][:15])

    def test_joint_reservation_cannot_depend_on_other_assets_future_volume(self):
        altered = deepcopy(self.values)
        opening = (31*24)+1
        s = engine.SYMBOLS[-1]
        altered[0][s][opening]["volume"] = 0
        altered[0][s][opening]["quote_volume"] = 0
        a, b = run(self.values), run(altered)
        self.assertEqual([p for p in a["opening_order_plans"] if p["time"] == "2024-01-01T01:00:00Z"],
                         [p for p in b["opening_order_plans"] if p["time"] == "2024-01-01T01:00:00Z"])

    def test_realized_future_rate_cannot_change_prior_orders(self):
        values = deepcopy(self.values)
        s = engine.SYMBOLS[0]
        for event in values[2][s]:
            if "2024-01-01T08" in event["time"]:
                event["funding_rate"] = -.2
        v = next(v for v in engine.grid() if v["family"] == "balanced_financing")
        a, b = run(self.values, v), run(values, v)
        self.assertEqual([p for p in a["opening_order_plans"] if p["time"] < "2024-01-01T08"],
                         [p for p in b["opening_order_plans"] if p["time"] < "2024-01-01T08"])

    def test_exact_boundary_debit_cannot_resize_joint_new_intents(self):
        values = deepcopy(self.values)
        stamp = "2024-01-02T01:00:00Z"
        values[2]["DOTUSDT"].append({"time": stamp, "known_at": stamp, "funding_rate": .02,
                                   "rate_kind": "realized_settlement_outcome"})
        values[2]["DOTUSDT"].sort(key=lambda e:e["time"])
        v = engine.grid()[0]
        first, second = engine.Features(*self.values), engine.Features(*values)
        for f in (first, second):
            f.observations(v)[32] = {"ETHUSDT": {"direction": 1, "weight": .3, "atr": 1,
                                    "known_at": "2024-01-02T00:00:00Z", "score": 1}}
        a = engine.simulate(first, v, "2024-01-01", "2024-02-01")
        b = engine.simulate(second, v, "2024-01-01", "2024-02-01")
        aa = [p for p in a["opening_order_plans"] if p["time"]==stamp]
        bb = [p for p in b["opening_order_plans"] if p["time"]==stamp]
        self.assertTrue(aa)
        self.assertEqual(aa, bb)

    def test_old_current_first_print_cannot_resize_another_asset_and_breach_is_flagged(self):
        changed = deepcopy(self.values)
        i = 32*24+1
        changed[0]['DOTUSDT'][i]['open'] *= 10
        changed[0]['DOTUSDT'][i]['high'] = changed[0]['DOTUSDT'][i]['open']
        v = engine.grid()[0]
        first, second = engine.Features(*self.values), engine.Features(*changed)
        for f in (first, second):
            f.observations(v)[32] = {'ETHUSDT': {'direction': 1, 'weight': .3, 'atr': 1,
                                    'known_at': '2024-01-02T00:00:00Z', 'score': 1}}
        a = engine.simulate(first, v, '2024-01-01', '2024-02-01')
        b = engine.simulate(second, v, '2024-01-01', '2024-02-01')
        aa = [p for p in a['opening_order_plans'] if p['time']=='2024-01-02T01:00:00Z']
        bb = [p for p in b['opening_order_plans'] if p['time']=='2024-01-02T01:00:00Z']
        self.assertTrue(aa)
        self.assertEqual(aa, bb)
        self.assertGreater(b['metrics']['retrospective_entry_union_gross_breaches'], 0)

    def test_old_exit_future_volume_cannot_resize_other_asset(self):
        changed = deepcopy(self.values)
        i = 32*24+1
        changed[0]['DOTUSDT'][i]['volume'] = changed[0]['DOTUSDT'][i]['quote_volume'] = 0
        v = engine.grid()[0]
        first, second = engine.Features(*self.values), engine.Features(*changed)
        for f in (first, second):
            f.observations(v)[32] = {'ETHUSDT': {'direction': 1, 'weight': .3, 'atr': 1,
                                    'known_at': '2024-01-02T00:00:00Z', 'score': 1}}
        a = engine.simulate(first, v, '2024-01-01', '2024-02-01')
        b = engine.simulate(second, v, '2024-01-01', '2024-02-01')
        aa = [p for p in a['opening_order_plans'] if p['time']=='2024-01-02T01:00:00Z']
        bb = [p for p in b['opening_order_plans'] if p['time']=='2024-01-02T01:00:00Z']
        self.assertTrue(aa)
        self.assertEqual(aa, bb)

    def test_double_cost_case_pays_both_legs_and_reconciles(self):
        a, b = run(self.values), run(self.values, costs=2)
        for r in (a, b):
            self.assertAlmostEqual(r["metrics"]["fees_paid"],
                math.fsum(t["entry_fee"]+t["exit_fee"]+t["liquidation_fee"] for t in r["trades"]), places=7)
            self.assertGreater(r["metrics"]["adverse_fill_cost"], 0)
            self.assertLess(r["metrics"]["account_pnl_reconciliation_error"], 1e-7)
        self.assertLess(b["metrics"]["final_equity"], a["metrics"]["final_equity"])

    def test_cash_and_one_x_joint_planned_cap(self):
        r = run(self.values)
        groups = {}
        for p in r["opening_order_plans"]:
            groups.setdefault(p["time"], []).append(p)
        for plans in groups.values():
            p = plans[0]
            self.assertLessEqual(p["joint_reserved_cash"], p["opening_free_cash"]+1e-7)
            self.assertTrue(all(x["signal_known_at"] < x["time"] for x in plans))

    def test_marks_do_not_become_trade_prices(self):
        values = deepcopy(self.values)
        for s in engine.SYMBOLS:
            for r in values[1][s]:
                for k in ("open", "high", "low", "close"):
                    r[k] *= 1.0001
        r = run(values)
        for t in r["trades"]:
            i = self.features.times.index(t["entry_time"])
            self.assertEqual(t["entry_raw_price"], self.features.raw[t["symbol"]]["open"][i])

    def test_liquidity_volume_is_previous_complete_days(self):
        values = deepcopy(self.values)
        for s in engine.SYMBOLS:
            for r in values[0][s][31*24:32*24]:
                r["quote_volume"] = 0
        f = engine.Features(*values)
        self.assertEqual(self.features.observations(engine.grid()[0])[31], f.observations(engine.grid()[0])[31])

    def test_missing_clocks_and_invalid_marks_reject(self):
        for mode in ("missing", "availability", "price"):
            values = deepcopy(self.values)
            if mode == "missing":
                values[1][engine.SYMBOLS[0]].pop(2)
            elif mode == "availability":
                values[1][engine.SYMBOLS[0]][2]["known_at"] = values[1][engine.SYMBOLS[0]][2]["time"]
            else:
                values[1][engine.SYMBOLS[0]][2]["high"] = float("nan")
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                engine.Features(*values)

    def test_slices_are_grouped_into_asset_episodes_not_independent_bets(self):
        r = run(self.values)
        terminal = {t["episode_id"] for t in r["trades"] if t["completed_episode"]}
        self.assertEqual(r["metrics"]["trade_count"], len(terminal))
        self.assertGreaterEqual(r["metrics"]["close_slice_count"], len(terminal))
        self.assertIn("correlated", r["inference_unit"])

    def test_asymmetric_prior_volatility_risk_caps_keep_initial_planned_sides_balanced(self):
        values = deepcopy(self.values)
        for s in ("DOTUSDT", "BCHUSDT", "BNBUSDT"):
            for r in values[0][s][:31*24]:
                r["high"] *= 1.12
                r["low"] *= .88
        v = next(v for v in engine.grid() if v["family"] == "balanced_momentum")
        r = run(values, v)
        plans = [p for p in r["opening_order_plans"] if p["time"]=="2024-01-01T01:00:00Z"]
        self.assertTrue(plans)
        p = plans[0]
        tolerance = .001*math.fsum(self.features.raw[s]["open"][31*24+1] for s in engine.SYMBOLS)
        self.assertLess(abs(p["planned_long_notional"]-p["planned_short_notional"]), tolerance)

    def test_current_mark_open_breach_cannot_recover_old_wallet_from_healthy_trade_open(self):
        values = deepcopy(self.values)
        i = 32*24+1
        r = values[1]["DOTUSDT"][i]
        r["open"], r["low"] = .00001, .000001
        f = engine.Features(*values)
        v = engine.grid()[0]
        f.observations(v)[32] = {}
        result = engine.simulate(f, v, "2024-01-01", "2024-02-01")
        episodes = [t for t in result["trades"] if t["symbol"]=="DOTUSDT" and t["reason"]=="current_mark_open_liquidation_bound"]
        self.assertTrue(episodes)
        self.assertTrue(all(t["recovered_margin"]==0 for t in episodes))
        self.assertGreater(result["metrics"]["current_mark_open_gap_breaches"], 0)
        self.assertGreater(result["metrics"]["liquidation_count"], 0)

    def test_late_exit_hour_debit_is_preserved_once_and_credit_omitted(self):
        values = deepcopy(self.values)
        stamp = "2024-01-02T01:00:00.007Z"
        for s in engine.SYMBOLS:
            values[2][s].append({"time": stamp, "known_at": stamp, "funding_rate": .001,
                                "rate_kind": "realized_settlement_outcome"})
            values[2][s].sort(key=lambda e:e["time"])
        f = engine.Features(*values)
        v = next(v for v in engine.grid() if v["family"]=="balanced_momentum")
        f.observations(v)[32] = {}
        result = engine.simulate(f, v, "2024-01-01", "2024-02-01")
        entries = [e for e in result["funding_ledger"] if e["time"]==stamp]
        self.assertTrue(entries)
        self.assertEqual(len(entries), len({e["episode_id"] for e in entries}))
        self.assertTrue(any(e["pnl"]<0 for e in entries))
        self.assertTrue(all(e["pnl"]==0 for e in entries if e["unadjusted_amount"]>0))
        self.assertTrue(all(e["intrabar_entitlement_ambiguous"] for e in entries))

    def test_missing_trade_exposure_and_reopening_are_explicit(self):
        values = deepcopy(self.values)
        values[0]["DOTUSDT"][32*24]["volume"] = 0
        values[0]["DOTUSDT"][32*24]["quote_volume"] = 0
        f = engine.Features(*values)
        v = engine.grid()[0]
        f.observations(v)[32] = {}
        result = engine.simulate(f, v, "2024-01-01", "2024-02-01")
        self.assertGreater(result["metrics"]["unresolved_zero_trade_exposure_bars"], 0)
        self.assertGreater(result["metrics"]["unknown_reopening_exit_count"], 0)

    def test_negative_late_debit_crossing_maintenance_does_not_recover_residual(self):
        values = deepcopy(self.values)
        stamp = "2024-01-02T01:00:00.007Z"
        values[2]["DOTUSDT"].append({"time": stamp, "known_at": stamp, "funding_rate": .995,
                                   "rate_kind": "realized_settlement_outcome"})
        values[2]["DOTUSDT"].sort(key=lambda e:e["time"])
        f = engine.Features(*values)
        v = engine.grid()[0]
        f.observations(v)[32] = {}
        result = engine.simulate(f, v, "2024-01-01", "2024-02-01")
        exits = [t for t in result["trades"] if t["symbol"]=="DOTUSDT" and t["reason"]=="old_exit_after_debit_liquidation_bound"]
        self.assertTrue(exits)
        self.assertTrue(all(t["recovered_margin"]==0 for t in exits))

    def test_sparse_mark_old_exit_and_prior_opening_are_counted(self):
        values = deepcopy(self.values)
        values[1]["DOTUSDT"][31*24]["source_auxiliary_count"] = 1
        values[1]["DOTUSDT"][32*24+1]["source_auxiliary_count"] = 1
        f = engine.Features(*values)
        v = engine.grid()[0]
        f.observations(v)[32] = {}
        result = engine.simulate(f, v, "2024-01-01", "2024-02-01")
        self.assertGreater(result["metrics"]["sparse_known_mark_opening_intents"], 0)
        self.assertGreater(result["metrics"]["sparse_mark_exposure_bars"], 0)


if __name__ == "__main__":
    unittest.main()
