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
from propdesk import native_crypto_trend as engine, research_lab as lab, market
from propdesk import target_evaluation as target, research_stats as stats
from scripts import research_broad as shared

DIRECTORY = ROOT/"data/native-crypto-trend-research"
SOURCE = ROOT/".local/perp-5m-history"
FUNDING_SOURCE = ROOT/".local/funding-history"
OUTPUT = ROOT/"docs/native-crypto-trend-research.json"
MARKDOWN = ROOT/"docs/NATIVE_CRYPTO_TREND_RESEARCH.md"


def write_report(report):
    temporary = OUTPUT.with_suffix(".tmp")
    temporary.write_text(json.dumps(report, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    temporary.replace(OUTPUT)
    lines = ["# Native perpetual trend/context research", "", f"Phase: **{report['phase']}**.", "",
             f"Protocol SHA256: `{report['protocol_sha256']}`.", "",
             "96 hierarchical variants: eight economic configurations × two decision resolutions × three risk budgets × two daily-ATR stops. Three hypothesis families; correlated parameters are not 96 independent discoveries.", "",
             "Actual CHECKSUM-verified BTC/ETH USD-M perpetual 5m trade candles and exact historical funding timestamps. Hourly/daily closed-bar decisions; no spot/derivative price mixing. Adaptive exploratory 2024–2026 history already inspected generally.", "",
             "One physical $100,000 account, isolated2x collateral,5bps fees +2bps slippage +1bp full spread per side; doubled friction stress. Mark/bid/ask/tier/execution assumptions remain provisional.", ""]
    training = report.get("training", [])
    if training:
        lines += [f"TRAIN variants completed: **{len(training)}**; frozen TRAIN survivors: **{sum(r['passed'] for r in training)}**.", ""]
        best = max(training, key=lambda r: r["metrics"]["return_pct"])
        m = best["metrics"]
        lines += [f"Best TRAIN net result (diagnostic, not selected unless it passes): `{best['id']}` **{m['return_pct']:+.4f}%**, doubled friction **{best['stress_metrics']['return_pct']:+.4f}%**, episodes **{m['trade_count']}**, adverse envelope DD **{m['max_drawdown_pct']:.4f}%**.", ""]
        lines += ["Insufficient episode counts mean insufficient evidence; a risk/activity rejection alone does not establish negative economic alpha.", ""]
    if report.get("reason"):
        lines += [report["reason"], ""]
    for role in ("validation", "final"):
        if role in report:
            row = report[role]
            monthly = row['target']['base']['geometric_monthly_return']
            monthly_text = f"{monthly*100:+.4f}%" if monthly is not None else "undefined (insolvent)"
            lines += [f"{role.capitalize()} locked-primary net **{row['metrics']['return_pct']:+.4f}%**, monthly equivalent **{monthly_text}**, episodes **{row['metrics']['trade_count']}**, common screen **{row['target']['passed']}**.", ""]
    lines += ["No substitutes, risk scaling or changed exits after failure. 8% geometric monthly equivalent is not an8% every-month guarantee or a withdrawal. Fresh forward/exact prop-contract verification remains required; live orders and Telegram are disabled.", ""]
    MARKDOWN.write_text("\n".join(lines), encoding="utf-8")


def freeze():
    path = DIRECTORY/"protocol.json"
    if path.exists():
        protocol = json.loads(path.read_text())
    else:
        files = [SOURCE/"manifest.json", FUNDING_SOURCE/"manifest.json"]
        for s in engine.SYMBOLS:
            files += [SOURCE/(s+"-5m.json"), FUNDING_SOURCE/(s+"-funding.json")]
        producers = ["propdesk/native_crypto_trend.py", "scripts/research_native_crypto_trend.py",
                     "tests/test_native_crypto_trend.py", "propdesk/target_evaluation.py",
                     "propdesk/research_lab.py", "propdesk/research_stats.py", "propdesk/market.py",
                     "scripts/research_broad.py"]
        protocol = {
            "version": "adaptive-native-perpetual-trend-context-v1", "frozen_at": shared.now(),
            "grid": engine.grid(), "windows": shared.WINDOWS, "training_folds": shared.FOLDS,
            "producers": {p: shared.file_hash(ROOT/p) for p in producers},
            "inputs": {str(p.relative_to(ROOT)): shared.file_hash(p) for p in files},
            "common_objective_path": "docs/EIGHT_PERCENT_PROTOCOL.json",
            "common_objective_sha256": shared.file_hash(ROOT/"docs/EIGHT_PERCENT_PROTOCOL.json"),
            "author_reference_path": "docs/author-regime-methods.json",
            "author_reference_sha256": shared.file_hash(ROOT/"docs/author-regime-methods.json"),
            "scope": "Adaptive exploratory; 2024–2026 general market prices already inspected in prior studies. Native5m sourcing is genuine, not globally untouched strategy evidence. Three families/eight economic configurations/96 total risk-time-stop variants, not96 independent strategies.",
            "source": "Original CHECKSUM-verified Binance USD-M native5m perpetual trade OHLC and realized funding settlements. No spot/perpetual prices are mixed. Personal non-production CC BY-NC-SA data; historical trade OHLC is not mark or executable bid/ask.",
            "source_protocol_sha256": json.loads((SOURCE/"manifest.json").read_text())["protocol_sha256"],
            "funding_source_protocol_sha256": json.loads((FUNDING_SOURCE/"manifest.json").read_text())["protocol_sha256"],
            "economic_hypotheses": "Slow trend continuation can reduce turnover; channel breakout provides a distinct trigger; fast RSI2 reversion is conditioned on past63-calendar-day momentum. These deterministic crypto adaptations do not reproduce/inherit original-author daily continuous-futures or learned changepoint performance.",
            "features": "Hourly/daily OHLC aggregate only from complete native5m bars. EMA alpha2/(n+1), seeded by first n known closes; no bfill. Day-based EMA/channel/context horizons multiply24 only for hourly decision resolution. Daily ATR14 Wilder smoothing uses previous FULLY completed UTC day, never current-day high/low. Observations cache economic configuration only.",
            "signals": {"ema": "Long fastEMA>slowEMA, short fastEMA<slowEMA, enter on next decision open when flat. Exit on prior completed observation no longer agreeing; no trailing modification or TP.",
                        "channel": "Completed close strictly breaks precedingN aggregated highs/lows excluding current aggregate; long/short. Exit long below precedingM lows, short above precedingM highs. No TP.",
                        "reversion": "RSI2<=5/10 and63day completed close-return>0 long; >=95/90 andreturn<0 short. Prior close exit longRSI>=50 or context<=0; shortRSI<=50 or context>=0; native2R target plus fixed protection."},
            "execution": "Next native5m opening trade-price proxy after prior hourly/daily observation completes. Observation known-at may coincide with next open boundary, so latency/quoted execution is unverified. Fixed protective stop2/3 prior dailyATR from adverse entry fill; gap stops at open, targets receive no favorable gap improvement; native intrabar stop prioritized overTP, liquidation prioritized when nativeOHLCcannot exclude it. At mostone position perasset; no same-native-bar reentry after an exit. Zero-volume bars prohibit modeledentry/indicator/stop/targetfills; unresolvedheldexposure recordedanddisqualifies. Boundary close is explicit retrospective mark, not a trading decision.",
            "capital": {"initial_total_equity": 100000, "risk_fraction_grid_current_marked_equity": [.0025, .005, .01],
                        "risk_size": "quantity=currentTOTALmarked equity*risk fraction/(stopATR*priorcompletedDailyATR), then rounded down and physical gross/cash capped. Fees/gaps/funding can exceed the nominal stop budget.",
                        "isolated_leverage": 2, "max_entry_total_gross_to_min_initial_current_equity": 2,
                        "max_entry_asset_gross_to_min_initial_current_equity": 1,
                        "collateral": "Eachmargin plus entryfee reservedfromsame positive freecash; PnL/funding stayisolated untilclose; no topups/additionalidle100k. Entry orderBTCthenETH deterministic withsymmetric1x cap; marked gross canmoveafterentry.",
                        "maintenance_assumption": .005, "liquidation_fee_assumption": .005,
                        "quantity_step_assumption": {"BTCUSDT": .001, "ETHUSDT": .001},
                        "liquidation": "TradeOHLC is not officialmark/tier/insurance. Proxyliquidation forfeits affectedmargin and recordsunpaiddeficit. Any BASE or doubled-cost liquidation/deficit disqualifies; no insurance guarantee."},
            "costs": {"fee_bps_each_side": 5, "slippage_bps_each_side": 2, "full_spread_bps": 1,
                      "double_friction_stress": True, "historical_executable_tariffs_verified": False,
                      "funding_stress": "Optional diagnostic doublesnegativepayments, halvespositivecredits; not a substitute for actual settled rates."},
            "funding_timeline": "Exact timestamps retained. ExactT old held positions charge beforeTorders onlyafterpre-fundinggap-liquidation check; T+.002 charges currentremainingoldpositions afterTopenorders. Heldage>=60s, new entries excluded. Future realized rate never finances earlier order. Historical mark missing: nativebaropen proxy. Positive credits omitted if same5mstop/TP/individuallegliq may precedeevent; negative charges retained andambiguity disclosed. Exactsample-end settlement/close tie retainspossibledebitand omitsuncertaincredit; latermillisecond event occursafterboundaryexit.",
            "risk_envelopes": "For each actual5m candle, account equity uses eachheldasset's unfavorable/favorable endpoint; simultaneous extrema unknown, so envelopes are conservative bounds. Whole-candle extrema may lie after an exit. Daily peak-before-worst conservatively bounds accountDD10%; priorUTCcalendarclose to dailyadverse dividedINITIAL100k bounds5%dailyreference. This is notFTMO staticfloor or Praguecontract replay.",
            "selection": "TRAIN2024 common net+doublecostpositive,30completedepisodes,60calendardays,adverseDD<=10%,dailyreference<=5%,zeroBASE+stressliquidation/debt plus2of3positive net folds. Highest netreturn/max(adverseDD,.25%) thenlexicographicID is ONE primary locked before2025. No eligible candidate => no OOS. 2025 common8%-monthlyscreen mustpass and immutablevalidationconfirmation binds selectedID+selectionlock+validationresult before2026; never substitute winner or scale after failure. Insolventdailyaccount explicitlyfails withnullgeometric/statisticalinference.",
            "target": "Unmodified EIGHT_PERCENT_PROTOCOL/target_evaluation: OOS60episodes,6fullmonths,geometric monthly>=8%,dailymean99%7day5000blocklower>0,doublecostmonthlypositive,medianmonthpositive,>=2/3positivefullmonths,bothhalvespositive,risklimits pluszeroBASE/stressdebt/liquidations. Historical screen never enables live/TG or certifies payout.",
            "training_diagnostics": "Gross-price-PnL accounting decomposition atsamequantities/exits, fees/funding/turnover/capitalexposure and dailyreturnBTC/ETHreferencecorrelation/beta TRAINONLY. Marketreferences are uncosted descriptive returns, not executable benchmarkalpha.",
            "orders": "No real exchange order, prop challenge, withdrawal or Telegram. No outcomes-guided sizing/parameter mutation; all failed variants retained. Freshforward/exactcontract/markexecution verification still required."}
        shared.immutable_write(path, protocol)
    report = {"phase": "frozen_before_outcomes", "protocol": protocol, "protocol_sha256": lab.digest(protocol),
              "selected": None, "retrospective_target_candidate": False, "live_qualified": False,
              "prop_qualified": False, "telegram_enabled": False}
    if not OUTPUT.exists():
        write_report(report)
    return report


def verify(report):
    protocol = report["protocol"]
    if lab.digest(protocol) != report["protocol_sha256"] or protocol["grid"] != engine.grid():
        raise ValueError("Frozen protocol/grid changed")
    for pathkey, hashkey in (("common_objective_path", "common_objective_sha256"),
                             ("author_reference_path", "author_reference_sha256")):
        if shared.file_hash(ROOT/protocol[pathkey]) != protocol[hashkey]:
            raise ValueError("Registered objective/source-method document changed")
    for namespace in ("inputs", "producers"):
        for p, expected in protocol[namespace].items():
            if shared.file_hash(ROOT/p) != expected:
                raise ValueError("Bound source/producer changed: "+p)


def _verified_receipt(root, row, filename):
    if row.get("json") != filename or row.get("json_sha256") != shared.file_hash(root/filename) or not row.get("complete_calendar"):
        raise ValueError("Official normalized source hash/calendar mismatch")
    sources = row.get("sources", [])
    expected_months = {(y, m) for y in (2024, 2025, 2026) for m in range(1, 13) if y != 2026 or m <= 9}
    if len(sources) != 33 or {(s.get("year"), s.get("month")) for s in sources} != expected_months or any(s.get("checksum_verified") is not True or not s["source_url"].startswith("https://data.binance.vision/data/futures/um/") or len(s.get("zip_sha256", "")) != 64 or any(c not in "0123456789abcdef" for c in s.get("zip_sha256", "")) for s in sources):
        raise ValueError("All33 original monthly archives require official adjacent verified CHECKSUM receipts")
    for source in sources:
        name = source["source_url"].rsplit("/", 1)[-1]
        raw, checksum = root/"raw"/name, root/"raw"/(name+".CHECKSUM")
        if raw.exists() or checksum.exists():
            if not raw.exists() or not checksum.exists() or shared.file_hash(raw) != source["zip_sha256"] or checksum.read_text().split()[0].lower() != source["zip_sha256"]:
                raise ValueError("Available original ZIP/adjacent CHECKSUM bytes disagree with receipt")


def load_inputs():
    manifest = json.loads((SOURCE/"manifest.json").read_text())
    funding_manifest = json.loads((FUNDING_SOURCE/"manifest.json").read_text())
    receipts = {r["symbol"]: r for r in manifest["datasets"]}
    funding_receipts = {(r["symbol"], r["kind"]): r for r in funding_manifest["datasets"]}
    datasets, funding = {}, {}
    for symbol in engine.SYMBOLS:
        name = symbol+"-5m.json"
        row = receipts[symbol]
        _verified_receipt(SOURCE, row, name)
        values = json.loads((SOURCE/name).read_text())
        if len(values) != 289152 or market.data_fingerprint(values) != row["data_fingerprint"]:
            raise ValueError("Native complete-source fingerprint/count mismatch")
        datasets[symbol] = engine.PackedBars(values)
        del values
        if datasets[symbol].times[0] != "2024-01-01T00:00:00Z" or datasets[symbol].times[-1] != "2026-09-30T23:55:00Z":
            raise ValueError("Complete2024–September2026 native calendar required")
        name = symbol+"-funding.json"
        _verified_receipt(FUNDING_SOURCE, funding_receipts[symbol, "fundingRate"], name)
        values = json.loads((FUNDING_SOURCE/name).read_text())
        slots = [market.utc_datetime(v["time"]).replace(microsecond=0) for v in values]
        if len(values) != 3012 or slots[0].isoformat() != "2024-01-01T00:00:00+00:00" or any((b-a).total_seconds() != 8*3600 for a, b in zip(slots, slots[1:])):
            raise ValueError("Complete original3012 settlements required; no imputation")
        funding[symbol] = values
    features = engine.NativeFeatures(datasets)
    return features, engine.prepare_funding(features, funding)


def evaluate(result, stressed, window, role, seed):
    insolvent = any(row["equity"] <= 0 for row in result["equity_curve"]+stressed["equity_curve"])
    if insolvent:
        return {"role": role, "passed": False, "status": "not_qualified",
                "checks": {"positive_finite_total_account_equity": False},
                "reason": "Insolvent modeled account. Geometric/statistical inference is undefined and was not computed.",
                "base": {"total_return": result["metrics"]["final_equity"]/result["metrics"]["initial_equity"]-1, "geometric_monthly_return": None},
                "double_cost_stress": {"total_return": stressed["metrics"]["final_equity"]/stressed["metrics"]["initial_equity"]-1, "geometric_monthly_return": None},
                "daily_mean_ci99": None, "selection_score_net_return_over_drawdown": -1e12,
                "live_orders": False, "telegram_enabled": False}
    dates = [r["date"] for r in result["daily_returns"]]
    assessed = target.evaluate_period(dates, [r["return"] for r in result["daily_returns"]],
                                     [r["return"] for r in stressed["daily_returns"]], result["metrics"]["trade_count"],
                                     daily_worst_equity=[r["worst_equity"] for r in result["equity_curve"]],
                                     daily_peak_equity=[r["best_equity"] for r in result["equity_curve"]],
                                     period_start=window[0], period_end_exclusive=window[1], role=role, samples=5000, seed=seed)
    assessed["checks"]["no_proxy_liquidation_base_and_stress"] = result["metrics"]["liquidation_count"] == stressed["metrics"]["liquidation_count"] == 0
    assessed["checks"]["no_unfunded_deficit_base_and_stress"] = result["metrics"]["unfunded_isolated_deficit"] == stressed["metrics"]["unfunded_isolated_deficit"] == 0
    assessed["checks"]["no_unresolved_zero_volume_exposure_base_and_stress"] = result["metrics"]["unresolved_zero_volume_exposure_bars"] == stressed["metrics"]["unresolved_zero_volume_exposure_bars"] == 0
    assessed["passed"] = all(assessed["checks"].values())
    assessed["status"] = "historical_reference_screen_passed" if assessed["passed"] else "not_qualified"
    return assessed


def price_decomposition(result):
    m = result["metrics"]
    gross = m["final_equity"]-m["initial_equity"]+m["fees_paid"]+m["adverse_fill_cost"]-m["funding_pnl"]
    return {"net_pnl": m["final_equity"]-m["initial_equity"], "gross_price_pnl_before_costs_and_funding": gross,
            "gross_price_return_pct": gross/m["initial_equity"]*100, "fees": m["fees_paid"],
            "adverse_fill_cost": m["adverse_fill_cost"], "funding_pnl": m["funding_pnl"],
            "identity_valid_without_liquidation_or_unfunded_deficit": m["liquidation_count"] == m["unfunded_isolated_deficit"] == 0,
            "scope": "Accounting atsameactualquantities/exits, not a zero-cost resized strategy or alpha proof."}


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
    return {k: result[k] for k in ("metrics", "daily_returns", "start", "end")}


def run():
    report = freeze()
    verify(report)
    if (DIRECTORY/"training_selection.json").exists():
        raise ValueError("TRAIN already completed/locked; immutable results must not be overwritten")
    features, funding = load_inputs()
    references = train_reference(features)
    training = []
    for i, variant in enumerate(report["protocol"]["grid"]):
        observations = features.observations(variant)
        result = engine.simulate(features, observations, funding, variant, *shared.WINDOWS["training"])
        stress = engine.simulate(features, observations, funding, variant, *shared.WINDOWS["training"], cost_multiplier=2)
        assessed = evaluate(result, stress, shared.WINDOWS["training"], "training", 20261007+i)
        folds = [engine.simulate(features, observations, funding, variant, *fold)["metrics"] for fold in shared.FOLDS]
        assessed["checks"]["two_of_three_training_folds_positive"] = sum(f["return_pct"] > 0 for f in folds) >= 2
        assessed["passed"] = all(assessed["checks"].values())
        assessed["status"] = "historical_reference_screen_passed" if assessed["passed"] else "not_qualified"
        training.append({"id": variant["id"], "variant": variant, "metrics": result["metrics"],
                         "stress_metrics": stress["metrics"], "target": assessed, "folds": folds,
                         "passed": assessed["passed"], "score": assessed["selection_score_net_return_over_drawdown"],
                         "decomposition": price_decomposition(result), "relationships": train_relationships(result, references)})
        report.update(phase="training_in_progress", training=training)
        write_report(report)
        print(f"Nativetrend TRAIN {i+1}/96 {variant['id']} net={result['metrics']['return_pct']:+.4f}% stress={stress['metrics']['return_pct']:+.4f}% episodes={result['metrics']['trade_count']} passed={assessed['passed']}", flush=True)
    surviving = sorted([r for r in training if r["passed"]], key=lambda r: (-r["score"], r["id"]))
    selected = surviving[0]["id"] if surviving else None
    lock = {"protocol_sha256": report["protocol_sha256"], "training_results_sha256": lab.digest(training),
            "selected": selected, "locked_before_validation": True, "locked_at": shared.now()}
    shared.immutable_write(DIRECTORY/"training_selection.json", lock)
    shared.immutable_write(DIRECTORY/"training_results.json", training)
    report.update(selected=selected, selection_lock=lock, selection_lock_sha256=lab.digest(lock))
    if selected is None:
        report.update(phase="completed_no_training_candidate", reason="No candidate passed all frozen TRAIN economic/risk/activity/CV gates. Lowepisodecount is evidence insufficiency, not necessarilynegativepriceedge. 2025/2026strategyperformance remains unopened.")
    else:
        report.update(phase="training_complete_primary_locked_oos_unopened", reason="One fixed TRAINprimary locked; this run is TRAINONLY. 2025/2026strategyperformance has not been computed; onlythisprimary mayproceed through frozen screens.")
    write_report(report)
    return report


def evaluate_locked():
    report = json.loads(OUTPUT.read_text())
    verify(report)
    selected = report.get("selected")
    if not selected:
        raise ValueError("No eligible lockedTRAINprimary; OOS remains unopened")
    lock = json.loads((DIRECTORY/"training_selection.json").read_text())
    if lab.digest(lock) != report["selection_lock_sha256"] or lock["selected"] != selected or lab.digest(report["training"]) != lock["training_results_sha256"]:
        raise ValueError("Registered TRAINprimary/results lock changed")
    variant = next(v for v in report["protocol"]["grid"] if v["id"] == selected)
    features, funding = load_inputs()
    observations = features.observations(variant)
    for role in ("validation", "final"):
        if role == "final":
            confirmation = json.loads((DIRECTORY/"validation-confirmation.json").read_text())
            expected = {"selected": selected, "selection_lock_sha256": report["selection_lock_sha256"],
                        "validation_result_sha256": lab.digest(report["validation"]),
                        "validation_passed": True, "protocol_sha256": report["protocol_sha256"]}
            if confirmation != expected or not report["validation"]["target"]["passed"]:
                raise ValueError("Immutable validation confirmation required before opening2026")
        if (DIRECTORY/(role+"_result.json")).exists():
            raise ValueError("Already-opened locked OOS results cannot be rerun/overwritten")
        result = engine.simulate(features, observations, funding, variant, *shared.WINDOWS[role])
        stress = engine.simulate(features, observations, funding, variant, *shared.WINDOWS[role], cost_multiplier=2)
        assessed = evaluate(result, stress, shared.WINDOWS[role], role, 20261007+(1000 if role == "validation" else 2000))
        record = {**compact(result), "stress_metrics": stress["metrics"], "target": assessed,
                  "decomposition": price_decomposition(result)}
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
