"""Read-only strategy evidence. Historical eligibility never enables orders."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

STUDIES = {
    "broad": ("broad-research.json", "Часовые стратегии", 208),
    "low_turnover": ("low-turnover-research.json", "Портфель и редкие сделки", 64),
    "liquidity": ("liquidity-full-research.json", "Liquidity / FVG", 4),
    "funding": ("funding-research.json", "Funding и хеджирование", 7),
    "funding_sized": ("funding-sized-research.json", "Funding с резервом капитала", 7),
    "funding_static": ("funding-static-research.json", "Постоянный хедж с повышенным залогом", 1),
    "funding_calibrated": ("funding-calibrated-research.json", "Хедж с расчётом размера по риску", 1),
}

CARRY_CHECKS = frozenset({
    "positive_net", "positive_double_costs", "positive_reduced_funding",
    "at_least_200_settlements", "no_liquidations", "max_drawdown_at_most_5pct",
    "daily_envelope_at_most_2_5pct", "at_least_180_days", "at_least_6_months",
    "block_ci99_lower_positive", "both_halves_positive",
    "positive_month_concentration_at_most_half", "asset_beta_abs_at_most_point1",
})


def passed_carry_stage(value):
    if not isinstance(value, dict):
        return False
    checks = value.get("checks")
    return (isinstance(checks, dict) and CARRY_CHECKS.issubset(checks)
            and all(v is True for v in checks.values()))


def report(root, study):
    if study not in STUDIES:
        raise ValueError("Неизвестное исследование")
    path = Path(root) / "docs" / STUDIES[study][0]
    if not path.is_file():
        return None
    if path.stat().st_size > 16 * 1024 * 1024:
        raise ValueError("Отчёт превышает допустимый размер")
    def reject(_):
        raise ValueError("Неконечное число в отчёте")
    value = json.loads(path.read_text(encoding="utf-8"), parse_constant=reject)
    if not isinstance(value, dict):
        raise ValueError("Неверный формат отчёта")
    return value


def verified_protocol(value, root):
    p = value.get("protocol")
    if not isinstance(p, dict) and value.get("study_id") == "binance-spot-btceth-liquidity-fixed-v1":
        # This earlier registration fingerprints the original, pretty-printed
        # plan file. Preserve its existing format and source identity.
        p = value.get("plan")
        lock = value.get("training_lock")
        if not isinstance(p, dict) or not isinstance(lock, dict):
            return False
        raw = (json.dumps(p, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()
        if hashlib.sha256(raw).hexdigest() != lock.get("protocol_sha256"):
            return False
        for name, key in (("propdesk/liquidity.py", "engine_sha256"),
                          ("scripts/research_liquidity.py", "producer_sha256")):
            path = Path(root) / name
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != value.get(key):
                return False
        return True
    if not isinstance(p, dict):
        return False
    raw = json.dumps(p, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    if hashlib.sha256(raw).hexdigest() != value.get("protocol_sha256"):
        return False
    producers = p.get("producers", p.get("producer_hashes", {}))
    if not isinstance(producers, dict) or not producers:
        return False
    base = Path(root).resolve()
    for name, expected in producers.items():
        if not isinstance(name, str) or Path(name).is_absolute():
            return False
        path = (base / name).resolve()
        if not path.is_relative_to(base) or not path.is_file():
            return False
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            return False
    return True


def board(root):
    studies, primary = [], None
    for identifier, (filename, title, count) in STUDIES.items():
        try:
            value = report(root, identifier)
            valid = value is not None and verified_protocol(value, root)
        except (OSError, ValueError, TypeError, UnicodeError):
            value, valid = None, False
        row = {"id": identifier, "title": title, "variant_count": count,
               "phase": value.get("phase", value.get("status", "unknown")) if value else "unavailable",
               "protocol_verified": valid,
               "eligible_for_forward_test": False,
               "report_url": "/api/trader/evidence?study=" + identifier,
               "mode": "historical_research"}
        # One fixed static-carry primary can become a paper candidate; failed
        # studies and their diagnostic alternatives never substitute for it.
        if identifier == "funding_calibrated" and valid:
            candidate = value.get("retrospective_provisional_candidate") is True
            if (candidate and value.get("phase") == "completed_provisional_candidate"
                    and passed_carry_stage(value.get("validation"))
                    and passed_carry_stage(value.get("final"))):
                row["eligible_for_forward_test"] = True
                primary = {"study": identifier, "title": title,
                           "mode": "paper_candidate", "report_url": row["report_url"]}
        studies.append(row)
    return {"phase": "candidate_needs_forward_test" if primary else "no_qualified_strategy",
            "variant_count": sum(r["variant_count"] for r in studies if str(r["phase"]).startswith("completed")),
            "registered_variant_count": sum(r["variant_count"] for r in studies if r["phase"] != "unavailable"),
            "studies": studies, "primary": primary,
            "live_orders": False, "telegram_enabled": False,
            "forward_test_required": True,
            "note": "Исторические результаты не подтверждают стабильную будущую прибыль."}
