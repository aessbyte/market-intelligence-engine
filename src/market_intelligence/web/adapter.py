"""Presentation projections only: calculations and causal events belong to the engine."""

from copy import deepcopy
import math
from typing import Any

from ..indicators import calculate, ema
from ..models import Interval, MarketError
from ..validation import parse_klines, validate
from .contracts import CompactAnalysis, HorizonQuality, ModelComparison, ModelQuality


def model_quality(bundle: dict[str, Any] | None, symbol: str) -> ModelQuality:
    if bundle is None or bundle["dataset"]["symbol"] != symbol:
        return ModelQuality(
            configured=False,
            model_version=None,
            dataset_version=None,
            availability_semantics=None,
            horizons={},
        )
    horizons = {}
    for horizon, entry in bundle["models"].items():
        model = entry.get("model") or {}
        report = bundle["report"]["horizons"].get(horizon, {})
        folds = report.get("folds", [])
        final: dict[str, Any] = next(
            (fold for fold in reversed(folds) if fold.get("final_test")), {}
        )
        test = final.get("split_metadata", {}).get("test", {})
        comparisons = []
        for kind, metrics in report.get("model_comparisons", {}).items():
            comparisons.append(
                ModelComparison(
                    model_kind=kind,
                    metrics=metrics,
                    same_population_reference_baseline_metrics=metrics.get(
                        "same_population_reference_baseline_metrics"
                    ),
                    fold_ids=metrics.get("fold_ids", []),
                )
            )
        horizons[horizon] = HorizonQuality(
            status=entry["status"],
            model_kind=model.get("kind"),
            training_start_ms=model.get("train_origin_start_ms"),
            training_end_ms=model.get("train_origin_end_ms"),
            final_test_start_ms=test.get("first_origin_ms"),
            final_test_end_ms=test.get("last_origin_ms"),
            selected_strategy_metrics=report.get("selected_strategy_metrics"),
            final_test_metrics=final.get("test_metrics", {}).get(model.get("kind")),
            comparisons=comparisons,
            calibration=model.get("calibration"),
            coverage=report.get("return_interval_coverage"),
            final_coverage=final.get("return_interval_coverage"),
            paired_comparison=report.get("frozen_final_model_comparison"),
            limitations=entry.get("limitations", []),
        )
    return ModelQuality(
        configured=True,
        model_version=bundle["model_version"],
        dataset_version=bundle["dataset"]["dataset_version"],
        availability_semantics=bundle.get("availability_semantics"),
        horizons=horizons,
    )


def compact_analysis(
    analysis_id: str,
    snapshot: dict[str, Any],
    result: dict[str, Any],
    mode: str,
    quality: ModelQuality,
    expires_at_ms: int,
    warnings: list[str],
) -> dict[str, Any]:
    """Omit large journals only; retain scalar results and all current evidence."""
    presentation = deepcopy(result)
    charts: dict[str, Any] = {}
    for interval in Interval:
        name = interval.name
        frame = presentation["timeframes"][name]
        structure = frame.get("structure") or {}
        wyckoff = frame.get("wyckoff") or {}
        structure.pop("event_journal", None)
        structure.pop("trend_history", None)
        wyckoff.pop("event_journal", None)
        chart: dict[str, Any] = {
            "candles": [],
            "ema20": [],
            "ema50": [],
            "rsi14": [],
            "events": structure.get("events", []) + wyckoff.get("events", []),
            "levels": structure.get("levels", []),
        }
        try:
            candles, validity = validate(
                parse_klines(snapshot["klines"].get(name, [])),
                interval,
                result["as_of_ms"],
                minimum=1,
            )
            if not validity.valid:
                raise MarketError("; ".join(validity.errors))
            chart["candles"] = [
                {
                    "time_ms": candle.open_time_ms,
                    "open": candle.open,
                    "high": candle.high,
                    "low": candle.low,
                    "close": candle.close,
                    "volume": candle.volume,
                }
                for candle in candles
            ]
            # Series reuse exactly the same EMA seeds and RSI implementation as the engine.
            closes = [candle.close for candle in candles]
            for period in (20, 50):
                if len(candles) >= period:
                    chart["ema" + str(period)] = [
                        {"time_ms": candle.open_time_ms, "value": value}
                        for candle, value in zip(candles[period - 1 :], ema(closes, period))
                    ]
            if frame["quality"]["valid"]:
                chart["rsi14"] = [
                    {
                        "time_ms": candles[end - 1].open_time_ms,
                        "value": calculate(candles[:end]).rsi14,
                    }
                    for end in range(100, len(candles) + 1)
                ]
        except (MarketError, ValueError, ArithmeticError) as exc:
            warnings.append(name + ": chart unavailable: " + str(exc))
        charts[name] = chart
    hourly = charts["H1"]["candles"]
    latest = hourly[-1] if hourly else None
    previous = hourly[-2] if len(hourly) > 1 else None
    features = result["timeframes"]["H1"].get("indicators") or {}
    metadata = snapshot.get("symbol_info", {})
    tick_size = None
    filters = metadata.get("filters", [])
    for price_filter in filters if isinstance(filters, list) else []:
        if isinstance(price_filter, dict) and price_filter.get("filterType") == "PRICE_FILTER":
            try:
                observed = float(price_filter["tickSize"])
                if math.isfinite(observed) and observed > 0:
                    tick_size = observed
            except (KeyError, ValueError, TypeError, OverflowError):
                pass
    payload = {
        "api_version": "1",
        "analysis_id": analysis_id,
        "mode": mode,
        "market": "spot",
        "exchange": "binance",
        "summary": {
            "symbol": result["symbol"],
            "base_asset": metadata.get("baseAsset")
            if isinstance(metadata.get("baseAsset"), str)
            else None,
            "quote_asset": metadata.get("quoteAsset")
            if isinstance(metadata.get("quoteAsset"), str)
            else None,
            "tick_size": tick_size,
            "reference_price": latest["close"] if latest else None,
            "reference_time_ms": latest["time_ms"] + Interval.H1.milliseconds - 1
            if latest
            else None,
            "as_of_ms": result["as_of_ms"],
            "change_percent": 100 * (latest["close"] / previous["close"] - 1)
            if latest and previous
            else None,
            "change_basis": "previous_closed_H1",
            "volume": latest["volume"] if latest else None,
            "volume_basis": "base_asset_last_closed_H1",
            "atr_percent": features.get("atr_percent"),
            "quality": result["status"],
        },
        "analysis": presentation,
        "charts": charts,
        "model_quality": quality.model_dump(mode="json"),
        "cache": {"hit": False, "expires_at_ms": expires_at_ms},
        "warnings": list(dict.fromkeys(warnings)),
    }
    return CompactAnalysis.model_validate(payload).model_dump(mode="json")
