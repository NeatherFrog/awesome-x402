from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from propdesk import cross_sectional as engine, research_lab as lab
from scripts import research_cross_sectional as driver


class DriverGuards(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.directory = self.root/'data/cross-sectional-research'
        self.directory.mkdir(parents=True)
        self.patchers = [patch.object(driver, 'ROOT', self.root), patch.object(driver, 'DIRECTORY', self.directory),
                         patch.object(driver, 'verify', return_value=None)]
        for p in self.patchers:
            p.start()
            self.addCleanup(p.stop)
        rows = [{'id': v['id'], 'variant': v, 'passed': i==0, 'target': {'passed': i==0},
                 'score': 1 if i==0 else 0, 'ledgers': {'base': {'test': 1}, 'double_cost': {'test': 2}}}
                for i,v in enumerate(engine.grid())]
        self.report = {'protocol_sha256': 'protocol', 'training': rows, 'selected': rows[0]['id']}
        self.put(self.directory/'training-results.json', rows)
        lock = {'selected': rows[0]['id'], 'training_sha256': lab.digest(rows), 'protocol_sha256': 'protocol',
                'locked_before_validation': True,
                'training_result_file_sha256': driver._sha(self.directory/'training-results.json'),
                'selected_ledger_receipts_sha256': lab.digest(rows[0]['ledgers'])}
        self.put(self.directory/'training-selection.json', lock)
        self.report.update(selection_lock=lock, selection_lock_sha256=lab.digest(lock))

    def put(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, sort_keys=True)+'\n')

    def test_complete_actual_training_and_each_ledger_are_required(self):
        with patch.object(driver, 'verify_recorded_period') as verify_ledger:
            driver.authorization(self.report, 'validation')
            self.assertEqual(verify_ledger.call_count, 72)
        (self.directory/'training-results.json').unlink()
        with self.assertRaises(FileNotFoundError):
            driver.authorization(self.report, 'validation')

    def test_partial_or_changed_actual_results_cannot_authorize(self):
        self.put(self.directory/'training-results.json', self.report['training'][:-1])
        with patch.object(driver, 'verify_recorded_period') as check, self.assertRaises(ValueError):
            driver.authorization(self.report, 'validation')
        check.assert_not_called()

    def test_missing_claimed_confirmation_is_not_repaired(self):
        self.report['confirmation_lock'] = {'claimed': True}
        with patch.object(driver, 'verify_recorded_period'), self.assertRaises(FileNotFoundError):
            driver.authorization(self.report, 'final')
        self.assertFalse((self.directory/'validation-confirmation.json').exists())

    def test_changed_actual_validation_cannot_authorize_final(self):
        validation = deepcopy(self.report['training'][0])
        self.report['validation'] = validation
        self.put(self.directory/'validation-result.json', validation)
        lock = {'protocol_sha256': 'protocol', 'selection_lock_sha256': self.report['selection_lock_sha256'],
                'validation_sha256': lab.digest(validation), 'selected': self.report['selected'],
                'locked_before_final': True,
                'validation_result_file_sha256': driver._sha(self.directory/'validation-result.json'),
                'selected_ledger_receipts_sha256': lab.digest(validation['ledgers'])}
        self.put(self.directory/'validation-confirmation.json', lock)
        self.report.update(confirmation_lock=lock, confirmation_lock_sha256=lab.digest(lock))
        with patch.object(driver, 'verify_recorded_period'), patch.object(driver, 'verify_validation_source_lock'):
            driver.authorization(self.report, 'final')
        self.put(self.directory/'validation-result.json', {**validation, 'passed': False})
        with patch.object(driver, 'verify_recorded_period'), patch.object(driver, 'verify_validation_source_lock'), self.assertRaises(ValueError):
            driver.authorization(self.report, 'final')

    def test_changed_validation_original_is_rejected_before_final_source_acquisition(self):
        root = self.root/'.local/cross-sectional-validation-v1'
        rows = []
        for s in engine.SYMBOLS:
            for k in driver.source.KINDS:
                name = s+'-'+k+'.json'
                self.put(root/name, [])
                rows.append({'symbol':s,'kind':k,'json':name,'json_sha256':driver._sha(root/name),
                             'sources':[{'raw_file':'raw.zip','checksum_file':'raw.CHECKSUM'}]})
        (root/'raw.zip').write_bytes(b'original')
        (root/'raw.CHECKSUM').write_bytes(b'checksum')
        self.put(root/'manifest.json', {'datasets':rows})
        self.put(root/'protocol.json', {'test':'immutable'})
        lock = {'research_protocol_sha256':'protocol','manifest_sha256':driver._sha(root/'manifest.json'),
                'source_protocol_file_sha256':driver._sha(root/'protocol.json'),
                'canonical_sources':{r['symbol']+'/'+r['kind']:r['json_sha256'] for r in rows},
                'originals':{'raw.zip':driver._sha(root/'raw.zip'),'raw.CHECKSUM':driver._sha(root/'raw.CHECKSUM')}}
        path = self.directory/'input-lock-cross-sectional-validation-v1.json'
        self.put(path,lock)
        self.report['confirmation_lock']={'validation_input_lock_file_sha256':driver._sha(path)}
        with patch.object(driver,'_stage_identity',return_value=({'datasets':rows},[],None,None)):
            driver.verify_validation_source_lock(self.report)
            (root/'raw.zip').write_bytes(b'changed')
            with self.assertRaises(ValueError):
                driver.verify_validation_source_lock(self.report)

    def test_invalid_role_cannot_acquire_holdout(self):
        with patch.object(driver.source, 'fetch_archive') as fetch, self.assertRaises(ValueError):
            driver.acquire_stage(self.report, 'confirmation')
        fetch.assert_not_called()

    def test_existing_stage_must_match_context_before_reuse(self):
        stage = self.root/'.local/cross-sectional-validation-v1'
        protocol = {'data_protocol_id': 'cross-sectional-hourly-validation-v1',
                    'symbols': list(engine.SYMBOLS), 'source_kinds': list(driver.source.KINDS),
                    'year': 2025, 'months': list(range(1,13)), 'authorized_primary': self.report['selected'],
                    'research_protocol_sha256': 'protocol', 'selection_lock_sha256': self.report['selection_lock_sha256']}
        self.put(stage/'protocol.json', protocol)
        self.put(stage/'manifest.json', {'protocol_sha256': driver._sha(stage/'protocol.json')})
        with patch.object(driver, 'authorization'):
            self.assertEqual(driver.acquire_stage(self.report, 'validation'), stage)
        protocol['months'].pop()
        self.put(stage/'protocol.json', protocol)
        self.put(stage/'manifest.json', {'protocol_sha256': driver._sha(stage/'protocol.json')})
        with patch.object(driver, 'authorization'), patch.object(driver.source, 'fetch_archive') as fetch, self.assertRaises(ValueError):
            driver.acquire_stage(self.report, 'validation')
        fetch.assert_not_called()

    def test_final_stage_must_bind_actual_confirmation(self):
        stage = self.root/'.local/cross-sectional-final-v1'
        protocol = {'data_protocol_id': 'cross-sectional-hourly-final-v1',
                    'symbols': list(engine.SYMBOLS), 'source_kinds': list(driver.source.KINDS),
                    'year': 2026, 'months': list(range(1,10)), 'authorized_primary': self.report['selected'],
                    'research_protocol_sha256': 'protocol', 'selection_lock_sha256': self.report['selection_lock_sha256'],
                    'confirmation_lock_sha256': 'wrong'}
        self.report['confirmation_lock_sha256'] = 'actual'
        self.put(stage/'protocol.json', protocol)
        self.put(stage/'manifest.json', {'protocol_sha256': driver._sha(stage/'protocol.json')})
        with self.assertRaises(ValueError):
            driver._stage_identity(stage, 'final', self.report)

    def test_actual_gzip_and_raw_ledger_are_verified(self):
        v = engine.grid()[0]
        row = {'id': v['id'], 'variant': v, 'metrics': {'return_pct': 1}, 'stress_metrics': {'return_pct': -1}, 'ledgers': {}}
        for case,suffix,key in [('base','base','metrics'),('double_cost','double-cost','stress_metrics')]:
            raw = json.dumps({'variant':v,'metrics':row[key]}).encode()
            packed = gzip.compress(raw, mtime=0)
            name = '.local/cross-sectional-research/training-'+v['id']+'-'+suffix+'.json.gz'
            path = self.root/name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(packed)
            row['ledgers'][case] = {'path':name,'gzip_sha256':hashlib.sha256(packed).hexdigest(),
                                    'raw_sha256':hashlib.sha256(raw).hexdigest()}
        driver.verify_recorded_period(row, 'training')
        path.write_bytes(packed+b'changed')
        with self.assertRaises(ValueError):
            driver.verify_recorded_period(row, 'training')


if __name__=='__main__':
    unittest.main()
