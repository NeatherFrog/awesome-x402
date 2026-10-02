#!/usr/bin/env python3
"""Preregister 96 native perpetual variants; lock one TRAIN primary before OOS."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from propdesk import native_crypto_mark as engine, research_lab as lab, market
from propdesk import target_evaluation as target, research_stats as stats
from scripts import research_broad as shared
from scripts import research_native_crypto_trend as parent

DIRECTORY = ROOT/"data/native-crypto-mark-research"
SOURCE = ROOT/".local/perp-5m-history"
FUNDING_SOURCE = ROOT/".local/funding-history"
MARK_SOURCE = ROOT/".local/mark-5m-complete-history"
OUTPUT = ROOT/"docs/native-crypto-mark-research.json"
MARKDOWN = ROOT/"docs/NATIVE_CRYPTO_MARK_RESEARCH.md"
COMMON_SHA256 = "5495a0683efeb6da230cf454b71c8e8ae952dc03534d23f3cedbcd9f56e9e839"
PARENT_PROTOCOL_SHA256 = "b692184bfda6da87510f10be08620e0cef1d4af7473b10764fab66f07ba0507e"
MARK_MANIFEST_SHA256 = "9887c9b08a73a6a63e71c00815f45d9534977045e15d79805e10ae4f37f59e94"
MARK_PROTOCOL_SHA256 = "84c03585b12b75ada698f942581953ddd4e56e9c96b474b12f748c38c7fc1aef"
MARK_SOURCE_AUDIT_SHA256 = "339d1f7ce0784f871ad8c9ca9c1f044c0cd790c07ef1b009ca315790f6c95b96"


def write_report(report):
    temporary = OUTPUT.with_suffix(".tmp")
    temporary.write_text(json.dumps(report, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    temporary.replace(OUTPUT)
    rows = report.get("training", [])
    lines = ["# Authentic mark-risk interpretation of native96", "", f"Phase: **{report['phase']}**.", "",
             f"Protocol SHA256: `{report['protocol_sha256']}`.", "",
             "The SAME96 registered alpha/risk/cost variants are retested with authentic computed marks and causally queued risk exits. This is adaptive evidence/execution refinement after the rejected trade-price-marking study, not96 new discoveries or globally blind history.", "",
             "Mark OHLC is risk evidence, never an executable price. Closed mark triggers queue until a later genuine positive-volume trade open. Uncertain reopening exits, sparse observed mark risk, liquidation/debt and terminal unfilled positions prevent qualification. 8% common objective is unchanged.", ""]
    if rows:
        lines += [f"TRAIN cases completed: **{len(rows)}**; survivors: **{sum(r['passed'] for r in rows)}**.", ""]
        best = max(rows, key=lambda r: r['metrics']['return_pct'])
        lines += [f"Highest net TRAIN result is diagnostic: `{best['id']}` **{best['metrics']['return_pct']:+.4f}%**, double friction **{best['stress_metrics']['return_pct']:+.4f}%**, episodes **{best['metrics']['trade_count']}**. It is not automatically the primary.", ""]
    if report.get("reason"):
        lines += [report['reason'], ""]
    if report.get("selected"):
        lines += [f"Locked primary: `{report['selected']}`.", ""]
    for role in ("validation", "final"):
        if role in report:
            row = report[role]; monthly = row['target']['base']['geometric_monthly_return']
            value = f"{monthly*100:+.4f}%" if monthly is not None else "undefined"
            lines += [f"{role.capitalize()}: net **{row['metrics']['return_pct']:+.4f}%**, geometric monthly **{value}**, episodes **{row['metrics']['trade_count']}**, target **{row['target']['passed']}**.", ""]
    lines += ["Original96 stays rejected and immutable. Genuine mark candles do not prove continuous sampling, executable quotes, settlement-ms marks or historical tiers. No substitute primary, sizing change, payout certification, Telegram or live orders.", ""]
    MARKDOWN.write_text("\n".join(lines), encoding="utf-8")


def freeze():
    path = DIRECTORY/"protocol.json"
    if path.exists():
        protocol = json.loads(path.read_text())
    else:
        if shared.file_hash(ROOT/'docs/EIGHT_PERCENT_PROTOCOL.json') != COMMON_SHA256 or shared.file_hash(MARK_SOURCE/'manifest.json') != MARK_MANIFEST_SHA256 or shared.file_hash(MARK_SOURCE/'protocol.json') != MARK_PROTOCOL_SHA256 or shared.file_hash(ROOT/'data/mark-resolution/source-audit.json') != MARK_SOURCE_AUDIT_SHA256:
            raise ValueError('Literal common/complete-source/audit registration changed')
        manifest = json.loads((MARK_SOURCE/"manifest.json").read_text())
        if manifest['data_protocol_id'] != 'binance-usdm-btceth-calculated-mark-five-minute-2024-2026-v2' or not manifest.get('assets_open_labels_aligned') or not all(r.get('complete_calendar') and not r.get('failures') for r in manifest['datasets']):
            raise ValueError("Only the complete official v2 mark acquisition may freeze; blockedv1 cannot substitute")
        inputs = [SOURCE/'manifest.json', FUNDING_SOURCE/'manifest.json', MARK_SOURCE/'manifest.json', MARK_SOURCE/'protocol.json', ROOT/'data/mark-resolution/source-audit.json', ROOT/'docs/MARK_DATA_SOURCES.md', ROOT/'docs/NATIVE_CRYPTO_MARK_PROTOCOL.md']
        for symbol in engine.SYMBOLS:
            inputs += [SOURCE/(symbol+'-5m.json'), FUNDING_SOURCE/(symbol+'-funding.json'), MARK_SOURCE/(symbol+'-mark-5m.json')]
        producers = ['propdesk/native_crypto_mark.py', 'scripts/research_native_crypto_mark.py', 'tests/test_native_crypto_mark.py',
                     'propdesk/native_crypto_trend.py', 'scripts/research_native_crypto_trend.py',
                     'propdesk/target_evaluation.py', 'propdesk/research_lab.py', 'propdesk/research_stats.py',
                     'propdesk/market.py', 'scripts/research_broad.py']
        producers = list(dict.fromkeys(producers+list(manifest['producer_hashes'])))
        for producer, expected in manifest['producer_hashes'].items():
            if shared.file_hash(ROOT/producer) != expected:
                raise ValueError('Mark acquisition producer changed')
        old = json.loads((ROOT/'docs/native-crypto-trend-research.json').read_text())
        parent.verify(old)
        if old['protocol_sha256'] != PARENT_PROTOCOL_SHA256 or old['protocol']['producers']['propdesk/native_crypto_trend.py'] != '75f43df5e547c3853369e5734d359d07df6409a19bb63939e1da1567a4956d28':
            raise ValueError('Literal frozen parent interpretation changed')
        if old['phase'] != 'completed_no_training_candidate' or old.get('selected') is not None:
            raise ValueError('Immutable rejected parent evidence required')
        protocol = {'version':'adaptive-native96-authentic-mark-execution-v1', 'frozen_at':shared.now(),
                    'grid':engine.grid(), 'windows':shared.WINDOWS, 'training_folds':shared.FOLDS,
                    'producers':{p:shared.file_hash(ROOT/p) for p in producers},
                    'inputs':{str(p.relative_to(ROOT)):shared.file_hash(p) for p in inputs},
                    'common_objective_path':'docs/EIGHT_PERCENT_PROTOCOL.json',
                    'common_objective_sha256':shared.file_hash(ROOT/'docs/EIGHT_PERCENT_PROTOCOL.json'),
                    'parent_report_path':'docs/native-crypto-trend-research.json',
                    'parent_report_sha256':shared.file_hash(ROOT/'docs/native-crypto-trend-research.json'),
                    'parent_protocol_sha256':old['protocol_sha256'],
                    'mark_source_protocol_sha256':manifest['protocol_sha256'],
                    'scope':'SAME96 alpha/risk/cost choices after observedTRAIN and rejected old mark-proxy evidence. New authentic-source/execution interpretation, not new independentalpha or untouchedhistory. Original producers/results unchanged.',
                    'alpha':'Import unchanged grid/NativeFeatures.observations from frozen parent:36EMA,36channel,24RSIcontext; closedtrade hourly/daily features and previous completed trade dailyATR14. No mark-price alpha or revised parameter grid.',
                    'marks':'Complete authentic official calculated-mark5m sourcev2:32monthly+all30June2026daily archives perasset, all checksums and unchangedmonthly overlap. Sourceauxiliary counts are metadata, never executedtrades or continuoussampling proof. No spot/index substitutes or fill-forward.',
                    'source_sparse_risk':'Preserve ALL records. Each heldasset-bar with computed-mark auxiliary_count<=2 flags incompleteobservedrisk; any openingintent referencing a precedingcompleted sparse mark separatelyflagsunknownpricing. Both mustbezero BASE/stress for eligibility; never retrospectivelyskip trades/days or synthesize missing extrema. Highercount also does not provecontinuouspath.',
                    'entry':'Use prior completed MARKCLOSE only for opening account equity/risk budgets. Same .25/.5/1% currentaccount risk and2/3 priortradeDailyATR stops, isolated2x physicalTOTAL100k, perasset1x/total2x cap againstmin(initial,currentequity). BOTHasset intents reserveknownopening cash/gross before future wholebar volume checks; unfilledBTC cannot enlargeETH in the same interval.',
                    'execution':'Mark prices never fill orders. Completed mark adverseendpoint touching fixedstop latches intent atknown_at, then firstsubsequent positive-volume tradeOPEN executes with originaladversefriction. No samebar mark-trigger fill. NativeTP only actualpositive-volume tradeOHLC; markstop wins simultaneousambiguity. Indicatorexit intentions persist overtradehalt. No samebar reentry.',
                    'liquidation':'Any observedmark maintenancebreach immediately latchesliquidation and forfeits modeledisolatedwallet for equity/sizing, no latermark/funding recovery. For OLD positions currentmarkOPEN maintenancebreach conservatively outranks an otherwise same-opening native exit: mark/order timestamp ordering is unknown, observed point is not an available feature. No mark fill, strategy signal, favorablecash or opening quantity improvement is inferred; wholemarkbar observation known_at remains end. Eventual genuine tradeopening only records an executionproxy; collateralneverrecoverable. Deficits preserved; any BASE/stress trigger/debt disqualifies. Historicalmaintenance/tier/insurance remainprovisional.',
                    'reopening':'ANY heldposition exit on firstpositive bar afterzero tradevolume has unknownfirst-print timing; retainpossible latefundingdebits/omitcredits AFTER new openingplans arelocked. Positive cash floor cannot silently pay excess; unfunded shortagefails. Unknownreopening exits alwaysfail eligibility, even if openingpriceisobserved. Stopintentsthroughabsenttrades nevergetmarkfills.',
                    'terminal':'No genuine trade or newlylatchedstop atsampleend => position/pendingorder remainsopen andfails, nofabricatedboundarycash. Otherwise finaltradeclose is explicitretrospective boundaryvaluation asparent; it isnot a tradingentry signal.',
                    'funding':'Actualrealized timestamp/rate maintained. ExactTpositivecredits omitted conservatively andneverfinanceorders; exactTdebits use labeled prior-completed-markproxy. Later events use computedmarkOPEN proxy onlyAFTER openingquantities/budgets locked; omitcredits if stop/TP/liquidationmayprecede. Heldage>=60s, newentriesexcluded. Pointmark atsettlementmillisecond unavailable; proxy isnot exactrealizedincome. Exactboundarytie debitonly.',
                    'risk':'Authenticobservedmark favorable/adversecorners anddaily peak-before-worst reference. Extremaordering/missedbetween-sample extrema unknown. Common10%peakDD/5%UTCdailyINITIAL-capital reference unchanged; no exactpropcontract replayclaim.',
                    'costs':{'fee_bps_each_side':5,'slippage_bps_each_side':2,'full_spread_bps':1,'double_friction_required':True,'executable_tariffs_verified':False},
                    'selection':'Unchanged commonTRAIN positivebase+double,30episodes/60days,riskbounds,zeroBASE/stressliq/debt plus2/3positiveCV. PositiveCV counts only if no unfilledterminal/unknownreopening/sparseheldmark/liq/debt. Require BASE/stress minimumavailablecash >= -1e-8 and flat finalaccount equality initial+sumcompletedPNL within 1e-6 dollars. Full base/stress primary daily adverse/favorable curves, trades and funding ledgers retained immutably. ONE highest netreturn/max(adverseDD,.25%),tiesID lockedBEFORE2025. No primary => noOOS; no substitutes or riskrescaling.',
                    'oos':'Unchanged8%geometric-monthly objective,60episodes/6fullmonths/99%mean7day5000CI lower>0,stresspositive,medianmonthpositive,>=2/3positivefullmonths,bothhalvespositive/risk/physical/sourceguards. Immutable2025confirmation binds selection/result/protocol before2026.',
                    'orders':'HistoricalpersonalnonproductionCCBYNCSA evidence only; truequotes/latency/fundingpoint/tier/contract/freshforwardstillunverified. No live/Telegram/cashpayoutcertification.'}
        shared.immutable_write(path,protocol)
    report={'phase':'frozen_before_outcomes','protocol':protocol,'protocol_sha256':lab.digest(protocol),'selected':None,
            'retrospective_target_candidate':False,'live_qualified':False,'prop_qualified':False,'telegram_enabled':False}
    if not OUTPUT.exists():write_report(report)
    return report


def verify(report):
    p=report['protocol']
    if lab.digest(p)!=report['protocol_sha256'] or p['grid']!=engine.grid():raise ValueError('Frozenmark interpretation/grid changed')
    if json.loads((DIRECTORY/'protocol.json').read_text()) != p:
        raise ValueError('Actual immutable protocol artifact differs from report')
    if p['common_objective_sha256'] != COMMON_SHA256 or p['parent_protocol_sha256'] != PARENT_PROTOCOL_SHA256:
        raise ValueError('Literal objective/parent changed')
    for path, literal in (('.local/mark-5m-complete-history/manifest.json', MARK_MANIFEST_SHA256),
                          ('.local/mark-5m-complete-history/protocol.json', MARK_PROTOCOL_SHA256),
                          ('data/mark-resolution/source-audit.json', MARK_SOURCE_AUDIT_SHA256)):
        if p['inputs'].get(path) != literal:
            raise ValueError('Literal complete mark-source registration changed')
    parent.verify(json.loads((ROOT/p['parent_report_path']).read_text()))
    for pathkey,hashkey in (('common_objective_path','common_objective_sha256'),('parent_report_path','parent_report_sha256')):
        if shared.file_hash(ROOT/p[pathkey])!=p[hashkey]:raise ValueError('Frozenparent/objective changed')
    for namespace in ('inputs','producers'):
        for path,expected in p[namespace].items():
            if shared.file_hash(ROOT/path)!=expected:raise ValueError('Boundsource/producer changed: '+path)


def _verified_mark_receipt(row):
    if row.get('price_kind')!='computed_mark_price' or row.get('quote_currency')!='USDT' or not row.get('complete_calendar') or row.get('failures') or row.get('bars')!=289152:
        raise ValueError('Authentic completecomputed marks required')
    name=row['symbol']+'-mark-5m.json'
    if row['json']!=name or shared.file_hash(MARK_SOURCE/name)!=row['json_sha256']:raise ValueError('Canonicalmark binding mismatch')
    expected={(year,month,None) for year in (2024,2025,2026) for month in range(1,13) if (year<2026 or month<=9) and (year,month)!=(2026,6)}
    expected.update((2026,6,day) for day in range(1,31))
    sources=row['sources']
    if len(sources)!=62 or {(s['year'],s['month'],s.get('day')) for s in sources}!=expected:
        raise ValueError('All32monthly+30registeredJune2026daily sources required')
    rejected=row.get('rejected_sources',[])
    if len(rejected)!=1 or rejected[0].get('used_for_prices') is not False or rejected[0].get('missing_intervals')!=288 or rejected[0].get('daily_overlap_ohlc_difference_rows')!=0 or not rejected[0].get('all30_daily_sources_verified'):
        raise ValueError('Exactregistered incompleteJune witness/unchanged overlap required')
    for source in sources+rejected:
        sha=source.get('zip_sha256','');url=source.get('source_url','')
        if source.get('checksum_verified') is not True or len(sha)!=64 or any(c not in '0123456789abcdef' for c in sha) or '/markPriceKlines/' not in url or not url.startswith('https://data.binance.vision/data/futures/um/'):
            raise ValueError('All used/witness originalofficial mark CHECKSUM receipts required')
        name=url.rsplit('/',1)[-1];raw=MARK_SOURCE/'raw'/name;checksum=MARK_SOURCE/'raw'/(name+'.CHECKSUM')
        if not raw.exists() or not checksum.exists() or shared.file_hash(raw)!=sha or checksum.read_text().split()[0].lower()!=sha:
            raise ValueError('Originalmark ZIP/CHECKSUM bytes mismatch')


def load_inputs():
    trade_features,funding=parent.load_inputs()
    manifest=json.loads((MARK_SOURCE/'manifest.json').read_text())
    if manifest['native_trade_manifest_sha256']!=shared.file_hash(SOURCE/'manifest.json') or manifest['data_protocol_id']!='binance-usdm-btceth-calculated-mark-five-minute-2024-2026-v2' or not manifest['assets_open_labels_aligned']:
        raise ValueError('Wrongmarksource/nativecalendar binding')
    marks={}
    for row in manifest['datasets']:
        _verified_mark_receipt(row)
        if row['native_trade_json_sha256']!=shared.file_hash(SOURCE/(row['symbol']+'-5m.json')):raise ValueError('Exactimmutabletrade-source binding required')
        values=json.loads((MARK_SOURCE/row['json']).read_text())
        if len(values)!=289152 or values[0]['time']!='2024-01-01T00:00:00Z' or values[-1]['known_at']!='2026-10-01T00:00:00Z':raise ValueError('Completemark nativeperiod required')
        marks[row['symbol']]=engine.MarkBars(values,source_kind=row['price_kind'])
        del values
    return engine.MarkFeatures(trade_features.bars,marks),funding


def execution_guards(result):
    m=result['metrics']
    flat=m['terminal_open_positions']==0
    reconciled = flat and math.isclose(m['final_equity'], m['initial_equity']+math.fsum(t['pnl'] for t in result['trades']), rel_tol=0, abs_tol=1e-6)
    return {'authentic_marks_available':m['historical_mark_prices_available'],
            'cash_nonnegative':math.isfinite(m['minimum_available_cash']) and m['minimum_available_cash']>=-1e-8,
            'flat_account_cashflow_reconciled':reconciled,
            'no_terminal_open_positions':m['terminal_open_positions']==0,
            'no_terminal_pending_orders':m['terminal_pending_orders']==0,
            'no_unknown_reopening_exit':m['reopening_execution_time_unknown_count']==0,
            'no_sparse_held_mark_risk':m['source_sparse_mark_held_bar_count']==0,
            'no_sparse_mark_opening_intents':m['source_sparse_mark_opening_intent_count']==0,
            'no_mark_liquidation_or_unfunded_debt':m['liquidation_count']==m['unfunded_isolated_deficit']==0}


def evaluate(result,stressed,window,role,seed):
    assessed=parent.evaluate(result,stressed,window,role,seed)
    for suffix,value in (('base',result),('doublecost',stressed)):
        for name,passed in execution_guards(value).items():assessed['checks'][name+'_'+suffix]=passed
    assessed['passed']=all(assessed['checks'].values())
    assessed['status']='historical_reference_screen_passed' if assessed['passed'] else 'not_qualified'
    return assessed


def price_decomposition(result):
    value=parent.price_decomposition(result)
    value['identity_valid_without_liquidation_or_unfunded_deficit']=value['identity_valid_without_liquidation_or_unfunded_deficit'] and result['metrics']['terminal_open_positions']==0
    return value


def train_reference(features):
    references = {}
    for symbol in engine.SYMBOLS:
        daily = features.aggregate[symbol, "daily"]
        rows = []
        previous = daily["open"][0]
        for i, stamp in enumerate(daily["times"]):
            if stamp[:10] >= "2025-01-01":
                break
            price = daily["close"][i]
            rows.append(price/previous-1)
            previous = price
        references[symbol] = rows
    return references


def train_relationships(result, references):
    values = [r["return"] for r in result["daily_returns"]]
    out = {}
    for symbol, reference in references.items():
        mx, my = math.fsum(reference)/len(reference), math.fsum(values)/len(values)
        variance = math.fsum((x-mx)**2 for x in reference)
        beta = math.fsum((x-mx)*(y-my) for x, y in zip(reference, values))/variance if variance else None
        out[symbol] = {"daily_return_correlation": stats.pearson_correlation(reference, values), "unadjusted_beta": beta}
    return {"scope": "TRAINONLY descriptive marketcorrelation/beta; not beta-neutral alpha or executablecostedbenchmark", "assets": out}


def compact(result):
    return {k: result[k] for k in ("metrics", "equity_curve", "daily_returns", "start", "end")}


def run():
    report = freeze()
    verify(report)
    if (DIRECTORY/"training_selection.json").exists():
        raise ValueError("TRAIN already completed/locked; immutable results must not be overwritten")
    features, funding = load_inputs()
    references = train_reference(features)
    training = []
    primary_evidence = None
    primary_rank = None
    for i, variant in enumerate(report["protocol"]["grid"]):
        observations = features.observations(variant)
        result = engine.simulate(features, observations, funding, variant, *shared.WINDOWS["training"])
        stress = engine.simulate(features, observations, funding, variant, *shared.WINDOWS["training"], cost_multiplier=2)
        assessed = evaluate(result, stress, shared.WINDOWS["training"], "training", 20261007+i)
        fold_results = [engine.simulate(features, observations, funding, variant, *fold) for fold in shared.FOLDS]
        folds = [r["metrics"] for r in fold_results]
        assessed["checks"]["two_of_three_training_folds_positive"] = sum(r["metrics"]["return_pct"] > 0 and all(execution_guards(r).values()) for r in fold_results) >= 2
        assessed["passed"] = all(assessed["checks"].values())
        assessed["status"] = "historical_reference_screen_passed" if assessed["passed"] else "not_qualified"
        training.append({"id": variant["id"], "variant": variant, "metrics": result["metrics"],
                         "stress_metrics": stress["metrics"], "target": assessed, "folds": folds,
                         "passed": assessed["passed"], "score": assessed["selection_score_net_return_over_drawdown"],
                         "decomposition": price_decomposition(result), "relationships": train_relationships(result, references)})
        if assessed['passed']:
            rank=(-assessed['selection_score_net_return_over_drawdown'],variant['id'])
            if primary_rank is None or rank<primary_rank:
                primary_rank=rank
                primary_evidence={'protocol_sha256':report['protocol_sha256'],'selected':variant['id'],
                                  'base':result,'double_cost':stress}
        report.update(phase="training_in_progress", training=training)
        write_report(report)
        print(f"Authenticmark96 TRAIN {i+1}/96 {variant['id']} net={result['metrics']['return_pct']:+.4f}% stress={stress['metrics']['return_pct']:+.4f}% episodes={result['metrics']['trade_count']} passed={assessed['passed']}", flush=True)
    surviving = sorted([r for r in training if r["passed"]], key=lambda r: (-r["score"], r["id"]))
    selected = surviving[0]["id"] if surviving else None
    lock = {"protocol_sha256": report["protocol_sha256"], "training_results_sha256": lab.digest(training),
            "selected": selected, "locked_before_validation": True, "locked_at": shared.now()}
    if selected is not None:
        if primary_evidence is None or primary_evidence['selected']!=selected:
            raise ValueError('Primary full ledgers must be retained from the original TRAIN run')
        shared.immutable_write(DIRECTORY/'training_primary_evidence.json',primary_evidence)
        lock['training_primary_evidence_sha256']=lab.digest(primary_evidence)
    shared.immutable_write(DIRECTORY/"training_selection.json", lock)
    shared.immutable_write(DIRECTORY/"training_results.json", training)
    report.update(selected=selected, selection_lock=lock, selection_lock_sha256=lab.digest(lock))
    if selected is None:
        report.update(phase="completed_no_training_candidate", reason="No candidate passed all frozen TRAIN economic/risk/activity/CV gates. Lowepisodecount is evidence insufficiency, not necessarilynegativepriceedge. 2025/2026strategyperformance remains unopened.")
    else:
        report.update(phase="training_complete_primary_locked_oos_unopened", reason="One fixed TRAINprimary locked; this run is TRAINONLY. 2025/2026strategyperformance has not been computed; onlythisprimary mayproceed through frozen screens.")
    write_report(report)
    return report


def verify_validation_artifacts(report, selected):
    confirmation=json.loads((DIRECTORY/'validation-confirmation.json').read_text())
    expected={'selected':selected,'selection_lock_sha256':report['selection_lock_sha256'],
              'validation_result_sha256':lab.digest(report['validation']),
              'validation_passed':True,'protocol_sha256':report['protocol_sha256']}
    if confirmation!=expected or not report['validation']['target']['passed']:
        raise ValueError('Immutable validation confirmation required before opening2026')
    actual_result=json.loads((DIRECTORY/'validation_result.json').read_text())
    if actual_result!=report['validation']:
        raise ValueError('Actual immutable validation result differs from confirmed report')
    evidence=json.loads((DIRECTORY/'validation_evidence.json').read_text())
    if lab.digest(evidence)!=actual_result['full_evidence_sha256'] or evidence['selected']!=selected or evidence['protocol_sha256']!=report['protocol_sha256']:
        raise ValueError('Immutable validated primary ledgers required before opening2026')


def evaluate_locked():
    report = json.loads(OUTPUT.read_text())
    verify(report)
    selected = report.get("selected")
    if not selected:
        raise ValueError("No eligible lockedTRAINprimary; OOS remains unopened")
    lock = json.loads((DIRECTORY/"training_selection.json").read_text())
    if lab.digest(lock) != report["selection_lock_sha256"] or lock["selected"] != selected or lab.digest(report["training"]) != lock["training_results_sha256"]:
        raise ValueError("Registered TRAINprimary/results lock changed")
    if json.loads((DIRECTORY/'training_results.json').read_text()) != report['training']:
        raise ValueError('Immutable original TRAIN rows differ from report')
    evidence=json.loads((DIRECTORY/'training_primary_evidence.json').read_text())
    if lab.digest(evidence)!=lock['training_primary_evidence_sha256'] or evidence['selected']!=selected or evidence['protocol_sha256']!=report['protocol_sha256']:
        raise ValueError('Immutable primary full ledgers changed')
    variant = next(v for v in report["protocol"]["grid"] if v["id"] == selected)
    features, funding = load_inputs()
    observations = features.observations(variant)
    for role in ("validation", "final"):
        if role == "final":
            verify_validation_artifacts(report,selected)
        if (DIRECTORY/(role+"_result.json")).exists():
            raise ValueError("Already-opened locked OOS results cannot be rerun/overwritten")
        result = engine.simulate(features, observations, funding, variant, *shared.WINDOWS[role])
        stress = engine.simulate(features, observations, funding, variant, *shared.WINDOWS[role], cost_multiplier=2)
        assessed = evaluate(result, stress, shared.WINDOWS[role], role, 20261007+(1000 if role == "validation" else 2000))
        full_evidence={'protocol_sha256':report['protocol_sha256'],'selected':selected,'base':result,'double_cost':stress}
        record = {**compact(result), "stress":compact(stress), "stress_metrics": stress["metrics"], "target": assessed,
                  "full_evidence_sha256":lab.digest(full_evidence),
                  "decomposition": price_decomposition(result)}
        shared.immutable_write(DIRECTORY/(role+'_evidence.json'),full_evidence)
        shared.immutable_write(DIRECTORY/(role+"_result.json"), record)
        shared.immutable_write(DIRECTORY/(role+"_trades.json"), result["trades"])
        shared.immutable_write(DIRECTORY/(role+"_funding.json"), result["funding_ledger"])
        report[role] = record
        if not assessed["passed"]:
            report.update(phase="completed_locked_"+role+"_failed", reason="The sole lockedprimary failed thecommon8%-monthlyscreen. Laterwindowunopened; no substitute,resizing orchangedexits.")
            write_report(report)
            return report
        report["phase"] = role+"_complete"
        if role == "validation":
            shared.immutable_write(DIRECTORY/"validation-confirmation.json",
                                   {"selected": selected, "selection_lock_sha256": report["selection_lock_sha256"],
                                    "validation_result_sha256": lab.digest(record), "validation_passed": True,
                                    "protocol_sha256": report["protocol_sha256"]})
        write_report(report)
    report.update(phase="completed_locked_final", retrospective_target_candidate=True,
                  reason="Locked historical reference screenspassed only; adaptivemarket/executionproxies/freshforward/exactpropcontract remainunverified. No liveorders/Telegram.")
    write_report(report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze", action="store_true")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--evaluate-locked", action="store_true")
    args = parser.parse_args()
    report = evaluate_locked() if args.evaluate_locked else run() if args.run else freeze()
    print(json.dumps({"phase": report["phase"], "protocol_sha256": report["protocol_sha256"], "variants": len(report["protocol"]["grid"]), "selected": report.get("selected")}))


if __name__ == "__main__":
    main()
