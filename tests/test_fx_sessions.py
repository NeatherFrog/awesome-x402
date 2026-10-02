import unittest
from datetime import datetime, timedelta, timezone
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from propdesk import fx_sessions as fx
from scripts import research_fx_sessions as driver


def fixture():
    start=datetime(2024,1,1,tzinfo=timezone.utc)
    rows=[]
    for i in range(48):
        t=start+timedelta(hours=i)
        rows.append({"time":t.isoformat(),"open":1.1,"high":1.101,"low":1.099,"close":1.1})
    rows[31].update(open=1.1005,high=1.105,low=1.1005,close=1.104)
    rows[32].update(open=1.104,high=1.105,low=1.102,close=1.104)
    return rows


class FXSessionTests(unittest.TestCase):
    def setUp(self):
        self.v=next(v for v in fx.variants() if v['symbol']=='EURUSD' and v['family']=='asian_breakout')
        self.rows=fixture()
    def run_model(self,rows=None,cost=1):
        return fx.simulate(rows or self.rows,self.v,'2024-01-01T00:00:00Z','2024-01-03T00:00:00Z',cost_multiplier=cost)
    def test_all_variants_fixed_and_currency_units(self):
        self.assertEqual(len(fx.variants()),72)
        self.assertAlmostEqual(fx.pnl(100000,1,150,151,'JPY'),100000/151)
        self.assertAlmostEqual(fx.pnl(100000,-1,150,151,'JPY'),-100000/151)
        self.assertEqual(fx.pnl(100000,1,1.1,1.11,'USD'),100000*(1.11-1.1))
    def test_future_ohlc_cannot_create_earlier_decision(self):
        original=fx.decisions(self.rows,self.v)
        changed=deepcopy(self.rows)
        for b in changed[32:]: b.update(open=2,high=3,low=1.9,close=2.5)
        later=fx.decisions(changed,self.v)
        self.assertEqual({k:v for k,v in original.items() if k<=32},{k:v for k,v in later.items() if k<=32})
        self.assertEqual(original[32]['signal_bar'],31)
    def test_next_open_and_cash_accounting(self):
        r=self.run_model()
        self.assertTrue(r['trades'])
        t=r['trades'][0]
        self.assertEqual(t['entry_time'],'2024-01-02T08:00:00+00:00')
        self.assertEqual(t['known_at'],t['entry_time'])
        self.assertAlmostEqual(r['reconciliation_error'],0,places=7)
        self.assertLessEqual(t['initial_margin']+t['entry_fee'],100000)
        self.assertEqual(len(r['dates']),2)
    def test_stop_precedes_target_on_ambiguous_bar(self):
        rows=deepcopy(self.rows);rows[32].update(high=1.12,low=1.09)
        r=self.run_model(rows)
        self.assertEqual(r['trades'][0]['exit_reason'],'stop_first')
        self.assertLess(r['trades'][0]['net_pnl'],0)
    def test_gap_exit_charges_actual_adverse_open_and_records_uncertainty(self):
        rows=deepcopy(self.rows);del rows[33]
        rows[33].update(open=1.08,high=1.081,low=1.079,close=1.08)
        r=self.run_model(rows)
        self.assertTrue(r['missing_exposure_exits'])
        self.assertEqual(r['trades'][0]['exit_reason'],'adverse_gap_exit')
        self.assertLess(r['trades'][0]['exit'],1.08)
    def test_doubled_friction_worsens_same_flat_trade(self):
        self.assertLess(self.run_model(cost=2)['final_equity'],self.run_model()['final_equity'])
    def test_missing_asian_bar_prevents_entry(self):
        rows=deepcopy(self.rows);del rows[26]
        self.assertNotIn(31,fx.decisions(rows,self.v))
    def test_invalid_prices_and_unregistered_parameters_rejected(self):
        rows=deepcopy(self.rows);rows[5]['low']=2
        with self.assertRaises(ValueError): fx.decisions(rows,self.v)
        with self.assertRaises(ValueError): fx.decisions(self.rows,{**self.v,'risk':.2})
    def test_timezone_winter_and_summer_real_offsets(self):
        self.assertEqual(datetime(2026,1,15,tzinfo=fx.LONDON).utcoffset(),timedelta(0))
        self.assertEqual(datetime(2026,7,15,tzinfo=fx.LONDON).utcoffset(),timedelta(hours=1))
    def test_intrabar_exit_interval_and_known_gap_open_are_distinct(self):
        rows=deepcopy(self.rows);rows[32].update(high=1.12,low=1.09)
        t=self.run_model(rows)['trades'][0]
        self.assertEqual(t['exit_time_precision'],'intrabar_unknown')
        self.assertEqual(t['exit_interval_start'],t['entry_time'])
        rows=deepcopy(self.rows);rows[33].update(open=1.08,high=1.081,low=1.079,close=1.08)
        t=self.run_model(rows)['trades'][0]
        self.assertEqual(t['exit_time_precision'],'known_open')
        self.assertEqual(t['exit_time'],'2024-01-02T09:00:00+00:00')
    def test_truncated_source_is_reported_and_never_certified_flat(self):
        r=self.run_model(self.rows[:34])
        self.assertFalse(r['source_coverage']['source_spans_declared_window'])
        self.assertTrue(r['source_coverage']['missing_or_partial_windows'])
        self.assertEqual(r['trades'][0]['entry_time'],self.run_model()['trades'][0]['entry_time'])
    def test_insolvency_records_failed_screen_without_aborting_grid(self):
        rows=deepcopy(self.rows);rows[33].update(open=.0001,high=.00011,low=.00009,close=.0001)
        v=next(v for v in fx.variants() if v['symbol']=='EURUSD' and v['family']=='asian_breakout' and v['risk']==.01 and v['reward_risk']==self.v['reward_risk'] and v['hold_hours']==self.v['hold_hours'])
        r=fx.simulate(rows,v,'2024-01-01T00:00:00Z','2024-01-03T00:00:00Z')
        self.assertTrue(r['insolvent'])
        with TemporaryDirectory() as directory,patch.object(driver,'ROOT',Path(directory)),patch.dict(driver.WINDOWS,{'training':('2024-01-01','2024-01-03')}):
            s=driver.period({'EURUSD':rows},v,'training')
        self.assertFalse(s['passed'])
        self.assertFalse(s['checks']['account_remained_solvent'])
        self.assertIsNone(s['base']['geometric_monthly_return'])
