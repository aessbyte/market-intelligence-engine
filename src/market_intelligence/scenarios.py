"""Three conditional theses. Forecast slots stay explicitly unavailable."""

from typing import Any


def build_scenarios(
    frames: dict[str, Any], comparison: dict[str, Any], as_of_ms: int, freshness_bars: int = 12
) -> list[dict[str, Any]]:
    step = {"H1": 3_600_000, "H4": 14_400_000, "D1": 86_400_000}
    votes = {"alta": 0, "baixa": 0, "lateralizacao": 0}
    directional: dict[str, list[dict[str, Any]]] = {"up": [], "down": []}
    levels: list[dict[str, Any]] = []
    ranges: list[dict[str, Any]] = []
    broken_ranges: list[dict[str, Any]] = []
    missing = list(comparison["insufficient_data"])
    observations = []
    for name in ("D1", "H4", "H1"):
        frame = frames.get(name, {})
        structure, wyckoff = frame.get("structure"), frame.get("wyckoff")
        if (
            not frame.get("quality", {}).get("valid")
            or not isinstance(structure, dict)
            or not isinstance(wyckoff, dict)
        ):
            if name not in missing:
                missing.append(name)
            continue
        trend = structure["trend"]
        if trend in votes:
            votes[trend] += 1
        observations.append(
            {
                "timeframe": name,
                "structural_trend": trend,
                "close": structure["last_close"],
                "available_at_ms": structure["last_close_time_ms"] + 1,
            }
        )
        if any(
            warning["event_time_ms"] == structure["last_close_time_ms"] - step[name] + 1
            for warning in wyckoff["liquidity_warnings"]
        ):
            missing.append(name + ":latest_candle_low_liquidity")
        levels.extend({"timeframe": name, **level} for level in structure["levels"])
        trading_range = wyckoff["range"]
        if trading_range:
            if trading_range["state"] == "invalidated" and trading_range.get("breakout_direction"):
                broken_ranges.append(
                    {
                        "timeframe": name,
                        "range_id": trading_range["id"],
                        "direction": trading_range["breakout_direction"],
                    }
                )
            levels.extend(
                [
                    {
                        "timeframe": name,
                        "kind": kind,
                        "price": trading_range[key],
                        "event_id": trading_range["id"],
                        "available_at_ms": trading_range["available_at_ms"],
                    }
                    for kind, key in (("range_support", "lower"), ("range_resistance", "upper"))
                ]
            )
            if (
                trading_range["state"] == "confirmed"
                and trading_range["lower"] <= structure["last_close"] <= trading_range["upper"]
            ):
                ranges.append(
                    {
                        "timeframe": name,
                        "range_id": trading_range["id"],
                        "lower": trading_range["lower"],
                        "upper": trading_range["upper"],
                    }
                )
        for event in structure["events"] + wyckoff["events"]:
            confirmation = event["confirmed_at_ms"]
            if (
                event["state"] != "confirmed"
                or confirmation is None
                or as_of_ms - confirmation > freshness_bars * step[name]
            ):
                continue
            direction = event["evidence"][0].get("direction")
            if event["kind"] in ("Spring", "SOS", "LPS"):
                direction = "up"
            elif event["kind"] in ("Upthrust", "SOW", "LPSY"):
                direction = "down"
            elif event["kind"] not in ("BOS", "CHoCH"):
                continue
            if direction in directional:
                directional[direction].append(
                    {
                        "timeframe": name,
                        "event_id": event["id"],
                        "kind": event["kind"],
                        "confirmed_at_ms": confirmation,
                    }
                )
    latest = next((o for o in observations if o["timeframe"] == "H1"), None)
    support = next(
        (
            level
            for level in reversed(levels)
            if level["timeframe"] == "H1" and level["kind"] == "support"
        ),
        None,
    )
    resistance = next(
        (
            level
            for level in reversed(levels)
            if level["timeframe"] == "H1" and level["kind"] == "resistance"
        ),
        None,
    )
    bull_failed = latest is not None and support is not None and latest["close"] < support["price"]
    bear_failed = (
        latest is not None and resistance is not None and latest["close"] > resistance["price"]
    )
    active = {
        "bullish": not missing
        and support is not None
        and votes["alta"] >= 2
        and votes["baixa"] == 0
        and bool(directional["up"])
        and not bull_failed,
        "bearish": not missing
        and resistance is not None
        and votes["baixa"] >= 2
        and votes["alta"] == 0
        and bool(directional["down"])
        and not bear_failed,
        "neutral": not missing and len(ranges) >= 2 and votes["alta"] < 2 and votes["baixa"] < 2,
    }
    result = []
    for name, trend, opposite, direction in (
        ("bullish", "alta", "baixa", "up"),
        ("bearish", "baixa", "alta", "down"),
        ("neutral", "lateralizacao", "indeterminado", "none"),
    ):
        neutral = name == "neutral"
        failed = (
            bull_failed
            if name == "bullish"
            else bear_failed
            if name == "bearish"
            else active["bullish"] or active["bearish"] or len(broken_ranges) >= 2
        )
        contradictory_votes = 0 if neutral else votes[opposite]
        invalidated = not missing and (failed or contradictory_votes >= 2)
        state = (
            "active" if active[name] else "invalidated" if invalidated else "awaiting_confirmation"
        )
        favorable = (
            [{"observation": "close_inside_confirmed_range", **r} for r in ranges]
            if neutral
            else [
                {"observation": "structural_trend", **o}
                for o in observations
                if o["structural_trend"] == trend
            ]
            + directional[direction]
        )
        contrary = (
            [
                {"observation": "directional_structure", **o}
                for o in observations
                if o["structural_trend"] in ("alta", "baixa")
            ]
            if neutral
            else [
                {"observation": "opposing_structural_trend", **o}
                for o in observations
                if o["structural_trend"] == opposite
            ]
            + directional["down" if direction == "up" else "up"]
        )
        thesis = {
            "bullish": "Continuidade ou desenvolvimento de estrutura ascendente com confirmacao em candles fechados.",
            "bearish": "Continuidade ou desenvolvimento de estrutura descendente com confirmacao em candles fechados.",
            "neutral": "Persistencia de faixas confirmadas, sem concordancia direcional suficiente.",
        }[name]
        activation = (
            [
                {
                    "rule": "inside_confirmed_ranges_on_two_timeframes",
                    "observed": len(ranges),
                    "required": 2,
                    "met": len(ranges) >= 2,
                },
                {
                    "rule": "no_two_directional_structural_votes",
                    "met": votes["alta"] < 2 and votes["baixa"] < 2,
                },
            ]
            if neutral
            else [
                {
                    "rule": "two_structural_votes",
                    "observed": votes[trend],
                    "required": 2,
                    "met": votes[trend] >= 2,
                },
                {
                    "rule": "no_opposing_structural_vote",
                    "observed": contradictory_votes,
                    "met": contradictory_votes == 0,
                },
                {
                    "rule": "fresh_confirmed_directional_event",
                    "event_ids": [e["event_id"] for e in directional[direction]],
                    "met": bool(directional[direction]),
                },
            ]
        )
        boundary = support if name == "bullish" else resistance if name == "bearish" else None
        if not neutral:
            activation.append(
                {
                    "rule": "H1_invalidation_boundary_available_and_holding",
                    "level": boundary,
                    "met": boundary is not None and not failed,
                }
            )
        invalidations = (
            [
                {
                    "rule": "confirmed_directional_scenario",
                    "met": active["bullish"] or active["bearish"],
                },
                {
                    "rule": "two_confirmed_range_breaks",
                    "observed": broken_ranges,
                    "met": len(broken_ranges) >= 2,
                },
            ]
            if neutral
            else [
                {
                    "rule": "two_opposing_structural_votes",
                    "observed": contradictory_votes,
                    "met": contradictory_votes >= 2,
                },
                {
                    "rule": "H1_close_below_support"
                    if name == "bullish"
                    else "H1_close_above_resistance",
                    "level": boundary,
                    "observed_close": latest["close"] if latest else None,
                    "met": bool(failed),
                    "available": boundary is not None,
                },
            ]
        )
        if not favorable:
            insufficient = missing + ["no_supporting_structure_or_confirmed_event"]
        else:
            insufficient = missing.copy()
        if not neutral and boundary is None:
            insufficient.append("no_confirmed_H1_invalidation_level")
        result.append(
            {
                "name": name,
                "thesis": thesis,
                "condition": thesis,
                "invalidation": "Reavaliar ao satisfazer qualquer condicao explicita de invalidacao.",
                "state": state,
                "favorable_evidence": favorable,
                "contrary_evidence": contrary,
                "activation_conditions": activation
                + [{"rule": "all_timeframes_available", "met": not missing}],
                "invalidation_conditions": invalidations,
                "structural_levels": levels,
                "insufficient_data": insufficient,
                "probability": None,
                "price_target": None,
                "forecast": {
                    "status": "unavailable",
                    "calibrated_probability": None,
                    "expected_return_interval": None,
                    "horizon": None,
                    "model_version": None,
                    "calibration_evidence": None,
                },
                "parameters": {
                    "version": "scenarios-v1",
                    "freshness_bars": freshness_bars,
                    "directional_votes_required": 2,
                },
                "as_of_ms": as_of_ms,
            }
        )
    return result
