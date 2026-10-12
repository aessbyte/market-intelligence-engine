"""Chronological, purged walk-forward partitions without random sampling."""

from dataclasses import dataclass, replace
from typing import Any

from .contracts import DAY_MS, HORIZONS, PredictionConfig, Sample


@dataclass(frozen=True)
class WalkForwardSplit:
    fold_id: int
    train: tuple[Sample, ...]
    validation: tuple[Sample, ...]
    calibration: tuple[Sample, ...]
    test: tuple[Sample, ...]
    final_test: bool
    boundaries: dict[str, int]
    metadata: dict[str, Any]


def _validate_order(samples: tuple[Sample, ...]) -> None:
    previous: int | None = None
    horizon: int | None = None
    for sample in samples:
        origin = sample.row.origin_ms
        if previous is not None and origin <= previous:
            raise ValueError("samples must have strictly increasing, unique origins")
        if sample.horizon_days not in HORIZONS:
            raise ValueError("unsupported sample horizon")
        if horizon is not None and sample.horizon_days != horizon:
            raise ValueError("a temporal partition cannot mix horizons")
        if sample.end_ms <= origin or sample.target_available_ms < sample.end_ms:
            raise ValueError("invalid target interval or availability")
        if any(timestamp > origin for timestamp in sample.row.available_at_ms):
            raise ValueError("a sample contains a feature unavailable at its origin")
        horizon = sample.horizon_days
        previous = origin


def _within(samples: tuple[Sample, ...], start: int, end: int) -> tuple[Sample, ...]:
    return tuple(sample for sample in samples if start <= sample.row.origin_ms < end)


def _purge(samples: tuple[Sample, ...], next_origin: int) -> tuple[Sample, ...]:
    # Equality is deliberately purged too: the left label must be available
    # strictly before the next block starts, not at the same timestamp.
    return tuple(sample for sample in samples if sample.target_available_ms < next_origin)


def _block_metadata(samples: tuple[Sample, ...]) -> dict[str, int | None]:
    return {
        "observations": len(samples),
        "first_origin_ms": samples[0].row.origin_ms if samples else None,
        "last_origin_ms": samples[-1].row.origin_ms if samples else None,
        "last_target_available_ms": max(
            (sample.target_available_ms for sample in samples), default=None
        ),
    }


def walk_forward(
    samples: tuple[Sample, ...], config: PredictionConfig
) -> tuple[WalkForwardSplit, ...]:
    """Return expanding train/validation/calibration/test blocks.

    Durations are UTC calendar days, never numbers of randomly selected rows.
    An origin embargo precedes each later block. Labels reaching the next
    block's first actual origin are removed from the earlier block. Test labels
    reaching the nominal test end are also removed, so adjacent holdouts do not
    share target periods. The last emitted test block is the frozen final test;
    a shorter residual block is accepted only with min_validation observations.
    """
    _validate_order(samples)
    if not samples:
        return ()
    first = samples[0].row.origin_ms
    last = samples[-1].row.origin_ms
    embargo = config.embargo_days * DAY_MS
    splits: list[WalkForwardSplit] = []
    fold_id = 0
    while True:
        train_end = first + (config.initial_train_days + fold_id * config.test_days) * DAY_MS
        validation_start = train_end + embargo
        validation_end = validation_start + config.validation_days * DAY_MS
        calibration_start = validation_end + embargo
        calibration_end = calibration_start + config.calibration_days * DAY_MS
        test_start = calibration_end + embargo
        test_end = test_start + config.test_days * DAY_MS
        if test_start > last:
            break

        raw_train = _within(samples, first, train_end)
        raw_validation = _within(samples, validation_start, validation_end)
        raw_calibration = _within(samples, calibration_start, calibration_end)
        raw_test = _within(samples, test_start, test_end)
        test = _purge(raw_test, test_end)
        if len(test) < config.min_validation:
            break
        if not raw_validation or not raw_calibration:
            fold_id += 1
            continue

        # Use actual retained block origins, including explicit missing days.
        train = _purge(raw_train, raw_validation[0].row.origin_ms)
        validation = _purge(raw_validation, raw_calibration[0].row.origin_ms)
        calibration = _purge(raw_calibration, test[0].row.origin_ms)
        if (
            len(train) < config.min_train
            or len(validation) < config.min_validation
            or len(calibration) < config.min_calibration
        ):
            fold_id += 1
            continue

        boundaries = {
            "train_start_ms": first,
            "train_end_ms": train_end,
            "validation_start_ms": validation_start,
            "validation_end_ms": validation_end,
            "calibration_start_ms": calibration_start,
            "calibration_end_ms": calibration_end,
            "test_start_ms": test_start,
            "test_end_ms": test_end,
        }
        metadata: dict[str, Any] = {
            "horizon_days": samples[0].horizon_days,
            "embargo_days": config.embargo_days,
            "purge_rule": "target_available_ms < next_block_first_origin_ms",
            "partial_test_window": last < test_end - DAY_MS,
            "train": _block_metadata(train),
            "validation": _block_metadata(validation),
            "calibration": _block_metadata(calibration),
            "test": _block_metadata(test),
            "purged": {
                "train": len(raw_train) - len(train),
                "validation": len(raw_validation) - len(validation),
                "calibration": len(raw_calibration) - len(calibration),
                "test": len(raw_test) - len(test),
            },
        }
        splits.append(
            WalkForwardSplit(
                fold_id, train, validation, calibration, test, False, boundaries, metadata
            )
        )
        fold_id += 1

    if splits:
        splits[-1] = replace(splits[-1], final_test=True)
    return tuple(splits)


def independent_indices(samples: tuple[Sample, ...]) -> tuple[int, ...]:
    """Greedily retain non-overlapping target windows, in chronological order.

    This reduces overlap dependence; it does not prove statistical independence
    of a market time series. That limitation also applies to paired bootstraps.
    """
    _validate_order(samples)
    selected: list[int] = []
    next_origin: int | None = None
    for index, sample in enumerate(samples):
        if next_origin is None or sample.row.origin_ms >= next_origin:
            selected.append(index)
            next_origin = max(
                sample.target_available_ms,
                sample.row.origin_ms + sample.horizon_days * DAY_MS,
            )
    return tuple(selected)


def independent_samples(samples: tuple[Sample, ...]) -> tuple[Sample, ...]:
    return tuple(samples[index] for index in independent_indices(samples))
