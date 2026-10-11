"""Pure snapshot analysis: identical snapshot yields identical JSON."""

import hashlib
import json
import math
from dataclasses import asdict
from typing import Any

from . import __version__
from .binance import normalize_symbol
from .indicators import calculate
from .models import Interval, MarketError, Regime
from .regime import RULES, aggregate, classify, scenarios
from .validation import parse_klines, validate

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


def analyze(snapshot: dict[str, Any]) -> dict[str, Any]:
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
        regimes.append(regime)
    overall = aggregate(regimes)
    valid = all(f["quality"]["valid"] for f in frames.values())
    return {
        "schema_version": "1",
        "engine_version": __version__,
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
