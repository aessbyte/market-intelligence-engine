"""Synthetic software checks; no fixture is evidence of real predictive ability."""

from dataclasses import replace
import json
import math
import unittest

from market_intelligence.models import MarketError
from market_intelligence.prediction.contracts import DAY_MS, FeatureRow, PredictionConfig, Sample
from market_intelligence.prediction.features import FEATURE_NAMES
from market_intelligence.prediction.inference import (
    empirical_distribution,
    forecast,
    return_distribution,
)
from market_intelligence.prediction.models import calibrate_model, fit_model, predict_model
from market_intelligence.prediction.training import (
    TRAINING_VERSION,
    _train_horizon,
    bundle_digest,
    validate_bundle,
)
from market_intelligence.prediction.validation import walk_forward


def synthetic_samples(count: int = 120, horizon: int = 7) -> tuple[Sample, ...]:
    samples = []
    momentum = FEATURE_NAMES.index("return7")
    for index in range(count):
        label = index % 3
        values = [
            math.sin((index + 1) * (column + 1) * 0.17) for column in range(len(FEATURE_NAMES))
        ]
        values[momentum] = (label - 1) * 0.1
        values[FEATURE_NAMES.index("liquidity_low")] = 0.0
        origin = (100 + index) * DAY_MS
        row = FeatureRow(
            origin,
            100.0,
            0.02,
            tuple(values),
            "lateralizacao",
            (origin,) * len(values),
            ("simulated_test",) * len(values),
        )
        log_return = (label - 1) * 0.1
        scale = row.sigma * math.sqrt(horizon)
        samples.append(
            Sample(
                row,
                horizon,
                origin + horizon * DAY_MS,
                origin + horizon * DAY_MS,
                label,
                log_return,
                math.expm1(log_return),
                log_return / scale,
                0.5 * scale,
                -0.5 * scale,
                0.2,
                -0.2,
            )
        )
    return tuple(samples)


def sealed_bundle(model: dict, status: str = "UNVALIDATED_MODEL") -> dict:
    samples = synthetic_samples()
    config = PredictionConfig(min_class=2)
    entry = {
        "status": status,
        "model": model,
        "return_distribution": empirical_distribution(samples[: model["training_observations"]]),
        "limitations": ["no_supported_predictive_edge"] if status != "VALIDATED_MODEL" else [],
        "evidence": {"test_observations": 20},
    }
    bundle = {
        "training_version": TRAINING_VERSION,
        "configuration": config.to_dict(),
        "history_sha256": "0" * 64,
        "dataset": {
            "symbol": "BTCUSDT",
            "exchange": "binance",
            "market": "spot",
            "source": "binance_public",
            "dataset_version": "test_metadata",
        },
        "feature_names": list(FEATURE_NAMES),
        "available_at_ms": max(samples[-1].row.origin_ms, model["train_target_available_max_ms"]),
        "models": {str(h): entry for h in (7, 30, 90)},
    }
    bundle["bundle_sha256"] = bundle_digest(bundle)
    bundle["model_version"] = "model-" + bundle["bundle_sha256"][:16]
    return bundle


class PredictionModelTests(unittest.TestCase):
    def test_frequency_prior_is_explicit_and_training_only(self) -> None:
        samples = synthetic_samples(12)
        model = fit_model("frequency", samples, FEATURE_NAMES, PredictionConfig(min_class=2))
        self.assertEqual(model["class_counts"], [4, 4, 4])
        self.assertEqual(model["probabilities"], [1 / 3] * 3)
        self.assertIn("Dirichlet", model["prior"])
        self.assertAlmostEqual(sum(predict_model(model, samples[0].row.values)), 1)

    def test_scaler_uses_training_only_and_logistic_serializes(self) -> None:
        samples = synthetic_samples()
        model = fit_model("logistic", samples, FEATURE_NAMES, PredictionConfig(min_class=2))
        column = FEATURE_NAMES.index("return7")
        self.assertAlmostEqual(model["scaler"]["mean"][column], 0.0, places=14)
        restored = json.loads(json.dumps(model, allow_nan=False))
        self.assertEqual(
            predict_model(model, samples[1].row.values),
            predict_model(restored, samples[1].row.values),
        )
        self.assertAlmostEqual(sum(predict_model(model, (1e6,) * len(FEATURE_NAMES))), 1)
        self.assertAlmostEqual(model["scaler"]["mean"][column], 0.0, places=14)

    def test_portable_logistic_matches_sklearn_reference(self) -> None:
        import numpy as np
        from sklearn.linear_model import LogisticRegression
        from sklearn.preprocessing import StandardScaler

        samples = synthetic_samples()
        config = PredictionConfig(min_class=2)
        matrix = np.array([s.row.values for s in samples])
        scaler = StandardScaler().fit(matrix)
        reference = LogisticRegression(
            C=config.logistic_c, solver="lbfgs", max_iter=600, random_state=config.seed
        ).fit(scaler.transform(matrix), [s.label for s in samples])
        exported = fit_model("logistic", samples, FEATURE_NAMES, config)
        for sample in samples[::17]:
            expected = reference.predict_proba(scaler.transform([sample.row.values]))[0]
            actual = predict_model(exported, sample.row.values)
            for left, right in zip(expected, actual, strict=True):
                self.assertAlmostEqual(left, right, places=12)

    def test_portable_gradient_boosting_matches_sklearn_reference(self) -> None:
        from sklearn.ensemble import GradientBoostingClassifier

        samples = synthetic_samples()
        config = PredictionConfig(min_class=2, min_boosting_train=100)
        reference = GradientBoostingClassifier(
            n_estimators=40,
            learning_rate=0.05,
            max_depth=2,
            subsample=1.0,
            random_state=config.seed,
            n_iter_no_change=None,
        ).fit([s.row.values for s in samples], [s.label for s in samples])
        exported = fit_model("gradient_boosting", samples, FEATURE_NAMES, config)
        self.assertFalse(exported["parameters"]["early_stopping"])
        for sample in samples[::17]:
            expected = reference.predict_proba([sample.row.values])[0]
            actual = predict_model(exported, sample.row.values)
            for left, right in zip(expected, actual, strict=True):
                self.assertAlmostEqual(left, right, places=12)

    def test_calibration_preserves_parameters_and_simplex(self) -> None:
        samples = synthetic_samples()
        model = fit_model("momentum", samples[:60], FEATURE_NAMES, PredictionConfig(min_class=2))
        calibrated = calibrate_model(model, samples[60:])
        self.assertEqual(calibrated["bin_probabilities"], model["bin_probabilities"])
        self.assertEqual(calibrated["calibration"]["origin_start_ms"], samples[60].row.origin_ms)
        self.assertEqual(model["temperature"], 1.0)
        self.assertAlmostEqual(sum(predict_model(calibrated, samples[-1].row.values)), 1)

    def test_empirical_quantiles_use_training_returns_and_order(self) -> None:
        samples = synthetic_samples()
        distribution = empirical_distribution(samples)
        result = return_distribution(distribution, [0.2, 0.5, 0.3], 0.02, 7)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertLessEqual(result["lower"], result["median"])
        self.assertLessEqual(result["median"], result["upper"])
        self.assertAlmostEqual(result["lower"], math.expm1(-0.1))
        self.assertEqual(result["interval_nominal_coverage"], 0.8)
        self.assertEqual(result["observations"], len(samples))

    def test_insufficient_history_returns_no_model(self) -> None:
        entry, report = _train_horizon(synthetic_samples(100), 7, PredictionConfig(), True)
        self.assertEqual(entry["status"], "INSUFFICIENT_EVIDENCE")
        self.assertIsNone(entry["model"])
        self.assertIsNone(report["selected_strategy_metrics"])

    def test_no_edge_public_probabilities_are_null(self) -> None:
        samples = synthetic_samples(130)
        model = fit_model("frequency", samples[:120], FEATURE_NAMES, PredictionConfig(min_class=2))
        bundle = sealed_bundle(model)
        results = forecast(bundle, samples[-1].row, "BTCUSDT", samples[-1].row.origin_ms)
        for result in results:
            self.assertEqual(result["status"], "UNVALIDATED_MODEL")
            self.assertIsNone(result["probabilities"])
            self.assertEqual(
                result["experimental_diagnostics"]["status"], "EXPERIMENTAL_NOT_VALIDATED"
            )

    def test_mismatches_future_model_and_low_liquidity_abstain(self) -> None:
        samples = synthetic_samples(130)
        model = fit_model("frequency", samples[:120], FEATURE_NAMES, PredictionConfig(min_class=2))
        bundle = sealed_bundle(model)
        row = samples[-1].row
        values = list(row.values)
        values[FEATURE_NAMES.index("liquidity_low")] = 1.0
        for altered_row, symbol, as_of, source in (
            (row, "ETHUSDT", row.origin_ms, "binance_public"),
            (samples[-5].row, "BTCUSDT", samples[-5].row.origin_ms, "binance_public"),
            (row, "BTCUSDT", row.origin_ms, "simulated"),
            (replace(row, values=tuple(values)), "BTCUSDT", row.origin_ms, "binance_public"),
            (replace(row, regime="indeterminado"), "BTCUSDT", row.origin_ms, "binance_public"),
            (
                replace(row, values=(1e6, *row.values[1:])),
                "BTCUSDT",
                row.origin_ms,
                "binance_public",
            ),
            (replace(row, values=row.values[:1]), "BTCUSDT", row.origin_ms, "binance_public"),
        ):
            result = forecast(bundle, altered_row, symbol, as_of, source)[0]
            self.assertEqual(result["status"], "INSUFFICIENT_EVIDENCE")
            self.assertIsNone(result["probabilities"])
            self.assertIsNone(result["experimental_diagnostics"])

    def test_bundle_checksum_rejects_mutation(self) -> None:
        model = fit_model(
            "frequency", synthetic_samples(), FEATURE_NAMES, PredictionConfig(min_class=2)
        )
        bundle = sealed_bundle(model)
        validate_bundle(bundle)
        bundle["configuration"]["seed"] = 1
        with self.assertRaises(MarketError):
            validate_bundle(bundle)

    def test_final_test_cannot_select_refit_or_calibrate_model(self) -> None:
        samples = synthetic_samples(620)
        config = PredictionConfig(
            initial_train_days=120,
            validation_days=90,
            calibration_days=90,
            test_days=100,
            min_train=80,
            min_validation=30,
            min_calibration=30,
            min_class=2,
            min_boosting_train=10000,
        )
        first_entry, first_report = _train_horizon(samples, 7, config, True)
        final = walk_forward(samples, config)[-1]
        held_out = {sample.row.origin_ms for sample in final.test}
        changed = tuple(
            replace(sample, label=2 - sample.label) if sample.row.origin_ms in held_out else sample
            for sample in samples
        )
        second_entry, second_report = _train_horizon(changed, 7, config, True)
        self.assertEqual(first_entry["model"], second_entry["model"])
        self.assertEqual(first_entry["return_distribution"], second_entry["return_distribution"])
        self.assertEqual(
            first_report["folds"][-1]["selected_model"],
            second_report["folds"][-1]["selected_model"],
        )
        self.assertFalse(first_report["final_model_refit_after_test"])

    def test_fixed_seed_and_config_repeat_identically(self) -> None:
        samples = synthetic_samples()
        config = PredictionConfig(min_class=2)
        self.assertEqual(
            fit_model("logistic", samples, FEATURE_NAMES, config),
            fit_model("logistic", samples, FEATURE_NAMES, config),
        )


if __name__ == "__main__":
    unittest.main()
