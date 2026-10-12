"""Frozen chronological training, calibration and out-of-sample reporting."""

import hashlib
import json
import math
from importlib.metadata import version
import platform
from typing import Any

from ..models import MarketError
from .contracts import CLASSES, HORIZONS, PredictionConfig, Sample
from .dataset import history_digest, validate_dataset
from .features import FEATURE_NAMES, build_features
from .inference import empirical_distribution, return_distribution
from .metrics import interval_coverage, paired_comparison, probability_metrics
from .models import (
    MODEL_KINDS,
    calibrate_model,
    fit_model,
    predict_model,
    validate_model_parameters,
)
from .targets import build_samples
from .validation import walk_forward

TRAINING_VERSION = "walk-forward-probabilistic-v1"


def bundle_digest(bundle: dict[str, Any]) -> str:
    payload = {
        key: value for key, value in bundle.items() if key not in ("bundle_sha256", "model_version")
    }
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )
    return hashlib.sha256(encoded.encode()).hexdigest()


def validate_bundle(bundle: Any) -> dict[str, Any]:
    if not isinstance(bundle, dict) or bundle.get("training_version") != TRAINING_VERSION:
        raise MarketError("unsupported model bundle")
    try:
        config = PredictionConfig.from_dict(bundle["configuration"])
        if bundle.get("bundle_sha256") != bundle_digest(bundle):
            raise MarketError("model bundle checksum mismatch")
        if bundle["model_version"] != "model-" + bundle["bundle_sha256"][:16]:
            raise MarketError("model version inconsistent with content checksum")
        if bundle["feature_names"] != list(FEATURE_NAMES):
            raise MarketError("model feature contract mismatch")
        if (
            not isinstance(bundle.get("history_sha256"), str)
            or len(bundle["history_sha256"]) != 64
            or any(character not in "0123456789abcdef" for character in bundle["history_sha256"])
        ):
            raise MarketError("invalid historical input checksum")
        if type(bundle["available_at_ms"]) is not int or bundle["available_at_ms"] < 0:
            raise MarketError("invalid model availability")
        if (
            not isinstance(bundle["dataset"], dict)
            or bundle["dataset"].get("exchange") != "binance"
            or bundle["dataset"].get("market") != "spot"
            or bundle["dataset"].get("source") not in ("binance_public", "simulated")
            or not isinstance(bundle["dataset"].get("symbol"), str)
        ):
            raise MarketError("invalid model dataset population")
        if not isinstance(bundle["models"], dict) or set(bundle["models"]) != {
            str(h) for h in HORIZONS
        }:
            raise MarketError("missing forecast horizon models")
        for entry in bundle["models"].values():
            if not isinstance(entry, dict) or entry.get("status") not in (
                "INSUFFICIENT_EVIDENCE",
                "UNVALIDATED_MODEL",
                "VALIDATED_MODEL",
            ):
                raise MarketError("invalid horizon model status")
            model = entry.get("model")
            if model is None and (
                entry["status"] == "VALIDATED_MODEL" or entry.get("return_distribution") is not None
            ):
                raise MarketError("model status or return distribution requires fitted parameters")
            if model is not None:
                validate_model_parameters(model, FEATURE_NAMES)
                if model.get("classes") != list(CLASSES) or model.get("feature_names") != list(
                    FEATURE_NAMES
                ):
                    raise MarketError("fitted model classes/features mismatch")
                if (
                    model["train_target_available_max_ms"] > bundle["available_at_ms"]
                    or model.get("calibration", {}).get("target_available_max_ms", 0)
                    > bundle["available_at_ms"]
                    or entry["return_distribution"]["training_target_available_max_ms"]
                    > bundle["available_at_ms"]
                ):
                    raise MarketError("fitted model depends on unavailable target information")
                distribution = entry["return_distribution"]
                groups = distribution.get("samples")
                if (
                    not isinstance(groups, list)
                    or len(groups) != 3
                    or any(
                        not isinstance(group, list)
                        or any(
                            isinstance(value, bool)
                            or not isinstance(value, (int, float))
                            or not math.isfinite(value)
                            for value in group
                        )
                        for group in groups
                    )
                ):
                    raise MarketError("invalid empirical return distribution")
                if (
                    sum(len(group) for group in groups) != distribution.get("observations")
                    or distribution.get("observations") != model["training_observations"]
                    or distribution.get("quantile_levels") != [0.05, 0.1, 0.5, 0.9, 0.95]
                    or distribution.get("interval_nominal_coverage") != 0.8
                ):
                    raise MarketError("empirical distribution population or quantiles mismatch")
                if entry["status"] == "VALIDATED_MODEL":
                    evidence = entry["evidence"]
                    if (
                        model["kind"] in ("frequency", "momentum")
                        or model.get("calibration", {}).get("status") != "CALIBRATED"
                        or evidence.get("independent_observations", 0)
                        < config.min_independent_tests
                        or not evidence.get("frozen_final_model_comparison", {}).get(
                            "positive_edge", False
                        )
                        or evidence["frozen_final_model_comparison"].get("n_independent", 0)
                        < config.min_independent_tests
                    ):
                        raise MarketError(
                            "validated model status lacks required frozen holdout evidence"
                        )
        # Reject non-JSON/nonfinite artifacts rather than deserializing executable code.
        json.dumps(bundle, allow_nan=False)
        return bundle
    except (KeyError, TypeError, ValueError, IndexError, AttributeError, OverflowError) as exc:
        raise MarketError(f"invalid model bundle: {exc}") from exc


def _predictions(model: dict[str, Any], samples: tuple[Sample, ...]) -> list[list[float]]:
    return [predict_model(model, sample.row.values) for sample in samples]


def _selection_key(kind: str, metrics: dict[str, Any]) -> tuple[float, float, int]:
    return (
        round(float(metrics["brier"]), 12),
        round(float(metrics["log_loss"]), 12),
        MODEL_KINDS.index(kind),
    )


def _train_horizon(
    samples: tuple[Sample, ...],
    horizon: int,
    config: PredictionConfig,
    real_population: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    splits = walk_forward(samples, config)
    all_samples: list[Sample] = []
    all_selected: list[list[float]] = []
    all_baseline: list[list[float]] = []
    all_magnitudes: list[dict[str, Any]] = []
    candidate_probabilities: dict[str, list[list[float]]] = {kind: [] for kind in MODEL_KINDS}
    candidate_samples: dict[str, list[Sample]] = {kind: [] for kind in MODEL_KINDS}
    candidate_references: dict[str, list[list[float]]] = {kind: [] for kind in MODEL_KINDS}
    candidate_folds: dict[str, list[int]] = {kind: [] for kind in MODEL_KINDS}
    folds: list[dict[str, Any]] = []
    terminal_model: dict[str, Any] | None = None
    terminal_distribution: dict[str, Any] | None = None
    maximum_available = 0
    for split in splits:
        if (
            len(split.train) < config.min_train
            or len(split.validation) < config.min_validation
            or len(split.calibration) < config.min_calibration
            or not split.test
        ):
            continue
        fitted: dict[str, dict[str, Any]] = {}
        validation_metrics: dict[str, dict[str, Any]] = {}
        skips: dict[str, str] = {}
        for kind in MODEL_KINDS:
            try:
                model = fit_model(kind, split.train, FEATURE_NAMES, config)
                validation_metrics[kind] = probability_metrics(
                    [sample.label for sample in split.validation],
                    _predictions(model, split.validation),
                )
                fitted[kind] = model
            except MarketError as exc:
                skips[kind] = str(exc)
        if not fitted:
            continue
        selected_kind = min(fitted, key=lambda kind: _selection_key(kind, validation_metrics[kind]))
        baseline_kind = min(
            (kind for kind in ("frequency", "momentum") if kind in fitted),
            key=lambda kind: _selection_key(kind, validation_metrics[kind]),
        )
        # No test metrics exist until selection and calibration have been frozen.
        calibrated = {
            kind: calibrate_model(model, split.calibration, config)
            for kind, model in fitted.items()
        }
        selected = calibrated[selected_kind]
        distribution = empirical_distribution(split.train)
        test_metrics = {}
        test_predictions = {}
        for kind, model in calibrated.items():
            probabilities = _predictions(model, split.test)
            test_predictions[kind] = probabilities
            test_metrics[kind] = probability_metrics(
                [sample.label for sample in split.test], probabilities
            )
            candidate_probabilities[kind].extend(probabilities)
            candidate_samples[kind].extend(split.test)
            candidate_folds[kind].append(split.fold_id)
        for kind in calibrated:
            candidate_references[kind].extend(test_predictions[baseline_kind])
        selected_probabilities = test_predictions[selected_kind]
        magnitudes = [
            return_distribution(distribution, probabilities, sample.row.sigma, horizon)
            for sample, probabilities in zip(split.test, selected_probabilities, strict=True)
        ]
        valid_magnitudes = [magnitude for magnitude in magnitudes if magnitude is not None]
        coverage = (
            interval_coverage(split.test, valid_magnitudes)
            if len(valid_magnitudes) == len(split.test)
            else None
        )
        all_samples.extend(split.test)
        all_selected.extend(selected_probabilities)
        all_baseline.extend(test_predictions[baseline_kind])
        all_magnitudes.extend(valid_magnitudes)
        maximum_available = max(maximum_available, max(s.target_available_ms for s in split.test))
        folds.append(
            {
                "fold_id": split.fold_id,
                "final_test": split.final_test,
                "boundaries": split.boundaries,
                "split_metadata": split.metadata,
                "observations": {
                    name: len(getattr(split, name))
                    for name in ("train", "validation", "calibration", "test")
                },
                "selected_model": selected_kind,
                "reference_baseline": baseline_kind,
                "selection": "validation_Brier_then_log_loss_then_simplicity; never_test",
                "validation_metrics": validation_metrics,
                "test_metrics": test_metrics,
                "calibration": {kind: model["calibration"] for kind, model in calibrated.items()},
                "skipped_models": skips,
                "return_interval_coverage": coverage,
                "paired_baseline_comparison": paired_comparison(
                    split.test, selected_probabilities, test_predictions[baseline_kind], config.seed
                ),
            }
        )
        terminal_model, terminal_distribution = selected, distribution
    limitations = []
    report: dict[str, Any] = {
        "horizon_days": horizon,
        "classes": list(CLASSES),
        "eligible_samples": len(samples),
        "folds": folds,
        "model_comparisons": {},
        "test_preserved_until_evaluation": True,
        "hyperparameters": {
            "logistic_c": config.logistic_c,
            "seed": config.seed,
            "chosen_from": "fixed_configuration_not_test",
        },
        "class_threshold": "predefined_label_sigma_times_origin_sigma_times_sqrt_calendar_days",
        "population": "single_symbol_binance_spot; no_claim_of_general_or_trading_edge",
    }
    if not all_samples or terminal_model is None:
        limitations.append("insufficient_purged_train_validation_calibration_test_history")
        report.update(
            status="INSUFFICIENT_EVIDENCE",
            limitations=limitations,
            selected_strategy_metrics=None,
            paired_baseline_comparison=None,
            return_interval_coverage=None,
        )
        return {
            "status": "INSUFFICIENT_EVIDENCE",
            "model": None,
            "return_distribution": None,
            "limitations": limitations,
            "available_at_ms": 0,
            "evidence": {"test_observations": 0, "folds": 0},
        }, report
    for kind in MODEL_KINDS:
        if candidate_samples[kind]:
            report["model_comparisons"][kind] = probability_metrics(
                [sample.label for sample in candidate_samples[kind]], candidate_probabilities[kind]
            )
            report["model_comparisons"][kind]["fold_ids"] = candidate_folds[kind]
            report["model_comparisons"][kind]["same_population_reference_baseline_metrics"] = (
                probability_metrics(
                    [sample.label for sample in candidate_samples[kind]], candidate_references[kind]
                )
            )
            report["model_comparisons"][kind]["comparison_note"] = (
                "compare_only_same_fold_population; nonlinear_model_may_have_fewer_folds"
            )
        else:
            report["model_comparisons"][kind] = {"status": "unavailable", "observations": 0}
    selected_metrics = probability_metrics([sample.label for sample in all_samples], all_selected)
    comparison = paired_comparison(tuple(all_samples), all_selected, all_baseline, config.seed)
    final_metrics = folds[-1]["test_metrics"][folds[-1]["selected_model"]]
    final_comparison = folds[-1]["paired_baseline_comparison"]
    if comparison["n_independent"] < config.min_independent_tests:
        limitations.append("insufficient_independent_out_of_sample_observations")
    if len(folds) < 3:
        limitations.append("insufficient_temporal_folds_for_stability")
    if not comparison["positive_edge"]:
        limitations.append("no_supported_improvement_over_validation_selected_simple_baseline")
    if terminal_model["kind"] in ("frequency", "momentum"):
        limitations.append("terminal_simple_baseline_has_no_supported_predictive_edge")
    if not final_comparison["positive_edge"]:
        limitations.append("frozen_final_model_has_no_supported_holdout_improvement")
    if final_comparison["n_independent"] < config.min_independent_tests:
        limitations.append("insufficient_independent_frozen_final_model_tests")
    if (
        selected_metrics["ece"] > config.max_calibration_error
        or final_metrics["ece"] > config.max_calibration_error
    ):
        limitations.append("out_of_sample_probabilities_poorly_calibrated")
    if min(terminal_model["class_counts"]) < config.min_class:
        limitations.append("insufficient_training_class_support")
    if terminal_model["calibration"]["status"] != "CALIBRATED":
        limitations.append("frozen_model_calibration_has_insufficient_evidence")
    if not real_population:
        limitations.append("synthetic_data_are_not_predictive_evidence")
    coverage = (
        interval_coverage(tuple(all_samples), all_magnitudes)
        if len(all_magnitudes) == len(all_samples)
        else None
    )
    final_coverage = folds[-1]["return_interval_coverage"]
    if (
        coverage is None
        or final_coverage is None
        or coverage["coverage"] < 0.65
        or final_coverage["coverage"] < 0.65
    ):
        limitations.append("return_interval_coverage_below_predefined_0.65_floor_for_0.8_nominal")
    status = "VALIDATED_MODEL" if not limitations else "UNVALIDATED_MODEL"
    report.update(
        status=status,
        limitations=limitations,
        selected_strategy_metrics=selected_metrics,
        paired_baseline_comparison=comparison,
        return_interval_coverage=coverage,
        final_test_selected_model=terminal_model["kind"],
        frozen_final_model_comparison=final_comparison,
        final_model_refit_after_test=False,
    )
    evidence = {
        "test_observations": len(all_samples),
        "independent_observations": comparison["n_independent"],
        "folds": len(folds),
        "selected_strategy_metrics": selected_metrics,
        "paired_baseline_comparison": comparison,
        "return_interval_coverage": coverage,
    }
    evidence["frozen_final_model_comparison"] = final_comparison
    return {
        "status": status,
        "model": terminal_model,
        "return_distribution": terminal_distribution,
        "limitations": limitations,
        "available_at_ms": maximum_available,
        "evidence": evidence,
    }, report


def train_bundle(
    dataset: dict[str, Any], config: PredictionConfig = PredictionConfig()
) -> dict[str, Any]:
    try:
        __import__("numpy")
        __import__("sklearn")
    except ImportError as exc:
        raise MarketError("training requires installation with .[predictive]") from exc
    candles, metadata = validate_dataset(dataset)
    rows = build_features(candles, config)
    models: dict[str, Any] = {}
    reports: dict[str, Any] = {}
    for horizon in HORIZONS:
        samples = build_samples(candles, rows, horizon, config)
        models[str(horizon)], reports[str(horizon)] = _train_horizon(
            samples, horizon, config, metadata["source"] == "binance_public"
        )
    bundle: dict[str, Any] = {
        "bundle_version": "1",
        "training_version": TRAINING_VERSION,
        "configuration": config.to_dict(),
        "dataset": metadata,
        "history_sha256": history_digest(candles),
        "feature_names": list(FEATURE_NAMES),
        "feature_observations": len(rows),
        "available_at_ms": max(
            metadata["as_of_ms"], *(entry["available_at_ms"] for entry in models.values())
        ),
        "availability_semantics": "information_cutoff_not_actual_artifact_creation; historical_eligibility_assumption",
        "models": models,
        "report": {
            "horizons": reports,
            "limitations": [
                "single_symbol_single_exchange_does_not_establish_general_predictive_edge",
                "historical_candle_availability_assumed_not_original_publication_or_revision_audit",
                "calibration_and_empirical_intervals_have_sampling_uncertainty",
                "overlapping_daily_labels_are_not_independent_tests",
                "no_order_execution_or_cost_adjusted_trading_backtest",
            ],
        },
        "reproducibility": {
            "seed": config.seed,
            "random_temporal_shuffle": False,
            "artifact_format": "JSON_only_no_executable_pickle",
            "final_model": "last_walk_forward_fold_frozen_before_its_test",
            "blas_threads_during_fit": 1,
            "software_versions": {
                "python": platform.python_version(),
                "numpy": version("numpy"),
                "scipy": version("scipy"),
                "scikit_learn": version("scikit-learn"),
                "platform": platform.platform(),
            },
        },
    }
    # All fitted/evaluated information was available by the represented data cutoff.
    if bundle["available_at_ms"] > metadata["as_of_ms"]:
        raise MarketError("model evaluation requires targets beyond dataset cutoff")
    bundle["bundle_sha256"] = bundle_digest(bundle)
    bundle["model_version"] = "model-" + bundle["bundle_sha256"][:16]
    return validate_bundle(bundle)
