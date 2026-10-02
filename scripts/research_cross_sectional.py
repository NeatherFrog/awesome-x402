#!/usr/bin/env python3
"""Preregistered72 current-survivor momentum adaptations; no order API."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from propdesk import cross_sectional as engine, cross_sectional_data as source
from propdesk import research_lab as lab, research_stats as stats, target_evaluation as target, market
from scripts import research_broad as shared

DIRECTORY = ROOT/'data/cross-sectional-research'
TRAIN_SOURCE = ROOT/'.local/cross-sectional-training-v1'
OUTPUT = ROOT/'docs/cross-sectional-research.json'
MARKDOWN = ROOT/'docs/CROSS_SECTIONAL_RESEARCH.md'
WINDOWS = {'training': ['2024-01-01', '2025-01-01'], 'validation': ['2025-01-01', '2026-01-01'],
           'final': ['2026-01-01', '2026-10-01']}
COMMON_SHA = '5495a0683efeb6da230cf454b71c8e8ae952dc03534d23f3cedbcd9f56e9e839'
TRAIN_MANIFEST_SHA = '7345f51f6733f1d3b62e3c911f5fcafed45940eb2951456d3cd8aca4fd106d5c'
TRAIN_DATA_PROTOCOL_SHA = '21ad25b060d9f88909c7e1a5cf48ce9065bece325e85c3efd033004df3a95a92'
PAPER_SHA = '01fa7e448623627078b43cc75ca70471caa1c436e48795f12704106392b486f2'


class IncompleteStage(ValueError):
    pass


def _sha(path):
    return shared.file_hash(path)


def write(report):
    OUTPUT.write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    lines = ['# Current-survivor cross-sectional crypto research', '',
             'Phase: **'+report['phase']+'**.', '', 'Protocol SHA256: `'+report['protocol_sha256']+'`.', '',
             '72 registered adaptations across eleven current-survivor assets. Official trade1h, calculated mark1h, and realized funding; conservative FTMO-inspired6.5bps commission PER SIDE,2bps slippage,1bp full spread,all doubled for stress; TOTAL$100,000,physical1x. Perpetual funding is not an FTMO swap. This is not historical FTMO eligibility or an unbiased historical universe.', '']
    rows = report.get('training', [])
    lines += [f'TRAIN: **{len(rows)}/72** completed configurations; **{sum(r["passed"] for r in rows)}** eligible.', '']
    if rows:
        lines += ['| ID | Net % | Double costs % | Asset episodes | Eligible |', '|---|---:|---:|---:|---|']
        for r in sorted(rows, key=lambda r: (-r['metrics']['return_pct'], r['id']))[:5]:
            lines.append(f'| {r["id"]} | {r["metrics"]["return_pct"]:+.4f} | {r["stress_metrics"]["return_pct"]:+.4f} | {r["metrics"]["trade_count"]} | {r["passed"]} |')
        lines += ['', 'Rows are descriptive. An immutable ONE-primary lock controls all later evaluation.', '']
    if report.get('reason'):
        lines += [report['reason'], '']
    for role in ('validation', 'final'):
        if role in report:
            r = report[role]
            lines += [f'{role.capitalize()} fixed primary: net **{r["metrics"]["return_pct"]:+.4f}%**, double costs **{r["stress_metrics"]["return_pct"]:+.4f}%**, passed **{r["target"]["passed"]}**.', '']
    lines += ['All evaluated full base/double ledgers are retained locally with gzip/raw hashes. Partial close slices are grouped into completed asset-position episodes; correlated constituent exits are not independent bets. Inference uses aggregate calendar-day portfolio blocks. Risk envelopes conservatively include possible old/new intrahour overlap. Mark/swap/filters/execution timing, FTMO contract and production licensing remain unverified; no orders or Telegram.', '']
    MARKDOWN.write_text('\n'.join(lines))


def freeze():
    path = DIRECTORY/'protocol.json'
    if path.exists():
        protocol = json.loads(path.read_text())
    else:
        if (_sha(ROOT/'docs/EIGHT_PERCENT_PROTOCOL.json') != COMMON_SHA
                or _sha(TRAIN_SOURCE/'manifest.json') != TRAIN_MANIFEST_SHA
                or _sha(TRAIN_SOURCE/'protocol.json') != TRAIN_DATA_PROTOCOL_SHA
                or _sha(ROOT/'.local/original-intraday-4f486d93a08d/liu_tsyvinski_wu_common_crypto_original.pdf') != PAPER_SHA):
            raise ValueError('Immutable common/source protocol identity differs')
        manifest = json.loads((TRAIN_SOURCE/'manifest.json').read_text())
        inputs = [TRAIN_SOURCE/'manifest.json', TRAIN_SOURCE/'protocol.json',
                  ROOT/'.local/prop-research/2026-10-02T10-37-13Z/ftmo_public_symbols.raw',
                  ROOT/'.local/original-intraday-4f486d93a08d/receipts.json',
                  ROOT/'.local/original-intraday-4f486d93a08d/liu_tsyvinski_wu_common_crypto_original.pdf']
        for row in manifest['datasets']:
            inputs.append(TRAIN_SOURCE/row['json'])
            for receipt in row['sources']:
                inputs += [TRAIN_SOURCE/receipt['raw_file'], TRAIN_SOURCE/receipt['checksum_file']]
        producers = ('propdesk/cross_sectional.py', 'propdesk/cross_sectional_data.py',
                     'scripts/research_cross_sectional.py', 'scripts/download_cross_sectional.py',
                     'tests/test_cross_sectional.py', 'tests/test_cross_sectional_data.py',
                     'tests/test_cross_sectional_driver.py',
                     'propdesk/target_evaluation.py', 'propdesk/research_stats.py',
                     'propdesk/research_lab.py', 'propdesk/market.py', 'propdesk/funding_data.py',
                     'propdesk/exchange.py', 'scripts/research_broad.py')
        protocol = {'schema': 1, 'id': 'current-survivor-cross-sectional-momentum-v1',
                    'frozen_at': shared.now(), 'grid': engine.grid(), 'windows': WINDOWS,
                    'human_protocol_path': 'docs/CROSS_SECTIONAL_PROTOCOL.md',
                    'human_protocol_sha256': _sha(ROOT/'docs/CROSS_SECTIONAL_PROTOCOL.md'),
                    'design_sha256': _sha(ROOT/'docs/CROSS_SECTIONAL_DESIGN.md'),
                    'common_objective_sha256': COMMON_SHA,
                    'source_manifest_sha256': TRAIN_MANIFEST_SHA,
                    'source_protocol_sha256': TRAIN_DATA_PROTOCOL_SHA,
                    'original_paper_pdf_sha256': PAPER_SHA,
                    'producers': {p: _sha(ROOT/p) for p in producers},
                    'inputs': {str(p.relative_to(ROOT)): _sha(p) for p in inputs},
                    'research_only': True, 'survivorship_conditioned': True,
                    'actual_prop_eligibility_verified': False, 'live_orders': False,
                    'selection': 'Exact72 TRAIN base/double; common30episodes/60days/positive net+stress/10%DD/5%daily plus all source/cash/liq/reconciliation guards. ONE highest net/max(adverseDD,.25%) tie ID locked before2025; unchanged8%monthly/60episodes/CI99/fullmonths/median/bothhalf gates before2026. No primary replacement.',
                    'funding': 'Actual settlement outcome, causal7-day persistence estimate only for financing-rank family. Computed hourly mark proxy is not exact settlement mark. Possible late-hour exit debit retained once; uncertain credit omitted. Never finance an earlier order with a future rate.',
                    'future_data': 'Only after ONE passing TRAIN lock acquire full2025 elevenasset trade/mark/funding monthly originals; only after passingvalidation confirmation acquire2026JanSep. Monthly failures reject whole stage; no shorter prefix/asset subset/delisted omission.',
                    'capital': 'Physical100k,1x fullyreservedlegcollateral+entryfees,perasset.35 current/initial ceiling,jointpre-exit reservations; no hidden credit/topups/reuse unverified same-hour closingcash. Lotstep.001 is explicit proxy, not verifiedFTMOcontract filter.',
                    'counts': '72 extra correlated adaptations after prior studies. Full failed base/double ledgers retained. Assetposition episodes grouped across partials count activity, not independent experiments; CI uses portfolio calendar blocks.',
                    'limits': 'Current-survivor universe and prior inspectedyears adaptive. Source personalnonproductionCC-BY-NC-SA; CFDswap/session/contracts/USDTparity/pointmark/MMtier/actualfills unverified. No actualpayout/live/Telegram proof.'}
        shared.immutable_write(path, protocol)
    if OUTPUT.exists():
        return json.loads(OUTPUT.read_text())
    report = {'phase': 'frozen_before_outcomes', 'protocol': protocol, 'protocol_sha256': lab.digest(protocol),
              'retrospective_target_candidate': False, 'live_qualified': False,
              'prop_qualified': False, 'telegram_enabled': False}
    write(report)
    return report


def verify(report):
    p = report['protocol']
    if (p != json.loads((DIRECTORY/'protocol.json').read_text()) or lab.digest(p) != report['protocol_sha256']
            or p['grid'] != engine.grid() or p.get('windows') != WINDOWS
            or p.get('common_objective_sha256') != COMMON_SHA
            or p.get('source_manifest_sha256') != TRAIN_MANIFEST_SHA
            or p.get('source_protocol_sha256') != TRAIN_DATA_PROTOCOL_SHA
            or _sha(ROOT/'docs/EIGHT_PERCENT_PROTOCOL.json') != COMMON_SHA
            or _sha(ROOT/p['human_protocol_path']) != p['human_protocol_sha256']
            or _sha(ROOT/'docs/CROSS_SECTIONAL_DESIGN.md') != p['design_sha256']):
        raise ValueError('Frozen cross-sectional specification differs')
    for kind in ('inputs', 'producers'):
        for name, expected in p[kind].items():
            if _sha(ROOT/name) != expected:
                raise ValueError('Frozen '+kind+' changed: '+name)


def _stage_identity(root, role='training', report=None):
    if role not in ('training', 'validation', 'final'):
        raise ValueError('Only registered TRAIN/validation/FINAL source stages are allowed')
    manifest = json.loads((root/'manifest.json').read_text())
    protocol = json.loads((root/'protocol.json').read_text())
    if manifest.get('protocol_sha256') != _sha(root/'protocol.json'):
        raise ValueError('Stage source protocol bytes changed')
    if protocol.get('symbols') != list(engine.SYMBOLS) or protocol.get('source_kinds') != list(source.KINDS):
        raise ValueError('Stage source protocol cohort/kinds differ')
    if role == 'training':
        months = [(2023, 12)]+[(2024, m) for m in range(1, 13)]
        first, finish = '2023-12-01T00:00:00Z', '2025-01-01T00:00:00Z'
        if protocol.get('start') != first or protocol.get('end_exclusive') != finish:
            raise ValueError('TRAIN source protocol calendar differs')
    else:
        year = 2025 if role == 'validation' else 2026
        months = [(year, m) for m in range(1, 13 if role=='validation' else 10)]
        first, finish = WINDOWS[role][0]+'T00:00:00Z', WINDOWS[role][1]+'T00:00:00Z'
        if (report is None or protocol.get('year') != year or protocol.get('months') != [m for _,m in months]
                or protocol.get('data_protocol_id') != 'cross-sectional-hourly-'+role+'-v1'
                or protocol.get('authorized_primary') != report.get('selected')
                or protocol.get('research_protocol_sha256') != report.get('protocol_sha256')
                or protocol.get('selection_lock_sha256') != report.get('selection_lock_sha256')):
            raise ValueError('OOS source protocol authorization/calendar differs')
        if role=='final' and protocol.get('confirmation_lock_sha256') != report.get('confirmation_lock_sha256'):
            raise ValueError('FINAL source protocol passing-confirmation differs')
    return manifest, months, first, finish


def load_sources(root, role='training', report=None):
    manifest, months, first, finish = _stage_identity(root, role, report)
    required = {(s, k) for s in engine.SYMBOLS for k in source.KINDS}
    if ({(r['symbol'], r['kind']) for r in manifest['datasets']} != required
            or len(manifest['datasets']) != 33 or manifest['all_requested_sources_complete'] is not True):
        raise IncompleteStage('Complete exact11 assets/three source kinds required; no prefix performance')
    result = {kind: {} for kind in source.KINDS}
    for row in manifest['datasets']:
        if [(r['year'], r['month']) for r in row['sources']] != months:
            raise ValueError('Exact requested original source months required')
        if row['failures'] or row['complete_calendar'] is not True or _sha(root/row['json']) != row['json_sha256']:
            raise ValueError('Requested stage has incomplete or changed source bytes')
        values = json.loads((root/row['json']).read_text())
        if source.digest(values) != row['data_fingerprint']:
            raise ValueError('Canonical source fingerprint differs')
        rebuilt = []
        for receipt in row['sources']:
            raw_path, sum_path = root/receipt['raw_file'], root/receipt['checksum_file']
            if (_sha(raw_path) != receipt['zip_sha256'] or _sha(sum_path) != receipt['checksum_sha256']):
                raise ValueError('Original stage archive/checksum bytes changed')
            parsed, actual = source.parse_archive(raw_path.read_bytes(), sum_path.read_bytes(), row['symbol'], row['kind'],
                                                  receipt['year'], receipt['month'])
            if any(receipt.get(k) != v for k, v in actual.items()):
                raise ValueError('Official archive receipt identity differs')
            rebuilt.extend(parsed)
        if rebuilt != values:
            raise ValueError('Canonical data differs from its original source rows')
        if row['rows'] != len(values):
            raise ValueError('Recorded canonical source row count differs')
        if row['kind'] == 'fundingRate':
            source.validate_funding(values)
        else:
            count = int((market.utc_datetime(finish)-market.utc_datetime(first)).total_seconds()/3600)
            if len(values) != count or values[0]['time'] != first or values[-1]['known_at'] != finish:
                raise ValueError('Exact complete source hour endpoints/calendar required')
        result[row['kind']][row['symbol']] = values
    return result


def verify_recorded_period(row, role):
    if row.get('variant') not in engine.grid() or row.get('id') != row['variant']['id']:
        raise ValueError('Retained period variant differs from catalogue')
    for label, suffix, metrics in (('base', 'base', 'metrics'), ('double_cost', 'double-cost', 'stress_metrics')):
        receipt = row['ledgers'][label]
        expected = '.local/cross-sectional-research/'+role+'-'+row['id']+'-'+suffix+'.json.gz'
        if receipt.get('path') != expected:
            raise ValueError('Retained period ledger path differs')
        packed = (ROOT/expected).read_bytes()
        if hashlib.sha256(packed).hexdigest() != receipt['gzip_sha256']:
            raise ValueError('Retained gzip ledger bytes differ')
        raw = gzip.decompress(packed)
        if hashlib.sha256(raw).hexdigest() != receipt['raw_sha256']:
            raise ValueError('Retained raw ledger bytes differ')
        ledger = json.loads(raw)
        if ledger['variant'] != row['variant'] or ledger['metrics'] != row[metrics]:
            raise ValueError('Retained ledger result differs from selected report')


def verify_validation_source_lock(report):
    root = ROOT/'.local/cross-sectional-validation-v1'
    path = DIRECTORY/'input-lock-cross-sectional-validation-v1.json'
    lock = json.loads(path.read_text())
    manifest, _, _, _ = _stage_identity(root, 'validation', report)
    if (lock.get('research_protocol_sha256') != report['protocol_sha256']
            or lock.get('manifest_sha256') != _sha(root/'manifest.json')
            or lock.get('source_protocol_file_sha256') != _sha(root/'protocol.json')
            or report['confirmation_lock'].get('validation_input_lock_file_sha256') != _sha(path)):
        raise ValueError('Immutable validation source lock differs before FINAL acquisition')
    expected = {r['symbol']+'/'+r['kind']: r['json_sha256'] for r in manifest['datasets']}
    if expected != lock.get('canonical_sources') or len(expected) != 33:
        raise ValueError('Validation canonical cohort lock differs')
    for row in manifest['datasets']:
        if _sha(root/row['json']) != row['json_sha256']:
            raise ValueError('Validation canonical source bytes changed before FINAL')
    originals = {src[field]: _sha(root/src[field]) for row in manifest['datasets'] for src in row['sources']
                 for field in ('raw_file', 'checksum_file')}
    if originals != lock.get('originals'):
        raise ValueError('Validation original source bytes changed before FINAL')


def authorization(report, role):
    if role not in ('validation', 'final'):
        raise ValueError('Only registered validation/FINAL acquisition is allowed')
    selection = json.loads((DIRECTORY/'training-selection.json').read_text())
    actual_training = json.loads((DIRECTORY/'training-results.json').read_text())
    if (actual_training != report.get('training') or len(actual_training) != 72
            or [r['variant'] for r in actual_training] != engine.grid()
            or selection.get('training_result_file_sha256') != _sha(DIRECTORY/'training-results.json')):
        raise ValueError('Immutable exact complete TRAIN results required')
    candidates = [r for r in report.get('training', []) if r.get('id') == report.get('selected')]
    eligible = sorted((r for r in actual_training if r['passed']), key=lambda r:(-r['score'],r['id']))
    if not eligible or eligible[0]['id'] != report.get('selected'):
        raise ValueError('Highest-score immutable ONE passing primary required')
    if (len(candidates) != 1 or not candidates[0]['passed'] or not candidates[0]['target']['passed']
            or selection != report.get('selection_lock') or lab.digest(selection) != report.get('selection_lock_sha256')
            or selection.get('protocol_sha256') != report['protocol_sha256']
            or selection.get('training_sha256') != lab.digest(report.get('training'))
            or selection.get('selected') != report.get('selected') or selection.get('locked_before_validation') is not True):
        raise ValueError('Existing immutable ONE passing primary lock required')
    for row in actual_training:
        verify_recorded_period(row, 'training')
    if selection.get('selected_ledger_receipts_sha256') != lab.digest(candidates[0]['ledgers']):
        raise ValueError('Selected TRAIN ledger receipts changed')
    if role == 'final':
        confirmation = json.loads((DIRECTORY/'validation-confirmation.json').read_text())
        validation = report.get('validation', {})
        if (confirmation != report.get('confirmation_lock') or lab.digest(confirmation) != report.get('confirmation_lock_sha256')
                or confirmation.get('protocol_sha256') != report['protocol_sha256']
                or confirmation.get('selection_lock_sha256') != report.get('selection_lock_sha256')
                or confirmation.get('validation_sha256') != lab.digest(validation)
                or confirmation.get('selected') != report.get('selected') or confirmation.get('locked_before_final') is not True
                or validation.get('target', {}).get('passed') is not True
                or validation.get('passed') is not True
                or validation.get('variant', {}).get('id') != report.get('selected')):
            raise ValueError('Existing passing-validation confirmation required before FINAL')
        if (json.loads((DIRECTORY/'validation-result.json').read_text()) != validation
                or confirmation.get('validation_result_file_sha256') != _sha(DIRECTORY/'validation-result.json')
                or confirmation.get('selected_ledger_receipts_sha256') != lab.digest(validation['ledgers'])):
            raise ValueError('Immutable passing-validation result/ledger binding required')
        verify_recorded_period(validation, 'validation')
        verify_validation_source_lock(report)
    verify(report)


def acquire_stage(report, role):
    authorization(report, role)
    root = ROOT/'.local'/('cross-sectional-'+role+'-v1')
    if (root/'manifest.json').exists():
        _stage_identity(root, role, report)
        return root
    root.mkdir(parents=True, exist_ok=True)
    year = 2025 if role == 'validation' else 2026
    months = range(1, 13 if role == 'validation' else 10)
    protocol = {'data_protocol_id': 'cross-sectional-hourly-'+role+'-v1', 'symbols': list(engine.SYMBOLS),
                'source_kinds': list(source.KINDS), 'year': year, 'months': list(months),
                'authorized_primary': report['selected'], 'research_protocol_sha256': report['protocol_sha256'],
                'selection_lock_sha256': report['selection_lock_sha256'], 'live_orders': False}
    if role=='final':
        protocol['confirmation_lock_sha256'] = report['confirmation_lock_sha256']
    shared.immutable_write(root/'protocol.json', protocol)
    def chunk(s, k, month):
        try:
            rows, receipt = source.fetch_archive(s, k, year, month, root/'raw')
            return rows, receipt, None
        except (ValueError, OSError) as exc:
            return [], None, {'symbol': s, 'kind': k, 'year': year, 'month': month, 'error': str(exc)}
    parts = {}
    with ThreadPoolExecutor(max_workers=6) as pool:
        jobs = {pool.submit(chunk, s, k, m): (s, k, m) for s in engine.SYMBOLS for k in source.KINDS for m in months}
        for future in as_completed(jobs):
            parts[jobs[future]] = future.result()
    datasets = []
    for s in engine.SYMBOLS:
        for k in source.KINDS:
            values, receipts, errors = [], [], []
            for m in months:
                rows, receipt, error = parts[s, k, m]
                values.extend(rows)
                if receipt:
                    receipts.append(receipt)
                if error:
                    errors.append(error)
            row = {'symbol': s, 'kind': k, 'sources': receipts, 'failures': errors,
                   'complete_calendar': not errors, 'json': None, 'rows': len(values)}
            if not errors:
                if k == 'fundingRate':
                    source.validate_funding(values)
                path = root/(s+'-'+k+'.json')
                shared.immutable_write(path, values)
                row.update(json=path.name, json_sha256=_sha(path), data_fingerprint=source.digest(values))
            datasets.append(row)
    manifest = {'schema': 1, 'protocol_sha256': _sha(root/'protocol.json'), 'datasets': datasets,
                'all_requested_sources_complete': all(r['complete_calendar'] for r in datasets),
                'data_license': 'CC-BY-NC-SA-4.0', 'live_orders': False}
    shared.immutable_write(root/'manifest.json', manifest)
    return root


def features_for(report, role):
    all_sources = load_sources(TRAIN_SOURCE)
    roots = []
    if role in ('validation', 'final'):
        roots.append(acquire_stage(report, 'validation'))
    if role == 'final':
        roots.append(acquire_stage(report, 'final'))
    for root in roots:
        source_role = 'validation' if root.name=='cross-sectional-validation-v1' else 'final'
        more = load_sources(root, source_role, report)
        for k in source.KINDS:
            for s in engine.SYMBOLS:
                all_sources[k][s].extend(more[k][s])
    for root in [TRAIN_SOURCE]+roots:
        manifest = json.loads((root/'manifest.json').read_text())
        lock = {'research_protocol_sha256': report['protocol_sha256'], 'manifest_sha256': _sha(root/'manifest.json'),
                'source_protocol_file_sha256': _sha(root/'protocol.json'),
                'canonical_sources': {r['symbol']+'/'+r['kind']: r['json_sha256'] for r in manifest['datasets']},
                'originals': {src[field]: _sha(root/src[field]) for r in manifest['datasets'] for src in r['sources']
                              for field in ('raw_file', 'checksum_file')}}
        shared.immutable_write(DIRECTORY/('input-lock-'+root.name+'.json'), lock)
    return engine.Features(all_sources['klines'], all_sources['markPriceKlines'], all_sources['fundingRate'])


def evaluate(base, stress, role, seed):
    if base['metrics']['account_insolvent'] or stress['metrics']['account_insolvent']:
        return {'role': role, 'passed': False, 'checks': {'positive_finite_total_account_equity': False},
                'status': 'not_qualified', 'base': {'geometric_monthly_return': None},
                'double_cost_stress': {'geometric_monthly_return': None},
                'selection_score_net_return_over_drawdown': -1e12, 'live_orders': False}
    rows, stressed = base['daily_curve'], stress['daily_curve']
    checked = target.evaluate_period([r['time'] for r in rows], [r['return'] for r in rows],
                                    [r['return'] for r in stressed], base['metrics']['trade_count'],
                                    daily_worst_equity=[r['worst_equity'] for r in rows],
                                    daily_peak_equity=[r['best_equity'] for r in rows],
                                    period_start=WINDOWS[role][0], period_end_exclusive=WINDOWS[role][1],
                                    role=role, samples=5000, seed=seed)
    for label, result in (('base', base), ('double_cost', stress)):
        m = result['metrics']
        checked['checks'].update({label+'_no_liquidation': m['liquidation_count']==0,
            label+'_no_unfunded_deficit': m['unfunded_isolated_deficit']==0,
            label+'_no_missing_trade_exposure': m['unresolved_zero_trade_exposure_bars']==0,
            label+'_no_unknown_reopening_exit': m['unknown_reopening_exit_count']==0,
            label+'_no_sparse_mark_exposure': m['sparse_mark_exposure_bars']==0,
            label+'_no_sparse_known_mark_intents': m['sparse_known_mark_opening_intents']==0,
            label+'_no_retrospective_entry_gross_breach': m['retrospective_entry_union_gross_breaches']==0,
            label+'_no_retrospective_entry_stop_risk_breach': m['retrospective_entry_union_stop_risk_breaches']==0,
            label+'_fully_flat_boundary': m['remaining_positions']==0,
            label+'_cash_nonnegative': m['minimum_available_cash']>=-1e-7,
            label+'_account_pnl_reconciled': m['account_pnl_reconciliation_error']<1e-7})
    checked['passed'] = all(checked['checks'].values())
    checked['status'] = 'historical_survivor_conditioned_reference_screen_passed' if checked['passed'] else 'not_qualified'
    return checked


def save_ledger(result, role, case):
    path = ROOT/'.local/cross-sectional-research'/(role+'-'+result['variant']['id']+'-'+case+'.json.gz')
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(result, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    packed = gzip.compress(raw, mtime=0)
    if path.exists() and path.read_bytes() != packed:
        raise ValueError('Immutable evaluated ledger changed')
    if not path.exists():
        with path.open('xb') as stream:
            stream.write(packed)
    return {'path': str(path.relative_to(ROOT)), 'gzip_sha256': _sha(path),
            'raw_sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(packed)}


def relationships(result, features):
    if result['metrics']['account_insolvent']:
        return {'not_defined': 'Account insolvency makes daily return inference undefined.'}
    indices = [int((market.utc_datetime(r['time']+'T00:00:00Z').timestamp()-features.epochs[0])/86400) for r in result['daily_curve']]
    returns = [r['return'] for r in result['daily_curve']]
    benchmarks = {s: [features.daily[s]['close'][i]/features.daily[s]['close'][i-1]-1 for i in indices] for s in engine.SYMBOLS}
    benchmarks['equal_weight_eleven'] = [math.fsum(benchmarks[s][j] for s in engine.SYMBOLS)/11 for j in range(len(indices))]
    report = {}
    mean = math.fsum(returns)/len(returns)
    for s in ('BTCUSDT', 'ETHUSDT', 'equal_weight_eleven'):
        values = benchmarks[s]
        average = math.fsum(values)/len(values)
        var = math.fsum((v-average)**2 for v in values)
        beta = math.fsum((x-average)*(y-mean) for x, y in zip(values, returns))/var if var else None
        report[s] = {'daily_correlation': stats.pearson_correlation(returns, values), 'daily_ols_beta': beta,
                     'mean_daily_residual': mean-beta*average if beta is not None else None,
                     'benchmark_scope': 'Gross daily traded-close price reference; not a costed investable benchmark or causal proof.'}
    return report


def period(v, features, role, seed):
    base = engine.simulate(features, v, *WINDOWS[role])
    stress = engine.simulate(features, v, *WINDOWS[role], cost_multiplier=2)
    assessed = evaluate(base, stress, role, seed)
    return {'id': v['id'], 'variant': v, 'metrics': base['metrics'], 'stress_metrics': stress['metrics'],
            'target': assessed, 'passed': assessed['passed'], 'score': assessed['selection_score_net_return_over_drawdown'],
            'relationships': relationships(base, features),
            'ledgers': {'base': save_ledger(base, role, 'base'), 'double_cost': save_ledger(stress, role, 'double-cost')}}


def run():
    report = freeze()
    verify(report)
    if 'confirmation_lock' in report or 'final' in report:
        authorization(report, 'final')
    if report['phase'].startswith('completed_'):
        return report
    variants = report['protocol']['grid']
    training = report.setdefault('training', [])
    if len(training)>72 or any(r['variant'] != v or r['id'] != v['id'] for r, v in zip(training, variants)):
        raise ValueError('Resume requires the exact complete registered prefix')
    features = features_for(report, 'training')
    for index in range(len(training), 72):
        row = period(variants[index], features, 'training', 20261301+index)
        training.append(row)
        report['phase'] = 'training_in_progress'
        write(report)
        print('CROSS TRAIN', index+1, row['id'], row['metrics']['return_pct'], row['stress_metrics']['return_pct'], row['passed'], flush=True)
    eligible = [r for r in training if r['passed']]
    selected = sorted(eligible, key=lambda r: (-r['score'], r['id']))[0]['id'] if eligible else None
    shared.immutable_write(DIRECTORY/'training-results.json', training)
    chosen = next((r for r in training if r['id']==selected), None)
    lock = {'locked_at': shared.now(), 'locked_before_validation': True, 'protocol_sha256': report['protocol_sha256'],
            'training_sha256': lab.digest(training), 'selected': selected,
            'training_result_file_sha256': _sha(DIRECTORY/'training-results.json'),
            'selected_ledger_receipts_sha256': lab.digest(chosen['ledgers']) if chosen else None}
    lock_path = DIRECTORY/'training-selection.json'
    if lock_path.exists():
        lock = json.loads(lock_path.read_text())
        if lock['selected'] != selected or lock['training_sha256'] != lab.digest(training) or lock['protocol_sha256'] != report['protocol_sha256']:
            raise ValueError('Existing immutable ONE primary selection changed')
    else:
        shared.immutable_write(lock_path, lock)
    report.update(selected=selected, selection_lock=lock, selection_lock_sha256=lab.digest(lock))
    write(report)
    if selected is None:
        report.update(phase='completed_no_training_candidate', reason='No registered configuration passed all frozen TRAIN gates. No new-cohort 2025/2026 performance or substitute.')
        write(report)
        return report
    v = next(v for v in variants if v['id']==selected)
    authorization(report, 'validation')
    if 'validation' not in report:
        report['phase'] = 'validation_in_progress'
        write(report)
        try:
            features = features_for(report, 'validation')
        except IncompleteStage as exc:
            report.update(phase='completed_source_blocked_before_validation', reason=str(exc))
            write(report)
            return report
        report['validation'] = period(v, features, 'validation', 20261390)
        shared.immutable_write(DIRECTORY/'validation-result.json', report['validation'])
        write(report)
    if not report['validation']['passed'] or report['validation']['target']['passed'] is not True:
        report.update(phase='completed_validation_failed', reason='ONE locked primary failed validation. No replacement, rescaling, or new-cohort 2026 performance.')
        write(report)
        return report
    if 'confirmation_lock' not in report:
        confirmation = {'locked_at': shared.now(), 'locked_before_final': True, 'protocol_sha256': report['protocol_sha256'],
                        'selection_lock_sha256': report['selection_lock_sha256'],
                        'validation_sha256': lab.digest(report['validation']), 'selected': selected,
                        'validation_result_file_sha256': _sha(DIRECTORY/'validation-result.json'),
                        'validation_input_lock_file_sha256': _sha(DIRECTORY/'input-lock-cross-sectional-validation-v1.json'),
                        'selected_ledger_receipts_sha256': lab.digest(report['validation']['ledgers'])}
        shared.immutable_write(DIRECTORY/'validation-confirmation.json', confirmation)
        report.update(confirmation_lock=confirmation, confirmation_lock_sha256=lab.digest(confirmation))
        write(report)
    authorization(report, 'final')
    if 'final' not in report:
        report['phase'] = 'final_in_progress'
        write(report)
        try:
            features = features_for(report, 'final')
        except IncompleteStage as exc:
            report.update(phase='completed_source_blocked_before_final', reason=str(exc))
            write(report)
            return report
        report['final'] = period(v, features, 'final', 20261391)
    report.update(phase='completed', retrospective_target_candidate=report['final']['passed'])
    write(report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--freeze', action='store_true')
    parser.add_argument('--run', action='store_true')
    args = parser.parse_args()
    if args.run:
        report = run()
    elif args.freeze:
        report = freeze()
        verify(report)
    else:
        parser.error('Choose --freeze or --run')
    print(json.dumps({k: report.get(k) for k in ('phase', 'protocol_sha256', 'selected', 'retrospective_target_candidate')}))


if __name__ == '__main__':
    main()
