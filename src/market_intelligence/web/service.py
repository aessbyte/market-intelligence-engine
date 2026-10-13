"""Bounded background jobs, explicit sources and immutable analytical results."""

from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from contextvars import ContextVar
from copy import deepcopy
from dataclasses import dataclass
import hashlib
from importlib.resources import files
import json
import logging
from pathlib import Path
import threading
import time
from typing import Any, Callable
import uuid

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]

from ..binance import BinanceClient, PublicHTTP, normalize_symbol
from ..engine import analyze, canonical_json
from ..models import Interval, MarketError
from ..prediction.contracts import DAY_MS
from ..prediction.dataset import create_dataset, restrict_dataset, validate_dataset
from ..prediction.training import validate_bundle
from .adapter import compact_analysis, model_quality
from .config import WebConfig
from .contracts import AnalysisRequest

LOGGER = logging.getLogger("market_intelligence.web")
_DEADLINE: ContextVar[float | None] = ContextVar("mie_web_deadline", default=None)


def log_event(event: str, **fields: Any) -> None:
    LOGGER.info(json.dumps({"event": event, **fields}, sort_keys=True, allow_nan=False))


class ServiceError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code, self.message, self.status_code = code, message, status_code


class BudgetHTTP:
    """Reuse the public allowlisted transport, bounding each upstream GET by the job budget."""

    base_url = "https://data-api.binance.vision"

    def get(self, path: str, params: dict[str, str | int]) -> Any:
        remaining = 8.0
        deadline = _DEADLINE.get()
        if deadline is not None:
            remaining = min(remaining, deadline - time.monotonic())
        if remaining <= 0:
            raise MarketError("analysis upstream timeout budget exhausted")
        return PublicHTTP(self.base_url, timeout=remaining, retries=0).get(path, params)


def read_json(path: Path) -> dict[str, Any]:
    if path.stat().st_size > 25 * 1024 * 1024:
        raise ValueError("configured JSON artifact exceeds 25 MiB limit")
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError("configured artifact must be a JSON object")
    return value


@dataclass
class Job:
    id: str
    created: float
    request_id: str
    status: str = "queued"
    stage: str = "validating"
    result_id: str | None = None
    error: dict[str, str] | None = None

    def response(self) -> dict[str, Any]:
        return {
            "job_id": self.id,
            "status": self.status,
            "stage": self.stage,
            "result_id": self.result_id,
            "error": self.error,
        }


@dataclass
class Record:
    created: float
    cache_until: float
    engine_json: str
    compact_json: str
    last_access: float
    retained_bytes: int
    cache_hit: bool = False


class AnalysisService:
    def __init__(
        self,
        config: WebConfig | None = None,
        client: BinanceClient | None = None,
        clock: Callable[[], float] = time.monotonic,
        wall_clock: Callable[[], float] = time.time,
    ) -> None:
        self.config = config or WebConfig.from_environment()
        self.client = client or BinanceClient(BudgetHTTP())
        self.clock, self.wall_clock = clock, wall_clock
        self.mode = "replay" if self.config.replay_snapshot else "live"
        self.replay = (
            read_json(self.config.replay_snapshot) if self.config.replay_snapshot else None
        )
        self.bundle = read_json(self.config.model_bundle) if self.config.model_bundle else None
        self.dataset = (
            read_json(self.config.prediction_dataset) if self.config.prediction_dataset else None
        )
        if self.bundle is not None:
            validate_bundle(self.bundle)
        if self.dataset is not None:
            validate_dataset(self.dataset)
        self._signature = hashlib.sha256(
            canonical_json(
                {
                    "mode": self.mode,
                    "bundle": self.bundle.get("bundle_sha256") if self.bundle else None,
                    "dataset": self.dataset.get("dataset_sha256") if self.dataset else None,
                    "replay": self.replay,
                }
            ).encode()
        ).hexdigest()
        self.validator = Draft202012Validator(
            json.loads(files("market_intelligence").joinpath("result-v3.schema.json").read_text())
        )
        self._lock = threading.RLock()
        self._history_lock = threading.Lock()
        self._slots = threading.BoundedSemaphore(self.config.workers + self.config.max_pending)
        self._executor = ThreadPoolExecutor(
            max_workers=self.config.workers, thread_name_prefix="mie-analysis"
        )
        self._jobs: dict[str, Job] = {}
        self._records: dict[str, Record] = {}
        self._cache: dict[str, str] = {}
        self._requests: dict[str, deque[float]] = defaultdict(deque)
        self._directory: tuple[float, list[dict[str, Any]]] | None = None
        self._historical: tuple[int, dict[str, Any]] | None = None
        self._closed = False

    def shutdown(self) -> None:
        with self._lock:
            self._closed = True
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _cleanup(self) -> None:
        now = self.clock()
        for job_id in list(self._jobs):
            job = self._jobs[job_id]
            if (
                job.status in ("completed", "failed")
                and now - job.created > self.config.retention_seconds
            ):
                del self._jobs[job_id]
        for result_id in list(self._records):
            if now - self._records[result_id].created > self.config.retention_seconds:
                del self._records[result_id]
        for key in list(self._cache):
            record = self._records.get(self._cache[key])
            if record is None or record.cache_until <= now:
                del self._cache[key]
        for ip in list(self._requests):
            if not self._requests[ip] or self._requests[ip][-1] <= now - 60:
                del self._requests[ip]

    def rate_limit(self, key: str, limit: int | None = None) -> None:
        with self._lock:
            self._cleanup()
            requests = self._requests[key]
            now = self.clock()
            while requests and requests[0] <= now - 60:
                requests.popleft()
            if len(requests) >= (limit or self.config.request_limit):
                raise ServiceError(
                    "RATE_LIMITED", "Limite temporário de consultas. Tente em um minuto.", 429
                )
            if len(self._requests) > 4096:
                raise ServiceError("SERVICE_BUSY", "Limite de clientes ativos atingido.", 503)
            requests.append(now)

    def symbols(self, query: str = "", exact: str | None = None) -> dict[str, Any]:
        if exact is not None:
            exact = normalize_symbol(exact)
        if self.replay is not None:
            items = [self.replay["symbol_info"]]
        else:
            with self._lock:
                directory = self._directory
            if directory is None or self.clock() - directory[0] >= 300:
                payload = self.client.transport.get("/api/v3/exchangeInfo", {})
                if not isinstance(payload, dict) or not isinstance(payload.get("symbols"), list):
                    raise ServiceError("SOURCE_UNAVAILABLE", "Resposta inválida da Binance.", 502)
                items = [
                    item
                    for item in payload["symbols"]
                    if isinstance(item, dict)
                    and item.get("status") == "TRADING"
                    and item.get("isSpotTradingAllowed") is True
                    and isinstance(item.get("symbol"), str)
                ]
                with self._lock:
                    self._directory = self.clock(), items
            else:
                items = directory[1]
        query = query.strip().upper()
        filtered = [
            item
            for item in items
            if (exact is None or item["symbol"] == exact) and (not query or query in item["symbol"])
        ]
        return {
            "exchange": "binance",
            "mode": self.mode,
            "symbols": [
                {
                    "symbol": item["symbol"],
                    "base_asset": item.get("baseAsset")
                    if isinstance(item.get("baseAsset"), str)
                    else None,
                    "quote_asset": item.get("quoteAsset")
                    if isinstance(item.get("quoteAsset"), str)
                    else None,
                    "markets": ["spot"],
                }
                for item in sorted(filtered, key=lambda item: item["symbol"])[:100]
            ],
            "supported_markets": ["spot"],
            "futures_checked": False,
        }

    def symbol_validation(self, symbol: str) -> dict[str, Any]:
        symbol = normalize_symbol(symbol)
        available = bool(self.symbols(exact=symbol)["symbols"])
        return {
            "symbol": symbol,
            "exchange": "binance",
            "mode": self.mode,
            "valid": available,
            "supported_markets": ["spot"] if available else [],
            "markets": [
                {
                    "market": "spot",
                    "available": available,
                    "supported": True,
                    "status": "TRADING" if available else "UNAVAILABLE",
                    "reason": None
                    if available
                    else "Símbolo indisponível no mercado spot consultado.",
                },
                {
                    "market": "futures",
                    "available": None,
                    "supported": False,
                    "status": "NOT_CHECKED",
                    "reason": "Motor auditado suporta somente spot; disponibilidade de futuros não consultada.",
                },
            ],
        }

    def submit(self, request: AnalysisRequest, request_id: str, client_key: str) -> dict[str, Any]:
        if request.market != "spot":
            raise ServiceError(
                "MARKET_UNSUPPORTED",
                "O motor disponível analisa Binance spot. Futuros ainda não são suportados.",
                422,
            )
        self.rate_limit("analysis:" + client_key)
        key = self._signature + ":" + request.symbol + ":" + str(request.bars)
        with self._lock:
            self._cleanup()
            if self._closed:
                raise ServiceError("SERVICE_UNAVAILABLE", "Serviço encerrando.", 503)
            if len(self._jobs) >= self.config.max_records:
                finished = [
                    key
                    for key, existing in self._jobs.items()
                    if existing.status in ("completed", "failed")
                ]
                if not finished:
                    raise ServiceError(
                        "SERVICE_BUSY", "Capacidade temporária de análises atingida.", 503
                    )
                del self._jobs[min(finished, key=lambda key: self._jobs[key].created)]
            job = Job(uuid.uuid4().hex, self.clock(), request_id)
            cached = self._records.get(self._cache.get(key, ""))
            if cached is not None and cached.cache_until > self.clock():
                job.status, job.stage = "completed", "completed"
                job.result_id = self._cache[key]
                cached.cache_hit = True
                self._jobs[job.id] = job
                return job.response()
            if not self._slots.acquire(blocking=False):
                raise ServiceError(
                    "SERVICE_BUSY",
                    "Fila de processamento cheia. Tente novamente em instantes.",
                    503,
                )
            self._jobs[job.id] = job
            self._executor.submit(self._run, job.id, request, key)
            return job.response()

    def job(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            self._cleanup()
            if job_id not in self._jobs:
                raise ServiceError("JOB_NOT_FOUND", "Análise inexistente ou expirada.", 404)
            return self._jobs[job_id].response()

    def result(self, result_id: str, full: bool = False) -> dict[str, Any]:
        with self._lock:
            self._cleanup()
            record = self._records.get(result_id)
            if record is None:
                raise ServiceError("ANALYSIS_NOT_FOUND", "Resultado inexistente ou expirado.", 404)
            record.last_access = self.clock()
            payload: dict[str, Any] = json.loads(
                record.engine_json if full else record.compact_json
            )
            if not full:
                payload["cache"]["hit"] = record.cache_hit
            return payload

    def _stage(self, job_id: str, stage: str) -> None:
        with self._lock:
            self._jobs[job_id].status = "running"
            self._jobs[job_id].stage = stage
        log_event("analysis_stage", job_id=job_id, stage=stage)
        deadline = _DEADLINE.get()
        if deadline is not None and time.monotonic() >= deadline:
            raise ServiceError("SOURCE_TIMEOUT", "Tempo limite da análise atingido.", 504)

    def _prediction_history(self, snapshot: dict[str, Any]) -> dict[str, Any] | None:
        if (
            self.bundle is None
            or self.dataset is None
            or snapshot["symbol"] != self.bundle["dataset"]["symbol"]
        ):
            return None
        if self.mode == "replay":
            return self.dataset
        cutoff = snapshot["as_of_ms"]
        origin = cutoff // DAY_MS * DAY_MS
        if self.dataset["last_closed_available_ms"] == origin:
            return self.dataset
        with self._history_lock:
            if self._historical is not None and self._historical[0] == origin:
                return self._historical[1]
            raw = create_dataset(
                self.client.klines(snapshot["symbol"], Interval.D1, cutoff, 5000),
                snapshot["symbol"],
                cutoff,
                snapshot["server_time_ms"],
                5000,
                snapshot["endpoint"],
                snapshot["symbol_info"],
                snapshot["source"],
            )
            selected = restrict_dataset(
                raw,
                self.bundle["dataset"]["first_observed_open_ms"],
                "Web inference: retain explicitly configured model cohort start; preserve original training history and append only later observed candles.",
            )
            # The unchanged engine additionally checks the frozen input history checksum.
            self._historical = origin, selected
            return selected

    def _run(self, job_id: str, request: AnalysisRequest, cache_key: str) -> None:
        token = _DEADLINE.set(time.monotonic() + self.config.job_timeout_seconds)
        started = self.clock()
        try:
            self._stage(job_id, "validating")
            if self.replay is not None and request.symbol != self.replay.get("symbol"):
                raise ServiceError(
                    "SYMBOL_UNAVAILABLE",
                    "Símbolo não disponível no replay explicitamente configurado.",
                    404,
                )
            self._stage(job_id, "fetching")
            snapshot = (
                deepcopy(self.replay)
                if self.replay is not None
                else self.client.snapshot(request.symbol, request.bars)
            )
            if snapshot.get("fetch_errors") and not any(snapshot.get("klines", {}).values()):
                raise ServiceError(
                    "SOURCE_UNAVAILABLE",
                    "A fonte pública Binance não disponibilizou nenhum dos intervalos solicitados.",
                    502,
                )
            warnings = []
            if self.mode == "replay":
                warnings.append(
                    "Replay explícito de captura histórica; esta consulta não representa cotação ao vivo."
                )
                if request.bars != snapshot["requested_bars"]:
                    warnings.append(
                        "Replay preserva a janela original da captura, sem redimensionar dados históricos."
                    )
            if snapshot.get("source") == "simulated":
                warnings.append(
                    "DADOS SIMULADOS: fixture de teste, sem observações reais da Binance."
                )
            bundle = (
                self.bundle
                if self.bundle and self.bundle["dataset"]["symbol"] == request.symbol
                else None
            )
            dataset = None
            try:
                dataset = self._prediction_history(snapshot)
            except (MarketError, ValueError, TypeError, KeyError) as exc:
                warnings.append("Histórico preditivo indisponível: " + str(exc))
            self._stage(job_id, "analyzing")
            result = json.loads(
                canonical_json(
                    analyze(
                        snapshot,
                        result_version=3,
                        prediction_bundle=bundle,
                        prediction_dataset=dataset,
                    )
                )
            )
            self.validator.validate(result)
            self._stage(job_id, "preparing")
            result_id = hashlib.sha256(
                (self.mode + ":" + canonical_json(result)).encode()
            ).hexdigest()[:24]
            expires_at_ms = int((self.wall_clock() + self.config.cache_seconds) * 1000)
            compact = compact_analysis(
                result_id,
                snapshot,
                result,
                self.mode,
                model_quality(bundle, request.symbol),
                expires_at_ms,
                warnings,
            )
            engine_json, compact_json = canonical_json(result), canonical_json(compact)
            retained_bytes = len(engine_json.encode()) + len(compact_json.encode())
            if retained_bytes > self.config.max_cache_bytes:
                raise ServiceError(
                    "SERVICE_BUSY",
                    "Resultado excede o orçamento de memória configurado do serviço.",
                    503,
                )
            self._stage(job_id, "preparing")
            with self._lock:
                self._cleanup()
                if result_id in self._records:
                    del self._records[result_id]
                while self._records and (
                    len(self._records) >= self.config.max_records
                    or sum(record.retained_bytes for record in self._records.values())
                    + retained_bytes
                    > self.config.max_cache_bytes
                ):
                    oldest = min(self._records, key=lambda key: self._records[key].last_access)
                    del self._records[oldest]
                self._records[result_id] = Record(
                    self.clock(),
                    self.clock() + self.config.cache_seconds,
                    engine_json,
                    compact_json,
                    self.clock(),
                    retained_bytes,
                )
                self._cache[cache_key] = result_id
                job = self._jobs[job_id]
                job.status, job.stage, job.result_id = "completed", "completed", result_id
            log_event(
                "analysis_completed",
                job_id=job_id,
                result_id=result_id,
                source=snapshot["source"],
                mode=self.mode,
                duration_ms=int((self.clock() - started) * 1000),
            )
        except ServiceError as exc:
            self._failure(job_id, exc.code, exc.message)
        except MarketError as exc:
            message = str(exc)
            code = (
                "SYMBOL_UNAVAILABLE"
                if "unavailable or not TRADING" in message
                or "not enabled for spot" in message
                or "HTTP 400 at /api/v3/exchangeInfo" in message
                else "SOURCE_UNAVAILABLE"
            )
            prefix = (
                "Símbolo indisponível no mercado spot da Binance: "
                if code == "SYMBOL_UNAVAILABLE"
                else "A fonte pública Binance está indisponível: "
            )
            self._failure(job_id, code, prefix + message)
        except Exception as exc:
            log_event("analysis_internal_failure", job_id=job_id, error_type=type(exc).__name__)
            self._failure(
                job_id,
                "ANALYSIS_FAILED",
                "Não foi possível produzir uma análise íntegra. Consulte os logs do serviço.",
            )
        finally:
            _DEADLINE.reset(token)
            self._slots.release()

    def _failure(self, job_id: str, code: str, message: str) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.status, job.stage = "failed", "failed"
            job.error = {"code": code, "message": message, "request_id": job.request_id}
        log_event("analysis_failed", job_id=job_id, code=code)
