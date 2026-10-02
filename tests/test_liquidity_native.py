from copy import deepcopy
from datetime import datetime, timedelta, timezone
import unittest

from propdesk import liquidity_native as engine


BASE = datetime(2024, 1, 1, tzinfo=timezone.utc)


def bar(i, *, open=100, high=101, low=99, close=100, volume=1):
    return {"time": engine.stamp_text(BASE+timedelta(minutes=5*i)), "open": open,
            "high": high, "low": low, "close": close, "volume": volume}


def event(hour, rate, *, milliseconds=0):
    t = engine.stamp_text(BASE+timedelta(hours=hour, milliseconds=milliseconds))
    return {"time": t, "known_at": t, "rate_kind": "realized_settlement_outcome",
            "funding_rate": rate, "funding_interval_hours": 8,
            "mark_price": None}


def fixture(changes=None, fund=None):
    rows = [bar(i) for i in range(288)]
    for i, values in (changes or {}).items():
        rows[i].update(values)
    return engine.Features({s: deepcopy(rows) for s in engine.SYMBOLS},
                           {s: deepcopy(fund or []) for s in engine.SYMBOLS})


def manual_setup(index=1, side=1, stop=98, target=104, symbol="BTCUSDT", expiry_hours=12):
    t = BASE+timedelta(minutes=index*5)
    x = {"symbol": symbol, "direction": side, "entry": 100, "stop": stop,
         "target": target, "entry_zone": [99.8, 100.2], "invalidation": stop,
         "signal_time": engine.stamp_text(t), "sweep_time": engine.stamp_text(BASE),
         "liquidity_level": 99, "expires_at": engine.stamp_text(t+timedelta(hours=expiry_hours)),
         "reason": "synthetictestfixture"}
    return {int(t.timestamp()): {symbol: x}}


class LiquidityNativeTests(unittest.TestCase):
    def test_grid192_unique_and_complete_resample(self):
        self.assertEqual(len(engine.grid()), 192)
        self.assertEqual(len({v['id'] for v in engine.grid()}), 192)
        rows = [bar(i, volume=i+1) for i in range(5)]
        result = engine.resample(rows, 15)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['known_at'], '2024-01-01T00:15:00Z')
        self.assertEqual(result[0]['volume'], 6)
        rows[2]['time'] = engine.stamp_text(BASE+timedelta(minutes=15))
        with self.assertRaisesRegex(ValueError, 'gap'):
            engine.resample(rows, 15)

    def test_prior_extremes_exclude_current_sweep(self):
        rows = [bar(i, high=100+i) for i in range(5)]
        self.assertEqual(engine._extremes(rows, 3, 'high', True), [None, None, None, 102, 103])

    def test_sweep_then_later_displacement_and_confirmed_gap(self):
        aggregated = [dict(open=101, high=102, low=100, close=101) for _ in range(120)]
        aggregated[100] = dict(open=101, high=102, low=98, close=101)
        aggregated[101] = dict(open=101, high=104.1, low=101, close=104)
        aggregated[102] = dict(open=104, high=104.5, low=103, close=104)
        rows = [bar(i, **aggregated[i//3]) for i in range(360)]
        f = engine.Features({s: deepcopy(rows) for s in engine.SYMBOLS}, {s: [] for s in engine.SYMBOLS})
        variant = engine.grid()[0]
        signals = engine.setups(f, variant)
        t = BASE+timedelta(minutes=103*15)
        result = signals[int(t.timestamp())]['BTCUSDT']
        self.assertEqual(result['entry_zone'], [102, 103])
        self.assertEqual(result['entry'], 102.5)
        self.assertEqual(result['sweep_time'], engine.stamp_text(BASE+timedelta(minutes=101*15)))
        self.assertLess(result['stop'], 98)
        self.assertNotIn(int((t-timedelta(minutes=5)).timestamp()), signals)
        changed = deepcopy(rows)
        for i in range(103*3, len(changed)):
            changed[i].update(open=10, high=1000, low=1, close=20)
        f2 = engine.Features({s: deepcopy(changed) for s in engine.SYMBOLS}, {s: [] for s in engine.SYMBOLS})
        later = engine.setups(f2, variant)
        self.assertEqual({k:v for k,v in signals.items() if k<=int(t.timestamp())},
                         {k:v for k,v in later.items() if k<=int(t.timestamp())})

    def test_physical_cash_margin_fees_and_total_account_reconcile(self):
        result = engine.simulate(fixture(), manual_setup(), '2024-01-01', '2024-01-02')
        entry = result['trades'][0]
        self.assertAlmostEqual(entry['margin'], entry['quantity']*entry['entry_price'])
        self.assertLessEqual(entry['risk_budget'], 250)
        self.assertGreaterEqual(min(x['available_cash'] for x in result['equity_curve']), 0)
        self.assertLessEqual(max(x['reserved_margin'] for x in result['equity_curve']), 100000)
        self.assertLess(result['metrics']['equity_pnl_reconciliation_error'], 1e-7)
        self.assertAlmostEqual(result['metrics']['final_equity']-100000, sum(t['pnl'] for t in result['trades']))

    def test_portfolio_risk_and_gross_not_double_counting_capital(self):
        signals = manual_setup()
        for t, asset in manual_setup(symbol='ETHUSDT').items():
            signals[t].update(asset)
        r = engine.simulate(fixture(), signals, '2024-01-01', '2024-01-02')
        self.assertEqual(len(r['trades']), 2)
        self.assertLessEqual(sum(x['risk_budget'] for x in r['trades']), 500)
        self.assertLessEqual(sum(x['margin'] for x in r['trades']), 100000)

    def test_entry_bar_target_is_not_credited_and_both_touched_stop_wins(self):
        f = fixture({1: {'high':105, 'low':97}})
        r = engine.simulate(f, manual_setup(), '2024-01-01', '2024-01-02')
        self.assertEqual(r['trades'][0]['reason'], 'stop')
        self.assertLess(r['trades'][0]['pnl'], 0)
        f = fixture({1: {'high':105}})
        r = engine.simulate(f, manual_setup(), '2024-01-01', '2024-01-02')
        self.assertEqual(r['trades'][0]['reason'], 'sample_boundary')

    def test_gap_past_limit_and_stop_does_not_avoid_loss(self):
        f = fixture({1: {'open':90,'high':91,'low':89,'close':90}})
        r = engine.simulate(f, manual_setup(), '2024-01-01', '2024-01-02')
        self.assertEqual(r['trades'][0]['reason'], 'stop')
        self.assertLess(r['trades'][0]['exit_price'], 90)
        self.assertLess(r['trades'][0]['pnl'], -250)

    def test_expiry_and_unknown_future_setup_are_rejected(self):
        signals = manual_setup()
        next(iter(signals.values()))['BTCUSDT']['expires_at'] = '2024-01-01T00:05:00Z'
        r = engine.simulate(fixture(), signals, '2024-01-01', '2024-01-02')
        self.assertEqual(r['trades'], [])
        signals = manual_setup()
        next(iter(signals.values()))['BTCUSDT']['signal_time'] = '2024-01-01T01:00:00Z'
        with self.assertRaisesRegex(ValueError, 'not yet known'):
            engine.simulate(fixture(), signals, '2024-01-01', '2024-01-02')

    def test_opening_target_precedes_a_later_intrabar_stop(self):
        f = fixture({2:{'open':105,'high':106,'low':97,'close':100}})
        r = engine.simulate(f,manual_setup(),'2024-01-01','2024-01-02')
        self.assertEqual(r['trades'][0]['reason'],'opening_target')
        self.assertGreater(r['trades'][0]['pnl'],0)

    def test_second_asset_sizing_cannot_use_future_first_asset_fill_profit(self):
        f=fixture({1:{'open':120,'high':121,'low':99,'close':100}})
        signals=manual_setup()
        for t, asset in manual_setup(symbol='ETHUSDT').items():
            signals[t].update(asset)
        r=engine.simulate(f,signals,'2024-01-01','2024-01-02')
        self.assertEqual(len(r['trades']),2)
        self.assertAlmostEqual(r['trades'][0]['quantity'],r['trades'][1]['quantity'])
        self.assertLessEqual(max(t['risk_budget'] for t in r['trades']),250)

    def test_strict_funding_entry_and_exit_times_preserve_milliseconds(self):
        # Short receives positive funding, but exactentryinstant never earns.
        r = engine.simulate(fixture(fund=[event(8,.001)]), manual_setup(96,-1,102,96), '2024-01-01','2024-01-02')
        self.assertEqual(r['funding_ledger'], [])
        # Millisecond-after-entry cannot earn positive credit either.
        r = engine.simulate(fixture(fund=[event(8,.001,milliseconds=1)]), manual_setup(96,-1,102,96), '2024-01-01','2024-01-02')
        self.assertEqual(r['funding_ledger'], [])
        # Long mayowe settlement after ambiguousintrabarentry; retain charge.
        r = engine.simulate(fixture(fund=[event(8,.001,milliseconds=1)]), manual_setup(96), '2024-01-01','2024-01-02')
        self.assertEqual(len(r['funding_ledger']), 1)
        self.assertTrue(r['funding_ledger'][0]['time'].endswith('.001000Z'))
        self.assertLess(r['funding_ledger'][0]['pnl'], 0)

    def test_funding_actual_cash_and_future_rate_not_a_forecast(self):
        fund = [event(8,.001),event(16,-.001)]
        r = engine.simulate(fixture(fund=fund), manual_setup(), '2024-01-01', '2024-01-02')
        self.assertEqual(len(r['funding_ledger']),2)
        self.assertAlmostEqual(r['metrics']['funding_pnl'],0)
        changed = deepcopy(fund); changed[1]['funding_rate'] = .005
        r2 = engine.simulate(fixture(fund=changed),manual_setup(),'2024-01-01','2024-01-02')
        self.assertEqual(r['trades'][0]['quantity'], r2['trades'][0]['quantity'])
        self.assertEqual(r['equity_curve'][:192],r2['equity_curve'][:192])
        self.assertLess(r2['metrics']['final_equity'],r['metrics']['final_equity'])

    def test_liquidation_before_positive_funding_and_unfunded_gap_visible(self):
        f = fixture({96:{'open':100,'high':250,'low':99,'close':100}},fund=[event(8,.01,milliseconds=1)])
        r = engine.simulate(f,manual_setup(1,-1,200,90),'2024-01-01','2024-01-02')
        self.assertEqual(r['funding_ledger'],[])
        self.assertEqual(r['metrics']['liquidation_count'],1)
        self.assertGreater(r['metrics']['unfunded_isolated_deficit'],0)
        self.assertGreaterEqual(r['metrics']['final_equity'],0)

    def test_absent_trade_bar_never_fills_and_held_unresolved_mark_flagged(self):
        f = fixture({1:{'volume':0}})
        signals = manual_setup()
        next(iter(signals.values()))['BTCUSDT']['expires_at'] = '2024-01-01T00:10:00Z'
        r = engine.simulate(f,signals,'2024-01-01','2024-01-02')
        self.assertEqual(r['trades'],[])
        f = fixture({2:{'volume':0,'open':1,'high':1,'low':1,'close':1}})
        r = engine.simulate(f,manual_setup(),'2024-01-01','2024-01-02')
        self.assertEqual(r['metrics']['unresolved_absent_trade_exposure_bars'],1)
        self.assertEqual(r['metrics']['liquidation_count'],0)

    def test_negative_funding_included_in_adverse_equity_before_stop(self):
        f = fixture({96:{'low':97}},fund=[event(8,.01,milliseconds=1)])
        r = engine.simulate(f,manual_setup(),'2024-01-01','2024-01-02')
        self.assertLess(r['funding_ledger'][0]['pnl'],0)
        self.assertLess(r['equity_curve'][96]['worst_equity'],r['equity_curve'][96]['equity'])
        self.assertLess(r['metrics']['equity_pnl_reconciliation_error'],1e-7)

    def test_fee_stress_and_daily_complete_bounds(self):
        a=engine.simulate(fixture(),manual_setup(),'2024-01-01','2024-01-02')
        b=engine.simulate(fixture(),manual_setup(),'2024-01-01','2024-01-02',cost_multiplier=2)
        self.assertLess(b['metrics']['final_equity'],a['metrics']['final_equity'])
        self.assertEqual(len(a['daily']),1)
        d=a['daily'][0]
        self.assertLessEqual(d['worst_equity'],d['equity'])
        self.assertGreaterEqual(d['best_equity'],d['equity'])

    def test_unfilled_btc_reservation_cannot_enlarge_same_bar_eth_quantity(self):
        signals=manual_setup(stop=99.999,target=110)
        for t,asset in manual_setup(stop=99.999,target=110,symbol='ETHUSDT').items():
            signals[t].update(asset)
        f=fixture()
        filled=engine.simulate(f,signals,'2024-01-01','2024-01-02')
        f=fixture()
        f.bars['BTCUSDT'][1].update(open=101,high=102,low=100.5,close=101)
        unfilled=engine.simulate(f,signals,'2024-01-01','2024-01-02')
        a=[t for t in filled['trades'] if t['symbol']=='ETHUSDT'][0]
        b=[t for t in unfilled['trades'] if t['symbol']=='ETHUSDT'][0]
        self.assertEqual(a['quantity'],b['quantity'])

    def test_exact_boundary_settlement_debit_but_no_credit(self):
        r=engine.simulate(fixture(fund=[event(24,.001)]),manual_setup(),'2024-01-01','2024-01-02')
        self.assertEqual(len(r['funding_ledger']),1)
        self.assertLess(r['funding_ledger'][0]['pnl'],0)
        r=engine.simulate(fixture(fund=[event(24,.001)]),manual_setup(side=-1,stop=102,target=96),'2024-01-01','2024-01-02')
        self.assertEqual(r['funding_ledger'],[])

    def test_predeclared_risk_catalogue_changes_sizing_without_extra_collateral(self):
        signal=manual_setup()
        for risk in (.0025,.005,.01):
            r=engine.simulate(fixture(),signal,'2024-01-01','2024-01-02',risk_fraction=risk)
            self.assertLessEqual(r['trades'][0]['risk_budget'],100000*risk)
            self.assertLessEqual(max(p['opening_planned_gross'] for p in r['equity_curve']),100000)
            self.assertGreaterEqual(min(p['available_cash'] for p in r['equity_curve']),0)
        with self.assertRaisesRegex(ValueError,'catalogue'):
            engine.simulate(fixture(),signal,'2024-01-01','2024-01-02',risk_fraction=.02)

    def test_insolvency_is_failed_screen_instead_of_geometric_exception(self):
        from scripts.research_liquidity_native import assess
        result={'metrics':{'return_pct':-100},'daily':[{'date':'2024-01-01','return':-1,'equity':0,'worst_equity':0,'best_equity':100000}]}
        out=assess(result,result,['2024-01-01','2024-01-02'],'training',1)
        self.assertFalse(out['passed'])
        self.assertFalse(out['checks']['positive_account_equity_every_day'])
        self.assertIsNone(out['base']['geometric_monthly_return'])


if __name__ == '__main__':
    unittest.main()
