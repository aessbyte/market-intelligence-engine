"""Synthetic fixtures verify software only, never real predictive performance."""

from dataclasses import replace
import math
import statistics
import unittest

from market_intelligence.models import Candle, MarketError
from market_intelligence.prediction.contracts import DAY_MS, FeatureRow, PredictionConfig
from market_intelligence.prediction.features import FEATURE_NAMES, build_features
from market_intelligence.prediction.targets import build_samples


def synthetic_history(count: int = 180) -> tuple[Candle, ...]:
    closes = [100 + 0.07 * i + 4 * math.sin(i / 4) + math.sin(i / 11) for i in range(count)]
    return tuple(
        Candle(
            i * DAY_MS,
            (i + 1) * DAY_MS - 1,
            close,
            close + 1,
            close - 1,
            close,
            10 + (i % 7),
            close * (10 + i % 7),
            5,
        )
        for i, close in enumerate(closes)
    )


def synthetic_range(tail: list[tuple[float, float, float, float, float]]) -> tuple[Candle, ...]:
    closes = [100, 104, 100, 96] * 25
    history = [
        Candle(i * DAY_MS, (i + 1) * DAY_MS - 1, p, p + 1, p - 1, p, 10, p * 10, 5)
        for i, p in enumerate(closes)
    ]
    for opening, high, low, close, volume in tail:
        index = len(history)
        history.append(
            Candle(
                index * DAY_MS,
                (index + 1) * DAY_MS - 1,
                opening,
                high,
                low,
                close,
                volume,
                close * volume,
                5,
            )
        )
    return tuple(history)


def feature(row: FeatureRow, name: str) -> float:
    return row.values[FEATURE_NAMES.index(name)]


class FeatureTests(unittest.TestCase):
    def test_reference_returns_sigma_and_sources(self) -> None:
        history = synthetic_history(140)
        rows = build_features(history)
        row = rows[-1]
        self.assertAlmostEqual(
            feature(row, "return7"), math.log(history[-1].close / history[-8].close)
        )
        changes = [math.log(b.close / a.close) for a, b in zip(history[-31:], history[-30:])]
        self.assertAlmostEqual(row.sigma, statistics.pstdev(changes))
        self.assertEqual(feature(row, "sigma_observed"), row.sigma)
        self.assertEqual(len(row.values), len(FEATURE_NAMES))
        self.assertEqual(len(row.sources), len(FEATURE_NAMES))
        self.assertEqual(len(row.available_at_ms), len(FEATURE_NAMES))
        self.assertTrue(all(timestamp <= row.origin_ms for timestamp in row.available_at_ms))
        self.assertTrue(all("D1" in source and "input_ohlcv" in source for source in row.sources))
        self.assertEqual(
            sum(
                feature(row, "regime_" + name)
                for name in ("alta", "baixa", "lateralizacao", "indeterminado")
            ),
            1,
        )

    def test_prefix_causality_for_every_available_origin(self) -> None:
        history = synthetic_history(160)
        complete = build_features(history)
        for count in range(100, len(history) + 1):
            with self.subTest(count=count):
                self.assertEqual(build_features(history[:count]), complete[: count - 99])

    def test_future_extremes_do_not_rewrite_past(self) -> None:
        history = synthetic_history(105)
        future = (
            Candle(105 * DAY_MS, 106 * DAY_MS - 1, 500, 510, 490, 500, 1000, 500000, 100),
            Candle(106 * DAY_MS, 107 * DAY_MS - 1, 10, 11, 9, 10, 1, 10, 1),
        )
        self.assertEqual(build_features(history), build_features(history + future)[:6])

    def test_spring_candidate_confirmation_then_invalidation_remain_causal(self) -> None:
        history = synthetic_range(
            [(98, 101, 93, 99, 10), (99, 103, 98, 102, 10), (92, 93, 91, 92, 10)]
        )
        rows = build_features(history)
        self.assertEqual(feature(rows[1], "spring_candidate_12d"), 1)
        self.assertEqual(feature(rows[1], "spring_confirmed_12d"), 0)
        self.assertEqual(feature(rows[2], "spring_confirmed_12d"), 1)
        self.assertEqual(feature(rows[3], "spring_confirmed_12d"), 0)
        self.assertEqual(build_features(history[:101]), rows[:2])
        self.assertEqual(build_features(history[:102]), rows[:3])

    def test_upthrust_and_pivots_confirm_only_when_known(self) -> None:
        history = synthetic_range(
            [(102, 107, 99, 101, 10), (101, 102, 97, 98, 10), (108, 109, 107, 108, 10)]
        )
        rows = build_features(history)
        self.assertEqual(feature(rows[1], "upthrust_candidate_12d"), 1)
        self.assertEqual(feature(rows[2], "upthrust_confirmed_12d"), 1)
        self.assertEqual(feature(rows[3], "upthrust_confirmed_12d"), 0)
        # The 107 high at day101 is unavailable until day103 (right_bars=2).
        self.assertAlmostEqual(feature(rows[1], "confirmed_high_distance_fraction"), 101 / 105 - 1)
        self.assertAlmostEqual(feature(rows[2], "confirmed_high_distance_fraction"), 98 / 105 - 1)

    def test_short_flat_zero_volume_and_gap(self) -> None:
        self.assertEqual(build_features(synthetic_history(99)), ())
        history = tuple(
            replace(c, open=100, high=100, low=100, close=100, volume=0, quote_volume=0, trades=0)
            for c in synthetic_history(105)
        )
        row = build_features(history)[-1]
        self.assertEqual(row.sigma, 0)
        self.assertEqual(feature(row, "volume_missing"), 1)
        self.assertEqual(feature(row, "volume_variance_missing"), 1)
        self.assertEqual(feature(row, "liquidity_low"), 1)
        self.assertEqual(feature(row, "range_compression_missing"), 1)
        self.assertTrue(all(math.isfinite(value) for value in row.values))
        with self.assertRaises(MarketError):
            build_features(synthetic_history(105)[:101] + synthetic_history(105)[102:])

    def test_determinism_and_window_configuration(self) -> None:
        history = synthetic_history(300)
        config = PredictionConfig(feature_window=120)
        rows = build_features(history, config)
        self.assertEqual(rows, build_features(history, config))
        self.assertEqual(rows[:16], build_features(history[:115], config))
        self.assertIn("trailing_window=120", rows[-1].sources[0])


class TargetTests(unittest.TestCase):
    def test_calendar_endpoint_and_causal_threshold(self) -> None:
        history = synthetic_history(200)
        rows = build_features(history)
        for horizon in (7, 30, 90):
            samples = build_samples(history, rows, horizon)
            sample = samples[0]
            self.assertEqual(sample.end_ms, sample.row.origin_ms + horizon * DAY_MS)
            self.assertEqual(sample.target_available_ms, sample.end_ms)
            self.assertAlmostEqual(
                sample.upper_log_threshold, 0.5 * sample.row.sigma * math.sqrt(horizon)
            )
            self.assertEqual(sample.lower_log_threshold, -sample.upper_log_threshold)
            self.assertAlmostEqual(
                sample.log_return, math.log(history[99 + horizon].close / history[99].close)
            )
            self.assertAlmostEqual(sample.return_value, math.expm1(sample.log_return))
            self.assertEqual(len(samples), len(rows) - horizon)

    def test_endpoint_return_and_path_excursions_are_distinct(self) -> None:
        history = list(synthetic_history(107))
        origin = history[99].close
        for index in range(100, 107):
            history[index] = replace(
                history[index], open=origin, close=origin, high=origin * 2, low=origin / 2
            )
        rows = build_features(tuple(history))
        sample = build_samples(tuple(history), rows[:1], 7)[0]
        self.assertEqual(sample.label, 1)
        self.assertEqual(sample.return_value, 0)
        self.assertEqual(sample.maximum_favorable_excursion, 1)
        self.assertEqual(sample.maximum_adverse_excursion, -0.5)

    def test_missing_future_and_zero_sigma_are_not_labelled(self) -> None:
        history = synthetic_history(105)
        rows = build_features(history)
        self.assertEqual(build_samples(history, rows, 7), ())
        self.assertEqual(build_samples(history, (replace(rows[0], sigma=0),), 1), ())
        self.assertEqual(build_samples(history, (replace(rows[0], sigma=float("nan")),), 1), ())

    def test_all_classes_cover_valid_results(self) -> None:
        history = list(synthetic_history(107))
        rows = build_features(tuple(history))
        row = rows[0]
        expected = ((row.close * 0.5, 0), (row.close, 1), (row.close * 2, 2))
        for close, label in expected:
            history[106] = replace(
                history[106], open=close, high=close + 1, low=close - 1, close=close
            )
            sample = build_samples(tuple(history), (row,), 7)[0]
            self.assertEqual(sample.label, label)

    def test_both_exact_threshold_boundaries_are_neutral(self) -> None:
        history = list(synthetic_history(104))
        # sqrt(4) * label_sigma(0.5) == 1 exactly; the +/- boundary is ln(2).
        row = replace(build_features(tuple(history))[0], sigma=math.log(2))
        for endpoint in (row.close * 2, row.close / 2):
            history[103] = replace(
                history[103], open=endpoint, high=endpoint + 1, low=endpoint - 1, close=endpoint
            )
            sample = build_samples(tuple(history), (row,), 4)[0]
            self.assertEqual(abs(sample.log_return), sample.upper_log_threshold)
            self.assertEqual(sample.label, 1)

    def test_future_append_leaves_existing_labels_unchanged(self) -> None:
        history = synthetic_history(190)
        short = history[:150]
        short_samples = build_samples(short, build_features(short), 30)
        full_samples = build_samples(history, build_features(history), 30)
        self.assertEqual(short_samples, full_samples[: len(short_samples)])

    def test_invalid_origins_and_future_metadata_fail_closed(self) -> None:
        history = synthetic_history(110)
        row = build_features(history)[0]
        with self.assertRaises(MarketError):
            build_samples(history, (replace(row, close=row.close + 1),), 7)
        with self.assertRaises(MarketError):
            build_samples(history, (replace(row, available_at_ms=(row.origin_ms + 1,)),), 7)
        for horizon in (0, -1, True, 1.5):
            with self.assertRaises(MarketError):
                build_samples(history, (row,), horizon)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
