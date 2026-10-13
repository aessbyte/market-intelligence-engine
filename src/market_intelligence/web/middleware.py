"""Bound public write request bodies before framework parsing or allocation."""

import asyncio
import time
import uuid

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class BodyLimitMiddleware:
    def __init__(self, app: ASGIApp, limit_bytes: int = 8192) -> None:
        self.app, self.limit_bytes = app, limit_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope["method"] not in ("POST", "PUT", "PATCH")
            or not scope["path"].startswith("/api/")
        ):
            await self.app(scope, receive, send)
            return

        async def reject(code: str, message: str, status: int) -> None:
            response = JSONResponse(
                {
                    "error": {
                        "code": code,
                        "message": message,
                        "request_id": scope.get("state", {}).get("request_id", uuid.uuid4().hex),
                    }
                },
                status_code=status,
            )
            await response(scope, receive, send)

        headers = dict(scope["headers"])
        try:
            declared = int(headers.get(b"content-length", b"0"))
            if declared < 0:
                raise ValueError("negative content length")
        except ValueError:
            await reject("VALIDATION_ERROR", "Content-Length inválido.", 400)
            return
        if declared > self.limit_bytes:
            await reject("PAYLOAD_TOO_LARGE", "Corpo da consulta excede o limite de 8 KiB.", 413)
            return
        chunks: list[bytes] = []
        total = 0
        deadline = time.monotonic() + 15.0
        while True:
            try:
                message = await asyncio.wait_for(
                    receive(), timeout=max(0.001, deadline - time.monotonic())
                )
            except TimeoutError:
                await reject(
                    "REQUEST_TIMEOUT", "Tempo limite de recebimento da consulta atingido.", 408
                )
                return
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            total += len(chunk)
            if total > self.limit_bytes:
                await reject(
                    "PAYLOAD_TOO_LARGE", "Corpo da consulta excede o limite de 8 KiB.", 413
                )
                return
            chunks.append(chunk)
            if not message.get("more_body", False):
                break
        body = b"".join(chunks)
        consumed = False

        async def bounded_receive() -> Message:
            nonlocal consumed
            if not consumed:
                consumed = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        await self.app(scope, bounded_receive, send)
