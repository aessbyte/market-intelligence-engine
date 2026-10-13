"""Offline browser-test server. Every candle is explicitly synthetic.

This script is a development test harness, never an automatic provider fallback.
It uses the production API, service, schemas and engine with an injected provider.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from market_intelligence.binance import BinanceClient  # noqa: E402
from market_intelligence.models import Interval, MarketError  # noqa: E402
from market_intelligence.web import create_app  # noqa: E402
from market_intelligence.web.config import WebConfig  # noqa: E402
from market_intelligence.web.service import AnalysisService  # noqa: E402

CUTOFF_MS = 1_791_676_800_000  # Fixed UTC boundary: reproducible synthetic fixture.
SYMBOLS = ("BTCUSDT", "SHORTUSDT", "FAILUSDT")


def symbol_info(symbol: str) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "status": "TRADING",
        "isSpotTradingAllowed": True,
        "baseAsset": symbol.removesuffix("USDT"),
        "quoteAsset": "USDT",
    }


def synthetic_rows(interval: Interval, count: int) -> list[list[Any]]:
    step = interval.milliseconds
    start = CUTOFF_MS - count * step
    rows: list[list[Any]] = []
    for index in range(count):
        price = (100.0, 104.0, 100.0, 96.0)[index % 4]
        open_price, high, low, close, volume = price, price + 1, price - 1, price, 10.0
        tail = [
            (104.0, 109.0, 103.0, 108.0, 20.0),
            (108.0, 110.0, 107.0, 109.0, 15.0),
            (107.0, 108.0, 104.5, 106.0, 8.0),
            (106.0, 110.0, 105.0, 109.0, 11.0),
        ]
        if count >= 100 and index >= count - len(tail):
            open_price, high, low, close, volume = tail[index - (count - len(tail))]
        rows.append(
            [
                start + index * step,
                str(open_price),
                str(high),
                str(low),
                str(close),
                str(volume),
                start + (index + 1) * step - 1,
                str(volume * close),
                5,
                str(volume / 2),
                str(volume * close / 2),
                "0",
            ]
        )
    return rows


class SyntheticTransport:
    def get(self, path: str, params: dict[str, str | int]) -> Any:
        if path == "/api/v3/time":
            return {"serverTime": CUTOFF_MS}
        if path == "/api/v3/exchangeInfo":
            exact = params.get("symbol")
            return {
                "symbols": [symbol_info(symbol) for symbol in SYMBOLS if not exact or symbol == exact]
            }
        raise AssertionError("Browser tests cannot access live endpoints")


class SyntheticBrowserProvider(BinanceClient):
    def __init__(self) -> None:
        super().__init__(SyntheticTransport())

    def snapshot(
        self,
        symbol: str,
        bars: int = 250,
        as_of_ms: int | None = None,
        source: str = "binance_public",
    ) -> dict[str, Any]:
        info = self.symbol_info(symbol)
        if symbol == "FAILUSDT":
            raise MarketError("temporary provider outage: synthetic failure test")
        count = 5 if symbol == "SHORTUSDT" else bars
        return {
            "snapshot_version": "1",
            "source": "simulated",
            "symbol": symbol,
            "as_of_ms": CUTOFF_MS,
            "server_time_ms": CUTOFF_MS,
            "requested_bars": bars,
            "endpoint": "https://data-api.binance.vision",
            "symbol_info": info,
            "klines": {interval.name: synthetic_rows(interval, count) for interval in Interval},
            "fetch_errors": {},
        }


def main() -> None:
    import uvicorn

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument(
        "--frontend-dist",
        type=Path,
        help="Serve an existing production build from the same ASGI application.",
    )
    args = parser.parse_args()
    frontend_dist = args.frontend_dist.resolve() if args.frontend_dist else None
    if frontend_dist is not None and not (frontend_dist / "index.html").is_file():
        parser.error("Frontend production build missing; run npm run build in frontend first.")
    config = WebConfig(
        frontend_dist=frontend_dist,
        cors_origins=("http://127.0.0.1:5174", "http://localhost:5174"),
        request_limit=120,
        read_request_limit=600,
        cache_seconds=300,
    )
    service = AnalysisService(config, client=SyntheticBrowserProvider())
    uvicorn.run(create_app(service=service), host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
