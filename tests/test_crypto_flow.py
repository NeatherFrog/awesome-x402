import ast
from copy import deepcopy
from datetime import datetime,timedelta,timezone
import hashlib
import inspect
from pathlib import Path
import unittest
from unittest.mock import patch
import json
import tempfile

from propdesk import crypto_flow as engine,native_crypto_trend as parent

BASE=datetime(2024,1,1,tzinfo=timezone.utc)


def fixture(days=3,*,absorption=False):
    rows=[]
    for i in range(days*288):
        t=BASE+timedelta(minutes=5*i)
        rows.append({'time':t.isoformat().replace('+00:00','Z'),
                     'known_at':(t+timedelta(minutes=5)).isoformat().replace('+00:00','Z'),
                     'open':100.,'high':100.1,'low':99.9,'close':100.,'volume':100.,
                     'quote_volume':10000.,'trade_count':100,
                     'taker_buy_base_volume':50.,'taker_buy_quote_volume':5000.})
    rows[288].update(volume=1000.,quote_volume=100000.,trade_count=1000,
                     taker_buy_base_volume=850.,taker_buy_quote_volume=85000.,
                     high=100.35,close=100.02 if absorption else 100.3)
    return {s:deepcopy(rows) for s in engine.SYMBOLS}


def variant(**updates):
    return next(v for v in engine.grid() if all(v[k]==x for k,x in updates.items()))


def manual(features,index=289,*,both=False,side=1):
    out={s:{'entry':[0]*len(features.times),'exit_long':[0]*len(features.times),
            'exit_short':[0]*len(features.times)} for s in engine.SYMBOLS}
    for s in engine.SYMBOLS if both else ('BTCUSDT',):
        out[s]['entry'][index-1]=side
    return out


def settled(features,index,rate=.001,milliseconds=0):
    t=datetime.fromtimestamp(features.epochs[index],timezone.utc)+timedelta(milliseconds=milliseconds)
    stamp=t.isoformat().replace('+00:00','Z')
    return {'time':stamp,'known_at':stamp,'rate_kind':'realized_settlement_outcome','funding_rate':rate}


class CryptoFlowTests(unittest.TestCase):
    def run_model(self,features=None,signals=None,v=None,funding=None,**kwargs):
        features=features or engine.FlowFeatures(fixture())
        return engine.simulate(features,signals or manual(features),
                               engine.prepare_funding(features,funding or {s:[] for s in engine.SYMBOLS}),
                               v or variant(), '2024-01-02','2024-01-04',keep_native_curve=True,**kwargs)

    def test_grid64_unique_and_registered_risk_holds(self):
        self.assertEqual(len(engine.grid()),64)
        self.assertEqual(len({v['id'] for v in engine.grid()}),64)
        self.assertEqual({v['risk_fraction'] for v in engine.grid()},{.005,.01})
        self.assertEqual({v['hold_hours'] for v in engine.grid()},{1,3})

    def test_parent_source_hash_and_all_isolated_wallet_helpers_exact_ast(self):
        self.assertEqual(hashlib.sha256(Path(parent.__file__).read_bytes()).hexdigest(),engine.PARENT_ENGINE_SHA256)
        def nodes(fn):
            tree=ast.parse(inspect.getsource(fn));return {n.name:ast.dump(n,include_attributes=False) for n in tree.body[0].body if isinstance(n,ast.FunctionDef)}
        self.assertEqual(nodes(parent.simulate),nodes(engine.simulate))
        def terminal(fn):
            tree=ast.parse(inspect.getsource(fn));body=tree.body[0].body
            start=next(i for i,n in enumerate(body) if isinstance(n,ast.Assign) and ast.unparse(n.targets[0])=='(wins, losses)')
            return ast.dump(ast.Module(body=body[start:],type_ignores=[]),include_attributes=False)
        self.assertEqual(terminal(parent.simulate),terminal(engine.simulate))

    def test_continuation_and_absorption_use_opposite_economic_direction(self):
        for absorption,family,expected in ((False,'flow_continuation',1),(True,'flow_absorption_reversion',-1)):
            f=engine.FlowFeatures(fixture(absorption=absorption))
            obs=f.observations(variant(family=family,flow_window=1))
            self.assertEqual(obs['BTCUSDT']['entry'][288],expected)
            r=self.run_model(f,obs,variant(family=family,flow_window=1))
            first=r['trades'][0]
            self.assertEqual(first['direction'],expected)
            self.assertEqual(first['signal_time'],'2024-01-02T00:00:00Z')
            self.assertEqual(first['entry_time'],'2024-01-02T00:05:00Z')

    def test_activity_baseline_excludes_the_entire_current_window(self):
        data=fixture()
        # A huge currentburst is not averaged into its own72bar activityscreen.
        data['BTCUSDT'][288].update(quote_volume=1e9,volume=1e7,taker_buy_quote_volume=8.5e8,taker_buy_base_volume=8.5e6)
        f=engine.FlowFeatures(data)
        self.assertEqual(f.observations(variant(family='flow_continuation',flow_window=1))['BTCUSDT']['entry'][288],1)

    def test_all64_feature_prefixes_causal_under_future_price_and_flow_changes(self):
        data=fixture();f=engine.FlowFeatures(data);changed=deepcopy(data)
        for rows in changed.values():
            for row in rows[400:]:
                row.update(open=200.,high=300.,low=100.,close=200.,volume=10.,quote_volume=2000.,
                           taker_buy_base_volume=9.,taker_buy_quote_volume=1800.,trade_count=10000)
        after=engine.FlowFeatures(changed)
        for v in engine.grid():
            a,b=f.observations(v),after.observations(v)
            for s in engine.SYMBOLS:
                self.assertEqual(a[s]['entry'][:400],b[s]['entry'][:400])

    def test_stop_hourly_atr_does_not_use_unfinished_current_hour(self):
        data=fixture();f=engine.FlowFeatures(data)
        changed=deepcopy(data)
        for s in engine.SYMBOLS:
            for row in changed[s][290:300]:
                row['high']=200.
        f2=engine.FlowFeatures(changed)
        a=self.run_model(f);b=self.run_model(f2)
        self.assertEqual(a['trades'][0]['quantity'],b['trades'][0]['quantity'])
        self.assertEqual(a['trades'][0]['stop_price'],b['trades'][0]['stop_price'])
        self.assertEqual(a['trades'][0]['atr_known_at'],'2024-01-02T00:00:00Z')

    def test_exact_registered_hold_next_open_exit_one_and_three_hours(self):
        f=engine.FlowFeatures(fixture())
        for hours in (1,3):
            r=self.run_model(f,v=variant(hold_hours=hours))
            trade=r['trades'][0]
            self.assertEqual(trade['reason'],'registered_time_exit')
            self.assertEqual(trade['exit_timing'],'open')
            self.assertEqual(trade['exit_time'],f.times[289+hours*12])

    def test_known_open_portfolio_reservations_do_not_use_future_zero_volume(self):
        f=engine.FlowFeatures(fixture())
        v=variant(risk_fraction=.01,stop_atr=1)
        a=self.run_model(f,manual(f,both=True),v)
        data=fixture();data['BTCUSDT'][289].update(volume=0.,quote_volume=0.,trade_count=0,
                                                 taker_buy_base_volume=0.,taker_buy_quote_volume=0.)
        f2=engine.FlowFeatures(data);b=self.run_model(f2,manual(f2,both=True),v)
        eth_a=next(t for t in a['trades'] if t['symbol']=='ETHUSDT')
        eth_b=next(t for t in b['trades'] if t['symbol']=='ETHUSDT')
        self.assertEqual(eth_a['quantity'],eth_b['quantity'])
        self.assertEqual(b['metrics']['skipped_zero_volume_entry_count'],1)

    def test_total100k_physical_margin_gross_risk_and_cash_conservation(self):
        f=engine.FlowFeatures(fixture())
        for risk in (.005,.01):
            r=self.run_model(f,manual(f,both=True),variant(risk_fraction=risk))
            self.assertLessEqual(sum(t['margin']+t['entry_fee'] for t in r['trades']),100000)
            self.assertLessEqual(sum(t['quantity']*t['entry_price'] for t in r['trades']),200000)
            self.assertLessEqual(sum(t['risk_budget'] for t in r['trades']),100000*risk*2)
            self.assertAlmostEqual(r['metrics']['final_equity'],100000+sum(t['pnl'] for t in r['trades']),places=7)
            self.assertGreaterEqual(r['metrics']['minimum_available_cash'],0)

    def test_actual_funding_preserves_ms_and_cannot_change_earlier_entry(self):
        f=engine.FlowFeatures(fixture());fund={s:[] for s in engine.SYMBOLS}
        fund['BTCUSDT']=[settled(f,294,rate=.001,milliseconds=2)]
        a=self.run_model(f,funding=fund)
        self.assertTrue(a['funding_ledger'][0]['time'].endswith('.002000Z'))
        self.assertLess(a['metrics']['funding_pnl'],0)
        fund['BTCUSDT'][0]['funding_rate']=.005
        b=self.run_model(f,funding=fund)
        self.assertEqual(a['trades'][0]['quantity'],b['trades'][0]['quantity'])
        self.assertEqual(a['native_equity_curve'][:6],b['native_equity_curve'][:6])

    def test_liquidation_precedes_positive_ambiguous_funding(self):
        data=fixture();data['BTCUSDT'][294]['high']=200.
        f=engine.FlowFeatures(data);fund={s:[] for s in engine.SYMBOLS}
        fund['BTCUSDT']=[settled(f,294,rate=.1,milliseconds=2)]
        r=self.run_model(f,manual(f,side=-1),funding=fund)
        self.assertEqual(r['metrics']['liquidation_count'],1)
        self.assertTrue(all(e['pnl']<=0 for e in r['funding_ledger']))
        self.assertGreater(r['metrics']['unfunded_isolated_deficit'],0)

    def test_undefined_zero_volume_flow_no_signal_and_complete_calendar_retained(self):
        data=fixture()
        for rows in data.values():
            rows[288].update(volume=0.,quote_volume=0.,trade_count=0,taker_buy_base_volume=0.,taker_buy_quote_volume=0.)
        f=engine.FlowFeatures(data)
        self.assertEqual(f.observations(variant())['BTCUSDT']['entry'][288],0)
        r=self.run_model(f)
        self.assertEqual(len(r['daily_returns']),2)
        self.assertEqual(len(r['native_equity_curve']),576)

    def test_source_known_at_and_count_domains_cannot_be_forged(self):
        data=fixture();data['BTCUSDT'][0]['known_at']=data['BTCUSDT'][0]['time']
        with self.assertRaisesRegex(ValueError,'only at'):
            engine.FlowFeatures(data)
        data=fixture();data['BTCUSDT'][0]['trade_count']=.5
        with self.assertRaisesRegex(ValueError,'domains'):
            engine.FlowFeatures(data)

    def test_double_cost_friction_and_adverse_daily_bounds(self):
        a=self.run_model();b=self.run_model(cost_multiplier=2)
        self.assertLess(b['metrics']['final_equity'],a['metrics']['final_equity'])
        for row in a['equity_curve']:
            self.assertLessEqual(row['worst_equity'],row['equity'])
            self.assertGreaterEqual(row['best_equity'],row['equity'])

    def test_final_authorization_rejects_missing_changed_and_failed_locks(self):
        from scripts import research_crypto_flow as driver
        training=[{'id':'fixture','passed':True,'target':{'passed':True}}]
        selection={'protocol_sha256':'proto','training_sha256':engine.lab.digest(training),'selected':'fixture',
                   'locked_before_validation':True,'locked_at':'fixturetime'}
        validation={'variant':{'id':'fixture'},'target':{'passed':True}}
        confirmation={'protocol_sha256':'proto','selection_lock_sha256':engine.lab.digest(selection),
                      'validation_sha256':engine.lab.digest(validation),'selected':'fixture','locked_before_final':True}
        report={'protocol_sha256':'proto','selected':'fixture','training':training,'selection_lock':selection,
                'selection_lock_sha256':engine.lab.digest(selection),'validation':validation,
                'confirmation_lock':confirmation,'confirmation_lock_sha256':engine.lab.digest(confirmation)}
        with tempfile.TemporaryDirectory() as tmp,patch.object(driver,'DIRECTORY',Path(tmp)),patch.object(driver,'verify'):
            (Path(tmp)/'training-selection.json').write_text(json.dumps(selection))
            cp=Path(tmp)/'validation-confirmation.json';cp.write_text(json.dumps(confirmation))
            driver.verify_final_authorization(report)
            modified=deepcopy(report);modified['validation']['target']['passed']=False
            with self.assertRaisesRegex(ValueError,'authorize'):
                driver.verify_final_authorization(modified)
            cp.unlink()
            with self.assertRaises(FileNotFoundError):
                driver.verify_final_authorization(report)
            self.assertFalse(cp.exists())

    def test_common_and_reviewed_parent_hashes_are_pinned_before_freeze(self):
        from scripts import research_crypto_flow as driver
        driver.verified_parent()
        with patch.object(driver.shared,'file_hash',return_value='0'*64):
            with self.assertRaisesRegex(ValueError,'identity'):
                driver.verified_parent()

    def test_funding_calendar_requires_all_original_slots_not_metadata_boolean(self):
        from scripts import research_crypto_flow as driver
        rows=[]
        for i in range(3012):
            stamp=(BASE+timedelta(hours=8*i)).isoformat().replace('+00:00','Z')
            rows.append({'time':stamp,'known_at':stamp,'funding_interval_hours':8,'mark_price':None,
                         'funding_rate':.001,'rate_kind':'realized_settlement_outcome'})
        with tempfile.TemporaryDirectory() as tmp,patch.object(driver,'FUNDING',Path(tmp)),patch.object(driver.parent_driver,'_verified_receipt') as verified:
            path=Path(tmp)/'BTCUSDT-funding.json';path.write_text(json.dumps(rows))
            self.assertEqual(len(driver.verified_funding_values({},path.name)),3012)
            self.assertTrue(verified.called)
            path.write_text(json.dumps(rows[:-1]))
            with self.assertRaisesRegex(ValueError,'3012'):
                driver.verified_funding_values({},path.name)


if __name__=='__main__':
    unittest.main()
