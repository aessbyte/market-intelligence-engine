"""Probabilistic scores and honest uncertainty for temporal holdout reports."""

import math
import random
import statistics
from collections.abc import Mapping, Sequence
from typing import Any

from .contracts import CLASSES, Sample
from .validation import independent_indices


def _validate_probabilities(
    labels: Sequence[int], probabilities: Sequence[Sequence[float]]
) -> None:
    if len(labels) != len(probabilities):
        raise ValueError("labels and predictions have different lengths")
    for label, probabilities_row in zip(labels, probabilities, strict=True):
        if type(label) is not int or not 0 <= label < len(CLASSES):
            raise ValueError("invalid class index")
        if len(probabilities_row) != len(CLASSES):
            raise ValueError("three class probabilities are required")
        if any(
            isinstance(value, bool) or not math.isfinite(value) or not 0 <= value <= 1
            for value in probabilities_row
        ):
            raise ValueError("class probabilities must be finite and in [0,1]")
        if abs(sum(probabilities_row) - 1.0) > 1e-8:
            raise ValueError("class probabilities must sum to one")


def _brier(label: int, probabilities: Sequence[float]) -> float:
    return sum((value - float(label == index)) ** 2 for index, value in enumerate(probabilities))


def _log_loss(label: int, probabilities: Sequence[float]) -> float:
    return -math.log(max(probabilities[label], 1e-15))


def probability_metrics(
    labels: Sequence[int], probabilities: Sequence[Sequence[float]]
) -> dict[str, Any]:
    """Brier uses sum over classes (range 0..2), with ten bins per class.

    ECE is the mean of three classwise weighted absolute calibration errors.
    Empty bins have unavailable means/frequencies instead of invented values.
    """
    _validate_probabilities(labels, probabilities)
    observations = len(labels)
    bins: dict[str, list[dict[str, Any]]] = {}
    ece = 0.0
    for class_index, class_name in enumerate(CLASSES):
        class_bins: list[dict[str, Any]] = []
        for bin_index in range(10):
            selected = [
                index
                for index, row in enumerate(probabilities)
                if min(int(row[class_index] * 10), 9) == bin_index
            ]
            count = len(selected)
            mean_probability = (
                sum(probabilities[index][class_index] for index in selected) / count
                if count
                else None
            )
            observed_frequency = (
                sum(labels[index] == class_index for index in selected) / count if count else None
            )
            if count and mean_probability is not None and observed_frequency is not None:
                ece += (
                    count * abs(mean_probability - observed_frequency) / observations / len(CLASSES)
                )
            class_bins.append(
                {
                    "lower_probability": bin_index / 10,
                    "upper_probability": (bin_index + 1) / 10,
                    "upper_inclusive": bin_index == 9,
                    "observations": count,
                    "mean_probability": mean_probability,
                    "observed_frequency": observed_frequency,
                }
            )
        bins[class_name] = class_bins
    return {
        "observations": observations,
        "brier": (
            sum(_brier(label, row) for label, row in zip(labels, probabilities, strict=True))
            / observations
            if observations
            else None
        ),
        "log_loss": (
            sum(_log_loss(label, row) for label, row in zip(labels, probabilities, strict=True))
            / observations
            if observations
            else None
        ),
        "accuracy": (
            sum(
                max(range(len(CLASSES)), key=lambda index: row[index]) == label
                for label, row in zip(labels, probabilities, strict=True)
            )
            / observations
            if observations
            else None
        ),
        "ece": ece if observations else None,
        "ece_definition": "mean of classwise weighted absolute bin calibration errors",
        "calibration_bins": bins,
    }


def interval_coverage(
    samples: Sequence[Sample], forecasts: Sequence[Mapping[str, float]]
) -> dict[str, Any]:
    """Evaluate arithmetic-return intervals separately from prices/path extrema."""
    if len(samples) != len(forecasts):
        raise ValueError("samples and return forecasts have different lengths")
    covered = 0
    widths: list[float] = []
    median_errors: list[float] = []
    for sample, forecast in zip(samples, forecasts, strict=True):
        lower, median, upper = (forecast[key] for key in ("lower", "median", "upper"))
        if not all(math.isfinite(value) for value in (lower, median, upper, sample.return_value)):
            raise ValueError("return intervals and outcomes must be finite")
        if not lower <= median <= upper:
            raise ValueError("return interval quantiles are not ordered")
        covered += lower <= sample.return_value <= upper
        widths.append(upper - lower)
        median_errors.append(abs(sample.return_value - median))
    observations = len(samples)
    return {
        "observations": observations,
        "covered_observations": covered,
        "coverage": covered / observations if observations else None,
        "mean_interval_width": sum(widths) / observations if observations else None,
        "median_prediction_mae": sum(median_errors) / observations if observations else None,
        "median_absolute_error": statistics.median(median_errors) if observations else None,
        "return_definition": "arithmetic end-of-horizon return; not path excursion",
    }


def _percentile(values: Sequence[float], probability: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    left = int(position)
    right = min(left + 1, len(ordered) - 1)
    return ordered[left] + (ordered[right] - ordered[left]) * (position - left)


def paired_comparison(
    samples: tuple[Sample, ...],
    selected: Sequence[Sequence[float]],
    baseline: Sequence[Sequence[float]],
    seed: int = 42,
    bootstrap_samples: int = 1000,
) -> dict[str, Any]:
    """Paired score improvement on horizon-spaced holdout origins.

    Positive lift means the selected model has lower loss. Percentile bootstrap
    intervals are exploratory; non-overlapping targets still share market
    regimes and do not establish durable predictive advantage.
    """
    labels = [sample.label for sample in samples]
    _validate_probabilities(labels, selected)
    _validate_probabilities(labels, baseline)
    if type(seed) is not int or type(bootstrap_samples) is not int or bootstrap_samples < 500:
        raise ValueError("bootstrap requires an integer seed and at least 500 resamples")
    indices = independent_indices(samples)
    count = len(indices)
    brier_lifts = [_brier(labels[i], baseline[i]) - _brier(labels[i], selected[i]) for i in indices]
    log_lifts = [
        _log_loss(labels[i], baseline[i]) - _log_loss(labels[i], selected[i]) for i in indices
    ]
    brier_confidence: list[float] | None = None
    log_confidence: list[float] | None = None
    if count >= 2:
        generator = random.Random(seed)
        boot_brier: list[float] = []
        boot_log: list[float] = []
        for _ in range(bootstrap_samples):
            draw = [generator.randrange(count) for _ in range(count)]
            boot_brier.append(sum(brier_lifts[index] for index in draw) / count)
            boot_log.append(sum(log_lifts[index] for index in draw) / count)
        brier_confidence = [_percentile(boot_brier, 0.025), _percentile(boot_brier, 0.975)]
        log_confidence = [_percentile(boot_log, 0.025), _percentile(boot_log, 0.975)]
    return {
        "observations": len(samples),
        "n_independent": count,
        "brier_lift": sum(brier_lifts) / count if count else None,
        "brier_confidence_interval": brier_confidence,
        "log_loss_lift": sum(log_lifts) / count if count else None,
        "log_loss_confidence_interval": log_confidence,
        "positive_edge": bool(
            brier_confidence is not None
            and log_confidence is not None
            and brier_confidence[0] > 0
            and log_confidence[0] > 0
        ),
        "confidence_level": 0.95,
        "bootstrap_samples": bootstrap_samples,
        "seed": seed,
        "method": "paired percentile bootstrap on greedy horizon-spaced origins",
        "limitations": [
            "non-overlapping targets do not prove statistical independence",
            "one historical sample cannot establish durable predictive advantage",
        ],
    }
