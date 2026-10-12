"""Causal D1 predictors; event revisions are consumed only when available.

Indicators use a trailing, configurable window (default 250 closed candles),
including their EMA/Wilder seeds. Structure and Wyckoff retain their original
sequential rules. H1/H4 historical coverage is never inferred from D1 candles.
"""

import math
import statistics
from typing import Any

from ..indicators import calculate, ema
from ..models import Candle, Interval, MarketError, Regime
from ..regime import classify
from ..structure import analyze_structure
from ..validation import validate
from ..wyckoff import analyze_wyckoff
from .contracts import DAY_MS, FeatureRow, PredictionConfig

_REGIMES = tuple(regime.value for regime in Regime)
_SIGNALS = ("Spring", "Upthrust", "SOS", "SOW", "LPS", "LPSY")
_BREAK_KINDS = ("BOS", "CHoCH")
FEATURE_NAMES = (
    "ema20_slope5_atr",
    "ema20_ema50_gap_atr",
    "close_ema20_distance_atr",
    "sma20_distance_atr",
    "rsi14_fraction",
    "macd12_26_atr",
    "macd_signal9_atr",
    "macd_histogram_atr",
    "atr_fraction",
    "return1",
    "return7",
    "return30",
    "price_relative5",
    "price_relative20",
    "sigma_observed",
    "range_compression5_20",
    "range_compression_missing",
    "bollinger_width_fraction",
    "efficiency20",
    "volume_ratio20",
    "volume_missing",
    "volume_zscore20",
    "volume_variance_missing",
    "log_quote_volume",
    "price_participation",
    "liquidity_low",
    "trend_persistence_days",
    *("regime_" + regime for regime in _REGIMES),
    *("structure_" + regime for regime in _REGIMES),
    "confirmed_high_distance_fraction",
    "confirmed_high_missing",
    "confirmed_low_distance_fraction",
    "confirmed_low_missing",
    *(
        kind.lower() + "_" + direction + "_" + state + "_12d"
        for kind in _BREAK_KINDS
        for direction in ("up", "down")
        for state in ("candidate", "confirmed")
    ),
    "false_break_confirmed_12d",
    "range_position",
    "range_width_fraction",
    "range_missing",
    "range_candidate",
    "range_confirmed",
    *(
        kind.lower() + "_" + state + "_12d"
        for kind in _SIGNALS
        for state in ("candidate", "confirmed")
    ),
)


def _valid_history(candles: tuple[Candle, ...]) -> tuple[Candle, ...]:
    if not candles:
        return ()
    cutoff = candles[-1].close_time_ms + 1
    closed, report = validate(candles, Interval.D1, cutoff, minimum=1)
    if not report.valid:
        raise MarketError(
            "Predictive features require contiguous D1 history: " + "; ".join(report.errors)
        )
    return closed


def _consume(
    journal: list[dict[str, Any]],
    index: int,
    now: int,
    state: dict[str, dict[str, Any]],
) -> int:
    """Replay immutable revisions; never inspect the final retrospective state."""
    while index < len(journal) and journal[index]["available_at_ms"] <= now:
        event = journal[index]
        state[event["id"]] = event
        index += 1
    return index


def _ratio(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator > 0 else 0.0


def build_features(
    candles: tuple[Candle, ...], config: PredictionConfig = PredictionConfig()
) -> tuple[FeatureRow, ...]:
    """Return one immutable feature row per available D1 origin after warmup.

    ``available_at_ms`` denotes the first time the complete scalar is observable;
    counts include the absence of newer events, and distances include the origin
    close, so their availability is the origin even when their pivot is older.
    Missing measurements are zero plus an explicit missing indicator.
    """
    history = _valid_history(candles)
    if len(history) < config.warmup:
        return ()
    cutoff = history[-1].close_time_ms + 1
    structure = analyze_structure(history, Interval.D1, cutoff)
    wyckoff = analyze_wyckoff(history, Interval.D1, cutoff, structure)
    structure_journal: list[dict[str, Any]] = structure["event_journal"]
    wyckoff_journal: list[dict[str, Any]] = wyckoff["event_journal"]
    structure_state: dict[str, dict[str, Any]] = {}
    wyckoff_state: dict[str, dict[str, Any]] = {}
    structure_index = wyckoff_index = 0
    trend_at = {item["available_at_ms"]: item["trend"] for item in structure["trend_history"]}
    result: list[FeatureRow] = []
    previous_regime: str | None = None
    persistence = 0
    for index in range(config.warmup - 1, len(history)):
        candle = history[index]
        now = candle.close_time_ms + 1
        window = history[max(0, index + 1 - config.feature_window) : index + 1]
        closes = [item.close for item in window]
        indicator = calculate(window)
        regime = classify(indicator)[0].value
        persistence = persistence + 1 if regime == previous_regime else 1
        previous_regime = regime
        log_returns = [math.log(b / a) for a, b in zip(closes, closes[1:])]
        sigma = statistics.pstdev(log_returns[-config.volatility_window :])
        ema12, ema26 = ema(closes, 12), ema(closes, 26)
        macd = [short - long for short, long in zip(ema12[14:], ema26)]
        signal = ema(macd, 9)[-1]
        spans = [item.high - item.low for item in window]
        previous_span = statistics.fmean(spans[-25:-5])
        volumes = [item.volume for item in window[-21:-1]]
        volume_mean = statistics.fmean(volumes)
        volume_sigma = statistics.pstdev(volumes)
        relative_volume = indicator.volume_ratio20 or 0.0
        values: dict[str, float] = {
            "ema20_slope5_atr": indicator.ema20_slope5_atr,
            "ema20_ema50_gap_atr": indicator.ema_gap_atr,
            "close_ema20_distance_atr": _ratio(candle.close - indicator.ema20, indicator.atr14),
            "sma20_distance_atr": _ratio(candle.close - indicator.sma20, indicator.atr14),
            "rsi14_fraction": indicator.rsi14 / 100,
            "macd12_26_atr": _ratio(macd[-1], indicator.atr14),
            "macd_signal9_atr": _ratio(signal, indicator.atr14),
            "macd_histogram_atr": _ratio(macd[-1] - signal, indicator.atr14),
            "atr_fraction": indicator.atr_percent / 100,
            "return1": log_returns[-1],
            "return7": math.log(closes[-1] / closes[-8]),
            "return30": math.log(closes[-1] / closes[-31]),
            "price_relative5": math.log(closes[-1] / closes[-6]),
            "price_relative20": math.log(closes[-1] / closes[-21]),
            "sigma_observed": sigma,
            "range_compression5_20": _ratio(statistics.fmean(spans[-5:]), previous_span),
            "range_compression_missing": float(previous_span == 0),
            "bollinger_width_fraction": (indicator.bollinger_upper20 - indicator.bollinger_lower20)
            / candle.close,
            "efficiency20": indicator.efficiency20,
            "volume_ratio20": relative_volume,
            "volume_missing": float(volume_mean == 0),
            "volume_zscore20": _ratio(candle.volume - volume_mean, volume_sigma),
            "volume_variance_missing": float(volume_sigma == 0),
            "log_quote_volume": math.log1p(candle.quote_volume),
            "price_participation": _ratio(abs(log_returns[-1]), relative_volume),
            "liquidity_low": float(
                candle.volume <= 0 or candle.trades <= 0 or relative_volume < 0.1
            ),
            "trend_persistence_days": float(persistence),
        }
        values.update({"regime_" + name: float(name == regime) for name in _REGIMES})
        structural_trend = trend_at.get(now, Regime.UNKNOWN.value)
        values.update({"structure_" + name: float(name == structural_trend) for name in _REGIMES})
        structure_index = _consume(structure_journal, structure_index, now, structure_state)
        wyckoff_index = _consume(wyckoff_journal, wyckoff_index, now, wyckoff_state)
        known_structure = tuple(structure_state.values())
        known_wyckoff = tuple(wyckoff_state.values())
        for kind, label in (("swing_high", "high"), ("swing_low", "low")):
            confirmed = [
                event
                for event in known_structure
                if event["kind"] == kind and event["state"] == "confirmed"
            ]
            pivot = max(confirmed, key=lambda event: event["event_time_ms"], default=None)
            values["confirmed_" + label + "_distance_fraction"] = (
                (candle.close / pivot["price"] - 1) if pivot else 0.0
            )
            values["confirmed_" + label + "_missing"] = float(pivot is None)
        fresh_structure = [
            event for event in known_structure if now - event["available_at_ms"] <= 12 * DAY_MS
        ]
        for kind in _BREAK_KINDS:
            for direction in ("up", "down"):
                for state in ("candidate", "confirmed"):
                    values[kind.lower() + "_" + direction + "_" + state + "_12d"] = float(
                        sum(
                            event["kind"] == kind
                            and event["state"] == state
                            and event["evidence"][0].get("direction") == direction
                            for event in fresh_structure
                        )
                    )
        values["false_break_confirmed_12d"] = float(
            sum(
                event["kind"] == "false_break" and event["state"] == "confirmed"
                for event in fresh_structure
            )
        )
        ranges = [event for event in known_wyckoff if event["kind"] == "trading_range"]
        latest_range = max(ranges, key=lambda event: event["detected_at_ms"], default=None)
        active_range = (
            latest_range if latest_range and latest_range["state"] != "invalidated" else None
        )
        lower = active_range["evidence"][0]["lower"] if active_range else 0.0
        upper = active_range["evidence"][0]["upper"] if active_range else 0.0
        values.update(
            {
                "range_position": _ratio(candle.close - lower, upper - lower)
                if active_range
                else 0.0,
                "range_width_fraction": (upper - lower) / ((upper + lower) / 2)
                if active_range
                else 0.0,
                "range_missing": float(active_range is None),
                "range_candidate": float(
                    active_range is not None and active_range["state"] == "candidate"
                ),
                "range_confirmed": float(
                    active_range is not None and active_range["state"] == "confirmed"
                ),
            }
        )
        for kind in _SIGNALS:
            for state in ("candidate", "confirmed"):
                values[kind.lower() + "_" + state + "_12d"] = float(
                    sum(
                        event["kind"] == kind
                        and event["state"] == state
                        and now - event["available_at_ms"] <= 12 * DAY_MS
                        for event in known_wyckoff
                    )
                )
        ordered = tuple(values[name] for name in FEATURE_NAMES)
        if not all(math.isfinite(value) for value in ordered):
            raise MarketError("Non-finite predictive feature at " + str(now))
        sources = tuple(
            "input_ohlcv:D1:structure-v1:availability_filtered_journal"
            if name.startswith(("structure_", "confirmed_", "bos_", "choch_", "false_break_"))
            else "input_ohlcv:D1:wyckoff-v1:availability_filtered_journal"
            if name.startswith(
                (
                    "range_position",
                    "range_width",
                    "range_missing",
                    "range_candidate",
                    "range_confirmed",
                    *(kind.lower() + "_" for kind in _SIGNALS),
                )
            )
            else "input_ohlcv:D1:causal_indicators:trailing_window="
            + str(config.feature_window)
            + ":volatility_window="
            + str(config.volatility_window)
            for name in FEATURE_NAMES
        )
        result.append(
            FeatureRow(now, candle.close, sigma, ordered, regime, (now,) * len(ordered), sources)
        )
    return tuple(result)
