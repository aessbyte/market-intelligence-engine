"""Compare closed D1/H4/H1 evidence without ranking a timeframe as truth."""

from typing import Any


def compare_timeframes(frames: dict[str, Any], as_of_ms: int) -> dict[str, Any]:
    roles = {
        "D1": "broader_structural_context",
        "H4": "intermediate_development",
        "H1": "detail_and_early_signals",
    }
    observations = []
    usable: dict[str, dict[str, Any]] = {}
    for name, role in roles.items():
        frame = frames.get(name, {})
        structure = frame.get("structure")
        ready = bool(frame.get("quality", {}).get("valid")) and isinstance(structure, dict)
        if ready:
            assert structure is not None
            close_time = structure.get("last_close_time_ms")
            ready = close_time is not None and close_time < as_of_ms
            for module in (structure, frame.get("wyckoff", {})):
                if any(
                    e["available_at_ms"] > as_of_ms
                    or (e.get("confirmed_at_ms") is not None and e["confirmed_at_ms"] > as_of_ms)
                    for e in module.get("event_journal", [])
                ):
                    raise ValueError("multitimeframe received an event beyond the cutoff")
        observation = {
            "timeframe": name,
            "role": role,
            "available": ready,
            "structural_trend": structure["trend"] if ready else "indeterminado",
            "indicator_regime": frame.get("regime", "indeterminado"),
            "last_closed_ms": structure.get("last_close_time_ms") if ready else None,
        }
        observations.append(observation)
        if ready:
            usable[name] = observation
    agreements, conflicts = [], []
    names = list(usable)
    for i, name in enumerate(names):
        for other in names[i + 1 :]:
            a, b = usable[name]["structural_trend"], usable[other]["structural_trend"]
            record = {
                "timeframes": [name, other],
                "observed": [a, b],
                "basis": "closed_structural_trends",
            }
            if a == b and a != "indeterminado":
                agreements.append(record)
            elif a != "indeterminado" and b != "indeterminado":
                conflicts.append(record)
    divergences = [
        {
            "timeframe": o["timeframe"],
            "structure": o["structural_trend"],
            "indicators": o["indicator_regime"],
        }
        for o in observations
        if o["available"]
        and o["structural_trend"] != "indeterminado"
        and o["indicator_regime"] != "indeterminado"
        and o["structural_trend"] != o["indicator_regime"]
    ]
    trends = [o["structural_trend"] for o in observations]
    consensus = trends[0] if len(usable) == 3 and len(set(trends)) == 1 else "indeterminado"
    return {
        "version": "multitimeframe-v1",
        "as_of_ms": as_of_ms,
        "observations": observations,
        "agreements": agreements,
        "conflicts": conflicts,
        "indicator_structure_divergences": divergences,
        "structural_consensus": consensus,
        "insufficient_data": [o["timeframe"] for o in observations if not o["available"]],
        "policy": "equal_evidence_weight_no_timeframe_is_truth",
    }
