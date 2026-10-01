"""Causal setup plans: current evidence, frozen levels and explicit unknowns."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import unittest

from propdesk.setups import build_setup

NOW = datetime(2026, 10, 1, 12, 5, tzinfo=timezone.utc)


def research():
    return {"selected_strategy": "ema_pullback", "training_candidate": "ema_pullback",
            "strategies": [{"id": "ema_pullback", "eligible": True, "training_winner": True,
                            "params": {"fast": 12, "slow": 48, "stop_atr": 1.7, "reward_risk": 1.8},
                            "rule_replay": {"status": "pass"}}],
            "data": {"source": "csv", "symbol": "EURUSD", "timeframe_minutes": 60,
                     "irregular_intervals": False},
            "latest_signal": {"status": "candidate", "direction": "long", "strategy_id": "ema_pullback",
                              "reference_time": "2026-10-01T11:00:00Z", "reference_price": 1.1,
                              "stop": 1.0983, "target": 1.10306, "regime": "trend"},
            "market_context": {"last_bar": {"time": "2026-10-01T11:00:00Z", "open": 1.099,
                                           "high": 1.101, "low": 1.098, "close": 1.1},
                               "atr14": 0.001, "ema20": 1.099, "ema50": 1.097,
                               "recent_high20": 1.103, "recent_low20": 1.09,
                               "volatility_pct": 0.1, "timeframe_minutes": 60},
            "profile_rules": {"news_allowed": False, "status": "user_verified"}}


def context():
    return {"macro_cycle": "unknown",
            "news": {"confirmed": True, "source": "Manual calendar check",
                     "observed_at": "2026-10-01T12:00:00Z", "events": []}}


def event(*, time="2026-10-01T12:20:00Z", known_at="2026-09-30T10:00:00Z", impact="high"):
    return {"time": time, "known_at": known_at, "impact": impact,
            "title": "Scheduled release", "currency": "USD"}


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.research = research()
        self.context = context()

    def plan(self, now=NOW):
        return build_setup(self.research, self.context, now)

    def test_fresh_eligible_signal_preserves_backtested_stop_and_target(self):
        before = deepcopy(self.research)
        result = self.plan()
        self.assertEqual(result["status"], "paper_review")
        self.assertEqual(result["direction"], "long")
        self.assertEqual(result["stop_loss"], 1.0983)
        self.assertEqual(result["take_profit_zone"]["target"], 1.10306)
        self.assertEqual(result["entry_zone"]["low"], 1.0999)
        self.assertEqual(result["entry_zone"]["high"], 1.1001)
        self.assertEqual(result["rr"], 1.8)
        self.assertTrue(result["planning_only"])
        self.assertFalse(result["can_trade"])
        self.assertEqual(self.research, before)
        json.dumps(result, allow_nan=False)

    def test_reference_is_bar_open_freshness_is_bar_close(self):
        result = self.plan()
        self.assertEqual(result["reference_time"], "2026-10-01T11:00:00Z")
        self.assertEqual(result["reference_close_time"], "2026-10-01T12:00:00Z")
        self.assertEqual(result["expires_at"], "2026-10-01T13:00:00Z")
        self.assertEqual(result["context"]["price_age_minutes"], 5)
        self.assertEqual(result["context"]["freshness_limit_minutes"], 180)

    def test_unclosed_bar_cannot_supply_signal(self):
        result = self.plan(NOW.replace(hour=11, minute=50))
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["direction"], "wait")
        self.assertIsNone(result["stop_loss"])
        self.assertEqual(result["context"]["price_state"], "future_unclosed")

    def test_older_snapshot_blocks_without_levels(self):
        result = self.plan(NOW + timedelta(hours=4))
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["context"]["price_state"], "stale")
        self.assertIsNone(result["entry_zone"]["low"])

    def test_next_expected_closed_bar_expires_even_within_freshness_limit(self):
        result = self.plan(NOW.replace(hour=13, minute=0))
        self.assertEqual(result["context"]["price_state"], "expired_next_bar")
        self.assertEqual(result["status"], "blocked")

    def test_synthetic_demo_cannot_become_actionable(self):
        self.research["data"]["source"] = "demo"
        result = self.plan()
        self.assertEqual(result["status"], "blocked")
        self.assertFalse(result["can_trade"])
        self.assertIsNone(result["stop_loss"])
        self.assertEqual(result["context"]["sources"]["prices"], "synthetic_demo")

    def test_failed_training_winner_is_not_replaced_by_holdout_runner_up(self):
        self.research["selected_strategy"] = None
        self.research["strategies"].append({"id": "donchian_breakout", "eligible": True})
        result = self.plan()
        self.assertEqual(result["strategy_id"], "ema_pullback")
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["direction"], "wait")

    def test_ineligible_or_baseline_candidate_is_blocked(self):
        for field, value in (("eligible", False), ("eligible", 1), ("training_winner", False), ("baseline", True)):
            self.research = research()
            self.research["strategies"][0][field] = value
            with self.subTest(field=field):
                self.assertEqual(self.plan()["status"], "blocked")

    def test_mismatched_signal_strategy_and_reference_are_blocked(self):
        for field, value in (("strategy_id", "donchian_breakout"), ("reference_time", "2026-10-01T10:00:00Z"),
                             ("reference_price", 100)):
            self.research = research()
            self.research["latest_signal"][field] = value
            with self.subTest(field=field):
                self.assertEqual(self.plan()["status"], "blocked")

    def test_no_new_signal_creates_wait_without_invented_price_levels(self):
        self.research["latest_signal"].update(direction="wait", stop=None, target=None)
        result = self.plan()
        self.assertEqual(result["status"], "wait")
        self.assertEqual(result["direction"], "wait")
        self.assertIsNone(result["entry_zone"]["low"])
        self.assertIn("EMA", result["entry_zone"]["trigger"])
        self.assertIsNone(result["take_profit_zone"]["target"])

    def test_missing_causal_snapshot_blocks_old_saved_research(self):
        del self.research["market_context"]
        result = self.plan()
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["context"]["price_state"], "unknown")

    def test_short_setup_has_original_short_stop_and_target(self):
        self.research["latest_signal"].update(direction="short", stop=1.1017, target=1.09694)
        result = self.plan()
        self.assertEqual(result["status"], "paper_review")
        self.assertEqual(result["direction"], "short")
        self.assertEqual(result["stop_loss"], 1.1017)
        self.assertLess(result["take_profit_zone"]["high"], result["entry_zone"]["low"])
        self.assertLess(result["entry_zone"]["high"], result["stop_loss"])

    def test_bad_stop_target_and_atr_are_not_repaired_silently(self):
        for target, stop, atr in ((1.09, 1.0983, .001), (1.103, 1.11, .001), (float("inf"), 1.0983, .001),
                                  (1.103, 1.0983, 0), (1.103, 1.0983, True), (1.103, 1.0983, float("nan"))):
            self.research = research()
            self.research["latest_signal"].update(target=target, stop=stop)
            self.research["market_context"]["atr14"] = atr
            with self.subTest(target=target, stop=stop, atr=atr):
                result = self.plan()
                self.assertEqual(result["status"], "blocked")
                self.assertIsNone(result["stop_loss"])
                json.dumps(result, allow_nan=False)

    def test_rules_replay_failure_blocks_plan(self):
        self.research["strategies"][0]["rule_replay"]["status"] = "breach"
        self.assertEqual(self.plan()["status"], "blocked")

    def test_unknown_context_stays_unknown_and_restricted_news_blocks(self):
        self.context = None
        result = self.plan()
        self.assertEqual(result["context"]["macro_cycle"], "unknown")
        self.assertEqual(result["context"]["sentiment"]["state"], "unknown")
        self.assertIsNone(result["context"]["sentiment"]["score"])
        self.assertEqual(result["context"]["news_state"], "unknown")
        self.assertEqual(result["status"], "blocked")

    def test_unknown_news_permitted_profile_still_explicit_warning(self):
        self.context = None
        self.research["profile_rules"]["news_allowed"] = True
        result = self.plan()
        self.assertEqual(result["status"], "paper_review")
        self.assertEqual(result["context"]["news_state"], "unknown")
        self.assertFalse(result["can_trade"])
        self.assertTrue(any("календарь неизвестен" in text for text in result["warnings"]))

    def test_news_without_fresh_check_or_source_is_unknown(self):
        for field, value in (("observed_at", None), ("observed_at", "2026-09-30T12:00:00Z"),
                             ("observed_at", "2026-10-01T13:00:00Z"), ("source", ""), ("confirmed", False)):
            self.context = context()
            self.context["news"][field] = value
            with self.subTest(field=field, value=value):
                result = self.plan()
                self.assertEqual(result["context"]["news_state"], "unknown")
                self.assertEqual(result["status"], "blocked")

    def test_known_high_impact_event_blackout_boundaries(self):
        self.context["news"]["events"] = [event(time="2026-10-01T12:20:00Z")]
        for delta in (-30, -5, 0, 15):
            with self.subTest(delta=delta):
                stamp = datetime(2026, 10, 1, 12, 20, tzinfo=timezone.utc) + timedelta(minutes=delta)
                self.context["news"]["observed_at"] = (stamp - timedelta(minutes=1)).isoformat().replace("+00:00", "Z")
                result = self.plan(stamp)
                self.assertEqual(result["context"]["news_state"], "blackout")
                self.assertEqual(result["status"], "blocked")
        self.context["news"]["observed_at"] = "2026-10-01T12:00:00Z"
        self.assertEqual(self.plan(datetime(2026, 10, 1, 12, 36, tzinfo=timezone.utc))["context"]["news_state"], "checked_no_blackout")

    def test_future_known_at_event_is_not_used(self):
        self.context["news"]["events"] = [event(known_at="2026-10-01T12:06:00Z")]
        result = self.plan()
        self.assertEqual(result["context"]["news_state"], "checked_no_blackout")
        self.assertEqual(result["context"]["news_events"], [])
        self.assertEqual(result["status"], "paper_review")
        self.assertTrue(any("ещё не известные" in text for text in result["warnings"]))

    def test_lower_impact_and_distant_events_do_not_form_blackout(self):
        self.context["news"]["events"] = [event(impact="medium"), event(time="2026-10-02T12:20:00Z")]
        result = self.plan()
        self.assertEqual(result["context"]["news_state"], "checked_no_blackout")
        self.assertEqual(len(result["context"]["news_events"]), 2)
        self.assertEqual(result["status"], "paper_review")

    def test_fresh_sentiment_is_qualitative_warning_not_unfitted_profit_filter(self):
        self.context.update(macro_cycle="recession", macro_source="Manual economic review",
                            sentiment={"score": -0.8, "source": "Manual sentiment review", "confirmed": True,
                                       "observed_at": "2026-10-01T11:45:00Z"})
        result = self.plan()
        self.assertEqual(result["status"], "paper_review")
        self.assertEqual(result["context"]["sentiment"]["score"], -0.8)
        self.assertEqual(result["context"]["sentiment"]["label"], "negative")
        self.assertTrue(any("против подтверждённых" in text for text in result["warnings"]))
        self.assertEqual(result["stop_loss"], self.research["latest_signal"]["stop"])
        self.assertEqual(result["context"]["sources"]["macro_cycle"], "Manual economic review")

    def test_future_stale_unconfirmed_sentiment_never_becomes_current_score(self):
        for observed, confirmed, state in (("2026-10-01T13:00:00Z", True, "future_not_known"),
                                           ("2026-09-29T13:00:00Z", True, "stale"),
                                           ("2026-10-01T12:00:00Z", False, "unconfirmed")):
            self.context["sentiment"] = {"score": .9, "source": "Manual", "confirmed": confirmed, "observed_at": observed}
            with self.subTest(state=state):
                sentiment = self.plan()["context"]["sentiment"]
                self.assertEqual(sentiment["state"], state)
                self.assertIsNone(sentiment["score"])

    def test_manual_context_types_and_bounded_event_count(self):
        invalid = [[], {"macro_cycle": "guaranteed bull"}, {"news": {"confirmed": 1}},
                   {"news": {"events": [event()] * 201}},
                   {"sentiment": {"score": True, "confirmed": True, "observed_at": "2026-10-01T12:00:00Z", "source": "Manual"}},
                   {"sentiment": {"score": float("nan"), "confirmed": True, "observed_at": "2026-10-01T12:00:00Z", "source": "Manual"}},
                   {"news": {"events": [event(known_at="2026-10-01T12:00:00")]}},
                   {"news": {"events": [event(impact="critical")]}}]
        for payload in invalid:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                build_setup(self.research, payload, NOW)

    def test_daily_bars_do_not_guess_exchange_calendar(self):
        self.research["market_context"]["timeframe_minutes"] = 1440
        self.research["market_context"]["last_bar"]["time"] = "2026-09-30T12:00:00Z"
        self.research["latest_signal"]["reference_time"] = "2026-09-30T12:00:00Z"
        result = self.plan()
        self.assertEqual(result["reference_close_time"], "2026-10-01T12:00:00Z")
        self.assertEqual(result["expires_at"], "2026-10-02T12:00:00Z")
        self.assertTrue(any("праздники" in text for text in result["warnings"]))
        self.assertFalse(result["can_trade"])

    def test_naive_decision_timestamp_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "часовым поясом"):
            build_setup(self.research, self.context, datetime(2026, 10, 1))


if __name__ == "__main__":
    unittest.main()
