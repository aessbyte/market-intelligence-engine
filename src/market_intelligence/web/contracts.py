"""Versioned presentation envelopes; engine JSON retains its own v3 schema."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..binance import normalize_symbol
from ..models import MarketError


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class AnalysisRequest(Contract):
    symbol: str = Field(min_length=5, max_length=30)
    market: Literal["spot", "futures"] = "spot"
    bars: int = Field(default=250, ge=100, le=500, strict=True)

    @field_validator("symbol")
    @classmethod
    def symbol_format(cls, value: str) -> str:
        try:
            return normalize_symbol(value)
        except MarketError as exc:
            raise ValueError(str(exc)) from exc


class APIError(Contract):
    code: str
    message: str
    request_id: str


class ErrorEnvelope(Contract):
    error: APIError


class JobResponse(Contract):
    job_id: str
    status: Literal["queued", "running", "completed", "failed"]
    stage: Literal["validating", "fetching", "analyzing", "preparing", "completed", "failed"]
    result_id: str | None = None
    error: APIError | None = None


class Summary(Contract):
    symbol: str
    base_asset: str | None = None
    quote_asset: str | None = None
    tick_size: float | None = None
    reference_price: float | None
    reference_time_ms: int | None
    as_of_ms: int
    change_percent: float | None
    change_basis: Literal["previous_closed_H1"] = "previous_closed_H1"
    volume: float | None
    volume_basis: Literal["base_asset_last_closed_H1"] = "base_asset_last_closed_H1"
    atr_percent: float | None
    quality: Literal["ok", "degraded"]


class ChartCandle(Contract):
    time_ms: int
    open: float
    high: float
    low: float
    close: float
    volume: float


class ChartPoint(Contract):
    time_ms: int
    value: float


class ChartEvent(Contract):
    id: str
    kind: str
    event_time_ms: int
    detected_at_ms: int
    available_at_ms: int
    confirmed_at_ms: int | None
    invalidated_at_ms: int | None
    price: float
    interval: str
    state: Literal["candidate", "confirmed", "invalidated"]
    evidence: list[dict[str, Any]]
    parameters: dict[str, Any]


class ChartData(Contract):
    candles: list[ChartCandle]
    ema20: list[ChartPoint]
    ema50: list[ChartPoint]
    rsi14: list[ChartPoint]
    events: list[ChartEvent]
    levels: list[dict[str, Any]]


class ModelComparison(Contract):
    model_kind: str
    metrics: dict[str, Any]
    same_population_reference_baseline_metrics: dict[str, Any] | None = None
    fold_ids: list[int]


class HorizonQuality(Contract):
    status: str
    model_kind: str | None
    training_start_ms: int | None
    training_end_ms: int | None
    final_test_start_ms: int | None
    final_test_end_ms: int | None
    selected_strategy_metrics: dict[str, Any] | None
    final_test_metrics: dict[str, Any] | None
    comparisons: list[ModelComparison]
    calibration: dict[str, Any] | None
    coverage: dict[str, Any] | None
    final_coverage: dict[str, Any] | None
    paired_comparison: dict[str, Any] | None
    limitations: list[str]


class ModelQuality(Contract):
    configured: bool
    model_version: str | None
    dataset_version: str | None
    availability_semantics: str | None
    horizons: dict[str, HorizonQuality]


class CacheInfo(Contract):
    hit: bool
    expires_at_ms: int


class CompactAnalysis(Contract):
    api_version: Literal["1"] = "1"
    analysis_id: str
    mode: Literal["live", "replay"]
    market: Literal["spot"] = "spot"
    exchange: Literal["binance"] = "binance"
    summary: Summary
    analysis: dict[str, Any]
    charts: dict[str, ChartData]
    model_quality: ModelQuality
    cache: CacheInfo
    warnings: list[str]


class MarketAvailability(Contract):
    market: Literal["spot", "futures"]
    available: bool | None
    supported: bool
    status: str
    reason: str | None = None


class SymbolValidation(Contract):
    symbol: str
    exchange: Literal["binance"] = "binance"
    mode: Literal["live", "replay"]
    valid: bool
    supported_markets: list[str]
    markets: list[MarketAvailability]


class SymbolItem(Contract):
    symbol: str
    base_asset: str | None
    quote_asset: str | None
    markets: list[str]


class SymbolsResponse(Contract):
    exchange: Literal["binance"] = "binance"
    mode: Literal["live", "replay"]
    symbols: list[SymbolItem]
    supported_markets: list[str] = ["spot"]
    futures_checked: Literal[False] = False


class Projection(Contract):
    analysis_id: str
    as_of_ms: int
    data: Any
