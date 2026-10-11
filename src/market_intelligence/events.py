"""Causal event journal: revisions append facts rather than rewrite history."""

from dataclasses import asdict, dataclass, replace
from typing import Any, Literal

from .models import Candle, Interval, MarketError
from .validation import validate

State = Literal["candidate", "confirmed", "invalidated"]


@dataclass(frozen=True)
class Event:
    id: str
    kind: str
    event_time_ms: int
    detected_at_ms: int
    available_at_ms: int
    price: float
    interval: str
    state: State
    evidence: tuple[dict[str, Any], ...]
    parameters: dict[str, Any]
    confirmed_at_ms: int | None = None
    invalidated_at_ms: int | None = None

    def transition(self, state: State, time_ms: int, evidence: dict[str, Any]) -> "Event":
        if self.state == "invalidated" or time_ms < self.available_at_ms:
            raise ValueError("invalid event transition")
        return replace(
            self,
            state=state,
            available_at_ms=time_ms,
            confirmed_at_ms=time_ms if state == "confirmed" else self.confirmed_at_ms,
            invalidated_at_ms=time_ms if state == "invalidated" else None,
            evidence=self.evidence + (evidence,),
        )


def observed(
    kind: str,
    candle: Candle,
    interval: Interval,
    price: float,
    parameters: dict[str, Any],
    evidence: dict[str, Any],
    state: State = "candidate",
    suffix: str = "",
) -> Event:
    available = candle.close_time_ms + 1
    return Event(
        f"{interval.name}:{kind}:{candle.open_time_ms}{suffix}",
        kind,
        candle.open_time_ms,
        available,
        available,
        price,
        interval.value,
        state,
        (evidence,),
        parameters,
        available if state == "confirmed" else None,
    )


def current_events(journal: list[Event]) -> list[Event]:
    current: dict[str, Event] = {}
    for event in journal:
        current[event.id] = event
    return list(current.values())


def serialize_events(events: list[Event]) -> list[dict[str, Any]]:
    return [asdict(event) for event in events]


def closed_history(
    candles: tuple[Candle, ...], interval: Interval, as_of_ms: int
) -> tuple[Candle, ...]:
    if not candles:
        return ()
    closed, quality = validate(candles, interval, as_of_ms, minimum=1)
    if not quality.valid:
        raise MarketError("Module input failed validation: " + "; ".join(quality.errors))
    return closed
