"""Public Binance spot endpoints only, injectable transport and bounded retries."""

import json
import re
import time
from collections.abc import Callable
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .models import Interval, MarketError

BASE_URLS = ("https://data-api.binance.vision", "https://api.binance.com")


class Transport(Protocol):
    def get(self, path: str, params: dict[str, str | int]) -> Any: ...


class PublicHTTP:
    def __init__(
        self,
        base_url: str = BASE_URLS[0],
        timeout: float = 15.0,
        retries: int = 2,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if base_url not in BASE_URLS or timeout <= 0 or not 0 <= retries <= 5:
            raise ValueError("invalid public transport configuration")
        self.base_url, self.timeout, self.retries, self.sleep = base_url, timeout, retries, sleep

    def get(self, path: str, params: dict[str, str | int]) -> Any:
        if path not in ("/api/v3/time", "/api/v3/exchangeInfo", "/api/v3/klines"):
            raise MarketError("Only allowlisted public GET endpoints are supported")
        request = Request(
            f"{self.base_url}{path}?{urlencode(params)}",
            headers={"User-Agent": "market-intelligence-engine/0.1.0"},
        )
        for attempt in range(self.retries + 1):
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    return json.loads(response.read())
            except HTTPError as exc:
                if (exc.code != 429 and exc.code < 500) or attempt == self.retries:
                    raise MarketError(f"Binance public API HTTP {exc.code} at {path}") from exc
                try:
                    delay = float(exc.headers.get("Retry-After", 2**attempt))
                except (ValueError, TypeError):
                    delay = float(2**attempt)
                self.sleep(max(0.0, min(delay, 30.0)))
            except (URLError, TimeoutError, OSError) as exc:
                if attempt == self.retries:
                    raise MarketError(f"Binance transport unavailable at {path}: {exc}") from exc
                self.sleep(float(2**attempt))
            except (ValueError, UnicodeError) as exc:
                raise MarketError(f"Invalid JSON from Binance at {path}") from exc
        raise MarketError("Retry budget exhausted")


def normalize_symbol(symbol: str) -> str:
    symbol = symbol.strip().upper()
    if not re.fullmatch(r"[A-Z0-9]{5,30}", symbol):
        raise MarketError("Symbol must be a Binance spot symbol, e.g. BTCUSDT")
    return symbol


class BinanceClient:
    def __init__(self, transport: Transport | None = None) -> None:
        self.transport = transport if transport is not None else PublicHTTP()

    def server_time(self) -> int:
        result = self.transport.get("/api/v3/time", {})
        if (
            not isinstance(result, dict)
            or type(result.get("serverTime")) is not int
            or result["serverTime"] <= 0
        ):
            raise MarketError("Invalid Binance server time")
        return int(result["serverTime"])

    def symbol_info(self, symbol: str) -> dict[str, Any]:
        result = self.transport.get("/api/v3/exchangeInfo", {"symbol": symbol})
        if not isinstance(result, dict) or not isinstance(result.get("symbols"), list):
            raise MarketError("Malformed Binance exchangeInfo")
        matches = [
            s for s in result["symbols"] if isinstance(s, dict) and s.get("symbol") == symbol
        ]
        if len(matches) != 1 or matches[0].get("status") != "TRADING":
            raise MarketError(f"{symbol} unavailable or not TRADING")
        if matches[0].get("isSpotTradingAllowed") is not True:
            raise MarketError(f"{symbol} is not enabled for spot trading")
        return dict(matches[0])

    def klines(self, symbol: str, interval: Interval, as_of_ms: int, bars: int = 250) -> list[Any]:
        if not 100 <= bars <= 5000:
            raise MarketError("bars must be between 100 and 5000")
        step = interval.milliseconds
        end = as_of_ms // step * step - 1
        start = max(0, end + 1 - bars * step)
        rows: list[Any] = []
        while start <= end and len(rows) < bars:
            page = self.transport.get(
                "/api/v3/klines",
                {
                    "symbol": symbol,
                    "interval": interval.value,
                    "startTime": start,
                    "endTime": end,
                    "limit": min(1000, bars - len(rows)),
                },
            )
            if not isinstance(page, list):
                raise MarketError("Malformed klines response")
            if not page:
                break
            if len(page) > min(1000, bars - len(rows)):
                raise MarketError("Klines response exceeds requested limit")
            try:
                if any(
                    not isinstance(r, list)
                    or len(r) != 12
                    or type(r[0]) is not int
                    or r[0] < start
                    or r[0] > end
                    for r in page
                ):
                    raise ValueError("invalid page timestamps")
                next_start = page[-1][0] + step
                if next_start <= start:
                    raise ValueError("pagination did not advance")
            except (TypeError, IndexError, ValueError) as exc:
                raise MarketError(f"Invalid klines page: {exc}") from exc
            rows.extend(page)
            start = next_start
        return rows

    def snapshot(
        self,
        symbol: str,
        bars: int = 250,
        as_of_ms: int | None = None,
        source: str = "binance_public",
    ) -> dict[str, Any]:
        symbol = normalize_symbol(symbol)
        if source not in ("binance_public", "simulated"):
            raise MarketError("Unknown data source")
        if not 100 <= bars <= 5000:
            raise MarketError("bars must be between 100 and 5000")
        server_time = self.server_time()
        cutoff = server_time if as_of_ms is None else as_of_ms
        if cutoff <= 0 or cutoff > server_time:
            raise MarketError("as_of must be positive and no later than Binance server time")
        info = self.symbol_info(symbol)
        data, failures = {}, {}
        for interval in Interval:
            try:
                data[interval.name] = self.klines(symbol, interval, cutoff, bars)
            except MarketError as exc:
                data[interval.name] = []
                failures[interval.name] = str(exc)
        return {
            "snapshot_version": "1",
            "source": source,
            "symbol": symbol,
            "as_of_ms": cutoff,
            "server_time_ms": server_time,
            "requested_bars": bars,
            "endpoint": getattr(self.transport, "base_url", "injected_transport"),
            "symbol_info": info,
            "klines": data,
            "fetch_errors": failures,
        }
