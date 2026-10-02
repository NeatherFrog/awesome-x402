from copy import deepcopy
from datetime import datetime, timedelta, timezone
import ast
import hashlib
import math
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from propdesk import native_noise_area as noise


def fixture(direction=1, days=22):
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    trades, marks = {}, {}
    for symbol in noise.SYMBOLS:
        rows, computed = [], []
        for index in range(days*288):
            dt = start + timedelta(minutes=5*index)
            local = dt.astimezone(noise.NEW_YORK)
            minute = local.hour*60+local.minute
            price = 100.
            if local.weekday() < 5 and 570 <= minute < 960:
                price += .1*(minute+5-570)/390
            if local.date().isoformat() == '2024-01-22' and minute >= 595:
                price = 100 + direction*.3
            stamp = dt.isoformat().replace('+00:00', 'Z')
            known = (dt + timedelta(minutes=5)).isoformat().replace('+00:00', 'Z')
            opening = 100 if minute == 570 or (local.date().isoformat() == '2024-01-22' and minute == 595) else price
            row = {'time': stamp, 'known_at': known, 'open': opening,
                   'high': max(opening, price)+.001, 'low': min(opening, price)-.001,
                   'close': price, 'volume': 10., 'quote_volume': 10*price}
            rows.append(row)
            computed.append({key: row[key] for key in ('time', 'known_at', 'open', 'high', 'low', 'close')}
                            | {'source_auxiliary_count': 300})
        trades[symbol], marks[symbol] = rows, computed
    entry = int((datetime(2024, 1, 22, 10, tzinfo=noise.NEW_YORK).astimezone(timezone.utc)-start).total_seconds()/300)
    return trades, marks, entry


def configuration(**parameters):
    return next(row for row in noise.grid() if all(row[key] == value for key, value in parameters.items()))


def run_fixture(trades, marks, value=None, settlements=None, cost=1, keep_curve=False):
    features = noise.NoiseFeatures(trades, marks)
    value = value or configuration(band_multiplier=1, checkpoint_minutes=30,
                                  exit_mode='current_band_vwap', aggregate_risk_fraction=.005)
    funding = noise.prepare_funding(features, settlements or {s: [] for s in noise.SYMBOLS})
    return noise.simulate(features, features.observations(value), funding, value,
                          '2024-01-01', '2024-01-23', cost_multiplier=cost, keep_native_curve=keep_curve)


class NativeNoiseTests(unittest.TestCase):
    def test_exact_24_catalog_and_all_branches_nonvacuous(self):
        self.assertEqual(len(noise.grid()), 24)
        self.assertEqual(len({row['id'] for row in noise.grid()}), 24)
        trades, marks, entry = fixture()
        features = noise.NoiseFeatures(trades, marks)
        funding = noise.prepare_funding(features, {s: [] for s in noise.SYMBOLS})
        for value in noise.grid():
            with self.subTest(configuration=value['id']):
                result = noise.simulate(features, features.observations(value), funding, value,
                                        '2024-01-01', '2024-01-23')
                self.assertTrue(result['trades'])
                self.assertTrue(any(row['entry_time'] == trades['BTCUSDT'][entry]['time'] for row in result['trades']))

    def test_prior_fourteen_same_slots_and_exact_quote_base_vwap(self):
        trades, marks, entry = fixture()
        features = noise.NoiseFeatures(trades, marks)
        j = entry-1
        base = features.base['BTCUSDT']
        expected = abs((100+.1*30/390)/100-1)
        self.assertAlmostEqual(base['sigma'][j], expected)
        first = entry-6
        actual = sum(trades['BTCUSDT'][k]['quote_volume'] for k in range(first, j+1))/60
        self.assertAlmostEqual(base['vwap'][j], actual)
        self.assertEqual(base['upper_anchor'][j], 100.1)
        self.assertEqual(base['lower_anchor'][j], trades['BTCUSDT'][first]['open'])

    def test_decision_exists_on_prefix_before_future_quote_or_session_close(self):
        trades, marks, entry = fixture()
        value = configuration(band_multiplier=1, checkpoint_minutes=30)
        baseline = noise.NoiseFeatures(trades, marks).observations(value)
        prefix = noise.NoiseFeatures({s: rows[:entry] for s, rows in trades.items()},
                                     {s: rows[:entry] for s, rows in marks.items()}).observations(value)
        for s in noise.SYMBOLS:
            for key in ('entry', 'stop_long', 'stop_short'):
                self.assertEqual(prefix[s][key][entry-1], baseline[s][key][entry-1])
        changed, changed_marks = deepcopy(trades), deepcopy(marks)
        for s in noise.SYMBOLS:
            for i in range(entry, len(changed[s])):
                changed[s][i].update(open=900, high=901, low=899, close=900, quote_volume=9000)
                changed_marks[s][i].update(open=900, high=901, low=899, close=900)
        future = noise.NoiseFeatures(changed, changed_marks).observations(value)
        self.assertEqual(future['BTCUSDT']['stop_long'][entry-1], baseline['BTCUSDT']['stop_long'][entry-1])

    def test_clock_weekends_and_warmup_have_no_fake_entries(self):
        trades, marks, entry = fixture()
        features = noise.NoiseFeatures(trades, marks)
        observations = features.observations(configuration(checkpoint_minutes=15))
        for s in noise.SYMBOLS:
            for j, side in enumerate(observations[s]['entry']):
                if side:
                    known = datetime.fromtimestamp(features.epochs[j]+300, timezone.utc).astimezone(noise.NEW_YORK)
                    self.assertLess(known.weekday(), 5)
                    self.assertGreaterEqual(known.hour*60+known.minute, 600)
                    self.assertLess(known.hour*60+known.minute, 960)
                    self.assertEqual((known.hour*60+known.minute-600) % 15, 0)
            self.assertFalse(any(observations[s]['entry'][:14*288]))

    def test_native_fills_both_notional_fees_physical_margin_stop_risk_and_cash(self):
        trades, marks, entry = fixture()
        result = run_fixture(trades, marks)
        self.assertEqual(len(result['daily_returns']), 22)
        self.assertEqual(result['metrics']['terminal_open_positions'], 0)
        self.assertGreaterEqual(result['metrics']['minimum_available_cash'], 0)
        self.assertAlmostEqual(result['metrics']['final_equity'], 100000+sum(t['pnl'] for t in result['trades']), places=7)
        for row in result['trades']:
            self.assertEqual(row['signal_known_at'], row['entry_time'])
            self.assertEqual(row['entry_time'], trades[row['symbol']][entry]['time'])
            self.assertAlmostEqual(row['margin'], row['quantity']*row['entry_price']/2)
            self.assertAlmostEqual(row['entry_fee'], row['quantity']*row['entry_price']*.0005)
            self.assertAlmostEqual(row['exit_fee'], row['quantity']*row['exit_price']*.0005)
            self.assertLessEqual(row['risk_at_stop_including_costs'], row['risk_budget']+1e-8)
            self.assertLessEqual(row['quantity']*row['entry_price'], 100000+1e-8)
            self.assertLessEqual(datetime.fromisoformat(row['exit_time'].replace('Z', '+00:00')).astimezone(noise.NEW_YORK).hour, 16)
        self.assertLessEqual(sum(t['margin']+t['entry_fee'] for t in result['trades']), 100000)
        self.assertFalse(result['prop_qualified'])

    def test_short_units_and_adverse_fills_mirror_long(self):
        trades, marks, entry = fixture(-1)
        result = run_fixture(trades, marks)
        self.assertTrue(result['trades'])
        for row in result['trades']:
            self.assertEqual(row['direction'], -1)
            self.assertLess(row['entry_price'], row['entry_raw_price'])
            self.assertGreater(row['exit_price'], row['exit_raw_price'])

    def test_zero_volume_intent_cannot_increase_other_asset_same_opening_size(self):
        trades, marks, entry = fixture()
        normal = run_fixture(trades, marks)
        changed = deepcopy(trades)
        changed['BTCUSDT'][entry].update(volume=0, quote_volume=0)
        result = run_fixture(changed, marks)
        def opening_eth(rows):
            return next(row for row in rows['trades'] if row['symbol'] == 'ETHUSDT' and row['entry_time'] == trades['ETHUSDT'][entry]['time'])
        self.assertEqual(opening_eth(result)['quantity'], opening_eth(normal)['quantity'])
        self.assertGreater(result['metrics']['skipped_zero_volume_entry_count'], 0)

    def test_old_exit_cash_cannot_enlarge_other_asset_same_opening_intent(self):
        trades, marks, entry = fixture()
        value = configuration(band_multiplier=1, checkpoint_minutes=30,
                              exit_mode='current_band_vwap', aggregate_risk_fraction=.005)
        # Isolate the order-planning primitive: an old BTC holding has a known
        # closed-checkpoint exit while ETH has its first known entry intention.
        opening = entry+6
        def execute(rows):
            features = noise.NoiseFeatures(rows, marks)
            observations = deepcopy(features.observations(value))
            observations['ETHUSDT']['entry'][entry-1] = 0
            observations['ETHUSDT']['entry'][opening-1] = 1
            observations['BTCUSDT']['exit_long'][opening-1] = 1
            funding = noise.prepare_funding(features, {s:[] for s in noise.SYMBOLS})
            result = noise.simulate(features, observations, funding, value, '2024-01-01','2024-01-23')
            return next(row for row in result['trades'] if row['symbol']=='ETHUSDT' and
                        row['entry_time']==rows['ETHUSDT'][opening]['time'])
        base = execute(trades)
        changed = deepcopy(trades)
        changed['BTCUSDT'][opening].update(volume=0, quote_volume=0)
        absent_old_exit = execute(changed)
        self.assertEqual(base['quantity'], absent_old_exit['quantity'])
        self.assertEqual(base['risk_budget'], absent_old_exit['risk_budget'])
        self.assertEqual(base['margin'], absent_old_exit['margin'])

    def test_unknown_old_mark_extrema_cannot_resize_new_other_asset_intent(self):
        trades, marks, entry = fixture()
        value = configuration(band_multiplier=1, checkpoint_minutes=30,
                              exit_mode='current_band_vwap', aggregate_risk_fraction=.005)
        opening=entry+6
        def execute(computed):
            features=noise.NoiseFeatures(trades,computed)
            observations=deepcopy(features.observations(value))
            observations['ETHUSDT']['entry'][entry-1]=0
            observations['ETHUSDT']['entry'][opening-1]=1
            funding=noise.prepare_funding(features,{s:[] for s in noise.SYMBOLS})
            result=noise.simulate(features,observations,funding,value,'2024-01-01','2024-01-23')
            return next(row for row in result['trades'] if row['symbol']=='ETHUSDT' and
                        row['entry_time']==trades['ETHUSDT'][opening]['time'])
        baseline=execute(marks)
        changed=deepcopy(marks)
        changed['BTCUSDT'][opening].update(low=40,high=150)
        shocked=execute(changed)
        self.assertEqual(baseline['quantity'],shocked['quantity'])
        self.assertEqual(baseline['risk_budget'],shocked['risk_budget'])

    def test_checkpoint_ratchets_cannot_move_backwards_or_activate_before_close(self):
        trades, marks, _ = fixture()
        result = run_fixture(trades, marks)
        self.assertTrue(result['stop_update_ledger'])
        for row in result['stop_update_ledger']:
            self.assertGreaterEqual(row['new_stop'], row['old_stop'])
            self.assertEqual(row['signal_known_at'], row['active_at'])
            self.assertEqual(datetime.fromisoformat(row['active_at'].replace('Z', '+00:00'))-
                             datetime.fromisoformat(row['signal_time'].replace('Z', '+00:00')), timedelta(minutes=5))

    def test_known_opening_gap_executes_actual_open_not_old_band(self):
        trades, marks, entry = fixture()
        for s in noise.SYMBOLS:
            trades[s][entry+1].update(open=80, high=80.1, low=79.9, close=80, quote_volume=800)
        result = run_fixture(trades, marks)
        row = result['trades'][0]
        self.assertEqual(row['reason'], 'known_opening_stop_gap')
        self.assertEqual(row['exit_raw_price'], 80)
        self.assertGreater(-row['pnl'], row['risk_budget'])

    def test_funding_is_charged_and_its_exact_positive_credit_not_used(self):
        trades, marks, entry = fixture()
        stamp = datetime(2024, 1, 22, 11, tzinfo=noise.NEW_YORK).astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')
        settlement = {s: [{'time': stamp, 'known_at': stamp, 'funding_rate': .001,
                           'rate_kind': 'realized_settlement_outcome'}] for s in noise.SYMBOLS}
        result = run_fixture(trades, marks, settlements=settlement)
        self.assertLess(result['metrics']['funding_pnl'], 0)
        self.assertTrue(result['funding_ledger'])
        for row in result['funding_ledger']:
            self.assertFalse(row['actual_mark_unavailable'])
            self.assertTrue(row['settlement_point_mark_unavailable'])
        short_trades, short_marks, _ = fixture(-1)
        positive = run_fixture(short_trades, short_marks, settlements=settlement)
        self.assertEqual(positive['metrics']['funding_pnl'], 0)

    def test_doubled_friction_changes_cash_and_fills(self):
        trades, marks, _ = fixture()
        base, stress = run_fixture(trades, marks), run_fixture(trades, marks, cost=2)
        self.assertLess(stress['metrics']['final_equity'], base['metrics']['final_equity'])
        self.assertNotEqual(stress['trades'][0]['entry_price'], base['trades'][0]['entry_price'])

    def test_parent_wallet_funding_and_liquidation_helpers_are_identical(self):
        root = Path(__file__).resolve().parents[1]
        parent = root/'propdesk/native_crypto_mark.py'
        self.assertEqual(hashlib.sha256(parent.read_bytes()).hexdigest(), noise.PARENT_MARK_ENGINE_SHA256)
        def helpers(path):
            simulation = next(node for node in ast.parse(path.read_text()).body if isinstance(node, ast.FunctionDef) and node.name == 'simulate')
            return {node.name: ast.dump(node, include_attributes=False) for node in simulation.body
                    if isinstance(node, ast.FunctionDef) and node.name in ('wallet', 'equity', 'close', 'funding_charge')}
        self.assertEqual(helpers(parent), helpers(root/'propdesk/native_noise_area.py'))

    def test_old_wallet_opening_mark_liquidation_outranks_scheduled_flat(self):
        trades, marks, entry = fixture()
        flat = entry+72
        for s in noise.SYMBOLS:
            marks[s][flat].update(open=40, low=40, high=100.3, close=100.3)
        result = run_fixture(trades, marks)
        self.assertEqual(result['metrics']['opening_mark_gap_liquidation_ambiguity_count'], 2)
        for row in result['trades']:
            self.assertEqual(row['reason'], 'opening_mark_liquidation_ambiguity')
            self.assertEqual(row['recovered_margin'], 0)
            self.assertIsNone(row['pending_known_at'])
            self.assertTrue(row['simultaneous_opening_mark_order_ordering_unverified'])
            self.assertGreater(row['unfunded_isolated_deficit'], 0)

    def test_missing_checkpoint_marks_unknown_update_without_future_skip(self):
        trades, marks, entry = fixture()
        for s in noise.SYMBOLS:
            trades[s][entry+5].update(volume=0, quote_volume=0)
        result = run_fixture(trades, marks)
        self.assertGreater(result['metrics']['unknown_checkpoint_stop_update_count'], 0)
        self.assertEqual(result['trades'][0]['entry_time'], trades['BTCUSDT'][entry]['time'])

    def test_delayed_session_flat_has_unknown_reopening_execution(self):
        trades, marks, entry = fixture()
        flat = entry+72
        for s in noise.SYMBOLS:
            trades[s][flat].update(volume=0, quote_volume=0)
        result = run_fixture(trades, marks)
        self.assertEqual(result['metrics']['reopening_execution_time_unknown_count'], 2)
        for row in result['trades']:
            self.assertEqual(row['exit_time'], trades[row['symbol']][flat+1]['time'])
            self.assertTrue(row['reopening_execution_time_unknown'])

    def test_stop_seen_on_zero_trade_mark_queues_next_genuine_opening(self):
        trades, marks, entry = fixture()
        for s in noise.SYMBOLS:
            trades[s][entry+1].update(volume=0, quote_volume=0)
            marks[s][entry+1].update(low=99)
        result = run_fixture(trades, marks)
        for row in result['trades'][:2]:
            self.assertEqual(row['exit_time'], trades[row['symbol']][entry+2]['time'])
            self.assertEqual(row['reason'], 'completed_mark_stop')
            self.assertTrue(row['reopening_execution_time_unknown'])

    def test_sparse_prior_mark_opening_and_held_risk_remain_flagged(self):
        trades, marks, entry = fixture()
        for s in noise.SYMBOLS:
            marks[s][entry-1]['source_auxiliary_count'] = 2
            marks[s][entry+1]['source_auxiliary_count'] = 1
        result = run_fixture(trades, marks)
        self.assertEqual(result['metrics']['source_sparse_mark_opening_intent_count'], 2)
        self.assertEqual(result['metrics']['source_sparse_mark_held_bar_count'], 2)

    def test_unseen_prior_reference_slot_is_unknown_without_older_replacement(self):
        trades, marks, entry = fixture()
        previous_slot = entry-1-3*288  # Previous Friday has a genuine absent trade.
        for s in noise.SYMBOLS:
            trades[s][previous_slot].update(volume=0, quote_volume=0)
        features = noise.NoiseFeatures(trades, marks)
        self.assertTrue(math.isnan(features.base['BTCUSDT']['sigma'][entry-1]))
        self.assertEqual(features.observations(configuration(checkpoint_minutes=30))['BTCUSDT']['entry'][entry-1],0)


class NativeNoiseArtifactTests(unittest.TestCase):
    def test_full_ledger_bytes_are_immutable_and_raw_tamper_is_rejected(self):
        from scripts import research_native_noise_area as driver
        with TemporaryDirectory() as directory:
            root=Path(directory)
            with patch.object(driver,'ROOT',root),patch.object(driver,'LEDGERS',root/'ledgers'):
                receipt=driver.ledger({'actual_trade_netcash':7},'case')
                self.assertEqual(driver.ledger_read(receipt),{'actual_trade_netcash':7})
                with self.assertRaisesRegex(ValueError,'immutable'):
                    driver.ledger({'actual_trade_netcash':8},'case')
                damaged=dict(receipt,raw_sha256='0'*64)
                with self.assertRaisesRegex(ValueError,'Original noise evidence'):
                    driver.ledger_read(damaged)

    def test_missing_claimed_passing_confirmation_refuses_final(self):
        from scripts import research_native_noise_area as driver
        with TemporaryDirectory() as directory:
            with patch.object(driver,'DIRECTORY',Path(directory)),patch.object(driver,'verify_selection'):
                with self.assertRaisesRegex(ValueError,'Missing claimed immutable'):
                    driver.verify_final_authority({'validation':{'passed':True}})

    def test_failed_or_different_primary_validation_cannot_authorize_final(self):
        from scripts import research_native_noise_area as driver
        report={'selected':'a','validation':{'passed':False,'id':'a'},'confirmation':{},'selection':{}}
        with patch.object(driver,'verify_selection'),patch.object(driver,'read_lock',return_value={}):
            with self.assertRaisesRegex(ValueError,'Passing sole validation'):
                driver.verify_final_authority(report)


if __name__ == '__main__':
    unittest.main()
