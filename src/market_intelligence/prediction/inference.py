"""Causal portable forecast, empirical magnitudes and explicit abstention gates."""

import math
from typing import Any, Sequence

from .contracts import CLASSES, DAY_MS, HORIZONS, FeatureRow, PredictionConfig, Sample
from .models import predict_model


def empirical_distribution(samples: Sequence[Sample]) -> dict[str, Any]:
    return {
        "method": "training_only_class_conditional_volatility_normalized_empirical_mixture",
        "samples": [
            sorted(s.normalized_return for s in samples if s.label == label) for label in range(3)
        ],
        "observations": len(samples),
        "training_target_available_max_ms": max(s.target_available_ms for s in samples),
        "quantile_levels": [0.05, 0.1, 0.5, 0.9, 0.95],
        "interval_nominal_coverage": 0.8,
        "downside_threshold_return": -0.2,
    }


def return_distribution(
    distribution: dict[str, Any], probabilities: Sequence[float], sigma: float, horizon: int
) -> dict[str, Any] | None:
    groups = distribution["samples"]
    if any(not group for group in groups) or not math.isfinite(sigma) or sigma <= 0:
        return None
    weighted = sorted(
        (float(value), float(probabilities[label]) / len(group))
        for label, group in enumerate(groups)
        for value in group
    )
    cumulative = 0.0
    quantiles: dict[str, float] = {}
    levels = iter([float(level) for level in distribution["quantile_levels"]])
    current = next(levels, None)
    magnitude = sigma * math.sqrt(horizon)
    tail = 0.0
    for value, weight in weighted:
        transformed = math.expm1(max(-700.0, min(700.0, value * magnitude)))
        cumulative += weight
        if transformed <= distribution["downside_threshold_return"]:
            tail += weight
        while current is not None and cumulative + 1e-12 >= current:
            quantiles[str(current)] = transformed
            current = next(levels, None)
    return {
        "method": distribution["method"],
        "median": quantiles["0.5"],
        "lower": quantiles["0.1"],
        "upper": quantiles["0.9"],
        "quantiles": quantiles,
        "interval_nominal_coverage": distribution["interval_nominal_coverage"],
        "downside_threshold_return": distribution["downside_threshold_return"],
        "downside_probability": min(1.0, max(0.0, tail)),
        "observations": distribution["observations"],
        "interpretation": "end_of_horizon_return_distribution_not_support_resistance_or_guarantee",
    }


def forecast(
    bundle: dict[str, Any],
    row: FeatureRow,
    symbol: str,
    as_of_ms: int,
    source: str = "binance_public",
) -> list[dict[str, Any]]:
    from .training import validate_bundle

    bundle = validate_bundle(bundle)
    config = PredictionConfig.from_dict(bundle["configuration"])
    results = []
    for horizon in HORIZONS:
        entry = bundle["models"].get(str(horizon), {})
        reasons = list(entry.get("limitations", []))
        status = entry.get("status", "INSUFFICIENT_EVIDENCE")
        model = entry.get("model")
        hard_failure = False
        metadata = bundle["dataset"]
        if symbol != metadata.get("symbol"):
            reasons.append("symbol_mismatch")
            hard_failure = True
        if metadata.get("exchange") != "binance" or metadata.get("market") != "spot":
            reasons.append("unsupported_or_mismatched_market")
            hard_failure = True
        if source != "binance_public" or metadata.get("source") != "binance_public":
            reasons.append("synthetic_or_unverified_real_population")
            hard_failure = True
        if as_of_ms < bundle["available_at_ms"]:
            reasons.append("model_or_evaluation_not_available_at_reference_time")
            hard_failure = True
        if (
            model is not None
            and max(
                model["train_target_available_max_ms"],
                model.get("calibration", {}).get("target_available_max_ms", 0),
                entry["return_distribution"]["training_target_available_max_ms"],
            )
            > row.origin_ms
        ):
            reasons.append("training_or_calibration_target_not_known_at_daily_origin")
            hard_failure = True
        if row.origin_ms > as_of_ms or any(value > row.origin_ms for value in row.available_at_ms):
            reasons.append("feature_not_available_at_prediction_origin")
            hard_failure = True
        if as_of_ms - row.origin_ms >= DAY_MS:
            reasons.append("stale_daily_prediction_origin")
            hard_failure = True
        if len(row.values) != len(bundle["feature_names"]) or not all(
            math.isfinite(v) for v in row.values
        ):
            reasons.append("invalid_feature_contract")
            hard_failure = True
        if (
            len(row.available_at_ms) != len(row.values)
            or len(row.sources) != len(row.values)
            or not math.isfinite(row.close)
            or row.close <= 0
        ):
            reasons.append("invalid_feature_availability_or_price_contract")
            hard_failure = True
        if (
            not hard_failure
            and "liquidity_low" in bundle["feature_names"]
            and row.values[bundle["feature_names"].index("liquidity_low")] >= 0.5
        ):
            reasons.append("latest_candle_insufficient_observed_liquidity")
            hard_failure = True
        if row.sigma <= 0 or not math.isfinite(row.sigma):
            reasons.append("zero_or_invalid_observable_volatility")
            hard_failure = True
        probabilities = None
        magnitude = None
        drift = None
        if model is not None and not hard_failure:
            drift = [
                abs(value - mean) / scale
                for value, mean, scale in zip(
                    row.values, model["drift_mean"], model["drift_scale"], strict=True
                )
            ]
            if max(drift, default=0.0) > config.drift_z_limit:
                reasons.append("feature_distribution_shift")
                hard_failure = True
            if model["regime_counts"].get(row.regime, 0) < config.min_class:
                reasons.append("current_regime_underrepresented_in_training")
                hard_failure = True
            if not hard_failure:
                probabilities = predict_model(model, row.values)
                magnitude = return_distribution(
                    entry["return_distribution"], probabilities, row.sigma, horizon
                )
        if hard_failure:
            status = "INSUFFICIENT_EVIDENCE"
        elif reasons and status == "VALIDATED_MODEL":
            status = "UNVALIDATED_MODEL"
        is_validated = status == "VALIDATED_MODEL" and probabilities is not None
        results.append(
            {
                "horizon_days": horizon,
                "status": status,
                "prediction_origin_ms": row.origin_ms,
                "as_of_ms": as_of_ms,
                "horizon_end_ms": row.origin_ms + horizon * DAY_MS,
                "reference_price": row.close,
                "probabilities": dict(zip(CLASSES, probabilities, strict=True))
                if is_validated and probabilities is not None
                else None,
                "return_distribution": magnitude if is_validated else None,
                "experimental_diagnostics": {
                    "status": "EXPERIMENTAL_NOT_VALIDATED",
                    "probabilities": dict(zip(CLASSES, probabilities, strict=True))
                    if probabilities is not None
                    else None,
                    "return_distribution": magnitude,
                    "use": "research_only_not_a_validated_forecast",
                }
                if probabilities is not None
                else None,
                "model_version": bundle["model_version"],
                "model_available_at_ms": bundle["available_at_ms"],
                "dataset_version": metadata.get("dataset_version"),
                "evidence": entry.get("evidence"),
                "max_feature_standardized_distance": max(drift, default=0.0) if drift else None,
                "limitations": sorted(set(reasons)),
                "scenario_relationship": "statistical_end_return_classes_are_distinct_from_conditional_rule_scenarios",
                "reference_timing": "daily_close_reference; reference_as_of_ms_is_data_cutoff_not_actual_issuance",
            }
        )
    return results
