"""请求链路可观测性：结构化日志（含脱敏）+ 请求上下文中间件。

两块放一起的原因：它们是同一条链路的两端 —— 中间件负责「记什么」，
formatter 负责「怎么写」。分开维护时，中间件新加一个 `extra` 字段，
要记得同步去改另一个文件里的白名单，否则字段静默丢失。

## 脱敏
日志只写标准输出，不落用户敏感原文：密钥、Authorization、出生时间与日期
都会在 `redact()` 里替换成占位符。

## 中间件
注入 `request_id`、记录耗时、统一访问日志（已脱敏），并关掉 uvicorn 的默认访问日志。
"""

from __future__ import annotations

import json
import logging
import re
import sys
import time
import uuid
from datetime import datetime, timezone

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.types import ASGIApp

from app.core import metrics

_REDACT_PATTERNS = [
    (re.compile(r"(sk-[A-Za-z0-9_\-]{8,})"), "sk-***"),
    (re.compile(r"(?i)(api[_-]?key|authorization|token|password)\"?\s*[:=]\s*\"?([^\s\",}]+)"), r"\1=***"),
    # 出生时间/日期不在日志里原文出现
    (re.compile(r"\b\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?\b"), "<datetime>"),
    (re.compile(r"\b\d{4}-\d{2}-\d{2}\b"), "<date>"),
]


def redact(text: str) -> str:
    for pattern, repl in _REDACT_PATTERNS:
        text = pattern.sub(repl, text)
    return text


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": redact(record.getMessage()),
        }
        for key in ("request_id", "user_id", "path", "status", "duration_ms"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        if record.exc_info:
            payload["exc"] = redact(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    # 关掉 uvicorn 默认访问日志，由中间件统一输出
    logging.getLogger("uvicorn.access").disabled = True


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
        # 按「路由模板」打标签而不是实际路径：/charts/123 归到 /charts/{chart_id}，
        # 否则每个 id 都是一个新时间序列，指标内存会随用户增长一直涨。
        route = request.scope.get("route")
        route_path = getattr(route, "path", None) or "<unmatched>"
        metrics.inc(
            "http_requests_total",
            {"route": route_path, "method": request.method, "status": str(response.status_code)},
        )
        metrics.observe("http_request_duration_seconds", duration / 1000, {"route": route_path})
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
