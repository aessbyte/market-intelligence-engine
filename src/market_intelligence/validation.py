"""Fail closed on invalid observed history; never sort, fill gaps or interpolate."""

import math
from typing import Any

from .models import Candle, Interval, MarketError, Validation


def parse_klines(rows: Any) -> tuple[Candle, ...]:
    if not isinstance(rows, list):
        raise MarketError("Binance klines must be an array")
    candles = []
    for index, row in enumerate(rows):
        try:
            if not isinstance(row, list) or len(row) != 12:
                raise ValueError("expected 12 fields")
            for position in (0, 6, 8):
                if isinstance(row[position], bool) or not isinstance(row[position], int):
                    raise ValueError("timestamps and trade counts must be integers")
            candles.append(
                Candle(
                    row[0],
                    row[6],
                    float(row[1]),
                    float(row[2]),
                    float(row[3]),
                    float(row[4]),
                    float(row[5]),
                    float(row[7]),
                    row[8],
                )
            )
        except (ValueError, TypeError, OverflowError) as exc:
            raise MarketError(f"Malformed kline at row {index}: {exc}") from exc
    return tuple(candles)


def validate(
    candles: tuple[Candle, ...], interval: Interval, as_of_ms: int, minimum: int = 100
) -> tuple[tuple[Candle, ...], Validation]:
    # Strictly earlier than cutoff. At the boundary (inclusive close time), exclude.
    closed = tuple(c for c in candles if c.close_time_ms < as_of_ms)
    errors = []
    step = interval.milliseconds
    for i, candle in enumerate(closed):
        if candle.open_time_ms < 0 or candle.open_time_ms % step:
            errors.append(f"row {i}: unaligned UTC open timestamp")
        if candle.close_time_ms != candle.open_time_ms + step - 1:
            errors.append(f"row {i}: invalid close timestamp")
        if i and candle.open_time_ms - closed[i - 1].open_time_ms != step:
            errors.append(f"row {i}: gap, duplicate or unordered timestamp")
        values = (
            candle.open,
            candle.high,
            candle.low,
            candle.close,
            candle.volume,
            candle.quote_volume,
        )
        if not all(math.isfinite(value) for value in values):
            errors.append(f"row {i}: non-finite OHLCV")
        elif (
            min(values[:4]) <= 0
            or candle.high < max(candle.open, candle.close)
            or candle.low > min(candle.open, candle.close)
            or candle.low > candle.high
            or min(candle.volume, candle.quote_volume) < 0
            or candle.trades < 0
        ):
            errors.append(f"row {i}: invalid price range, volume or trades")
    if len(closed) < minimum:
        errors.append(f"insufficient closed history: {len(closed)} < {minimum}")
    expected_last_open = (as_of_ms // step - 1) * step
    if closed and closed[-1].open_time_ms != expected_last_open:
        errors.append("stale history: latest fully closed interval unavailable")
    report = Validation(
        not errors,
        len(candles),
        len(closed),
        len(candles) - len(closed),
        tuple(errors),
        closed[0].open_time_ms if closed else None,
        closed[-1].close_time_ms if closed else None,
    )
    return closed, report
