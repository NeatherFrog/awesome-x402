"""Dollar-account sizing tests; fixtures provide no trading profit evidence."""
from datetime import date, timedelta
import unittest

from propdesk import funding_sized as lab


def result(equities, *, capital=25_000.0, worst=None, maxima=None):
    dates = [(date(2024, 1, 1) + timedelta(days=i)).isoformat() for i in range(len(equities))]
    pnl = equities[-1] - capital
    return {"dates": dates, "daily_equity": equities, "capital": capital,
            "daily_rows": {day: {"worst_equity": (worst or equities)[i],
                                  "maximum_close_equity": (maxima or equities)[i]}
                           for i, day in enumerate(dates)},
            "funding_received": pnl, "paired_price_pnl": 0.0, "fees": 0.0,
            "liquidation_penalties": 0.0, "settlements": 20, "liquidations": 0, "fills": 4}


class FundingSizedTests(unittest.TestCase):
    def test_idle_cash_is_total_denominator_without_extra_profit(self):
        assets = [result([25_100, 25_200]), result([25_100, 25_200])]
        out = lab.account(assets)
        self.assertEqual(out["daily_equity"], [100_200, 100_400])
        self.assertAlmostEqual(out["return_pct"], .4)
        self.assertAlmostEqual(out["daily_returns"][0], .002)
        self.assertAlmostEqual(out["daily_returns"][1], 200 / 100_200)
        # Rescaling each active day's return by half uses the wrong denominator.
        self.assertNotAlmostEqual(out["daily_returns"][1], .5 * (25_200 / 25_100 - 1))
        self.assertEqual(out["funding_received"], 400)
        self.assertAlmostEqual(out["accounting_reconciliation_error"], 0)

    def test_risk_envelopes_use_total_account_not_active_subaccount(self):
        out = lab.account([result([25_000], worst=[24_000]), result([25_000], worst=[24_000])])
        self.assertAlmostEqual(out["max_drawdown_pct"], 2)
        self.assertAlmostEqual(out["max_daily_drawdown_pct"], 2)
        self.assertEqual(out["daily_worst_equity"], [98_000])

    def test_idle_cash_does_not_change_liquidation_count_or_active_wallets(self):
        asset = result([24_900])
        asset["liquidations"] = 1
        active = lab.account([asset], idle_cash=0)
        dormant = lab.account([asset], idle_cash=75_000)
        self.assertEqual(active["liquidations"], dormant["liquidations"])
        self.assertIs(dormant["assets"][0], asset)
        self.assertAlmostEqual(dormant["return_pct"], -.1)

    def test_bootstrap_and_monthly_returns_use_total_daily_curve(self):
        values = [25_000 + (i + 1) * 10 for i in range(14)]
        out = lab.account([result(values), result(values)], samples=200)
        self.assertEqual(out["block_mean_ci99"]["observations"], 14)
        self.assertAlmostEqual(out["block_mean_ci99"]["mean"], sum(out["daily_returns"]) / 14)
        self.assertAlmostEqual(out["monthly"]["monthly_returns"]["2024-01"], .0028)
        self.assertEqual(out["idle_cash"], 50_000)

    def test_bad_calendar_or_idle_cash_fail(self):
        asset = result([25_000, 25_000])
        asset["dates"][1] = "2024-01-03"
        with self.assertRaises(ValueError):
            lab.account([asset])
        with self.assertRaises(ValueError):
            lab.account([result([25_000])], idle_cash=-1)


if __name__ == "__main__":
    unittest.main()
