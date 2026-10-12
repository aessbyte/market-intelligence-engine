"""Transparent fitted classifiers and portable JSON inference, without pickle."""

import math
import statistics
import struct
from typing import Any, Sequence

from ..models import MarketError
from .contracts import CLASSES, PredictionConfig, Sample
from .validation import independent_indices

MODEL_KINDS = ("frequency", "momentum", "logistic", "gradient_boosting")
MIN_INDEPENDENT_CALIBRATION = 10


def validate_model_parameters(model: Any, feature_names: Sequence[str]) -> None:
    """Validate portable JSON parameters before evaluating an imported artifact."""

    def numbers(value: Any, length: int, positive: bool = False) -> None:
        if not isinstance(value, list) or len(value) != length:
            raise MarketError("model numeric array dimension mismatch")
        if any(
            isinstance(item, bool)
            or not isinstance(item, (int, float))
            or not math.isfinite(item)
            or (positive and item <= 0)
            for item in value
        ):
            raise MarketError("model numeric arrays must be finite with positive scales")

    def probabilities(value: Any) -> None:
        numbers(value, 3)
        if any(item < 0 or item > 1 for item in value) or abs(sum(value) - 1) > 1e-8:
            raise MarketError("model probabilities must form a three-class simplex")

    try:
        if not isinstance(model, dict) or model.get("kind") not in MODEL_KINDS:
            raise MarketError("unsupported portable model kind")
        if model.get("classes") != list(CLASSES) or model.get("feature_names") != list(
            feature_names
        ):
            raise MarketError("model class or feature ordering mismatch")
        dimensions = len(feature_names)
        numbers(model["drift_mean"], dimensions)
        numbers(model["drift_scale"], dimensions, positive=True)
        numbers([model["temperature"]], 1, positive=True)
        numbers(model["class_counts"], 3)
        if (
            type(model["training_observations"]) is not int
            or model["training_observations"] <= 0
            or any(type(count) is not int or count < 0 for count in model["class_counts"])
            or sum(model["class_counts"]) != model["training_observations"]
        ):
            raise MarketError("invalid model training class counts")
        if not isinstance(model["regime_counts"], dict) or any(
            not isinstance(key, str) or type(count) is not int or count < 0
            for key, count in model["regime_counts"].items()
        ):
            raise MarketError("invalid model regime support counts")
        if sum(model["regime_counts"].values()) != model["training_observations"]:
            raise MarketError("regime counts do not match training population")
        kind = model["kind"]
        if kind == "frequency":
            probabilities(model["probabilities"])
        elif kind == "momentum":
            if type(model["column"]) is not int or not 0 <= model["column"] < dimensions:
                raise MarketError("invalid momentum feature column")
            if (
                not isinstance(model["bin_probabilities"], list)
                or len(model["bin_probabilities"]) != 3
            ):
                raise MarketError("momentum model needs three bins")
            for row in model["bin_probabilities"]:
                probabilities(row)
        elif kind == "logistic":
            numbers(model["scaler"]["mean"], dimensions)
            numbers(model["scaler"]["scale"], dimensions, positive=True)
            numbers(model["intercept"], 3)
            if not isinstance(model["coefficients"], list) or len(model["coefficients"]) != 3:
                raise MarketError("logistic model needs three coefficient vectors")
            for row in model["coefficients"]:
                numbers(row, dimensions)
        else:
            numbers(model["initial_logits"], 3)
            numbers([model["parameters"]["learning_rate"]], 1, positive=True)
            if not isinstance(model["trees"], list) or not 1 <= len(model["trees"]) <= 1000:
                raise MarketError("invalid number of boosting stages")
            for stage in model["trees"]:
                if not isinstance(stage, list) or len(stage) != 3:
                    raise MarketError("boosting stage needs three class trees")
                for tree in stage:
                    if not isinstance(tree, dict) or not isinstance(tree.get("left"), list):
                        raise MarketError("invalid tree arrays")
                    count = len(tree["left"])
                    if not 1 <= count <= 10000:
                        raise MarketError("invalid tree node count")
                    for key in ("left", "right", "feature", "threshold", "value"):
                        numbers(tree[key], count)
                    for index, (left, right, feature) in enumerate(
                        zip(tree["left"], tree["right"], tree["feature"], strict=True)
                    ):
                        if any(type(item) is not int for item in (left, right, feature)):
                            raise MarketError("tree indices must be integers")
                        if left == right == -1:
                            continue
                        if (
                            not index < left < count
                            or not index < right < count
                            or left == right
                            or not 0 <= feature < dimensions
                        ):
                            raise MarketError("tree is cyclic or has invalid child/feature indices")
    except (KeyError, TypeError, ValueError, IndexError, OverflowError) as exc:
        raise MarketError(f"malformed portable model parameters: {exc}") from exc


def _frequencies(labels: Sequence[int]) -> list[float]:
    # A fixed symmetric Dirichlet(1,1,1) prior prevents undefined log losses.
    counts = [1.0, 1.0, 1.0]
    for label in labels:
        counts[label] += 1.0
    return [count / sum(counts) for count in counts]


def _momentum_bin(value: float) -> int:
    return 0 if value < 0 else 2 if value > 0 else 1


def fit_model(
    kind: str,
    samples: Sequence[Sample],
    feature_names: Sequence[str],
    config: PredictionConfig,
) -> dict[str, Any]:
    if kind not in MODEL_KINDS or not samples:
        raise MarketError("unknown model or empty training data")
    labels = [sample.label for sample in samples]
    common: dict[str, Any] = {
        "kind": kind,
        "classes": list(CLASSES),
        "temperature": 1.0,
        "training_observations": len(samples),
        "class_counts": [labels.count(label) for label in range(3)],
        "feature_names": list(feature_names),
        "train_origin_start_ms": samples[0].row.origin_ms,
        "train_origin_end_ms": samples[-1].row.origin_ms,
        "train_target_available_max_ms": max(s.target_available_ms for s in samples),
        "regime_counts": {
            regime: sum(sample.row.regime == regime for sample in samples)
            for regime in sorted({s.row.regime for s in samples})
        },
    }
    columns = tuple(zip(*(s.row.values for s in samples), strict=True))
    common["drift_mean"] = [statistics.fmean(column) for column in columns]
    common["drift_scale"] = [statistics.pstdev(column) or 1.0 for column in columns]
    if kind == "frequency":
        common.update(
            probabilities=_frequencies(labels),
            prior="fixed_symmetric_Dirichlet_1_per_class",
        )
        return common
    if kind == "momentum":
        # Sign of the observed seven-day log return; frequencies are learned.
        column = next(
            (i for i, name in enumerate(feature_names) if name in ("return7", "return7_log")),
            None,
        )
        if column is None:
            raise MarketError("momentum baseline requires return7 feature")
        bins = [
            [s.label for s in samples if _momentum_bin(s.row.values[column]) == category]
            for category in range(3)
        ]
        fallback = _frequencies(labels)
        common.update(
            column=column,
            bin_probabilities=[_frequencies(group) if group else fallback for group in bins],
            bin_counts=[len(group) for group in bins],
            prior="fixed_symmetric_Dirichlet_1_per_class",
            rule="sign_of_causal_seven_day_log_return",
        )
        return common
    if min(common["class_counts"]) < config.min_class:
        raise MarketError("insufficient training observations per target class")
    try:
        import numpy as np
        from sklearn.ensemble import GradientBoostingClassifier
        from sklearn.linear_model import LogisticRegression
        from sklearn.preprocessing import StandardScaler
        from threadpoolctl import threadpool_limits  # type: ignore[import-untyped]
    except ImportError as exc:
        raise MarketError("training requires installation of the predictive extra") from exc
    matrix = np.asarray([sample.row.values for sample in samples], dtype=float)
    scaler = StandardScaler().fit(matrix)
    common["scaler"] = {"mean": scaler.mean_.tolist(), "scale": scaler.scale_.tolist()}
    common["drift_mean"] = scaler.mean_.tolist()
    common["drift_scale"] = scaler.scale_.tolist()
    if kind == "logistic":
        classifier = LogisticRegression(
            C=config.logistic_c,
            solver="lbfgs",
            max_iter=600,
            random_state=config.seed,
        )
        with threadpool_limits(limits=1):
            classifier.fit(scaler.transform(matrix), labels)
        if classifier.n_iter_.max() >= classifier.max_iter:
            raise MarketError("logistic fitting did not converge")
        common.update(
            coefficients=classifier.coef_.tolist(),
            intercept=classifier.intercept_.tolist(),
            parameters={"C": config.logistic_c, "solver": "lbfgs", "max_iter": 600},
        )
    else:
        if len(samples) < config.min_boosting_train:
            raise MarketError("insufficient training data for nonlinear model")
        classifier_boost = GradientBoostingClassifier(
            n_estimators=40,
            learning_rate=0.05,
            max_depth=2,
            subsample=1.0,
            random_state=config.seed,
            n_iter_no_change=None,
        )
        with threadpool_limits(limits=1):
            classifier_boost.fit(matrix, labels)
        exported = []
        for stage in classifier_boost.estimators_:
            trees = []
            for estimator in stage:
                tree = estimator.tree_
                trees.append(
                    {
                        "left": tree.children_left.tolist(),
                        "right": tree.children_right.tolist(),
                        "feature": tree.feature.tolist(),
                        "threshold": tree.threshold.tolist(),
                        "value": tree.value[:, 0, 0].tolist(),
                    }
                )
            exported.append(trees)
        initial = classifier_boost.init_.class_prior_.tolist()
        common.update(
            initial_logits=[math.log(float(value)) for value in initial],
            trees=exported,
            parameters={
                "n_estimators": 40,
                "learning_rate": 0.05,
                "max_depth": 2,
                "subsample": 1.0,
                "early_stopping": False,
            },
        )
    return common


def _softmax(logits: Sequence[float]) -> list[float]:
    maximum = max(logits)
    weights = [math.exp(value - maximum) for value in logits]
    return [weight / sum(weights) for weight in weights]


def temperature_scale(probabilities: Sequence[float], temperature: float) -> list[float]:
    if not math.isfinite(temperature) or temperature <= 0:
        raise MarketError("invalid calibration temperature")
    return _softmax([math.log(max(float(p), 1e-15)) / temperature for p in probabilities])


def predict_model(model: dict[str, Any], values: Sequence[float]) -> list[float]:
    kind = model["kind"]
    if kind == "frequency":
        raw = [float(value) for value in model["probabilities"]]
    elif kind == "momentum":
        raw = [
            float(value)
            for value in model["bin_probabilities"][_momentum_bin(values[model["column"]])]
        ]
    elif kind == "logistic":
        scaler = model["scaler"]
        standardized = [
            (value - mean) / scale
            for value, mean, scale in zip(values, scaler["mean"], scaler["scale"], strict=True)
        ]
        logits = [
            float(intercept)
            + sum(
                float(coefficient) * value
                for coefficient, value in zip(coefficients, standardized, strict=True)
            )
            for coefficients, intercept in zip(
                model["coefficients"], model["intercept"], strict=True
            )
        ]
        raw = _softmax(logits)
    elif kind == "gradient_boosting":
        logits = [float(value) for value in model["initial_logits"]]
        # sklearn tree evaluation casts predictors to float32 before traversal.
        tree_values = [struct.unpack("f", struct.pack("f", value))[0] for value in values]
        for stage in model["trees"]:
            for category, tree in enumerate(stage):
                node = 0
                for _ in range(len(tree["left"]) + 1):
                    if tree["left"][node] == -1:
                        break
                    node = (
                        tree["left"][node]
                        if tree_values[tree["feature"][node]] <= tree["threshold"][node]
                        else tree["right"][node]
                    )
                else:
                    raise MarketError("cyclic imported tree cannot be evaluated")
                logits[category] += float(model["parameters"]["learning_rate"]) * float(
                    tree["value"][node]
                )
        raw = _softmax(logits)
    else:
        raise MarketError("unsupported portable model")
    return temperature_scale(raw, float(model.get("temperature", 1.0)))


def calibrate_model(
    model: dict[str, Any],
    samples: Sequence[Sample],
    config: PredictionConfig = PredictionConfig(),
) -> dict[str, Any]:
    """Fit a one-parameter temperature on a reserved chronological block only."""
    uncalibrated = dict(model, temperature=1.0)
    class_counts = [sum(sample.label == label for sample in samples) for label in range(3)]
    independent_count = len(independent_indices(tuple(samples)))
    limitations = []
    if len(samples) < config.min_calibration:
        limitations.append("insufficient_calibration_observations")
    if min(class_counts) < config.min_class:
        limitations.append("insufficient_calibration_class_support")
    if independent_count < MIN_INDEPENDENT_CALIBRATION:
        limitations.append("insufficient_independent_calibration_origins")
    metadata = {
        "observations": len(samples),
        "class_counts": class_counts,
        "n_independent": independent_count,
        "minimum_independent_observations": MIN_INDEPENDENT_CALIBRATION,
        "origin_start_ms": samples[0].row.origin_ms if samples else None,
        "origin_end_ms": samples[-1].row.origin_ms if samples else None,
        "target_available_max_ms": max((s.target_available_ms for s in samples), default=0),
        "used_for_model_selection": False,
    }
    if limitations:
        uncalibrated["calibration"] = dict(
            metadata,
            method="unavailable",
            status="INSUFFICIENT_EVIDENCE",
            temperature=1.0,
            limitations=limitations,
        )
        return uncalibrated
    raw = [predict_model(uncalibrated, sample.row.values) for sample in samples]
    candidates = sorted(
        {1.0, *(math.exp(math.log(0.5) + i * math.log(6.0) / 40) for i in range(41))}
    )
    best = min(
        candidates,
        key=lambda temperature: (
            sum(
                -math.log(max(temperature_scale(probabilities, temperature)[sample.label], 1e-15))
                for sample, probabilities in zip(samples, raw, strict=True)
            )
            / len(samples),
            abs(math.log(temperature)),
        ),
    )
    result = dict(model, temperature=best)
    result["calibration"] = {
        **metadata,
        "status": "CALIBRATED",
        "method": "scalar_temperature_log_loss_fixed_grid_0.5_to_3",
        "temperature": best,
        "limitations": [],
    }
    return result
