#!/usr/bin/env python3
"""Preregister, then evaluate ONE locked funding-carry candidate; no orders."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from propdesk import funding_lab as lab

OUTPUT = ROOT / "docs/funding-research.json"
MARKDOWN = ROOT / "docs/FUNDING_RESEARCH.md"
PROTOCOL_DOC = ROOT / "docs/FUNDING_PROTOCOL.md"
WINDOWS = {"training": ["2024-01-01T00:00:00Z", "2025-01-01T00:00:00Z"],
           "validation": ["2025-01-01T00:00:00Z", "2026-01-01T00:00:00Z"],
           "final": ["2026-01-01T00:00:00Z", "2026-10-01T00:00:00Z"]}
SEED = 20261002


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def write_report(report):
    temporary = OUTPUT.with_suffix(".tmp")
    temporary.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(OUTPUT)
    lines = ["# Spot/perpetual funding carry research", "", f"Status: **{report['phase']}**.", "",
             "Seven bounded variants: one static benchmark and six realized-funding-persistence variants. New economic hypothesis after208 hourly spot variants failed2025 validation; this is additional adaptive research, not an untouched global holdout.", "",
             f"Frozen protocol SHA256: `{report['protocol_sha256']}`.", "",
             "One100,000USD portfolio, two50,000USD asset buckets. Each holds25,000USD spot cash and25,000USD isolated perpetual collateral initially. Equal base units long spot/short perpetual. Spot unrealized profit is not collateral and no hidden cash transfer occurs.", "",
             "Spot10bp/side, perpetual5bp/side, slippage2bp/side and full spread1bp are modeling assumptions, not verified account tariffs. Trade OHLC is not liquidation mark OHLC. Missing funding mark prices use preceding closed perpetual trade price. Every result is provisional, unsuitable for live execution/prop qualification.", "",
             "CC BY-NC-SA archive data is used only for personal non-production analysis; this is not production-data licensing. No exchange orders, real account, payouts or Telegram messages are created.", ""]
    if report.get("reason"):
        lines += [report["reason"], ""]
    if report.get("training"):
        lines += ["| Variant |2024 net | Double costs |75% positive funding | Liquidations |", "| --- | ---: | ---: | ---: | ---: |"]
        for row in report["training"]:
            lines.append(f"|{row['variant']['id']}|{row['base']['return_pct']:+.4f}%|{row['cost_stress']['return_pct']:+.4f}%|{row['funding_stress']['return_pct']:+.4f}%|{row['base']['liquidations']}|")
        lines += [""]
    if "training_selection" in report:
        lines += [f"Locked training choice: `{report['training_selection']['variant_id']}`.", ""]
    for phase in ("validation", "final"):
        if report.get(phase):
            row = report[phase]
            ci = row["base"]["block_mean_ci99"]
            lines += [f"{phase.title()} net: **{row['base']['return_pct']:+.4f}%**; annualized: {row['base']['annualized_return_pct']:+.4f}%; conservative drawdown: {row['base']['max_drawdown_pct']:.4f}%; daily envelope drawdown: {row['base']['max_daily_drawdown_pct']:.4f}%.", "",
                      f"Doubled costs: {row['cost_stress']['return_pct']:+.4f}%; positive funding reduced25% (negative payments unchanged): {row['funding_stress']['return_pct']:+.4f}%.", "",
                      f"99%7-day circular-block interval for mean daily return: [{ci['lower']*100:+.6f}%, {ci['upper']*100:+.6f}%]. Conditional approximate inference; stationarity and selection uncertainty remain.", "",
                      f"Funding settlements credited: {row['base']['settlements']}; modeled liquidations: {row['base']['liquidations']}; checks: `{canonical(row['checks'])}`.", ""]
    lines += [f"Retrospective provisional candidate: **{report.get('retrospective_provisional_candidate', False)}**. Live/prop qualification: **false**.", "",
              "Funding settlement count is not an independent trade sample. Correlated days, changing regimes, venue default/counterparty/outage risk and imperfect marks limit the evidence. Forward observation and official executable account data remain required. No alternative replaces a failed locked candidate.", ""]
    MARKDOWN.write_text("\n".join(lines), encoding="utf-8")


def freeze():
    if OUTPUT.exists():
        report = json.loads(OUTPUT.read_text(encoding="utf-8"))
        verify(report)
        return report
    producers = ["propdesk/funding_lab.py", "scripts/research_funding.py", "propdesk/research_stats.py"]
    protocol = {"version": "funding-carry-v1", "frozen_at": now(), "windows": WINDOWS,
                "variants": lab.variants(), "producers": {p: file_hash(ROOT / p) for p in producers},
                "hypothesis": "Positive perpetual funding may compensate a fully funded spot-long/perpetual-short hedge after both-leg friction, basis changes and isolated-margin risk. Actual realized funding is only known at settlement.",
                "previous_studies": "208 hourly spot variants failed2025 validation; eight liquidity/FVG variants lost on inspected2026Q3. Daily ETF studies and market periods previously inspected. No global blind-final claim; all seven additional variants count in the cumulative research ledger.",
                "selection": "Evaluate seven variants in2024, require positive base/doubled-cost/75%-positive-funding return,>=200 credited settlements, zero modeled liquidations,<=5% drawdown,<=2.5% daily envelope drawdown. ChooseONE by return/max(drawdown,.25), then lexicographicID. Persist selection hash BEFORE2025 simulation. No replacement if2025 fails. Persist confirmation hash BEFORE2026 simulation; never open2026 performance if validation fails.",
                "validation_final_gates": "Positive base/doubled-cost/75%-positive-funding return;>=180 full calendar days and>=6months;>=200 funding settlements; zero modeled liquidations;99%7-day block mean CI lower>0; both chronological halves positive; largest positive month share<=.5;<=5% maxdrawdown and<=2.5% daily envelope; per-asset beta absolute<=.1. Candidate remains provisional, live/propfalse.",
                "capital": "100kportfolio BTCETH50keach; each spotcash25k+isolatedperpcash25k; baseqty=min25kspotbudget/perpsafeavailablecollateral, roundeddown1e-6. Equalfixedunitsbetweenfills,<=initial25kspotnotionalperasset; market drift may change notional. No spot-profittransfer into collateral, borrow, idlecashinterest or free margin.",
                "signals": "Static alwayson benchmark. Persistence mean of3/9/21 past realized settlementrates; entry strictmean>0or.00005; exit mean<=0; decisions use only eventsstrictlybeforecurrentopen; eachdecisionfillsnextclosedbaropen. Tradecosts included; ratesnotquotedfuturefunding. Staticdisabledafterliquidation.",
                "margin": "Maintenanceproxy.5%currentperpnotional, tradeOHLCupperpriceproxy(marknotverified). Gapbreachprioritizesliquidation beforeplannedexit; intrabarbreach usesperphigh andspotlow nonsimultaneousadverseenvelope+1%perpliquidationpenalty. Persistencepriorclosedperpmarginequity<50%currentnotional reducespairedquantity50%atnextopen. No futurehigh usedforrebalancing.",
                "settlements": "Creditshortq*actualsettledrate*officialmarkwhenpresent; otherwise PRECEDING closedperptradeprice. Nevercurrent/futureclose/highasfundingmark. Newlyopenedpair mustbeheld>1minute beforeeligiblesettlement; exitatsettlementtimestamp closesbeforeevent andreceivesnopaymentafterexit. Eventratemeanupdatedafterexecution, cannotpredictsame-eventrate. MillisecondtimestampsparsedasUTCdatetime. Conservativepre-receiptperphighmargincheck liquidatespair BEFORE allfundingreceiptsifpriorcollateral insufficient; positivefundingcannotrescueanambiguous earlierhigh. Negativefundingthenanotherhighcheck. Nofundingafterliquidation.",
                "friction": {"spot_fee_bps": 10, "perp_fee_bps": 5, "slippage_bps": 2,
                             "full_spread_bps": 1, "stress_multiplier": 2,
                             "positive_funding_stress_multiplier": .75,
                             "negative_funding_stress": "Unchanged; no loss discount",
                             "status": "Illustrative conservative assumptions, notverified tariffs/filters"},
                "data": "SamevenueofficialBinancespot1h andUSD-Mperpetual1h closedcandles full2024Jan–2026Sep; fundingsettlementarchive actualrates/intervals. ImmutableSHA256receiptsandchecksums required. Allhourlytimestampsmustmatch; no gaps/imputation/date deletion. Knownfundingintervalschecksettlementgaps. NullintervalallowedonlyverifiedexhaustiveofficialRESTpaginationreceipt; expectedintervalunknownrecorded, neverinvent8h or missingrate. Finalboundarypositionsclosedhypothetically, noentrylastbar.",
                "inference": "Dailycalendar returns includingflatdays;5000circular7dayblocks,99%CI seed20261002; inferenceapproxconditionalstationarity, noindependenceclaim. Seven adaptivevariantsandallpriorstudiesremainselectionuncertainty. Perassetregressionbeta/correlationdescriptive, notcausalproof.",
                "permissions": "PersonalnonproductionCCBYNCSAarchivalresearch; noactualaccounts/orders/purchases/Telegram/credentials. Requireverifiedlicensedproductionfeedandprospectivepaperdata beforelive."}
    report = {"phase": "frozen_awaiting_funding_data", "protocol": protocol,
              "protocol_sha256": digest(protocol), "retrospective_provisional_candidate": False,
              "live_qualified": False, "prop_qualified": False}
    PROTOCOL_DOC.write_text("# Frozen funding-carry protocol\n\nPreregistered before funding strategy outcomes.\n\n```json\n" + json.dumps(protocol, indent=2) + "\n```\n", encoding="utf-8")
    write_report(report)
    return report


def verify(report):
    protocol = report["protocol"]
    if digest(protocol) != report["protocol_sha256"] or protocol["variants"] != lab.variants():
        raise ValueError("Frozen protocol/grid changed")
    for path, expected in protocol["producers"].items():
        if file_hash(ROOT / path) != expected:
            raise ValueError("Producer changed after freeze: " + path)


def load_inputs(report):
    paths = {f"{symbol}_{kind}": ROOT / directory / f"{symbol}-{suffix}.json"
             for symbol in ("BTCUSDT", "ETHUSDT")
             for kind, directory, suffix in (("spot", ".local/exchange-history", "1h"),
                                             ("perp", ".local/funding-history", "1h"),
                                             ("funding", ".local/funding-history", "funding"))}
    receipts = {"spot_manifest": ROOT / ".local/exchange-history/manifest.json",
                "funding_manifest": ROOT / ".local/funding-history/manifest.json"}
    missing = [str(p.relative_to(ROOT)) for p in list(paths.values()) + list(receipts.values()) if not p.exists()]
    if missing:
        raise ValueError("Official complete funding inputs not ready: " + ", ".join(missing))
    hashes = {key: {"path": str(path.relative_to(ROOT)), "sha256": file_hash(path)} for key, path in {**paths, **receipts}.items()}
    if report.get("input_lock") and report["input_lock"] != hashes:
        raise ValueError("Research input changed after first outcomes")
    # Receipt binding is checked before values are simulated; no source fallback.
    funding_manifest = json.loads(receipts["funding_manifest"].read_text())
    spot_manifest = json.loads(receipts["spot_manifest"].read_text())
    for key, path in paths.items():
        manifest = spot_manifest if key.endswith("_spot") else funding_manifest
        relative = path.name
        entries = [row for row in manifest.get("datasets", []) if Path(row.get("json", "")).name == relative]
        if len(entries) != 1 or entries[0].get("json_sha256") != hashes[key]["sha256"]:
            raise ValueError("Funding manifest does not bind file: " + relative)
        if not entries[0].get("complete_calendar"):
            raise ValueError("Incomplete funding calendar: " + relative)
        if entries[0].get("failures"):
            raise ValueError("Funding acquisition failures: " + relative)
        if not entries[0].get("sources") or any(not source.get("checksum_verified") for source in entries[0]["sources"]):
            raise ValueError("Unverified archive checksum: " + relative)
    report["input_lock"] = hashes
    report["input_lock_sha256"] = digest(hashes)
    write_report(report)
    result = {key: json.loads(path.read_text()) for key, path in paths.items()}
    for symbol in ("BTCUSDT", "ETHUSDT"):
        entry = next(row for row in funding_manifest["datasets"] if Path(row.get("json", "")).name == symbol + "-funding.json")
        result[symbol + "_allow_unknown_intervals"] = bool(entry.get("exhaustive_pagination_verified"))
    return result


def experiment(inputs, variant, phase, *, samples=5000):
    start, end = WINDOWS[phase]
    def run(friction=1, funding_multiplier=1):
        assets = [lab.simulate(inputs[symbol + "_spot"], inputs[symbol + "_perp"], inputs[symbol + "_funding"],
                               variant, start, end, friction=friction,
                               positive_funding_multiplier=funding_multiplier,
                               allow_unknown_intervals=inputs[symbol + "_allow_unknown_intervals"])
                  for symbol in ("BTCUSDT", "ETHUSDT")]
        return lab.portfolio(assets, samples=samples)
    base, costs, funding = run(), run(2), run(1, .75)
    return {"variant": variant, "base": base, "cost_stress": costs, "funding_stress": funding}


def basic_checks(row):
    base = row["base"]
    return {"positive_net": base["return_pct"] > 0,
            "positive_double_costs": row["cost_stress"]["return_pct"] > 0,
            "positive_reduced_funding": row["funding_stress"]["return_pct"] > 0,
            "at_least_200_settlements": base["settlements"] >= 200,
            "no_liquidations": base["liquidations"] == 0,
            "max_drawdown_at_most_5pct": base["max_drawdown_pct"] <= 5,
            "daily_envelope_at_most_2_5pct": base["max_daily_drawdown_pct"] <= 2.5}


def confirm_checks(row):
    base, returns = row["base"], row["base"]["daily_returns"]
    midpoint = len(returns) // 2
    def compound(values):
        result = 1
        for value in values:
            result *= 1 + value
        return result - 1
    concentration = base["monthly"]["largest_positive_month_share"]
    return {**basic_checks(row), "at_least_180_days": len(returns) >= 180,
            "at_least_6_months": base["monthly"]["months"] >= 6,
            "block_ci99_lower_positive": base["block_mean_ci99"]["lower"] > 0,
            "both_halves_positive": compound(returns[:midpoint]) > 0 and compound(returns[midpoint:]) > 0,
            "positive_month_concentration_at_most_half": concentration is not None and concentration <= .5,
            "asset_beta_abs_at_most_point1": all(asset["market_beta"] is not None and abs(asset["market_beta"]) <= .1 for asset in base["assets"])}


def run(report):
    verify(report)
    inputs = load_inputs(report)
    registered = report["protocol"]["variants"]
    report.setdefault("training", [])
    evaluated = [row["variant"] for row in report["training"]]
    if len(evaluated) > len(registered) or evaluated != registered[:len(evaluated)]:
        raise ValueError("Training resume is not the exact registered ordered prefix")
    for variant in registered[len(evaluated):]:
        row = experiment(inputs, variant, "training")
        row["checks"] = basic_checks(row)
        report["training"].append(row)
        write_report(report)
    if [row["variant"] for row in report["training"]] != registered:
        raise ValueError("Full seven-variant training grid required before selection")
    survivors = [row for row in report["training"] if all(row["checks"].values())]
    if not survivors:
        report.update(phase="completed_no_training_candidate_final_unopened", reason="No funding variant passed frozen2024 gates.2025/2026 outcomes remain unopened.")
        write_report(report)
        return report
    chosen = sorted(survivors, key=lambda row: (-row["base"]["return_pct"] / max(.25, row["base"]["max_drawdown_pct"]), row["variant"]["id"]))[0]
    selection = {"variant_id": chosen["variant"]["id"], "protocol_sha256": report["protocol_sha256"],
                 "training_results_sha256": digest(report["training"]), "input_lock_sha256": report["input_lock_sha256"]}
    if report.get("training_selection") and report["training_selection"] != selection:
        raise ValueError("Locked training selection changed")
    if "training_selection" not in report:
        report["training_selection"] = selection
        report["training_selection_sha256"] = digest(selection)
        report["training_selection_locked_at"] = now()
        report["phase"] = "training_choice_locked_before_validation"
        write_report(report)
    if "validation" not in report:
        report["validation"] = experiment(inputs, chosen["variant"], "validation")
        report["validation"]["checks"] = confirm_checks(report["validation"])
        write_report(report)
    if not all(report["validation"]["checks"].values()):
        report.update(phase="completed_validation_failed_final_unopened", reason="Locked2024 winner failed2025 confirmation.2026 funding performance remains unopened; no candidate replacement.")
        write_report(report)
        return report
    if "validation_confirmation_sha256" not in report:
        report["validation_confirmation_sha256"] = digest(report["validation"])
        report["validation_confirmation_locked_at"] = now()
        report["phase"] = "validation_confirmed_before_final"
        write_report(report)
    elif report["validation_confirmation_sha256"] != digest(report["validation"]):
        raise ValueError("Locked validation confirmation changed")
    if "final" not in report:
        report["final"] = experiment(inputs, chosen["variant"], "final")
        report["final"]["checks"] = confirm_checks(report["final"])
    report["retrospective_provisional_candidate"] = all(report["final"]["checks"].values())
    report["phase"] = "completed_provisional_candidate" if report["retrospective_provisional_candidate"] else "completed_final_failed"
    report["reason"] = "One locked candidate evaluated; imperfect marks and adaptive historical research prevent live/prop/stable-profit certification. Forward data required."
    write_report(report)
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--freeze", action="store_true")
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()
    if not (args.freeze or args.run):
        parser.error("Use--freeze before--run")
    report = freeze()
    if args.run:
        try:
            report = run(report)
        except ValueError as error:
            report["phase"] = "blocked_data_or_integrity"
            report["reason"] = str(error)
            write_report(report)
            raise
    print(json.dumps({"phase": report["phase"], "protocol_sha256": report["protocol_sha256"],
                      "retrospective_provisional_candidate": report.get("retrospective_provisional_candidate", False)}))


if __name__ == "__main__":
    main()
