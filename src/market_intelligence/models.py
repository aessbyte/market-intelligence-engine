"""Immutable domain objects and extension contracts."""

from dataclasses import dataclass
from enum import Enum
from typing import Protocol


class MarketError(Exception):
    """Expected input, transport or data error safe to report in the CLI."""


class Interval(str, Enum):
    H1 = "1h"
    H4 = "4h"
    D1 = "1d"

    @property
    def milliseconds(self) -> int:
        return {Interval.H1: 3_600_000, Interval.H4: 14_400_000, Interval.D1: 86_400_000}[self]


class Regime(str, Enum):
    BULL = "alta"
    BEAR = "baixa"
    SIDEWAYS = "lateralizacao"
    UNKNOWN = "indeterminado"


@dataclass(frozen=True)
class Candle:
    open_time_ms: int
    close_time_ms: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    quote_volume: float
    trades: int


@dataclass(frozen=True)
class Validation:
    valid: bool
    received: int
    closed: int
    excluded_unclosed: int
    errors: tuple[str, ...]
    first_open_ms: int | None
    last_close_ms: int | None


@dataclass(frozen=True)
class Features:
    close: float
    sma20: float
    ema20: float
    ema50: float
    ema20_slope5_atr: float
    ema_gap_atr: float
    rsi14: float
    atr14: float
    atr_percent: float
    realized_volatility20: float
    bollinger_lower20: float
    bollinger_upper20: float
    volume_ratio20: float | None
    obv: float
    efficiency20: float


class AnalysisModule(Protocol):
    """Future Wyckoff/SMC/flow modules receive only validated closed candles.

    A consumer must restrict historical inputs to what was available at as_of_ms.
    No module may read the clock or fetch additional data behind this contract.
    """

    name: str
    version: str

    def analyze(self, candles: tuple[Candle, ...], as_of_ms: int) -> dict[str, object]: ...
