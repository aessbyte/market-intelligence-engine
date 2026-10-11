"""Clearly synthetic candles, no claim of observed Binance prices."""

from market_intelligence.models import Candle, Interval
from market_intelligence.wyckoff import WyckoffConfig

INTERVAL = Interval.H1
STEP = INTERVAL.milliseconds
SHORT_RANGE = WyckoffConfig(
    range_lookback=10, touch_tolerance=0.15, min_inside_fraction=0.5, max_efficiency=0.5
)


def prices(values: list[float], interval: Interval = INTERVAL) -> tuple[Candle, ...]:
    step = interval.milliseconds
    return tuple(
        Candle(i * step, (i + 1) * step - 1, p, p + 1, p - 1, p, 10, 10 * p, 5)
        for i, p in enumerate(values)
    )


def range_candles(tail: list[tuple[float, float, float, float, float]]) -> tuple[Candle, ...]:
    result = list(prices([100, 104, 100, 96] * 3))
    for o, h, low, close, volume in tail:
        i = len(result)
        result.append(
            Candle(
                i * STEP,
                (i + 1) * STEP - 1,
                o,
                h,
                low,
                close,
                volume,
                volume * close,
                5 if volume > 0 else 0,
            )
        )
    return tuple(result)


SPRING = [(98, 101, 93, 99, 10), (99, 103, 98, 102, 10)]
UPTHRUST = [(102, 107, 99, 101, 10), (101, 102, 97, 98, 10)]
SOS_LPS = [
    (104, 109, 103, 108, 20),
    (108, 110, 107, 109, 15),
    (107, 108, 104.5, 106, 8),
    (106, 110, 105, 109, 11),
]
SOW_LPSY = [(96, 97, 91, 92, 20), (92, 93, 90, 91, 15), (93, 95.5, 92, 94, 8), (94, 95, 90, 91, 11)]
STRUCTURE_PRICES = [
    100,
    105,
    110,
    105,
    100,
    104,
    112,
    107,
    102,
    108,
    114,
    116,
    113,
    111,
    104,
    98,
    97,
    99,
    100,
]
