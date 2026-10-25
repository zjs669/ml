"""统一错误体系：对外只暴露稳定 code + 可读 message，绝不泄露堆栈/SQL/密钥。"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class AppError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 400,
        details: Any | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details


# ---- 具体错误（集中定义，避免各处拼字符串）----
class NotFound(AppError):
    def __init__(self, code: str = "NOT_FOUND", message: str = "资源不存在或无权访问") -> None:
        super().__init__(code, message, status_code=404)


class Unauthorized(AppError):
    def __init__(self, message: str = "登录状态无效，请重新登录") -> None:
        super().__init__("UNAUTHORIZED", message, status_code=401)


class Forbidden(AppError):
    def __init__(self, message: str = "无权执行该操作") -> None:
        super().__init__("FORBIDDEN", message, status_code=403)


class Conflict(AppError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(code, message, status_code=409)


class QuotaExceeded(AppError):
    def __init__(self, message: str = "当前额度不足，请稍后再试或查看套餐") -> None:
        super().__init__("QUOTA_EXCEEDED", message, status_code=402)


class UpstreamError(AppError):
    def __init__(self, message: str = "解读服务暂时不可用，请稍后重试") -> None:
        super().__init__("UPSTREAM_UNAVAILABLE", message, status_code=503)


def _payload(request: Request, code: str, message: str, details: Any | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {
        "error": {
            "code": code,
            "message": message,
            "request_id": getattr(request.state, "request_id", None),
        }
    }
    if details is not None:
        body["error"]["details"] = details
    return body


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_payload(request, exc.code, exc.message, exc.details),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            {"loc": ".".join(str(part) for part in err.get("loc", [])), "msg": err.get("msg", "")}
            for err in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content=_payload(request, "INVALID_REQUEST", "请求参数不合法", details),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_payload(request, f"HTTP_{exc.status_code}", str(exc.detail)),
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:  # pragma: no cover
        return JSONResponse(
            status_code=500,
            content=_payload(request, "INTERNAL_ERROR", "服务内部错误，请稍后重试"),
        )
