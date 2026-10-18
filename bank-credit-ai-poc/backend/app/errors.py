"""Standard error envelope for /api/v1. Legacy routes keep FastAPI's default {"detail": ...} shape."""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.correlation import current_correlation_id

logger = logging.getLogger(__name__)

_CODES = {400: "bad_request", 401: "unauthenticated", 403: "forbidden", 404: "not_found", 409: "conflict", 422: "validation_error", 429: "rate_limited"}


def _is_v1(request: Request) -> bool:
    return request.url.path.startswith("/api/v1/")


def _envelope(status: int, message: str, details=None, headers=None) -> JSONResponse:
    body = {"error": {"code": _CODES.get(status, "error"), "message": message, "correlation_id": current_correlation_id(), "details": details}}
    return JSONResponse(status_code=status, content=jsonable_encoder(body), headers=headers)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException):
        if not _is_v1(request):
            return await http_exception_handler(request, exc)
        return _envelope(exc.status_code, str(exc.detail), headers=getattr(exc, "headers", None))

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        if not _is_v1(request):
            return await request_validation_exception_handler(request, exc)
        return _envelope(422, "Request validation failed", details=exc.errors())

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, exc: Exception):
        logger.exception("Unhandled error correlation_id=%s", current_correlation_id())
        # No exception text in the response: it can contain SQL, prompts or customer data.
        return _envelope(500, "Internal error")
