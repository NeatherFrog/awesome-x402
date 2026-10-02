"""Read-only accounting of the new 8% monthly research campaign.

Fingerprints establish consistency with local artifacts, never a profitable
strategy, execution permission, or independent/statistical proof.
"""
from __future__ import annotations

from functools import lru_cache
import hashlib
import json
from pathlib import Path

PREVIOUS_EVALUATED_CONFIGURATIONS = 292
MAX_REPORT_BYTES = 32 * 1024 * 1024
STUDIES = {
    "pairs": {"file": "relative-value-research.json", "directory": "relative-value-research", "title": "Крипто: относительная стоимость", "count": 48, "engine": "relative_value", "driver": "research_relative_value", "kind": "generic"},
    "pairs_close": {"file": "relative-value-close-research.json", "directory": "relative-value-close-research", "title": "Крипто: повторная оценка исполнения пар", "count": 48, "engine": "relative_value_close", "driver": "research_relative_value_close", "kind": "generic"},
    "sessions": {"file": "session-research.json", "directory": "session-research", "title": "Индексы: сессионные стратегии", "count": 144, "engine": "session_strategies", "driver": "research_sessions", "kind": "sessions"},
    "fx": {"file": "fx-session-research.json", "directory": "fx-session-research", "title": "Форекс: Азия и Лондон", "count": 72, "engine": "fx_sessions", "driver": "research_fx_sessions", "kind": "fx"},
    "native_fvg": {"file": "liquidity-native-research.json", "directory": "liquidity-native-research", "title": "Крипто: снятие ликвидности и FVG", "count": 192, "engine": "liquidity_native", "driver": "research_liquidity_native", "kind": "generic"},
    "native_trend": {"file": "native-crypto-trend-research.json", "directory": "native-crypto-trend-research", "title": "Крипто: тренд и контекст", "count": 96, "engine": "native_crypto_trend", "driver": "research_native_crypto_trend", "kind": "generic"},
    "native_context": {"file": "liquidity-context-research.json", "directory": "liquidity-context-research", "title": "Крипто: FVG в часы Нью-Йорка и Лондона", "count": 48, "engine": "native_liquidity_context", "driver": "research_native_liquidity_context", "kind": "generic"},
    "metals": {"file": "metal-session-research.json", "directory": "metal-session-research", "title": "Золото: сессионные стратегии", "count": 96, "engine": "metal_sessions", "driver": "research_metal_sessions", "kind": "fx"},
    "crypto_flow": {"file": "crypto-flow-research.json", "directory": "crypto-flow-research", "title": "Крипто: направленный поток сделок", "count": 64, "engine": "crypto_flow", "driver": "research_crypto_flow", "kind": "generic"},
}


def digest(value, *, ascii=True):
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=ascii, allow_nan=False).encode()
    return hashlib.sha256(raw).hexdigest()


def _path(root, name):
    if (not isinstance(name, str) or not name or len(name) > 512 or "\\" in name or ":" in name
            or Path(name).is_absolute() or any(part in (".", "..") for part in name.split("/"))):
        raise ValueError("Недопустимый путь артефакта")
    base = Path(root).resolve()
    path = (base / name).resolve()
    if not path.is_relative_to(base):
        raise ValueError("Артефакт находится за пределами проекта")
    return path


def _json(path):
    if not path.is_file():
        return None
    if path.stat().st_size > MAX_REPORT_BYTES:
        raise ValueError("Отчёт превышает допустимый размер")
    def reject(_):
        raise ValueError("Неконечное число в отчёте")
    value = json.loads(path.read_text(encoding="utf-8"), parse_constant=reject)
    if not isinstance(value, dict):
        raise ValueError("Неверный формат артефакта")
    return value


def _receipt(root, directory, filename):
    """Prefer original locks; portable copies are used only when absent.

    This lookup never applies to market inputs. An existing invalid original
    must fail verification rather than being hidden by a valid packaged copy.
    """
    name = "data/" + directory + "/" + filename
    original = _path(root, name)
    lexical = Path(root) / name
    if original.exists() or lexical.is_symlink():
        return _json(original)
    return _json(_path(root, "docs/research-receipts/" + directory + "/" + filename))


@lru_cache(maxsize=256)
def _cached_file_hash(path, signature):
    # The stat signature includes ctime; changing bytes invalidates the cache.
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def _file_hash(path):
    stat = path.stat()
    return _cached_file_hash(str(path), (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns))


def _hash_matches(root, name, expected):
    if not isinstance(expected, str) or len(expected) != 64 or any(c not in "0123456789abcdef" for c in expected):
        return False
    path = _path(root, name)
    return path.is_file() and _file_hash(path) == expected


def read_report(root, study):
    if study not in STUDIES:
        raise ValueError("Неизвестное исследование")
    return _json(_path(root, "docs/" + STUDIES[study]["file"]))


def _input_records(protocol, report, kind):
    if kind == "sessions":
        source = report.get("source_lock", {})
        return [(item.get("path"), item.get("file_sha256"), item.get("canonical_bars_sha256"))
                for item in source.values()] if isinstance(source, dict) and all(isinstance(v, dict) for v in source.values()) else []
    source = protocol.get("inputs", {})
    if not isinstance(source, dict):
        return []
    records = []
    for name, item in source.items():
        if isinstance(item, str):
            records.append((name, item, None))
        elif isinstance(item, dict):
            records.append((item.get("file"), item.get("sha256"), None))
        else:
            return []
    acquisition = protocol.get("acquisition_receipt")
    if acquisition is not None:
        if not isinstance(acquisition, dict):
            return []
        records.append((acquisition.get("file"), acquisition.get("sha256"), None))
    return records


def _rows(report, kind):
    if kind == "sessions":
        rows = report.get("variants", [])
        return [(item.get("id"), item.get("training")) for item in rows if isinstance(item, dict)] if isinstance(rows, list) else []
    rows = report.get("training", [])
    if not isinstance(rows, list):
        return []
    return [(item.get("id", item.get("variant", {}).get("id") if isinstance(item.get("variant"), dict) else None),
             item if kind == "fx" else item.get("target")) for item in rows if isinstance(item, dict)]


def inspect(root, study, value):
    spec, reasons = STUDIES[study], []
    kind, ascii = spec["kind"], spec["kind"] != "sessions"
    protocol = value.get("protocol", {})
    if not isinstance(protocol, dict):
        protocol = {}
    protocol_digest = bool(protocol) and digest(protocol, ascii=ascii) == value.get("protocol_sha256")
    locked_protocol = _receipt(root, spec["directory"], "protocol.json")
    protocol_lock = locked_protocol == protocol and bool(protocol)
    if not protocol_digest or not protocol_lock:
        reasons.append("Контрольная сумма или фиксация протокола не подтверждена")
    producers = value.get("producer_sha256") if kind == "sessions" else protocol.get("producers")
    required = {"propdesk/" + spec["engine"] + ".py", "scripts/" + spec["driver"] + ".py"}
    producer_verified = (isinstance(producers, dict) and required.issubset(producers)
                         and all(_hash_matches(root, name, expected) for name, expected in producers.items()))
    if not producer_verified:
        reasons.append("Версия движка или исследовательского скрипта не подтверждена")
    objective = protocol.get("common_target_protocol", {}) if kind == "sessions" else {}
    objective_path = objective.get("path", protocol.get("common_objective_path"))
    objective_hash = objective.get("file_sha256", protocol.get("common_objective_sha256"))
    objective_verified = (_hash_matches(root, objective_path, objective_hash) if objective_path else
                          "docs/EIGHT_PERCENT_PROTOCOL.json" in (producers or {}) and
                          _hash_matches(root, "docs/EIGHT_PERCENT_PROTOCOL.json", producers["docs/EIGHT_PERCENT_PROTOCOL.json"]))
    if not objective_verified:
        reasons.append("Общий протокол цели не подтверждён")
    human_protocol_verified = (not protocol.get("human_protocol_path") or
                              _hash_matches(root, protocol["human_protocol_path"], protocol.get("human_protocol_sha256")))
    if not human_protocol_verified:
        reasons.append("Описание зафиксированных правил изменилось")
    records = _input_records(protocol, value, kind)
    available = bool(records) and all(_path(root, name).is_file() for name, _, _ in records)
    inputs_verified = available and all(_hash_matches(root, name, expected) for name, expected, _ in records)
    if inputs_verified and kind == "sessions":
        for name, _, canonical_hash in records:
            payload = _json(_path(root, name))
            if not payload or digest(payload.get("bars"), ascii=False) != canonical_hash:
                inputs_verified = False
    if not available:
        reasons.append("Исходные файлы истории отсутствуют; полный повтор не подтверждён")
    elif not inputs_verified:
        reasons.append("Контрольная сумма истории не совпадает")
    declared = protocol.get("variants", protocol.get("grid", []))
    declared_ids = {item.get("id") for item in declared if isinstance(item, dict)} if isinstance(declared, list) else set()
    rows = _rows(value, kind)
    evaluated = [(name, item) for name, item in rows if isinstance(name, str) and isinstance(item, dict)
                 and isinstance(item.get("passed"), bool) and isinstance(item.get("base"), dict)
                 and isinstance(item["base"].get("total_return"), (int, float))
                 and not isinstance(item["base"]["total_return"], bool)]
    ids = [name for name, _ in evaluated]
    rows_verified = (len(ids) == len(rows) and len(ids) == len(set(ids)) and set(ids).issubset(declared_ids)
                     and len(ids) <= spec["count"] and len(declared_ids) <= spec["count"])
    training_verified, result_verified = not evaluated, True
    if evaluated:
        if kind == "sessions":
            lock = _receipt(root, spec["directory"], "training-lock.json") or {}
            source_lock = _receipt(root, spec["directory"], "source-lock.json")
            training_verified = (digest(lock, ascii=False) == value.get("training_lock_sha256")
                and lock.get("protocol_sha256") == value.get("protocol_sha256")
                and lock.get("producer_sha256") == producers and source_lock == value.get("source_lock")
                and lock.get("source_lock_sha256") == digest(value.get("source_lock"), ascii=False)
                and lock.get("training_metrics") == dict(evaluated))
            if value.get("phase") == "complete":
                result_lock = _receipt(root, spec["directory"], "result-lock.json") or {}
                result_verified = (result_lock.get("report_sha256") == _file_hash(_path(root, "docs/" + spec["file"]))
                    and result_lock.get("protocol_sha256") == value.get("protocol_sha256")
                    and result_lock.get("producer_sha256") == producers
                    and result_lock.get("training_lock_sha256") == value.get("training_lock_sha256"))
        elif kind == "fx":
            lock = _receipt(root, spec["directory"], "selection.json")
            input_lock = _receipt(root, spec["directory"], "input-lock.json")
            training_verified = (isinstance(lock, dict) and lock == value.get("selection")
                and lock.get("training_sha256") == digest(value.get("training"))
                and input_lock == protocol.get("inputs"))
        else:
            lock = value.get("selection_lock", value.get("training_selection"))
            # Legacy pairs use an underscore; newer native studies declare a
            # hyphenated lock. Both paths are fixed by the campaign allowlist.
            filename = "training_selection.json" if study in ("pairs", "pairs_close", "native_trend") else "training-selection.json"
            stored = _receipt(root, spec["directory"], filename)
            expected = value.get("selection_lock_sha256", value.get("training_selection_sha256"))
            training_verified = (isinstance(lock, dict) and stored == lock and digest(lock) == expected
                and lock.get("protocol_sha256") == value.get("protocol_sha256")
                and lock.get("training_results_sha256", lock.get("training_sha256")) == digest(value.get("training")))
    if not rows_verified or not training_verified or not result_verified:
        reasons.append("Учёт результатов TRAIN или его фиксация не подтверждены")
    protocol_verified = bool(protocol_digest and protocol_lock and objective_verified and human_protocol_verified)
    replay = bool(protocol_verified and producer_verified and inputs_verified and rows_verified and training_verified and result_verified)
    return {"id": study, "title": spec["title"], "phase": str(value.get("phase", "unknown")),
            "expected_configurations": spec["count"], "registered_configurations": len(declared_ids),
            "reported_evaluated_configurations": len(set(ids) & declared_ids), "training_passes_reported": sum(item["passed"] for name, item in evaluated if name in declared_ids),
            "protocol_verified": protocol_verified, "producer_hashes_verified": bool(producer_verified),
            "input_available": bool(available), "input_hashes_verified": bool(inputs_verified),
            "training_results_verified": bool(rows_verified and training_verified and result_verified),
            "replay_artifacts_verified": replay, "verification_reasons": reasons,
            "status": "verified_artifacts" if replay else "unverified_artifacts",
            "report_url": "/api/trader/research-progress?study=" + study,
            "interpretation": "48 повторных оценок исполнения; не 48 новых независимых стратегий" if study == "pairs_close" else "Историческое исследование; будущая прибыль не доказана",
            "eligible_for_paper": False, "live_orders": False, "telegram_enabled": False}


def board(root):
    studies = []
    for study, spec in STUDIES.items():
        try:
            value = read_report(root, study)
            row = inspect(root, study, value) if value is not None else None
        except (OSError, ValueError, TypeError, KeyError, UnicodeError):
            row = {"id": study, "title": spec["title"], "phase": "unverified", "status": "unverified_artifacts",
                   "reported_evaluated_configurations": 0, "replay_artifacts_verified": False,
                   "verification_reasons": ["Артефакт повреждён или содержит недопустимые данные"],
                   "report_url": "/api/trader/research-progress?study=" + study}
        if row is None:
            row = {"id": study, "title": spec["title"], "phase": "pending", "status": "missing_report",
                   "expected_configurations": spec["count"], "registered_configurations": 0,
                   "reported_evaluated_configurations": 0, "replay_artifacts_verified": False,
                   "verification_reasons": [], "report_url": None}
        for name in ("protocol_verified", "producer_hashes_verified", "input_available", "input_hashes_verified", "training_results_verified", "eligible_for_paper", "live_orders", "telegram_enabled"):
            row.setdefault(name, False)
        studies.append(row)
    reported = sum(row["reported_evaluated_configurations"] for row in studies)
    verified = sum(row["reported_evaluated_configurations"] for row in studies if row["replay_artifacts_verified"])
    producer_verified = sum(row["reported_evaluated_configurations"] for row in studies
                            if row["protocol_verified"] and row["producer_hashes_verified"] and row["training_results_verified"])
    pending_crypto = any(row["id"] in ("native_fvg", "native_trend", "native_context", "crypto_flow") and row["phase"] != "unverified"
                         and row["phase"] != "complete" and not row["phase"].startswith("completed") for row in studies)
    return {"target_monthly_return_pct": 8, "previous_evaluated_configurations": PREVIOUS_EVALUATED_CONFIGURATIONS,
            "new_reported_evaluated_configurations": reported,
            "reported_evaluated_configurations": PREVIOUS_EVALUATED_CONFIGURATIONS + reported,
            "new_protocol_producer_verified_configurations": producer_verified,
            "new_replay_artifacts_verified_configurations": verified,
            "previous_input_verification": "292 — прежний учёт выполненных исследований; полный контроль исходных файлов этим API не заявлен",
            "phase": "research_in_progress" if pending_crypto else "reports_available", "crypto_pending_reports": pending_crypto,
            "studies": studies, "primary": None, "eligible_for_paper": False,
            "live_orders": False, "telegram_enabled": False,
            "verification_scope": "SHA256/artifact consistency; API does not rerun simulations or provide external attestation",
            "note": "Результаты исследований. Цель 8% в месяц не означает подтверждённую доходность или допуск к торговле."}


def report(root, study):
    value = read_report(root, study)
    if value is None:
        return None
    return {"study": study, "verification": inspect(root, study, value), "historical_report": value,
            "verification_scope": "SHA256/artifact consistency; API does not rerun simulations or provide external attestation",
            "eligible_for_paper": False, "live_orders": False, "telegram_enabled": False}
