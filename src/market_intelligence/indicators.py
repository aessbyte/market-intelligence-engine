"""Causal indicators, explicit seeds; no centered windows or future observations."""

import math
import statistics

from .models import Candle, Features


def ema(values: list[float], period: int) -> list[float]:
    """Seed with first period SMA; output index zero corresponds to period-1."""
    if len(values) < period:
        raise ValueError("insufficient EMA history")
    result = [statistics.fmean(values[:period])]
    alpha = 2.0 / (period + 1)
    for value in values[period:]:
        result.append(alpha * value + (1 - alpha) * result[-1])
    return result


def wilder(values: list[float], period: int) -> float:
    if len(values) < period:
        raise ValueError("insufficient Wilder history")
    value = statistics.fmean(values[:period])
    for observation in values[period:]:
        value = ((period - 1) * value + observation) / period
    return value


def calculate(candles: tuple[Candle, ...]) -> Features:
    if len(candles) < 100:
        raise ValueError("indicators require 100 closed candles")
    closes = [c.close for c in candles]
    changes = [b - a for a, b in zip(closes, closes[1:])]
    gains = wilder([max(v, 0.0) for v in changes], 14)
    losses = wilder([max(-v, 0.0) for v in changes], 14)
    rsi = (
        50.0 if gains == losses == 0 else 100.0 if losses == 0 else 100 - 100 / (1 + gains / losses)
    )
    tr = [
        max(c.high - c.low, abs(c.high - prev.close), abs(c.low - prev.close))
        for prev, c in zip(candles, candles[1:])
    ]
    atr = wilder(tr, 14)
    ema20 = ema(closes, 20)
    ema50 = ema(closes, 50)[-1]
    mean = statistics.fmean(closes[-20:])
    sigma = statistics.pstdev(closes[-20:])
    returns = [math.log(b / a) for a, b in zip(closes[-21:], closes[-20:])]
    baseline_volume = statistics.fmean(c.volume for c in candles[-21:-1])
    travel = sum(abs(v) for v in changes[-20:])
    obv = sum(
        c.volume * (1 if change > 0 else -1 if change < 0 else 0)
        for c, change in zip(candles[1:], changes)
    )
    return Features(
        close=closes[-1],
        sma20=mean,
        ema20=ema20[-1],
        ema50=ema50,
        ema20_slope5_atr=(ema20[-1] - ema20[-6]) / (5 * atr) if atr else 0.0,
        ema_gap_atr=(ema20[-1] - ema50) / atr if atr else 0.0,
        rsi14=rsi,
        atr14=atr,
        atr_percent=100 * atr / closes[-1],
        realized_volatility20=statistics.pstdev(returns),
        bollinger_lower20=mean - 2 * sigma,
        bollinger_upper20=mean + 2 * sigma,
        volume_ratio20=candles[-1].volume / baseline_volume if baseline_volume else None,
        obv=obv,
        efficiency20=abs(closes[-1] - closes[-21]) / travel if travel else 0.0,
    )
