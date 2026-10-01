"""Bounded public economic-calendar ingestion; never a price or alpha feed.

Only refresh() performs network I/O. Calendar availability is a prerequisite
check for conditional paper plans, not proof of compliance with a firm's rules.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import socket
import ssl
import stat
import tempfile
import threading
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener

SOURCE_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
PROVIDER = "Forex Factory weekly calendar via Fair Economy Media"
MAX_RESPONSE_BYTES = 1024 * 1024
MAX_EVENTS = 200
REFRESH_TTL = timedelta(hours=1)
FRESH_TTL = timedelta(hours=6)
_HOST = "nfs.faireconomy.media"
_TIMEOUT_SECONDS = 10
_MAX_CACHE_BYTES = 1024 * 1024
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-](?:0\d|1[0-4]):[0-5]\d)\Z")
_HASH = re.compile(r"[a-f0-9]{64}\Z")
_CURRENCIES = {"AUD", "CAD", "CHF", "CNY", "EUR", "GBP", "JPY", "NZD", "USD", "ALL"}
_IMPACTS = {"high", "medium", "low"}
_NON_ECONOMIC = {"holiday", "non-economic"}
_WARNINGS = [
    "Публичный недельный календарь может содержать задержки, пропуски и изменения; полнота расписания не подтверждена проп-фирмой.",
    "Время known_at — момент получения ответа, а не время публикации события. Этот снимок не доказывает доступность календаря в историческом бэктесте.",
    "Forecast, actual и previous не используются как торговые сигналы. Окна ограничений и применимость валют нужно сверить с актуальными правилами фирмы.",
    "Границы недели выводятся из явных смещений дат поставщика; это ограниченная область проверки, а не календарь всех рынков.",
]


def _clock(now):
    if now is None:
        return datetime.now(timezone.utc)
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now: требуется datetime с явным часовым поясом")
    return now.astimezone(timezone.utc)


def _iso(stamp):
    return stamp.isoformat(timespec="microseconds" if stamp.microsecond else "seconds").replace("+00:00", "Z")


def _seconds(value, name, minimum, maximum):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name}: требуется конечное число секунд")
    try:
        result = float(value)
    except (ValueError, OverflowError):
        raise ValueError(f"{name}: число секунд вне допустимого диапазона") from None
    if not math.isfinite(result) or not minimum <= result <= maximum:
        raise ValueError(f"{name}: число секунд вне допустимого диапазона")
    return result


def _stamp(value, name):
    if not isinstance(value, str) or len(value) > 40 or not _DATE.fullmatch(value):
        raise ValueError(f"{name}: требуется полная ISO дата с явным UTC-смещением")
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(f"{name}: недопустимая ISO дата") from None
    # -00:00 denotes an unknown local offset in RFC 3339, not verified UTC.
    if value.endswith("-00:00") or stamp.utcoffset() is None or abs(stamp.utcoffset()) > timedelta(hours=14):
        raise ValueError(f"{name}: неизвестное или недопустимое UTC-смещение")
    return stamp


def _safe_text(value, name, maximum):
    if (not isinstance(value, str) or not 1 <= len(value) <= maximum
            or any(unicodedata.category(character).startswith("C") or character in "<>" for character in value)):
        raise ValueError(f"{name}: требуется ограниченная строка без управляющих символов или HTML")
    value = value.strip()
    if not value:
        raise ValueError(f"{name}: пустая строка")
    return value


def _finite_float(value):
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("Нефинитное число в JSON")
    return number


def _bad_constant(value):
    raise ValueError("Нефинитное число в JSON")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Повторяющееся поле JSON")
        result[key] = value
    return result


def _decode(raw):
    if not isinstance(raw, bytes) or len(raw) > MAX_RESPONSE_BYTES:
        raise ValueError("Ответ календаря превышает 1 MiB или имеет неверный тип")
    try:
        payload = json.loads(raw.decode("utf-8"), parse_constant=_bad_constant,
                             parse_float=_finite_float, object_pairs_hook=_unique_object)
        pending, nodes = [(payload, 0)], 0
        while pending:
            item, depth = pending.pop()
            nodes += 1
            if depth > 16 or nodes > 20_000:
                raise ValueError("Недопустимая вложенность или сложность JSON")
            if isinstance(item, dict):
                pending.extend((child, depth + 1) for child in item.values())
            elif isinstance(item, list):
                pending.extend((child, depth + 1) for child in item)
        return payload
    except (UnicodeDecodeError, ValueError, RecursionError, OverflowError):
        raise ValueError("Поставщик вернул некорректный или нефинитный JSON календаря") from None


def _safe_url(url):
    try:
        parsed = urlsplit(url)
        return (parsed.scheme == "https" and parsed.hostname == _HOST
                and parsed.port in (None, 443) and parsed.username is None
                and parsed.password is None and not parsed.fragment)
    except (ValueError, TypeError):
        return False


class _SafeRedirect(HTTPRedirectHandler):
    max_redirections = 3
    max_repeats = 1

    def __init__(self, deadline=None):
        super().__init__()
        self.deadline = deadline

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not _safe_url(newurl):
            raise ValueError("Перенаправление календаря вне фиксированного HTTPS-хоста отклонено")
        if self.deadline is not None:
            remaining = self.deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Calendar transport deadline")
            # urllib forwards this timeout to the redirected request.
            req.timeout = min(getattr(req, "timeout", _TIMEOUT_SECONDS), remaining)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _fetch():
    """Request the fixed endpoint with verified TLS and sanitized failures."""
    try:
        redirect = _SafeRedirect()
        opener = build_opener(redirect, HTTPSHandler(context=ssl.create_default_context()))
        request = Request(SOURCE_URL, headers={
            "User-Agent": "Mozilla/5.0 (compatible; PropDeskResearch/1.0)", "Accept": "application/json",
        })
        deadline = time.monotonic() + _TIMEOUT_SECONDS
        redirect.deadline = deadline
        with opener.open(request, timeout=_TIMEOUT_SECONDS) as response:
            if not _safe_url(response.geturl()):
                raise ValueError("Ответ календаря получен с неразрешённого HTTPS-хоста")
            if response.getcode() != 200:
                raise ValueError("Календарь не получен: поставщик вернул неожиданный HTTP-статус")
            chunks, size = [], 0
            read = getattr(response, "read1", response.read)
            while size <= MAX_RESPONSE_BYTES:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("Calendar transport deadline")
                # HTTPResponse exposes the live verified socket through its
                # buffered reader. Short reads and a decreasing timeout avoid
                # extending the budget through redirects or a dripping body.
                sock = getattr(getattr(getattr(response, "fp", None), "raw", None), "_sock", None)
                if sock is not None:
                    sock.settimeout(remaining)
                chunk = read(min(65536, MAX_RESPONSE_BYTES + 1 - size))
                if not chunk:
                    break
                chunks.append(chunk)
                size += len(chunk)
            raw = b"".join(chunks)
    except HTTPError as error:
        raise ValueError(f"Календарь не получен: HTTP {int(error.code)}; проверьте доступ к {_HOST}") from None
    except URLError as error:
        if isinstance(error.reason, ssl.SSLError):
            raise ValueError("Проверка TLS-сертификата календаря не прошла; проверка не отключается") from None
        if isinstance(error.reason, (socket.timeout, TimeoutError)):
            raise ValueError("Календарь не получен: таймаут 10 секунд") from None
        raise ValueError(f"Календарь не получен по HTTPS; проверьте сетевой доступ к {_HOST}") from None
    except ssl.SSLError:
        raise ValueError("Проверка TLS-сертификата календаря не прошла; проверка не отключается") from None
    except (socket.timeout, TimeoutError):
        raise ValueError("Календарь не получен: таймаут 10 секунд") from None
    except OSError:
        raise ValueError("Соединение с календарём прервано") from None
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ValueError("Ответ календаря превышает 1 MiB")
    return raw


def _week_start(stamp):
    try:
        return stamp.date() - timedelta(days=(stamp.weekday() + 1) % 7)
    except OverflowError:
        raise ValueError("Граница недели календаря вне допустимого диапазона") from None


def _digest(value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def parse_calendar(payload, *, retrieved_at=None):
    """Validate the entire weekly response; an ambiguous row fails closed.

    Input dates preserve their explicit provider offsets for week inference.
    Output dates are UTC. No publication timestamp is invented, and prediction
    or released-number fields are deliberately absent from normalized events.
    """
    clock = _clock(retrieved_at)
    if not isinstance(payload, list) or not 1 <= len(payload) <= MAX_EVENTS:
        raise ValueError("Календарь должен содержать от 1 до 200 событий; пустой ответ не подтверждает отсутствие новостей")
    rows, events, week_starts, offsets, seen = [], [], set(), set(), set()
    non_economic = 0
    for index, item in enumerate(payload, 1):
        if not isinstance(item, dict):
            raise ValueError(f"Событие {index}: требуется объект")
        title = _safe_text(item.get("title"), f"Событие {index}, title", 256)
        currency = _safe_text(item.get("country"), f"Событие {index}, country", 3).upper()
        if currency not in _CURRENCIES:
            raise ValueError(f"Событие {index}: неподдерживаемая или неизвестная валюта")
        impact = _safe_text(item.get("impact"), f"Событие {index}, impact", 16).lower()
        if impact not in _IMPACTS | _NON_ECONOMIC:
            raise ValueError(f"Событие {index}: неподдерживаемая или неизвестная важность")
        local_stamp = _stamp(item.get("date"), f"Событие {index}, date")
        try:
            stamp = local_stamp.astimezone(timezone.utc)
        except (ValueError, OverflowError):
            raise ValueError(f"Событие {index}: дата UTC вне допустимого диапазона") from None
        key = (_iso(stamp), currency, title, impact)
        if key in seen:
            raise ValueError("Календарь содержит повторяющееся событие")
        seen.add(key)
        rows.append({"title": title, "country": currency, "date": local_stamp.isoformat(), "impact": impact})
        if impact in _NON_ECONOMIC:
            non_economic += 1
            continue
        week_starts.add(_week_start(local_stamp))
        offsets.add(local_stamp.utcoffset())
        events.append({"title": title, "currency": currency, "impact": impact,
                       "time": _iso(stamp), "known_at": _iso(clock)})
    if not events:
        raise ValueError("Нет событий с известной экономической важностью; отсутствие экономических новостей не подтверждено")
    if len(week_starts) != 1:
        raise ValueError("Календарь содержит смешанные недели; область покрытия неоднозначна")
    week = next(iter(week_starts))
    beginnings, endings = [], []
    for offset in offsets:
        zone = timezone(offset)
        if _week_start(clock.astimezone(zone)) != week:
            raise ValueError("Календарь относится к другой или истёкшей неделе")
        beginnings.append(datetime.combine(week, datetime.min.time(), zone).astimezone(timezone.utc))
        endings.append(datetime.combine(week + timedelta(days=7), datetime.min.time(), zone).astimezone(timezone.utc))
    # When different offsets occur (e.g. DST), use only their intersection.
    beginning, ending = max(beginnings), min(endings)
    if not beginning <= clock < ending:
        raise ValueError("Граница недели календаря неоднозначна для текущего времени")
    events.sort(key=lambda event: (_stamp(event["time"], "event.time"), event["currency"], event["title"], event["impact"]))
    offset_strings = sorted(str(timezone(offset)) for offset in offsets)
    warnings = list(_WARNINGS)
    if non_economic:
        warnings.append(f"Holiday/Non-Economic исключены из экономических blackout-событий: {non_economic}. Эти записи не подтверждают торговые сессии или доступность рынка.")
    return {
        "rows": rows, "events": events,
        "coverage": {"basis": "inferred_provider_local_sunday_week", "week_start_local": week.isoformat(),
                     "start": _iso(beginning), "end_exclusive": _iso(ending), "offsets": offset_strings},
        "warnings": warnings,
    }


class CalendarFeed:
    """Local cache and explicit refresh; construction and reads never fetch."""

    def __init__(self, directory):
        self.directory = Path(directory)
        self.path = self.directory / "news.json"
        self._lock = threading.RLock()
        self._last_error = None
        self._last_attempt = None
        self._lifecycle_lock = threading.RLock()
        self._thread = None
        self._stop_event = threading.Event()
        self._poll_interval = None
        self._worker_error = None

    def start(self, enabled=lambda: False, poll_interval=30):
        """Start one non-daemon serving worker; return False if already running.

        enabled must be a quick callback returning a strict boolean. Disabled
        workers make no network requests. Reading status never starts a worker.
        """
        if not callable(enabled):
            raise ValueError("enabled: требуется callable, возвращающий boolean")
        poll_interval = _seconds(poll_interval, "poll_interval", .01, 300)
        with self._lifecycle_lock:
            if self._thread is not None and self._thread.is_alive():
                return False
            self._stop_event = threading.Event()
            self._poll_interval = poll_interval
            self._worker_error = None
            self._thread = threading.Thread(
                target=self._background, args=(enabled, self._poll_interval, self._stop_event),
                name="PropDeskCalendar", daemon=False,
            )
            self._thread.start()
            return True

    def stop(self, timeout=12):
        """Interrupt waiting and join; return whether the worker has exited.

        An in-progress HTTPS request keeps its verified transport timeout. A
        False return retains the thread reference so a caller can join again.
        """
        timeout = _seconds(timeout, "timeout", 0, 30)
        with self._lifecycle_lock:
            thread = self._thread
            self._stop_event.set()
        if thread is None:
            return True
        if thread is threading.current_thread():
            return False
        thread.join(float(timeout))
        stopped = not thread.is_alive()
        if stopped:
            with self._lifecycle_lock:
                if self._thread is thread:
                    self._thread = None
        return stopped

    def _background(self, enabled, poll_interval, stopped):
        while not stopped.is_set():
            try:
                if stopped.is_set():
                    break
                active = enabled()
                if stopped.is_set():
                    break
                if not isinstance(active, bool):
                    raise TypeError("enabled callback must return boolean")
                self._worker_error = None
                if active:
                    due = self.status()["refresh_due"]
                    if stopped.is_set():
                        break
                    if due:
                        self.refresh(_cancel_event=stopped)
            except Exception:
                # Callback/worker details may contain application secrets. No
                # arbitrary exception strings or background tracebacks escape.
                self._worker_error = "Фоновая проверка календаря не выполнена; проверьте состояние автопилота и провайдера"
            if stopped.wait(poll_interval):
                break

    def _load(self):
        try:
            if self.directory.is_symlink() or self.path.is_symlink():
                return None, "Кэш календаря с символической ссылкой отклонён"
            descriptor = os.open(self.path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
            with os.fdopen(descriptor, "rb") as stream:
                metadata = os.fstat(stream.fileno())
                if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > _MAX_CACHE_BYTES:
                    return None, "Кэш календаря имеет недопустимый тип или размер"
                raw = stream.read(_MAX_CACHE_BYTES + 1)
            record = _decode(raw)
            if (not isinstance(record, dict) or type(record.get("schema_version")) is not int or record["schema_version"] != 1
                    or record.get("source") != SOURCE_URL or record.get("provider") != PROVIDER
                    or not isinstance(record.get("body_sha256"), str) or not _HASH.fullmatch(record["body_sha256"])):
                raise ValueError("Некорректная версия или источник кэша")
            stamp = _stamp(record.get("retrieved_at"), "retrieved_at")
            if stamp.utcoffset() != timedelta(0):
                raise ValueError("Кэш должен содержать UTC дату получения")
            calendar = parse_calendar(record.get("rows"), retrieved_at=stamp)
            expected = _digest({"rows": calendar["rows"], "retrieved_at": _iso(stamp), "coverage": calendar["coverage"]})
            if record.get("normalized_sha256") != expected or record.get("coverage") != calendar["coverage"]:
                raise ValueError("Кэш календаря не прошёл проверку согласованности")
            return {**record, **calendar}, None
        except FileNotFoundError:
            return None, None
        except (OSError, ValueError, TypeError, OverflowError, RecursionError):
            return None, "Кэш календаря не читается или не прошёл проверку; область новостей неизвестна"

    def _save(self, record):
        if self.directory.is_symlink() or self.path.is_symlink():
            raise ValueError("Кэш календаря с символической ссылкой отклонён")
        self.directory.mkdir(parents=True, exist_ok=True)
        raw = json.dumps(record, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
        if len(raw) > _MAX_CACHE_BYTES:
            raise ValueError("Кэш календаря превышает допустимый размер")
        descriptor, temporary = tempfile.mkstemp(prefix=".news-", suffix=".tmp", dir=self.directory)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass

    def _state(self, clock):
        record, cache_error = self._load()
        warnings = list(record["warnings"] if record else _WARNINGS)
        if cache_error:
            warnings.append(cache_error)
        if self._last_error:
            warnings.append(self._last_error)
        if self._worker_error:
            warnings.append(self._worker_error)
        age, confirmed, state = None, False, "unknown"
        if record:
            retrieved = _stamp(record["retrieved_at"], "retrieved_at").astimezone(timezone.utc)
            age = (clock - retrieved).total_seconds()
            beginning = _stamp(record["coverage"]["start"], "coverage.start")
            ending = _stamp(record["coverage"]["end_exclusive"], "coverage.end_exclusive")
            if age < 0:
                warnings.append("Дата получения кэша находится в будущем; календарь не подтверждён")
            elif age > FRESH_TTL.total_seconds():
                state = "stale"
                warnings.append("Снимок календаря старше 6 часов; область новостей неизвестна")
            elif not beginning <= clock < ending:
                state = "stale"
                warnings.append("Недельная область кэша истекла; область новостей неизвестна")
            else:
                confirmed, state = True, "ready"
        reference = self._last_attempt
        if record:
            retrieved = _stamp(record["retrieved_at"], "retrieved_at").astimezone(timezone.utc)
            if reference is None or retrieved > reference:
                reference = retrieved
        next_refresh = reference + REFRESH_TTL if reference is not None else None
        # A clock rollback does not confirm data or suppress recovery forever.
        refresh_due = next_refresh is None or clock >= next_refresh or (reference is not None and reference > clock)
        status = {
            "provider": PROVIDER, "source": SOURCE_URL, "generation": "provider", "state": state,
            "confirmed": confirmed, "retrieved_at": record["retrieved_at"] if record else None,
            "observed_at": record["retrieved_at"] if record else None, "age_seconds": age,
            "event_count": len(record["events"]) if record else 0,
            "coverage": record["coverage"] if record else None,
            "body_sha256": record["body_sha256"] if record else None,
            "refresh_due": refresh_due, "next_refresh_at": _iso(next_refresh) if next_refresh else None,
            "last_attempt_at": _iso(self._last_attempt) if self._last_attempt else None,
            "last_error": self._last_error, "warnings": warnings,
            "worker_running": self._thread is not None and self._thread.is_alive(),
            "worker_stopping": self._thread is not None and self._thread.is_alive() and self._stop_event.is_set(),
            "worker_poll_interval": self._poll_interval, "worker_error": self._worker_error,
            "provenance": {"provider": PROVIDER, "source": SOURCE_URL, "transport": "HTTPS; TLS verification enabled",
                           "known_at_basis": "actual retrieval clock, not provider publication time",
                           "historical_publication_times_verified": False, "complete_schedule_verified": False},
        }
        return status, record

    def status(self, now=None):
        clock = _clock(now)
        with self._lock:
            return self._state(clock)[0]

    def context(self, now=None):
        clock = _clock(now)
        with self._lock:
            status, record = self._state(clock)
            return {"confirmed": status["confirmed"], "source": SOURCE_URL,
                    "observed_at": status["observed_at"], "generation": "provider", "provider": PROVIDER,
                    "events": record["events"] if status["confirmed"] else [],
                    "coverage": status["coverage"], "body_sha256": status["body_sha256"],
                    "provenance": status["provenance"], "warnings": status["warnings"]}

    def refresh(self, now=None, *, _cancel_event=None):
        # now is injectable for reproducible fixtures. Production should omit it
        # so the successful response is stamped after transport completes.
        clock = _clock(now)
        with self._lock:
            status, _ = self._state(clock)
            if not status["refresh_due"] or (_cancel_event is not None and _cancel_event.is_set()):
                return status
            self._last_attempt = clock
            try:
                raw = _fetch()
                retrieved = _clock(now)
                calendar = parse_calendar(_decode(raw), retrieved_at=retrieved)
                record = {
                    "schema_version": 1, "provider": PROVIDER, "source": SOURCE_URL,
                    "retrieved_at": _iso(retrieved), "body_sha256": hashlib.sha256(raw).hexdigest(),
                    "rows": calendar["rows"], "coverage": calendar["coverage"], "warnings": calendar["warnings"],
                    "normalized_sha256": _digest({"rows": calendar["rows"], "retrieved_at": _iso(retrieved),
                                                  "coverage": calendar["coverage"]}),
                    "provenance": {"provider": PROVIDER, "source": SOURCE_URL,
                                   "known_at_basis": "actual retrieval clock, not provider publication time"},
                }
                self._save(record)
                self._last_error = None
                clock = retrieved
            except ValueError as error:
                # Only locally authored validation messages reach callers.
                self._last_error = str(error)
            except OSError:
                self._last_error = "Кэш календаря не удалось атомарно сохранить; прежний снимок сохранён"
            return self._state(_clock(now))[0]
