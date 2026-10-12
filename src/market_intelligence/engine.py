"""Pure snapshot analysis: identical snapshot yields identical JSON."""

import hashlib
import json
import math
from dataclasses import asdict
from typing import Any

from . import __version__
from .binance import normalize_symbol
from .config import AnalysisConfig
from .indicators import calculate
from .models import Candle, Interval, MarketError, Regime
from .multitimeframe import compare_timeframes
from .regime import RULES, aggregate, classify, scenarios
from .validation import parse_klines, validate
from .scenarios import build_scenarios
from .structure import analyze_structure
from .wyckoff import analyze_wyckoff

LIMITATIONS = [
    "Regras heuristicas descritivas; sem calibracao, probabilidades ou vantagem estatistica demonstrada.",
    "OHLCV spot Binance nao representa outras corretoras, livro de ofertas ou fluxo de ordens.",
    "EMA, RSI e ATR dependem da janela e das sementes; nao equivalem a historico infinito.",
    "Cenarios condicionais nao sao previsoes nem recomendacoes de negociacao.",
    "Candles historicos podem ser revisados pela fonte; replay reproduz o snapshot, nao a disponibilidade historica.",
]


def canonical_json(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def analyze(
    snapshot: dict[str, Any],
    config: AnalysisConfig | None = None,
    result_version: int = 2,
    prediction_bundle: dict[str, Any] | None = None,
    prediction_dataset: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if result_version not in (1, 2, 3):
        raise MarketError("Unsupported result version")
    if result_version != 3 and (prediction_bundle is not None or prediction_dataset is not None):
        raise MarketError("Predictive inputs require result version 3")
    config = config if config is not None else AnalysisConfig()
    try:
        if snapshot.get("snapshot_version") != "1":
            raise MarketError("Unsupported snapshot version")
        source = snapshot["source"]
        if source not in ("binance_public", "simulated"):
            raise MarketError("Snapshot must identify binance_public or simulated source")
        if not isinstance(snapshot["symbol"], str):
            raise MarketError("Snapshot symbol must be a string")
        symbol = normalize_symbol(snapshot["symbol"])
        cutoff = snapshot["as_of_ms"]
        server_time = snapshot["server_time_ms"]
        bars = snapshot["requested_bars"]
        if (
            type(cutoff) is not int
            or type(server_time) is not int
            or cutoff <= 0
            or cutoff > server_time
            or type(bars) is not int
            or not 100 <= bars <= 5000
        ):
            raise MarketError("Invalid snapshot timestamps or requested_bars")
        if not isinstance(snapshot["klines"], dict):
            raise MarketError("Snapshot klines must be an object")
        if not isinstance(snapshot.get("fetch_errors", {}), dict):
            raise MarketError("Snapshot fetch_errors must be an object")
        info = snapshot.get("symbol_info")
        if (
            not isinstance(info, dict)
            or info.get("symbol") != symbol
            or info.get("status") != "TRADING"
            or info.get("isSpotTradingAllowed") is not True
        ):
            raise MarketError("Snapshot symbol metadata is unavailable or inconsistent")
        digest = hashlib.sha256(canonical_json(snapshot).encode()).hexdigest()
    except (KeyError, ValueError, TypeError, AttributeError) as exc:
        raise MarketError(f"Invalid snapshot envelope: {exc}") from exc

    frames: dict[str, Any] = {}
    regimes = []
    for interval in Interval:
        errors: list[str] = []
        try:
            candles = parse_klines(snapshot["klines"].get(interval.name, []))
            closed, quality = validate(candles, interval, cutoff)
            quality_json = asdict(quality)
            errors.extend(quality.errors)
        except MarketError as exc:
            closed = ()
            errors.append(str(exc))
            quality_json = {"valid": False, "errors": errors}
        fetch_error = snapshot.get("fetch_errors", {}).get(interval.name)
        if fetch_error:
            errors.append(str(fetch_error))
        if len(closed) != bars:
            errors.append(f"requested {bars} closed candles, received {len(closed)}")
        quality_json["valid"] = not errors
        quality_json["errors"] = list(dict.fromkeys(errors))
        features: dict[str, Any] | None = None
        evidence: list[dict[str, object]] = []
        regime = Regime.UNKNOWN
        if not errors:
            try:
                computed = calculate(closed)
                features = asdict(computed)
                if not all(value is None or math.isfinite(value) for value in features.values()):
                    raise ValueError("non-finite computed indicator")
                regime, evidence = classify(computed)
            except (ArithmeticError, ValueError) as exc:
                features = None
                regime = Regime.UNKNOWN
                quality_json["valid"] = False
                quality_json["errors"].append(f"indicator calculation failed: {exc}")
        frames[interval.name] = {
            "interval": interval.value,
            "quality": quality_json,
            "indicators": features,
            "regime": regime.value,
            "evidence": evidence,
            "scenarios": scenarios(regime),
        }
        if result_version >= 2:
            frames[interval.name]["structure"] = None
            frames[interval.name]["wyckoff"] = None
            if quality_json["valid"]:
                structural = analyze_structure(closed, interval, cutoff, config.structure)
                frames[interval.name]["structure"] = structural
                frames[interval.name]["wyckoff"] = analyze_wyckoff(
                    closed, interval, cutoff, structural, config.wyckoff
                )
        regimes.append(regime)
    overall = aggregate(regimes)
    valid = all(f["quality"]["valid"] for f in frames.values())
    result: dict[str, Any] = {
        "schema_version": str(result_version),
        "engine_version": __version__
        if result_version == 3
        else "0.2.0"
        if result_version == 2
        else "0.1.0",
        "symbol": symbol,
        "as_of_ms": cutoff,
        "status": "ok" if valid else "degraded",
        "provenance": {
            "source": source,
            "market": "binance_spot",
            "simulated": source == "simulated",
            "snapshot_sha256": digest,
            "server_time_ms": server_time,
            "requested_bars": bars,
            "endpoint": snapshot.get("endpoint", "unspecified"),
            "source_claim_verified": False,
        },
        "configuration": {
            "rules": asdict(RULES),
            "minimum_history": 100,
            "aggregate_rule": "unanimous_H1_H4_D1",
        },
        "timeframes": frames,
        "regime": overall.value,
        "evidence": [{"rule": "unanimous_H1_H4_D1", "observed": [r.value for r in regimes]}],
        "limitations": LIMITATIONS
        + (["Dados simulados: nenhum preco real foi observado."] if source == "simulated" else []),
        "scenarios": scenarios(overall),
    }
    if result_version >= 2:
        comparison = compare_timeframes(frames, cutoff)
        result["multitimeframe"] = comparison
        result["scenarios"] = build_scenarios(
            frames, comparison, cutoff, config.scenario_freshness_bars
        )
        result["configuration"]["analysis"] = asdict(config)
        result["limitations"] += [
            "Pivos e eventos confirmados significam regras satisfeitas, nao certeza de fase Wyckoff.",
            "Liquidez observada em OHLCV nao mede profundidade de livro ou capacidade de execucao.",
        ]
    if result_version == 3:
        result["predictions"] = _predictions(
            snapshot, frames, prediction_bundle, prediction_dataset
        )
        result["limitations"][0] = (
            "Regime, estrutura e cenarios condicionais usam regras heuristicas descritivas; sua ativacao nao valida capacidade preditiva."
        )
        result["limitations"] += [
            "Classes estatisticas descrevem retorno ao final do horizonte; nao sao probabilidades de ativacao dos cenarios condicionais.",
            "Diagnosticos experimentais nao constituem previsoes validadas; probabilidades publicas permanecem null quando a evidencia e insuficiente.",
        ]
    return result


def _unavailable_predictions(
    cutoff: int,
    reason: str,
    origin: int | None = None,
    price: float | None = None,
    bundle: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Missing information is never replaced by unconditional invented numbers."""
    from .prediction.contracts import DAY_MS, HORIZONS

    metadata = bundle.get("dataset", {}) if isinstance(bundle, dict) else {}
    model_version = bundle.get("model_version") if isinstance(bundle, dict) else None
    model_available = bundle.get("available_at_ms") if isinstance(bundle, dict) else None
    dataset_version = metadata.get("dataset_version") if isinstance(metadata, dict) else None
    return [
        {
            "horizon_days": horizon,
            "status": "INSUFFICIENT_EVIDENCE",
            "prediction_origin_ms": origin,
            "as_of_ms": cutoff,
            "horizon_end_ms": origin + horizon * DAY_MS if origin is not None else None,
            "reference_price": price,
            "probabilities": None,
            "return_distribution": None,
            "experimental_diagnostics": None,
            "model_version": model_version if isinstance(model_version, str) else None,
            "model_available_at_ms": model_available
            if type(model_available) is int and model_available > 0
            else None,
            "dataset_version": dataset_version if isinstance(dataset_version, str) else None,
            "evidence": None,
            "max_feature_standardized_distance": None,
            "limitations": [reason],
            "scenario_relationship": "statistical_end_return_classes_are_distinct_from_conditional_rule_scenarios",
            "reference_timing": "daily_close_reference; issued_at_as_of_ms; not_historical_issuance_at_daily_origin",
        }
        for horizon in HORIZONS
    ]


def _predictions(
    snapshot: dict[str, Any],
    frames: dict[str, Any],
    bundle: dict[str, Any] | None,
    dataset: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Integrate portable inference with an explicitly aligned historical dataset."""
    cutoff = int(snapshot["as_of_ms"])
    origin = frames["D1"]["quality"].get("last_close_ms")
    origin = origin + 1 if isinstance(origin, int) else None
    if not frames["D1"]["quality"]["valid"]:
        return _unavailable_predictions(cutoff, "invalid_daily_snapshot", origin, bundle=bundle)
    if bundle is None:
        return _unavailable_predictions(cutoff, "prediction_model_not_supplied", origin)
    if dataset is None:
        return _unavailable_predictions(
            cutoff, "prediction_dataset_not_supplied", origin, bundle=bundle
        )
    try:
        from .prediction.contracts import PredictionConfig
        from .prediction.dataset import validate_dataset
        from .prediction.features import build_features
        from .prediction.inference import forecast
        from .prediction.training import validate_bundle

        validate_bundle(bundle)
        candles, metadata = validate_dataset(dataset)
        symbol = normalize_symbol(snapshot["symbol"])
        if metadata["symbol"] != symbol or metadata["source"] != snapshot["source"]:
            raise MarketError("prediction_dataset_symbol_or_source_mismatch")
        if metadata["as_of_ms"] > cutoff:
            raise MarketError("prediction_dataset_cutoff_exceeds_snapshot")
        if not candles or candles[-1].close_time_ms + 1 != origin:
            raise MarketError("prediction_dataset_origin_does_not_match_latest_closed_D1")
        daily = parse_klines(snapshot["klines"]["D1"])
        observed = {candle.open_time_ms: candle for candle in candles}
        closed_daily = tuple(candle for candle in daily if candle.close_time_ms < cutoff)
        if any(observed.get(candle.open_time_ms) != candle for candle in closed_daily):
            raise MarketError("prediction_dataset_candles_differ_from_snapshot")
        _validate_prediction_history(candles, metadata, bundle)
        config = PredictionConfig.from_dict(bundle["configuration"])
        rows = build_features(candles, config)
        if not rows:
            raise MarketError("insufficient_daily_history_for_predictive_features")
        row = rows[-1]
        if row.origin_ms != origin:
            raise MarketError("prediction_feature_origin_does_not_match_latest_closed_D1")
        return forecast(bundle, row, symbol, cutoff, snapshot["source"])
    except (MarketError, ValueError, TypeError, KeyError, IndexError, ArithmeticError) as exc:
        return _unavailable_predictions(
            cutoff, "prediction_unavailable: " + str(exc), origin, bundle=bundle
        )


def _validate_prediction_history(
    candles: tuple[Candle, ...], metadata: dict[str, Any], bundle: dict[str, Any]
) -> None:
    """History can append right, while the frozen model context remains identical."""
    from .prediction.dataset import history_digest

    trained_metadata = bundle["dataset"]
    if metadata.get("first_observed_open_ms") != trained_metadata.get("first_observed_open_ms"):
        raise MarketError("prediction_dataset_historical_start_does_not_match_model_context")
    until = trained_metadata.get("last_closed_available_ms")
    if type(until) is not int or not candles or until > candles[-1].close_time_ms + 1:
        raise MarketError("prediction_dataset_does_not_include_complete_training_history")
    if history_digest(candles, until) != bundle.get("history_sha256"):
        raise MarketError("prediction_dataset_training_history_revised_or_missing")
