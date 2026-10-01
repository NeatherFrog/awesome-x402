import math
import unittest
from datetime import datetime, timedelta, timezone

from propdesk.risk import default_profiles, normalize_profile, check_trade
from propdesk.payout import simulate


class RiskChecks(unittest.TestCase):
    def setUp(self):
        self.profile = default_profiles()[0]
        self.account = {"balance": 100000, "equity": 100000, "day_start_balance": 100000,
                        "day_start_equity": 100000, "high_water_equity": 100000,
                        "confirmed_rules": True, "open_risk": 0, "trading_days": 0}
        self.trade = {"side": "long", "entry": 100, "stop": 99, "target": 102,
                      "quantity": 100, "contract_multiplier": 1, "risk_pct": 0.25,
                      "spread_bps": 2, "fee_bps": 3, "slippage_bps": 5}

    def test_examples_never_claim_real_firm_verification(self):
        profiles = default_profiles()
        self.assertEqual(len(profiles), 3)
        self.assertTrue(all(p["status"] == "illustrative" and p["verified_at"] is None for p in profiles))
        self.assertFalse(profiles[2]["challenge_required"])

    def test_adverse_roundtrip_costs_reduce_allowed_quantity(self):
        result = check_trade(self.profile, self.account, self.trade)
        self.assertTrue(result["allowed"], result)
        self.assertEqual(result["decision"], "ALLOW_PAPER")
        self.assertAlmostEqual(result["risk_amount"], 118)
        self.assertAlmostEqual(result["max_safe_quantity"], 211.86)
        self.assertFalse(result["rule_checks"]["live_execution_authorized"])
        expensive = check_trade(self.profile, self.account, {**self.trade, "quantity": 250})
        self.assertFalse(expensive["allowed"])
        self.assertAlmostEqual(expensive["risk_amount"], 295)

    def test_per_side_cash_fee_is_added_twice_per_quantity_unit(self):
        result = check_trade(self.profile, self.account, {**self.trade, "fee_per_unit": .25})
        self.assertTrue(result["allowed"])
        self.assertAlmostEqual(result["risk_amount"], 168)
        self.assertEqual(result["rule_checks"]["roundtrip_cost_bps"], 18)
        self.assertEqual(result["rule_checks"]["roundtrip_fixed_fee_per_unit"], .5)
        self.assertEqual(result["rule_checks"]["cost_definitions"]["fee_bps"], "per side")
        self.assertFalse(check_trade(self.profile, self.account, {**self.trade, "fee_per_unit": -1})["allowed"])

    def test_missing_confirmation_and_unknown_requested_restriction_block(self):
        result = check_trade(self.profile, {**self.account, "confirmed_rules": False}, self.trade)
        self.assertFalse(result["allowed"])
        unknown = normalize_profile({**self.profile, "ea_allowed": None})
        result = check_trade(unknown, self.account, {**self.trade, "is_automated": True})
        self.assertFalse(result["allowed"])
        self.assertTrue(any("ea_allowed" in reason for reason in result["reasons"]))
        self.assertTrue(check_trade(unknown, self.account, self.trade)["allowed"])

    def test_nonfinite_negative_and_zero_inputs_block(self):
        for key, value in (("entry", math.nan), ("stop", math.inf), ("quantity", 0),
                           ("quantity", -1), ("fee_bps", -1), ("risk_pct", 0),
                           ("quantity", True), ("news_window", "false")):
            with self.subTest(key=key, value=value):
                result = check_trade(self.profile, self.account, {**self.trade, key: value})
                self.assertFalse(result["allowed"], result)
                self.assertTrue(result["reasons"])
        for key in ("balance", "equity", "open_risk", "day_start_balance", "high_water_equity"):
            self.assertFalse(check_trade(self.profile, {**self.account, key: -1}, self.trade)["allowed"])

    def test_huge_finite_inputs_are_blocked_before_arithmetic(self):
        for key in ("entry", "stop", "target", "quantity", "contract_multiplier"):
            result = check_trade(self.profile, self.account, {**self.trade, key: 1e308})
            self.assertFalse(result["allowed"])
            self.assertIsNone(result["risk_amount"])
        result = check_trade(self.profile, {**self.account, "equity": 1e308}, self.trade)
        self.assertFalse(result["allowed"])
        with self.assertRaises(ValueError):
            normalize_profile({**self.profile, "challenge_fee": 1e308})

    def test_stop_and_target_directions_for_both_sides(self):
        self.assertFalse(check_trade(self.profile, self.account, {**self.trade, "stop": 101})["allowed"])
        self.assertFalse(check_trade(self.profile, self.account, {**self.trade, "target": 99.5})["allowed"])
        short = {**self.trade, "side": "short", "stop": 101, "target": 98}
        self.assertTrue(check_trade(self.profile, self.account, short)["allowed"])
        self.assertFalse(check_trade(self.profile, self.account, {**short, "stop": 99})["allowed"])

    def test_daily_loss_equity_reference_and_boundary(self):
        account = {**self.account, "day_start_equity": 102000, "equity": 97000, "balance": 98000}
        result = check_trade(self.profile, account, self.trade)
        self.assertEqual(result["rule_checks"]["daily_floor"], 97000)
        self.assertEqual(result["daily_remaining"], 0)
        self.assertFalse(result["allowed"])
        account = {**self.account, "equity": 95200, "balance": 95200, "open_risk": 100}
        result = check_trade(self.profile, account, self.trade)
        self.assertEqual(result["effective_budget"], 99)
        self.assertFalse(result["allowed"])

    def test_static_and_trailing_floors_diverge(self):
        account = {**self.account, "balance": 103000, "equity": 103000, "high_water_equity": 112000,
                   "day_start_balance": 103000, "day_start_equity": 103000}
        static = check_trade(self.profile, account, self.trade)
        trailing = check_trade({**self.profile, "drawdown_type": "trailing_eod"}, account, self.trade)
        self.assertEqual(static["total_remaining"], 13000)
        self.assertEqual(trailing["total_remaining"], 1000)
        intraday = check_trade({**self.profile, "drawdown_type": "trailing_intraday"},
                               {**account, "high_water_equity": 100000}, self.trade)
        self.assertEqual(intraday["rule_checks"]["total_reference"], 103000)

    def test_missing_history_does_not_invent_limits(self):
        account = dict(self.account)
        del account["day_start_equity"]
        self.assertFalse(check_trade(self.profile, account, self.trade)["allowed"])
        account = dict(self.account)
        del account["high_water_equity"]
        self.assertFalse(check_trade({**self.profile, "drawdown_type": "trailing_eod"}, account, self.trade)["allowed"])

    def test_sizes_optional_quantity_and_respects_futures_step(self):
        trade = {key: value for key, value in self.trade.items() if key != "quantity"}
        result = check_trade({**self.profile, "quantity_step": 1}, self.account, trade)
        self.assertTrue(result["allowed"])
        self.assertEqual(result["quantity"], 211)
        self.assertFalse(check_trade({**self.profile, "quantity_step": 1}, self.account,
                                     {**self.trade, "quantity": 2.5})["allowed"])

    def test_daily_reference_modes_are_explicit_and_equity_sensitive(self):
        account = {**self.account, "day_start_balance": 102000, "day_start_equity": 103000}
        expected_floors = {"max_balance_equity": 98000, "balance": 97000, "equity": 98000, "initial": 95000}
        for basis, expected in expected_floors.items():
            result = check_trade({**self.profile, "daily_reference_basis": basis}, account, self.trade)
            self.assertEqual(result["rule_checks"]["daily_floor"], expected)

    def test_capped_trailing_floor_stops_at_initial_balance(self):
        account = {**self.account, "balance": 112000, "equity": 112000, "high_water_equity": 125000}
        uncapped = check_trade({**self.profile, "drawdown_type": "trailing_eod"}, account, self.trade)
        capped = check_trade({**self.profile, "drawdown_type": "trailing_eod", "trailing_cap_at_initial": True}, account, self.trade)
        self.assertEqual(uncapped["rule_checks"]["total_floor"], 115000)
        self.assertEqual(capped["rule_checks"]["total_floor"], 100000)
        self.assertFalse(uncapped["allowed"])
        self.assertTrue(capped["allowed"])

    def test_user_verified_missing_provenance_has_warning_and_empty_consistency_is_null(self):
        profile = normalize_profile({**self.profile, "status": "user_verified", "best_day_pct": ""})
        self.assertIsNone(profile["best_day_pct"])
        result = check_trade(profile, self.account, self.trade)
        self.assertTrue(result["allowed"])
        self.assertTrue(any("source_url" in warning for warning in result["warnings"]))

    def test_invalid_profiles_raise(self):
        for key, value in (("daily_reset_timezone", "No/Zone"), ("account_size", math.inf),
                           ("daily_loss_pct", -1), ("best_day_pct", 0), ("ea_allowed", "yes"),
                           ("verified_at", "yesterday"), ("status", "verified"),
                           ("daily_reference_basis", "unknown"), ("trailing_cap_at_initial", "false"),
                           ("challenge_required", None)):
            with self.subTest(key=key):
                with self.assertRaises(ValueError):
                    normalize_profile({**self.profile, key: value})


class PayoutSimulation(unittest.TestCase):
    def setUp(self):
        self.profile = normalize_profile({**default_profiles()[0], "profit_target_pct": 1,
                                          "min_trading_days": 5, "challenge_fee": 500})
        self.config = {"returns_are_oos": True, "paths": 200, "seed": 77,
                       "risk_pct": 0.25, "trades_per_day": 3, "payout_target_pct": 1}

    def returns(self, value, n=40, **extra):
        return [{"net_r": value, **extra} for _ in range(n)]

    def test_insufficient_or_unmarked_data_requires_explicit_illustration(self):
        for trades, config in ((self.returns(1, 29), self.config), (self.returns(1), {"paths": 200})):
            result = simulate(trades, self.profile, config)
            self.assertFalse(result["feasible"])
            self.assertEqual(result["status"], "unsupported")
            self.assertIsNone(result["payout_probability"])
        result = simulate(self.returns(1, 10), self.profile, {**self.config, "allow_illustrative": True})
        self.assertTrue(result["feasible"])
        self.assertEqual(result["status"], "illustrative")

    def test_deterministic_seed_and_probabilities_have_complete_outcomes(self):
        returns = [{"net_r": r} for r in ([1.8, -1, -1, 2, 0.5, -1, 0.2, 1.5] * 10)]
        first = simulate(returns, self.profile, self.config)
        second = simulate(returns, self.profile, self.config)
        self.assertEqual(first, second)
        self.assertTrue(first["feasible"])
        self.assertAlmostEqual(sum(item["probability"] for item in first["distribution"]), 1)
        self.assertEqual(sum(item["count"] for item in first["distribution"]), 200)
        self.assertLessEqual(first["payout_probability"], first["challenge_pass_probability"])

    def test_funded_balance_resets_and_fee_is_charged_on_each_attempt(self):
        result = simulate(self.returns(1), self.profile, self.config)
        self.assertEqual(result["challenge_pass_probability"], 1)
        self.assertEqual(result["payout_probability"], 1)
        # Five days * three returns * $250 = $3,750 each separate stage.
        # Split of funded profit is $3,000; challenge PnL is not withdrawn.
        self.assertEqual(result["net_expected_value"], 2500)
        self.assertEqual(result["mean_gross_payout"], 3000)
        self.assertEqual(result["stage_losses"]["mean_challenge_account_pnl"], 3750)
        self.assertEqual(result["stage_losses"]["mean_funded_account_pnl_unconditional"], 3750)
        self.assertEqual(result["first_payout_account_reset"]["high_water"], 100000)

    def test_losing_paths_fee_is_personal_loss_not_account_nominal_drawdown(self):
        profile = {**self.profile, "max_loss_pct": 1, "risk_buffer_amount": 0}
        result = simulate(self.returns(-5), profile, self.config)
        self.assertEqual(result["breach_probability"], 1)
        self.assertEqual(result["payout_probability"], 0)
        self.assertEqual(result["net_expected_value"], -500)
        self.assertEqual(result["stage_losses"]["mean_challenge_account_pnl"], -1250)

    def test_touching_boundary_is_a_terminal_breach(self):
        profile = {**self.profile, "max_loss_pct": 1, "risk_buffer_amount": 0}
        result = simulate(self.returns(-4), profile, self.config)
        self.assertEqual(result["breach_probability"], 1)
        self.assertEqual(result["stage_losses"]["mean_challenge_account_pnl"], -1000)

    def test_intraday_mae_detects_loss_hidden_by_profitable_close(self):
        profile = {**self.profile, "max_loss_pct": 1, "risk_buffer_amount": 0}
        result = simulate(self.returns(2, mae_r=4, mfe_r=2), profile, self.config)
        self.assertEqual(result["breach_probability"], 1)
        self.assertEqual(result["payout_probability"], 0)
        self.assertTrue(result["inputs"]["intratrade_excursions"])

    def test_instant_skips_challenge_and_respects_consistency(self):
        profile = {**default_profiles()[2], "challenge_fee": 350}
        result = simulate(self.returns(1), profile, self.config)
        self.assertEqual(result["payout_probability"], 1)
        self.assertEqual(result["stage_losses"]["mean_challenge_account_pnl"], 0)
        self.assertFalse(result["inputs"]["challenge_required"])
        # Instant $25k * .25% * 15 trades *80% - 350 activation fee.
        self.assertEqual(result["net_expected_value"], 400)
        strict = simulate(self.returns(1), {**profile, "best_day_pct": 1},
                          {**self.config, "funded_max_calendar_days": 7})
        self.assertEqual(strict["payout_probability"], 0)
        self.assertEqual(strict["distribution"][-2]["count"], 200)

    def test_no_trade_days_do_not_satisfy_minimum_trading_days(self):
        profile = {**self.profile, "daily_loss_pct": 0.25, "risk_buffer_amount": 1}
        result = simulate(self.returns(1), profile, self.config)
        self.assertEqual(result["challenge_pass_probability"], 0)
        self.assertEqual(result["payout_probability"], 0)
        self.assertEqual(result["breach_probability"], 0)
        self.assertEqual(result["net_expected_value"], -500)

    def test_invalid_config_and_nonfinite_returns_are_rejected(self):
        for config in ({"paths": 199}, {"paths": 1001}, {"risk_pct": -1},
                       {"risk_pct": 5}, {"trades_per_day": 0}, {"allow_illustrative": "true"},
                       {"paths": 1000, "trades_per_day": 100, "max_calendar_days": 60}):
            result = simulate(self.returns(1), self.profile, {**self.config, **config})
            self.assertFalse(result["feasible"], config)
            self.assertTrue(result["reasons"])
        self.assertFalse(simulate(self.returns(1), self.profile, [1])["feasible"])
        self.assertFalse(simulate(self.returns(math.inf), self.profile, self.config)["feasible"])
        self.assertFalse(simulate(self.returns(1), {**self.profile, "account_size": 1e308}, self.config)["feasible"])

    def test_simulator_uses_configured_daily_reference_and_trailing_cap(self):
        profile = {**self.profile, "daily_loss_pct": 1, "max_loss_pct": 20, "profit_target_pct": 30, "min_trading_days": 1}
        config = {**self.config, "seed": 42, "trades_per_day": 1, "max_calendar_days": 10}
        returns = [{"net_r": r} for r in [10, -5, 10, -5, 10] * 8]
        daily_balance = simulate(returns, {**profile, "daily_reference_basis": "balance"}, config)
        daily_initial = simulate(returns, {**profile, "daily_reference_basis": "initial"}, config)
        self.assertGreater(daily_balance["breach_probability"], daily_initial["breach_probability"])
        profile.update({"daily_loss_pct": 30, "max_loss_pct": 5, "drawdown_type": "trailing_eod"})
        returns = [{"net_r": r} for r in [30, -24, 30, -24, 30] * 8]
        uncapped = simulate(returns, profile, config)
        capped = simulate(returns, {**profile, "trailing_cap_at_initial": True}, config)
        self.assertGreater(uncapped["breach_probability"], capped["breach_probability"])

    def test_synthetic_data_is_explicitly_illustrative_even_with_oos_marks(self):
        blocked = simulate(self.returns(1), self.profile, {**self.config, "data_source": "demo"})
        self.assertFalse(blocked["feasible"])
        illustrated = simulate(self.returns(1), self.profile, {**self.config, "data_source": "synthetic demo", "allow_illustrative": True})
        self.assertTrue(illustrated["feasible"])
        self.assertEqual(illustrated["status"], "illustrative")

    def test_fractional_trade_rate_is_deterministic_and_changes_calendar_outcomes(self):
        config = {**self.config, "trades_per_day": .25}
        first = simulate(self.returns(1), self.profile, config)
        repeated = simulate(self.returns(1), self.profile, config)
        frequent = simulate(self.returns(1), self.profile, self.config)
        self.assertTrue(first["feasible"])
        self.assertEqual(first, repeated)
        self.assertEqual(first["inputs"]["trades_per_day"], .25)
        self.assertGreater(first["payout_probability"], 0)
        self.assertLess(first["payout_probability"], frequent["payout_probability"])
        self.assertLess(first["net_expected_value"], frequent["net_expected_value"])

    def test_empty_fractional_calendar_days_do_not_count_as_trading_days(self):
        config = {**self.config, "trades_per_day": .025,
                  "max_calendar_days": 7, "funded_max_calendar_days": 7}
        single_day = simulate(self.returns(10), {**self.profile, "min_trading_days": 1}, config)
        five_days = simulate(self.returns(10), {**self.profile, "min_trading_days": 5}, config)
        self.assertGreater(single_day["challenge_pass_probability"], 0)
        self.assertEqual(five_days["challenge_pass_probability"], 0)
        self.assertEqual(five_days["payout_probability"], 0)
        self.assertEqual(five_days["net_expected_value"], -500)

    def test_missing_rate_is_inferred_from_full_timestamped_business_span(self):
        start = datetime(2020, 1, 6, 9, tzinfo=timezone.utc)
        trades = []
        for index in range(40):
            entry = start + timedelta(days=index * 14)
            exit_at = entry + timedelta(days=4, hours=7)
            trades.append({"net_r": 1, "split": "oos", "entry_time": entry.isoformat(), "exit_time": exit_at.isoformat()})
        config = {key: value for key, value in self.config.items() if key != "trades_per_day"}
        result = simulate(trades, self.profile, config)
        self.assertTrue(result["feasible"])
        self.assertAlmostEqual(result["inputs"]["trades_per_day"], 40 / 395)
        self.assertEqual(result["inputs"]["trade_rate_basis"], "oos_closed_trades_per_business_day")
        self.assertEqual(result["inputs"]["observed_cadence"]["business_days"], 395)
        self.assertAlmostEqual(result["inputs"]["observed_cadence"]["mean_holding_calendar_days"], 4 + 7 / 24)
        explicit = simulate(trades, self.profile, {**config, "trades_per_day": .025, "trade_rate_basis": "archived OOS estimator"})
        self.assertEqual(explicit["inputs"]["trades_per_day"], .025)
        self.assertEqual(explicit["inputs"]["trade_rate_basis"], "archived OOS estimator")

    def test_invalid_fractional_rate_is_rejected_and_missing_timestamps_are_labeled(self):
        for rate in (0, .0009, -1, math.nan, 101, True):
            result = simulate(self.returns(1), self.profile, {**self.config, "trades_per_day": rate})
            self.assertFalse(result["feasible"])
        result = simulate(self.returns(1), self.profile, {"returns_are_oos": True, "paths": 200})
        self.assertEqual(result["inputs"]["trades_per_day"], 3)
        self.assertEqual(result["inputs"]["trade_rate_basis"], "illustrative_default_no_timestamps")
        self.assertTrue(any("3 сделки/день" in text for text in result["limitations"]))

    def test_row_oos_marks_work_without_config_assertion(self):
        result = simulate(self.returns(1, split="oos"), self.profile, {"paths": 200})
        self.assertTrue(result["feasible"])
        self.assertTrue(result["inputs"]["returns_are_oos"])


if __name__ == "__main__":
    unittest.main()
