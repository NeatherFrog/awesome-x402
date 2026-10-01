"""Train-only cross-market selection with locked, diagnostic holdouts.

No network, broker, files or orders live here. A caller supplies canonical closed
bars, persists the optional lock callback and retains its own source snapshots.
Only the training-ranked primary market may become a research candidate.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import statistics
from copy import deepcopy
from datetime import date, datetime, timezone
from urllib.parse import urlsplit

from . import backtest, market, payout, strategies
from .risk import normalize_profile

MAX_DATASETS = 12
MAX_LOCKED_MARKETS = 3
MAX_PROFILES = 30
BOOTSTRAP_RESAMPLES = 3000
FIRM_RULE_MAX_AGE_DAYS = 90
EXECUTION_FIELDS = {"fee_bps", "fee_per_unit", "spread_bps", "slippage_bps", "contract_multiplier", "quantity_step", "max_leverage"}


def _hash(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def _source(provenance: dict) -> str:
    label = str(provenance.get("source", "")) + " " + str(provenance.get("provider", ""))
    if provenance.get("synthetic") is True or any(word in label.lower() for word in ("demo", "synthetic", "generated", "illustrative")):
        return "demo"
    if provenance.get("source") == "csv" or "yahoo" in label.lower():
        return "csv"
    return "unknown"


def _currency(value, name):
    if not isinstance(value, str) or len(value) != 3 or not value.isascii() or not value.isalpha():
        raise ValueError(f"{name} must be a three-letter currency code")
    return value.upper()


def _quote_currency(symbol: str, provenance: dict, account_currency: str) -> tuple[str, bool]:
    explicit = provenance.get("quote_currency", provenance.get("currency"))
    if explicit is not None:
        if explicit == "GBp":
            return "GBX", False  # Yahoo pence must not silently become GBP.
        return _currency(explicit, "quote_currency"), False
    pair = symbol.removesuffix("=X")
    currencies = {"USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "NZD"}
    if len(pair) == 6 and pair[:3] in currencies and pair[3:] in currencies:
        return pair[3:], False
    return account_currency, True


def _settings(settings: dict | None) -> tuple[dict, str, datetime, dict]:
    supplied = {} if settings is None else deepcopy(settings)
    if not isinstance(supplied, dict):
        raise ValueError("scanner settings must be an object")
    account_currency = _currency(supplied.pop("account_currency", "USD"), "account_currency")
    as_of = supplied.pop("as_of", None)
    now = market.utc_datetime(as_of) if as_of is not None else datetime.now(timezone.utc)
    profile = normalize_profile(supplied.get("prop_profile", {}))
    defaults = {"account_size": profile["account_size"], "risk_pct": min(0.25, profile["max_risk_pct"]),
                "fee_bps": 2.0, "slippage_bps": 1.0, "spread_bps": 1.0, "max_leverage": 2.0,
                "quantity_step": profile["quantity_step"], "train_fraction": 0.6,
                "max_drawdown_pct": profile["max_loss_pct"] * 0.8}
    defaults.update(supplied)
    defaults["strategy_ids"] = [item["id"] for item in strategies.catalog()]
    defaults["prop_profile"] = profile
    defaults["source"] = "unknown"
    config = backtest.normalize_config(defaults)
    if config["risk_pct"] > profile["max_risk_pct"]:
        raise ValueError("risk_pct exceeds the selected rule profile maximum")
    config["prop_profile"]["account_size"] = config["account_size"]
    return config, account_currency, now, profile


def train_market(symbol: str, prefix: list[dict], config: dict) -> dict:
    """Only a training prefix is passed to this fitting helper."""
    labels = strategies.regimes(prefix)
    families = []
    for definition in strategies.catalog():
        strategy_id = definition["id"]
        if strategy_id == "buy_hold":
            continue
        candidates = [{"params": params, "signals": strategies.signals_for(prefix, strategy_id, params, regime_labels=labels)} for params in strategies.parameter_candidates(strategy_id)]
        chosen, result = backtest._choose_candidate(prefix, candidates, config, 0, len(prefix), strategy_id)
        walk_forward = backtest._walk_forward(prefix, candidates, config, len(prefix), strategy_id)
        families.append({"id": strategy_id, "name": definition["name"], "params": candidates[chosen]["params"],
                         "score": round(backtest._train_score(result), 6), "train_metrics": result["metrics"], "walk_forward": walk_forward})
    winner = max(enumerate(families), key=lambda item: (item[1]["score"], -item[0]))[1]
    return {"symbol": symbol, "training_bars": len(prefix), "training_start": prefix[0]["time"],
            "training_end": prefix[-1]["time"], "training_hash": market.data_fingerprint(prefix),
            "winner": winner, "family_results": families}


def adjusted_confidence(trades: list[dict], comparisons: int) -> dict:
    """A stricter descriptive interval; dependence prevents calibrated claims."""
    values = [trade["return_r"] for trade in trades]
    n = len(values)
    result = {"sample_size": n, "comparison_count": comparisons, "interval_confidence_pct": 99,
              "mean_r_interval": None, "lower_above_zero": False,
              "method": "99% descriptive moving-block bootstrap; conservative nominal coverage for up to three diagnostic markets",
              "warnings": ["This is not a calibrated family-wise error bound or a future-profit probability.",
                           "Asset dependence, repeated scans, limited samples and nonstationarity remain unresolved."]}
    if n < 2:
        return result
    block = max(2, min(10, int(math.sqrt(n))))
    rng = random.Random(int(_hash(values)[:16], 16))
    means = []
    for _ in range(BOOTSTRAP_RESAMPLES):
        sample = []
        while len(sample) < n:
            start = rng.randrange(n - block + 1)
            sample.extend(values[start:start + block])
        means.append(statistics.mean(sample[:n]))
    means.sort()
    interval = [round(means[int(0.005 * (BOOTSTRAP_RESAMPLES - 1))], 6),
                round(means[int(0.995 * (BOOTSTRAP_RESAMPLES - 1))], 6)]
    result.update({"mean_r_interval": interval, "block_length": block, "resamples": BOOTSTRAP_RESAMPLES,
                   "lower_above_zero": n >= backtest.MIN_HOLDOUT_TRADES and interval[0] > 0})
    return result


def full_holdout_cadence(report: dict, trades: list[dict]) -> dict:
    first = market.utc_datetime(report["data"]["holdout_start"])
    last = market.utc_datetime(report["data"]["end"])
    days = payout._business_day_count(first.date(), last.date())
    if days < 1:
        raise ValueError("Holdout has no weekday cadence exposure")
    return {"trades_per_day": len(trades) / days, "trade_rate_basis": "oos_full_holdout_closed_trades_per_business_day",
            "full_holdout_start": first.isoformat().replace("+00:00", "Z"),
            "full_holdout_end": last.isoformat().replace("+00:00", "Z"), "business_days": days,
            "closed_trades": len(trades), "includes_inactive_holdout_days": True}


def _verified_rules(profile: dict, now: datetime) -> list[str]:
    reasons = []
    if profile["status"] != "user_verified":
        reasons.append("Firm rules are illustrative or not user verified")
    try:
        url = urlsplit(profile["source_url"])
        if url.scheme != "https" or not url.hostname or url.username or url.password:
            reasons.append("A public HTTPS rule source is required")
    except ValueError:
        reasons.append("The rule source URL is invalid")
    try:
        verification = profile["verified_at"]
        if isinstance(verification, str) and len(verification) == 10:
            day = date.fromisoformat(verification)
            if day.isoformat() != verification:
                raise ValueError("ambiguous verification date")
            stamp = datetime.combine(day, datetime.min.time(), timezone.utc)
        else:
            stamp = market.utc_datetime(verification)
        age = (now - stamp).total_seconds() / 86400
        if not 0 <= age <= FIRM_RULE_MAX_AGE_DAYS:
            reasons.append("Rule verification is future dated or more than 90 days old")
    except (ValueError, TypeError):
        reasons.append("A YYYY-MM-DD verification date or explicit UTC timestamp is required")
    return reasons


def compare_firms(primary: dict, profiles: list[dict], *, selected: bool, now: datetime, account_currency: str) -> dict:
    rows = []
    report = primary["report"]
    locked_id = primary["strategy_id"]
    strategy = next(item for item in report["strategies"] if item["id"] == locked_id)
    trades = strategy["trades"]
    cadence = full_holdout_cadence(report, trades)
    for raw_profile in profiles:
        profile = normalize_profile(raw_profile)
        reasons = _verified_rules(profile, now)
        currency = _currency(raw_profile.get("account_currency", "USD"), "profile account_currency")
        if currency != account_currency:
            reasons.append("Firm account currency differs; cross-currency EV cannot be ranked without conversion")
        if profile["ea_allowed"] is False:
            reasons.append("This profile prohibits automated trading")
        if not selected:
            reasons.append("The locked primary market did not qualify; another holdout is not substituted")
        if len(trades) < 30:
            reasons.append("At least 30 out-of-sample trades are required for payout economics")
        row = {"profile_id": profile["id"], "profile_name": profile["name"], "status": "needs_verified_rules" if _verified_rules(profile, now) else "not_supported",
               "rules_verified": not _verified_rules(profile, now), "reasons": reasons, "simulation": None,
               "account_currency": currency, "recommended": False}
        if not reasons:
            risk_pct = report["config"]["risk_pct"]
            if risk_pct > profile["max_risk_pct"]:
                row["reasons"].append("Research risk exceeds this firm profile risk limit")
            elif not 0.001 <= cadence["trades_per_day"] <= 100:
                row["reasons"].append("Observed full-holdout cadence is outside the supported payout model range")
            else:
                config = {"risk_pct": risk_pct, "paths": 300, "seed": 42, "returns_are_oos": True,
                          "data_source": report["data"]["source"], "trades_per_day": cadence["trades_per_day"],
                          "trade_rate_basis": cadence["trade_rate_basis"], "max_calendar_days": min(60, profile["max_calendar_days"] or 60)}
                simulation = payout.simulate(trades, profile, config)
                row["simulation"] = simulation
                row["status"] = "modeled_positive" if simulation["feasible"] and simulation["status"] == "supported" and simulation["net_expected_value"] > 0 else "model_not_positive"
                row["reasons"].extend(simulation.get("reasons", []))
        rows.append(row)
    positive = sorted((row for row in rows if row["status"] == "modeled_positive"),
                      key=lambda row: (-row["simulation"]["net_expected_value"], row["profile_id"]))
    preferred = positive[0]["profile_id"] if positive else None
    if positive:
        positive[0]["recommended"] = True
    return {"status": "research_candidate" if preferred else "needs_verified_rules" if not any(row["rules_verified"] for row in rows) else "no_supported_positive_model",
            "recommended_profile_id": preferred, "profiles": rows, "cadence": cadence,
            "basis": "Empirical first-payout net EV in a common account currency, not real firm acceptance or future profit",
            "warnings": ["Profile verification is a user attestation, not independent confirmation by this scanner.",
                         "News, session policies, instruments, overnight/weekend positions and actual firm execution require separate checks.",
                         "R returns are rescaled to each account size; different account lot rounding is not replayed.",
                         "The payout model uses weekdays even for crypto; completed trade cadence does not reproduce actual holding times."]}


def scan(datasets: dict, settings: dict | None = None, profiles: list[dict] | None = None, *, on_lock=None, progress=None) -> dict:
    """Select a primary market on training, then gate its frozen holdout.

    At most three locked markets receive final diagnostics. A better diagnostic
    holdout never replaces a failed primary. Generic rule examples can support
    a paper illustration but cannot produce a recommended firm.
    """
    if not isinstance(datasets, dict) or not 1 <= len(datasets) <= MAX_DATASETS:
        raise ValueError("Provide between 1 and 12 market datasets")
    if on_lock is not None and not callable(on_lock) or progress is not None and not callable(progress):
        raise ValueError("Scanner callbacks must be callable")
    config, account_currency, now, default_profile = _settings(settings)
    profiles = [default_profile] if profiles is None else deepcopy(profiles)
    if not isinstance(profiles, list) or len(profiles) > MAX_PROFILES:
        raise ValueError("At most 30 firm profiles are supported")
    normalized_profiles = [normalize_profile(profile) for profile in profiles]
    if len({profile["id"] for profile in normalized_profiles}) != len(profiles):
        raise ValueError("Firm profile IDs must be unique")
    prepared, exclusions = {}, []
    for raw_symbol, dataset in datasets.items():
        if not isinstance(raw_symbol, str) or not raw_symbol.strip() or len(raw_symbol) > 40:
            raise ValueError("Market symbol must be a nonempty string of at most 40 characters")
        symbol = raw_symbol.strip().upper()
        if symbol in prepared:
            raise ValueError("Market symbols must be unique after normalization")
        if not isinstance(dataset, dict) or not isinstance(dataset.get("provenance", {}), dict):
            raise ValueError(f"{symbol}: dataset requires bars and a provenance object")
        bars = market.validate_bars(dataset.get("bars"))
        if len(bars) < backtest.MIN_RESEARCH_BARS:
            raise ValueError(f"{symbol}: at least 300 closed bars are required")
        provenance = deepcopy(dataset.get("provenance", {}))
        try:
            if len(json.dumps(provenance, allow_nan=False).encode()) > 65536:
                raise ValueError("provenance is too large")
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{symbol}: provenance must be finite JSON under 64 KiB") from exc
        if "synthetic" in provenance and not isinstance(provenance["synthetic"], bool):
            raise ValueError("provenance.synthetic must be boolean")
        quote_currency, assumed = _quote_currency(symbol, provenance, account_currency)
        if quote_currency != account_currency:
            exclusions.append({"symbol": symbol, "status": "needs_currency_conversion", "quote_currency": quote_currency,
                               "account_currency": account_currency, "reason": "Price P&L is in another currency; no dynamic FX conversion is implemented"})
            continue
        asset_config = deepcopy(config)
        asset_config["symbol"], asset_config["source"] = symbol, _source(provenance)
        execution_model = dataset.get("execution_model", {})
        if not isinstance(execution_model, dict) or set(execution_model) - EXECUTION_FIELDS:
            raise ValueError(f"{symbol}: execution_model contains unsupported fields")
        asset_config.update(execution_model)
        asset_config = backtest.normalize_config(asset_config)
        prepared[symbol] = {"bars": bars, "provenance": provenance, "config": asset_config,
                            "context": {"account_currency": account_currency, "quote_currency": quote_currency,
                                        "currency_assumed": assumed, "contract_multiplier": asset_config["contract_multiplier"],
                                        "quantity_step": asset_config["quantity_step"], "planning_only": True,
                                        "execution_model": {key: asset_config[key] for key in sorted(EXECUTION_FIELDS)},
                                        "execution_assumptions": True}}
    training = []
    for index, symbol in enumerate(sorted(prepared), 1):
        asset = prepared[symbol]
        end = int(len(asset["bars"]) * config["train_fraction"])
        training.append(train_market(symbol, asset["bars"][:end], asset["config"]))
        if progress:
            progress({"phase": "training", "completed": index, "total": len(prepared), "symbol": symbol})
    ranked = sorted(training, key=lambda item: (-item["winner"]["score"], item["symbol"]))
    candidates = [{"rank": index + 1, "symbol": item["symbol"], "strategy_id": item["winner"]["id"],
                   "params": deepcopy(item["winner"]["params"]), "training_score": item["winner"]["score"],
                   "training_bars": item["training_bars"], "training_hash": item["training_hash"],
                   "training_start": item["training_start"], "training_end": item["training_end"],
                   "train_metrics": item["winner"]["train_metrics"], "walk_forward": item["winner"]["walk_forward"]}
                  for index, item in enumerate(ranked[:MAX_LOCKED_MARKETS])]
    lock = {"version": "train-only-global-scanner-v1", "primary_symbol": candidates[0]["symbol"] if candidates else None,
            "candidates": candidates, "training_results": training, "settings": config,
            "account_currency": account_currency, "max_diagnostic_markets": MAX_LOCKED_MARKETS,
            "selection_basis": "Global primary ranked exclusively by training score; ties by symbol. Holdout only gates the primary.",
            "confidence_policy": {"interval_pct": 99, "bootstrap_resamples": BOOTSTRAP_RESAMPLES}, "exclusions": exclusions}
    lock["execution_models"] = {symbol: deepcopy(asset["context"]["execution_model"]) for symbol, asset in prepared.items()}
    lock = deepcopy(lock)
    lock_hash = _hash(lock)
    if on_lock:
        on_lock(deepcopy({"phase": "training_locked", "training_lock": lock, "training_lock_sha256": lock_hash}))
    if progress:
        progress({"phase": "training_locked", "primary_symbol": lock["primary_symbol"], "candidates": len(candidates)})
    outcomes = []
    for chosen in candidates:
        symbol = chosen["symbol"]
        asset = prepared[symbol]
        research = backtest.run_research(asset["bars"], asset["config"])
        if research["training_candidate"] != chosen["strategy_id"]:
            raise ValueError("Frozen training winner changed; abort rather than choose another holdout")
        result = next(item for item in research["strategies"] if item["id"] == chosen["strategy_id"])
        if result["params"] != chosen["params"] or result["train_metrics"] != chosen["train_metrics"]:
            raise ValueError("Frozen training parameters or metrics changed during final evaluation")
        confidence = adjusted_confidence(result["trades"], len(candidates))
        qualified = result["eligible"] and confidence["lower_above_zero"] and asset["config"]["source"] == "csv"
        reasons = list(result["reasons"])
        if not confidence["lower_above_zero"]:
            reasons.append("The stricter descriptive 99% mean-R interval includes zero or lacks 20 holdout trades")
        if asset["context"]["currency_assumed"]:
            research["summary"]["warnings"].append("Quote currency is assumed to match account currency; verify the actual broker denomination")
        research["data"]["provenance"] = deepcopy(asset["provenance"])
        research["data"]["source_format"] = "canonical_ohlcv"
        research["market_context"] = deepcopy(asset["context"])
        research["scanner_selected"] = qualified and chosen["rank"] == 1
        if not research["scanner_selected"]:
            research["selected_strategy"] = None
            research["summary"]["selected_name"] = None
            research["summary"]["status"] = "demo" if asset["config"]["source"] == "demo" else "no_qualified_strategy"
            research["latest_signal"]["status"] = "demo" if asset["config"]["source"] == "demo" else "research_only"
            research["latest_signal"]["reason"] = "Global scanner did not select this market; it is a diagnostic research observation"
        research["summary"]["core_qualified_count"] = research["summary"]["qualified_count"]
        research["summary"]["qualified_count"] = int(research["scanner_selected"])
        research["scanner_reasons"] = reasons
        outcomes.append({"symbol": symbol, "rank": chosen["rank"], "primary": chosen["rank"] == 1,
                         "strategy_id": chosen["strategy_id"], "qualified": qualified, "selected": research["scanner_selected"],
                         "adjusted_confidence": confidence, "reasons": reasons, "report": research})
        if progress:
            progress({"phase": "holdout", "symbol": symbol, "completed": len(outcomes), "total": len(candidates)})
    primary = outcomes[0] if outcomes else None
    selected_symbol = primary["symbol"] if primary and primary["selected"] else None
    firms = compare_firms(primary, profiles, selected=bool(selected_symbol), now=now, account_currency=account_currency) if primary else {
        "status": "no_supported_market", "recommended_profile_id": None, "profiles": [], "reasons": ["No market has compatible price/account currency"]}
    if _hash(lock) != lock_hash:
        raise AssertionError("Training lock changed after holdout evaluation")
    return {"phase": "final_review", "training_lock": lock, "training_lock_sha256": lock_hash,
            "markets": outcomes, "primary_symbol": lock["primary_symbol"], "selected_symbol": selected_symbol,
            "selected_strategy": primary["strategy_id"] if selected_symbol else None,
            "selected_profile_id": firms["recommended_profile_id"],
            "firm_comparison": firms, "decision": "paper_research_candidate" if selected_symbol else "no_qualified_primary",
            "provenance": {symbol: deepcopy(asset["provenance"]) for symbol, asset in prepared.items()},
            "exclusions": exclusions, "evaluated_at": now.isoformat().replace("+00:00", "Z"),
            "planning_only": True, "live_orders": False, "live_orders_enabled": False,
            "warnings": ["No diagnostic market replaces a failed primary. Repeated scans of the same holdout can still overfit.",
                         "Public prices, cost assumptions, contract quantities and rule examples are research approximations.",
                         "A positive model does not guarantee future trading profit, eligibility of a strategy, or acceptance of a payout."]}


run_scan = scan
