"""Confirmed pivots, causal HH/HL/LH/LL and close-based structure breaks."""

import math
from dataclasses import asdict, dataclass
from typing import Any

from .events import Event, closed_history, current_events, observed, serialize_events
from .models import Candle, Interval, Regime


@dataclass(frozen=True)
class StructureConfig:
    version: str = "structure-v1"
    left_bars: int = 2
    right_bars: int = 2
    equality_tolerance: float = 0.001
    break_buffer: float = 0.001
    confirmation_closes: int = 2
    false_break_window: int = 5

    def __post_init__(self) -> None:
        if self.version != "structure-v1":
            raise ValueError("unsupported structure rule version")
        for value in (
            self.left_bars,
            self.right_bars,
            self.confirmation_closes,
            self.false_break_window,
        ):
            if type(value) is not int or not 1 <= value <= 100:
                raise ValueError("structure counts must be integers in [1, 100]")
        for tolerance in (self.equality_tolerance, self.break_buffer):
            if not math.isfinite(tolerance) or not 0 <= tolerance <= 0.1:
                raise ValueError("structure tolerances must be finite fractions in [0, .1]")
        if self.confirmation_closes - 1 > self.false_break_window:
            raise ValueError("confirmation window exceeds break monitoring window")


@dataclass(frozen=True)
class Pivot:
    index: int
    event: Event
    label: str | None


def pivot_trend(highs: list[Pivot], lows: list[Pivot]) -> Regime:
    if len(highs) < 2 or len(lows) < 2:
        return Regime.UNKNOWN
    pair = (highs[-1].label, lows[-1].label)
    if pair == ("HH", "HL"):
        return Regime.BULL
    if pair == ("LH", "LL"):
        return Regime.BEAR
    if pair in (("EH", "EL"), ("LH", "HL")):
        return Regime.SIDEWAYS
    return Regime.UNKNOWN


def analyze_structure(
    candles: tuple[Candle, ...],
    interval: Interval,
    as_of_ms: int,
    config: StructureConfig = StructureConfig(),
) -> dict[str, Any]:
    history = closed_history(candles, interval, as_of_ms)
    params = asdict(config)
    journal: list[Event] = []
    pending: list[tuple[int, Event]] = []
    highs: list[Pivot] = []
    lows: list[Pivot] = []
    broken: set[str] = set()
    breaks: list[tuple[int, Event, str, float, int, Regime]] = []
    trend = Regime.UNKNOWN
    trend_history: list[dict[str, Any]] = []
    for i, candle in enumerate(history):
        now = candle.close_time_ms + 1
        # Breaks use levels available BEFORE this candle, not a retrospectively found pivot.
        new_breaks = []
        for start, event, direction, level, count, prior_trend in breaks:
            if event.state == "confirmed" and i - start > config.false_break_window:
                continue
            outside = (
                candle.close > level * (1 + config.break_buffer)
                if direction == "up"
                else candle.close < level * (1 - config.break_buffer)
            )
            returned = candle.close <= level if direction == "up" else candle.close >= level
            if returned:
                revised = event.transition(
                    "invalidated",
                    now,
                    {
                        "reason": "close_returned_across_level",
                        "close": candle.close,
                        "level": level,
                    },
                )
                journal.append(revised)
                broken.discard(event.evidence[0]["level_id"])
                journal.append(
                    observed(
                        "false_break",
                        candle,
                        interval,
                        level,
                        params,
                        {
                            "break_id": event.id,
                            "direction": direction,
                            "observation": "close_returned_across_level",
                        },
                        "confirmed",
                        suffix=":" + event.id,
                    )
                )
                if event.state == "confirmed":
                    trend = Regime.UNKNOWN
                continue
            if event.state == "candidate":
                count = count + 1 if outside else 0
                if count >= config.confirmation_closes:
                    event = event.transition(
                        "confirmed", now, {"consecutive_closes": count, "level": level}
                    )
                    journal.append(event)
                    trend = Regime.BULL if direction == "up" else Regime.BEAR
                elif i - start >= config.false_break_window:
                    journal.append(
                        event.transition("invalidated", now, {"reason": "confirmation_timeout"})
                    )
                    broken.discard(event.evidence[0]["level_id"])
                    continue
            if i - start <= config.false_break_window or event.state == "candidate":
                new_breaks.append((start, event, direction, level, count, prior_trend))
        breaks = new_breaks
        for direction, pivots in (("up", highs), ("down", lows)):
            if not pivots:
                continue
            pivot = pivots[-1]
            level = pivot.event.price
            outside = (
                candle.close > level * (1 + config.break_buffer)
                if direction == "up"
                else candle.close < level * (1 - config.break_buffer)
            )
            wick = candle.high > level if direction == "up" else candle.low < level
            if pivot.event.id not in broken and outside:
                kind = (
                    "CHoCH"
                    if (
                        direction == "up"
                        and trend == Regime.BEAR
                        or direction == "down"
                        and trend == Regime.BULL
                    )
                    else "BOS"
                )
                event = observed(
                    kind,
                    candle,
                    interval,
                    level,
                    params,
                    {
                        "direction": direction,
                        "level_id": pivot.event.id,
                        "level": level,
                        "prior_trend": trend.value,
                        "close": candle.close,
                    },
                )
                journal.append(event)
                broken.add(pivot.event.id)
                if config.confirmation_closes == 1:
                    event = event.transition("confirmed", now, {"consecutive_closes": 1})
                    journal.append(event)
                    trend = Regime.BULL if direction == "up" else Regime.BEAR
                breaks.append((i, event, direction, level, 1, trend))
            elif wick and not outside and pivot.event.id not in broken:
                journal.append(
                    observed(
                        "possible_false_break",
                        candle,
                        interval,
                        level,
                        params,
                        {
                            "direction": direction,
                            "level_id": pivot.event.id,
                            "close": candle.close,
                            "wick_crossed_level": True,
                        },
                        suffix=":" + pivot.event.id,
                    )
                )
        remaining = []
        for index, event in pending:
            value = candle.high if event.kind == "swing_high" else candle.low
            violated = value >= event.price if event.kind == "swing_high" else value <= event.price
            if violated:
                journal.append(
                    event.transition(
                        "invalidated", now, {"reason": "right_window_not_strict_extreme"}
                    )
                )
            elif i - index == config.right_bars:
                event = event.transition(
                    "confirmed", now, {"right_bars_observed": config.right_bars}
                )
                journal.append(event)
                pivots = highs if event.kind == "swing_high" else lows
                label = None
                if pivots:
                    previous = pivots[-1].event.price
                    delta = (event.price - previous) / previous
                    label = (
                        ("EH" if event.kind == "swing_high" else "EL")
                        if abs(delta) <= config.equality_tolerance
                        else ("HH" if delta > 0 else "LH")
                        if event.kind == "swing_high"
                        else ("HL" if delta > 0 else "LL")
                    )
                    relation = observed(
                        label,
                        history[index],
                        interval,
                        event.price,
                        params,
                        {
                            "previous_pivot_id": pivots[-1].event.id,
                            "previous_price": previous,
                            "relative_change": delta,
                        },
                        "confirmed",
                    )
                    # Relation is known at confirmation, never at the original pivot candle.
                    from dataclasses import replace

                    relation = replace(
                        relation, detected_at_ms=now, available_at_ms=now, confirmed_at_ms=now
                    )
                    journal.append(relation)
                pivots.append(Pivot(index, event, label))
                trend = pivot_trend(highs, lows)
            else:
                remaining.append((index, event))
        pending = remaining
        if i >= config.left_bars:
            left = history[i - config.left_bars : i]
            for kind, value, qualifies in (
                ("swing_high", candle.high, all(candle.high > c.high for c in left)),
                ("swing_low", candle.low, all(candle.low < c.low for c in left)),
            ):
                if qualifies:
                    event = observed(
                        kind,
                        candle,
                        interval,
                        value,
                        params,
                        {"left_bars_observed": config.left_bars, "rule": "strict_extreme_no_tie"},
                    )
                    pending.append((i, event))
                    journal.append(event)
        trend_history.append({"available_at_ms": now, "trend": trend.value})
    levels = [
        {
            "kind": kind,
            "price": pivot.event.price,
            "event_id": pivot.event.id,
            "available_at_ms": pivot.event.confirmed_at_ms,
            "label": pivot.label,
            "broken": pivot.event.id in broken,
        }
        for kind, group in (("resistance", highs), ("support", lows))
        for pivot in group[-3:]
    ]
    insufficient = (
        [] if len(highs) >= 2 and len(lows) >= 2 else ["need_two_confirmed_highs_and_lows"]
    )
    return {
        "version": config.version,
        "parameters": params,
        "trend": trend.value,
        "events": serialize_events(current_events(journal)),
        "event_journal": serialize_events(journal),
        "levels": levels,
        "trend_history": trend_history,
        "insufficient_data": insufficient,
        "last_close": history[-1].close if history else None,
        "last_close_time_ms": history[-1].close_time_ms if history else None,
    }
