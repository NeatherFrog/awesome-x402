"""Optional public market-history ingestion with explicit source provenance.

Yahoo Chart is an unofficial research endpoint, not a broker or executable quote
feed. No cookie, account, API key, TLS bypass, OHLC imputation, or synthetic
fallback is used. Network availability must be verified in the user's runtime.
"""
from __future__ import annotations

import json
import math
import re
import socket
import ssl
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener

from .market import MAX_BARS, validate_bars

_PROVIDER = "Yahoo Chart (public unofficial endpoint)"
_HOST = "query1.finance.yahoo.com"
_REDIRECT_HOSTS = {_HOST, "query2.finance.yahoo.com"}
_MAX_RESPONSE_BYTES = 8 * 1024 * 1024
_TIMEOUT_SECONDS = 15
_TICKER = re.compile(r"[A-Za-z0-9^=._-]{1,32}\Z")
_INTERVALS = {"15m": timedelta(minutes=15), "1h": timedelta(hours=1), "1d": timedelta(days=1)}
_RANGES = ("1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "max")
_ALIASES = {"EURUSD": "EURUSD=X", "XAUUSD": "GC=F", "NAS100": "^NDX", "BTCUSD": "BTC-USD"}
_ALIAS_WARNINGS = {
    "XAUUSD": "XAUUSD использует GC=F — непрерывный futures-прокси золота, а не spot XAU/USD или CFD вашего брокера; контракты и rollover отличаются.",
    "NAS100": "NAS100 использует ^NDX — неторгуемый индекс Nasdaq 100, а не CFD NAS100 и не исполнимую котировку брокера.",
    "EURUSD": "EURUSD=X — публичная FX-история Yahoo; она может отличаться от bid/ask, сессий и истории вашего брокера.",
    "BTCUSD": "BTC-USD — агрегированная история Yahoo; это не стакан или исполнимая котировка выбранной криптобиржи.",
}


def _clock(now):
    if now is None:
        return datetime.now(timezone.utc)
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now: требуется datetime с явно заданным часовым поясом")
    return now.astimezone(timezone.utc)


def _iso(stamp):
    return stamp.isoformat(timespec="seconds").replace("+00:00", "Z")


def _arguments(symbol, interval, range_):
    if not isinstance(symbol, str) or any(ord(character) < 32 or ord(character) == 127 for character in symbol):
        raise ValueError("Тикер должен быть строкой без управляющих символов")
    requested = symbol.strip().upper()
    if not _TICKER.fullmatch(requested) or not any(character.isalnum() for character in requested):
        raise ValueError("Тикер: 1–32 символа A–Z, 0–9, ^, =, ., _, -; URL и обозначения с ':' или '/' не поддерживаются")
    if not isinstance(interval, str) or interval not in _INTERVALS:
        raise ValueError("interval: доступны 15m, 1h и 1d")
    if not isinstance(range_, str) or range_ not in _RANGES:
        raise ValueError("range: доступны 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, max")
    if interval == "15m" and range_ not in ("1d", "5d", "1mo"):
        raise ValueError("Yahoo ограничивает 15m короткой историей: используйте 1d, 5d или 1mo")
    if interval == "1h" and range_ not in ("1d", "5d", "1mo", "3mo", "6mo", "1y", "2y"):
        raise ValueError("Для 1h доступно не более 2y истории; долгую историю запрашивайте как 1d")
    provider_symbol = _ALIASES.get(requested, requested)
    url = "https://" + _HOST + "/v8/finance/chart/" + quote(provider_symbol, safe="") + "?" + urlencode({
        "interval": interval, "range": range_, "includePrePost": "false", "events": "div,splits",
    })
    return requested, provider_symbol, url


def _safe_url(url):
    try:
        parsed = urlsplit(url)
        return (parsed.scheme == "https" and parsed.hostname in _REDIRECT_HOSTS
                and parsed.port in (None, 443) and parsed.username is None and parsed.password is None)
    except (ValueError, TypeError):
        return False


class _SafeRedirect(HTTPRedirectHandler):
    max_redirections = 3
    max_repeats = 1

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not _safe_url(newurl):
            raise ValueError("Поставщик попытался перенаправить запрос за пределы разрешённых HTTPS-хостов Yahoo")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _bad_constant(value):
    raise ValueError("Нефинитное число в JSON")


def _request_json(url):
    """Bounded TLS-verified request; exception details and headers never escape."""
    try:
        opener = build_opener(_SafeRedirect(), HTTPSHandler(context=ssl.create_default_context()))
        request = Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; PropDeskResearch/1.0)", "Accept": "application/json"})
        with opener.open(request, timeout=_TIMEOUT_SECONDS) as response:
            if not _safe_url(response.geturl()):
                raise ValueError("Ответ получен с неразрешённого хоста или без HTTPS")
            raw = response.read(_MAX_RESPONSE_BYTES + 1)
    except HTTPError as error:
        if error.code == 429:
            raise ValueError("Yahoo временно ограничил запросы (HTTP 429). Повторите позже или загрузите CSV") from None
        raise ValueError(f"Сеть или поставщик отклонили получение истории (HTTP {int(error.code)}). Проверьте доступ к query1.finance.yahoo.com или загрузите CSV") from None
    except URLError as error:
        if isinstance(error.reason, ssl.SSLError):
            raise ValueError("Проверка TLS-сертификата Yahoo не прошла; проверка не отключается. Используйте CSV или исправьте доверенные сертификаты среды") from None
        if isinstance(error.reason, (socket.timeout, TimeoutError)):
            raise ValueError("История Yahoo не получена: истёк таймаут 15 секунд. Повторите позже или загрузите CSV") from None
        raise ValueError("Не удалось получить историю по HTTPS. Проверьте сетевой доступ к query1.finance.yahoo.com или загрузите CSV") from None
    except ssl.SSLError:
        raise ValueError("Проверка TLS-сертификата Yahoo не прошла; проверка не отключается. Используйте CSV или исправьте доверенные сертификаты среды") from None
    except (socket.timeout, TimeoutError):
        raise ValueError("История Yahoo не получена: истёк таймаут 15 секунд. Повторите позже или загрузите CSV") from None
    except OSError:
        raise ValueError("Соединение с историей Yahoo прервано. Повторите позже или загрузите CSV") from None
    if len(raw) > _MAX_RESPONSE_BYTES:
        raise ValueError("Ответ Yahoo превышает допустимые 8 MiB; уменьшите диапазон истории")
    try:
        return json.loads(raw.decode("utf-8"), parse_constant=_bad_constant)
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise ValueError("Yahoo вернул некорректный JSON вместо проверяемой истории") from None


def parse_chart(payload, symbol, interval="1h", range_="3mo", *, now=None, source_url=None):
    """Validate a Yahoo fixture/response without repairing prices or their order.

    Only missing timestamps/OHLC and incomplete bars may be skipped. Malformed
    finite prices, invalid envelopes and duplicate/unordered timestamps reject
    the response. Missing volume becomes zero with a disclosed warning because
    some public FX/index feeds supply no meaningful volume.
    """
    requested, provider_symbol, expected_url = _arguments(symbol, interval, range_)
    clock = _clock(now)
    if source_url is not None and source_url != expected_url:
        raise ValueError("source_url должен соответствовать фиксированному запросу Yahoo")
    source_url = expected_url
    if not isinstance(payload, dict) or not isinstance(payload.get("chart"), dict):
        raise ValueError("Yahoo: отсутствует объект chart с историей")
    chart = payload["chart"]
    if chart.get("error") is not None:
        raise ValueError("Yahoo не вернул историю для выбранного тикера или диапазона; проверьте символ и используйте CSV при необходимости")
    results = chart.get("result")
    if not isinstance(results, list) or len(results) != 1 or not isinstance(results[0], dict):
        raise ValueError("Yahoo: требуется один непустой результат истории")
    result = results[0]
    metadata = result.get("meta") or {}
    if not isinstance(metadata, dict):
        raise ValueError("Yahoo: некорректная metadata инструмента")
    if metadata.get("symbol") is not None and (not isinstance(metadata["symbol"], str) or metadata["symbol"].upper() != provider_symbol):
        raise ValueError("Yahoo вернул историю другого инструмента; результат отклонён")
    timestamps = result.get("timestamp")
    if not isinstance(timestamps, list) or not timestamps:
        raise ValueError("Yahoo: нет временных меток истории")
    if len(timestamps) > MAX_BARS:
        raise ValueError("История Yahoo превышает 30 000 баров; уменьшите диапазон")
    indicators = result.get("indicators")
    quotes = indicators.get("quote") if isinstance(indicators, dict) else None
    if not isinstance(quotes, list) or len(quotes) != 1 or not isinstance(quotes[0], dict):
        raise ValueError("Yahoo: отсутствует ряд OHLC котировок")
    quote_rows = quotes[0]
    for field in ("open", "high", "low", "close"):
        if field not in quote_rows or not isinstance(quote_rows[field], list):
            raise ValueError("Yahoo: отсутствует полноценный ряд open/high/low/close; цены не восстанавливаются")
    if "volume" in quote_rows and quote_rows["volume"] is not None and not isinstance(quote_rows["volume"], list):
        raise ValueError("Yahoo: некорректный ряд volume")
    warnings = [
        "Публичный неофициальный endpoint Yahoo может менять формат, ограничивать доступ и задерживать данные; доступность не гарантируется.",
        "Эти OHLC — исследовательская история, не брокерские bid/ask, ликвидность, исполнимые цены или календарь проп-фирмы.",
        "Используются исходные OHLC quote, без подмены adjclose; корпоративные действия и futures rollover могут создавать разрывы.",
    ]
    if requested in _ALIAS_WARNINGS:
        warnings.append(_ALIAS_WARNINGS[requested])
    if provider_symbol.endswith("=F") and requested != "XAUUSD":
        warnings.append("Непрерывный futures-тикер Yahoo не моделирует конкретный контракт, rollover и условия брокера")
    if provider_symbol.startswith("^") and requested != "NAS100":
        warnings.append("Индекс Yahoo сам по себе не является торгуемым контрактом или CFD")
    if interval == "1d":
        warnings.append("Закрытие дневной сессии неизвестно: текущий UTC-день исключён и применяется консервативное open + 24h; это не календарь биржи")
    bars = []
    previous = None
    skips = {"forming": 0, "missing_ohlc": 0, "missing_timestamp": 0}
    missing_volume = 0
    last_close = None
    for row, epoch in enumerate(timestamps):
        if epoch is None:
            skips["missing_timestamp"] += 1
            continue
        try:
            valid_epoch = not isinstance(epoch, bool) and isinstance(epoch, (int, float)) and math.isfinite(epoch) and epoch == int(epoch)
        except (ValueError, OverflowError, TypeError):
            valid_epoch = False
        if not valid_epoch:
            raise ValueError(f"Yahoo: некорректный epoch timestamp в строке {row + 1}")
        try:
            stamp = datetime.fromtimestamp(epoch, timezone.utc)
            nominal_close = stamp + _INTERVALS[interval]
        except (ValueError, OverflowError, OSError):
            raise ValueError(f"Yahoo: timestamp вне допустимого диапазона в строке {row + 1}") from None
        if previous is not None and stamp <= previous:
            raise ValueError("Yahoo: временные метки должны возрастать без дубликатов; история не сортируется автоматически")
        previous = stamp
        if nominal_close > clock or (interval == "1d" and stamp.date() >= clock.date()):
            skips["forming"] += 1
            continue
        fields = {}
        for field in ("open", "high", "low", "close"):
            series = quote_rows[field]
            fields[field] = series[row] if row < len(series) else None
        if any(value is None for value in fields.values()):
            skips["missing_ohlc"] += 1
            continue
        volumes = quote_rows.get("volume") or []
        volume = volumes[row] if row < len(volumes) else None
        if volume is None:
            volume = 0
            missing_volume += 1
        candidate = {"time": _iso(stamp), **fields, "volume": volume}
        try:
            canonical = validate_bars([candidate])[0]
        except (ValueError, OverflowError, TypeError):
            raise ValueError(f"Yahoo: некорректные конечные OHLC/volume или high/low envelope в строке {row + 1}; цены не восстанавливаются") from None
        bars.append(canonical)
        last_close = nominal_close
    if not bars:
        raise ValueError("Yahoo не вернул ни одного полного закрытого OHLC-бара; увеличьте диапазон или загрузите CSV")
    bars = validate_bars(bars)
    skipped = sum(skips.values())
    if skipped:
        warnings.append(f"Пропущено строк: {skipped}; формирующиеся: {skips['forming']}, без OHLC: {skips['missing_ohlc']}, без timestamp: {skips['missing_timestamp']}. Пропуски не заполняются")
    if missing_volume:
        warnings.append(f"Для {missing_volume} баров volume отсутствует и явно установлен 0; это отсутствие данных, а не подтверждённый нулевой торговый объём")
    return {"bars": bars, "provenance": {
        "provider": _PROVIDER, "retrieved_at": _iso(clock), "source_url": source_url,
        "requested_symbol": requested, "provider_symbol": provider_symbol,
        "quote_currency": metadata.get("currency") if isinstance(metadata.get("currency"), str) and re.fullmatch(r"[A-Za-z]{3,8}", metadata["currency"]) else None,
        "instrument_type": metadata.get("instrumentType") if isinstance(metadata.get("instrumentType"), str) and re.fullmatch(r"[A-Z_]{1,32}", metadata["instrumentType"]) else None,
        "interval": interval, "range": range_, "last_closed_at": _iso(last_close),
        "last_closed_bar_open": bars[-1]["time"], "warnings": warnings,
        "skipped_rows": skipped, "skipped_reasons": skips, "missing_volume_rows": missing_volume,
        "bar_timestamp": "opening time UTC", "daily_close_method": "conservative UTC previous-day and open+24h filter" if interval == "1d" else None,
    }}


def get_history(symbol: str, interval="1h", range_="3mo", now: datetime | None = None) -> dict:
    """Fetch canonical closed OHLCV history or raise a sanitized ValueError.

    Safe fixed-host ticker requests only; no arbitrary URL, login, secret or
    authentication header. There is deliberately no silent synthetic fallback.
    """
    requested, _, url = _arguments(symbol, interval, range_)
    _clock(now)  # Validate an optional test clock before making a request.
    payload = _request_json(url)
    return parse_chart(payload, requested, interval, range_, now=_clock(now), source_url=url)
