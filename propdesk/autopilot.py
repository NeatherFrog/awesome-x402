"""One bounded, persistent research scheduler. It never places an order.

The host explicitly decides whether first-run automation is enabled. The
controller accepts local scanner adapters rather than importing Application.
It performs at most one automatic attempt per UTC day, survives restarts, and
waits for scanner/maintenance locks. Manual refresh is an explicit user action.
"""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile
import threading
import time
from uuid import UUID

from .feeds import _arguments

DEFAULT_SETTINGS = {
    "source": "yahoo", "symbols": ["EURUSD", "XAUUSD", "NAS100", "BTCUSD", "MES=F", "MNQ=F", "AAPL", "MSFT"],
    "interval": "1h", "range": "2y", "profile_id": None,
    "config": {"risk_pct": .25, "fee_bps": 10, "slippage_bps": 2, "spread_bps": 2, "use_market_costs": True},
}
_ACTIVE = {"queued", "running"}
_TERMINAL = {"completed", "failed", "interrupted"}
_MAX_STATE_BYTES = 64 * 1024
_MAX_RUN_SECONDS = 600
_ID = re.compile(r"(?:[0-9a-f]{32}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\Z", re.I)
_PROFILE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}\Z")


class ResearchDeferred(Exception):
    """The host observed scanner/maintenance contention before starting work."""


class _StateBusy(ValueError):
    pass


def _finite(value, name, lower, upper):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name}: требуется конечное число")
    try:
        value = float(value)
    except (ValueError, OverflowError):
        raise ValueError(f"{name}: недопустимое число") from None
    if not math.isfinite(value) or not lower <= value <= upper:
        raise ValueError(f"{name}: число вне допустимых границ")
    return value


def normalize_settings(payload=None):
    supplied = {} if payload is None else payload
    if not isinstance(supplied, dict) or set(supplied) - set(DEFAULT_SETTINGS):
        raise ValueError("Настройки автопоиска содержат неизвестные поля; секреты здесь не принимаются")
    result = deepcopy(DEFAULT_SETTINGS)
    result.update(deepcopy(supplied))
    if result["source"] != "yahoo":
        raise ValueError("Автоматический источник — Yahoo; демо или архив не подставляются")
    symbols = result["symbols"]
    if not isinstance(symbols, list) or not 1 <= len(symbols) <= 12:
        raise ValueError("symbols: список от 1 до 12 тикеров")
    normalized = []
    for symbol in symbols:
        ticker, _, _ = _arguments(symbol, result["interval"], result["range"])
        if ticker not in normalized:
            normalized.append(ticker)
    result["symbols"] = normalized
    profile = result["profile_id"]
    if profile is not None and (not isinstance(profile, str) or not _PROFILE.fullmatch(profile)):
        raise ValueError("profile_id: корректный локальный идентификатор профиля или null")
    config = result["config"]
    allowed = set(DEFAULT_SETTINGS["config"])
    if not isinstance(config, dict) or set(config) - allowed:
        raise ValueError("config содержит неизвестные поля; токены и произвольные параметры не принимаются")
    result["config"] = {key: _finite(config.get(key, default), key, lower, upper)
                        for key, default, lower, upper in (
                            ("risk_pct", .25, .001, 5), ("fee_bps", 10, 0, 100),
                            ("slippage_bps", 2, 0, 100), ("spread_bps", 2, 0, 200))}
    use_costs = config.get("use_market_costs", True)
    if not isinstance(use_costs, bool):
        raise ValueError("use_market_costs: требуется boolean")
    result["config"]["use_market_costs"] = use_costs
    return result


def _stamp(value):
    if not isinstance(value, str):
        raise ValueError("Состояние автопоиска содержит некорректное UTC-время")
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("Состояние автопоиска содержит некорректное UTC-время") from None
    if stamp.tzinfo is None or stamp.utcoffset() != timedelta(0):
        raise ValueError("Состояние автопоиска требует явно заданного UTC-времени")
    return stamp


def _iso(value):
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _identifier(value):
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ValueError("Сканер вернул некорректный идентификатор задания")
    return str(UUID(value))


def _fingerprint(settings):
    return hashlib.sha256(json.dumps(settings, sort_keys=True, allow_nan=False, separators=(",", ":")).encode()).hexdigest()


class Autopilot:
    def __init__(self, state_path, start_scan, get_scan, *, latest_scan=None, can_start=None,
                 enabled=False, settings=None, clock=None, poll_interval=30):
        if not callable(start_scan) or not callable(get_scan):
            raise ValueError("Для автопоиска требуются локальные start_scan/get_scan адаптеры")
        if latest_scan is not None and not callable(latest_scan) or can_start is not None and not callable(can_start):
            raise ValueError("Адаптеры состояния сканера должны быть callable")
        if not isinstance(enabled, bool) or clock is not None and not callable(clock):
            raise ValueError("enabled должен быть boolean; clock — callable")
        self.poll_interval = _finite(poll_interval, "poll_interval", .01, 3600)
        self.state_path = Path(state_path).absolute()
        current = self.state_path
        while current != current.parent:
            if current.is_symlink():
                raise ValueError("Файл и каталог автопоиска не должны быть символическими ссылками")
            current = current.parent
        self.start_scan, self.get_scan = start_scan, get_scan
        self.latest_scan, self.can_start = latest_scan, can_start
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self._guard = threading.RLock()
        self._stop = threading.Event()
        self._thread = None
        self._transaction_depth = 0
        initial = {"schema": 1, "enabled": enabled, "settings": normalize_settings(settings),
                   "state": "idle" if enabled else "disabled", "running": False,
                   "last_attempt_at": None, "next_attempt_at": None, "job_id": None,
                   "job_started_at": None, "last_completed_at": None, "last_error": None,
                   "last_attempt_day": None, "failure_count": 0, "manual_requested": False,
                   "request_fingerprint": None, "result_ready": False, "qualified_count": 0,
                   "selected_symbol": None}
        self._initial = deepcopy(initial)
        with self._transaction(sync=False):
            if self.state_path.exists():
                self._state = self._load(initial)
            else:
                self._state = initial
                self._save()

    @contextmanager
    def _transaction(self, *, sync=True):
        """Serialize state transitions across threads, instances, and processes.

        The short local start adapter runs inside this transaction. The actual
        network/research worker runs elsewhere. OS locks disappear on a crash,
        unlike a timestamp lease which could authorize a duplicate active job.
        """
        with self._guard:
            if self._transaction_depth:
                yield
                return
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            lock_path = self.state_path.with_name(self.state_path.name + ".lock")
            if lock_path.is_symlink():
                raise ValueError("Файл блокировки автопоиска не должен быть символической ссылкой")
            descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
            acquired = False
            try:
                if os.fstat(descriptor).st_size == 0:
                    os.write(descriptor, b"0")
                deadline = time.monotonic() + 1
                while not acquired:
                    try:
                        if os.name == "nt":
                            import msvcrt
                            os.lseek(descriptor, 0, os.SEEK_SET)
                            msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
                        else:
                            import fcntl
                            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        acquired = True
                    except OSError:
                        if time.monotonic() >= deadline:
                            raise _StateBusy("Состояние автопоиска обновляет другой процесс; повторите позже") from None
                        time.sleep(.01)
                self._transaction_depth = 1
                if sync:
                    self._state = self._load(self._initial)
                yield
            finally:
                self._transaction_depth = 0
                if acquired:
                    if os.name == "nt":
                        import msvcrt
                        os.lseek(descriptor, 0, os.SEEK_SET)
                        msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(descriptor, fcntl.LOCK_UN)
                os.close(descriptor)

    def _now(self):
        stamp = self.clock()
        if not isinstance(stamp, datetime) or stamp.tzinfo is None or stamp.utcoffset() is None:
            raise ValueError("clock должен возвращать timezone-aware datetime")
        return stamp.astimezone(timezone.utc)

    def _load(self, initial):
        if not self.state_path.is_file() or self.state_path.stat().st_size > _MAX_STATE_BYTES:
            raise ValueError("Файл автопоиска отсутствует или превышает 64 KiB")
        try:
            def invalid(_):
                raise ValueError("Неконечное число в состоянии")
            state = json.loads(self.state_path.read_text(encoding="utf-8"), parse_constant=invalid)
        except (OSError, UnicodeError, ValueError, RecursionError):
            raise ValueError("Файл автопоиска повреждён; исходный файл сохранён") from None
        if not isinstance(state, dict) or set(state) != set(initial) or type(state.get("schema")) is not int or state["schema"] != 1:
            raise ValueError("Файл автопоиска имеет неподдерживаемую схему")
        state["settings"] = normalize_settings(state["settings"])
        for field in ("enabled", "running", "manual_requested", "result_ready"):
            if not isinstance(state[field], bool):
                raise ValueError("Файл автопоиска содержит неверный boolean")
        for field in ("last_attempt_at", "next_attempt_at", "job_started_at", "last_completed_at"):
            if state[field] is not None:
                _stamp(state[field])
        if state["job_id"] is not None:
            state["job_id"] = _identifier(state["job_id"])
        if state["running"] and (state["job_id"] is None or state["job_started_at"] is None or state["last_attempt_at"] is None):
            raise ValueError("Активное задание автопоиска требует job_id и время начала")
        if state["state"] not in ("idle", "disabled", "waiting_for_idle", "running", "stalled", "cooldown", "completed", "persistence_error"):
            raise ValueError("Файл автопоиска содержит неизвестное состояние")
        for field in ("failure_count", "qualified_count"):
            value = state[field]
            if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 1000000:
                raise ValueError("Файл автопоиска содержит неверный счётчик")
        if state["last_attempt_day"] is not None:
            try:
                parsed = date.fromisoformat(state["last_attempt_day"])
                if parsed.isoformat() != state["last_attempt_day"]:
                    raise ValueError("Неверный формат даты")
            except (TypeError, ValueError):
                raise ValueError("Файл автопоиска содержит неверную дату попытки") from None
        if state["request_fingerprint"] is not None and (not isinstance(state["request_fingerprint"], str) or
                re.fullmatch(r"[0-9a-f]{64}", state["request_fingerprint"]) is None):
            raise ValueError("Файл автопоиска содержит неверный fingerprint")
        if state["last_error"] is not None and (not isinstance(state["last_error"], str) or len(state["last_error"]) > 500):
            raise ValueError("Файл автопоиска содержит неверное сообщение состояния")
        if state["selected_symbol"] is not None:
            symbol, _, _ = _arguments(state["selected_symbol"], "1h", "2y")
            state["selected_symbol"] = symbol
        return state

    def _save(self):
        encoded = json.dumps(self._state, ensure_ascii=False, allow_nan=False, sort_keys=True).encode("utf-8")
        if len(encoded) > _MAX_STATE_BYTES:
            raise ValueError("Состояние автопоиска превышает 64 KiB")
        if self.state_path.is_symlink():
            raise ValueError("Файл автопоиска не должен быть символической ссылкой")
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, filename = tempfile.mkstemp(prefix=".autopilot-", suffix=".tmp", dir=self.state_path.parent)
        temporary = Path(filename)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temporary, 0o600)
            os.replace(temporary, self.state_path)
        finally:
            temporary.unlink(missing_ok=True)

    def status(self):
        with self._guard:
            return {**deepcopy(self._state), "planning_only": True, "live_orders": False,
                    "automatic_frequency": "once_per_UTC_day", "thread_active": bool(self._thread and self._thread.is_alive())}

    def configure(self, payload):
        if not isinstance(payload, dict) or set(payload) - {"enabled", "settings"}:
            raise ValueError("Изменить можно enabled и settings")
        with self._transaction():
            pending = deepcopy(self._state)
            if "enabled" in payload:
                if not isinstance(payload["enabled"], bool):
                    raise ValueError("enabled: требуется boolean")
                pending["enabled"] = payload["enabled"]
                if not pending["enabled"]:
                    pending["manual_requested"] = False
            if "settings" in payload:
                pending["settings"] = normalize_settings(payload["settings"])
                if pending["settings"] != self._state["settings"]:
                    if self._state["running"]:
                        raise ValueError("Дождитесь завершения текущего исследования перед изменением настроек")
                    pending.update(result_ready=False, qualified_count=0, selected_symbol=None)
            if not pending["running"]:
                pending["state"] = "idle" if pending["enabled"] else "disabled"
            before = self._state
            self._state = pending
            try:
                self._save()
            except (OSError, ValueError):
                self._state = before
                raise
            return self.status()

    def _next_day(self, now):
        return now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)

    def _failure(self, now, message):
        self._state.update(running=False, state="cooldown" if self._state["enabled"] else "disabled",
                           last_completed_at=_iso(now), last_error=message, result_ready=False,
                           qualified_count=0, selected_symbol=None,
                           failure_count=min(1000000, self._state["failure_count"] + 1))
        pause = min(21600, 300 * 2 ** min(self._state["failure_count"] - 1, 7))
        self._state["next_attempt_at"] = _iso(max(self._next_day(now), now + timedelta(seconds=pause)))
        self._save()

    def _complete(self, record, now):
        if record["state"] != "completed":
            self._failure(now, "Автоисследование не завершилось. Проверьте источник и параметры; повтор — после паузы.")
            return
        result = record.get("result")
        if not isinstance(result, dict):
            self._failure(now, "Сканер не вернул проверяемый результат; повтор — после паузы.")
            return
        markets = result.get("markets", [])
        if not isinstance(markets, list) or len(markets) > 12 or any(not isinstance(item, dict) for item in markets):
            self._failure(now, "Сканер вернул некорректный список рынков; повтор — после паузы.")
            return
        if not markets and result.get("fetch_errors"):
            self._failure(now, "Котировки не получены. Проверьте доступ к Yahoo или источник данных; демо не подставляется.")
            return
        selected = result.get("selected_symbol")
        chosen = next((item for item in markets if item.get("symbol") == selected and item.get("selected") is True and item.get("primary") is True and item.get("qualified") is True), None)
        try:
            selected = _arguments(selected, "1h", "2y")[0] if chosen else None
        except ValueError:
            self._failure(now, "Сканер вернул некорректный выбранный рынок; повтор — после паузы.")
            return
        self._state.update(running=False, state="completed" if self._state["enabled"] else "disabled",
                           last_completed_at=_iso(now), last_error=None, failure_count=0,
                           result_ready=bool(markets), qualified_count=sum(item.get("qualified") is True for item in markets),
                           selected_symbol=selected, next_attempt_at=_iso(self._next_day(now)))
        self._save()

    def _refresh(self, now):
        if not self._state["running"]:
            return
        try:
            record = self.get_scan(self._state["job_id"])
            if not isinstance(record, dict) or _identifier(record.get("id")) != self._state["job_id"] or record.get("state") not in _ACTIVE | _TERMINAL:
                raise ValueError("Неверное состояние сканера")
        except Exception:
            # Unknown status cannot justify launching another job. Preserve the
            # job id and stay blocked until this adapter observes a terminal job.
            self._state.update(state="stalled", last_error="Состояние текущего задания неизвестно. Новый поиск не запускается, чтобы не создать дубликат.")
            self._save()
            return
        if record["state"] in _TERMINAL:
            self._complete(record, now)
        else:
            since = _stamp(self._state["job_started_at"] or self._state["last_attempt_at"])
            elapsed = (now - since).total_seconds()
            self._state.update(state="stalled" if elapsed > _MAX_RUN_SECONDS else "running",
                               last_error="Исследование выполняется более 10 минут; новое задание ждёт завершения текущего." if elapsed > _MAX_RUN_SECONDS else None)
            self._save()

    def tick(self):
        try:
            with self._transaction():
                return self._tick_locked()
        except _StateBusy:
            # Another controller is committing this same state. Do not write
            # through its lock or start a second worker from a stale snapshot.
            return {**self.status(), "state": "waiting_for_idle"}

    def _tick_locked(self):
        with self._guard:
            now = self._now()
            self._refresh(now)
            if self._state["running"]:
                return self.status()
            manual = self._state["manual_requested"]
            if not self._state["enabled"] and not manual:
                return self.status()
            if not manual:
                if self._state["last_attempt_day"] == now.date().isoformat():
                    return self.status()
                next_at = self._state["next_attempt_at"]
                if next_at is not None and _stamp(next_at) > now:
                    return self.status()
            try:
                permission = self.can_start() if self.can_start is not None else True
                allowed = permission.get("allowed") is True if isinstance(permission, dict) else permission is True
                latest = self.latest_scan() if self.latest_scan is not None else None
                if isinstance(latest, dict) and latest.get("state") in _ACTIVE:
                    allowed = False
            except Exception:
                allowed = False
            if not allowed:
                self._state.update(state="waiting_for_idle", next_attempt_at=_iso(now + timedelta(seconds=self.poll_interval)))
                self._save()
                return self.status()
            settings = deepcopy(self._state["settings"])
            fingerprint = _fingerprint(settings)
            # A host may explicitly certify that its cached job represents the
            # same freshly checked input fingerprint. Never guess from scores.
            if (not manual and isinstance(latest, dict) and latest.get("state") == "completed"
                    and latest.get("reuse_allowed") is True and latest.get("request_fingerprint") == fingerprint):
                try:
                    identifier = _identifier(latest.get("id"))
                    completed = _stamp(latest.get("updated_at", ""))
                    if completed.date() == now.date():
                        self._state.update(job_id=identifier, job_started_at=latest.get("created_at") or _iso(now),
                                           last_attempt_at=_iso(now), last_attempt_day=now.date().isoformat(),
                                           request_fingerprint=fingerprint, manual_requested=False)
                        self._complete(latest, now)
                        return self.status()
                except (ValueError, TypeError):
                    pass
            # Reserve and persist the attempt before enqueueing a scan. A crash
            # here cannot silently trigger repeated automatic holdout fitting.
            before_attempt = deepcopy(self._state)
            self._state.update(last_attempt_at=_iso(now), last_attempt_day=now.date().isoformat(),
                               next_attempt_at=_iso(self._next_day(now)), request_fingerprint=fingerprint,
                               manual_requested=False, result_ready=False, qualified_count=0, selected_symbol=None,
                               last_error=None, job_id=None, job_started_at=None)
            self._save()
            try:
                record = self.start_scan(settings)
                if not isinstance(record, dict) or record.get("state") not in _ACTIVE | _TERMINAL:
                    raise ValueError("Неверное новое задание")
                identifier = _identifier(record.get("id"))
            except ResearchDeferred:
                self._state = before_attempt
                self._state.update(state="waiting_for_idle", next_attempt_at=_iso(now + timedelta(seconds=self.poll_interval)))
                self._save()
                return self.status()
            except Exception:
                self._failure(now, "Не удалось запустить автопоиск. Проверьте источник и настройки; повтор — после паузы.")
                return self.status()
            self._state.update(job_id=identifier, job_started_at=_iso(now), running=True, state="running")
            self._save()
            if record["state"] in _TERMINAL:
                self._complete(record, now)
            return self.status()

    def run_now(self):
        with self._transaction():
            self._refresh(self._now())
            if self._state["running"]:
                return self.status()
            self._state["manual_requested"] = True
            self._save()
            return self.tick()

    def _loop(self):
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception:
                with self._guard:
                    self._state.update(enabled=False, state="persistence_error",
                                       last_error="Автопоиск приостановлен: не удалось безопасно сохранить локальное состояние.")
            self._stop.wait(self.poll_interval)

    def start(self):
        with self._guard:
            if self._thread is None or not self._thread.is_alive():
                self._stop.clear()
                self._thread = threading.Thread(target=self._loop, name="research-autopilot", daemon=False)
                self._thread.start()
            return self.status()

    def stop(self, timeout=5):
        timeout = _finite(timeout, "timeout", 0, 60)
        self._stop.set()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout)
            if thread.is_alive():
                raise RuntimeError("Автопоиск не остановился: локальный адаптер сканера не завершил вызов")
        return self.status()
