"""Small transparent, fixed strategy family and causal indicators.

Signals are evaluated only at a fully closed bar. Nothing in these functions
reads the next bar, and a signal is not a filled trade or a promise of edge.
"""

from __future__ import annotations

import math
from collections import deque
from copy import deepcopy

_STRATEGIES = [
    {"id": "ema_pullback", "name": "Откат в тренде EMA", "description": "Возврат через быструю EMA в направлении медленной EMA.", "regimes": ["trend"], "params": {"fast": 12, "slow": 48, "atr_period": 14, "stop_atr": 1.7, "reward_risk": 1.8, "max_hold_bars": 36}, "alternatives": [{"fast": 20, "slow": 60}]},
    {"id": "donchian_breakout", "name": "Пробой канала Donchian", "description": "Закрытие за экстремумом предыдущих баров; текущий бар не входит в канал.", "regimes": ["trend", "volatile"], "params": {"lookback": 20, "atr_period": 14, "stop_atr": 2.0, "reward_risk": 2.0, "max_hold_bars": 72}, "alternatives": [{"lookback": 40}]},
    {"id": "rsi_reversion", "name": "Возврат RSI в диапазоне", "description": "Возврат RSI из перепроданности/перекупленности при низкой направленности цены.", "regimes": ["range"], "params": {"rsi_period": 14, "lower": 30, "upper": 70, "efficiency_period": 20, "max_efficiency": 0.4, "atr_period": 14, "stop_atr": 1.4, "reward_risk": 1.4, "max_hold_bars": 24}, "alternatives": [{"lower": 25, "upper": 75}]},
    {"id": "bollinger_reversion", "name": "Возврат в полосы Bollinger", "description": "Закрытие обратно внутри полос в спокойном диапазоне; стандартное отклонение генеральной совокупности.", "regimes": ["range"], "params": {"lookback": 20, "deviation": 2.0, "efficiency_period": 20, "max_efficiency": 0.4, "atr_period": 14, "stop_atr": 1.5, "reward_risk": 1.5, "max_hold_bars": 24}, "alternatives": [{"deviation": 2.5}]},
    {"id": "trend_momentum", "name": "Ускорение тренда", "description": "Первое пересечение импульсом порога 2 ATR в направлении EMA 50.", "regimes": ["trend", "volatile"], "params": {"lookback": 12, "momentum_atr": 2.0, "trend_period": 50, "atr_period": 14, "stop_atr": 2.0, "reward_risk": 2.0, "max_hold_bars": 48}, "alternatives": [{"lookback": 24}]},
    {"id": "inside_bar_breakout", "name": "Пробой внутреннего бара", "description": "Пробой внутреннего бара закрытием в направлении EMA 50.", "regimes": ["trend", "transition"], "params": {"trend_period": 50, "atr_period": 14, "stop_atr": 1.4, "reward_risk": 1.8, "max_hold_bars": 24}, "alternatives": [{"stop_atr": 1.8}]},
    {"id": "volatility_expansion", "name": "Расширение волатильности", "description": "Тело бара больше предыдущего ATR и закрытие за предыдущим каналом.", "regimes": ["volatile", "trend"], "params": {"lookback": 10, "body_atr": 1.4, "trend_period": 50, "atr_period": 14, "stop_atr": 2.0, "reward_risk": 1.8, "max_hold_bars": 36}, "alternatives": [{"body_atr": 1.8}]},
    {"id": "buy_hold", "name": "Buy & hold · ориентир", "description": "Ориентир с длинной позицией и экспозицией до 1×, с теми же торговыми издержками.", "regimes": ["baseline"], "params": {"baseline": True}, "alternatives": []},
]
_BY_ID = {strategy["id"]: strategy for strategy in _STRATEGIES}


def catalog() -> list[dict]:
    return [{key: deepcopy(value) for key, value in strategy.items() if key != "alternatives"} for strategy in _STRATEGIES]


def parameter_candidates(strategy_id: str) -> list[dict]:
    if strategy_id not in _BY_ID:
        raise ValueError(f"unknown strategy: {strategy_id}")
    strategy = _BY_ID[strategy_id]
    return [deepcopy(strategy["params"])] + [{**deepcopy(strategy["params"]), **override} for override in strategy["alternatives"]]


def ema(values: list[float], period: int) -> list[float]:
    alpha = 2.0 / (period + 1.0)
    result = []
    current = values[0] if values else 0.0
    for value in values:
        current = alpha * value + (1.0 - alpha) * current
        result.append(current)
    return result


def atr(bars: list[dict], period: int = 14) -> list[float | None]:
    ranges = [max(bar["high"] - bar["low"], abs(bar["high"] - bars[i - 1]["close"]), abs(bar["low"] - bars[i - 1]["close"])) if i else bar["high"] - bar["low"] for i, bar in enumerate(bars)]
    result = [None] * len(bars)
    if len(bars) >= period:
        current = sum(ranges[:period]) / period
        result[period - 1] = current
        for i in range(period, len(bars)):
            current = ((period - 1) * current + ranges[i]) / period
            result[i] = current
    return result


def rsi(values: list[float], period: int = 14) -> list[float | None]:
    result = [None] * len(values)
    if len(values) <= period:
        return result
    diffs = [values[i] - values[i - 1] for i in range(1, len(values))]
    gain = sum(max(0.0, diff) for diff in diffs[:period]) / period
    loss = sum(max(0.0, -diff) for diff in diffs[:period]) / period

    def value():
        return 50.0 if gain == loss == 0 else 100.0 if loss == 0 else 100.0 - 100.0 / (1.0 + gain / loss)

    result[period] = value()
    for i in range(period + 1, len(values)):
        gain = (gain * (period - 1) + max(0.0, diffs[i - 1])) / period
        loss = (loss * (period - 1) + max(0.0, -diffs[i - 1])) / period
        result[i] = value()
    return result


def efficiency(values: list[float], period: int = 20) -> list[float | None]:
    result = [None] * len(values)
    total = 0.0
    moves = deque()
    for i in range(1, len(values)):
        change = abs(values[i] - values[i - 1])
        moves.append(change)
        total += change
        if len(moves) > period:
            total -= moves.popleft()
        if len(moves) == period:
            result[i] = abs(values[i] - values[i - period]) / total if total > 1e-14 else 0.0
    return result


def rolling_bands(values: list[float], period: int, deviations: float = 2.0) -> tuple[list, list, list]:
    # Small windows make a stable direct two-pass variance inexpensive; the
    # subtraction-of-squares formula loses precision for high-price instruments.
    middles, lowers, uppers = ([None] * len(values) for _ in range(3))
    for i in range(period - 1, len(values)):
        window = values[i - period + 1:i + 1]
        mean = sum(window) / period
        deviation = math.sqrt(sum((item - mean) ** 2 for item in window) / period) * deviations
        middles[i], lowers[i], uppers[i] = mean, mean - deviation, mean + deviation
    return middles, lowers, uppers


def regimes(bars: list[dict]) -> list[str]:
    closes = [bar["close"] for bar in bars]
    ratios = efficiency(closes, 20)
    ranges = atr(bars, 14)
    result = []
    for i in range(len(bars)):
        previous = [value for value in ranges[max(0, i - 50):i] if value is not None]
        typical = sum(previous) / len(previous) if previous else None
        if ranges[i] is not None and typical is not None and ranges[i] > typical * 1.35:
            regime = "volatile"
        elif ratios[i] is not None and ratios[i] >= 0.35:
            regime = "trend"
        elif ratios[i] is not None and ratios[i] < 0.22:
            regime = "range"
        else:
            regime = "transition"
        result.append(regime)
    return result


def signals_for(bars: list[dict], strategy_id: str, params: dict | None = None, *, regime_labels: list[str] | None = None) -> list[dict | None]:
    """Return one causal closed-bar observation per input bar.

    The backtester executes observation i only at opening i+1. ATR comes from
    observation i, so neither next-bar volatility nor its close sizes a trade.
    """
    if strategy_id not in _BY_ID:
        raise ValueError(f"unknown strategy: {strategy_id}")
    settings = {**_BY_ID[strategy_id]["params"], **(params or {})}
    n = len(bars)
    signals = [None] * n
    if not n:
        return signals
    labels = regime_labels or regimes(bars)
    if strategy_id == "buy_hold":
        return [{"direction": 1, "atr": None, "regime": labels[i]} for i in range(n)]
    closes = [bar["close"] for bar in bars]
    ranges = atr(bars, settings["atr_period"])
    warmup = max(60, settings.get("slow", 0) + 3, settings.get("lookback", 0) + 2)
    fast = ema(closes, settings.get("fast", 12)) if strategy_id == "ema_pullback" else None
    slow = ema(closes, settings.get("slow", 48)) if strategy_id == "ema_pullback" else None
    trend = ema(closes, settings.get("trend_period", 50)) if strategy_id in ("trend_momentum", "inside_bar_breakout", "volatility_expansion") else None
    strengths = rsi(closes, settings.get("rsi_period", 14)) if strategy_id == "rsi_reversion" else None
    efficiencies = efficiency(closes, settings.get("efficiency_period", 20)) if strategy_id in ("rsi_reversion", "bollinger_reversion") else None
    bands = rolling_bands(closes, settings["lookback"], settings["deviation"]) if strategy_id == "bollinger_reversion" else None
    for i in range(warmup, n):
        if ranges[i] is None or ranges[i] <= 0:
            continue
        direction = 0
        if strategy_id == "ema_pullback":
            if fast[i] > slow[i] and slow[i] > slow[i - 3] and closes[i - 1] <= fast[i - 1] and closes[i] > fast[i]:
                direction = 1
            elif fast[i] < slow[i] and slow[i] < slow[i - 3] and closes[i - 1] >= fast[i - 1] and closes[i] < fast[i]:
                direction = -1
        elif strategy_id == "donchian_breakout":
            previous = bars[i - settings["lookback"]:i]
            if closes[i] > max(bar["high"] for bar in previous):
                direction = 1
            elif closes[i] < min(bar["low"] for bar in previous):
                direction = -1
        elif strategy_id == "rsi_reversion":
            if efficiencies[i] is not None and efficiencies[i] < settings["max_efficiency"]:
                if strengths[i - 1] <= settings["lower"] < strengths[i]:
                    direction = 1
                elif strengths[i - 1] >= settings["upper"] > strengths[i]:
                    direction = -1
        elif strategy_id == "bollinger_reversion":
            _, lower, upper = bands
            if efficiencies[i] is not None and efficiencies[i] < settings["max_efficiency"]:
                if closes[i - 1] <= lower[i - 1] and closes[i] > lower[i]:
                    direction = 1
                elif closes[i - 1] >= upper[i - 1] and closes[i] < upper[i]:
                    direction = -1
        elif strategy_id == "trend_momentum":
            current = closes[i] - closes[i - settings["lookback"]]
            previous = closes[i - 1] - closes[i - 1 - settings["lookback"]]
            threshold = settings["momentum_atr"] * ranges[i]
            previous_threshold = settings["momentum_atr"] * ranges[i - 1]
            if current > threshold and previous <= previous_threshold and closes[i] > trend[i]:
                direction = 1
            elif current < -threshold and previous >= -previous_threshold and closes[i] < trend[i]:
                direction = -1
        elif strategy_id == "inside_bar_breakout":
            mother, inside = bars[i - 2], bars[i - 1]
            if inside["high"] < mother["high"] and inside["low"] > mother["low"]:
                if closes[i] > inside["high"] and closes[i] > trend[i]:
                    direction = 1
                elif closes[i] < inside["low"] and closes[i] < trend[i]:
                    direction = -1
        elif strategy_id == "volatility_expansion":
            if abs(closes[i] - bars[i]["open"]) > settings["body_atr"] * ranges[i - 1]:
                previous = bars[i - settings["lookback"]:i]
                if closes[i] > max(bar["high"] for bar in previous) and closes[i] > trend[i]:
                    direction = 1
                elif closes[i] < min(bar["low"] for bar in previous) and closes[i] < trend[i]:
                    direction = -1
        if direction:
            signals[i] = {"direction": direction, "atr": ranges[i], "regime": labels[i]}
    return signals
