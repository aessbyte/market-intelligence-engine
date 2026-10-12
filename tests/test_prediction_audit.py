"""Adversarial audit checks: fixture populations are explicitly synthetic."""

import copy
from dataclasses import replace
import unittest

from market_intelligence.models import MarketError
from market_intelligence.engine import _validate_prediction_history
from market_intelligence.prediction.contracts import PredictionConfig
from market_intelligence.prediction.dataset import history_digest
from market_intelligence.prediction.features import FEATURE_NAMES
from market_intelligence.prediction.models import calibrate_model, fit_model
from market_intelligence.prediction.training import bundle_digest, validate_bundle

from tests.test_prediction_models import sealed_bundle, synthetic_samples
from tests.test_prediction_features import synthetic_history


def reseal(bundle: dict) -> dict:
    """Recompute integrity checksum; integrity alone cannot validate parameters."""
    bundle["bundle_sha256"] = bundle_digest(bundle)
    bundle["model_version"] = "model-" + bundle["bundle_sha256"][:16]
    return bundle


class PredictionAuditTests(unittest.TestCase):
    def history_contract(self) -> tuple:
        candles = synthetic_history(180)
        until = candles[-1].close_time_ms + 1
        metadata = {
            "first_observed_open_ms": candles[0].open_time_ms,
            "last_closed_available_ms": until,
        }
        bundle = {"dataset": metadata, "history_sha256": history_digest(candles, until)}
        return candles, metadata, bundle

    def test_history_contract_allows_identical_prefix_with_right_append(self) -> None:
        candles, metadata, bundle = self.history_contract()
        extended = synthetic_history(190)
        self.assertEqual(candles, extended[: len(candles)])
        _validate_prediction_history(extended, metadata, bundle)

    def test_history_contract_rejects_shortened_initial_context(self) -> None:
        candles, metadata, bundle = self.history_contract()
        shifted = dict(metadata, first_observed_open_ms=candles[1].open_time_ms)
        with self.assertRaisesRegex(MarketError, "historical_start_does_not_match_model_context"):
            _validate_prediction_history(candles[1:], shifted, bundle)

    def test_history_contract_rejects_revised_old_candle(self) -> None:
        candles, metadata, bundle = self.history_contract()
        revised = (replace(candles[0], volume=candles[0].volume + 1), *candles[1:])
        with self.assertRaisesRegex(MarketError, "training_history_revised_or_missing"):
            _validate_prediction_history(revised, metadata, bundle)

    def test_history_contract_rejects_missing_training_endpoint(self) -> None:
        candles, metadata, bundle = self.history_contract()
        with self.assertRaisesRegex(MarketError, "does_not_include_complete_training_history"):
            _validate_prediction_history(candles[:-1], metadata, bundle)

    def test_checksum_does_not_authorize_invalid_probability_vector(self) -> None:
        model = fit_model("frequency", synthetic_samples(), FEATURE_NAMES, PredictionConfig())
        for probabilities in ([0.5, 0.5], [-0.2, 0.4, 0.8], [0.2, 0.2, 0.2]):
            corrupted = sealed_bundle(copy.deepcopy(model))
            corrupted["models"]["7"]["model"]["probabilities"] = probabilities
            with self.subTest(probabilities=probabilities), self.assertRaises(MarketError):
                validate_bundle(reseal(corrupted))

    def test_invalid_drift_dimensions_and_scales_are_rejected(self) -> None:
        model = fit_model("frequency", synthetic_samples(), FEATURE_NAMES, PredictionConfig())
        for field, replacement in (
            ("drift_mean", model["drift_mean"][:-1]),
            ("drift_scale", [0.0, *model["drift_scale"][1:]]),
            ("class_counts", [40, 40]),
            ("feature_names", list(FEATURE_NAMES[:-1])),
        ):
            corrupted = sealed_bundle(copy.deepcopy(model))
            corrupted["models"]["7"]["model"][field] = replacement
            with self.subTest(field=field), self.assertRaises(MarketError):
                validate_bundle(reseal(corrupted))

    def test_invalid_logistic_dimensions_rejected_before_inference(self) -> None:
        model = fit_model("logistic", synthetic_samples(), FEATURE_NAMES, PredictionConfig())
        for field, replacement in (
            ("coefficients", model["coefficients"][:2]),
            ("intercept", model["intercept"][:2]),
            ("scaler", {"mean": model["scaler"]["mean"], "scale": [0.0] * len(FEATURE_NAMES)}),
        ):
            corrupted = sealed_bundle(copy.deepcopy(model))
            corrupted["models"]["7"]["model"][field] = replacement
            with self.subTest(field=field), self.assertRaises(MarketError):
                validate_bundle(reseal(corrupted))

    def test_tree_cycle_is_rejected_without_traversing_it(self) -> None:
        model = fit_model(
            "gradient_boosting",
            synthetic_samples(),
            FEATURE_NAMES,
            PredictionConfig(min_boosting_train=100),
        )
        corrupted = sealed_bundle(copy.deepcopy(model))
        tree = corrupted["models"]["7"]["model"]["trees"][0][0]
        tree["left"][0] = 0
        with self.assertRaises(MarketError):
            validate_bundle(reseal(corrupted))

    def test_tree_feature_out_of_bounds_is_rejected(self) -> None:
        model = fit_model(
            "gradient_boosting",
            synthetic_samples(),
            FEATURE_NAMES,
            PredictionConfig(min_boosting_train=100),
        )
        corrupted = sealed_bundle(copy.deepcopy(model))
        corrupted["models"]["7"]["model"]["trees"][0][0]["feature"][0] = len(FEATURE_NAMES)
        with self.assertRaises(MarketError):
            validate_bundle(reseal(corrupted))

    def test_calibration_with_missing_class_abstains(self) -> None:
        samples = synthetic_samples(120)
        model = fit_model("frequency", samples, FEATURE_NAMES, PredictionConfig())
        one_class = tuple(replace(sample, label=2) for sample in samples)
        result = calibrate_model(model, one_class, PredictionConfig())
        self.assertEqual(result["temperature"], 1.0)
        self.assertEqual(result["calibration"]["status"], "INSUFFICIENT_EVIDENCE")
        self.assertIn(
            "insufficient_calibration_class_support", result["calibration"]["limitations"]
        )

    def test_overlapping_calibration_count_is_not_independent_support(self) -> None:
        samples = synthetic_samples(120, horizon=90)
        model = fit_model("frequency", samples, FEATURE_NAMES, PredictionConfig())
        result = calibrate_model(model, samples, PredictionConfig())
        self.assertEqual(result["temperature"], 1.0)
        self.assertEqual(result["calibration"]["status"], "INSUFFICIENT_EVIDENCE")
        self.assertLess(result["calibration"]["n_independent"], 10)
        self.assertIn(
            "insufficient_independent_calibration_origins", result["calibration"]["limitations"]
        )

    def test_sufficient_calibration_reports_population_support(self) -> None:
        samples = synthetic_samples(120, horizon=7)
        model = fit_model("frequency", samples, FEATURE_NAMES, PredictionConfig())
        result = calibrate_model(model, samples, PredictionConfig())
        self.assertEqual(result["calibration"]["status"], "CALIBRATED")
        self.assertEqual(result["calibration"]["class_counts"], [40, 40, 40])
        self.assertGreaterEqual(result["calibration"]["n_independent"], 10)
