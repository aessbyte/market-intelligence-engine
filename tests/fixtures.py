"""Synthetic data only. These prices were never observed on Binance."""

from typing import Any

from market_intelligence.binance import BinanceClient
from market_intelligence.models import Interval

CUTOFF = 86_400_000 * 1000


def rows(
    interval: Interval, count: int = 250, slope: float = 0.1, cutoff: int = CUTOFF
) -> list[list[Any]]:
    step = interval.milliseconds
    start = cutoff // step * step - count * step
    result = []
    for i in range(count):
        close = 100 + slope * i
        result.append(
            [
                start + i * step,
                str(close),
                str(close + 1),
                str(close - 1),
                str(close),
                "10",
                start + (i + 1) * step - 1,
                str(close * 10),
                5,
                "5",
                str(close * 5),
                "0",
            ]
        )
    return result


class FakeBinance:
    def __init__(self, slope: float = 0.2) -> None:
        self.slope = slope
        self.calls: list[tuple[str, dict[str, str | int]]] = []

    def get(self, path: str, params: dict[str, str | int]) -> Any:
        self.calls.append((path, params.copy()))
        if path == "/api/v3/time":
            return {"serverTime": CUTOFF}
        if path == "/api/v3/exchangeInfo":
            return {
                "symbols": [
                    {"symbol": params["symbol"], "status": "TRADING", "isSpotTradingAllowed": True}
                ]
            }
        interval = Interval(params["interval"])
        start, end, limit = int(params["startTime"]), int(params["endTime"]), int(params["limit"])
        # Fixed origin makes paginated observations stable across request boundaries.
        data = rows(interval, 5000, self.slope)
        for i, row in enumerate(data):
            price = 1000 + self.slope * (i - 4750)
            row[1], row[2], row[3], row[4] = str(price), str(price + 1), str(price - 1), str(price)
            row[7], row[10] = str(price * 10), str(price * 5)
        return [r for r in data if start <= r[0] <= end][:limit]


def snapshot(slope: float = 0.2) -> dict[str, Any]:
    return BinanceClient(FakeBinance(slope)).snapshot("BTCUSDT", source="simulated")
