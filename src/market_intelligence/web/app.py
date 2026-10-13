"""Versioned ASGI API. Public requests never train models or execute orders."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
import time
from typing import Any, Literal
import uuid

from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from starlette.exceptions import HTTPException

from .. import __version__
from ..models import MarketError
from .config import WebConfig
from .contracts import (
    AnalysisRequest,
    CompactAnalysis,
    ErrorEnvelope,
    JobResponse,
    Projection,
    SymbolsResponse,
    SymbolValidation,
)
from .service import AnalysisService, ServiceError, log_event
from .middleware import BodyLimitMiddleware


def create_app(service: AnalysisService | None = None, config: WebConfig | None = None) -> FastAPI:
    active = service or AnalysisService(config)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        active.shutdown()

    app = FastAPI(
        title="Market Intelligence Engine API",
        version="1.0.0",
        description="Public Binance spot analytical engine; conditional scenarios and explicitly gated statistical forecasts.",
        lifespan=lifespan,
        responses={
            400: {"model": ErrorEnvelope},
            404: {"model": ErrorEnvelope},
            422: {"model": ErrorEnvelope},
            429: {"model": ErrorEnvelope},
            502: {"model": ErrorEnvelope},
            503: {"model": ErrorEnvelope},
        },
    )
    app.state.service = active
    app.add_middleware(BodyLimitMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(active.config.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type"],
        expose_headers=["X-Request-ID"],
    )
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    def error(request: Request, code: str, message: str, status_code: int) -> JSONResponse:
        body = ErrorEnvelope.model_validate(
            {
                "error": {
                    "code": code,
                    "message": message,
                    "request_id": getattr(request.state, "request_id", uuid.uuid4().hex),
                }
            }
        ).model_dump(mode="json")
        return JSONResponse(body, status_code=status_code)

    @app.middleware("http")
    async def requests(request: Request, call_next: Any) -> Response:
        request.state.request_id = uuid.uuid4().hex
        started = time.monotonic()
        try:
            if request.url.path.startswith("/api/") and request.method != "OPTIONS":
                host = request.client.host if request.client else "unknown"
                active.rate_limit("read:" + host, active.config.read_request_limit)
            response: Response = await call_next(request)
        except ServiceError as exc:
            response = error(request, exc.code, exc.message, exc.status_code)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["X-Frame-Options"] = "DENY"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        log_event(
            "http_request",
            request_id=request.state.request_id,
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=int((time.monotonic() - started) * 1000),
        )
        return response

    @app.exception_handler(ServiceError)
    async def service_error(request: Request, exc: ServiceError) -> JSONResponse:
        return error(request, exc.code, exc.message, exc.status_code)

    @app.exception_handler(MarketError)
    async def source_error(request: Request, exc: MarketError) -> JSONResponse:
        code = "VALIDATION_ERROR" if "Symbol must" in str(exc) else "SOURCE_UNAVAILABLE"
        return error(request, code, str(exc), 422 if code == "VALIDATION_ERROR" else 502)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        message = "; ".join(
            ".".join(str(value) for value in entry["loc"]) + ": " + entry["msg"]
            for entry in exc.errors()
        )
        return error(request, "VALIDATION_ERROR", message, 422)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        return error(
            request,
            "NOT_FOUND" if exc.status_code == 404 else "HTTP_ERROR",
            str(exc.detail),
            exc.status_code,
        )

    @app.exception_handler(Exception)
    async def internal_error(request: Request, exc: Exception) -> JSONResponse:
        log_event(
            "http_internal_failure",
            request_id=request.state.request_id,
            error_type=type(exc).__name__,
        )
        return error(request, "INTERNAL_ERROR", "Falha interna do serviço.", 500)

    @app.get("/api/v1/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "api_version": "1",
            "engine_version": __version__,
            "mode": active.mode,
            "replay_as_of_ms": active.replay.get("as_of_ms") if active.replay is not None else None,
            "supported_markets": ["spot"],
            "supported_timeframes": ["H1", "H4", "D1"],
            "models_configured": active.bundle is not None,
            "training_available": False,
        }

    @app.get("/api/v1/symbols", response_model=SymbolsResponse)
    def symbols(
        request: Request,
        q: str = Query(default="", max_length=30, pattern="^[A-Za-z0-9]*$"),
        exact: str | None = Query(default=None, min_length=5, max_length=30),
    ) -> dict[str, Any]:
        active.rate_limit("discovery:" + (request.client.host if request.client else "unknown"))
        return active.symbols(q, exact)

    @app.get("/api/v1/symbol-validation/{symbol}", response_model=SymbolValidation)
    @app.get("/api/v1/symbols/{symbol}", response_model=SymbolValidation)
    def symbol_validation(symbol: str, request: Request) -> dict[str, Any]:
        active.rate_limit("discovery:" + (request.client.host if request.client else "unknown"))
        return active.symbol_validation(symbol)

    @app.post("/api/v1/analyses", response_model=JobResponse, status_code=202)
    def submit(payload: AnalysisRequest, request: Request) -> dict[str, Any]:
        return active.submit(
            payload, request.state.request_id, request.client.host if request.client else "unknown"
        )

    @app.get("/api/v1/jobs/{job_id}", response_model=JobResponse)
    def job(job_id: str) -> dict[str, Any]:
        return active.job(job_id)

    @app.get("/api/v1/analyses/{analysis_id}", response_model=CompactAnalysis)
    def analysis(analysis_id: str) -> dict[str, Any]:
        return active.result(analysis_id)

    @app.get("/api/v1/analyses/{analysis_id}/engine")
    def engine(analysis_id: str) -> dict[str, Any]:
        """Unchanged analytical v3 JSON, including complete append-only event journals."""
        return active.result(analysis_id, full=True)

    @app.get("/api/v1/analyses/{analysis_id}/ohlcv", response_model=Projection)
    def ohlcv(analysis_id: str, interval: Literal["H1", "H4", "D1", "W1"] = "H1") -> dict[str, Any]:
        if interval == "W1":
            raise ServiceError(
                "TIMEFRAME_UNAVAILABLE", "W1 não está disponível no motor atual.", 422
            )
        result = active.result(analysis_id)
        return {
            "analysis_id": analysis_id,
            "as_of_ms": result["analysis"]["as_of_ms"],
            "data": result["charts"][interval],
        }

    @app.get("/api/v1/analyses/{analysis_id}/{section}", response_model=Projection)
    def projection(
        analysis_id: str,
        section: Literal[
            "indicators",
            "diagnostic",
            "structure",
            "wyckoff",
            "scenarios",
            "predictions",
            "model-quality",
        ],
    ) -> dict[str, Any]:
        result = active.result(analysis_id)
        analytical = result["analysis"]
        if section in ("indicators", "structure", "wyckoff"):
            data = {name: frame.get(section) for name, frame in analytical["timeframes"].items()}
        elif section == "diagnostic":
            data = {
                key: analytical[key]
                for key in ("regime", "evidence", "multitimeframe", "limitations", "status")
            }
        elif section == "model-quality":
            data = result["model_quality"]
        else:
            data = analytical[section]
        return {"analysis_id": analysis_id, "as_of_ms": analytical["as_of_ms"], "data": data}

    if active.config.frontend_dist is not None:
        frontend_root = active.config.frontend_dist.resolve()
        if not frontend_root.joinpath("index.html").is_file():
            raise ValueError("MIE_FRONTEND_DIST must contain a built index.html")

        @app.get("/{asset_path:path}", include_in_schema=False)
        def frontend(asset_path: str) -> FileResponse:
            if asset_path == "api" or asset_path.startswith("api/"):
                raise ServiceError("NOT_FOUND", "Endpoint de API inexistente.", 404)
            target: Path = frontend_root.joinpath(asset_path).resolve()
            if not target.is_relative_to(frontend_root):
                raise ServiceError("NOT_FOUND", "Arquivo inexistente.", 404)
            return FileResponse(target if target.is_file() else frontend_root / "index.html")

    return app
