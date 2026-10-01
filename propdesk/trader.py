"""Cached setup board and a bounded record of every background search.

The board never fetches a price, chooses a holdout winner, or submits an order.
Each search keeps its own compact audit file; older attempts are never pruned.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import heapq
import json
import math
import os
from pathlib import Path
import re
import tempfile
import threading
from uuid import UUID

from .setups import build_setup

_MAX_RECORD = 512 * 1024
_MAX_REPORT = 32 * 1024 * 1024
_ID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\Z", re.I)
_PARAM = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,63}\Z")
_ACTIVE = {"queued", "running"}
_COSTS = {"risk_pct", "fee_bps", "fee_per_unit", "slippage_bps", "spread_bps",
          "contract_multiplier", "quantity_step", "max_leverage", "use_market_costs"}


def _iso(now):
    return now.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _identifier(value):
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ValueError("Некорректный идентификатор попытки поиска")
    return str(UUID(value))


def _text(value, limit=500):
    return value[:limit] if isinstance(value, str) else None


def _numbers(value):
    """Only named finite metrics; never persist arbitrary worker payloads."""
    if not isinstance(value, dict):
        return {}
    return {key: item for key, item in value.items()
            if isinstance(key, str) and _PARAM.fullmatch(key)
            and not any(word in key.lower() for word in ("token", "secret", "password", "apikey"))
            and isinstance(item, (int, float)) and not isinstance(item, bool)
            and math.isfinite(item)}


def _validation(value):
    if not isinstance(value, dict):
        return {}
    summary = _numbers(value)
    summary["folds"] = [{**{key: _text(fold.get(key), 64) for key in
                           ("train_start", "train_end", "validation_start", "validation_end")},
                         "params": _numbers(fold.get("params")), "metrics": _numbers(fold.get("metrics"))}
                        for fold in value.get("folds", [])[:12] if isinstance(fold, dict)]
    return summary


def _parameters(value):
    result = _numbers(value)
    if isinstance(value, dict):
        result.update({key: item for key, item in value.items() if isinstance(item, bool)
                       and isinstance(key, str) and _PARAM.fullmatch(key)
                       and not any(word in key.lower() for word in ("token", "secret", "password", "apikey"))})
    return result


def _read_json(path, maximum):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > maximum:
        raise ValueError("Локальные данные отсутствуют или имеют недопустимый размер")
    def invalid(_):
        raise ValueError("Неконечное число в локальных данных")
    result = json.loads(path.read_text(encoding="utf-8"), parse_constant=invalid)
    if not isinstance(result, dict):
        raise ValueError("Локальные данные должны быть объектом")
    return result


def _verify_hash(report, name):
    expected = report.get(name + "_sha256")
    if expected is None:
        return
    value = report.get(name)
    if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected) or not isinstance(value, dict):
        raise ValueError("Отчёт содержит некорректный отпечаток протокола")
    actual = hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                                     separators=(",", ":")).encode()).hexdigest()
    if actual != expected:
        raise ValueError("Замороженный протокол или выбор стратегии изменился")


def compact_job(job):
    if not isinstance(job, dict):
        return None
    return {key: deepcopy(job.get(key)) for key in
            ("id", "state", "created_at", "updated_at", "progress", "error")}


class Trader:
    def __init__(self, directory, root):
        self.directory = Path(directory).absolute() / "trader"
        current = self.directory
        while current != current.parent:
            if current.is_symlink():
                raise ValueError("Каталог журнала поиска не должен быть символической ссылкой")
            current = current.parent
        self.root = Path(root)
        self.attempts = self.directory / "attempts"
        if self.attempts.is_symlink():
            raise ValueError("Каталог попыток поиска не должен быть символической ссылкой")
        self.attempts.mkdir(parents=True, exist_ok=True)
        self._guard = threading.RLock()
        self._evidence_cache = None
        self._evidence_stamp = None

    def _path(self, identifier):
        if self.directory.is_symlink() or self.attempts.is_symlink():
            raise ValueError("Каталог журнала поиска не должен быть символической ссылкой")
        result = self.attempts / (_identifier(identifier) + ".json")
        if result.is_symlink():
            raise ValueError("Файл попытки поиска не должен быть символической ссылкой")
        return result

    def _save(self, record):
        destination = self._path(record["id"])
        encoded = json.dumps(record, ensure_ascii=False, allow_nan=False, sort_keys=True,
                             separators=(",", ":")).encode("utf-8")
        if len(encoded) > _MAX_RECORD:
            raise ValueError("Метаданные попытки поиска превышают 512 KiB")
        descriptor, filename = tempfile.mkstemp(prefix=".attempt-", dir=self.attempts)
        temporary = Path(filename)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temporary, 0o600)
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)

    def _event(self, record):
        # Append-only metadata index. The per-attempt files remain authoritative
        # if a process stops between saving a record and appending this event.
        path = self.directory / "attempts.jsonl"
        if self.directory.is_symlink() or path.is_symlink():
            raise ValueError("Индекс попыток поиска не должен быть символической ссылкой")
        event = {key: record.get(key) for key in ("id", "state", "started_at", "updated_at")}
        event["training_lock_sha256"] = record.get("training_lock_sha256")
        encoded = (json.dumps(event, sort_keys=True, allow_nan=False) + "\n").encode()
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(descriptor, "ab") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())

    def begin(self, identifier, payload):
        with self._guard:
            path = self._path(identifier)
            if path.exists():
                raise ValueError("Попытка поиска уже записана; существующий журнал сохранён")
            now = _iso(datetime.now(timezone.utc))
            config = payload.get("config", {})
            request = {key: deepcopy(payload.get(key)) for key in
                       ("source", "symbols", "interval", "range", "profile_id")}
            request["config"] = {key: value for key, value in config.items() if key in _COSTS
                                 and isinstance(value, (int, float, bool)) and math.isfinite(value)}
            record = {"schema": 1, "id": _identifier(identifier), "state": "running",
                      "started_at": now, "updated_at": now, "request": request,
                      "training": [], "outcomes": [], "live_orders": False,
                      "selection_policy": "Training locks the primary; no diagnostic replaces a failed primary"}
            self._save(record)
            self._event(record)

    def training_locked(self, identifier, details):
        wrapper = details.get("training_lock") if isinstance(details, dict) else None
        if not isinstance(wrapper, dict):
            return
        # Progress wraps the original scanner lock in its publication envelope.
        lock = wrapper.get("training_lock", wrapper)
        if not isinstance(lock, dict):
            return
        with self._guard:
            record = _read_json(self._path(identifier), _MAX_RECORD)
            fingerprint = wrapper.get("training_lock_sha256") or details.get("training_lock_sha256")
            if not isinstance(fingerprint, str):
                fingerprint = hashlib.sha256(json.dumps(lock, sort_keys=True, allow_nan=False,
                    separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
            if record.get("training_lock_sha256"):
                if record["training_lock_sha256"] != fingerprint:
                    raise ValueError("Замороженный выбор стратегии изменился; поиск остановлен")
                return
            training = []
            for asset in lock.get("training_results", [])[:12]:
                families = []
                for family in asset.get("family_results", [])[:12]:
                    families.append({"id": _text(family.get("id"), 80),
                                     "params": _parameters(family.get("params")),
                                     "metrics": _numbers(family.get("train_metrics")),
                                     "validation": _validation(family.get("walk_forward"))})
                training.append({"symbol": _text(asset.get("symbol"), 32),
                                 "start": _text(asset.get("training_start"), 64),
                                 "end": _text(asset.get("training_end"), 64),
                                 "bars": asset.get("training_bars"),
                                 "data_sha256": _text(asset.get("training_hash"), 64),
                                 "execution_model": _numbers(lock.get("execution_models", {}).get(asset.get("symbol"))),
                                 "families": families})
            record.update(training=training, primary_symbol=lock.get("primary_symbol"),
                          training_lock_sha256=fingerprint, updated_at=_iso(datetime.now(timezone.utc)))
            self._save(record)
            self._event(record)

    def finish(self, identifier, result=None, *, error_type=None):
        with self._guard:
            record = _read_json(self._path(identifier), _MAX_RECORD)
            if record["state"] != "running":
                raise ValueError("Завершённая попытка поиска не перезаписывается")
            result = result if isinstance(result, dict) else {}
            outcomes = []
            for market in result.get("markets", [])[:12]:
                report = market.get("report", {})
                chosen = next((strategy for strategy in report.get("strategies", [])
                               if strategy.get("id") == market.get("strategy_id")), {})
                families = [{"id": _text(strategy.get("id"), 80),
                             "params": _parameters(strategy.get("params")),
                             "metrics": _numbers(strategy.get("test_metrics")),
                             "eligible": strategy.get("eligible") is True,
                             "training_winner": strategy.get("training_winner") is True,
                             "baseline": strategy.get("baseline") is True,
                             "reasons": [_text(reason) for reason in strategy.get("reasons", [])[:20]
                                         if isinstance(reason, str)],
                             "validation": _validation(strategy.get("walk_forward"))}
                            for strategy in report.get("strategies", [])[:12] if isinstance(strategy, dict)]
                outcomes.append({"symbol": _text(market.get("symbol"), 32),
                                 "strategy_id": _text(market.get("strategy_id"), 80),
                                 "primary": market.get("primary") is True,
                                 "qualified": market.get("qualified") is True,
                                 "selected": market.get("selected") is True,
                                 "metrics": _numbers(chosen.get("test_metrics")), "families": families,
                                 "execution_model": {key: value for key, value in _numbers(report.get("config")).items() if key in _COSTS},
                                 "execution_assumptions": True,
                                 "provenance": {key: _text(report.get("data", {}).get("provenance", {}).get(key), 256)
                                                for key in ("provider", "provider_symbol", "requested_symbol", "quote_currency", "interval", "retrieved_at", "body_sha256")}})
            record.update(state="interrupted" if error_type == "Interrupted" else "failed" if error_type else "completed", outcomes=outcomes,
                          selected_symbol=result.get("selected_symbol"),
                          failed_symbols=[item.get("symbol") for item in result.get("fetch_errors", [])[:12]],
                          error_type=_text(error_type, 80), updated_at=_iso(datetime.now(timezone.utc)))
            self._save(record)
            self._event(record)

    def recover(self, scanner):
        """Reconcile interrupted startup jobs without rewriting terminal audits."""
        with self._guard:
            for path in self.attempts.glob("*.json"):
                if not _ID.fullmatch(path.stem):
                    continue
                record = self.attempt(path.stem)
                if not record or record.get("state") != "running":
                    continue
                try:
                    job = scanner.get(path.stem)
                except (OSError, ValueError):
                    continue
                if job.get("state") == "interrupted":
                    self.finish(path.stem, error_type="Interrupted")

    def attempt(self, identifier):
        with self._guard:
            try:
                record = _read_json(self._path(identifier), _MAX_RECORD)
                if (record.get("schema") != 1 or record.get("id") != _identifier(identifier)
                        or record.get("state") not in {"running", "completed", "failed", "interrupted"}):
                    return None
                return record
            except FileNotFoundError:
                return None
            except ValueError:
                return None

    def summary(self):
        with self._guard:
            latest, latest_time, count = None, -1, 0
            for path in self.attempts.glob("*.json"):
                if not _ID.fullmatch(path.stem) or path.is_symlink() or not path.is_file():
                    continue
                count += 1
                stamp = path.stat().st_mtime_ns
                if stamp > latest_time:
                    latest, latest_time = path, stamp
            record = self.attempt(latest.stem) if latest else None
            return {"count": count, "retention": "All compact attempt records retained; no automatic pruning",
                    "latest": {key: record.get(key) for key in
                               ("id", "state", "started_at", "updated_at", "primary_symbol", "selected_symbol")}
                              if record else None}

    def listing(self, limit=20):
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError("limit: целое число от 1 до 100")
        with self._guard:
            paths = (path for path in self.attempts.glob("*.json")
                     if _ID.fullmatch(path.stem) and not path.is_symlink() and path.is_file())
            latest = heapq.nlargest(limit, paths, key=lambda path: path.stat().st_mtime_ns)
            records = []
            for path in latest:
                record = self.attempt(path.stem)
                if record is None:
                    records.append({"id": path.stem, "state": "unavailable"})
                    continue
                row = {key: deepcopy(record.get(key)) for key in
                       ("id", "state", "started_at", "updated_at", "request", "primary_symbol", "selected_symbol", "training_lock_sha256")}
                row["strategy_count"] = sum(len(asset.get("families", [])) for asset in record.get("training", []))
                row["holdout_market_count"] = len(record.get("outcomes", []))
                row["detail_url"] = "/api/trader/attempts/" + path.stem
                records.append(row)
            return {"schema": 1, "records": records, "limit": limit, "total_count": self.summary()["count"],
                    "live_orders": False, "notice": "Автоматический журнал исследований; записи не являются исполненными сделками."}

    def export_attempt(self, identifier):
        identifier = _identifier(identifier)
        record = self.attempt(identifier)
        if record is None:
            raise ValueError("Попытка поиска не найдена или её метаданные повреждены")
        result = {key: deepcopy(record.get(key)) for key in
                  ("schema", "id", "state", "started_at", "updated_at", "request", "training", "outcomes",
                   "primary_symbol", "selected_symbol", "training_lock_sha256", "selection_policy",
                   "failed_symbols", "error_type", "live_orders")}
        if len(json.dumps(result, ensure_ascii=False, allow_nan=False).encode()) > _MAX_RECORD:
            raise ValueError("Экспорт метаданных попытки превышает 512 KiB")
        return result

    def _study_evidence(self, path, study_id, title):
        empty = {"id": study_id, "title": title, "state": "unavailable", "primary": None, "live_candidate": False}
        if not path.exists():
            return empty
        try:
            report = _read_json(path, _MAX_REPORT)
            _verify_hash(report, "protocol")
            _verify_hash(report, "training_lock")
            primary_id = report.get("training_lock", {}).get("primary_strategy_id")
            if report.get("primary_strategy_id") not in (None, primary_id) or report.get("selected_strategy_id") not in (None, primary_id):
                raise ValueError("Основной кандидат не соответствует замороженному выбору")
            # An unlocked declared family cannot become the selected primary.
            primary = next((strategy for strategy in report.get("strategies", [])
                            if strategy.get("id") == primary_id and strategy.get("primary") is True), None)
            window_results = {}
            if primary:
                names = ("holdout",) if study_id == "intraday" else ("historical_holdout", "confirmation")
                for name in names:
                    window = primary.get("windows", {}).get(name, {})
                    window_results[name] = {"data": {key: window.get("data", {}).get(key) for key in ("start", "end", "bars")},
                                            "metrics": _numbers(window.get("metrics")),
                                            "confidence": deepcopy(window.get("confidence", {})),
                                            "passes_window": window.get("passes_window") is True,
                                            "reasons": deepcopy(window.get("evidence_reasons", []))[:20],
                                            "financing_4pct": _numbers(window.get("stress4pct", {}).get("metrics")),
                                            "financing_8pct": _numbers(window.get("stress8pct", {}).get("metrics")),
                                            "friction_stress": _numbers(window.get("friction_stress", {}).get("metrics"))}
            positive = bool(primary) and bool(window_results) and all(
                item["metrics"].get("net_return_pct", 0) > 0 for item in window_results.values())
            protocol = report.get("protocol", {})
            availability_errors = []
            for field in ("source_errors", "coverage_errors"):
                errors = report.get(field, {})
                if isinstance(errors, dict):
                    availability_errors.extend({"symbol": _text(symbol, 32), "reason": _text(reason, 500)}
                                               for symbol, reason in list(errors.items())[:12])
                elif isinstance(errors, list):
                    availability_errors.extend({"symbol": _text(error.get("symbol"), 32),
                                                "reason": _text(error.get("error", error.get("reason")), 500)}
                                               for error in errors[:12] if isinstance(error, dict))
            result = {"id": study_id, "title": title, "state": report.get("phase", "unavailable"), "finished_at": report.get("finished_at"),
                      "primary": {"id": primary_id, "name": primary.get("name"),
                                  "status": "historically_positive_watch" if positive else "unqualified",
                                  "eligible_historical_price_model": primary.get("eligible_historical_price_model") is True,
                                  "real_prop_qualified": False, "windows": window_results,
                                  "rules": protocol.get("rules", {}).get(primary_id),
                                  "sources": [source for source in protocol.get("sources", []) if source.get("strategy_id") == primary_id],
                                  "reasons": deepcopy(primary.get("reasons", []))[:20]} if primary else None,
                      "protocol_sha256": report.get("protocol_sha256"),
                      "training_lock_sha256": report.get("training_lock_sha256"),
                      "live_candidate": False, "live_orders": False,
                      "scope": protocol.get("scope"), "symbols": protocol.get("symbols", []), "interval": protocol.get("interval"),
                      "decision": _text(report.get("decision"), 1000) or "Исторические тесты не разрешают вход на контракте проп-фирмы без проверки правил и реальных исполнений.",
                      "availability_errors": availability_errors,
                      "limitations": deepcopy(report.get("limitations", []))[:20]}
        except (OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError):
            result = {**empty, "decision": "Отчёт проверки не читается; вход по нему запрещён."}
        return result

    def evidence(self):
        files = (("sourced_daily", "Дневные стратегии из опубликованных источников", "sourced-strategy-research.json"),
                 ("intraday", "Внутридневные стратегии с закрытием до конца сессии", "intraday-research.json"),
                 ("mean_reversion", "Возврат к среднему: фиксированная дневная проверка", "mean-reversion-research.json"))
        with self._guard:
            stamp = tuple((path.stat().st_mtime_ns, path.stat().st_size) if path.exists() else None
                          for _, _, name in files for path in (self.root / "docs" / name,))
            if stamp == self._evidence_stamp:
                return deepcopy(self._evidence_cache)
            studies = [self._study_evidence(self.root / "docs" / name, study_id, title)
                       for study_id, title, name in files]
            # The legacy convenience primary remains the daily study's locked
            # primary. No later study or diagnostic can replace it by returns.
            result = {**deepcopy(studies[0]), "studies": studies,
                      "selection_policy": "Each preregistered study retains its own training-selected primary; no global holdout repick",
                      "sequential_search_notice": "Исследования идут последовательно. Повторный поиск на истории увеличивает риск подгонки; новый тест не стирает результат прежнего."}
            self._evidence_stamp, self._evidence_cache = stamp, result
            return deepcopy(result)

    def board(self, job, automation, news, *, context=None, now=None):
        now = now or datetime.now(timezone.utc)
        if not isinstance(now, datetime) or now.tzinfo is None:
            raise ValueError("Время доски требует timezone-aware datetime")
        result = job.get("result", {}) if isinstance(job, dict) else {}
        result = result if isinstance(result, dict) else {}
        attempt = self.attempt(job["id"]) if isinstance(job, dict) else None
        requested = (attempt or {}).get("request", {}).get("symbols") or automation.get("settings", {}).get("symbols", [])
        requested = list(dict.fromkeys(requested))[:12]
        lock = result.get("training_lock", {})
        trained = {asset.get("symbol"): asset for asset in lock.get("training_results", []) if isinstance(asset, dict)}
        outcomes = {market.get("symbol"): market for market in result.get("markets", []) if isinstance(market, dict)}
        failed = {item.get("symbol"): item for item in result.get("fetch_errors", []) if isinstance(item, dict)}
        exclusions = {item.get("symbol"): item for item in result.get("exclusions", []) if isinstance(item, dict)}
        symbols = list(dict.fromkeys(requested + list(trained) + list(outcomes) + list(failed) + list(exclusions)))[:12]
        effective = deepcopy(context) if isinstance(context, dict) else {}
        supplied_news = effective.get("news")
        empty_manual = (isinstance(supplied_news, dict) and supplied_news.get("confirmed", False) is False
                        and supplied_news.get("source", "") == "" and supplied_news.get("events", []) == []
                        and supplied_news.get("observed_at") is None)
        if not isinstance(supplied_news, dict) or supplied_news.get("generation") == "provider" or empty_manual:
            effective["news"] = news
        markets, admitted = [], []
        for symbol in symbols:
            market = outcomes.get(symbol, {})
            report = market.get("report")
            primary = market.get("primary") is True and result.get("primary_symbol") == symbol
            historically_qualified = market.get("qualified") is True
            selected = primary and historically_qualified and market.get("selected") is True and result.get("selected_symbol") == symbol
            blockers = []
            setup = None
            if isinstance(report, dict):
                try:
                    setup = build_setup(report, effective, now=now)
                except (ValueError, TypeError, KeyError, OverflowError):
                    blockers.append("Снимок цены или контекста некорректен; вход не строится.")
                if not selected:
                    blockers.append("Рынок не допущен замороженным выбором обучения; диагностический результат не заменяет основного кандидата.")
                if report.get("archived") is True or report.get("data", {}).get("input_source") == "reference":
                    blockers.append("Архивные котировки: вход сейчас не разрешён.")
                rules = report.get("profile_rules", {})
                if rules.get("status") != "user_verified":
                    blockers.append("Действующие правила выбранной проп-фирмы и счета не подтверждены.")
                contract = report.get("market_context", {})
                if contract.get("execution_assumptions") is not False:
                    blockers.append("Спецификация контракта, комиссии и исполнимая котировка брокера не подтверждены.")
                if not result.get("selected_profile_id"):
                    blockers.append("Подходящая подтверждённая проп-программа не выбрана.")
                elif report.get("profile_id") != result.get("selected_profile_id"):
                    blockers.append("План не проверен на правилах выбранной проп-программы.")
                if setup and setup["status"] == "blocked":
                    blockers.extend(setup["reasons"])
            elif symbol in failed:
                blockers.append("Котировки этого рынка не получены; синтетические цены не подставляются.")
            elif symbol in exclusions:
                blockers.append("Рынок исключён из сопоставимого теста; проверьте валюту и спецификацию.")
            elif symbol in trained:
                blockers.append("Проверено только обучение; рынок не попал в замороженную проверку на отложенной истории.")
            else:
                blockers.append("Для рынка ещё нет завершённой проверки и свежего снимка.")
            if setup and setup["status"] != "paper_review" and not blockers:
                blockers.append("На последнем закрытом баре нет нового подтверждённого сигнала.")
            card = {"symbol": symbol, "status": "unavailable" if symbol in failed or symbol in exclusions else
                    "qualified" if selected else "unqualified", "primary": primary,
                    "historical_qualified": historically_qualified, "selected": selected,
                    "strategy_id": market.get("strategy_id") or trained.get(symbol, {}).get("winner", {}).get("id"),
                    "price_state": setup.get("context", {}).get("price_state", "unknown") if setup else "unknown",
                    "setup": setup, "blockers": list(dict.fromkeys(blockers)),
                    "live_orders": False, "planning_only": True}
            markets.append(card)
            if selected and setup and setup["status"] == "paper_review" and card["price_state"] == "fresh" and not blockers:
                admitted.append(deepcopy(card))
        searching = isinstance(job, dict) and job.get("state") in _ACTIVE or automation.get("running") is True or automation.get("manual_requested") is True
        status = "searching" if searching else "paper_review" if admitted else "no_trade" if result or markets else "idle"
        decision = ("Поиск выполняется: новые входы ожидают завершения проверки." if searching else
                    "Есть план для бумажной проверки: проверьте счёт и фактический вход перед исполнением." if admitted else
                    "Сейчас допущенных входов нет. Причины по каждому рынку показаны ниже.")
        return {"schema": 1, "mode": "paper", "live_orders": False, "status": status,
                "generated_at": _iso(now), "decision": decision, "next_check_at": automation.get("next_attempt_at"),
                "automation": deepcopy(automation), "job": compact_job(job),
                "coverage": {"requested": symbols, "scanned_count": len(trained) or result.get("market_count", 0),
                             "holdout_count": len(outcomes), "failed_count": len(failed),
                             "scope": "configured_markets", "universal": False},
                "markets": markets, "setups": [] if searching else admitted,
                "evidence": self.evidence(), "attempts": self.summary(),
                "warnings": ["Публичный источник не охватывает все рынки и не заменяет котировки брокера.",
                             "Положительная история не гарантирует будущую прибыль; здесь нет исполнения реальных ордеров."]}
