"""Explicit process configuration; no credentials or implicit example fallbacks."""

from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(frozen=True)
class WebConfig:
    replay_snapshot: Path | None = None
    model_bundle: Path | None = None
    prediction_dataset: Path | None = None
    frontend_dist: Path | None = None
    cors_origins: tuple[str, ...] = ("http://localhost:5173", "http://127.0.0.1:5173")
    cache_seconds: float = 30.0
    retention_seconds: float = 1200.0
    max_records: int = 16
    max_cache_bytes: int = 64 * 1024 * 1024
    workers: int = 2
    max_pending: int = 8
    request_limit: int = 30
    read_request_limit: int = 180
    job_timeout_seconds: float = 90.0

    def __post_init__(self) -> None:
        if self.workers != 2 or not 1 <= self.max_pending <= 32:
            raise ValueError("web workers must be 2 and pending queue bounded in [1,32]")
        if not 1 <= self.max_records <= 128 or not 0 < self.cache_seconds <= 300:
            raise ValueError("invalid web memory/cache bounds")
        if not 1024 <= self.max_cache_bytes <= 256 * 1024 * 1024:
            raise ValueError("cache byte budget must be in [1 KiB,256 MiB]")
        if self.retention_seconds < self.cache_seconds or not 1 <= self.request_limit <= 120:
            raise ValueError("invalid retention or request limit")
        if not 1 <= self.read_request_limit <= 600 or not 1 <= self.job_timeout_seconds <= 120:
            raise ValueError("invalid read limit or job timeout")
        if "*" in self.cors_origins or any(
            not origin.startswith(("http://", "https://")) or origin.endswith("/")
            for origin in self.cors_origins
        ):
            raise ValueError("CORS requires explicit HTTP(S) origins without trailing slash")
        if bool(self.model_bundle) != bool(self.prediction_dataset):
            raise ValueError("configure both MIE_MODEL_BUNDLE and MIE_PREDICTION_DATASET")

    @classmethod
    def from_environment(cls) -> "WebConfig":
        def path(name: str) -> Path | None:
            value = os.environ.get(name, "").strip()
            return Path(value).expanduser().resolve() if value else None

        origins = tuple(
            value.strip()
            for value in os.environ.get(
                "MIE_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
            ).split(",")
            if value.strip()
        )
        return cls(
            replay_snapshot=path("MIE_REPLAY_SNAPSHOT"),
            model_bundle=path("MIE_MODEL_BUNDLE"),
            prediction_dataset=path("MIE_PREDICTION_DATASET"),
            frontend_dist=path("MIE_FRONTEND_DIST"),
            cors_origins=origins,
        )
