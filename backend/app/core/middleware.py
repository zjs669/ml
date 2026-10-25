"""请求上下文中间件：注入 request_id、记录耗时、统一访问日志（已脱敏）。"""

from __future__ import annotations

import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.types import ASGIApp

logger = logging.getLogger("app.access")


class RequestContextMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("x-request-id") or f"req_{uuid.uuid4().hex[:16]}"
        request.state.request_id = request_id
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            duration = (time.perf_counter() - started) * 1000
            logger.exception(
                "unhandled error",
                extra={
                    "request_id": request_id,
                    "path": request.url.path,
                    "duration_ms": round(duration, 2),
                },
            )
            raise
        duration = (time.perf_counter() - started) * 1000
        response.headers["x-request-id"] = request_id
        logger.info(
            "request",
            extra={
                "request_id": request_id,
                "user_id": getattr(request.state, "user_id", None),
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": round(duration, 2),
            },
        )
        return response
