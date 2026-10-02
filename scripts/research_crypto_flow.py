#!/usr/bin/env python3
"""Fixed64 causal native aggressor-volume hypotheses; no order API."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))
from propdesk import crypto_flow as engine,flow_data,research_lab as lab,market
from propdesk.funding_lab import validate_events
from scripts import research_broad as shared,research_native_crypto_trend as parent_driver

DIRECTORY=ROOT/'data/crypto-flow-research'
SOURCE=ROOT/'.local/perp-5m-history'
FUNDING=ROOT/'.local/funding-history'
OUTPUT=ROOT/'docs/crypto-flow-research.json'
MARKDOWN=ROOT/'docs/CRYPTO_FLOW_RESEARCH.md'
WINDOWS={'training':['2024-01-01','2025-01-01'],'validation':['2025-01-01','2026-01-01'],
         'final':['2026-01-01','2026-10-01']}
COMMON_SHA256='5495a0683efeb6da230cf454b71c8e8ae952dc03534d23f3cedbcd9f56e9e839'
PARENT_PROTOCOL_SHA256='b692184bfda6da87510f10be08620e0cef1d4af7473b10764fab66f07ba0507e'


def verified_parent():
    protocol=json.loads((ROOT/'data/native-crypto-trend-research/protocol.json').read_text())
    if lab.digest(protocol)!=PARENT_PROTOCOL_SHA256 or shared.file_hash(ROOT/'docs/EIGHT_PERCENT_PROTOCOL.json')!=COMMON_SHA256:
        raise ValueError('Original immutable parent/common protocol identity differs')
    parent_driver.verify({'protocol':protocol,'protocol_sha256':PARENT_PROTOCOL_SHA256})
    return protocol


def write_report(report):
    OUTPUT.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    lines=['# Native aggressor-volume research','',f"Phase: **{report['phase']}**.",'',
           f"Protocol SHA256: `{report['protocol_sha256']}`.",'',
           '64 preregistered flow-continuation / absorption-reversion configurations. Original checksum-verified USD-M5m quote/base taker-buy volumes and integer trade counts are real source fields, not inferred order books or liquidations. Fields become known at candle close; fills follow at the next native opening.','',
           'Adaptive prior price research remains selection history.100k TOTAL physical capital, isolated2x and total2x/perasset1x entry caps; registered0.5/1% stop risks include modeled round-trip friction. Actual settlements and doubled fees/slippage/spread are paid. No unlicensed live service or prop payout certification.','']
    if report.get('training'):
        lines += [f"TRAIN: **{len(report['training'])}/64** evaluated; **{sum(r['passed'] for r in report['training'])}** eligible.",'',
                  '| TRAIN ID | Net % | Double costs % | Trades | Eligible |','|---|---:|---:|---:|---|']
        for r in sorted(report['training'],key=lambda r:(-r['metrics']['return_pct'],r['id']))[:5]:
            lines.append(f"| {r['id']} | {r['metrics']['return_pct']:+.4f} | {r['stress_metrics']['return_pct']:+.4f} | {r['metrics']['trade_count']} | {r['passed']} |")
        lines+=['','Top TRAIN rows are descriptive; the immutable ONE-primary lock determines all later evaluation.','']
    if report.get('reason'):
        lines += [report['reason'],'']
    for role in ('validation','final'):
        if role in report:
            r=report[role];monthly=r['target']['base']['geometric_monthly_return']
            monthly_text='not defined' if monthly is None else f'{monthly*100:+.4f}%'
            lines += [f"{role.capitalize()} ONE-primary net **{r['metrics']['return_pct']:+.4f}%**, double costs **{r['stress_metrics']['return_pct']:+.4f}%**, monthly equivalent **{monthly_text}**, completed trades **{r['metrics']['trade_count']}**, passed **{r['target']['passed']}**.",'',
                      'Failed checks: '+(', '.join(k for k,v in r['target']['checks'].items() if not v) or 'none')+'.','']
    lines += ['No substitute, after-outcome sizing, threshold revision, actual orders or Telegram.8%monthly equivalent is not8%every month or received payout. Official marks/tier/fees/filters/queue, volume-zero execution gaps, USDT parity, licensed live data and approved contract remain unverified. Conservative envelopes may combine nonsimultaneous extrema.','',
              'Source/producer/parent/common hashes and all rejected configurations remain saved; selected full base/double ledgers are immutable local gzip artifacts. Parent wallet/funding/closing/account math is AST-identical; the explicitly registered flow timeframe, volatility, fixed-hold and causal entry-plan hooks are new.','']
    MARKDOWN.write_text('\n'.join(lines))


def freeze():
    path=DIRECTORY/'protocol.json'
    if path.exists():
        protocol=json.loads(path.read_text())
    else:
        verified_parent()
        parent_protocol=ROOT/'data/native-crypto-trend-research/protocol.json'
        if shared.file_hash(ROOT/'propdesk/native_crypto_trend.py')!=engine.PARENT_ENGINE_SHA256:
            raise ValueError('Immutable reviewed parent engine changed')
        producers=['propdesk/crypto_flow.py','propdesk/flow_data.py','scripts/research_crypto_flow.py',
                   'tests/test_crypto_flow.py','tests/test_flow_source_audit.py','propdesk/native_crypto_trend.py',
                   'scripts/research_native_crypto_trend.py','propdesk/target_evaluation.py',
                   'propdesk/research_lab.py','propdesk/research_stats.py','propdesk/market.py',
                   'propdesk/funding_lab.py','propdesk/funding_data.py','propdesk/exchange.py',
                   'propdesk/perp_resolution.py','scripts/research_broad.py']
        inputs=[SOURCE/'manifest.json',FUNDING/'manifest.json',parent_protocol,
                ROOT/'.local/perp-flow-data-audit.json',ROOT/'.local/perp-flow-reader-audit.json',
                ROOT/'docs/PERP_FLOW_DATA_AUDIT.md']
        manifest=json.loads((SOURCE/'manifest.json').read_text())
        for row in manifest['datasets']:
            inputs.append(SOURCE/(row['symbol']+'-5m.json'))
            for src in row['sources']:
                name=src['source_url'].rsplit('/',1)[-1]
                inputs += [SOURCE/'raw'/name,SOURCE/'raw'/(name+'.CHECKSUM')]
        for s in engine.SYMBOLS:
            inputs.append(FUNDING/(s+'-funding.json'))
        protocol={'schema':1,'id':'native-closed-aggressor-flow-v1','frozen_at':shared.now(),
                  'human_protocol_path':'docs/CRYPTO_FLOW_PROTOCOL.md',
                  'human_protocol_sha256':shared.file_hash(ROOT/'docs/CRYPTO_FLOW_PROTOCOL.md'),
                  'common_objective_path':'docs/EIGHT_PERCENT_PROTOCOL.json',
                  'common_objective_sha256':COMMON_SHA256,
                  'parent_protocol_sha256':lab.digest(json.loads(parent_protocol.read_text())),
                  'parent_engine_sha256':engine.PARENT_ENGINE_SHA256,'grid':engine.grid(),'windows':WINDOWS,
                  'producers':{p:shared.file_hash(ROOT/p) for p in producers},
                  'inputs':{str(p.relative_to(ROOT)):shared.file_hash(p) for p in inputs},
                  'hypotheses':'64 configurations:2families×1/3barflowwindow×.15/.30signedquoteimbalance×1/3hourhold×1/2fullyclosedhourATR20stop×.5/1%risk. Originalvolume/tradecountfacts, noorderbook/liquidationclassification.',
                  'causality':'Allflowwindowfields knownonlyatclosednativebar. Prior72baractivitymean excludesentirewindow;flowundefinedzeroquote/volume;allcurrentwindowactualtradesrequired. Next5mopening orders, hourlystopATRfromlatestFULLhour, fixedageexitonly.',
                  'execution_delta':'Parentwallet/equity/close/fundinghelpers andmetrics/dailyterminal ASTidentical. Explicitnative5mdecision/priorATRindex/actualhourATRknown-at/prior5msignaltime/fixed1or3hhold/stoplabel/jointknownopeningentryplans+stopfriction+aggregaterisksizing hooks.',
                  'capital':{'initial_total_equity':100000,'isolated_leverage':2,'total_entry_gross_equity_cap':2,
                             'per_asset_entry_gross_equity_cap':1,'risk_current_equity':[.005,.01],
                             'aggregate_stop_risk_current_equity':[.01,.02],
                             'quantity_step_assumption':.001,'maintenance_assumption':.005,'liquidation_fee_assumption':.005,
                             'collateral':'Allmargin+entryfees fromsharedpositivecash; no topup/credit/extramoney. Grosscaps min(initial,currentmarkedcapital). Actualfundingstayslegwalletuntilclose; negativegapdeficitsreportedineligible.'},
                  'costs':{'taker_bps_side':5,'adverse_slip_bps_side':2,'full_spread_bps':1,'double_all_friction':True},
                  'funding':'Exactrealizedsettlements, >=60shold,parentbeforeopen/afteropen/ms/boundary/debit/ambiguouspositive/liquidationchronology unchanged; neverforecasts. Officialmarkabsent=>tradeopenpriceproxy.',
                  'selection':'All64TRAINbase+doublecost; unchangedcommonpositivecost/30episodes/60days/10%DD/5%daily +zero liquidation/deficit/unknownheldmarks/cashpositive/reconcile. ONEhighestnet/max(adverseDD,.25%)tieID lockedbefore2025;common8monthly/60episodes/6months/CI99/stress/median/2of3months/bothhalves gates thenconfirmationbeforeONE2026. Failurestopswithoutreplacement/rescaling.',
                  'adaptive_history':'All earlier price-based strategies and inspected2024–2026markets remain correlatedselectionhistory. Additional64 registeredconfigurations;fieldsnewlyusedbutnogloballyblindclaim. No formalall-trialsprobabilityorunconditionalprofitalpha.',
                  'limits':'SourceCC-BY-NC-SA personalnonproduction. Takeraggressorvolume isnotbook/dealer/liquidationfact. TradeOHLCmark/filters/fees/queue/zero-volumedataholes/USDTparity/contract/payoutunknown. No purchases/orders/withdrawals/Telegram; no fake livequalification.'}
        shared.immutable_write(path,protocol)
    if OUTPUT.exists():
        return json.loads(OUTPUT.read_text())
    report={'phase':'frozen_before_outcomes','protocol':protocol,'protocol_sha256':lab.digest(protocol),
            'retrospective_target_candidate':False,'live_qualified':False,'prop_qualified':False,'telegram_enabled':False}
    write_report(report)
    return report


def verify(report):
    verified_parent()
    p=report['protocol']
    if p!=json.loads((DIRECTORY/'protocol.json').read_text()) or lab.digest(p)!=report['protocol_sha256'] or p['grid']!=engine.grid():
        raise ValueError('Frozen flow grid/protocol changed')
    for kind in ('producers','inputs'):
        for name,digest in p[kind].items():
            if shared.file_hash(ROOT/name)!=digest:
                raise ValueError('Frozen '+kind+' changed: '+name)
    for prefix in ('human_protocol','common_objective'):
        if shared.file_hash(ROOT/p[prefix+'_path'])!=p[prefix+'_sha256']:
            raise ValueError('Frozen common/human objective changed')


def verify_final_authorization(report):
    """Missing or changed claimed locks never authorize or get repaired forFINAL."""
    selection=json.loads((DIRECTORY/'training-selection.json').read_text())
    confirmation=json.loads((DIRECTORY/'validation-confirmation.json').read_text())
    validation=report.get('validation',{})
    primary=[r for r in report.get('training',[]) if r.get('id')==report.get('selected')]
    if (not isinstance(report.get('selected'),str) or len(primary)!=1 or primary[0].get('passed') is not True
            or primary[0].get('target',{}).get('passed') is not True
            or selection!=report.get('selection_lock') or lab.digest(selection)!=report.get('selection_lock_sha256')
            or selection.get('protocol_sha256')!=report.get('protocol_sha256')
            or selection.get('training_sha256')!=lab.digest(report.get('training'))
            or selection.get('selected')!=report.get('selected') or selection.get('locked_before_validation') is not True
            or confirmation!=report.get('confirmation_lock') or lab.digest(confirmation)!=report.get('confirmation_lock_sha256')
            or confirmation.get('protocol_sha256')!=report.get('protocol_sha256')
            or confirmation.get('selection_lock_sha256')!=report.get('selection_lock_sha256')
            or confirmation.get('validation_sha256')!=lab.digest(validation)
            or confirmation.get('selected')!=report.get('selected') or confirmation.get('locked_before_final') is not True
            or validation.get('target',{}).get('passed') is not True
            or validation.get('variant',{}).get('id')!=report.get('selected')):
        raise ValueError('Frozen selection/validation confirmation does not authorizeFINAL')
    verify(report)


def verified_funding_values(row,filename):
    parent_driver._verified_receipt(FUNDING,row,filename)
    values=json.loads((FUNDING/filename).read_text())
    validate_events(values)
    slots=[market.utc_datetime(v['time']).replace(microsecond=0) for v in values]
    if (len(slots)!=3012 or slots[0].isoformat()!='2024-01-01T00:00:00+00:00'
            or slots[-1].isoformat()!='2026-09-30T16:00:00+00:00'
            or any((b-a).total_seconds()!=8*3600 for a,b in zip(slots,slots[1:]))):
        raise ValueError('Exact original3012 recorded8h slots/endpoints required; noimputation')
    return values


def load_inputs(report):
    data,receipts=flow_data.load_originals(SOURCE)
    lock={'protocol_sha256':report['protocol_sha256'],'original_flow_receipts':receipts,
          'receipts_sha256':lab.digest(receipts),'rows_per_asset':{s:len(data[s]) for s in engine.SYMBOLS},
          'fields_known_at':'exactsourceopen+300seconds','flow_is_not_order_book':True}
    shared.immutable_write(DIRECTORY/'input-lock.json',lock)
    features=engine.FlowFeatures(data)
    funding={};manifest=json.loads((FUNDING/'manifest.json').read_text())
    for s in engine.SYMBOLS:
        row=next(x for x in manifest['datasets'] if x['symbol']==s and x['kind']=='fundingRate')
        funding[s]=verified_funding_values(row,s+'-funding.json')
    return features,engine.prepare_funding(features,funding)


def evaluate(base,stress,window,role,seed):
    checked=parent_driver.evaluate(base,stress,window,role,seed)
    for prefix,r in (('base',base),('double_cost',stress)):
        m=r['metrics']
        error=abs(m['final_equity']-100000-sum(t['pnl'] for t in r['trades']))
        checked['checks'].update({prefix+'_physical_cash_nonnegative':m['minimum_available_cash']>=-1e-7,
                                  prefix+'_account_pnl_reconciled':error<1e-7})
    checked['passed']=all(checked['checks'].values())
    checked['status']='historical_reference_screen_passed' if checked['passed'] else 'not_qualified'
    return checked


def save_ledger(result,role,case):
    path=ROOT/'.local/crypto-flow-research'/(role+'-'+case+'.json.gz');path.parent.mkdir(parents=True,exist_ok=True)
    raw=json.dumps(result,separators=(',',':'),allow_nan=False).encode();packed=gzip.compress(raw,mtime=0)
    if path.exists() and path.read_bytes()!=packed:
        raise ValueError('Immutable flow primary ledger changed')
    path.write_bytes(packed)
    return {'path':str(path.relative_to(ROOT)),'gzip_sha256':shared.file_hash(path),
            'raw_sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(packed)}


def run():
    report=freeze();verify(report)
    if 'confirmation_lock' in report or 'final' in report:
        verify_final_authorization(report)
    if report['phase'].startswith('completed_'):
        return report
    features,funding=load_inputs(report);variants=report['protocol']['grid']
    training=report.setdefault('training',[])
    if len(training)>len(variants) or any(r['id']!=v['id'] or r['variant']!=v for r,v in zip(training,variants)):
        raise ValueError('Resume requires exact ordered registered flow prefix')
    for index in range(len(training),len(variants)):
        v=variants[index];obs=features.observations(v)
        base=engine.simulate(features,obs,funding,v,*WINDOWS['training'])
        stress=engine.simulate(features,obs,funding,v,*WINDOWS['training'],cost_multiplier=2)
        checked=evaluate(base,stress,WINDOWS['training'],'training',20261201+index)
        training.append({'id':v['id'],'variant':v,'metrics':base['metrics'],'stress_metrics':stress['metrics'],
                         'target':checked,'passed':checked['passed'],'score':checked['selection_score_net_return_over_drawdown']})
        report['phase']='training_in_progress';write_report(report)
        print(f"FLOW TRAIN{index+1}/64 {v['id']} net={base['metrics']['return_pct']:+.4f}% double={stress['metrics']['return_pct']:+.4f}% trades={base['metrics']['trade_count']} eligible={checked['passed']}",flush=True)
    eligible=sorted((r for r in training if r['passed']),key=lambda r:(-r['score'],r['id']))
    selected=eligible[0]['id'] if eligible else None
    lockpath=DIRECTORY/'training-selection.json'
    lock={'protocol_sha256':report['protocol_sha256'],'training_sha256':lab.digest(training),
          'selected':selected,'locked_before_validation':True,'locked_at':shared.now()}
    if lockpath.exists():
        lock['locked_at']=json.loads(lockpath.read_text())['locked_at']
    shared.immutable_write(lockpath,lock)
    report.update(selected=selected,selection_lock=lock,selection_lock_sha256=lab.digest(lock),phase='training_complete');write_report(report)
    if selected is None:
        report.update(phase='completed_no_training_candidate',reason='None of64flow configurations passed frozen TRAIN net/stress/risk/activity/mark gates.2025/2026flow-strategy returns remain unopened; no substitute/rescaling.')
        write_report(report);return report
    v=next(v for v in variants if v['id']==selected);obs=features.observations(v)
    for role in ('training_primary','validation','final'):
        if role=='final':
            verify_final_authorization(report)
        window=WINDOWS['training' if role=='training_primary' else role]
        if role not in report:
            base=engine.simulate(features,obs,funding,v,*window)
            stress=engine.simulate(features,obs,funding,v,*window,cost_multiplier=2)
            checked=None
            if role=='training_primary':
                primary=next(r for r in training if r['id']==selected)
                if base['metrics']!=primary['metrics'] or stress['metrics']!=primary['stress_metrics']:
                    raise ValueError('LockedTRAINflow primary no longer reproduces')
            else:
                checked=evaluate(base,stress,window,role,20261301 if role=='validation' else 20261302)
            report[role]={'variant':v,'metrics':base['metrics'],'stress_metrics':stress['metrics'],
                          'daily_returns':base['daily_returns'],'stress_daily_returns':stress['daily_returns'],
                          'raw_ledger':{'base':save_ledger(base,role,'base'),'double_cost':save_ledger(stress,role,'double_cost')}}
            if checked is not None:
                report[role]['target']=checked
            report['phase']=role+'_complete';write_report(report)
        if role=='training_primary':
            continue
        row=report[role]
        if not row['target']['passed']:
            report.update(phase='completed_'+role+'_failed',reason='Immutable ONEflow primary failed '+role+' gates; no replacement/scaling. '+('2026flow-strategy returns remain unopened.' if role=='validation' else 'No qualified historical8%-monthly candidate.'))
            write_report(report);return report
        if role=='validation':
            cpath=DIRECTORY/'validation-confirmation.json'
            confirmation={'protocol_sha256':report['protocol_sha256'],'selection_lock_sha256':report['selection_lock_sha256'],
                          'validation_sha256':lab.digest(row),'selected':selected,'locked_before_final':True,'locked_at':shared.now()}
            if cpath.exists():
                confirmation['locked_at']=json.loads(cpath.read_text())['locked_at']
            shared.immutable_write(cpath,confirmation)
            report.update(confirmation_lock=confirmation,confirmation_lock_sha256=lab.digest(confirmation));write_report(report)
    report.update(phase='completed_retrospective_target_candidate',retrospective_target_candidate=True,
                  reason='ONEflow candidate passed fixedhistorical screens; actualmarks/contract/fees/forwardpaper/data-license remainrequired. No live/propqualification/Telegram.')
    write_report(report);return report


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--freeze',action='store_true');parser.add_argument('--run',action='store_true')
    args=parser.parse_args()
    if not(args.freeze or args.run):
        parser.error('Choose --freeze or --run')
    report=run() if args.run else freeze();verify(report)
    print(json.dumps({k:report.get(k) for k in ('phase','protocol_sha256','selected','retrospective_target_candidate')}))


if __name__=='__main__':
    main()
