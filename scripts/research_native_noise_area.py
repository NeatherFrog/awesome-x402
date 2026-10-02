#!/usr/bin/env python3
"""Freeze24 original-source crypto-clock adaptations; lock one before OOS."""
from __future__ import annotations

import argparse
from bisect import bisect_left
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from propdesk import native_noise_area as engine, flow_data, market, research_lab as lab
from scripts import research_broad as shared
from scripts import research_native_crypto_trend as trend
from scripts import research_native_crypto_mark as marks_parent

DIRECTORY = ROOT/'data/native-noise-area-research'
LEDGERS = ROOT/'.local/native-noise-area-research'
OUTPUT = ROOT/'docs/native-noise-area-research.json'
MARKDOWN = ROOT/'docs/NATIVE_NOISE_AREA_RESEARCH.md'
SOURCE = ROOT/'.local/perp-5m-history'
FUNDING_SOURCE = ROOT/'.local/funding-history'
MARK_SOURCE = ROOT/'.local/mark-5m-complete-history'
ORIGINAL = ROOT/'.local/original-intraday-4f486d93a08d'
FIXED = {
    'docs/EIGHT_PERCENT_PROTOCOL.json': '5495a0683efeb6da230cf454b71c8e8ae952dc03534d23f3cedbcd9f56e9e839',
    'propdesk/tzdata/America/New_York': 'e9ed07d7bee0c76a9d442d091ef1f01668fee7c4f26014c0a868b19fe6c18a95',
    'propdesk/native_crypto_mark.py': '0d72deb7ae3e8bd75f22472f8533981e502330d52763a76aa20a651aa9d770b2',
    '.local/perp-5m-history/manifest.json': 'a849e9ae1891a8974bedd1dd294e0779a7f8cbf5d0cdffdd1416c91049403ea3',
    '.local/funding-history/manifest.json': '0474ae39b55f8e8ed2baa3ebb169dd326a4e47b2fa87c387d6f4906dc106c2d5',
    '.local/funding-history/BTCUSDT-funding.json': '6bbb69ac5fa5497af6cb4ad621b511e6cb395ebdace6ba512bdf034d901f27f7',
    '.local/funding-history/ETHUSDT-funding.json': '033fc2ed8a46ee53196356f13341caa788e9e1a9938bd75e43a0b06afb0e54c3',
    '.local/mark-5m-complete-history/manifest.json': '9887c9b08a73a6a63e71c00815f45d9534977045e15d79805e10ae4f37f59e94',
    '.local/original-intraday-4f486d93a08d/receipts.json': 'c9dfc54479f322d52c21f9fd95c832d650a0bdbae429f790c73f5a50a6ba0702',
}
PRODUCERS = (
    'propdesk/native_noise_area.py', 'scripts/research_native_noise_area.py',
    'tests/test_native_noise_area.py', 'propdesk/native_crypto_mark.py',
    'scripts/research_native_crypto_mark.py', 'propdesk/native_crypto_trend.py',
    'scripts/research_native_crypto_trend.py', 'propdesk/flow_data.py',
    'propdesk/funding_data.py', 'propdesk/exchange.py', 'propdesk/perp_resolution.py',
    'propdesk/market.py', 'propdesk/research_lab.py', 'propdesk/research_stats.py',
    'propdesk/target_evaluation.py', 'scripts/research_broad.py',
    'propdesk/tzdata/America/New_York', 'docs/EIGHT_PERCENT_PROTOCOL.json',
    'docs/INTRADAY_PRIMARY_METHODS.md', 'docs/intraday-primary-methods.json',
    'docs/NATIVE_NOISE_AREA_PROTOCOL.md',
)


def immutable(name, value):
    shared.immutable_write(DIRECTORY/name, value)


def read_lock(name):
    path = DIRECTORY/name
    if not path.exists():
        raise ValueError('Missing claimed immutable noise lock: '+name)
    return json.loads(path.read_text())


def ledger_bytes(value):
    output = io.BytesIO()
    with gzip.GzipFile(filename='', mode='wb', fileobj=output, mtime=0) as stream:
        stream.write(lab.canonical(value).encode())
    return output.getvalue()


def ledger(value, name):
    LEDGERS.mkdir(parents=True, exist_ok=True)
    path = LEDGERS/(name+'.json.gz')
    raw = ledger_bytes(value)
    if path.exists():
        if path.read_bytes() != raw:
            raise ValueError('Refusing immutable noise ledger mutation: '+name)
    else:
        with path.open('xb') as stream:
            stream.write(raw)
    return {'path': str(path.relative_to(ROOT)), 'compressed_sha256': shared.file_hash(path),
            'raw_sha256': hashlib.sha256(lab.canonical(value).encode()).hexdigest()}


def ledger_read(receipt):
    path = ROOT/receipt['path']
    if shared.file_hash(path) != receipt['compressed_sha256']:
        raise ValueError('Compressed noise evidence changed: '+receipt['path'])
    raw = gzip.decompress(path.read_bytes())
    if hashlib.sha256(raw).hexdigest() != receipt['raw_sha256']:
        raise ValueError('Original noise evidence changed: '+receipt['path'])
    return json.loads(raw)


def source_files():
    paths = {SOURCE/'manifest.json', FUNDING_SOURCE/'manifest.json', MARK_SOURCE/'manifest.json',
             MARK_SOURCE/'protocol.json', ROOT/'data/mark-resolution/source-audit.json', ORIGINAL/'receipts.json'}
    for root in (SOURCE, FUNDING_SOURCE, MARK_SOURCE):
        manifest = json.loads((root/'manifest.json').read_text())
        for row in manifest['datasets']:
            if row['symbol'] not in engine.SYMBOLS or (root == FUNDING_SOURCE and row.get('kind') != 'fundingRate'):
                continue
            paths.add(root/row['json'])
            for receipt in row.get('sources', [])+row.get('rejected_sources', []):
                name = receipt['source_url'].rsplit('/', 1)[-1]
                original, checksum = root/'raw'/name, root/'raw'/(name+'.CHECKSUM')
                if root != FUNDING_SOURCE or original.exists() or checksum.exists():
                    paths.update((original, checksum))
    papers = json.loads((ORIGINAL/'receipts.json').read_text())
    for paper in papers['sources']:
        if paper['id'] not in ('concretum_noise_original', 'concretum_orb_original'):
            continue
        if paper['status'] != 200 or not paper.get('accepted_original_pdf'):
            raise ValueError('Verified original author PDF required')
        pdf, private = ORIGINAL/paper['pdf_file'], ORIGINAL/paper['private_text_file']
        if shared.file_hash(pdf) != paper['pdf_sha256'] or shared.file_hash(private) != paper['private_text_sha256']:
            raise ValueError('Original private PDF/text hash changed')
        paths.update((pdf, private))
    return {str(path.relative_to(ROOT)): shared.file_hash(path) for path in sorted(paths)}


def audit_and_load(end_date):
    """Audit source bytes; construct only alpha through the requested role end."""
    datasets, _ = flow_data.load_originals(SOURCE)
    expected_count = 289152
    for symbol in engine.SYMBOLS:
        rows = datasets[symbol]
        if len(rows) != expected_count or rows[0]['time'] != '2024-01-01T00:00:00Z' or rows[-1]['known_at'] != '2026-10-01T00:00:00Z':
            raise ValueError('Exact full authentic trade source calendar required')
    cutoff = bisect_left([row['time'] for row in datasets[engine.SYMBOLS[0]]], end_date+'T00:00:00Z')
    if cutoff == 0:
        raise ValueError('Role cannot have an empty source prefix')
    for symbol in engine.SYMBOLS:
        del datasets[symbol][cutoff:]
        if market.utc_datetime(datasets[symbol][-1]['known_at']) != market.utc_datetime(end_date+'T00:00:00Z'):
            raise ValueError('Exact role end must be represented by source known-at boundary')
    funding_manifest = json.loads((FUNDING_SOURCE/'manifest.json').read_text())
    funding_receipts = {(row['symbol'], row['kind']): row for row in funding_manifest['datasets']}
    funding = {}
    for symbol in engine.SYMBOLS:
        name = symbol+'-funding.json'
        trend._verified_receipt(FUNDING_SOURCE, funding_receipts[symbol, 'fundingRate'], name)
        values = json.loads((FUNDING_SOURCE/name).read_text())
        slots = [market.utc_datetime(row['time']).replace(microsecond=0) for row in values]
        if len(values) != 3012 or slots[0].isoformat() != '2024-01-01T00:00:00+00:00' or any((b-a).total_seconds()!=28800 for a,b in zip(slots,slots[1:])):
            raise ValueError('Full original3012 funding settlements required')
        boundary=market.utc_datetime(end_date+'T00:00:00Z')
        funding[symbol] = [row for row in values if market.utc_datetime(row['time']) <= boundary]
    manifest = json.loads((MARK_SOURCE/'manifest.json').read_text())
    if (manifest['data_protocol_id'] != 'binance-usdm-btceth-calculated-mark-five-minute-2024-2026-v2' or
            not manifest['assets_open_labels_aligned'] or
            manifest['native_trade_manifest_sha256'] != shared.file_hash(SOURCE/'manifest.json')):
        raise ValueError('Wrong official calculated-mark/native-clock identity')
    marks = {}
    for row in manifest['datasets']:
        marks_parent._verified_mark_receipt(row)
        if row['native_trade_json_sha256'] != shared.file_hash(SOURCE/(row['symbol']+'-5m.json')):
            raise ValueError('Mark/trade canonical source binding mismatch')
        values = json.loads((MARK_SOURCE/row['json']).read_text())
        if len(values) != expected_count or values[0]['time'] != '2024-01-01T00:00:00Z' or values[-1]['known_at'] != '2026-10-01T00:00:00Z':
            raise ValueError('Full original observed mark calendar required')
        marks[row['symbol']] = values[:cutoff]
    features = engine.NoiseFeatures(datasets, marks)
    del datasets, marks
    return features, engine.prepare_funding(features, funding)


def freeze():
    if OUTPUT.exists():
        report = json.loads(OUTPUT.read_text()); verify(report); return report
    for path, expected in FIXED.items():
        if shared.file_hash(ROOT/path) != expected:
            raise ValueError('Literal noise source/clock/objective/parent mismatch: '+path)
    inputs = source_files()
    # Source-quality parsing is permitted before outcomes; do not simulate here.
    features, _ = audit_and_load(shared.WINDOWS['training'][1])
    source_audit = {'first_open': features.times[0], 'last_training_known_at':
                    shared.WINDOWS['training'][1]+'T00:00:00Z', 'training_native_bar_count': len(features.times),
                    'input_count': len(inputs), 'performance_evaluated': False}
    del features
    protocol = {'id': 'native-noise-area-24-v1', 'frozen_at': shared.now(), 'grid': engine.grid(),
                'windows': shared.WINDOWS, 'training_folds': shared.FOLDS,
                'producers': {path: shared.file_hash(ROOT/path) for path in PRODUCERS},
                'inputs': inputs, 'literal_bindings': FIXED, 'source_audit': source_audit,
                'scope': 'New deterministic crypto NY-clock adaptation after earlier crypto studies. Author originalSPY corpus genuinely read, but these histories are adaptively inspected and no globally pristine test claim is made. Imported preservedmarkV1 source/mathhelpers do not endorse its revoked old-exit/new-entry selection chronology; NEW Noise reservationordering separately fixes that issue before outcomes.',
                'clock': 'Pinned direct NewYork TZif; weekday09:30open,10:00first closed checkpoint,15/30minute checkpoints strictlybefore16:00,flat at16:00firstgenuine tradeopen. Crypto weekdays do not certify NYSE holidays/news.',
                'noise': 'Previous EXACT14 completed localweekday sessions, same completed5m slot abs(close/open0930-1), arithmeticmean; absenttradeslot unknown without older replacement. Gapboundsmax/min current0930open versus previouseligible1555close known16. No future-day/full-session completeness entry filter.',
                'vwap': 'Actual cumulative originalUSDT quote_volume / originalBTC-or-ETHbase_volume since0930, using only completed5m rows. Missing/taker/orderbook data never fabricated.',
                'entry': 'Completedcheckpoint close>UB long/<LBshort. Current next5m opening proxy after observation completes, initial thresholdcurrentband orcurrentband+VWAP. Stop must remain onloss side ofactualadverseentry andknowncompletedmark. No same5m re-entry/flip afterexit.',
                'stops': 'Own initialprotective threshold andmonotoniccheckpoint ratchet. New thresholdsknownatcheckpoint activate noearlierthan next5mopen. Openinggap stop executes observedtradeopen, neverband. Knowncompleted-mark extremum touching currentstop queues firstlater positive-volume tradeopen; no historicalintrabarfill atstop. This is notauthorsemi-hourlyexit replication.',
                'capital': 'TOTAL100kUSDT-equivalentaccount; 2xisolatedpositivecollateral, totalentrygross<=2xmin(initial,currentknownmarkequity),eachasset<=1x. Halfaggregate .5/1% riskrequestedperasset includingentry+plannedstop fillfriction+bothnotionalfees; both intentsreservecash/gross/risk BEFORE currentwholebarvolume checks. Quantityfloor.001baseunit assumption.',
                'costs': {'fee_bps_each_side':5,'slippage_bps_each_side':2,'full_spread_bps':1,'double_all_friction':True,'executable_tariffs_verified':False},
                'risk': 'Finalreviewedauthentic-markwallet/funding/liquidationmodel pinned0d72deb7. Completedcomputedmarks for sizing; wholemarkOHLC conservativeriskbound neverfill. OLD-wallet currentmarkOPEN ambiguousmaintenancebreach forfeitscollateralbefore sameopeningexit. Sparseheld/priorintent marks,unknowncheckpoints,reopeningexecution,terminalpositions,liquidation/debt/cashfailure disqualify; no favorablelater recovery.',
                'funding': 'Actualtimestampedrealizedfunding charges, nofutureforecast. Prior-completedmarkproxyfor exactTdebit; omitpositive exactTcredits. Lateevents/possible reopeningdebits cannotfinanceearlier openingorders. Settlement-ms exactmark/tier/bookunknown.',
                'selection': 'All24TRAIN base+doublecost,3chronologicalfolds andfixedcommonpositive/activity/risk/physical/sourcegates. Onehighestnet/adverseDDscore,tiesID; bindall24exactidentitiesbefore2025. FailedTRAIN=>noOOS; failedsole2025=>2026unopened; immutablepassingconfirmationbeforeFINAL. Noalternative/rescale.',
                'target': 'Unmodified common8% geometricmonthly OOSobjective+99%dailymean7day5000bootstraplower>0,60episodes/6fullmonths,positivecoststress,median/2of3months/bothhalves/riskchecks. ConditionalmeanCIdoesnotprovefuture8%expectation.',
                'limits': 'Historicalfixedbps execution,2xmaintenance/lotstep/tariffs/latency/settlementpoint/continuousmarks are provisional. USDT perpetualcrypto data notSPYequity/exactFTMO instruments/rules. No author-performance transfer, productionlicense grant, live/TG/propqualification.'}
    immutable('protocol.json', protocol); immutable('input-lock.json', inputs)
    report = {'phase':'frozen_before_outcomes','protocol':protocol,'protocol_sha256':lab.digest(protocol),
              'variant_count':24,'selected':None,'retrospective_target_candidate':False,
              'live_qualified':False,'prop_qualified':False,'live_orders':False,'telegram_enabled':False}
    save(report)
    return report


def identities(rows):
    return [{'id':row['id'],'variant_sha256':lab.digest(row['variant']),
             'result_sha256':lab.digest(row)} for row in rows]


def verify(report):
    protocol = report['protocol']
    if (lab.digest(protocol) != report['protocol_sha256'] or read_lock('protocol.json') != protocol or
            read_lock('input-lock.json') != protocol['inputs'] or protocol['grid'] != engine.grid() or
            report['variant_count'] != 24 or protocol['windows'] != shared.WINDOWS or
            protocol['training_folds'] != shared.FOLDS or set(protocol['producers']) != set(PRODUCERS) or
            protocol['literal_bindings'] != FIXED):
        raise ValueError('Exact noise protocol/input/catalog/window/literal identity changed')
    for namespace in ('inputs','producers'):
        for path, expected in protocol[namespace].items():
            if shared.file_hash(ROOT/path) != expected:
                raise ValueError('Frozen noise source/producer changed: '+path)
    for path, expected in FIXED.items():
        if shared.file_hash(ROOT/path) != expected:
            raise ValueError('Literal identity changed: '+path)
    rows = report.get('training', [])
    if rows and [row['variant'] for row in rows] != protocol['grid'][:len(rows)]:
        raise ValueError('Noise TRAIN rows differ from ordered frozen catalog')
    for name in ('selection','confirmation'):
        if name in report and read_lock(name+'.json') != report[name]:
            raise ValueError('Claimed noise immutable '+name+' changed')
    if 'final' in report and 'confirmation' not in report:
        raise ValueError('FINAL lacks immutable passing confirmation')
    for role in ('training','validation','final'):
        values = report.get(role, []); values = values if isinstance(values,list) else [values]
        for row in values:
            for mode in ('base','stress'):
                value = ledger_read(row[mode+'_ledger'])
                if (value['variant_id'] != row['id'] or value['window'] != shared.WINDOWS[role] or
                        value['role'] != role or value['start'] != shared.WINDOWS[role][0]+'T00:00:00Z' or
                        market.utc_datetime(value['end']).timestamp()+300 != market.utc_datetime(shared.WINDOWS[role][1]+'T00:00:00Z').timestamp() or
                        value['metrics'] != row['metrics' if mode=='base' else 'stress_metrics']):
                    raise ValueError('Actual full noise evidence identity/window differs')
            for fold in row.get('folds', []):
                value = ledger_read(fold['ledger'])
                if (value['window'] != fold['window'] or value['variant_id'] != row['id'] or
                        value['metrics'] != fold['metrics']):
                    raise ValueError('Actual immutable TRAIN fold identity/window differs')


def assess(base, stress, window, role, seed):
    result = marks_parent.evaluate(base, stress, window, role, seed)
    for name, value in (('base',base),('doublecost',stress)):
        result['checks']['no_unknown_checkpoint_update_'+name] = value['metrics']['unknown_checkpoint_stop_update_count']==0
    result['passed'] = all(result['checks'].values())
    result['status'] = 'historical_reference_screen_passed' if result['passed'] else 'not_qualified'
    return result


def period(features, funding, variant, role, seed):
    window = shared.WINDOWS[role]
    observations = features.observations(variant)
    base = engine.simulate(features,observations,funding,variant,*window)
    stress = engine.simulate(features,observations,funding,variant,*window,cost_multiplier=2)
    for value in (base,stress):
        value.update(variant_id=variant['id'],window=window,role=role)
    result = assess(base,stress,window,role,seed)
    folds = []
    if role == 'training':
        for index,fold in enumerate(shared.FOLDS):
            value = engine.simulate(features,observations,funding,variant,*fold)
            value.update(variant_id=variant['id'],window=fold,role='training_fold')
            guards = marks_parent.execution_guards(value)
            guards['no_unknown_checkpoint_update'] = value['metrics']['unknown_checkpoint_stop_update_count']==0
            folds.append({'window':fold,'metrics':value['metrics'],'guards':guards,
                          'ledger':ledger(value,'training-fold'+str(index)+'-'+variant['id'])})
        result['checks']['two_of_three_training_folds_positive'] = sum(
            row['metrics']['return_pct']>0 and all(row['guards'].values()) for row in folds)>=2
        result['passed'] = all(result['checks'].values())
        result['status'] = 'historical_reference_screen_passed' if result['passed'] else 'not_qualified'
    return {'id':variant['id'],'variant':variant,'metrics':base['metrics'],'stress_metrics':stress['metrics'],
            'target':result,'passed':result['passed'],'score':result['selection_score_net_return_over_drawdown'],
            'folds':folds,'decomposition':marks_parent.price_decomposition(base),
            'base_ledger':ledger(base,role+'-'+variant['id']+'-base'),
            'stress_ledger':ledger(stress,role+'-'+variant['id']+'-stress')}


def verify_selection(report):
    verify(report)
    selection = read_lock('selection.json')
    rows = report['training']
    survivors = sorted((row for row in rows if row['passed']),key=lambda row:(-row['score'],row['id']))
    winner = survivors[0]['id'] if survivors else None
    if (len(rows)!=24 or selection!=report['selection'] or lab.digest(selection)!=report['selection_sha256'] or selection['selected']!=winner or
            report['selected']!=winner or selection['protocol_sha256']!=report['protocol_sha256'] or
            selection['training_sha256']!=lab.digest(rows) or selection['training_identities']!=identities(rows) or
            read_lock('training.json')!=rows):
        raise ValueError('Sole primary selection no longer binds all24 original TRAIN rows')


def verify_final_authority(report):
    verify_selection(report)
    confirmation = read_lock('confirmation.json')
    if (not report['validation']['passed'] or report['validation']['id']!=report['selected'] or
            read_lock('validation.json')!=report['validation'] or confirmation!=report['confirmation'] or
            confirmation['selected']!=report['selected'] or
            confirmation['protocol_sha256']!=report['protocol_sha256'] or
            confirmation['selection_sha256']!=lab.digest(report['selection']) or
            confirmation['validation_sha256']!=lab.digest(report['validation'])):
        raise ValueError('Passing sole validation/confirmation required immediately before FINAL')


def run_training():
    report = freeze(); verify(report)
    if report.get('training') or (DIRECTORY/'selection.json').exists():
        raise ValueError('Noise TRAIN already opened; refusing rerun/partial resume')
    features,funding = audit_and_load(shared.WINDOWS['training'][1])
    rows = []
    for index,variant in enumerate(report['protocol']['grid']):
        row = period(features,funding,variant,'training',20261012+index)
        rows.append(row)
        report.update(phase='training_in_progress',training=rows); save(report)
        print(f"Noise24 TRAIN {index+1}/24 {row['id']} net={row['metrics']['return_pct']:+.4f}% stress={row['stress_metrics']['return_pct']:+.4f}% episodes={row['metrics']['trade_count']} passed={row['passed']}",flush=True)
    survivors = sorted((row for row in rows if row['passed']),key=lambda row:(-row['score'],row['id']))
    selected = survivors[0]['id'] if survivors else None
    selection = {'selected':selected,'protocol_sha256':report['protocol_sha256'],
                 'training_sha256':lab.digest(rows),'training_identities':identities(rows),
                 'locked_at':shared.now(),'locked_before_validation':True}
    immutable('training.json',rows); immutable('selection.json',selection)
    report.update(selected=selected,selection=selection,selection_sha256=lab.digest(selection),
                  phase='training_complete_primary_locked_oos_unopened' if selected else 'completed_no_training_candidate')
    save(report); verify_selection(report)
    return report


def evaluate_locked():
    report = json.loads(OUTPUT.read_text()); verify_selection(report)
    if not report.get('selected'):
        raise ValueError('No locked eligible primary; OOS remains unopened')
    if 'validation' in report:
        if not report['validation']['passed']:
            raise ValueError('Sole validation already failed; no later window or replacement')
        verify_final_authority(report)
    variant = next(row for row in report['protocol']['grid'] if row['id']==report['selected'])
    for role in ('validation','final'):
        if role == 'validation' and 'validation' in report:
            continue
        verify_selection(report)
        if role == 'final':
            verify_final_authority(report)
        if (DIRECTORY/(role+'.json')).exists() or role in report:
            raise ValueError('Noise OOS already opened; refusing rerun/overwrite')
        features,funding = audit_and_load(shared.WINDOWS[role][1])
        row = period(features,funding,variant,role,20262012+(0 if role=='validation' else 1000))
        immutable(role+'.json',row); report[role]=row
        if not row['passed']:
            report.update(phase='completed_locked_'+role+'_failed',reason='Sole primary failed fixed common8%/risk/source/statistical screen; no replacement or scaling; later window unopened.')
            save(report); return report
        if role == 'validation':
            confirmation={'selected':report['selected'],'protocol_sha256':report['protocol_sha256'],
                          'selection_sha256':lab.digest(report['selection']),
                          'validation_sha256':lab.digest(row),'locked_at':shared.now()}
            immutable('confirmation.json',confirmation); report['confirmation']=confirmation
        report['phase']=role+'_complete'; save(report)
    report.update(phase='completed_locked_final',retrospective_target_candidate=True,
                  reason='Historical reference gates passed; freshforward/exactexecution/propcontract unverified. No orders/Telegram.')
    save(report); return report


def save(report):
    OUTPUT.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    lines=['# Native crypto noise-area reference research','',f"Phase: **{report['phase']}**;24 configurations.",'',
           f"Protocol SHA256: `{report['protocol_sha256']}`.",'',
           'Original SPY author formulas are adapted to BTC/ETH weekday New-York hours. Physical isolated collateral, original quote/base VWAP, both-side costs, realized funding and authentic calculated marks are explicit. This is not the paper performance or exact prop execution.','']
    if report.get('training'):
        rows=report['training']; lines += [f"TRAIN completed: {len(rows)}; passing: {sum(row['passed'] for row in rows)}.",'']
    if report.get('selected'):
        lines += [f"Immutable sole primary: `{report['selected']}`.",'']
    for role in ('validation','final'):
        if role in report:
            row=report[role]; monthly=row['target']['base']['geometric_monthly_return']
            formatted='undefined' if monthly is None else f'{monthly*100:+.4f}%'
            lines += [f"{role}: net {row['metrics']['return_pct']:+.4f}%; geometric monthly {formatted}; {row['metrics']['trade_count']} episodes; passed {row['passed']}.",'']
    lines += [report.get('reason','One fixed primary only; no postfailure substitute or leverage increase.'),'',
              'All full base/stress ledgers remain checksum-bound privately. A positive conditional mean-return interval cannot prove future8%monthly returns. Live/Telegram/prop qualification remains false.','']
    MARKDOWN.write_text('\n'.join(lines))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--freeze',action='store_true');parser.add_argument('--run',action='store_true')
    parser.add_argument('--evaluate-locked',action='store_true')
    args=parser.parse_args()
    report=evaluate_locked() if args.evaluate_locked else run_training() if args.run else freeze()
    print(json.dumps({'phase':report['phase'],'protocol_sha256':report['protocol_sha256'],
                      'variant_count':24,'selected':report.get('selected')}))


if __name__=='__main__':
    main()
