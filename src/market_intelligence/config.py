"""Explicit, validated configuration; no hidden environment or clock inputs."""

from dataclasses import dataclass, field
from typing import Any

from .models import MarketError
from .structure import StructureConfig
from .wyckoff import WyckoffConfig


@dataclass(frozen=True)
class AnalysisConfig:
    structure: StructureConfig = field(default_factory=StructureConfig)
    wyckoff: WyckoffConfig = field(default_factory=WyckoffConfig)
    scenario_freshness_bars: int = 12

    def __post_init__(self) -> None:
        if (
            type(self.scenario_freshness_bars) is not int
            or not 1 <= self.scenario_freshness_bars <= 500
        ):
            raise ValueError("scenario_freshness_bars must be an integer in [1, 500]")

    @classmethod
    def from_dict(cls, value: Any) -> "AnalysisConfig":
        if not isinstance(value, dict) or set(value) - {
            "structure",
            "wyckoff",
            "scenario_freshness_bars",
        }:
            raise MarketError("Invalid analysis configuration sections")
        try:
            return cls(
                StructureConfig(**value.get("structure", {})),
                WyckoffConfig(**value.get("wyckoff", {})),
                value.get("scenario_freshness_bars", 12),
            )
        except (ValueError, TypeError) as exc:
            raise MarketError(f"Invalid analysis configuration: {exc}") from exc
