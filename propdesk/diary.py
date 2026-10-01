"""Read-only monthly diary of the frozen algorithm's historical replay.

The ledger is deliberately separate from the user's journal.  It represents
modeled decisions and fills, never broker executions or an invented history of
our trading.  Charts use only local quote files; optional quote warming runs in
a background worker and never in ``build_diary`` or an HTTP GET.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile
from urllib.parse import urlencode

from . import feeds, market, strategies
from .timezones import timezone_for

_SYMBOLS = ("SPY", "QQQ", "IWM", "TLT", "GLD")
_EXCHANGES = {"SPY": "AMEX", "QQQ": "NASDAQ", "IWM": "AMEX", "TLT": "NASDAQ", "GLD": "AMEX"}
_FAMILIES = {"bt_sma_10_30", "qc_ema_15_30", "faber_sma_10m"}
_REPORT = Path("docs/sourced-strategy-research.json")
_STUDIES = {"sourced_daily": (_REPORT, _FAMILIES),
            "mean_reversion": (Path("docs/mean-reversion-research.json"), {"rsi2_pullback_5"})}
_QUOTE_LIMIT = 12 * 1024 * 1024
_MONTH = re.compile(r"\d{4}-(?:0[1-9]|1[0-2])\Z")
_WARNINGS = [
    "Это ретроспективный исторический прогон алгоритма, а не наши реальные сделки, выплаты или независимый форвард-тест.",
    "Решения восстановлены по закрытым барам; цены исполнения и расходы смоделированы, брокерские исполнения неизвестны.",
    "Графики строятся из локальных котировок. Это не скриншоты TradingView; ссылка открывает настоящий TradingView отдельно.",
    "Новости, настроение и макроцикл не использованы как проверенные фильтры этой стратегии; объяснения их не выдумывают.",
]


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _digest(value):
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _iso(value):
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _clock(now):
    if now is None:
        return datetime.now(timezone.utc)
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be a timezone-aware datetime")
    return now.astimezone(timezone.utc)


def _period(now, month):
    tz = timezone_for("Europe/Kyiv")
    current_start = now.astimezone(tz).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if month is None:
        month = (current_start - timedelta(days=1)).strftime("%Y-%m")
    if not isinstance(month, str) or not _MONTH.fullmatch(month):
        raise ValueError("month: required YYYY-MM")
    try:
        start = datetime.strptime(month, "%Y-%m").replace(tzinfo=tz)
    except ValueError:
        raise ValueError("month: invalid calendar month") from None
    end = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
    if end > current_start:
        raise ValueError("Only completed calendar months can be replayed")
    return {"month": month, "start": _iso(start), "end_exclusive": _iso(end), "timezone": "Europe/Kyiv"}, start, end


def _session_close(label):
    """Conservative US regular-session close, not a fabricated intrabar fill.

    The source's daily timestamp labels the opening.  NY16:00 also excludes
    incomplete half-day bars conservatively; exact intraday stop time is unknown.
    """
    stamp = market.utc_datetime(label).astimezone(timezone_for("America/New_York"))
    return stamp.replace(hour=16, minute=0, second=0, microsecond=0).astimezone(timezone.utc)


def _number(value, default=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return default
    return value


def _read_json(path):
    if path.stat().st_size > _QUOTE_LIMIT:
        raise ValueError("Local diary file exceeds size limit")
    return json.loads(path.read_text(encoding="utf-8"))


def _quotes(root, report, symbol, directory):
    """Prefer the exact hashed study snapshot; fail closed on its corruption."""
    for record in report.get("snapshots", []):
        if not isinstance(record, dict) or record.get("symbol") != symbol:
            continue
        relative = record.get("json_path")
        if not isinstance(relative, str):
            break
        path = (root / relative).resolve()
        allowed = (root / "data/sourced-history").resolve()
        if not path.is_relative_to(allowed):
            return [], "invalid_snapshot_path"
        if not path.exists():
            break
        try:
            if path.stat().st_size > _QUOTE_LIMIT:
                raise ValueError("Snapshot too large")
            body = path.read_bytes()
            if hashlib.sha256(body).hexdigest() != record.get("json_sha256"):
                return [], "snapshot_hash_mismatch"
            bars = market.validate_bars(json.loads(body)["bars"])
            return bars, "frozen_study_snapshot"
        except (OSError, ValueError, KeyError, TypeError):
            return [], "invalid_snapshot"
    cache = directory / (symbol + "-1d.json")
    try:
        payload = _read_json(cache)
        if payload.get("symbol") != symbol:
            raise ValueError("Quote cache symbol mismatch")
        return market.validate_bars(payload["bars"]), "runtime_history_revision_possible"
    except (OSError, ValueError, KeyError, TypeError):
        return [], "not_loaded"


def _ema(values, period):
    if len(values) < period:
        return None
    value = sum(values[:period]) / period
    alpha = 2 / (period + 1)
    for close in values[period:]:
        value = alpha * close + (1 - alpha) * value
    return value


def _rsi2(closes):
    """The fixed model's exact Wilder seed/smoothing, including flat RSI=50."""
    if len(closes) < 3:
        return None
    gain = sum(max(closes[i] - closes[i - 1], 0) for i in (1, 2)) / 2
    loss = sum(max(closes[i - 1] - closes[i], 0) for i in (1, 2)) / 2
    for index in range(3, len(closes)):
        change = closes[index] - closes[index - 1]
        gain = (gain + max(change, 0)) / 2
        loss = (loss + max(-change, 0)) / 2
    return 50.0 if gain == loss == 0 else 100.0 if loss == 0 else 100 - 100 / (1 + gain / loss)


def _entry_context(trade, strategy_id, bars, basis):
    label = trade["signal_time"]
    reasons = []
    indicators = {"calculation_basis": basis, "as_of_bar_open": label, "as_of_close": _iso(_session_close(label))}
    if strategy_id == "bt_sma_10_30":
        reasons.append("На предыдущем закрытом дневном баре SMA10 пересекла SMA30 вверх: предыдущая разница строго < 0, новая строго > 0. Равенство не считается пересечением.")
    elif strategy_id == "qc_ema_15_30":
        reasons.append("На предыдущем закрытом дневном баре EMA15 > EMA30 × 1.00015; вход разрешён только при отсутствии позиции.")
    elif strategy_id == "rsi2_pullback_5":
        reasons.append("На предыдущем закрытом дневном баре Wilder RSI2 строго < 5, а close строго > SMA200: перепроданный откат внутри фильтра восходящего тренда. Равенство не разрешает вход.")
    else:
        reasons.append("На первом торговом открытии нового месяца предыдущая завершённая месячная цена выше среднего 10 завершённых месячных закрытий.")
    # A prefix ending at the actual signal label is the only input to reasons.
    # Later month prices, realized profit and future exits cannot change them.
    prefix = [bar for bar in bars if bar["time"] <= label]
    if prefix and prefix[-1]["time"] == label:
        closes = [bar["close"] for bar in prefix]
        if strategy_id == "bt_sma_10_30" and len(closes) >= 31:
            indicators.update(sma10=sum(closes[-10:]) / 10, sma30=sum(closes[-30:]) / 30,
                              previous_difference=sum(closes[-11:-1]) / 10 - sum(closes[-31:-1]) / 30)
            indicators["difference"] = indicators["sma10"] - indicators["sma30"]
        elif strategy_id == "qc_ema_15_30" and len(closes) >= 30:
            indicators.update(ema15=_ema(closes, 15), ema30=_ema(closes, 30), tolerance=1.00015)
        elif strategy_id == "faber_sma_10m":
            endings = {}
            for bar in prefix:
                endings[bar["time"][:7]] = bar["close"]
            if len(endings) >= 10:
                indicators.update(previous_month_close=closes[-1], sma10_months=sum(list(endings.values())[-10:]) / 10)
        elif strategy_id == "rsi2_pullback_5" and len(closes) >= 200:
            indicators.update(rsi2=_rsi2(closes), sma200=sum(closes[-200:]) / 200,
                              sma5=sum(closes[-5:]) / 5, close=closes[-1], rsi_entry_threshold=5)
            indicators["entry_condition"] = indicators["rsi2"] < 5 and closes[-1] > indicators["sma200"]
        atr = strategies.atr(prefix, 14)[-1]
        if atr is not None:
            indicators["atr14"] = atr
    else:
        indicators["values_status"] = "original_signal_quotes_unavailable"
    reasons.append("Вход смоделирован на следующем открытии с издержками; будущие бары не использованы для сигнала.")
    if strategy_id == "rsi2_pullback_5":
        reasons.append("Фиксированный стоп — 3 × ATR14 предыдущего закрытого бара; тейк-профита нет. Выход на следующем открытии после close строго > SMA5 либо по стопу; пересечение SMA5 не требуется.")
    else:
        reasons.append("Фиксированный стоп — 3 × ATR14 предыдущего закрытого бара; тейк-профита нет, выход по обратному сигналу или стопу.")
    if basis == "runtime_history_revision_possible":
        reasons.append("Числа индикаторов пересчитаны по локально загруженной истории; возможные правки поставщика не подтверждают исходный сигнал заново.")
    return reasons, indicators


def _exit_notes(reason, strategy_id):
    if reason == "gap_stop":
        return ["Сессия открылась ниже фиксированного стопа: выход по цене открытия с издержками, а не по недоступной цене стопа."]
    if reason == "stop":
        return ["Дневной low достиг фиксированного стопа; смоделирован выход по стопу с издержками. Точное время касания внутри дня неизвестно."]
    if reason == "signal_exit":
        rule = {"bt_sma_10_30": "SMA10 пересекла SMA30 вниз при строго положительной предыдущей и строго отрицательной новой разнице",
                "qc_ema_15_30": "EMA15 стала ниже EMA30",
                "faber_sma_10m": "завершённое месячное закрытие стало ниже среднего 10 завершённых месяцев",
                "rsi2_pullback_5": "Предыдущее дневное закрытие строго выше SMA5; достаточно уровня, пересечение не требуется"}[strategy_id]
        return [rule + "; выход на следующем открытии с издержками."]
    return ["Причина выхода в отчёте не распознана; торговое объяснение не выдумано."]


def _chart(bars, start, end, entry_time, exit_time, basis):
    closed = [bar for bar in bars if _session_close(bar["time"]) < end]
    if not closed:
        return {"state": "unavailable", "source": basis, "bars": [], "is_tradingview_screenshot": False}
    # A contiguous bounded window preserves actual candle spacing and does not
    # splice a distant old entry into the last month's chart.
    visible = closed[-120:]
    visible_start = market.utc_datetime(visible[0]["time"])
    visible_end = _session_close(visible[-1]["time"])
    return {"state": "ready", "source": basis, "label": "Локальный график реальных котировок · исторический прогон",
            "bars": visible, "period_start": _iso(visible_start), "last_session_close": _iso(visible_end),
            "entry_in_view": visible_start <= market.utc_datetime(entry_time) <= visible_end,
            "exit_in_view": bool(exit_time and visible_start <= market.utc_datetime(exit_time) <= visible_end),
            "is_tradingview_screenshot": False, "quote_timestamps": "daily_bar_open_utc",
            "coverage": "local_quote_history; no imputation; source may omit latest completed session"}


def _trade_item(trade, strategy_id, bars, basis, start, end):
    entry = market.utc_datetime(trade["entry_time"])
    exit_label = market.utc_datetime(trade["exit_time"])
    forced = trade.get("exit_reason") == "end_of_sample"
    closed = not forced and exit_label < end
    exit_time = trade["exit_time"] if closed else None
    reasons, indicators = _entry_context(trade, strategy_id, bars, basis)
    identifier = hashlib.sha256((strategy_id + "|" + trade["symbol"] + "|" + trade["entry_time"]).encode()).hexdigest()[:20]
    item = {"id": identifier, "symbol": trade["symbol"], "strategy_id": strategy_id, "side": "long",
            "mode": "historical_replay", "status": "closed" if closed else "open_at_period_end",
            "carried_from_previous_month": entry < start,
            "entry_time": trade["entry_time"], "signal_time": trade["signal_time"],
            "signal_known_after": _iso(_session_close(trade["signal_time"])),
            "entry_price": _number(trade.get("entry_price")), "raw_entry_price": _number(trade.get("raw_entry_price")),
            "exit_time": exit_time, "exit_price": _number(trade.get("exit_price")) if closed else None,
            "raw_exit_price": _number(trade.get("raw_exit_price")) if closed else None,
            "exit_reason": trade.get("exit_reason") if closed else None,
            "exit_time_precision": ("intrabar_time_unknown" if trade.get("exit_reason") == "stop" else "modeled_session_open") if closed else None,
            "stop": _number(trade.get("stop")), "take_profit": None,
            "quantity": _number(trade.get("quantity")), "risk_amount": _number(trade.get("risk_amount")),
            "pnl": _number(trade.get("pnl")) if closed else None, "return_r": _number(trade.get("return_r")) if closed else None,
            "costs": {key: _number(trade.get(key), 0) for key in ("fees", "slippage", "spread", "financing_total", "total_costs")} if closed else None,
            "entry_reasons": reasons, "entry_indicators": indicators,
            "exit_reasons": _exit_notes(trade.get("exit_reason"), strategy_id) if closed else ["Позиция открыта на границе месяца; стратегия ещё не дала показанный в дневнике выход."],
            "tradingview_url": "https://www.tradingview.com/chart/?" + urlencode({"symbol": _EXCHANGES[trade["symbol"]] + ":" + trade["symbol"], "interval": "D"}),
            "tradingview_screenshot": {"state": "not_captured", "reason": "Реальный скриншот TradingView не получен; локальный график обозначен отдельно."}}
    if forced and _session_close(trade["exit_time"]) < end:
        item["valuation_boundary"] = {"time": _iso(_session_close(trade["exit_time"])),
                                      "hypothetical_liquidation_price": _number(trade.get("exit_price")),
                                      "hypothetical_liquidation_pnl": _number(trade.get("pnl")),
                                      "reason": "Принудительная оценка в конце бэктеста, а не сигнал стратегии и не реальная закрытая сделка."}
    item["chart"] = _chart(bars, start, end, item["entry_time"], exit_time, basis)
    return item


def _summary(window, trades, start, end):
    points = window.get("equity_curve", [])
    before = [row for row in points if _session_close(row["time"]) < start]
    within = [row for row in points if start <= _session_close(row["time"]) < end]
    initial = before[-1]["equity"] if before else window.get("metrics", {}).get("initial_equity")
    final = within[-1]["equity"] if within else None
    change = final - initial if _number(initial) is not None and _number(final) is not None else None
    return {"currency": "USD", "positions": len(trades), "entries_in_month": sum(not row["carried_from_previous_month"] for row in trades),
            "closed_in_month": sum(row["status"] == "closed" for row in trades),
            "open_at_period_end": sum(row["status"] != "closed" for row in trades),
            "closed_trade_pnl": sum(row["pnl"] or 0 for row in trades if row["status"] == "closed"),
            "month_open_equity": initial, "month_end_equity": final, "month_equity_change": change,
            "month_return_pct": change / initial * 100 if change is not None and initial > 0 else None,
            "equity_observations": len(within), "pnl_basis": "Closed-trade PnL covers each whole trade, including pre-month holding; monthly equity change is separate and includes modeled boundary-liquidation costs.",
            "live_executions": 0, "payouts": 0}


def build_diary(root, *, now=None, month=None, directory=None, study="sourced_daily"):
    """Build a bounded, causal monthly replay view without requests or writes."""
    if not isinstance(study, str) or study not in _STUDIES:
        raise ValueError("study: sourced_daily или mean_reversion")
    report_path, families = _STUDIES[study]
    root = Path(root).resolve()
    directory = Path(directory).resolve() if directory is not None else root / ".local/diary-quotes"
    clock = _clock(now)
    period, start, end = _period(clock, month)
    result = {"schema_version": 1, "state": "no_report", "mode": "historical_replay", "title": "Дневник алгоритма · исторический прогон",
              "study": study, "period": period, "generated_at": _iso(clock), "strategy": None, "qualification": None,
              "summary": None, "trades": [], "warnings": list(_WARNINGS), "charts_source_status": "unavailable", "available_months": [],
              "manual_journal_unchanged": True, "live_orders": False}
    try:
        report = _read_json(root / report_path)
    except FileNotFoundError:
        result["reason"] = "Отчёт стратегии ещё не установлен; история реальных сделок не выдумывается."
        return result
    except (OSError, ValueError, TypeError):
        result.update(state="unavailable", reason="Локальный отчёт не читается; дневник не сформирован.")
        return result
    try:
        if _digest(report["protocol"]) != report["protocol_sha256"]:
            raise ValueError("Frozen protocol hash mismatch")
        lock = report.get("training_lock")
        if lock is not None and _digest(lock) != report.get("training_lock_sha256"):
            raise ValueError("Frozen selection hash mismatch")
        primary = report.get("primary_strategy_id") or (lock or {}).get("primary_strategy_id")
        if primary is None:
            result.update(state="in_progress", reason="Правила зафиксированы; выбранная на обучении стратегия ещё не опубликована.")
            return result
        if not isinstance(lock, dict) or primary != lock.get("primary_strategy_id"):
            raise ValueError("Report primary differs from frozen training selection")
        if primary not in families:
            raise ValueError("Unknown sourced family")
        if not report.get("strategies") and report.get("phase") not in ("completed", "final_review"):
            result.update(state="in_progress", reason="Выбор на обучении зафиксирован; контрольный дневник ещё рассчитывается.")
            return result
        selected = next(row for row in report["strategies"] if row.get("id") == primary)
        if selected.get("primary") is not True or report.get("selected_strategy_id") not in (None, primary):
            raise ValueError("Selected diary strategy differs from frozen primary")
        window = selected["windows"]["confirmation"]
        available = sorted({row["month"] for row in window.get("monthly_returns", [])})
        result.update(strategy={"id": primary, "name": selected.get("name", primary), "selection": "frozen_training_primary", "protocol_sha256": report["protocol_sha256"]},
                      qualification={"historical_price_model_eligible": bool(selected.get("eligible_historical_price_model")),
                                     "real_prop_qualified": False, "reasons": selected.get("reasons", []),
                                     "status": "research_watch_only"},
                      available_months=available)
        if period["month"] not in available:
            result.update(state="unavailable", reason="Этот месяц отсутствует в опубликованном контрольном периоде; свежая история не подменяется старым месяцем.")
            return result
        quote_report = ({"snapshots": report["protocol"].get("inputs", [])}
                        if study == "mean_reversion" else report)
        quotes = {symbol: _quotes(root, quote_report, symbol, directory) for symbol in _SYMBOLS}
        for trade in window.get("trades", []):
            if trade.get("symbol") not in _SYMBOLS:
                raise ValueError("Unexpected instrument in diary")
            entry, exit_label = market.utc_datetime(trade["entry_time"]), market.utc_datetime(trade["exit_time"])
            if entry >= end or exit_label < start:
                continue
            if _session_close(trade["signal_time"]) >= entry:
                raise ValueError("Noncausal entry signal")
            bars, basis = quotes[trade["symbol"]]
            result["trades"].append(_trade_item(trade, primary, bars, basis, start, end))
        result["trades"].sort(key=lambda row: (row["entry_time"], row["symbol"]))
        result.update(state="ready", summary=_summary(window, result["trades"], start, end),
                      charts_source_status="ready" if result["trades"] and all(row["chart"]["state"] == "ready" for row in result["trades"]) else "partial_or_not_loaded")
        if not result["qualification"]["real_prop_qualified"]:
            result["warnings"].append("Стратегия ещё не подтверждена для реальной проп-фирмы. Дневник показывает её исторические решения и не превращает их в разрешённые торговые сигналы.")
        return result
    except (KeyError, ValueError, TypeError, StopIteration, OverflowError):
        result.update(state="unavailable", reason="Структура или целостность отчёта не подтверждена; дневник не сформирован.", trades=[], summary=None)
        return result


def _write_cache(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".diary-quotes-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(_canonical(value) + "\n")
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def warm_diary_quotes(root, *, now=None, history_loader=None, directory=None):
    """Optionally download user-local charts once a day in a background worker.

    This does not alter the frozen backtest, rules, eligibility or manual
    journal.  The unofficial quote provider may fail; failures stay explicit.
    The caller owns thread scheduling and must never await this from a GET.
    """
    root, clock = Path(root).resolve(), _clock(now)
    directory = Path(directory).resolve() if directory is not None else root / ".local/diary-quotes"
    loader = history_loader or feeds.get_history
    status = {"updated_at": _iso(clock), "mode": "local_quote_cache", "symbols": {}, "live_orders": False}

    def load(symbol):
        path = directory / (symbol + "-1d.json")
        try:
            cached = _read_json(path)
            if cached.get("retrieved_at", "")[:10] == clock.date().isoformat() and cached.get("symbol") == symbol:
                market.validate_bars(cached["bars"])
                return symbol, {"state": "cached", "bars": len(cached["bars"])}
        except (OSError, ValueError, KeyError, TypeError):
            pass
        try:
            history = loader(symbol, "1d", "5y", now=clock)
            bars = market.validate_bars(history["bars"])
            _write_cache(path, {"symbol": symbol, "retrieved_at": _iso(clock), "bars": bars, "provenance": history.get("provenance", {}),
                                "basis": "runtime_history_revision_possible", "not_a_frozen_backtest_snapshot": True})
            return symbol, {"state": "loaded", "bars": len(bars), "last_bar": bars[-1]["time"]}
        except (OSError, ValueError, KeyError, TypeError):
            return symbol, {"state": "unavailable", "reason": "Публичные котировки не загружены; синтетические свечи не создаются."}

    with ThreadPoolExecutor(max_workers=5, thread_name_prefix="diary-quotes") as executor:
        for future in as_completed([executor.submit(load, symbol) for symbol in _SYMBOLS]):
            symbol, outcome = future.result()
            status["symbols"][symbol] = outcome
    _write_cache(directory / "status.json", status)
    return status
