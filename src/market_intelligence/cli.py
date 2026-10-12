"""JSON on stdout, operational errors on stderr, never silent simulated fallback."""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from .binance import BASE_URLS, BinanceClient, PublicHTTP
from .engine import _unavailable_predictions, _validate_prediction_history, analyze
from .config import AnalysisConfig
from .models import MarketError
from .render import render_prediction_text, render_text


def parse_cutoff(value: str) -> int:
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            raise ValueError("timezone required")
        return int(dt.timestamp() * 1000)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "Use ISO 8601 with timezone, e.g. 2026-01-01T00:00:00Z"
        ) from exc


def _read_object(path: Path, description: str) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise MarketError(description + " must be a JSON object")
    return value


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _predict(dataset: dict[str, object], bundle: dict[str, object]) -> dict[str, object]:
    from .prediction.contracts import PredictionConfig
    from .prediction.dataset import validate_dataset
    from .prediction.features import build_features
    from .prediction.inference import forecast
    from .prediction.training import validate_bundle

    validate_bundle(bundle)
    candles, metadata = validate_dataset(dataset)
    try:
        _validate_prediction_history(candles, metadata, bundle)
    except MarketError as exc:
        predictions = _unavailable_predictions(
            metadata["as_of_ms"],
            str(exc),
            metadata["last_closed_available_ms"],
            candles[-1].close if candles else None,
            bundle,
        )
    else:
        config = PredictionConfig.from_dict(bundle["configuration"])
        rows = build_features(candles, config)
        predictions = (
            forecast(bundle, rows[-1], metadata["symbol"], metadata["as_of_ms"], metadata["source"])
            if rows
            else _unavailable_predictions(
                metadata["as_of_ms"], "insufficient_daily_feature_history"
            )
        )
    return {
        "prediction_schema_version": "1",
        "symbol": metadata["symbol"],
        "exchange": metadata["exchange"],
        "market": metadata["market"],
        "source": metadata["source"],
        "as_of_ms": metadata["as_of_ms"],
        "dataset_sha256": metadata["dataset_sha256"],
        "predictions": predictions,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Auditable Binance spot market analysis")
    commands = parser.add_subparsers(dest="command", required=True)
    live = commands.add_parser("analyze", help="Fetch real public Binance data")
    live.add_argument("symbol")
    live.add_argument("--bars", type=int, default=250)
    live.add_argument("--as-of", type=parse_cutoff)
    live.add_argument("--base-url", choices=BASE_URLS, default=BASE_URLS[0])
    live.add_argument("--snapshot", type=Path, help="Save raw input for exact replay")
    replay = commands.add_parser("replay", help="Analyze an explicitly labeled saved snapshot")
    replay.add_argument("input", type=Path)
    for command in (live, replay):
        command.add_argument("--output", type=Path, help="Write JSON instead of stdout")
        command.add_argument("--format", choices=("json", "text"), default="json")
        command.add_argument("--config", type=Path, help="JSON analysis configuration")
        command.add_argument("--schema-version", type=int, choices=(1, 2, 3), default=2)
        command.add_argument("--model", type=Path, help="Portable predictive model bundle (v3)")
        command.add_argument(
            "--prediction-dataset", type=Path, help="Aligned historical D1 dataset (v3)"
        )
    dataset = commands.add_parser("dataset", help="Save real public Binance spot D1 history")
    dataset.add_argument("symbol")
    dataset.add_argument("--bars", type=int, default=5000)
    dataset.add_argument("--as-of", type=parse_cutoff)
    dataset.add_argument("--base-url", choices=BASE_URLS, default=BASE_URLS[0])
    dataset.add_argument("--output", type=Path, required=True)
    dataset.add_argument("--start", type=parse_cutoff, help="Explicit UTC-aligned cohort start")
    dataset.add_argument(
        "--selection-reason", help="Reason for excluding the earlier contiguous period"
    )
    train = commands.add_parser(
        "train", help="Fit and evaluate a purged chronological research bundle"
    )
    train.add_argument("input", type=Path)
    train.add_argument("--config", type=Path, help="PredictionConfig JSON; no test-derived tuning")
    train.add_argument("--output", type=Path, required=True)
    train.add_argument("--report", type=Path)
    predict = commands.add_parser(
        "predict", help="Predict from saved data and bundle without fitting"
    )
    predict.add_argument("input", type=Path)
    predict.add_argument("--model", type=Path, required=True)
    predict.add_argument("--format", choices=("json", "text"), default="json")
    predict.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if (
        args.command in ("analyze", "replay")
        and args.schema_version != 3
        and (args.model or args.prediction_dataset)
    ):
        parser.error("--model and --prediction-dataset require --schema-version 3")
    if args.command == "dataset" and (args.start is None) != (args.selection_reason is None):
        parser.error("--start and --selection-reason must be supplied together")
    try:
        if args.command == "dataset":
            from .prediction.dataset import collect_dataset, restrict_dataset

            historical = collect_dataset(
                BinanceClient(PublicHTTP(args.base_url)), args.symbol, args.bars, args.as_of
            )
            if args.start is not None:
                historical = restrict_dataset(historical, args.start, args.selection_reason)
            _write_json(args.output, historical)
            return 0 if historical["quality"]["valid"] else 2
        if args.command == "train":
            from .prediction.contracts import PredictionConfig
            from .prediction.training import train_bundle

            prediction_config = (
                PredictionConfig.from_dict(_read_object(args.config, "Prediction configuration"))
                if args.config
                else PredictionConfig()
            )
            bundle = train_bundle(_read_object(args.input, "Dataset"), prediction_config)
            _write_json(args.output, bundle)
            if args.report:
                _write_json(args.report, bundle["report"])
            return 0
        if args.command == "predict":
            prediction = _predict(
                _read_object(args.input, "Dataset"), _read_object(args.model, "Model bundle")
            )
            output = (
                render_prediction_text(prediction)
                if args.format == "text"
                else json.dumps(prediction, ensure_ascii=False, allow_nan=False, indent=2) + "\n"
            )
            if args.output:
                args.output.write_text(output, encoding="utf-8")
            else:
                sys.stdout.write(output)
            return 0
        if args.command == "analyze":
            client = BinanceClient(PublicHTTP(args.base_url))
            snapshot = client.snapshot(args.symbol, args.bars, args.as_of)
            if args.snapshot:
                args.snapshot.write_text(
                    json.dumps(snapshot, allow_nan=False, indent=2) + "\n", encoding="utf-8"
                )
        else:
            snapshot = json.loads(args.input.read_text(encoding="utf-8"))
        if not isinstance(snapshot, dict):
            raise MarketError("Snapshot must be a JSON object")
        config = (
            AnalysisConfig.from_dict(json.loads(args.config.read_text(encoding="utf-8")))
            if args.config
            else AnalysisConfig()
        )
        result = analyze(
            snapshot,
            config,
            result_version=args.schema_version,
            prediction_bundle=_read_object(args.model, "Model bundle") if args.model else None,
            prediction_dataset=_read_object(args.prediction_dataset, "Dataset")
            if args.prediction_dataset
            else None,
        )
        output = (
            render_text(result)
            if args.format == "text"
            else json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2) + "\n"
        )
        if args.output:
            args.output.write_text(output, encoding="utf-8")
        else:
            sys.stdout.write(output)
        return 0 if result["status"] == "ok" else 2
    except ImportError as exc:
        sys.stderr.write(
            json.dumps(
                {
                    "error": "Install predictive training dependencies with python -m pip install -e '.[predictive]'",
                    "detail": str(exc),
                }
            )
            + "\n"
        )
        return 1
    except (
        MarketError,
        OSError,
        ValueError,
        TypeError,
        KeyError,
        IndexError,
        ArithmeticError,
    ) as exc:
        sys.stderr.write(json.dumps({"error": str(exc)}, ensure_ascii=False) + "\n")
        return 1
