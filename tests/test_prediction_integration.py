"""Offline Task03 integration; all fixture prices are explicitly simulated."""

import contextlib
import copy
import io
import json
import tempfile
import unittest
from importlib.resources import files
from pathlib import Path
from unittest.mock import patch

import jsonschema

from market_intelligence.cli import main
from market_intelligence.engine import analyze, canonical_json
from market_intelligence.models import MarketError
from market_intelligence.prediction.contracts import DAY_MS, PredictionConfig
from market_intelligence.prediction.dataset import create_dataset, history_digest
from market_intelligence.prediction.dataset import validate_dataset
from market_intelligence.prediction.features import FEATURE_NAMES, build_features
from market_intelligence.prediction.training import TRAINING_VERSION, bundle_digest
from market_intelligence.render import render_text

from tests.fixtures import snapshot


def dataset_for(data: dict) -> dict:
    return create_dataset(
        data["klines"]["D1"],
        data["symbol"],
        data["as_of_ms"],
        data["server_time_ms"],
        data["requested_bars"],
        data["endpoint"],
        data["symbol_info"],
        data["source"],
    )


def empty_bundle(dataset: dict) -> dict:
    """No fitted model: valid portable envelope for insufficient-data tests."""
    metadata = {key: value for key, value in dataset.items() if key != "klines"}
    candles, _ = validate_dataset(dataset)
    bundle = {
        "bundle_version": "1",
        "training_version": TRAINING_VERSION,
        "configuration": PredictionConfig().to_dict(),
        "dataset": metadata,
        "feature_names": list(FEATURE_NAMES),
        "available_at_ms": dataset["as_of_ms"],
        "models": {
            str(h): {
                "status": "INSUFFICIENT_EVIDENCE",
                "model": None,
                "return_distribution": None,
                "available_at_ms": 0,
                "evidence": {"test_observations": 0, "folds": 0},
                "limitations": ["historical_dataset_insufficient_for_walk_forward"],
            }
            for h in (7, 30, 90)
        },
        "report": {"horizons": {}},
        "history_sha256": history_digest(candles),
    }
    bundle["bundle_sha256"] = bundle_digest(bundle)
    bundle["model_version"] = "model-" + bundle["bundle_sha256"][:16]
    return bundle


class PredictionIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = snapshot()
        cls.dataset = dataset_for(cls.data)
        cls.bundle = empty_bundle(cls.dataset)
        cls.schema = json.loads(
            files("market_intelligence").joinpath("result-v3.schema.json").read_text()
        )

    def validate(self, result: dict) -> None:
        jsonschema.Draft202012Validator(self.schema).validate(json.loads(canonical_json(result)))

    def test_v3_without_model_preserves_descriptive_modules_and_abstains(self) -> None:
        legacy, result = analyze(self.data), analyze(self.data, result_version=3)
        self.validate(result)
        self.assertEqual(result["schema_version"], "3")
        self.assertEqual(result["timeframes"], legacy["timeframes"])
        self.assertEqual(result["scenarios"], legacy["scenarios"])
        self.assertEqual([p["horizon_days"] for p in result["predictions"]], [7, 30, 90])
        for prediction in result["predictions"]:
            self.assertEqual(prediction["status"], "INSUFFICIENT_EVIDENCE")
            self.assertIsNone(prediction["probabilities"])
            self.assertIsNone(prediction["return_distribution"])
        self.assertIn("Probabilidades validadas: indisponiveis", render_text(result))

    def test_legacy_versions_are_stable_after_package_version_changes(self) -> None:
        with patch("market_intelligence.engine.__version__", "0.3.0"):
            self.assertEqual(analyze(self.data, result_version=1)["engine_version"], "0.1.0")
            self.assertEqual(analyze(self.data, result_version=2)["engine_version"], "0.2.0")
            self.assertEqual(analyze(self.data, result_version=3)["engine_version"], "0.3.0")
        for version in (1, 2):
            with self.assertRaises(MarketError):
                analyze(self.data, result_version=version, prediction_bundle=self.bundle)

    def test_schema_rejects_public_probabilities_for_unvalidated_models(self) -> None:
        result = analyze(self.data, result_version=3)
        prediction = result["predictions"][0]
        prediction["status"] = "UNVALIDATED_MODEL"
        prediction["probabilities"] = {"bearish": 0.2, "neutral": 0.3, "bullish": 0.5}
        with self.assertRaises(jsonschema.ValidationError):
            self.validate(result)

    def test_aligned_short_simulated_dataset_has_no_predictive_claims(self) -> None:
        with patch(
            "market_intelligence.prediction.training.train_bundle",
            side_effect=AssertionError("analysis cannot fit models"),
        ):
            result = analyze(
                self.data,
                result_version=3,
                prediction_bundle=self.bundle,
                prediction_dataset=self.dataset,
            )
        self.validate(result)
        for prediction in result["predictions"]:
            self.assertEqual(prediction["status"], "INSUFFICIENT_EVIDENCE")
            self.assertIn("synthetic_or_unverified_real_population", prediction["limitations"])
            self.assertIsNone(prediction["experimental_diagnostics"])

    def test_missing_historical_dataset_fails_closed(self) -> None:
        result = analyze(self.data, result_version=3, prediction_bundle=self.bundle)
        self.assertEqual(
            result["predictions"][0]["limitations"], ["prediction_dataset_not_supplied"]
        )
        self.validate(result)

    def test_integration_uses_frozen_bundle_feature_configuration(self) -> None:
        bundle = copy.deepcopy(self.bundle)
        config = PredictionConfig(feature_window=100)
        bundle["configuration"] = config.to_dict()
        bundle["bundle_sha256"] = bundle_digest(bundle)
        bundle["model_version"] = "model-" + bundle["bundle_sha256"][:16]
        candles, _ = validate_dataset(self.dataset)
        expected = build_features(candles, config)[-1]
        default = build_features(candles)[-1]
        self.assertNotEqual(expected.values, default.values)
        unavailable = analyze(self.data, result_version=3)["predictions"]
        with patch(
            "market_intelligence.prediction.inference.forecast", return_value=unavailable
        ) as inference:
            result = analyze(
                self.data,
                result_version=3,
                prediction_bundle=bundle,
                prediction_dataset=self.dataset,
            )
        self.validate(result)
        self.assertEqual(inference.call_args.args[1], expected)
        self.assertEqual(inference.call_args.args[3], self.data["as_of_ms"])

    def test_prediction_dataset_alignment_checks(self) -> None:
        variants = []
        different_symbol = copy.deepcopy(self.data)
        different_symbol["symbol"] = "ETHUSDT"
        different_symbol["symbol_info"]["symbol"] = "ETHUSDT"
        variants.append((dataset_for(different_symbol), "symbol_or_source_mismatch"))
        future_cutoff = copy.deepcopy(self.data)
        future_cutoff["as_of_ms"] += 1
        future_cutoff["server_time_ms"] += 1
        variants.append((dataset_for(future_cutoff), "cutoff_exceeds_snapshot"))
        stale = copy.deepcopy(self.data)
        stale["as_of_ms"] -= DAY_MS
        stale["klines"]["D1"] = stale["klines"]["D1"][:-1]
        variants.append((dataset_for(stale), "origin_does_not_match"))
        changed_candle = copy.deepcopy(self.data)
        changed_candle["klines"]["D1"][-1][2] = str(
            float(changed_candle["klines"]["D1"][-1][2]) + 1
        )
        variants.append((dataset_for(changed_candle), "candles_differ_from_snapshot"))
        for historical, reason in variants:
            with self.subTest(reason=reason):
                result = analyze(
                    self.data,
                    result_version=3,
                    prediction_bundle=self.bundle,
                    prediction_dataset=historical,
                )
                self.validate(result)
                self.assertIn(reason, result["predictions"][0]["limitations"][0])
                self.assertTrue(all(p["probabilities"] is None for p in result["predictions"]))

    def test_corrupt_bundle_and_invalid_D1_fail_closed(self) -> None:
        bundle = copy.deepcopy(self.bundle)
        bundle["configuration"]["seed"] = 9
        result = analyze(
            self.data, result_version=3, prediction_bundle=bundle, prediction_dataset=self.dataset
        )
        self.assertIn("checksum mismatch", result["predictions"][0]["limitations"][0])
        self.validate(result)
        data = copy.deepcopy(self.data)
        del data["klines"]["D1"][20]
        result = analyze(
            data, result_version=3, prediction_bundle=self.bundle, prediction_dataset=self.dataset
        )
        self.assertEqual(result["predictions"][0]["limitations"], ["invalid_daily_snapshot"])
        self.validate(result)

    def test_v3_cli_replay_and_standalone_predict(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            data, dataset, bundle = [
                Path(folder) / name for name in ("snapshot.json", "dataset.json", "bundle.json")
            ]
            for path, value in ((data, self.data), (dataset, self.dataset), (bundle, self.bundle)):
                path.write_text(json.dumps(value))
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = main(
                    [
                        "replay",
                        str(data),
                        "--schema-version",
                        "3",
                        "--model",
                        str(bundle),
                        "--prediction-dataset",
                        str(dataset),
                    ]
                )
            self.assertEqual(code, 0)
            self.validate(json.loads(out.getvalue()))
            with (
                contextlib.redirect_stdout(io.StringIO()),
                contextlib.redirect_stderr(io.StringIO()),
                self.assertRaises(SystemExit),
            ):
                main(["replay", str(data), "--model", str(bundle)])
            out = io.StringIO()
            with (
                patch(
                    "market_intelligence.prediction.training.train_bundle",
                    side_effect=AssertionError("predict cannot retrain"),
                ),
                contextlib.redirect_stdout(out),
            ):
                self.assertEqual(main(["predict", str(dataset), "--model", str(bundle)]), 0)
            self.assertEqual(len(json.loads(out.getvalue())["predictions"]), 3)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(
                    main(["predict", str(dataset), "--model", str(bundle), "--format", "text"]), 0
                )
            self.assertIn("simulated", out.getvalue())
            self.assertIn("INSUFFICIENT_EVIDENCE", out.getvalue())

    def test_dataset_cli_retains_integrity_failures_and_does_not_fill(self) -> None:
        bad = copy.deepcopy(self.data)
        del bad["klines"]["D1"][10]
        historical = dataset_for(bad)
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "dataset.json"
            with patch(
                "market_intelligence.prediction.dataset.collect_dataset", return_value=historical
            ):
                self.assertEqual(main(["dataset", "BTCUSDT", "--output", str(target)]), 2)
            saved = json.loads(target.read_text())
            self.assertFalse(saved["quality"]["valid"])
            self.assertEqual(saved["klines"], historical["klines"])
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                main(
                    [
                        "dataset",
                        "BTCUSDT",
                        "--output",
                        str(target),
                        "--start",
                        "2026-01-01T00:00:00Z",
                    ]
                )

    def test_training_cli_writes_explicit_report_and_config(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            dataset, config, bundle, report = [
                Path(folder) / name
                for name in ("dataset.json", "config.json", "bundle.json", "report.json")
            ]
            dataset.write_text(json.dumps(self.dataset))
            config.write_text(json.dumps({"seed": 123}))
            with patch(
                "market_intelligence.prediction.training.train_bundle", return_value=self.bundle
            ) as train:
                self.assertEqual(
                    main(
                        [
                            "train",
                            str(dataset),
                            "--config",
                            str(config),
                            "--output",
                            str(bundle),
                            "--report",
                            str(report),
                        ]
                    ),
                    0,
                )
            self.assertEqual(train.call_args.args[1].seed, 123)
            self.assertEqual(json.loads(report.read_text()), self.bundle["report"])
            self.assertEqual(
                canonical_json(json.loads(bundle.read_text())), canonical_json(self.bundle)
            )
            error = io.StringIO()
            with (
                patch(
                    "market_intelligence.prediction.training.train_bundle",
                    side_effect=ImportError("sklearn"),
                ),
                contextlib.redirect_stderr(error),
            ):
                self.assertEqual(main(["train", str(dataset), "--output", str(bundle)]), 1)
            self.assertIn(".[predictive]", json.loads(error.getvalue())["error"])

    def test_text_labels_experimental_probabilities_separately(self) -> None:
        result = analyze(self.data, result_version=3)
        prediction = result["predictions"][0]
        prediction["status"] = "UNVALIDATED_MODEL"
        prediction["experimental_diagnostics"] = {
            "status": "EXPERIMENTAL_NOT_VALIDATED",
            "probabilities": {"bearish": 0.2, "neutral": 0.3, "bullish": 0.5},
            "return_distribution": None,
            "use": "research_only_not_a_validated_forecast",
        }
        prediction["evidence"] = {
            "test_observations": 120,
            "independent_observations": 15,
            "folds": 2,
            "selected_strategy_metrics": {"brier": 0.5, "log_loss": 0.9, "ece": 0.1},
            "return_interval_coverage": {"coverage": 0.75},
        }
        self.validate(result)
        text = render_text(result)
        self.assertIn("EXPERIMENTAL / somente pesquisa", text)
        self.assertIn("bullish=50.00%", text)
        self.assertIn("120 observacoes; 15 janelas sem sobreposicao", text)
        self.assertIn("brier=0.500000", text)
        self.assertIn("75.00%", text)
        self.assertTrue(
            all(s["forecast"]["calibrated_probability"] is None for s in result["scenarios"])
        )
