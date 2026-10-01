import unittest

from propdesk.pine import SUPPORTED_STRATEGIES, generate


class PineExportTests(unittest.TestCase):
    def test_all_supported_signals_export_complete_next_bar_templates(self):
        for strategy_id in SUPPORTED_STRATEGIES:
            with self.subTest(strategy_id=strategy_id):
                script = generate(strategy_id)
                self.assertTrue(script.startswith("//@version=6\n"))
                self.assertNotIn("__SIGNALS__", script)
                self.assertNotIn("__ID__", script)
                self.assertIn("process_orders_on_close=false", script)
                self.assertIn("calc_on_every_tick=false", script)
                self.assertIn("calc_on_order_fills=false", script)
                self.assertIn("barstate.isconfirmed", script)
                self.assertIn("commission_value=0.02", script)
                self.assertIn("slippage=1", script)
                self.assertIn('"mode":"paper"', script)
                self.assertIn('"strategy":"' + strategy_id + '"', script)
                self.assertIn('"price_kind":"signal_close"', script)
                self.assertIn('webhookToken = input.string(""', script)
                self.assertIn("execution is NOT equivalent", script)
                self.assertIn("strategy.exit", script)
                self.assertIn("f_escape(webhookToken)", script)

    def test_baseline_and_untrusted_id_are_rejected(self):
        for strategy_id in ("buy_hold", "unknown", 'ema_pullback\"\nstrategy.close_all()'):
            with self.subTest(strategy_id=strategy_id):
                with self.assertRaises(ValueError):
                    generate(strategy_id)

    def test_ema_uses_previous_closed_bar_and_prior_slope(self):
        script = generate("ema_pullback")
        self.assertIn("close[1] <= emaFast[1]", script)
        self.assertIn("emaSlow > emaSlow[3]", script)
        self.assertIn("close[1] >= emaFast[1]", script)
        self.assertIn('input.float(1.7, "Stop distance', script)
        self.assertIn('input.float(1.8, "Target / stop', script)

    def test_breakout_excludes_current_bar_from_channel(self):
        script = generate("donchian_breakout")
        self.assertIn("ta.highest(high, lookback)[1]", script)
        self.assertIn("ta.lowest(low, lookback)[1]", script)

    def test_indicator_calculations_are_outside_entry_branch(self):
        for strategy_id in SUPPORTED_STRATEGIES:
            script = generate(strategy_id)
            before, _ = script.split("if ready and strategy.position_size == 0", 1)
            self.assertIn("longSignal =", before)
            self.assertIn("shortSignal =", before)
            self.assertIn("atr = ta.atr(14)", before)

    def test_payload_strings_preserve_pine_escaping(self):
        script = generate("ema_pullback")
        self.assertIn(r'str.replace_all(value, "\\", "\\\\")', script)
        self.assertIn(r'str.replace_all(escaped, "\"", "\\\"")', script)
        self.assertIn(r'str.replace_all(escaped, "\n", "\\n")', script)
        self.assertIn(r'str.replace_all(escaped, "\r", "\\r")', script)


if __name__ == "__main__":
    unittest.main()
