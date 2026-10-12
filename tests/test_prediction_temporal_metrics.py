"""Synthetic temporal labels verify splitting and scores, never predictive edge."""

import math
import unittest
from dataclasses import replace

from market_intelligence.prediction.contracts import DAY_MS, FeatureRow, PredictionConfig, Sample
from market_intelligence.prediction.metrics import (
    interval_coverage,
    paired_comparison,
    probability_metrics,
)
from market_intelligence.prediction.validation import independent_indices, walk_forward


def sample(day: int, horizon: int = 7, label: int = 1) -> Sample:
    origin = day * DAY_MS
    row = FeatureRow(origin, 100.0, 0.01, (0.5,), "lateralizacao", (origin,), ("synthetic",))
    end = origin + horizon * DAY_MS
    log_return = (label - 1) * 0.05
    return Sample(
        row,
        horizon,
        end,
        end,
        label,
        log_return,
        math.expm1(log_return),
        log_return / (0.01 * math.sqrt(horizon)),
        0.01,
        -0.01,
        0.06,
        -0.06,
    )


def small_config(**overrides: int) -> PredictionConfig:
    values = {
        "initial_train_days": 40,
        "validation_days": 20,
        "calibration_days": 20,
        "test_days": 30,
        "embargo_days": 2,
        "min_train": 20,
        "min_validation": 5,
        "min_calibration": 5,
    }
    values.update(overrides)
    return PredictionConfig(**values)


class TemporalValidationTests(unittest.TestCase):
    def test_purge_and_embargo_are_calendar_time_based(self) -> None:
        splits = walk_forward(tuple(sample(day) for day in range(125)), small_config())
        self.assertEqual(len(splits), 2)
        first = splits[0]
        self.assertEqual(first.boundaries["validation_start_ms"], 42 * DAY_MS)
        self.assertEqual(first.boundaries["calibration_start_ms"], 64 * DAY_MS)
        self.assertEqual(first.boundaries["test_start_ms"], 86 * DAY_MS)
        self.assertEqual(first.train[-1].row.origin_ms, 34 * DAY_MS)
        self.assertEqual(first.validation[-1].row.origin_ms, 56 * DAY_MS)
        self.assertEqual(first.calibration[-1].row.origin_ms, 78 * DAY_MS)
        self.assertEqual(first.test[-1].row.origin_ms, 108 * DAY_MS)
        for left, right in (
            (first.train, first.validation),
            (first.validation, first.calibration),
            (first.calibration, first.test),
        ):
            self.assertLess(max(s.target_available_ms for s in left), right[0].row.origin_ms)
        self.assertLess(first.test[-1].target_available_ms, splits[1].test[0].row.origin_ms)
        self.assertFalse(first.final_test)
        self.assertTrue(splits[-1].final_test)
        self.assertTrue(splits[-1].metadata["partial_test_window"])

    def test_missing_origins_are_not_replaced_or_counted_as_days(self) -> None:
        samples = tuple(sample(day) for day in range(125) if day not in (42, 43))
        first = walk_forward(samples, small_config())[0]
        self.assertEqual(first.validation[0].row.origin_ms, 44 * DAY_MS)
        self.assertEqual(first.train[-1].row.origin_ms, 36 * DAY_MS)
        self.assertNotIn(42 * DAY_MS, [s.row.origin_ms for s in first.validation])

    def test_equal_target_availability_is_purged(self) -> None:
        first = walk_forward(tuple(sample(day) for day in range(125)), small_config())[0]
        self.assertNotIn(35 * DAY_MS, [s.row.origin_ms for s in first.train])
        self.assertEqual(sample(35).target_available_ms, first.validation[0].row.origin_ms)

    def test_insufficient_history_and_purged_short_windows(self) -> None:
        self.assertEqual(walk_forward((), small_config()), ())
        self.assertEqual(walk_forward(tuple(sample(day) for day in range(89)), small_config()), ())
        self.assertEqual(
            walk_forward(tuple(sample(day, 90) for day in range(125)), small_config()), ()
        )

    def test_invalid_order_mixed_horizon_or_noncausal_feature_rejected(self) -> None:
        for samples in (
            (sample(1), sample(0)),
            (sample(0), sample(0)),
            (sample(0), sample(1, 30)),
            (replace(sample(0), target_available_ms=0),),
            (replace(sample(0), row=replace(sample(0).row, available_at_ms=(1,))),),
        ):
            with self.subTest(samples=samples), self.assertRaises(ValueError):
                walk_forward(samples, small_config())

    def test_later_fold_training_only_uses_available_labels(self) -> None:
        splits = walk_forward(tuple(sample(day) for day in range(240)), small_config())
        for earlier, later in zip(splits, splits[1:]):
            self.assertGreater(len(later.train), len(earlier.train))
            self.assertGreater(later.test[0].row.origin_ms, earlier.test[-1].row.origin_ms)
            self.assertLess(
                max(s.target_available_ms for s in later.train), later.validation[0].row.origin_ms
            )

    def test_future_append_does_not_change_a_completed_earlier_fold(self) -> None:
        prefix = tuple(sample(day) for day in range(125))
        extended = prefix + tuple(sample(day) for day in range(125, 240))
        prefix_first = walk_forward(prefix, small_config())[0]
        extended_first = walk_forward(extended, small_config())[0]
        self.assertEqual(prefix_first, extended_first)

    def test_determinism_and_horizon_spaced_origins(self) -> None:
        samples = tuple(sample(day) for day in range(125))
        self.assertEqual(
            walk_forward(samples, small_config()), walk_forward(samples, small_config())
        )
        self.assertEqual(independent_indices(samples), tuple(range(0, 125, 7)))
        delayed = (replace(sample(0), target_available_ms=9 * DAY_MS),) + samples[1:]
        self.assertEqual(independent_indices(delayed)[:2], (0, 9))


class ProbabilityMetricTests(unittest.TestCase):
    def test_uniform_reference_score_and_calibration(self) -> None:
        metrics = probability_metrics([0, 1, 2], [[1 / 3] * 3] * 3)
        self.assertAlmostEqual(metrics["brier"], 2 / 3)
        self.assertAlmostEqual(metrics["log_loss"], math.log(3))
        self.assertAlmostEqual(metrics["ece"], 0)
        self.assertEqual(metrics["observations"], 3)
        for bins in metrics["calibration_bins"].values():
            self.assertEqual(sum(bin_row["observations"] for bin_row in bins), 3)
            self.assertIsNone(bins[0]["mean_probability"])
            self.assertAlmostEqual(bins[3]["observed_frequency"], 1 / 3)

    def test_perfect_and_wrong_predictions_are_not_conflated(self) -> None:
        perfect = probability_metrics([0, 1, 2], [[1, 0, 0], [0, 1, 0], [0, 0, 1]])
        self.assertEqual(perfect["brier"], 0)
        self.assertEqual(perfect["log_loss"], 0)
        self.assertEqual(perfect["accuracy"], 1)
        self.assertEqual(perfect["ece"], 0)
        wrong = probability_metrics([0], [[0, 1, 0]])
        self.assertEqual(wrong["brier"], 2)
        self.assertAlmostEqual(wrong["log_loss"], -math.log(1e-15))

    def test_invalid_probability_simplex_and_classes_rejected(self) -> None:
        invalid = (
            ([0], [[0.2, 0.2, 0.2]]),
            ([0], [[-0.1, 0.6, 0.5]]),
            ([0], [[math.nan, 0, 1]]),
            ([0], [[True, 0, 0]]),
            ([3], [[1, 0, 0]]),
            ([True], [[1, 0, 0]]),
            ([0], [[0.5, 0.5]]),
            ([0], []),
        )
        for labels, probabilities in invalid:
            with (
                self.subTest(labels=labels, probabilities=probabilities),
                self.assertRaises(ValueError),
            ):
                probability_metrics(labels, probabilities)
        self.assertIsNone(probability_metrics([], [])["brier"])

    def test_return_interval_coverage_is_empirical(self) -> None:
        samples = tuple(sample(day, label=label) for day, label in enumerate((0, 1, 2)))
        forecasts = [{"lower": -0.05, "median": 0.0, "upper": 0.05}] * 3
        metrics = interval_coverage(samples, forecasts)
        self.assertEqual(metrics["covered_observations"], 2)
        self.assertAlmostEqual(metrics["coverage"], 2 / 3)
        self.assertAlmostEqual(metrics["mean_interval_width"], 0.1)
        with self.assertRaises(ValueError):
            interval_coverage(samples[:1], [{"lower": 1, "median": 0, "upper": 2}])

    def test_no_advantage_is_reported_as_no_edge(self) -> None:
        samples = tuple(sample(day, label=day % 3) for day in range(140))
        probabilities = [[1 / 3] * 3] * len(samples)
        comparison = paired_comparison(samples, probabilities, probabilities, seed=7)
        self.assertEqual(comparison["n_independent"], 20)
        self.assertEqual(comparison["brier_lift"], 0)
        self.assertEqual(comparison["log_loss_lift"], 0)
        self.assertEqual(comparison["brier_confidence_interval"], [0, 0])
        self.assertFalse(comparison["positive_edge"])
        self.assertEqual(
            comparison, paired_comparison(samples, probabilities, probabilities, seed=7)
        )

    def test_paired_scores_detect_only_supplied_synthetic_difference(self) -> None:
        samples = tuple(sample(day, label=1) for day in range(140))
        selected = [[0.1, 0.8, 0.1]] * len(samples)
        baseline = [[1 / 3] * 3] * len(samples)
        comparison = paired_comparison(samples, selected, baseline)
        self.assertGreater(comparison["brier_lift"], 0)
        self.assertGreater(comparison["log_loss_lift"], 0)
        self.assertTrue(comparison["positive_edge"])
        one = paired_comparison(samples[:1], selected[:1], baseline[:1])
        self.assertIsNone(one["brier_confidence_interval"])
        self.assertFalse(one["positive_edge"])


if __name__ == "__main__":
    unittest.main()
