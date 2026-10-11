"""Operational range observations and cautious Wyckoff hypotheses, not phase labels."""

import math
import statistics
from dataclasses import asdict, dataclass, replace
from typing import Any

from .events import Event, closed_history, current_events, observed, serialize_events
from .models import Candle, Interval


@dataclass(frozen=True)
class WyckoffConfig:
    version: str = "wyckoff-v1"
    range_lookback: int = 40
    min_touches: int = 2
    touch_tolerance: float = 0.1
    min_width_fraction: float = 0.003
    max_width_fraction: float = 0.25
    max_efficiency: float = 0.35
    min_inside_fraction: float = 0.8
    range_confirmation_closes: int = 2
    break_buffer_width: float = 0.02
    signal_window: int = 8
    retest_window: int = 12
    strength_volume_ratio: float = 1.2
    confirmation_volume_ratio: float = 0.8
    min_body_fraction: float = 0.5
    min_liquid_fraction: float = 0.8
    low_volume_ratio: float = 0.1
    min_quote_volume: float = 0.0

    def __post_init__(self) -> None:
        if self.version != "wyckoff-v1":
            raise ValueError("unsupported Wyckoff rule version")
        for value in (
            self.range_lookback,
            self.min_touches,
            self.range_confirmation_closes,
            self.signal_window,
            self.retest_window,
        ):
            if type(value) is not int or not 1 <= value <= 500:
                raise ValueError("Wyckoff counts must be integers in [1, 500]")
        if self.range_lookback < 10:
            raise ValueError("range_lookback must be at least 10")
        if self.retest_window < self.signal_window:
            raise ValueError("retest_window must cover signal_window")
        fractions = (
            self.touch_tolerance,
            self.max_efficiency,
            self.min_inside_fraction,
            self.break_buffer_width,
            self.min_body_fraction,
            self.min_liquid_fraction,
            self.low_volume_ratio,
        )
        if any(not math.isfinite(v) or not 0 <= v <= 1 for v in fractions):
            raise ValueError("Wyckoff fractions must be finite and in [0, 1]")
        if not 0 < self.min_width_fraction < self.max_width_fraction <= 1:
            raise ValueError("invalid range width bounds")
        if any(
            not math.isfinite(v) or v < 0
            for v in (
                self.strength_volume_ratio,
                self.confirmation_volume_ratio,
                self.min_quote_volume,
            )
        ):
            raise ValueError("volume thresholds must be finite and nonnegative")


@dataclass
class RangeContext:
    event: Event
    lower: float
    upper: float
    start: int
    confirmations: int
    prior_trend: str
    breakout_index: int | None = None
    breakout_direction: str | None = None
    breakout_volume: float | None = None


@dataclass
class Signal:
    event: Event
    index: int
    lower: float
    upper: float
    trigger: float
    direction: str
    origin_liquid: bool
    origin_strength: bool


def _touches(flags: list[bool]) -> int:
    return sum(flag and (i == 0 or not flags[i - 1]) for i, flag in enumerate(flags))


def find_range(past: tuple[Candle, ...], config: WyckoffConfig) -> dict[str, Any] | None:
    if len(past) < config.range_lookback:
        return None
    window = past[-config.range_lookback :]
    lower, upper = min(c.low for c in window), max(c.high for c in window)
    width = upper - lower
    mid = (upper + lower) / 2
    if mid <= 0 or not config.min_width_fraction <= width / mid <= config.max_width_fraction:
        return None
    closes = [c.close for c in window]
    travel = sum(abs(b - a) for a, b in zip(closes, closes[1:]))
    efficiency = abs(closes[-1] - closes[0]) / travel if travel else 0.0
    tolerance = width * config.touch_tolerance
    lower_touches = _touches([c.low <= lower + tolerance for c in window])
    upper_touches = _touches([c.high >= upper - tolerance for c in window])
    inside = sum(lower + tolerance <= c.close <= upper - tolerance for c in window) / len(window)
    liquid = sum(
        c.volume > 0 and c.trades > 0 and c.quote_volume >= config.min_quote_volume for c in window
    ) / len(window)
    if (
        efficiency > config.max_efficiency
        or lower_touches < config.min_touches
        or upper_touches < config.min_touches
        or inside < config.min_inside_fraction
        or liquid < config.min_liquid_fraction
    ):
        return None
    return {
        "lower": lower,
        "upper": upper,
        "width_fraction": width / mid,
        "lower_touches": lower_touches,
        "upper_touches": upper_touches,
        "efficiency": efficiency,
        "inside_fraction": inside,
        "liquid_fraction": liquid,
        "window_start_ms": window[0].open_time_ms,
        "window_end_ms": window[-1].close_time_ms,
    }


def analyze_wyckoff(
    candles: tuple[Candle, ...],
    interval: Interval,
    as_of_ms: int,
    structure: dict[str, Any],
    config: WyckoffConfig = WyckoffConfig(),
) -> dict[str, Any]:
    history = closed_history(candles, interval, as_of_ms)
    params = asdict(config)
    journal: list[Event] = []
    context: RangeContext | None = None
    signals: list[Signal] = []
    emitted: set[tuple[str, str]] = set()
    liquidity: list[dict[str, Any]] = []
    next_range = config.range_lookback
    structural_history = {
        row["available_at_ms"]: row["trend"] for row in structure.get("trend_history", [])
    }
    for i, candle in enumerate(history):
        now = candle.close_time_ms + 1
        past = history[:i]
        baseline = statistics.fmean(c.volume for c in past[-20:]) if past else 0.0
        ratio = candle.volume / baseline if baseline > 0 else None
        liquid = (
            candle.volume > 0
            and candle.trades > 0
            and candle.quote_volume >= config.min_quote_volume
            and ratio is not None
            and ratio >= config.low_volume_ratio
        )
        if not liquid:
            liquidity.append(
                {
                    "event_time_ms": candle.open_time_ms,
                    "available_at_ms": now,
                    "volume_ratio": ratio,
                    "trades": candle.trades,
                    "reason": "insufficient_observed_liquidity",
                }
            )
        span = candle.high - candle.low
        body = abs(candle.close - candle.open) / span if span else 0.0
        strength = (
            liquid
            and ratio is not None
            and ratio >= config.strength_volume_ratio
            and body >= config.min_body_fraction
        )
        remaining = []
        for signal in signals:
            elapsed = i - signal.index
            if signal.event.state == "confirmed" and elapsed > config.retest_window:
                continue
            if elapsed <= 0:
                remaining.append(signal)
                continue
            lower, upper = signal.lower, signal.upper
            is_retest = signal.event.kind in ("LPS", "LPSY")
            tolerance = (upper - lower) * config.touch_tolerance
            invalid = (
                candle.close < (upper - tolerance if is_retest else lower)
                if signal.direction == "up"
                else candle.close > (lower + tolerance if is_retest else upper)
            )
            if signal.event.kind == "SOS":
                invalid = candle.close <= upper
            elif signal.event.kind == "SOW":
                invalid = candle.close >= lower
            if invalid:
                journal.append(
                    signal.event.transition(
                        "invalidated",
                        now,
                        {"close": candle.close, "reason": "invalidation_level_crossed"},
                    )
                )
                continue
            if signal.event.state == "candidate":
                beyond = (
                    candle.close > signal.trigger
                    if signal.direction == "up"
                    else candle.close < signal.trigger
                )
                volume_ok = ratio is not None and ratio >= config.confirmation_volume_ratio
                if (
                    liquid
                    and signal.origin_liquid
                    and signal.origin_strength
                    and beyond
                    and volume_ok
                ):
                    signal.event = signal.event.transition(
                        "confirmed",
                        now,
                        {
                            "close": candle.close,
                            "trigger": signal.trigger,
                            "volume_ratio": ratio,
                            "liquid": liquid,
                            "observation": "subsequent_close_follow_through",
                            "interpretation": "rule_supported_not_certain_phase",
                        },
                    )
                    journal.append(signal.event)
                    if context and signal.event.kind in ("SOS", "SOW"):
                        context.breakout_index = i
                        context.breakout_direction = signal.direction
                        context.breakout_volume = history[signal.index].volume
                        if context.event.state == "confirmed":
                            context.event = context.event.transition(
                                "invalidated",
                                now,
                                {
                                    "reason": "range_close_break_confirmed",
                                    "signal_id": signal.event.id,
                                },
                            )
                            journal.append(context.event)
                elif elapsed >= config.signal_window:
                    journal.append(
                        signal.event.transition(
                            "invalidated", now, {"reason": "follow_through_timeout"}
                        )
                    )
                    continue
            if elapsed <= config.retest_window:
                remaining.append(signal)
        signals = remaining
        if (
            context
            and context.breakout_index is not None
            and i - context.breakout_index > config.retest_window
        ):
            context = None
            next_range = i + config.range_lookback
        if context and context.event.state == "candidate":
            if not context.lower <= candle.close <= context.upper:
                journal.append(
                    context.event.transition(
                        "invalidated", now, {"reason": "range_candidate_close_outside"}
                    )
                )
                context = None
                next_range = i + config.range_lookback
            elif liquid:
                context.confirmations += 1
                if context.confirmations >= config.range_confirmation_closes:
                    context.event = context.event.transition(
                        "confirmed", now, {"inside_confirmation_closes": context.confirmations}
                    )
                    journal.append(context.event)
        if context is None and i >= next_range:
            found = find_range(past, config)
            if found and found["lower"] <= candle.close <= found["upper"]:
                event = observed(
                    "trading_range",
                    candle,
                    interval,
                    (found["lower"] + found["upper"]) / 2,
                    params,
                    {"observation": "past_window_bounded_repeated_extremes", **found},
                )
                event = replace(event, event_time_ms=found["window_start_ms"])
                journal.append(event)
                prior = structural_history.get(history[i - 1].close_time_ms + 1, "indeterminado")
                context = RangeContext(
                    event, found["lower"], found["upper"], i, 1 if liquid else 0, prior
                )
                if liquid and config.range_confirmation_closes == 1:
                    context.event = event.transition(
                        "confirmed", now, {"inside_confirmation_closes": 1}
                    )
                    journal.append(context.event)
        if not context or context.event.state == "candidate":
            continue
        lower, upper = context.lower, context.upper
        width = upper - lower
        buffer = width * config.break_buffer_width
        tolerance = width * config.touch_tolerance
        range_id = context.event.id
        inside = lower <= candle.close <= upper
        for kind, tested in (
            ("range_lower_test", candle.low <= lower + tolerance and inside),
            ("range_upper_test", candle.high >= upper - tolerance and inside),
        ):
            if tested:
                journal.append(
                    observed(
                        kind,
                        candle,
                        interval,
                        lower if kind == "range_lower_test" else upper,
                        params,
                        {
                            "range_id": range_id,
                            "close": candle.close,
                            "observation": "extreme_test_close_inside",
                        },
                        "confirmed",
                    )
                )
        candidates = [
            ("Spring", candle.low < lower - buffer and inside, "up", candle.high, True),
            ("Upthrust", candle.high > upper + buffer and inside, "down", candle.low, True),
            ("SOS", candle.close > upper + buffer, "up", upper + buffer, strength),
            ("SOW", candle.close < lower - buffer, "down", lower - buffer, strength),
        ]
        if context.breakout_index is not None and i > context.breakout_index:
            up = context.breakout_direction == "up"
            retest = (
                upper - tolerance <= candle.low <= upper + tolerance and candle.close >= upper
                if up
                else lower - tolerance <= candle.high <= lower + tolerance and candle.close <= lower
            )
            lower_volume = (
                context.breakout_volume is not None and candle.volume <= context.breakout_volume
            )
            candidates.append(
                (
                    "LPS" if up else "LPSY",
                    retest and lower_volume,
                    "up" if up else "down",
                    candle.high if up else candle.low,
                    True,
                )
            )
        for kind, matched, direction, trigger, origin_strength in candidates:
            key = (range_id, kind)
            if not matched or key in emitted:
                continue
            event = observed(
                kind,
                candle,
                interval,
                candle.close,
                params,
                {
                    "range_id": range_id,
                    "lower": lower,
                    "upper": upper,
                    "low": candle.low,
                    "high": candle.high,
                    "close": candle.close,
                    "volume_ratio": ratio,
                    "body_fraction": body,
                    "liquid": liquid,
                    "strength_filter": origin_strength,
                    "observation": "sweep_and_close_inside"
                    if kind in ("Spring", "Upthrust")
                    else "close_outside_or_retest",
                    "interpretation": "possible_" + kind,
                    "prior_trend": context.prior_trend,
                },
            )
            journal.append(event)
            signals.append(
                Signal(event, i, lower, upper, trigger, direction, liquid, origin_strength)
            )
            emitted.add(key)
    current = current_events(journal)
    hypotheses = []
    for event in current:
        if event.kind not in ("Spring", "Upthrust", "SOS", "SOW") or event.state == "invalidated":
            continue
        if as_of_ms - event.available_at_ms > config.retest_window * interval.milliseconds:
            continue
        bullish = event.kind in ("Spring", "SOS")
        prior = event.evidence[0].get("prior_trend", "indeterminado")
        interpretation = (
            ("reaccumulation" if prior == "alta" else "accumulation")
            if bullish
            else ("redistribution" if prior == "baixa" else "distribution")
        )
        hypotheses.append(
            {
                "interpretation": interpretation,
                "state": "candidate",
                "event_ids": [event.id],
                "support": event.state,
                "observation": event.evidence[0],
                "phase": None,
                "limitation": "pattern_rules_do_not_establish_inventory_or_Wyckoff_phase",
            }
        )
    active_range = None
    if context:
        active_range = {
            "id": context.event.id,
            "lower": context.lower,
            "upper": context.upper,
            "state": context.event.state,
            "prior_trend": context.prior_trend,
            "available_at_ms": context.event.available_at_ms,
            "breakout_direction": context.breakout_direction,
        }
    return {
        "version": config.version,
        "parameters": params,
        "range": active_range,
        "events": serialize_events(current),
        "event_journal": serialize_events(journal),
        "hypotheses": hypotheses,
        "liquidity_warnings": liquidity,
        "insufficient_data": []
        if any(e.kind == "trading_range" and e.confirmed_at_ms is not None for e in current)
        else ["no_rule_supported_trading_range"],
        "limitations": [
            "OHLCV cannot establish institutional accumulation/distribution",
            "confirmed means rule confirmed; phase remains a hypothesis",
        ],
    }
