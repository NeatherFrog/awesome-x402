#!/usr/bin/env python3
"""Preregistered192 native perpetual FVG hypotheses; no orders or Telegram."""
from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from propdesk import liquidity_native as engine, market, research_lab as lab, target_evaluation as target
from scripts import research_broad as shared

DIRECTORY = ROOT/"data/liquidity-native-research"
SOURCE = ROOT/".local/perp-5m-history"
FUNDING = ROOT/".local/funding-history"
OUTPUT = ROOT/"docs/liquidity-native-research.json"
MARKDOWN = ROOT/"docs/LIQUIDITY_NATIVE_RESEARCH.md"
WINDOWS = {"training": ["2024-01-01", "2025-01-01"],
           "validation": ["2025-01-01", "2026-01-01"],
           "final": ["2026-01-01", "2026-10-01"]}


def write_report(report):
    OUTPUT.write_text(json.dumps(report, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    rows = ["# Native perpetual sweep / displacement / FVG research", "",
            f"Phase: **{report['phase']}**.", "", f"Protocol SHA256: `{report['protocol_sha256']}`.", "",
            "192 explicitly preregistered causal price-action configurations on genuine BTC/ETH perpetual5m candles. Signals use only completed15m/1h resamples; recorded entry zone, stop, target and invalidation. No retrospective pivots or spot short assumptions.", "",
            "Adaptive historical study: other strategies previously inspected2024–2026 markets. No globally blind claim. Complete100kphysicalcapital; .25/.5/1%perposition and .5/1/2%aggregate stoprisk;1xisolatedmargin and1xentrygross cap; actual settlementcashflows; doublefriction stress.", ""]
    if report.get("training"):
        rows += [f"TRAIN evaluated: **{len(report['training'])}/192**; eligible: **{sum(r['passed'] for r in report['training'])}**.", ""]
        best = sorted(report["training"], key=lambda r: (-r["metrics"]["return_pct"], r["id"]))[:5]
        rows += ["| TRAIN ID | Net % | Double costs % | Trades | Eligible |", "|---|---:|---:|---:|---|"]
        for r in best:
            rows.append(f"| {r['id']} | {r['metrics']['return_pct']:+.4f} | {r['stress_metrics']['return_pct']:+.4f} | {r['metrics']['trade_count']} | {r['passed']} |")
        rows += ["", "Top TRAIN rows are diagnostic only; eligibility and the immutable ONE-primary lock govern selection.", ""]
    if report.get("reason"):
        rows += [report["reason"], ""]
    for phase in ("validation", "final"):
        if report.get(phase):
            r = report[phase]
            monthly = r['target']['base']['geometric_monthly_return']
            monthly_text = "not defined (account insolvency)" if monthly is None else f"{monthly*100:+.4f}%"
            rows += [f"{phase.capitalize()} ONE-primary net **{r['metrics']['return_pct']:+.4f}%**, monthly equivalent **{monthly_text}**, double costs **{r['stress_metrics']['return_pct']:+.4f}%**, completed trades **{r['metrics']['trade_count']}**, passed **{r['target']['passed']}**.", "",
                     f"Failed checks: {', '.join(k for k,v in r['target']['checks'].items() if not v) or 'none'}.", ""]
    rows += ["Zero-volume archive bars cannot prove fills; affected signals are excluded and any held exposure flags an unverified mark gap that disqualifies the period. Native/hourly provider differences are retained with raw source receipts.", "",
             "TradeOHLC proxies official marks and assumes historical filters/maintenance/fees, uncertain intrabar funding entitlement, USDT/USD parity and queue availability. Adverse daily envelopes are conservative bounds. ArchiveCC-BY-NC-SA is personal/nonproduction research. A historical screen does not certify a prop contract, payout, future profit or licensed executable data.", "",
             "No alternative substitution, after-validation scaling, exchange orders or Telegram.8%monthly equivalent is not8%everymonth or cash received. Full primary ledgers are localgzip artifacts with hashes; compact results retain all rejected variants.", ""]
    MARKDOWN.write_text("\n".join(rows), encoding="utf-8")


def freeze():
    path = DIRECTORY/"protocol.json"
    if path.exists():
        protocol = json.loads(path.read_text())
    else:
        producers = ["propdesk/liquidity_native.py", "scripts/research_liquidity_native.py",
                     "tests/test_liquidity_native.py", "propdesk/funding_lab.py", "propdesk/market.py",
                     "propdesk/research_lab.py", "propdesk/research_stats.py", "propdesk/target_evaluation.py",
                     "scripts/research_broad.py"]
        inputs = [SOURCE/"manifest.json", FUNDING/"manifest.json",
                  ROOT/".local/perp-5m-resample-audit.json", ROOT/".local/perp-5m-resample-source-confirmation.json"]
        for s in engine.SYMBOLS:
            inputs += [SOURCE/(s+"-5m.json"), FUNDING/(s+"-funding.json")]
        protocol = {"schema": 1, "id": "native-perpetual-causal-sweep-fvg-v1", "frozen_at": shared.now(),
                    "human_protocol_path": "docs/LIQUIDITY_NATIVE_PROTOCOL.md",
                    "human_protocol_sha256": shared.file_hash(ROOT/"docs/LIQUIDITY_NATIVE_PROTOCOL.md"),
                    "common_objective_path": "docs/EIGHT_PERCENT_PROTOCOL.json",
                    "common_objective_sha256": shared.file_hash(ROOT/"docs/EIGHT_PERCENT_PROTOCOL.json"),
                    "grid": engine.grid(), "windows": WINDOWS,
                    "producers": {p: shared.file_hash(ROOT/p) for p in producers},
                    "inputs": {str(p.relative_to(ROOT)): shared.file_hash(p) for p in inputs},
                    "trial_disclosure": "64economic/time hypotheses ×3predeclared risks=192configurations plus all previous adaptive research. Coststresses are scenarios ofsamehypothesis; prior2024–2026markets already inspected generally, no globallyblindclaim.",
                    "signal": "Completed15m/1h;strictprior24/72barrollinghigh/low sweepwithclosebackinside;latestunconsumed sweep expires6bars orstopinvalidation. Latermiddlebody>=.6/1ATR20 knownbeforemiddle;thirdbarconfirmsFVG. OptionalpriorEMA24/96 directionalcontext. Firstsubsequentmidpointlimit;stopactualsweepextreme+.1ATRknownbeforesweep;fixedRR1.5/2.5;exclusiveexpiry4/12bars;24hhold.",
                    "execution": "Each5mopening plans bothpending quantities/margin/fees/risk fromalreadyknownaccount anddeterministicBTCthenETH reservations BEFOREfuturetouches. Unfilledreservation cannotfinanceotherasset duringthatinterval;releasednextopen. Knownopening stop/liq/TP/timeexits precede intrabarentry;gapacrosslimit+stop givesconservativeentryatlimitthenadverseopenstop. Bothintrabarstop/TP=>stop;newentrybarnoprofittargetcredit. No samebarexit/reentry.",
                    "capital": {"initial_total_equity": 100000, "risk_per_position_current_equity": [.0025, .005, .01],
                                "aggregate_entry_stop_risk_current_equity": [.005, .01, .02], "max_positions": 2,
                                "max_entry_gross_initial_capital": 1, "isolated_leverage": 1,
                                "sizing_costs": "Roundtripmodeledstopfill+fees includedinriskunit;gaps/funding/uncertainmarks canexceedbudget.",
                                "collateral": "Paymargin+entryfee frompositivecash; isolatedmargin+funding+pricePnL remainswalletuntilclose. Noinjection/credit/extraidlecapital. Proxyliquidation forfeitsmargin,deficitsreportednotfinanced.",
                                "maintenance_proxy": .005, "liquidation_fee_proxy": .005, "quantity_step_proxy": .001},
                    "costs": {"taker_fee_bps_each_side": 5, "adverse_slip_bps_each_side": 2,
                              "full_spread_bps": 1, "double_all_friction": True, "historical_tariffs_verified": False},
                    "funding": "Actualrealizedexactmssettlementcashflows,nosignalforecast. Oldheldpositions payatT beforeopenexit;positivecreditsrequirecertain>=60sheld andnoambiguouspriorstop/exit/liquidation. NewintrabarentryearliestT/latestT+5m;possiblenegativeentitlementretained,uncertainpositiveexcluded. Precreditmaintenancecheck;negativefeesbeforepostfundingmaintenance. Eventexactfinish:debitretained/creditexcluded;eventafterfinishnone. Markmissing=>knownnativeopenproxy.",
                    "missing_execution": "Noexec onzero-volume bars;FVG/sweepcandleswithanynativeabsenceexcluded. Heldzero-volumecalendar preservedusingpreviousknowntradedcloseproxy andcountedunresolved;any suchheldperiodineligible. Unknownmark riskcannotbeprovedwithclosingquotes.",
                    "selection": "All192TRAINbase/doublecost withcommon gate+zeroliquidation/deficit/unresolvedheldquote+accountreconciliation. ONEbest netreturn/max(adverseDD,.25%)tieID lockedbefore2025. 2025common8%gate thenconfirmationlockbeforeone2026final;noalternativeorresizingafterfailure.",
                    "inference": "Unchangedcommon target_evaluation,completecalendarUTCtotalaccountdailycloses,best/worstconservativebounds;99%7daycircularblockbootstrap5000 conditionalstationarity;30TRAIN/60OOScompletedtrades,60days/6OOSfullmonths;8%monthlygeometric OOS,noeverymonthguarantee.",
                    "source": "OfficialBinanceUSDM native5m+funding originalCHECKSUMreceipts;providerhourlydifferences retained ratherthan substituted. CC-BY-NC-SA personalnonproductionresearch.",
                    "limits": "Actualofficialhistoricalmark/tier/filters/queue/tariff,USDTparity,contract/payout/data-productionlicense unknown. Conservativeenvelopes maycombinetimes. No livequalification/orders/Telegram/purchases."}
        shared.immutable_write(path, protocol)
    if OUTPUT.exists():
        report = json.loads(OUTPUT.read_text())
    else:
        report = {"phase": "frozen_before_outcomes", "protocol": protocol,
                  "protocol_sha256": lab.digest(protocol), "retrospective_target_candidate": False,
                  "live_qualified": False, "prop_qualified": False, "telegram_enabled": False}
        write_report(report)
    return report


def verify(report):
    protocol = report["protocol"]
    if protocol != json.loads((DIRECTORY/"protocol.json").read_text()) or lab.digest(protocol) != report["protocol_sha256"] or protocol["grid"] != engine.grid():
        raise ValueError("Frozenprotocol/grid changed")
    for kind in ("inputs", "producers"):
        for p, digest in protocol[kind].items():
            if shared.file_hash(ROOT/p) != digest:
                raise ValueError("Frozen "+kind+" changed: "+p)
    for prefix in ("human_protocol", "common_objective"):
        if shared.file_hash(ROOT/protocol[prefix+"_path"]) != protocol[prefix+"_sha256"]:
            raise ValueError("Frozen objective/protocol changed")


def load_inputs():
    native = json.loads((SOURCE/"manifest.json").read_text())
    fund = json.loads((FUNDING/"manifest.json").read_text())
    datasets, funding = {}, {}
    for s in engine.SYMBOLS:
        row = next(r for r in native["datasets"] if r["symbol"] == s and r["interval"] == "5m")
        frow = next(r for r in fund["datasets"] if r["symbol"] == s and r["kind"] == "fundingRate")
        for receipt, path in ((row, SOURCE/(s+"-5m.json")), (frow, FUNDING/(s+"-funding.json"))):
            if not receipt.get("complete_calendar") or receipt["json_sha256"] != shared.file_hash(path):
                raise ValueError("Exactcompleteoriginal source binding required")
            if not receipt.get("sources") or any(not src.get("checksum_verified") or not src["source_url"].startswith("https://data.binance.vision/data/futures/um/") for src in receipt["sources"]):
                raise ValueError("Allsources requireofficialarchiveCHECKSUMverifiedreceipt")
        datasets[s] = json.loads((SOURCE/(s+"-5m.json")).read_text())
        if market.data_fingerprint(datasets[s]) != row["data_fingerprint"]:
            raise ValueError("Nativecanonicalfingerprint mismatch")
        funding[s] = json.loads((FUNDING/(s+"-funding.json")).read_text())
        events = engine.validate_events(funding[s])
        if not events or events[0]["_stamp"] > market.utc_datetime('2024-01-01T08:00:01Z') or events[-1]["_stamp"] < market.utc_datetime('2026-09-30T16:00:00Z'):
            raise ValueError("Funding events do not cover bothcalendar edges")
    return engine.Features(datasets, funding)


def assess(base, stress, window, role, seed):
    daily, sd = base["daily"], stress["daily"]
    if [r["date"] for r in daily] != [r["date"] for r in sd]:
        raise ValueError("Stresscalendar mismatch")
    if any(r['equity'] <= 0 or r['return'] <= -1 for r in daily+sd):
        return {"role": role, "passed": False, "status": "not_qualified",
                "checks": {"positive_account_equity_every_day": False},
                "base": {"total_return": base['metrics']['return_pct']/100,
                         "geometric_monthly_return": None},
                "double_cost_stress": {"geometric_monthly_return": None},
                "risk": {"max_account_drawdown": 1.0},
                "selection_score_net_return_over_drawdown": -1.0,
                "reason": "Accountinsolvencycannotqualify;geometricinferenceundefined.Norescalingorimputation."}
    result = target.evaluate_period([r["date"] for r in daily], [r["return"] for r in daily],
             [r["return"] for r in sd], base["metrics"]["trade_count"],
             daily_worst_equity=[r["worst_equity"] for r in daily],
             daily_peak_equity=[r["best_equity"] for r in daily],
             period_start=window[0], period_end_exclusive=window[1], role=role, seed=seed)
    for prefix, scenario in (("base", base), ("double_cost", stress)):
        m = scenario["metrics"]
        result["checks"].update({prefix+"_zero_liquidation": m["liquidation_count"] == 0,
                                prefix+"_zero_unfunded_deficit": m["unfunded_isolated_deficit"] == 0,
                                prefix+"_zero_unresolved_absent_trade_exposure": m["unresolved_absent_trade_exposure_bars"] == 0,
                                prefix+"_account_pnl_reconciled": m["equity_pnl_reconciliation_error"] < 1e-7})
    result["passed"] = all(result["checks"].values())
    result["status"] = "historical_reference_screen_passed" if result["passed"] else "not_qualified"
    return result


def save_ledger(result, phase, scenario):
    path = ROOT/".local/liquidity-native-research"/(phase+"-"+scenario+".json.gz")
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(result, separators=(",", ":"), allow_nan=False).encode()
    compressed = gzip.compress(payload, mtime=0)
    if path.exists() and path.read_bytes() != compressed:
        raise ValueError("Immutableprimaryledger differs")
    path.write_bytes(compressed)
    return {"path": str(path.relative_to(ROOT)), "gzip_sha256": shared.file_hash(path),
            "raw_sha256": __import__('hashlib').sha256(payload).hexdigest(), "bytes": len(compressed)}


def run():
    report = freeze()
    verify(report)
    if report["phase"].startswith("completed_"):
        return report
    features = load_inputs()
    variants = report["protocol"]["grid"]
    training = report.setdefault("training", [])
    if len(training) > len(variants) or any(r["id"] != v["id"] or r["variant"] != v for r, v in zip(training, variants)):
        raise ValueError("Trainingresume must be exact registered variant prefix")
    for index in range(len(training), len(variants)):
        v = variants[index]
        signals = engine.setups(features, v)
        base = engine.simulate(features, signals, *WINDOWS["training"], risk_fraction=v["risk_fraction"])
        stress = engine.simulate(features, signals, *WINDOWS["training"], cost_multiplier=2, risk_fraction=v["risk_fraction"])
        evaluated = assess(base, stress, WINDOWS["training"], "training", 20261002+index)
        training.append({"id": v["id"], "variant": v, "metrics": base["metrics"],
                         "stress_metrics": stress["metrics"], "target": evaluated,
                         "passed": evaluated["passed"], "score": evaluated["selection_score_net_return_over_drawdown"]})
        report["phase"] = "training_in_progress"
        write_report(report)
        print(f"NativeFVG TRAIN{index+1}/192 {v['id']} net={base['metrics']['return_pct']:+.4f}% double={stress['metrics']['return_pct']:+.4f}% trades={base['metrics']['trade_count']} eligible={evaluated['passed']}", flush=True)
    eligible = sorted((r for r in training if r["passed"]), key=lambda r: (-r["score"], r["id"]))
    selected = eligible[0]["id"] if eligible else None
    lockpath = DIRECTORY/"training-selection.json"
    lock = {"protocol_sha256": report["protocol_sha256"], "training_sha256": lab.digest(training),
            "selected": selected, "locked_before_validation": True, "locked_at": shared.now()}
    if lockpath.exists():
        lock["locked_at"] = json.loads(lockpath.read_text())["locked_at"]
    shared.immutable_write(lockpath, lock)
    report.update(selected=selected, selection_lock=lock, selection_lock_sha256=lab.digest(lock), phase="training_complete")
    write_report(report)
    if selected is None:
        report.update(phase="completed_no_training_candidate", reason="None of192nativeFVG configurations passed registered TRAIN costs/risk/activity/source gates. No2025/2026strategyperformance computed, no substitute/rescaling.")
        write_report(report)
        return report
    variant = next(v for v in variants if v["id"] == selected)
    signals = engine.setups(features, variant)
    if "training_primary" not in report:
        primary = next(r for r in training if r["id"] == selected)
        base = engine.simulate(features, signals, *WINDOWS["training"], risk_fraction=variant["risk_fraction"])
        stress = engine.simulate(features, signals, *WINDOWS["training"], cost_multiplier=2, risk_fraction=variant["risk_fraction"])
        if base["metrics"] != primary["metrics"] or stress["metrics"] != primary["stress_metrics"]:
            raise ValueError("LockedTRAINprimary failed deterministic replay")
        report["training_primary"] = {"variant": variant, "metrics": base["metrics"],
                                       "stress_metrics": stress["metrics"], "daily": base["daily"],
                                       "stress_daily": stress["daily"],
                                       "raw_ledger": {"base": save_ledger(base, "training", "base"),
                                                      "double_cost": save_ledger(stress, "training", "double_cost")}}
        write_report(report)
    for phase in ("validation", "final"):
        if phase not in report:
            base = engine.simulate(features, signals, *WINDOWS[phase], risk_fraction=variant["risk_fraction"])
            stress = engine.simulate(features, signals, *WINDOWS[phase], cost_multiplier=2, risk_fraction=variant["risk_fraction"])
            checked = assess(base, stress, WINDOWS[phase], phase, 20261080 if phase == "validation" else 20261081)
            report[phase] = {"variant": variant, "metrics": base["metrics"], "stress_metrics": stress["metrics"],
                             "target": checked, "daily": base["daily"], "stress_daily": stress["daily"],
                             "raw_ledger": {"base": save_ledger(base, phase, "base"), "double_cost": save_ledger(stress, phase, "double_cost")}}
            report["phase"] = phase+"_complete"
            write_report(report)
        row = report[phase]
        if not row["target"]["passed"]:
            report.update(phase="completed_"+phase+"_failed", reason="The immutable ONE-primary failed registered "+phase+" gates; no replacement or post-outcome sizing. "+("2026strategyperformance remains unopened." if phase == "validation" else "No historically qualified8%-monthly candidate."))
            write_report(report)
            return report
        if phase == "validation":
            confirm_path = DIRECTORY/"validation-confirmation.json"
            confirmation = {"protocol_sha256": report["protocol_sha256"], "selection_lock_sha256": report["selection_lock_sha256"],
                            "validation_sha256": lab.digest(row), "selected": selected,
                            "locked_before_final": True, "locked_at": shared.now()}
            if confirm_path.exists():
                confirmation["locked_at"] = json.loads(confirm_path.read_text())["locked_at"]
            shared.immutable_write(confirm_path, confirmation)
            report.update(confirmation_lock=confirmation, confirmation_lock_sha256=lab.digest(confirmation))
            write_report(report)
    report.update(phase="completed_retrospective_target_candidate", retrospective_target_candidate=True,
                  reason="ONE candidate passed fixedhistorical proxy screens. Approvedcontract/executablemarks/forwardproof/license remainrequired; live/prop/Telegramdisabled.")
    write_report(report)
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--freeze", action="store_true")
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()
    if not (args.freeze or args.run):
        parser.error("Choose --freeze or --run")
    report = run() if args.run else freeze()
    verify(report)
    print(json.dumps({k: report.get(k) for k in ("phase", "protocol_sha256", "selected", "retrospective_target_candidate")}))


if __name__ == "__main__":
    main()
