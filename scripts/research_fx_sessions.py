"""Register and evaluate one train-selected FX session hypothesis; no orders."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib, json, gzip, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from propdesk import fx_sessions as engine
from propdesk.target_evaluation import evaluate_period

OUTPUT=ROOT/'docs/fx-session-research.json'
LOCKS=ROOT/'data/fx-session-research'
WINDOWS={'training':('2024-10-03','2025-01-01'),'validation':('2025-01-01','2026-01-01'),'final':('2026-01-01','2026-10-01')}
PRODUCERS=('propdesk/fx_sessions.py','scripts/research_fx_sessions.py','propdesk/target_evaluation.py','propdesk/research_stats.py',
           'propdesk/tzdata/Europe/London','docs/EIGHT_PERCENT_PROTOCOL.json')
EXPECTED_PROVIDERS={'EURUSD':'EURUSD=X','GBPUSD':'GBPUSD=X','USDJPY':'JPY=X'}

def canonical(x): return json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False)
def digest(x): return hashlib.sha256(canonical(x).encode()).hexdigest()
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def now(): return datetime.now(timezone.utc).isoformat()
def immutable(name,value):
    path=LOCKS/name;path.parent.mkdir(parents=True,exist_ok=True)
    raw=canonical(value)+'\n'
    if path.exists():
        if path.read_text()!=raw: raise ValueError('Immutable lock mismatch: '+str(path))
    else: path.write_text(raw)
def save(value):
    OUTPUT.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')
def verify(value):
    if digest(value['protocol'])!=value['protocol_sha256']: raise ValueError('Changed protocol')
    for path,expected in value['protocol']['producers'].items():
        if sha(ROOT/path)!=expected: raise ValueError('Producer changed after freeze: '+path)

def freeze(data_dir):
    if OUTPUT.exists():
        report=json.loads(OUTPUT.read_text());verify(report);return report
    inputs={symbol:{'file':str((data_dir/(symbol+'-1h.json')).relative_to(ROOT)),
                    'sha256':sha(data_dir/(symbol+'-1h.json'))} for symbol in engine.SPECS}
    receipt_path=ROOT/'data/prop-data'/data_dir.name/'manifest.json'
    receipt=json.loads(receipt_path.read_text())
    if receipt['protocol']['id']!='prop-fx-acquisition-v1' or receipt['errors']:
        raise ValueError('Unverified FX acquisition identity')
    sources={x['symbol']:x for x in receipt['sources']}
    for symbol,source in inputs.items():
        raw=json.loads((ROOT/source['file']).read_text());provenance=raw['provenance'];s=sources[symbol]
        if (s['json_sha256']!=source['sha256'] or s['json_path']!=source['file'] or
            s['provider_symbol']!=EXPECTED_PROVIDERS[symbol] or
            provenance['provider_symbol']!=EXPECTED_PROVIDERS[symbol] or
            provenance['instrument_type']!='CURRENCY' or provenance['interval']!='1h' or
            provenance['quote_currency']!=engine.SPECS[symbol]['quote'] or
            s['expected_quote_currency']!=engine.SPECS[symbol]['quote']):
            raise ValueError('Wrong FX price/quote/source identity: '+symbol)
        source['provider_symbol']=EXPECTED_PROVIDERS[symbol]
        source['quote_currency']=engine.SPECS[symbol]['quote']
    acquisition={'file':str(receipt_path.relative_to(ROOT)),'sha256':sha(receipt_path),'protocol':receipt['protocol']}
    p={'id':'fx-asian-london-72-v1','registered_at':now(),'windows':WINDOWS,'variants':engine.variants(),
       'producers':{x:sha(ROOT/x) for x in PRODUCERS},'inputs':inputs,'acquisition_receipt':acquisition,
       'cash':'100000USD nominal CFD equity, reserved initial margin is included, never extra capital. 30xSwing forex margin assumptions; integer1000baseunits (0.01lot). Actual broker prices/fees/margin-stopout unverified.',
       'causality':'Six prior00-06Europe/London candles define range; completed07/08/09 candles signal; next available consecutive hourly open executes. Missing range means no entry, missing active exposure exits at available adverse open and blocks qualification. One entry per London date, flat15local or fixed3/6hour duration.',
       'costs':'Current FTMO commission field5flat_USD/lot ambiguous side/roundtrip: conservative5USD/100000units per SIDE. Spread1pipEURUSD,1.5GBPUSD,1USDJPY; slippage.5pip eachside. All explicit modeling assumptions; doubled stress includes all friction.',
       'signals':'Asian breakout; failed Asian-extreme raid closing inside; Asia directional drift followed by London. Fixed pre-signal14bar ATR, .5..6ATR range context, drift>.5ATR, rejection>.05ATR. Stops frozen at decision; targetRR1/2 from actual modeled entry.',
       'selection':'Common train gates, then ONE max TRAIN return/adverseDD deterministicID; immutable before2025. Stop after any validation fail. Immutable confirmation before single2026. No diagnostic substitute or held-out risk multiplication.',
       'additional_gate':'No missing active-exposure interval and source spans declared start/end. Report every partial London calendar window explicitly; do not use future completeness to decide an entry. Holidays are uncertified and no price bars are fabricated. Close-only proxy stopout unknown so live/contract qualification alwaysfalse.',
       'history':'Adaptive additional study after292previous configurations and48coarse-pairs rejection. General2025/26 macro/prices seen; GBPUSD/USDJPY new model returns unopened. FreshYahoo revisedprices are not globally independent holdout.',
       'interpretation':'Historical8monthlyreference only; confidence lowerpositive does not prove8futureexpectedreturn. Genuine prospective data, permitted brokerfeed/spec/cost and exact stage replay required.'}
    r={'phase':'frozen_before_outcomes','protocol':p,'protocol_sha256':digest(p),'variant_count':72,
       'live_qualified':False,'prop_qualified':False,'telegram_enabled':False,'selected':None}
    immutable('protocol.json',p);immutable('input-lock.json',inputs)
    save(r)
    (ROOT/'docs/FX_SESSION_PROTOCOL.md').write_text('# Frozen Asian / London FX protocol\n\n```json\n'+json.dumps(p,indent=2)+'\n```\n')
    return r

def load(r):
    receipt=r['protocol']['acquisition_receipt']
    if sha(ROOT/receipt['file'])!=receipt['sha256']:raise ValueError('Acquisition receipt changed')
    inputs=r['protocol']['inputs']; out={}
    for symbol,receipt in inputs.items():
        path=ROOT/receipt['file']
        if sha(path)!=receipt['sha256']: raise ValueError('Input changed')
        value=json.loads(path.read_text())
        if value['provenance']['provider_symbol']!=receipt_provider(symbol) or value['provenance']['quote_currency']!=engine.SPECS[symbol]['quote']:
            raise ValueError('FX quote identity changed')
        out[symbol]=value['bars']
    return out

def receipt_provider(symbol):return EXPECTED_PROVIDERS[symbol]

def period(bars,variant,role):
    begin,finish=WINDOWS[role]
    base=engine.simulate(bars[variant['symbol']],variant,begin+'T00:00:00Z',finish+'T00:00:00Z')
    stress=engine.simulate(bars[variant['symbol']],variant,begin+'T00:00:00Z',finish+'T00:00:00Z',cost_multiplier=2)
    if base['insolvent'] or stress['insolvent']:
        s={'passed':False,'checks':{'account_remained_solvent':False},'completed_episodes':base['completed_episodes'],
           'base':{'total_return':base['final_equity']/100000-1,'geometric_monthly_return':None},
           'double_cost_stress':{'total_return':stress['final_equity']/100000-1,'geometric_monthly_return':None},
           'risk':{'max_account_drawdown':None},'selection_score_net_return_over_drawdown':-1e30,
           'status':'insolvent_model_not_eligible_for_geometric_inference'}
    else:
        s=evaluate_period(base['dates'],base['daily_returns'],stress['daily_returns'],base['completed_episodes'],
                      initial_equity=100000,daily_worst_equity=base['daily_worst_equity'],daily_peak_equity=base['daily_peak_equity'],
                      period_start=begin,period_end_exclusive=finish,role=role,samples=5000)
    s['checks']['no_missing_active_exposure']=not(base['missing_exposure_exits'] or stress['missing_exposure_exits'])
    s['checks']['source_spans_declared_period']=base['source_coverage']['source_spans_declared_window']
    s['source_coverage']=base['source_coverage']
    s['passed']=all(s['checks'].values())
    s['variant']=variant
    ledger=ROOT/'.local/fx-session-research';ledger.mkdir(exist_ok=True,parents=True)
    for mode,value in (('base',base),('stress',stress)):
        raw=canonical(value).encode();path=ledger/(role+'-'+variant['id']+'-'+mode+'.json.gz')
        with gzip.GzipFile(filename=str(path),mode='wb',mtime=0) as f: f.write(raw)
        s[mode+'_ledger']={'path':str(path.relative_to(ROOT)),'raw_sha256':hashlib.sha256(raw).hexdigest(),'compressed_sha256':sha(path)}
    s['daily_returns']=base['daily_returns'];s['daily_dates']=base['dates']
    s['reconciliation_error']=base['reconciliation_error']
    return s

def run(r):
    verify(r);bars=load(r)
    if 'training' not in r:
        r['training']=[period(bars,v,'training') for v in engine.variants()]
        save(r)
    survivors=[x for x in r['training'] if x['passed']]
    chosen=sorted(survivors,key=lambda x:(-x['selection_score_net_return_over_drawdown'],x['variant']['id']))[0] if survivors else None
    selection={'variant':chosen['variant'] if chosen else None,'training_sha256':digest(r['training']),'locked_at':r.get('selection',{}).get('locked_at',now())}
    immutable('selection.json',selection);r['selection']=selection;r['selected']=selection['variant'];save(r)
    if not chosen:
        r['phase']='completed_training_failed';save(r);return r
    if 'validation' not in r: r['validation']=period(bars,chosen['variant'],'validation');save(r)
    if not r['validation']['passed']:
        r['phase']='completed_validation_failed_final_unopened';save(r);return r
    confirmation={'selection_sha256':digest(selection),'validation_sha256':digest(r['validation']),'locked_at':r.get('confirmation',{}).get('locked_at',now())}
    immutable('confirmation.json',confirmation);r['confirmation']=confirmation;save(r)
    if 'final' not in r:r['final']=period(bars,chosen['variant'],'final')
    r['phase']='completed_historical_target_passed' if r['final']['passed'] else 'completed_final_failed'
    r['historical_target_candidate']=r['final']['passed'];save(r);return r

def markdown(r):
    def pc(value):return 'not defined' if value is None else f'{100*value:+.4f}%'
    rows=sorted(r.get('training',[]),key=lambda x:-x['base']['total_return'])[:5]
    lines=['# Asian-range / London FX research','',f"Status: **{r['phase']}**;72 preregistered configurations.",'',
           'Risk .5%/1%, RR1/2,3/6h hold were selected only on training; account return is not a cash payout. Provisional Yahoo quotes and assumed friction, not actual broker executions.', '',
           '| Training variant | Net period | Monthly equivalent | Double-cost monthly | Episodes | Adverse DD |',
           '| --- | ---: | ---: | ---: | ---: | ---: |']
    for x in rows:
        lines.append(f"|{x['variant']['id']}|{pc(x['base']['total_return'])}|{pc(x['base']['geometric_monthly_return'])}|{pc(x['double_cost_stress']['geometric_monthly_return'])}|{x['completed_episodes']}|{pc(x['risk']['max_account_drawdown'])}|")
    lines+=['',f"Fixed selection: `{r['selected']}`. No alternative replaces it."]
    for role in ('validation','final'):
        if role in r:
            x=r[role];lines+=['',f"{role}: net{100*x['base']['total_return']:+.4f}%; monthly equivalent{100*x['base']['geometric_monthly_return']:+.4f}%; passed{x['passed']}.",'',json.dumps(x['checks'],indent=2)]
    lines+=['','No live/prop qualification or Telegram signals. Existing overlapping history and sequential decisions are disclosed;99% positive-mean CI alone does not support an8% future monthly expectation.']
    (ROOT/'docs/FX_SESSION_RESEARCH.md').write_text('\n'.join(lines)+'\n')

def main():
    p=argparse.ArgumentParser();p.add_argument('--freeze',action='store_true');p.add_argument('--run',action='store_true');p.add_argument('--data-dir',default='.local/prop-research/fx-2026-10-02T10-40-40Z');a=p.parse_args()
    if not(a.freeze or a.run):p.error('Freeze before outcomes')
    r=freeze((ROOT/a.data_dir).resolve())
    if a.run:r=run(r);markdown(r)
    print(r['phase'],r['protocol_sha256'])

if __name__=='__main__':main()
