"""Exclusive calendar-day targets with origin-observable volatility thresholds."""

import math

from ..models import Candle, MarketError
from .contracts import DAY_MS, FeatureRow, PredictionConfig, Sample
from .features import _valid_history


def build_samples(
    candles: tuple[Candle, ...],
    rows: tuple[FeatureRow, ...],
    horizon_days: int,
    config: PredictionConfig = PredictionConfig(),
) -> tuple[Sample, ...]:
    """Label the endpoint, and record path excursions separately.

    Return log thresholds are +/- label_sigma * sigma_at_origin * sqrt(days).
    Equality is neutral. No estimated volatility means no valid target, rather
    than a fabricated threshold. Missing endpoints do not shorten the horizon.
    """
    if type(horizon_days) is not int or horizon_days <= 0:
        raise MarketError("Target horizon must be a positive number of calendar days")
    history = _valid_history(candles)
    indexes = {candle.close_time_ms + 1: index for index, candle in enumerate(history)}
    samples: list[Sample] = []
    for row in rows:
        index = indexes.get(row.origin_ms)
        if index is None or history[index].close != row.close:
            raise MarketError("Feature origin does not match its historical candle")
        if any(timestamp > row.origin_ms for timestamp in row.available_at_ms):
            raise MarketError("Future feature availability cannot be labelled")
        if not math.isfinite(row.sigma) or row.sigma <= 0:
            continue
        endpoint = row.origin_ms + horizon_days * DAY_MS
        end_index = indexes.get(endpoint)
        if end_index is None:
            continue
        end = history[end_index]
        scale = row.sigma * math.sqrt(horizon_days)
        threshold = config.label_sigma * scale
        log_return = math.log(end.close / row.close)
        label = 2 if log_return > threshold else 0 if log_return < -threshold else 1
        path = history[index + 1 : end_index + 1]
        samples.append(
            Sample(
                row=row,
                horizon_days=horizon_days,
                end_ms=endpoint,
                target_available_ms=end.close_time_ms + 1,
                label=label,
                log_return=log_return,
                return_value=end.close / row.close - 1,
                normalized_return=log_return / scale,
                upper_log_threshold=threshold,
                lower_log_threshold=-threshold,
                maximum_favorable_excursion=max(
                    0.0, max(candle.high for candle in path) / row.close - 1
                ),
                maximum_adverse_excursion=min(
                    0.0, min(candle.low for candle in path) / row.close - 1
                ),
            )
        )
    return tuple(samples)
