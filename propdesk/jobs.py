"""One background scanner with atomic, restart-aware local job snapshots.

The caller owns market access and research locking. Inputs exist only in memory;
credentials are never part of saved job configuration. One manager should own a
state directory in a running application.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import tempfile
import threading
from uuid import UUID, uuid4

_INPUT_KEYS = {"source", "symbols", "interval", "range", "profile_id", "config"}
_STATES = {"queued", "running", "completed", "failed", "interrupted"}
_ID = re.compile(r"(?:[0-9a-f]{32}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\Z", re.IGNORECASE)
_MAX_INPUT_BYTES = 5 * 1024 * 1024
_MAX_RECORD_BYTES = 50 * 1024 * 1024
_MAX_PROGRESS_BYTES = 512 * 1024
_SECRET_KEYS = {"token", "apikey", "secret", "password", "authorization", "credential",
                "credentials", "accesstoken", "refreshtoken", "ghtoken", "githubtoken",
                "tradinggithubtoken", "tradingwebhooktoken"}
_ENV_SECRETS = ("TRADING_GITHUB_TOKEN", "GH_TOKEN", "GITHUB_TOKEN", "TRADING_WEBHOOK_TOKEN")


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _job_id(value):
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ValueError("Некорректный идентификатор сканирования")
    return str(UUID(value))


def _bytes(value, maximum):
    pending = [(value, 0)]
    while pending:
        item, depth = pending.pop()
        if depth > 64:
            raise ValueError("Слишком глубокая структура задания")
        if isinstance(item, dict):
            pending.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, (list, tuple)):
            pending.extend((child, depth + 1) for child in item)
    try:
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                             separators=(",", ":")).encode("utf-8")
    except (ValueError, TypeError, OverflowError, RecursionError):
        raise ValueError("Данные задания должны быть конечным JSON без секретов и нестандартных объектов") from None
    if len(encoded) > maximum:
        raise ValueError("Результат или параметры задания превышают допустимый размер")
    return encoded


def _sensitive(key):
    normalized = re.sub(r"[^a-z0-9]", "", key.casefold())
    return normalized in _SECRET_KEYS or normalized.endswith("password") or normalized.endswith("secret") or normalized.endswith("token") or normalized.endswith("apikey")


def _redact(text, secrets, *, redact_urls=True):
    for secret in secrets:
        if secret and (len(secret) >= 4 or text == secret):
            text = text.replace(secret, "[redacted]")
    if redact_urls:
        text = re.sub(r"https?://[^\s<>\"']+", "[URL]", text, flags=re.IGNORECASE)
    text = re.sub(r"\bBearer\s+\S+", "Bearer [redacted]", text, flags=re.IGNORECASE)
    text = re.sub(r"(?i)\b(token|api[_-]?key|secret|password|authorization|signature|sig)\s*[:=]\s*[^\s,;]+",
                  r"\1=[redacted]", text)
    return text


def _find_secrets(value, found):
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(key, str) and _sensitive(key) and isinstance(item, str):
                found.add(item)
            _find_secrets(item, found)
    elif isinstance(value, list):
        for item in value:
            _find_secrets(item, found)


def _public(value, secrets):
    if isinstance(value, dict):
        return {key: _public(item, secrets) for key, item in value.items()
                if isinstance(key, str) and not _sensitive(key)}
    if isinstance(value, list):
        return [_public(item, secrets) for item in value]
    if isinstance(value, str):
        return _redact(value, secrets, redact_urls=False)
    return value


class ScannerJobs:
    def __init__(self, directory: Path, worker):
        if not callable(worker):
            raise ValueError("Для сканера требуется функция worker")
        self.directory = Path(directory).absolute()
        current = self.directory
        while current != current.parent:
            if current.is_symlink():
                raise ValueError("Каталог сканера не должен быть символической ссылкой")
            current = current.parent
        self.directory.mkdir(parents=True, exist_ok=True)
        self.worker = worker
        self._guard = threading.Lock()
        self._active_id = None
        self._latest_id = None
        self._records = {}
        self._threads = {}
        self._secrets = {os.environ[name] for name in _ENV_SECRETS if os.environ.get(name)}
        existing = []
        for path in self.directory.glob("*.json"):
            if not _ID.fullmatch(path.stem):
                continue
            try:
                record = self._load(_job_id(path.stem))
            except (ValueError, OSError):
                continue
            if record["state"] in ("queued", "running"):
                record["last_progress"] = deepcopy(record["progress"])
                record.update(state="interrupted", updated_at=_now(), result=None,
                              error="Предыдущий процесс остановился. Запустите сканирование заново.")
                record["progress"] = {"stage": "interrupted", "details": {}}
                self._save(record)
            existing.append((datetime.fromisoformat(record["created_at"].replace("Z", "+00:00")).astimezone(timezone.utc), record["id"]))
        if existing:
            self._latest_id = max(existing)[1]

    @property
    def busy(self):
        with self._guard:
            return self._active_id is not None

    def _path(self, job_id):
        path = self.directory / (_job_id(job_id) + ".json")
        if path.is_symlink():
            raise ValueError("Файл сканирования не должен быть символической ссылкой")
        return path

    def _save(self, record):
        encoded = _bytes(record, _MAX_RECORD_BYTES)
        destination = self._path(record["id"])
        handle, name = tempfile.mkstemp(prefix=".job-", suffix=".tmp", dir=self.directory)
        temporary = Path(name)
        try:
            with os.fdopen(handle, "wb") as file:
                file.write(encoded)
                file.flush()
                os.fsync(file.fileno())
            os.chmod(temporary, 0o600)
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)

    def _load(self, job_id):
        path = self._path(job_id)
        if not path.is_file():
            raise ValueError("Сканирование не найдено")
        if path.stat().st_size > _MAX_RECORD_BYTES:
            raise ValueError("Слишком большой файл задания")
        try:
            def invalid_constant(_value):
                raise ValueError("Неконечное число в файле задания")
            record = json.loads(path.read_text(encoding="utf-8"), parse_constant=invalid_constant)
            if not isinstance(record, dict) or _job_id(record.get("id")) != _job_id(job_id):
                raise ValueError("Некорректный файл задания")
            if record.get("state") not in _STATES or not isinstance(record.get("created_at"), str):
                raise ValueError("Некорректное состояние задания")
            created = datetime.fromisoformat(record["created_at"].replace("Z", "+00:00"))
            if created.tzinfo is None or not isinstance(record.get("progress"), dict):
                raise ValueError("Некорректное время или прогресс задания")
            _bytes(record, _MAX_RECORD_BYTES)
        except (UnicodeError, TypeError, json.JSONDecodeError, OverflowError, RecursionError):
            raise ValueError("Файл задания повреждён") from None
        record = {key: value for key, value in record.items() if key in (
            "schema", "id", "state", "created_at", "updated_at", "progress", "last_progress", "result", "error", "error_type")}
        return _public(record, self._secrets)

    def get(self, job_id):
        identifier = _job_id(job_id)
        with self._guard:
            if identifier in self._records:
                return deepcopy(self._records[identifier])
            return self._load(identifier)

    def status(self, job_id):
        return self.get(job_id)

    def latest(self):
        with self._guard:
            if self._latest_id is None:
                return None
            record = self._records.get(self._latest_id)
            return deepcopy(record) if record is not None else self._load(self._latest_id)

    def start(self, payload):
        if not isinstance(payload, dict):
            raise ValueError("Параметры сканера должны быть объектом")
        # Canonicalization copies all worker inputs before starting the thread.
        inputs = {key: value for key, value in payload.items() if key in _INPUT_KEYS}
        inputs = json.loads(_bytes(inputs, _MAX_INPUT_BYTES))
        secrets = set(self._secrets)
        _find_secrets(inputs, secrets)
        created = _now()
        identifier = str(uuid4())
        record = {"schema": 1, "id": identifier, "state": "running", "created_at": created,
                  "updated_at": created, "progress": {"stage": "starting", "details": {}},
                  "result": None, "error": None}
        with self._guard:
            if self._active_id is not None:
                raise ValueError("Сканирование уже выполняется. Дождитесь результата.")
            self._save(record)
            self._records[identifier] = record
            self._latest_id = identifier
            self._active_id = identifier
            initial = deepcopy(record)
            thread = threading.Thread(target=self._run, args=(identifier, inputs, secrets),
                                      name="scanner-" + identifier[:8], daemon=True)
            self._threads[identifier] = thread
        try:
            thread.start()
        except BaseException:
            with self._guard:
                record["last_progress"] = deepcopy(record["progress"])
                record.update(state="failed", updated_at=_now(), error="Не удалось запустить поток сканера")
                record["progress"] = {"stage": "failed", "details": {}}
                self._active_id = None
                self._save(record)
            raise ValueError("Не удалось запустить сканер") from None
        return initial

    def _progress(self, identifier, secrets, stage, details=None):
        if not isinstance(stage, str) or not stage.strip() or len(stage) > 120:
            raise ValueError("progress.stage: строка длиной от 1 до 120 символов")
        if details is not None and not isinstance(details, dict):
            raise ValueError("progress.details должен быть объектом")
        data = {"stage": _redact(stage.strip(), secrets), "details": _public(details or {}, secrets)}
        data = json.loads(_bytes(data, _MAX_PROGRESS_BYTES))
        with self._guard:
            record = self._records.get(identifier)
            if identifier != self._active_id or record is None or record["state"] != "running":
                return
            record.update(progress=data, updated_at=_now())
            self._save(record)

    def _run(self, identifier, inputs, secrets):
        result = None
        error = None
        error_type = None
        try:
            report = self.worker(inputs, lambda stage, details=None: self._progress(identifier, secrets, stage, details))
            if not isinstance(report, dict):
                raise ValueError("Сканер должен вернуть объект результата")
            result = json.loads(_bytes(_public(report, secrets), _MAX_RECORD_BYTES))
        except BaseException as exc:
            error_type = type(exc).__name__
            error = (_redact(str(exc), secrets).replace("\x00", "")[:500] if isinstance(exc, ValueError)
                     else f"Сканирование прервано: {error_type}")
        with self._guard:
            record = self._records[identifier]
            record["last_progress"] = deepcopy(record["progress"])
            record.update(state="failed" if error is not None else "completed", updated_at=_now(),
                          result=result if error is None else None, error=error)
            record["progress"] = {"stage": record["state"], "details": {}}
            if error_type:
                record["error_type"] = error_type
            try:
                self._save(record)
            except (OSError, ValueError):
                record.update(state="failed", result=None,
                              error="Не удалось сохранить результат сканирования; проверьте место и права записи.",
                              error_type="PersistenceError", progress={"stage": "failed", "details": {}})
                try:
                    self._save(record)
                except (OSError, ValueError):
                    pass
            finally:
                self._active_id = None
                self._threads.pop(identifier, None)
                # Keep only the current in-memory report; older records stay on disk.
                self._records = {identifier: record}
