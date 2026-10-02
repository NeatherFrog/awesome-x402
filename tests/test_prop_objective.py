"""Public-rule scenario tests; invented cash paths never prove trading returns."""
from datetime import datetime, timedelta, timezone
import unittest

from propdesk import prop_objective as model
from propdesk.timezones import timezone_for


META = {"source_kind": "synthetic_scenario", "complete_equity_envelopes": True,
        "external_cashflows_in_source": False}


def iso(stamp):
    return stamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def point(start, end, prior, balance, *, worst=None, best=None, trades=None, **extra):
    return {"interval_start": iso(start), "time": iso(end), "balance": balance,
            "net_equity": balance, "worst_equity": min(prior, balance) if worst is None else worst,
            "best_equity": max(prior, balance) if best is None else best,
            "open_positions": 0, "open_orders": 0,
            "trade_open_times": [iso(t) for t in trades or []], **extra}


def ftmo_path(profits, *, first_date=(2026, 1, 1), requests=None):
    zone = timezone_for("Europe/Prague")
    now = datetime(*first_date, tzinfo=zone)
    balance = 100000.0
    out = [point(now, now, balance, balance)]
    for i, profit in enumerate(profits):
        end = now + timedelta(days=1)
        extra = {"payout_request_gross": requests[i]} if requests and i in requests else {}
        out.append(point(now, end, balance, balance+profit, trades=[now+timedelta(hours=12)], **extra))
        now, balance = end, balance+profit
    return out


def topstep_path(profits, stage="topstep_xfa_standard", *, requests=None, initial_date=(2026, 1, 4)):
    zone = timezone_for("America/Chicago")
    start = datetime(*initial_date, 17, tzinfo=zone)
    initial = model.reference_rules(stage)["initial_balance"]
    balance = initial
    out = [point(start, start, balance, balance)]
    day = start.date() + timedelta(days=1)
    for i, profit in enumerate(profits):
        while day.weekday() >= 5:
            day += timedelta(days=1)
        begin = datetime(day.year, day.month, day.day, 17, tzinfo=zone) - timedelta(days=1)
        if begin > start:
            out.append(point(start, begin, balance, balance))
            start = begin
        finish = datetime(day.year, day.month, day.day, 15, 10, tzinfo=zone)
        out.append(point(start, finish, balance, balance+profit,
                         trades=[finish.replace(hour=10, minute=0)], session_end=True))
        balance += profit
        locked = finish.replace(hour=16, minute=0)
        extra = {"payout_request_gross": requests[i]} if requests and i in requests else {}
        out.append(point(finish, locked, balance, balance, day_close=True, **extra))
        start = finish.replace(hour=17, minute=0)
        out.append(point(locked, start, balance, balance))
        day += timedelta(days=1)
    return out


class PropObjectiveTests(unittest.TestCase):
    def test_eight_percent_profit_is_not_eight_percent_received(self):
        out = model.objective_math()
        self.assertAlmostEqual(out["compound_annual_return_pct"], 151.81701168189793)
        self.assertEqual(out["fixed_monthly_withdrawal_annual_pct"], 96)
        self.assertEqual(out["ftmo80_received_from_profit_goal"], 6400)
        self.assertEqual(out["gross_profit_for_equal_cash_ftmo80"], 10000)
        self.assertAlmostEqual(out["gross_profit_for_equal_cash_split90"], 8888.888888888889)
        self.assertEqual(out["topstep_standard_requests_min_before_fees"], 3)

    def test_ftmo_two_phases_reset_not_single_generic_evaluation(self):
        first = ftmo_path([2500]*4)
        second = ftmo_path([1250]*4, first_date=(2026, 1, 5))
        result = model.replay_lifecycle([{ "stage": "ftmo_challenge", "points": first, "metadata": META},
                                         {"stage": "ftmo_verification", "points": second, "metadata": META}])
        self.assertTrue(all(r["phase"] == "evaluation_passed_model" for r in result["stages"]))
        self.assertEqual(result["cash_received_model"], 0)
        self.assertEqual(result["stages"][1]["snapshots"][0]["balance"], 100000)

    def test_ftmo_requires_four_opening_days_despite_one_large_win(self):
        out = model.replay_stage(ftmo_path([10000]), "ftmo_challenge", META)
        self.assertEqual(out["phase"], "incomplete_stage")
        self.assertEqual(out["payouts"], [])

    def test_ftmo_float_loss_at_new_midnight_can_breach_even_profitable_balance(self):
        path = ftmo_path([1000])
        path[-1].update(net_equity=95500, worst_equity=95500, open_positions=1)
        out = model.replay_stage(path, "ftmo_funded", META)
        self.assertIn("new_midnight_daily_loss", [e["rule"] for e in out["breaches"]])

    def test_ftmo_profit_eight_thousand_pays6400_after_eligible_wait(self):
        path = ftmo_path([400]*20, requests={19:8000})
        out = model.replay_stage(path, "ftmo_funded", META)
        self.assertEqual(out["cash_received_model"], 6400)
        self.assertEqual(out["end_balance_model"], 100000)
        self.assertFalse(out["user_verified_contract"])
        self.assertFalse(out["strategy_profitability_proven"])

    def test_fourteen_calendar_dates_without_full_elapsed_wait_are_uncertain_not_paid(self):
        # Jan1noon firsttrade -> Jan15midnight is only13.5elapsed days.
        path = ftmo_path([100]*14, requests={13:1000})
        out = model.replay_stage(path,"ftmo_funded",META)
        self.assertEqual(out["cash_received_model"],0)
        self.assertIn("reward_too_early",out["payout_rejections"][0]["reasons"])

    def test_fresh_stage_rejects_unexplained_float_or_initial_trade(self):
        path = ftmo_path([100]); path[0].update(net_equity=100001,best_equity=100001)
        with self.assertRaises(ValueError):
            model.replay_stage(path,"ftmo_funded",META)
        path = ftmo_path([100]); path[0]["trade_open_times"]=[path[0]["time"]]
        with self.assertRaises(ValueError):
            model.replay_stage(path,"ftmo_funded",META)

    def test_missing_reset_or_worst_marks_rejected(self):
        path = ftmo_path([100,100])
        with self.assertRaises(ValueError):
            model.replay_stage([path[0], {**path[-1], "interval_start": path[0]["time"]}], "ftmo_funded", META)
        bad = ftmo_path([100]); del bad[-1]["worst_equity"]
        with self.assertRaises((KeyError, ValueError)):
            model.replay_stage(bad, "ftmo_funded", META)
        with self.assertRaises(ValueError):
            model.replay_stage(ftmo_path([100]), "ftmo_funded", {**META,"complete_equity_envelopes":False})

    def test_prague_dst_midnight_uses23_and25_hour_days(self):
        for first, hours in (((2026,3,28),[24,23]), ((2026,10,24),[24,25])):
            path = ftmo_path([100,100], first_date=first)
            actual = [(datetime.fromisoformat(r['time'].replace('Z','+00:00'))-
                       datetime.fromisoformat(r['interval_start'].replace('Z','+00:00'))).total_seconds()/3600 for r in path[1:]]
            self.assertEqual(actual,hours)
            self.assertFalse(model.replay_stage(path,"ftmo_funded",META)["breaches"])

    def test_topstep_combine_eod_trails_and_caps_without_intraday_peak_ratchet(self):
        path = topstep_path([2000,1000], stage="topstep_combine")
        path[1]["best_equity"] = 109000
        out = model.replay_stage(path,"topstep_combine",META)
        floors = [r["total_floor"] for r in out["snapshots"]]
        self.assertEqual(floors[0],97000)
        self.assertEqual(floors[1],99000)
        self.assertEqual(floors[-1],100000)
        self.assertFalse(out["breaches"])

    def test_topstep_combine_fresh_xfa_zero_no_nominal_cash_transfer(self):
        out = model.replay_stage(topstep_path([3000,3000],stage="topstep_combine"),"topstep_combine",META)
        self.assertEqual(out["phase"],"evaluation_passed_model")
        xfa = topstep_path([150]*5)
        xfa[0].update(balance=106000,net_equity=106000,worst_equity=106000,best_equity=106000)
        with self.assertRaises(ValueError):
            model.replay_stage(xfa,"topstep_xfa_standard",META)

    def test_topstep_cap_half_balance_and_ach_fee_after_split(self):
        path = topstep_path([1600]*5, requests={4:3000})
        out = model.replay_stage(path,"topstep_xfa_standard",META,payout_method_fee=30)
        self.assertEqual(out["cash_received_model"],2670)
        self.assertEqual(out["end_balance_model"],5000)
        self.assertEqual(out["payouts"][0]["remaining_balance"],5000)
        rejected = model.replay_stage(topstep_path([1600]*5,requests={4:4000}),"topstep_xfa_standard",META)
        self.assertIn("exceeds_half_balance_or_stage_cap",rejected["payout_rejections"][0]["reasons"])

    def test_first_xfa_payout_locks_floor_zero_and_cannot_spend_remaining_buffer(self):
        out = model.replay_stage(topstep_path([150]*5,requests={4:300}),"topstep_xfa_standard",META)
        self.assertEqual(out["payouts"][0]["cash_received_model"],270)
        self.assertEqual(out["snapshots"][-1]["total_floor"],0)
        path = topstep_path([150]*5+[-451],requests={4:300})
        breached = model.replay_stage(path,"topstep_xfa_standard",META)
        self.assertIn("total_loss_touch",[e["rule"] for e in breached["breaches"]])

    def test_consistency_new_window_excludes_retained_balance(self):
        path = topstep_path([3000,3000,3000,600,-500,100],stage="topstep_xfa_consistency",requests={2:4000,5:1000})
        out = model.replay_stage(path,"topstep_xfa_consistency",META)
        self.assertEqual(len(out["payouts"]),1)
        self.assertEqual(out["cash_received_model"],3600)
        self.assertIn("new_window_three_days_and_40pct_consistency_required",out["payout_rejections"][0]["reasons"])
        self.assertEqual(out["snapshots"][-1]["cycle_profit"],200)
        self.assertEqual(out["snapshots"][-1]["best_day"],600)

    def test_optional_dll_is_session_pause_not_automatic_mll_failure(self):
        path = topstep_path([-2100],stage="topstep_combine")
        out = model.replay_stage(path,"topstep_combine",META,optional_dll=2000)
        self.assertFalse(out["breaches"])
        self.assertEqual(out["phase"],"incomplete_stage")
        self.assertEqual(out["snapshots"][-1]["total_floor"],97000)

    def test_chicago_spring_dst_changes_weekend_utc_duration(self):
        path = topstep_path([150]*6,initial_date=(2026,3,1))
        intervals = [(datetime.fromisoformat(p['time'].replace('Z','+00:00'))-
                      datetime.fromisoformat(p['interval_start'].replace('Z','+00:00'))).total_seconds()/3600 for p in path]
        self.assertIn(47,intervals)
        out = model.replay_stage(path,"topstep_xfa_standard",META)
        self.assertFalse(out["breaches"])


if __name__ == "__main__":
    unittest.main()
