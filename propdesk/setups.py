"""Causal, conditional paper plans built from a frozen research candidate.

Manual hypotheses and an optional cached provider calendar are planning inputs,
never a regime optimizer, execution service, or proof of a profitable strategy.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from numbers import Real

from .market import utc_datetime
from .strategies import catalog

_MACRO_CYCLES = {"unknown", "expansion", "slowdown", "recession", "recovery"}
_REGIMES = {"trend", "range", "volatile", "transition"}
_IMPACTS = {"high", "medium", "low"}
_CATALOG = {item["id"]: item for item in catalog()}
_TRIGGERS = {
    "ema_pullback": "Ждать закрытия обратно через выбранную быструю EMA по направлению медленной EMA; периоды сохранены из обучения.",
    "donchian_breakout": "Ждать закрытия за каналом предыдущих баров с сохранённым lookback; текущий бар не включать в канал.",
    "rsi_reversion": "Ждать возврата RSI через сохранённый порог в достаточно спокойном диапазоне.",
    "bollinger_reversion": "Ждать закрытия обратно внутри выбранных полос Bollinger в диапазоне.",
    "trend_momentum": "Ждать первого пересечения сохранённого порога импульса ATR по направлению трендовой EMA.",
    "inside_bar_breakout": "Ждать закрытия за внутренним баром в направлении трендовой EMA.",
    "volatility_expansion": "Ждать закрытия за предыдущим каналом с расширением тела относительно предыдущего ATR.",
}


def _text(value, name, *, maximum=256, optional=False):
    if value is None and optional:
        return ""
    if not isinstance(value, str) or len(value) > maximum:
        raise ValueError(f"{name}: требуется строка длиной до {maximum} символов")
    return value.strip()


def _number(value, name, minimum, maximum):
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name}: требуется конечное число, не boolean")
    result = float(value)
    if not math.isfinite(result) or not minimum <= result <= maximum:
        raise ValueError(f"{name}: число вне допустимого диапазона")
    return result


def _stamp(value, name):
    if not isinstance(value, str) or len(value) > 40:
        raise ValueError(f"{name}: требуется ISO дата UTC с Z или +00:00")
    try:
        return utc_datetime(value)
    except ValueError:
        raise ValueError(f"{name}: требуется ISO дата UTC с Z или +00:00") from None


def _iso(value):
    return value.isoformat(timespec="microseconds" if value.microsecond else "seconds").replace("+00:00", "Z")


def _price(value):
    return float(f"{value:.12g}")


def _context(payload, decision, warnings):
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        raise ValueError("context должен быть объектом")
    macro = payload.get("macro_cycle", "unknown")
    if not isinstance(macro, str) or macro not in _MACRO_CYCLES:
        raise ValueError("macro_cycle: unknown, expansion, slowdown, recession или recovery")
    macro_source = _text(payload.get("macro_source"), "macro_source", optional=True)
    if macro != "unknown":
        warnings.append("Макроцикл указан вручную; это качественная гипотеза, а не проверенный фильтр стратегии.")
    else:
        warnings.append("Макроцикл неизвестен; программа не получает макроэкономический поток.")

    supplied_sentiment = payload.get("sentiment")
    sentiment = {"state": "unknown", "score": None, "label": "unknown",
                 "observed_at": None, "source": None, "confirmed": False}
    if supplied_sentiment is not None:
        if not isinstance(supplied_sentiment, dict):
            raise ValueError("sentiment должен быть объектом")
        if supplied_sentiment:
            confirmed = supplied_sentiment.get("confirmed", False)
            if not isinstance(confirmed, bool):
                raise ValueError("sentiment.confirmed: требуется boolean")
            score = _number(supplied_sentiment.get("score"), "sentiment.score", -1, 1)
            observed = _stamp(supplied_sentiment.get("observed_at"), "sentiment.observed_at")
            source = _text(supplied_sentiment.get("source", ""), "sentiment.source")
            age = (decision - observed).total_seconds()
            sentiment.update(observed_at=_iso(observed), source=source or None, confirmed=confirmed)
            if age < 0:
                sentiment["state"] = "future_not_known"
                warnings.append("Настроения с будущим observed_at исключены из решения.")
            elif age > 24 * 3600:
                sentiment["state"] = "stale"
                warnings.append("Наблюдение настроений старше 24 часов; считать его текущим нельзя.")
            elif not confirmed or not source:
                sentiment["state"] = "unconfirmed"
                warnings.append("Настроения не подтверждены или не имеют источника.")
            else:
                sentiment.update(state="manual_confirmed", score=score,
                                 label="positive" if score > 0.2 else "negative" if score < -0.2 else "neutral")
                warnings.append("Настроения подтверждены пользователем; их влияние на доходность этой стратегии не тестировалось.")
    if sentiment["state"] == "unknown":
        warnings.append("Настроения неизвестны; программа не выдумывает оценку участников рынка.")

    supplied_news = payload.get("news")
    news_state = "unknown"
    news_source = None
    observed_news = None
    known_events = []
    blackout = []
    if supplied_news is not None:
        if not isinstance(supplied_news, dict):
            raise ValueError("news должен быть объектом")
        confirmed = supplied_news.get("confirmed", False)
        if not isinstance(confirmed, bool):
            raise ValueError("news.confirmed: требуется boolean")
        news_source = _text(supplied_news.get("source", ""), "news.source") or None
        observed_value = supplied_news.get("observed_at")
        observed_news = _stamp(observed_value, "news.observed_at") if observed_value is not None else None
        events = supplied_news.get("events", [])
        if not isinstance(events, list) or len(events) > 200:
            raise ValueError("news.events: список максимум из 200 событий")
        ignored = 0
        for index, event in enumerate(events):
            if not isinstance(event, dict):
                raise ValueError("Каждое news.events должно быть объектом")
            stamp = _stamp(event.get("time"), f"news.events[{index}].time")
            known = _stamp(event.get("known_at"), f"news.events[{index}].known_at")
            impact = event.get("impact")
            if not isinstance(impact, str) or impact not in _IMPACTS:
                raise ValueError("news.events.impact: high, medium или low")
            title = _text(event.get("title", ""), "news.events.title", maximum=512)
            currency = _text(event.get("currency", ""), "news.events.currency", maximum=16).upper()
            if known > decision:
                ignored += 1
                continue
            item = {"time": _iso(stamp), "known_at": _iso(known), "impact": impact,
                    "title": title, "currency": currency}
            known_events.append(item)
            if impact == "high" and -30 * 60 <= (decision - stamp).total_seconds() <= 15 * 60:
                blackout.append(item)
        if ignored:
            warnings.append(f"События, ещё не известные в момент решения, исключены: {ignored}.")
        calendar_fresh = observed_news is not None and 0 <= (decision - observed_news).total_seconds() <= 6 * 3600
        if confirmed and news_source and calendar_fresh:
            news_state = "blackout" if blackout else "checked_no_blackout"
        elif confirmed:
            warnings.append("Проверка календаря требует источника и observed_at не старше 6 часов, без будущей даты.")
        if blackout and news_state == "unknown":
            warnings.append("В неподтверждённом календаре есть важное событие возле решения; уточните календарь.")
    if news_state == "unknown":
        warnings.append("Новостной календарь неизвестен или не подтверждён; отсутствие события в списке не доказывает отсутствие новостей.")
    else:
        if supplied_news.get("generation") == "provider":
            warnings.append("Использован свежий снимок календаря поставщика; полнота событий не установлена. Общее окно -30/+15 минут не заменяет правила фирмы.")
        else:
            warnings.append("Календарь подтверждён вручную; поток обновлений отсутствует. Общее окно -30/+15 минут не заменяет правила фирмы.")
    return {"regime": "unknown", "macro_cycle": macro, "sentiment": sentiment,
            "news_state": news_state, "news_observed_at": _iso(observed_news) if observed_news else None,
            "news_generation": "provider" if isinstance(supplied_news, dict) and supplied_news.get("generation") == "provider" else "manual" if supplied_news else "unknown",
            "news_events": known_events, "news_blackout_events": blackout,
            "sources": {"macro_cycle": macro_source or ("manual" if macro != "unknown" else None),
                        "sentiment": sentiment["source"], "news": news_source,
                        "prices": "research_snapshot"},
            "policy": "Context is planning only; macro/sentiment/news filters are not a tested edge"}


def build_setup(research: dict, context: dict | None = None, now: datetime | None = None) -> dict:
    """Return a paper plan; only the frozen eligible candidate can supply levels.

    Bar time is its opening time. A signal becomes observable at open+timeframe;
    the next expected closed candle expires it. No market calendar is inferred.
    """
    if not isinstance(research, dict):
        raise ValueError("research должен быть объектом")
    decision = datetime.now(timezone.utc) if now is None else now
    if not isinstance(decision, datetime) or decision.tzinfo is None or decision.utcoffset() is None:
        raise ValueError("now должен быть datetime с часовым поясом")
    decision = decision.astimezone(timezone.utc)
    warnings = ["Это план для бумажной проверки. Он не разрешает реальный ордер и не гарантирует прибыль.",
                "Фактический вход следующего бара, спред и риск должны отдельно пройти чекер счёта."]
    normalized_context = _context(context, decision, warnings)
    data = research.get("data") if isinstance(research.get("data"), dict) else {}
    signal = research.get("latest_signal") if isinstance(research.get("latest_signal"), dict) else {}
    market = research.get("market_context") if isinstance(research.get("market_context"), dict) else {}
    config = research.get("config") if isinstance(research.get("config"), dict) else {}
    rules = research.get("profile_rules")
    if not isinstance(rules, dict):
        rules = config.get("prop_profile") if isinstance(config.get("prop_profile"), dict) else {}
    chosen = research.get("selected_strategy")
    strategy_id = chosen or signal.get("strategy_id") or research.get("training_candidate")
    if not isinstance(strategy_id, str) or strategy_id not in _CATALOG or strategy_id == "buy_hold":
        strategy_id = None
    strategies = research.get("strategies")
    strategies = strategies if isinstance(strategies, list) else []
    candidate = next((item for item in strategies if isinstance(item, dict) and item.get("id") == chosen), None)
    symbol = str(data.get("symbol") or signal.get("symbol") or "unknown")[:32]
    regime = signal.get("regime")
    normalized_context["regime"] = regime if regime in _REGIMES else "unknown"
    normalized_context["sources"]["prices"] = "synthetic_demo" if data.get("source") == "demo" else "imported_csv_snapshot" if data.get("source") == "csv" else "unknown_snapshot"
    trigger = _TRIGGERS.get(strategy_id, "Сначала исследовать реальные данные и получить прошедшего проверки кандидата.")
    result = {"status": "wait", "symbol": symbol, "strategy_id": strategy_id, "direction": "wait",
              "entry_zone": {"low": None, "high": None, "trigger": trigger}, "stop_loss": None,
              "take_profit_zone": {"low": None, "high": None, "target": None},
              "invalidation_zone": {"low": None, "high": None},
              "invalidation_conditions": ["Цена пересекла исходный стоп: идея отменена; стоп не расширять.",
                                          "Рыночный режим сменился: заново оценить кандидата без подбора по будущей доходности.",
                                          "Закрылся следующий бар или котировки устарели: пересчитать план.",
                                          "Началось окно важных новостей или нарушены правила счёта: отменить вход."],
              "context": normalized_context, "reasons": [], "warnings": warnings,
              "reference_time": None, "reference_close_time": None, "decision_time": _iso(decision),
              "expires_at": None, "rr": None, "planning_only": True, "can_trade": False,
              "execution_basis": "Original backtest uses next-bar open; displayed entry zone is a review tolerance, not a tested fill model"}
    blockers = []
    if data.get("source") == "demo":
        blockers.append("Синтетические данные: реальный сетап и прибыльный edge не установлены.")
    elif data.get("source") != "csv":
        blockers.append("Происхождение рыночных данных не подтверждено; нужен реальный CSV.")
    if chosen is None or strategy_id is None or candidate is None:
        blockers.append("Обученный кандидат не прошёл проверку на отложенной истории; замена победителем теста запрещена.")
    elif candidate.get("eligible") is not True or candidate.get("baseline") is True or candidate.get("training_winner") is False:
        blockers.append("Выбранная стратегия не является допущенным замороженным кандидатом обучения.")
    if chosen and signal.get("strategy_id") != chosen:
        blockers.append("Последний сигнал относится к другой стратегии.")
    if candidate and isinstance(candidate.get("rule_replay"), dict) and candidate["rule_replay"].get("status") != "pass":
        blockers.append("Историческая проверка правил счёта не пройдена.")
    if rules.get("status") != "user_verified":
        warnings.append("Профиль правил учебный или не подтверждён пользователем; актуальные условия фирмы не установлены.")
    if rules.get("news_allowed") is False and normalized_context["news_state"] == "unknown":
        blockers.append("Фирма запрещает торговлю вокруг новостей, но текущий календарь не подтверждён.")
    elif rules.get("news_allowed") is None:
        warnings.append("Правило торговли на новостях неизвестно; подтвердите действующие условия фирмы.")
    if normalized_context["news_state"] == "blackout":
        blockers.append("Окно важных новостей: консервативная политика планировщика блокирует новый вход (-30/+15 минут).")

    bar = market.get("last_bar") if isinstance(market.get("last_bar"), dict) else {}
    price = atr = None
    try:
        opening = _stamp(bar.get("time"), "market_context.last_bar.time")
        minutes = _number(market.get("timeframe_minutes", data.get("timeframe_minutes")), "timeframe_minutes", 1 / 60, 10080)
        interval = timedelta(minutes=minutes)
        closed = opening + interval
        expires = closed + interval
        age = (decision - closed).total_seconds() / 60
        freshness_limit = max(3 * minutes, 15)
        result.update(reference_time=_iso(opening), reference_close_time=_iso(closed), expires_at=_iso(expires))
        normalized_context.update(price_age_minutes=round(age, 4), freshness_limit_minutes=freshness_limit,
                                  price_state="fresh" if 0 <= age <= freshness_limit else "future_unclosed" if age < 0 else "stale")
        if age < 0:
            blockers.append("Последний бар ещё не закрылся; его сигнал недоступен в момент решения.")
        elif age > freshness_limit:
            blockers.append("Котировки устарели: загрузите свежие закрытые бары.")
        elif decision >= expires:
            normalized_context["price_state"] = "expired_next_bar"
            blockers.append("Ожидаемый следующий бар уже закрылся: этот сигнал истёк, нужен новый снимок.")
        price = _number(bar.get("close"), "last_bar.close", 1e-12, 1e12)
        atr = _number(market.get("atr14"), "atr14", 1e-12, 1e12)
        reference = _number(signal.get("reference_price"), "latest_signal.reference_price", 1e-12, 1e12)
        if _stamp(signal.get("reference_time"), "latest_signal.reference_time") != opening or not math.isclose(price, reference, rel_tol=1e-9, abs_tol=1e-12):
            blockers.append("Цена или время сигнала не совпадают с последним баром исследования.")
    except (ValueError, OverflowError):
        normalized_context["price_state"] = "unknown"
        blockers.append("Нет корректного причинного снимка цены, ATR и таймфрейма; числовые зоны не строятся.")
    if data.get("irregular_intervals"):
        warnings.append("Интервалы баров нерегулярны; закрытие и срок действия предполагают типичный таймфрейм, проверьте сессию инструмента.")
    warnings.append("Биржевые сессии, праздники и задержка живой котировки не известны; для дневных баров календарь проверить отдельно.")

    direction = signal.get("direction")
    # A waiting strategy never receives invented entry, stop, or target levels.
    if direction not in ("long", "short"):
        result["status"] = "blocked" if blockers else "wait"
        result["reasons"] = blockers + ["На последнем закрытом баре нет нового сигнала; ждать условие выбранной стратегии."]
        return result
    if blockers:
        result["status"] = "blocked"
        result["reasons"] = blockers
        return result
    try:
        stop = _number(signal.get("stop"), "latest_signal.stop", 1e-12, 1e12)
        target = _number(signal.get("target"), "latest_signal.target", 1e-12, 1e12)
        entry_low, entry_high = price - 0.1 * atr, price + 0.1 * atr
        target_low, target_high = target - 0.1 * atr, target + 0.1 * atr
        invalid_low, invalid_high = stop - 0.05 * atr, stop + 0.05 * atr
        ordered = (0 < invalid_low <= stop < entry_low <= price <= entry_high < target_low <= target <= target_high
                   if direction == "long" else
                   0 < target_low <= target <= target_high < entry_low <= price <= entry_high < stop <= invalid_high)
        if not ordered or invalid_low <= 0 or any(not math.isfinite(number) for number in (entry_low, entry_high, target_low, target_high, invalid_low, invalid_high)):
            raise ValueError("invalid price ordering")
        risk = abs(price - stop)
        rr = abs(target - price) / risk
        if not math.isfinite(rr) or rr <= 0:
            raise ValueError("invalid risk reward")
    except (ValueError, ZeroDivisionError, TypeError):
        result["status"] = "blocked"
        result["reasons"] = ["Исходные стоп/цель не образуют корректный план относительно цены и ATR; менять их без повторного теста нельзя."]
        return result
    result.update(status="paper_review", direction=direction, stop_loss=stop, rr=round(rr, 6),
                  entry_zone={"low": _price(entry_low), "high": _price(entry_high),
                              "trigger": "Закрытый бар дал сигнал; проверить фактический следующий open и цену в зоне ±0.1 ATR, затем бумажный чекер."},
                  take_profit_zone={"low": _price(target_low), "high": _price(target_high), "target": target},
                  invalidation_zone={"low": _price(invalid_low), "high": _price(invalid_high)},
                  reasons=["Замороженный кандидат прошёл исторические критерии допуска; текущий закрытый бар дал сигнал.",
                           "Стоп и цель сохранены из исходного сигнала; зоны вокруг них служат визуальному обзору."])
    observed_sentiment = normalized_context["sentiment"]["score"]
    if observed_sentiment is not None and (direction == "long" and observed_sentiment < -0.2 or direction == "short" and observed_sentiment > 0.2):
        warnings.append("Направление против подтверждённых вручную настроений: проверить гипотезу; доходность такого фильтра не установлена.")
    allowed_regimes = _CATALOG[strategy_id]["regimes"]
    if regime not in allowed_regimes:
        warnings.append("Текущий режим вне обычного описания семейства; режимные срезы описательные и не разрешают переключать стратегию по результату теста.")
    return result
