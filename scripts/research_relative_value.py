#!/usr/bin/env python3
"""Frozen BTCETH perpetual-pair research against the8%-monthly objective."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from propdesk import relative_value as engine, research_lab as lab, market, target_evaluation as target
from scripts import research_broad as shared

DIRECTORY = ROOT/"data/relative-value-research"
SOURCE = ROOT/".local/funding-history"
OUTPUT = ROOT/"docs/relative-value-research.json"
MARKDOWN = ROOT/"docs/RELATIVE_VALUE_RESEARCH.md"


def write_report(report):
    OUTPUT.write_text(json.dumps(report, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    lines = ["# Relative-value perpetual-pair research", "", f"Phase: **{report['phase']}**.", "",
             f"Protocol SHA256: `{report['protocol_sha256']}`.", "",
             "48 fixed BTCETH log-price residual variants; all2024–2026 market history has already been inspected generally. Adaptive exploratory study, no blind-history claim.", "",
             "Both actual USD-M perpetual legs, historical funding,5bps/side fees+2bps adverse slippage+1bp full spread. Mark-price/maintenance/quantity assumptions remain provisional; no live or prop payout certification.", ""]
    if report.get("training"):
        lines += [f"Training variants: {len(report['training'])}; common TRAIN survivors: {sum(r['passed'] for r in report['training'])}.", ""]
    if report.get("reason"):
        lines += [report["reason"], ""]
    for phase in ("validation", "final"):
        if report.get(phase):
            row = report[phase]
            lines += [f"{phase.capitalize()} locked-primary net return **{row['metrics']['return_pct']:+.4f}%**, geometric monthly **{row['target']['base']['geometric_monthly_return']*100:+.4f}%**, trades **{row['metrics']['trade_count']}**, target screen **{row['target']['passed']}**.", ""]
    lines += ["No winner substitution or rescaling after validation/final failure.8% monthly equivalent is not a guarantee of8% each month, a withdrawal or a payout. Telegram/exchange execution remain disabled.", ""]
    MARKDOWN.write_text("\n".join(lines), encoding="utf-8")


def freeze():
    path = DIRECTORY/"protocol.json"
    if path.exists():
        protocol = json.loads(path.read_text())
    else:
        manifest = json.loads((SOURCE/"manifest.json").read_text())
        files = {str(p.relative_to(ROOT)): shared.file_hash(p) for p in
                 [SOURCE/"manifest.json", SOURCE/"BTCUSDT-1h.json", SOURCE/"ETHUSDT-1h.json", SOURCE/"BTCUSDT-funding.json", SOURCE/"ETHUSDT-funding.json"]}
        producers = ["propdesk/relative_value.py", "scripts/research_relative_value.py", "propdesk/target_evaluation.py", "propdesk/research_lab.py", "propdesk/research_stats.py", "scripts/research_broad.py"]
        protocol = {"version": "adaptive-btceth-perpetual-relative-value-v1", "frozen_at": shared.now(),
                    "common_objective_path": "docs/EIGHT_PERCENT_PROTOCOL.json",
                    "common_objective_sha256": shared.file_hash(ROOT/"docs/EIGHT_PERCENT_PROTOCOL.json"),
                    "scope": "Adaptiveexploratory;2024–2026pricesgenerallyinspected inpriorstudies. New-economic-family48boundedvariants, no globallyblindhistoryclaim.",
                    "economic_hypothesis": "BTC/ETH relative deviations sometimes revert after controlling contemporaneous logprice relation. A rolling regression byitself cannot establish stationarycointegration or economicalpha.",
                    "grid": engine.grid(), "windows": shared.WINDOWS, "training_folds": shared.FOLDS,
                    "producers": {p: shared.file_hash(ROOT/p) for p in producers}, "inputs": files,
                    "source_protocol_sha256": manifest["protocol_sha256"],
                    "source": "OriginalCHECKSUM-verifiedBinanceUSDMperpetualOHLCandrealizedfundingsettlements; bothlong/short actualderivativelegs, not syntheticspotshort.",
                    "ols": "Priorfullyclosed168/336/720hour rollingOLS logBTC=alpha+beta*logETH+residual; requirebeta in[.25,3] andsigma>=.0001. Entryz>=1.5/2 and<3.5; sign reversal trade, beta/alpha/sigma frozenentry.",
                    "exits": "Entry nextopen iffrozenresidualstillbetween targetandstop. Exitnextopenafterpriorclosedfrozenresidual reaches0/.5 target, ormaxhold72/168h. Openingresidualgapstop3.5sigma prioritized. Intrabartwoassetspreadstop uses individuallyadverseOHLCendpoints conservatively; exact spreadstoppath unknowable. NointrabarTPcredit.",
                    "capital": {"initial_total_equity": 100000, "risk_per_trade_fraction_grid": [.0025, .005],
                                "risk_size": "BTCnotional=initialRiskBudget/((stop_z+direction*opening_z)*sigma), approximatelogspreadrisk; gap/cost/adversepathcanexceedbudget. ETHnotional=beta*BTCnotional.",
                                "max_entry_gross_to_initial_capital": 2, "isolated_leverage": 2,
                                "collateral": "Bothlegmargins andentryfees reservedfrompositivefreecash. IsolatedPnLandfunding remaininlegwallet untilclose; no collateralreinjection. Walletmarkfloor0; proxyliquidationforfeitswholelegmargin, gapdeficitsreported not silently financed.",
                                "maintenance_assumption": .005, "liquidation_fee_assumption": .005,
                                "liquidation_status": "ProvisionaltradeOHLCproxy instead of unavailablehistoricalofficialmark/tier/insurance. Any liquidation/deficit prevents qualification; no exchangeinsuranceguarantee.",
                                "quantity_step_assumption": {"BTCUSDT": .001, "ETHUSDT": .001}},
                    "costs": {"fee_bps_per_leg_per_side": 5, "slippage_bps_per_leg_per_side": 2, "full_spread_bps_per_leg": 1,
                              "all_four_leg_sides_charged": True, "double_friction_stress": True,
                              "funding_stress": "Extra diagnostic doublesnegativepayments, halvespositivecredits; never substitutesactualsettledbaserates.",
                              "executable_tariffs_verified": False},
                    "funding_timeline": "Exactrecordedsettlementtimestamp retained. ExactTchargesoldheldpositions beforeTopenorders; eventT+.002occursAFTERTopenorders, onlycurrentremainingposition held>=60s entitled. Newentriescannotcaptureentry-hour funding; openexits avoidlaterfunding. Realizedfutureevent never financesopenorder. Markpriceunavailable=>baropenpriceproxyprovisional. Stop/eventchronologyunknown=>omitpositivecreditsretainadversecharges andflagambiguity.",
                    "selection": "CommonTRAIN net+doublecostpositive,adverseDD<=10,dailyreference<=5%initial,30trades60days plus2of3CVfoldspositive; ONEhighest netreturn/max(adverseDD,.25%),tiesID LOCKEDBEFORE2025. No alternative aftervalidationfailure. Validation common8%-monthlygate, thenexactlockedprimary2026onlyifpasses.",
                    "target": {"monthly_geometric_return_minimum": .08, "out_of_sample_completed_episodes_minimum": 60,
                               "full_calendar_months_minimum": 6, "mean_daily_ci99_lower_positive": True,
                               "doublecost_monthly_positive": True, "median_month_positive": True,
                               "positive_month_fraction_minimum": 2/3, "both_chronological_halves_positive": True,
                               "adverse_drawdown_maximum": .10, "daily_reference_loss_initial_maximum": .05,
                               "days_train_minimum": 60, "episodes_train_minimum": 30,
                               "daily_risk_reference": "UTCcalendar priorclosemarked equity to dailyadverse equity dividedbyINITIAL100k; notFTMOPraguerule replay",
                               "monthly_8_not_each_month_guarantee": True, "cash_payout_verified": False},
                    "inference": "Unmodifiedcommon target_evaluation:99%7daycircularmovingblocks5000resamples; conditional approximate understationarity, noadaptive-data-erasure.",
                    "training_diagnostics": "RollingOLSresidual AR1/half-life/Hurstapprox andbeta distributions descriptiveTRAINONLY; rollingmodel caninducemeanreversion, no formalcointegrationqualification.",
                    "orders": "No actualexchangeorder/withdrawal/challenge/Telegram. SourceCCBYNCSApersonalnonproductiondata. No after-final risk/sizing search."}
        shared.immutable_write(path, protocol)
    report = {"phase": "frozen_before_outcomes", "protocol": protocol, "protocol_sha256": lab.digest(protocol),
              "retrospective_target_candidate": False, "live_qualified": False, "prop_qualified": False, "telegram_enabled": False}
    if not OUTPUT.exists():
        write_report(report)
    return report


def verify(report):
    protocol = report["protocol"]
    if lab.digest(protocol) != report["protocol_sha256"] or protocol["grid"] != engine.grid():
        raise ValueError("Frozenprotocol/grid changed")
    if shared.file_hash(ROOT/protocol["common_objective_path"]) != protocol["common_objective_sha256"]:
        raise ValueError("Common8%-monthlyobjective changed")
    for namespace in ("inputs", "producers"):
        for p, expected in protocol[namespace].items():
            if shared.file_hash(ROOT/p) != expected:
                raise ValueError("Boundsourceorproducer changed: "+p)


def load_inputs():
    manifest = json.loads((SOURCE/"manifest.json").read_text())
    receipts = {(r["symbol"], r["kind"]): r for r in manifest["datasets"]}
    datasets, funding = {}, {}
    for symbol in engine.SYMBOLS:
        for kind, filename in (("klines", symbol+"-1h.json"), ("fundingRate", symbol+"-funding.json")):
            row = receipts[symbol, kind]
            if row["json_sha256"] != shared.file_hash(SOURCE/filename) or not row.get("complete_calendar"):
                raise ValueError("Originalofficialsourcebinding orcalendar mismatch")
            if not row.get("sources") or any(not s.get("checksum_verified") or not s["source_url"].startswith("https://data.binance.vision/data/futures/um/") for s in row["sources"]):
                raise ValueError("Everyoriginalderivativesource requiresofficialCHECKSUMverifiedreceipt")
            values = json.loads((SOURCE/filename).read_text())
            if kind == "klines":
                bars = market.validate_bars(values, max_bars=100_000)
                if market.data_fingerprint(bars) != row["data_fingerprint"] or bars[0]["time"] != "2024-01-01T00:00:00Z" or bars[-1]["time"] != "2026-09-30T23:00:00Z":
                    raise ValueError("Completeoriginalhourlypricefingerprint mismatch")
                datasets[symbol] = bars
            else:
                if len(values) != 3012:
                    raise ValueError("Complete2024-Sep2026eight-hourfundingcalendar required")
                slots = [market.utc_datetime(v["time"]).replace(microsecond=0) for v in values]
                if any((b-a).total_seconds() != 8*3600 for a, b in zip(slots, slots[1:])):
                    raise ValueError("Missingfundingeventcannotbeimputed")
                funding[symbol] = values
    return engine.PairFeatures(datasets), funding


def evaluate(result, stressed, window, role, seed):
    lows, highs = {}, {}
    for row in result["equity_curve"]:
        date = row["time"][:10]
        lows[date] = min(lows.get(date, row["worst_equity"]), row["worst_equity"])
        highs[date] = max(highs.get(date, row["best_equity"]), row["best_equity"])
    dates = [r["date"] for r in result["daily_returns"]]
    assessed = target.evaluate_period(dates, [r["return"] for r in result["daily_returns"]],
                                      [r["return"] for r in stressed["daily_returns"]], result["metrics"]["trade_count"],
                                      daily_worst_equity=[lows[d] for d in dates], daily_peak_equity=[highs[d] for d in dates],
                                      period_start=window[0], period_end_exclusive=window[1], role=role, samples=5000, seed=seed)
    assessed["checks"]["no_proxy_liquidation"] = result["metrics"]["liquidation_count"] == stressed["metrics"]["liquidation_count"] == 0
    assessed["checks"]["no_unfunded_margin_deficit"] = result["metrics"]["unfunded_isolated_deficit"] == stressed["metrics"]["unfunded_isolated_deficit"] == 0
    assessed["passed"] = all(assessed["checks"].values())
    assessed["status"] = "historical_reference_screen_passed" if assessed["passed"] else "not_qualified"
    return assessed


def training_diagnostics(features):
    out = []
    for hours in (168, 336, 720):
        rows = [r for i, r in enumerate(features.ols(hours)) if r is not None and features.times[i][:10] < "2025-01-01"]
        residuals = [r["z"]*r["sigma"] for r in rows]
        if len(residuals) < 100:
            continue
        mean = sum(residuals)/len(residuals)
        denominator = sum((x-mean)**2 for x in residuals[:-1])
        phi = sum((a-mean)*(b-mean) for a, b in zip(residuals[:-1], residuals[1:]))/denominator if denominator else None
        variances = []
        for lag in (1, 2, 4, 8, 16, 32):
            diffs = [residuals[i+lag]-residuals[i] for i in range(len(residuals)-lag)]
            avg = sum(diffs)/len(diffs)
            variance = sum((x-avg)**2 for x in diffs)/len(diffs)
            if variance > 0:
                variances.append((math.log(lag), math.log(variance)))
        mx = sum(x for x, _ in variances)/len(variances)
        my = sum(y for _, y in variances)/len(variances)
        slope = sum((x-mx)*(y-my) for x, y in variances)/sum((x-mx)**2 for x, _ in variances)
        out.append({"hedge_hours": hours, "observations": len(rows), "mean_beta": sum(r["beta"] for r in rows)/len(rows),
                    "residual_ar1_phi": phi, "approx_half_life_hours": -math.log(2)/math.log(phi) if phi is not None and 0 < phi < 1 else None,
                    "descriptive_hurst_variogram": slope/2})
    return {"scope": "TRAINONLY; rollingregressionresiduals caninducestationarity; Hurst/AR1descriptive, not EngleGrangerproof or confidence", "windows": out}


def compact(result):
    return {k: result[k] for k in ("metrics", "daily_returns", "start", "end")}


def run():
    report = freeze()
    verify(report)
    features, funding = load_inputs()
    report["training_diagnostics"] = training_diagnostics(features)
    training = []
    variants = {v["id"]: v for v in report["protocol"]["grid"]}
    for i, variant in enumerate(variants.values()):
        obs = engine.observations(features, variant)
        result = engine.simulate(features, obs, funding, variant, *shared.WINDOWS["training"])
        stress = engine.simulate(features, obs, funding, variant, *shared.WINDOWS["training"], cost_multiplier=2)
        assessed = evaluate(result, stress, shared.WINDOWS["training"], "training", 20261004+i)
        folds = [engine.simulate(features, obs, funding, variant, *fold)["metrics"] for fold in shared.FOLDS]
        assessed["checks"]["two_of_three_training_folds_positive"] = sum(f["return_pct"] > 0 for f in folds) >= 2
        assessed["passed"] = all(assessed["checks"].values())
        assessed["status"] = "historical_reference_screen_passed" if assessed["passed"] else "not_qualified"
        training.append({"id": variant["id"], "variant": variant, "metrics": result["metrics"],
                         "stress_metrics": stress["metrics"], "target": assessed, "folds": folds,
                         "passed": assessed["passed"], "score": assessed["selection_score_net_return_over_drawdown"]})
        print(f"Relativevaluetrain {i+1}/48 {variant['id']} net={result['metrics']['return_pct']:+.4f}% stress={stress['metrics']['return_pct']:+.4f}%", flush=True)
    surviving = sorted([r for r in training if r["passed"]], key=lambda r: (-r["score"], r["id"]))
    selected = surviving[0]["id"] if surviving else None
    lock = {"protocol_sha256": report["protocol_sha256"], "training_results_sha256": lab.digest(training),
            "selected": selected, "locked_before_validation": True, "locked_at": shared.now()}
    lockpath = DIRECTORY/"training_selection.json"
    if lockpath.exists():
        lock["locked_at"] = json.loads(lockpath.read_text())["locked_at"]
    shared.immutable_write(lockpath, lock)
    report.update(phase="training_complete", training=training, selected=selected,
                  selection_lock=lock, selection_lock_sha256=lab.digest(lock))
    write_report(report)
    if selected is None:
        report.update(phase="completed_no_training_candidate", reason="No relative-value variant passed frozen TRAIN cost/risk/activity/CV requirements;2025 and2026 strategyperformance remainunopened bythisstudy. No substitute orrescaling.")
        write_report(report)
        return report
    variant = variants[selected]
    obs = engine.observations(features, variant)
    for role in ("validation", "final"):
        result = engine.simulate(features, obs, funding, variant, *shared.WINDOWS[role])
        stress = engine.simulate(features, obs, funding, variant, *shared.WINDOWS[role], cost_multiplier=2)
        funding_stress = engine.simulate(features, obs, funding, variant, *shared.WINDOWS[role], funding_stress=True)
        assessed = evaluate(result, stress, shared.WINDOWS[role], role, 20261004+(1000 if role == "validation" else 2000))
        record = {**compact(result), "stress_metrics": stress["metrics"], "funding_stress_metrics": funding_stress["metrics"], "target": assessed}
        report[role] = record
        shared.immutable_write(DIRECTORY/(role+"_result.json"), record)
        shared.immutable_write(DIRECTORY/(role+"_trades.json"), result["trades"])
        report["phase"] = role+"_complete"
        write_report(report)
        if not assessed["passed"]:
            report.update(phase="completed_locked_"+role+"_failed", reason="Lockedprimaryfailedthecommon8%-monthlyevidencescreen; laterwindowunopened/noafterfailure alternative/sizing.")
            write_report(report)
            return report
    report.update(phase="completed_locked_final", retrospective_target_candidate=True,
                  reason="BothlockedOOSscreenspassedhistoricalreferencecriteriaonly; adaptivehistory/provisionalmarkexecution/exactpropcontract/freshforward remainunverified. NoTelegram/live enabled.")
    write_report(report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--freeze", action="store_true")
    args = parser.parse_args()
    report = run() if args.run else freeze()
    print(json.dumps({"phase": report["phase"], "protocol_sha256": report["protocol_sha256"], "variants": len(report["protocol"]["grid"]), "selected": report.get("selected")}))


if __name__ == "__main__":
    main()
