"""Immutable boundaries shared by dataset, modelling and inference modules."""

from dataclasses import asdict, dataclass
import math
from typing import Any

from ..models import MarketError

DAY_MS = 86_400_000
CLASSES = ("bearish", "neutral", "bullish")
HORIZONS = (7, 30, 90)


@dataclass(frozen=True)
class PredictionConfig:
    version: str = "prediction-config-v1"
    seed: int = 42
    warmup: int = 100
    feature_window: int = 250
    volatility_window: int = 30
    label_sigma: float = 0.5
    initial_train_days: int = 730
    validation_days: int = 180
    calibration_days: int = 180
    test_days: int = 365
    embargo_days: int = 7
    min_train: int = 250
    min_validation: int = 50
    min_calibration: int = 60
    min_class: int = 10
    min_independent_tests: int = 30
    min_boosting_train: int = 1500
    max_calibration_error: float = 0.15
    drift_z_limit: float = 6.0
    logistic_c: float = 0.1

    def __post_init__(self) -> None:
        if self.version != "prediction-config-v1":
            raise ValueError("unsupported prediction configuration")
        for name in (
            "seed",
            "warmup",
            "feature_window",
            "volatility_window",
            "initial_train_days",
            "validation_days",
            "calibration_days",
            "test_days",
            "embargo_days",
            "min_train",
            "min_validation",
            "min_calibration",
            "min_class",
            "min_independent_tests",
            "min_boosting_train",
        ):
            value = getattr(self, name)
            if type(value) is not int or value < (0 if name in ("seed", "embargo_days") else 1):
                raise ValueError(f"invalid integer configuration: {name}")
        if (
            self.warmup < 100
            or self.feature_window < self.warmup
            or self.volatility_window >= self.warmup
        ):
            raise ValueError("invalid feature warmup/windows")
        for name in ("label_sigma", "max_calibration_error", "drift_z_limit", "logistic_c"):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value <= 0
            ):
                raise ValueError(f"invalid positive configuration: {name}")
        if self.max_calibration_error > 1:
            raise ValueError("calibration error must be in (0,1]")

    @classmethod
    def from_dict(cls, value: Any) -> "PredictionConfig":
        if not isinstance(value, dict):
            raise MarketError("prediction configuration must be an object")
        try:
            return cls(**value)
        except (TypeError, ValueError) as exc:
            raise MarketError(f"invalid prediction configuration: {exc}") from exc

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FeatureRow:
    origin_ms: int
    close: float
    sigma: float
    values: tuple[float, ...]
    regime: str
    available_at_ms: tuple[int, ...]
    sources: tuple[str, ...]


@dataclass(frozen=True)
class Sample:
    row: FeatureRow
    horizon_days: int
    end_ms: int
    target_available_ms: int
    label: int
    log_return: float
    return_value: float
    normalized_return: float
    upper_log_threshold: float
    lower_log_threshold: float
    maximum_favorable_excursion: float
    maximum_adverse_excursion: float
