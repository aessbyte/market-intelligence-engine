"""Reproducible real spot daily datasets; collection never substitutes simulation."""

from dataclasses import asdict
import hashlib
import json
from typing import Any

from ..binance import BinanceClient, normalize_symbol
from ..models import Candle, Interval, MarketError
from ..validation import parse_klines, validate
from .contracts import DAY_MS

DATASET_VERSION = "binance-spot-daily-v1"


def history_digest(candles: tuple[Candle, ...], until_ms: int | None = None) -> str:
    """Hash parsed historical inputs, independently of later acquisition metadata."""
    observed = [
        asdict(candle)
        for candle in candles
        if until_ms is None or candle.close_time_ms + 1 <= until_ms
    ]
    encoded = json.dumps(observed, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode()).hexdigest()


def dataset_digest(value: dict[str, Any]) -> str:
    payload = {key: item for key, item in value.items() if key != "dataset_sha256"}
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    return hashlib.sha256(encoded.encode()).hexdigest()


def create_dataset(
    rows: list[Any],
    symbol: str,
    as_of_ms: int,
    server_time_ms: int,
    requested_bars: int,
    endpoint: str,
    symbol_info: dict[str, Any],
    source: str = "binance_public",
    selection: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Wrap observed rows, preserving short listings and data problems explicitly."""
    symbol = normalize_symbol(symbol)
    if source not in ("binance_public", "simulated"):
        raise MarketError("dataset must declare a supported source")
    if (
        type(as_of_ms) is not int
        or type(server_time_ms) is not int
        or not 0 < as_of_ms <= server_time_ms
    ):
        raise MarketError("invalid dataset cutoff/server timestamps")
    if type(requested_bars) is not int or not 100 <= requested_bars <= 5000:
        raise MarketError("requested dataset bars must be an integer in [100,5000]")
    candles = parse_klines(rows)
    closed, quality = validate(candles, Interval.D1, as_of_ms, minimum=1)
    requested_start = max(0, (as_of_ms // DAY_MS - requested_bars) * DAY_MS)
    value: dict[str, Any] = {
        "dataset_version": DATASET_VERSION,
        "exchange": "binance",
        "market": "spot",
        "symbol": symbol,
        "interval": "1d",
        "timezone": "UTC",
        "source": source,
        "simulated": source == "simulated",
        "endpoint": endpoint,
        "as_of_ms": as_of_ms,
        "server_time_ms": server_time_ms,
        "requested_bars": requested_bars,
        "requested_start_ms": requested_start,
        "first_observed_open_ms": closed[0].open_time_ms if closed else None,
        "last_closed_available_ms": closed[-1].close_time_ms + 1 if closed else None,
        "short_history": len(closed) < requested_bars,
        "listing_boundary_unknown": True,
        "source_claim_verified": False,
        "availability_assumption": "historical candles available at close+1ms; original publication latency/revisions not known",
        "symbol_info": symbol_info,
        "quality": asdict(quality),
        "klines": rows,
        "selection": selection,
        "limitations": [
            "exchangeInfo is current, not point-in-time listing metadata",
            "short history may reflect listing, requested start or provider omissions; not automatically labelled listing date",
            "SHA256 checks content equality, not authenticity or historical revision absence",
        ],
    }
    value["dataset_sha256"] = dataset_digest(value)
    return value


def collect_dataset(
    client: BinanceClient,
    symbol: str,
    bars: int = 5000,
    as_of_ms: int | None = None,
) -> dict[str, Any]:
    symbol = normalize_symbol(symbol)
    server = client.server_time()
    cutoff = server if as_of_ms is None else as_of_ms
    if type(cutoff) is not int or not 0 < cutoff <= server:
        raise MarketError("dataset cutoff must not exceed Binance server time")
    info = client.symbol_info(symbol)
    rows = client.klines(symbol, Interval.D1, cutoff, bars)
    return create_dataset(
        rows,
        symbol,
        cutoff,
        server,
        bars,
        getattr(client.transport, "base_url", "injected_transport"),
        info,
    )


def validate_dataset(value: Any) -> tuple[tuple[Candle, ...], dict[str, Any]]:
    if not isinstance(value, dict) or value.get("dataset_version") != DATASET_VERSION:
        raise MarketError("unsupported daily dataset envelope")
    if (
        value.get("exchange"),
        value.get("market"),
        value.get("interval"),
        value.get("timezone"),
    ) != ("binance", "spot", "1d", "UTC"):
        raise MarketError("dataset exchange/market/interval/timezone mismatch")
    try:
        if value.get("dataset_sha256") != dataset_digest(value):
            raise MarketError("dataset checksum mismatch")
        regenerated = create_dataset(
            value["klines"],
            value["symbol"],
            value["as_of_ms"],
            value["server_time_ms"],
            value["requested_bars"],
            value["endpoint"],
            value["symbol_info"],
            value["source"],
            value.get("selection"),
        )
        if regenerated != value:
            # JSON encodes tuples as lists. Compare canonical JSON at the boundary.
            if json.dumps(regenerated, sort_keys=True) != json.dumps(value, sort_keys=True):
                raise MarketError("dataset derived metadata inconsistent with observed rows")
        info = value["symbol_info"]
        if (
            not isinstance(info, dict)
            or info.get("symbol") != normalize_symbol(value["symbol"])
            or info.get("status") != "TRADING"
            or info.get("isSpotTradingAllowed") is not True
        ):
            raise MarketError("dataset spot symbol metadata unavailable/inconsistent")
        if not regenerated["quality"]["valid"]:
            raise MarketError(
                "dataset integrity failed: " + "; ".join(regenerated["quality"]["errors"])
            )
        candles, _ = validate(
            parse_klines(value["klines"]), Interval.D1, value["as_of_ms"], minimum=1
        )
        metadata = {key: item for key, item in regenerated.items() if key != "klines"}
        return candles, metadata
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise MarketError(f"invalid dataset: {exc}") from exc


def restrict_dataset(value: dict[str, Any], start_ms: int, reason: str) -> dict[str, Any]:
    """Explicit contiguous cohort selection; never repair individual candles/gaps."""
    if type(start_ms) is not int or start_ms < 0 or start_ms % DAY_MS or not reason.strip():
        raise MarketError("cohort start must be aligned UTC, with a selection reason")
    if value.get("dataset_sha256") != dataset_digest(value):
        raise MarketError("parent dataset checksum mismatch")
    selected = [row for row in value["klines"] if row[0] >= start_ms]
    selection = {
        "parent_dataset_sha256": value["dataset_sha256"],
        "start_ms": start_ms,
        "reason": reason,
        "excluded_rows": len(value["klines"]) - len(selected),
        "parent_quality": value["quality"],
    }
    result = create_dataset(
        selected,
        value["symbol"],
        value["as_of_ms"],
        value["server_time_ms"],
        max(100, min(value["requested_bars"], len(selected))),
        value["endpoint"],
        value["symbol_info"],
        value["source"],
        selection,
    )
    validate_dataset(result)
    return result
