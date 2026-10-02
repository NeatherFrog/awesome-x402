import unittest
from datetime import date,timedelta
from propdesk.monthly_inference import monthly_growth_interval


class MonthlyInferenceTests(unittest.TestCase):
    def dates(self,n):return [(date(2024,1,1)+timedelta(days=i)).isoformat() for i in range(n)]
    def test_constant_net_growth_uses_actual_calendar_month_duration(self):
        r=monthly_growth_interval(self.dates(31),[1.08**(1/31)-1]*31,samples=200)
        self.assertAlmostEqual(r['observed_geometric_monthly_growth'],.08,places=12)
        self.assertAlmostEqual(r['conditional_monthly_log_growth_interval']['lower'],.08,places=12)
        self.assertFalse(r['future_target_demonstrated'])
        self.assertFalse(r['live_orders'])
    def test_positive_returns_can_be_far_below_requested_target(self):
        r=monthly_growth_interval(self.dates(90),[.0001]*90,samples=200)
        self.assertGreater(r['conditional_monthly_log_growth_interval']['lower'],0)
        self.assertFalse(r['conditional_lower_bound_above_target'])
    def test_variability_can_leave_target_outside_supported_lower_bound(self):
        returns=[.045,-.038]*45
        r=monthly_growth_interval(self.dates(90),returns,samples=500)
        self.assertLess(r['conditional_monthly_log_growth_interval']['lower'],.08)
        self.assertFalse(r['future_target_demonstrated'])
    def test_missing_days_insolvency_and_infinite_returns_rejected(self):
        dates=self.dates(31);dates[12]=dates[11]
        for d,r in [(dates,[.001]*31),(self.dates(31),[-1]+[.001]*30),(self.dates(31),[float('inf')]+[0]*30)]:
            with self.assertRaises(ValueError):monthly_growth_interval(d,r,samples=200)
