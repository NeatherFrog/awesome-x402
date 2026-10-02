#!/usr/bin/env python3
"""Predeclare and replay fixed futures session hypotheses against 8%/month.

The provider history has been inspected before; this is adaptive retrospective
research, not a globally blind test. No source/report may be replaced after PnL.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from propdesk import session_strategies as engine
from propdesk.target_evaluation import evaluate_period

OUTPUT = ROOT / "docs" / "session-research.json"
MARKDOWN = ROOT / "docs" / "SESSION_RESEARCH.md"
LOCKS = ROOT / "data" / "session-research"
HISTORY = ROOT / "data" / "current-history" / "2026-10-01T09-23-08Z"
CALENDAR_RAW = ROOT / ".local" / "prop-data-sources" / "market-hours-database.json"
CALENDAR_SHA256 = "bffec9c2e5efe30c0f21a1af9d1803b2a8e9a1356ac4f7408130693b7261e440"
COMMON_TARGET_SHA256 = "5495a0683efeb6da230cf454b71c8e8ae952dc03534d23f3cedbcd9f56e9e839"
SYMBOLS = ("MES=F", "MNQ=F")
AGGREGATE_RISK_PCTS = (.5, 1.0, 1.5)
VERIFIED_TOPSTEP_RECEIPTS = (
    {"id": "topstep_commission", "topic": "Advertised MES/MNQ commission $1.22 round trip/$0.61 derived per side",
     "url": "https://help.topstep.com/en/articles/8284213-topstepx-commissions-and-fees",
     "retrieved_sha256": "89e0285102d116bd1c1590a3f5e317a940d4ee7b1ccf42a51ad02b26697a20e2"},
    {"id": "topstep_combine", "topic": "100K Combine aggregate maximum 10 minis/100 micros; not XFA scaling",
     "url": "https://help.topstep.com/en/articles/8284197-trading-combine-parameters",
     "retrieved_sha256": "dceedd3fb2d025d783fef0bb84ad702bdc5fb9df113d3b0a7ce1c1a65f16d0ed"},
    {"id": "topstep_scaling", "topic": "XFA aggregate balance-based scaling; numerical tier image unverified",
     "url": "https://help.topstep.com/en/articles/8284223-what-is-the-scaling-plan",
     "retrieved_sha256": "9c4a40cc17b884f9389fa81b0630d966f8774345b7ac0bbb337ea888f4870807"})
PERIODS = {"training": ("2024-10-01", "2025-01-01"),
           "validation": ("2025-01-01", "2026-01-01"), "final": ("2026-01-01", "2026-10-01")}
PRODUCERS = ("scripts/research_sessions.py", "propdesk/session_strategies.py", "propdesk/target_evaluation.py",
             "propdesk/research_stats.py", "propdesk/market.py", "propdesk/timezones.py",
             "propdesk/timezone_bootstrap.py", "propdesk/__init__.py", "propdesk/tzdata/America/New_York")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def file_digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def immutable_write(path, value):
    path = Path(path)
    text = canonical(value) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_text() != text:
            raise ValueError("Immutable research artifact mismatch: " + str(path))
        return
    with path.open("x", encoding="utf-8") as stream:
        stream.write(text)


def write_output(report):
    text = canonical(report) + "\n"
    temporary = OUTPUT.with_name(OUTPUT.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(OUTPUT)


def producer_hashes():
    return {name: file_digest(ROOT / name) for name in PRODUCERS}


def portfolio_variants():
    return [{**item, "economic_id": item["id"], "id": item["id"] + f"__risk{risk:g}",
             "aggregate_risk_pct": risk} for item in engine.catalog() for risk in AGGREGATE_RISK_PCTS]


def calendar():
    if file_digest(CALENDAR_RAW) != CALENDAR_SHA256:
        raise ValueError("Official pinned calendar source hash mismatch")
    entry = json.loads(CALENDAR_RAW.read_text())["entries"]["Equity-usa-[*]"]
    convert = lambda values: sorted(datetime.strptime(item, "%m/%d/%Y").date().isoformat()
                                    for item in values if "2024-10-01" <= datetime.strptime(item, "%m/%d/%Y").date().isoformat() < "2026-10-01")
    return {"timezone": "America/New_York", "holidays": convert(entry["holidays"]),
            "early_close_dates": convert(entry["earlyCloses"]),
            "source_sha256": CALENDAR_SHA256,
            "source_url": "https://raw.githubusercontent.com/QuantConnect/Lean/41c6e603e5671ca7b5d3de0cbe13b3c4b109bba4/Data/market-hours/market-hours-database.json",
            "scope": "NYSE cash-open research window for index futures; not a complete CME execution calendar",
            "normal_first_full_hour": "10:00–11:00", "normal_flatten_open": "15:00",
            "early_first_full_hour": "09:30–10:30", "early_flatten_open": "12:30"}


def make_protocol():
    if file_digest(ROOT / "docs" / "EIGHT_PERCENT_PROTOCOL.json") != COMMON_TARGET_SHA256:
        raise ValueError("Common target protocol hash mismatch")
    source_review = json.loads((ROOT / "docs" / "high-return-source-review.json").read_text())
    receipts = {item["id"]: item for item in source_review["retrievals"]}
    for source in VERIFIED_TOPSTEP_RECEIPTS:
        receipt = receipts.get(source["id"], {})
        if receipt.get("sha256") != source["retrieved_sha256"] or not receipt.get("body_verified"):
            raise ValueError("Verified Topstep source receipt mismatch: " + source["id"])
    return {"version": engine.VERSION, "frozen_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "common_target_protocol": {"path": "docs/EIGHT_PERCENT_PROTOCOL.json", "file_sha256": COMMON_TARGET_SHA256},
            "markets": list(SYMBOLS), "interval": "1h", "periods": {name: list(bounds) for name, bounds in PERIODS.items()},
            "variants": portfolio_variants(), "economic_rulesets": 48, "aggregate_risk_grid_pct": list(AGGREGATE_RISK_PCTS),
            "portfolio_variants": 144, "distinct_market_hypotheses": 288,
            "calendar": calendar(), "execution_config_per_bucket": engine.DEFAULT_CONFIG,
            "contract_specs": engine.SPECS, "initial_total_account": 100000,
            "allocation": "Two independent50000 risk buckets; aggregateTRAINsizing(.5%,1%,1.5%) meansinitial250/500/750dollars cost-inclusive plannedrisk perasset. Integercontracts,max10perasset(20total),no nominalcash/notional margin inference; thisconservativeresearchcapdoesnotclaimverifiedpersonalbrokerbuyingpower.",
            "maximum_initial_aggregate_planned_risk_pct": 1.5,
            "rules": {"late_opening_range": "First1or2fullyclosed fullRTHhours10–11/10–12normal(or0930startinghalfday); followingclosedbarclosebeyondrange+0or.1priorATR14; nextopenmustremainbeyondrange; stopoppositeedge+.1ATRbuffer,target1.5or2.5Rfromrawentry; optionallydirectionpriorEMA20.",
                      "failed_range_reversion": "Afterfirst1or2fullhourrange, signalwickstrictlybreaksoneedgeby0or.25priorATRandclosesstrictlyinside. Both-sidesweepexcluded. Nextopenentry,stopsignalextreme+.1ATR,targetfrozenrangemidpointorOHLCvolumeVWAPproxy. OptionalcontrarianEMA20stretchfilter; nonpositivecostnetrewardblocked.",
                      "volatility_release": "Closedhourdirectionalbody>=.75or1.25priorATR14,closebeyondchannelof4or8priorclosedfullRTHfeaturebarsandterminalquarter. Channel excludescurrentbar andmaycrosspriorcashsessions. Nextopenentry,stopsignalextreme+.1ATR,target1.5or2.5R,optionalpriorEMA20direction."},
            "features": "ATR14WilderandEMA20onlypreviousfullyclosedfeaturehours; normal15andhalfday1230markerOHLC/volumeexcluded. VWAPusescumulativecurrentwindowtypical(H+L+C)/3*reportedvolume,explicitproxy,nottrue0930/tradeVWAP.",
            "fills": "Nextobservedhourlyopeningonly; signalclose timestamp. Wholecontractsizebycostinclusivestopbudget,max10. Adversequartertickrounding,.61dollaradvertisedMES/MNQfee/contract/side,1tickfullspread+1tickslippageeachside. StopswinOHLCcollisions; adversegapstopopeningprice,favorablegaptargettargetprice. Dailyflatknownobserved15normal/1230halfday beforelaterOHLC. Atmost1entry/asset/session,nocarry,missingflatfail.",
            "cost_stress": "Separatefixedscenario doublescommission,slippageandspread beforetickrounding; no riskupscaling ornewwinnerselection.",
            "selection": "OnlyTRAINpassed variants compete on standardizedtrainingtotalnetreturn/adverseDDfloor. LexicalIDtie. Oneprimarylocked beforevalidation; no OOS substitute. IfTRAINnonepasses, highestTRAINscorecandidateislockedasfaileddiagnosticandselected_variant=null,allOOSnot_evaluated. Onlyeligibleprimaryevaluatedonvalidation;ifvalidationfailsfinalnot_evaluated. Passingvalidationconfirmationislockedbeforeoneprimaryfinalrun.",
            "training_gates": {"positive_net": True, "positive_double_cost": True, "minimum_complete_episodes": 30,
                               "minimum_calendar_days": 60, "max_adverse_drawdown_pct": 10, "max_reference_daily_loss_pct_initial": 5},
            "oos_gates": {"geometric_monthly_total_account_pct": 8, "minimum_full_calendar_months": 6,
                          "minimum_complete_episodes": 60, "daily_mean_ci99_lower_above": 0,
                          "bootstrap_calendar_block_days": 7, "samples": 5000, "seed": 20261002,
                          "double_cost_geometric_monthly_positive": True, "median_full_month_positive": True,
                          "minimum_positive_full_month_fraction": "2/3", "both_chronological_halves_positive": True,
                          "max_adverse_drawdown_pct": 10, "max_reference_daily_loss_pct_initial": 5},
            "risk_reference": "UTCcashdates(allRTHtradesflatbeforeUTC/Praguemidnight),100kTOTALaccount,flatcalendarweekends/holidaysincluded; conservativeOHLCliquidationestimatesincludingexitcostswithsynchronousmarketworst/bestbounds,notactualbrokerMTM; referencegateisnotactualpropcontractreplay.",
            "data_quality": "All501expectedNYcashsessions andeveryrequiredobservedfullhour/flattenanchor onbothfutures. Wholehour9normalstraddles0930andisexcludedratherthanresampled. KnowncashcloseddaysCMEdataexcludedbycalendarbeforePnL. No imputation,dropofmissinglossdays orfictional09:30fills.",
            "scope": "ExistingYahooOct2024–Sep2026pricespreviouslyinspectedinotherstudies,notgloballyblind. Continuousfuturesrolls/unofficialOHLCnotfixedbrokercontract,feesassumednotpersonaltariff; historicalpassesprovisionalonly.",
            "public_sources": [{"topic": "Session calendar", "url": "https://github.com/QuantConnect/Lean/tree/41c6e603e5671ca7b5d3de0cbe13b3c4b109bba4/Data/market-hours", "access": "retrieved_pinned_bytes"},
                               {"topic": "Opening-range concept", "url": "https://github.com/QuantConnect/Lean/blob/41c6e603e5671ca7b5d3de0cbe13b3c4b109bba4/Algorithm.CSharp/OpeningBreakoutAlgorithm.cs", "access": "prior_source_review;thishourlyadaptationisnotoriginal3minutealgorithm"},
                               *VERIFIED_TOPSTEP_RECEIPTS],
            "qualification": "No brokerorders,Telegramtrades,payoutclaim orqualifiedlive flag. ActualFTMOPrague/TopstepMLL replay andnewforwardbrokerdata remainseparate."}


def freeze():
    if OUTPUT.exists():
        report = json.loads(OUTPUT.read_text())
        if digest(report["protocol"]) != report["protocol_sha256"]:
            raise ValueError("Frozen session protocol mismatch")
        stored = json.loads((LOCKS / "protocol.json").read_text())
        if stored != report["protocol"]:
            raise ValueError("Protocol lock mismatch")
        expected = make_protocol()
        expected["frozen_at"] = report["protocol"]["frozen_at"]
        if expected != report["protocol"]:
            raise ValueError("Current implementation parameters differ from frozen session protocol")
        return report
    protocol = make_protocol()
    immutable_write(LOCKS / "protocol.json", protocol)
    report = {"phase": "predeclared", "protocol": protocol, "protocol_sha256": digest(protocol),
              "orders": False, "real_prop_qualified": False, "selected_variant": None}
    write_output(report)
    return report


def load_sources(protocol):
    prepared, locks = {}, {}
    for symbol in SYMBOLS:
        path = HISTORY / (symbol.replace("=", "_") + "-1h.json")
        payload = json.loads(path.read_text())
        bars, audit = engine.prepare_bars(payload["bars"], protocol["calendar"], "2024-10-01", "2026-10-01")
        prepared[symbol] = bars
        locks[symbol] = {"path": str(path.relative_to(ROOT)), "file_sha256": file_digest(path),
                         "canonical_bars_sha256": digest(payload["bars"]), "provenance": payload["provenance"], "coverage": audit}
    immutable_write(LOCKS / "source-lock.json", locks)
    return prepared, locks


def combine(runs, start, end):
    """Synchronous total-account equity; no per-asset percentage averaging."""
    curves = [{point["time"]: point for point in run["curve"]} for run in runs]
    if len(curves) != 2 or set(curves[0]) != set(curves[1]):
        raise ValueError("Both risk buckets must cover identical observed hourly anchors")
    combined = []
    for stamp in sorted(curves[0]):
        points = [curve[stamp] for curve in curves]
        combined.append({"time": stamp, "session_date": points[0]["session_date"],
                         "equity": sum(point["equity"] for point in points),
                         "balance": sum(point["balance"] for point in points),
                         "worst_equity": sum(point["worst_equity"] for point in points),
                         "best_equity": sum(point["best_equity"] for point in points)})
    by_day = {}
    for point in combined:
        date = point["session_date"]
        item = by_day.setdefault(date, {"equity": point["equity"], "worst": point["worst_equity"], "peak": point["best_equity"]})
        item.update(equity=point["equity"], worst=min(item["worst"], point["worst_equity"]), peak=max(item["peak"], point["best_equity"]))
    dates, returns, worst, peaks = [], [], [], []
    stamp, finish, equity = datetime.fromisoformat(start).date(), datetime.fromisoformat(end).date(), 100000.0
    while stamp < finish:
        date = stamp.isoformat()
        item = by_day.get(date, {"equity": equity, "worst": equity, "peak": equity})
        dates.append(date)
        returns.append(item["equity"] / equity - 1)
        worst.append(min(equity, item["worst"], item["equity"]))
        peaks.append(max(equity, item["peak"], item["equity"]))
        equity = item["equity"]
        stamp += timedelta(days=1)
    trades = sorted([trade for run in runs for trade in run["trades"]], key=lambda item: (item["entry_time"], item["symbol"]))
    return {"dates": dates, "daily_returns": returns, "daily_worst_equity": worst, "daily_peak_equity": peaks,
            "trades": trades, "curve": combined, "market_metrics": {run["symbol"]: run["metrics"] for run in runs}}


def run_period(prepared, variant, role):
    params = next(item for item in portfolio_variants() if item["id"] == variant)
    start, end = PERIODS[role]
    results = []
    for cost_multiplier in (1, 2):
        runs = []
        for symbol in SYMBOLS:
            visible = [bar for bar in prepared[symbol] if bar["session_date"] < end]
            simulation = engine.simulate(visible, params["economic_id"], symbol,
                        config={"cost_multiplier": cost_multiplier, "risk_pct": params["aggregate_risk_pct"]},
                        start_date=start, end_date=end)
            for trade in simulation["trades"]:
                trade.update(portfolio_variant=variant, aggregate_risk_pct=params["aggregate_risk_pct"])
            runs.append(simulation)
        results.append(combine(runs, start, end))
    base, stress = results
    evaluation = evaluate_period(base["dates"], base["daily_returns"], stress["daily_returns"], len(base["trades"]),
                                daily_worst_equity=base["daily_worst_equity"], daily_peak_equity=base["daily_peak_equity"],
                                period_start=start, period_end_exclusive=end, role=role, risk_day_timezone="UTC")
    return {"evaluation": evaluation, "base": base, "double_cost": stress}


def write_markdown(report):
    if report["phase"] != "complete":
        return
    lines = ["# Futures session research against 8% monthly", "", "Adaptive retrospective study; existing prices were inspected before. No real trades or qualified live strategy.",
             "", f"Protocol SHA256: `{report['protocol_sha256']}`. 48 frozen economic rules×3 predeclaredTRAINrisk levels=144portfolio variants/288market hypotheses.",
             "Regular futures hourly data cannot represent09:30RTH opening range: the first full interval is10–11NY. Halfdays use the known09:30anchor; daily flatten15:00normal/12:30halfday.",
             "VWAP is only an OHLC-volume proxy. 100k nominal balance is not margin; TRAINselects initially250/500/750dollars plannedrisk per market, fixedintegercontract cap10/asset, fixed fees and adverse ticks. No failed heldout return is rescaled.",
             "", f"Locked training candidate: `{report['training_candidate']}`; selected eligible variant: `{report['selected_variant']}`.",
             "", "| Period | Net total | Geometric monthly | Double-cost monthly | Episodes | Adverse DD | Gate |",
             "|---|---:|---:|---:|---:|---:|---|"]
    for role in PERIODS:
        period = report["primary"][role]
        if "evaluation" not in period:
            lines.append(f"|{role}|not evaluated|—|—|—|—|{period['reason']}|")
            continue
        item = period["evaluation"]
        lines.append(f"|{role}|{item['base']['total_return']*100:.3f}%|{item['base']['geometric_monthly_return']*100:.3f}%|{item['double_cost_stress']['geometric_monthly_return']*100:.3f}%|{item['completed_episodes']}|{item['risk']['max_account_drawdown']*100:.3f}%|{'pass' if item['passed'] else 'fail'}|")
    lines += ["", "| Frozen variant | Train net | Train monthly | Double-cost monthly | Train episodes | Training gate |",
              "|---|---:|---:|---:|---:|---|"]
    for row in report["variants"]:
        item = row['training']
        lines.append(f"|{row['id']}|{item['base']['total_return']*100:.3f}%|{item['base']['geometric_monthly_return']*100:.3f}%|{item['double_cost_stress']['geometric_monthly_return']*100:.3f}%|{item['completed_episodes']}|{'pass' if item['passed'] else 'fail'}|")
    lines += ["", "Diagnostics do not replace a failed locked candidate. Full gate failures, monthly returns, conditional99% intervals, source/protocol/producer locks, primary trades and curves are in session-research.json.",
              "All failed experiments remain registered. Historical screening does not establish stability, broker fills, prop payouts or forward profitability."]
    MARKDOWN.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run():
    report = freeze()
    prepared, source_lock = load_sources(report["protocol"])
    hashes = producer_hashes()
    if report["phase"] == "complete":
        if report["producer_sha256"] != hashes or report["source_lock"] != source_lock:
            raise ValueError("Completed immutable session study producer/source mismatch")
        result_lock = json.loads((LOCKS / "result-lock.json").read_text())
        if result_lock["report_sha256"] != file_digest(OUTPUT):
            raise ValueError("Completed immutable session report fingerprint mismatch")
        return report
    variants = report["protocol"]["variants"]
    training = {item["id"]: run_period(prepared, item["id"], "training") for item in variants}
    eligible = [item["id"] for item in variants if training[item["id"]]["evaluation"]["passed"]]
    candidates = eligible or [item["id"] for item in variants]
    candidate = min(candidates, key=lambda name: (-training[name]["evaluation"]["selection_score_net_return_over_drawdown"], name))
    selected = candidate if eligible else None
    lock = {"candidate": candidate, "selected": selected, "locked_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "protocol_sha256": report["protocol_sha256"], "producer_sha256": hashes,
            "source_lock_sha256": digest(source_lock), "training_metrics": {key: value["evaluation"] for key, value in training.items()},
            "selection": report["protocol"]["selection"]}
    path = LOCKS / "training-lock.json"
    if path.exists():
        existing = json.loads(path.read_text())
        lock["locked_at"] = existing["locked_at"]
    immutable_write(path, lock)
    report.update(phase="training_locked", training_candidate=candidate, selected_variant=selected,
                  producer_sha256=hashes, source_lock=source_lock, training_lock_sha256=digest(lock))
    write_output(report)
    rows = [{"id": item["id"], "family": item["family"], "training": training[item["id"]]["evaluation"]} for item in variants]
    primary = {"training": training[candidate], "validation": {"status": "not_evaluated", "reason": "no eligible training candidate"},
               "final": {"status": "not_evaluated", "reason": "no eligible training candidate"}}
    if selected is not None:
        validation = run_period(prepared, selected, "validation")
        primary["validation"] = validation
        primary["final"] = {"status": "not_evaluated", "reason": "locked primary failed validation; no final inspection"}
        if validation["evaluation"]["passed"]:
            confirmation = {"candidate": selected, "protocol_sha256": report["protocol_sha256"],
                            "training_lock_sha256": report["training_lock_sha256"], "producer_sha256": hashes,
                            "validation_sha256": digest(validation),
                            "confirmed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")}
            confirmation_path = LOCKS / "validation-confirmation.json"
            if confirmation_path.exists():
                confirmation["confirmed_at"] = json.loads(confirmation_path.read_text())["confirmed_at"]
            immutable_write(confirmation_path, confirmation)
            primary["final"] = run_period(prepared, selected, "final")
    if producer_hashes() != hashes:
        raise ValueError("Source changed during frozen session execution")
    provisional = selected is not None and all(primary[role].get("evaluation", {}).get("passed", False) for role in PERIODS)
    report.update(phase="complete", variants=rows, primary=primary,
                  historical_reference_passed=provisional, real_prop_qualified=False,
                  diagnostic_oos_passes=[], diagnostic_heldout_substitution=False,
                  finished_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                  global_blind_holdout=False, live_orders=False, telegram_enabled=False)
    write_output(report)
    immutable_write(LOCKS / "result-lock.json", {"report_sha256": file_digest(OUTPUT), "protocol_sha256": report["protocol_sha256"],
                                               "training_lock_sha256": report["training_lock_sha256"], "producer_sha256": hashes})
    write_markdown(report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze", action="store_true")
    args = parser.parse_args()
    report = freeze() if args.freeze else run()
    print(json.dumps({"phase": report["phase"], "protocol_sha256": report["protocol_sha256"],
                      "training_candidate": report.get("training_candidate"), "selected_variant": report.get("selected_variant"),
                      "historical_reference_passed": report.get("historical_reference_passed", False)}, indent=2))


if __name__ == "__main__":
    main()
