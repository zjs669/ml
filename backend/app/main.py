"""应用装配。

启动顺序固定：日志 → 生产配置自检 → 时区库自检 → 中间件 → 错误处理 → 路由。
任何一步失败都直接退出，而不是带病上线。
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.v1 import (
    auth,
    billing,
    charts,
    knowledge,
    me,
    meta,
    reports,
    vision,
)
from app.core.config import settings
from app.core.db import engine
from app.core.errors import install_error_handlers
from app.core import metrics
from app.core.observability import RequestContextMiddleware, configure_logging

logger = logging.getLogger("app.startup")


def _check_timezone() -> None:
    try:
        ZoneInfo("Asia/Shanghai")
    except ZoneInfoNotFoundError as exc:  # pragma: no cover - 缺 tzdata 的环境
        raise RuntimeError(
            "缺少 IANA 时区数据库，请先安装 tzdata（Windows 下不加会直接抛 ZoneInfoNotFoundError）"
        ) from exc


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging("INFO" if not settings.is_production else "WARNING")
    settings.assert_safe_for_production()
    _check_timezone()
    logger.info("应用启动", extra={"env": settings.app_env, "llm_mode": settings.llm_mode})
    yield
    logger.info("应用停止")


app = FastAPI(
    title=f"{settings.app_name} API",
    version="0.1.0",
    description="玄枢国学研习台 · 四柱八字 MVP：确定性排盘 + 带引用的 AI 解读",
    lifespan=lifespan,
    docs_url="/docs" if not settings.is_production else None,
    redoc_url=None,
)

app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["x-request-id", "Content-Disposition"],
)

install_error_handlers(app)

for module in (auth, charts, reports, knowledge, billing, me, meta, vision):
    app.include_router(module.router, prefix=settings.api_prefix)
app.include_router(charts.share_router, prefix=settings.api_prefix)
# 根级路径的辅助 router：分享预览、反馈、问卷题库。它们不在任何前缀下，
# 因此单独注册，而不是硬塞进某个带 prefix 的模块。
app.include_router(me.feedback_router, prefix=settings.api_prefix)
app.include_router(meta.mbti_router, prefix=settings.api_prefix)


def _register_gauges() -> None:
    """注册「取值时才计算」的 gauge。放在启动时注册，避免模块导入期就连数据库。"""

    def _pool_in_use() -> float:
        pool = engine.pool
        # QueuePool 有 checkedout()；NullPool / StaticPool 没有，返回 0 而不是报错
        checkedout = getattr(pool, "checkedout", None)
        return float(checkedout()) if callable(checkedout) else 0.0

    metrics.register_gauge(
        "db_pool_in_use", "数据库连接池当前借出的连接数", _pool_in_use
    )


_register_gauges()


@app.get("/metrics", tags=["meta"], include_in_schema=False)
def prometheus_metrics() -> Response:
    """Prometheus 文本格式指标。

    刻意不挂在 /api/v1 下：运维系统按固定路径抓取，不该随业务前缀变化。
    也刻意不鉴权：指标里只有路由模板与状态码，没有任何用户数据；
    若部署到公网，应在 nginx 层限制来源 IP（见 infra/nginx.conf 的注释）。
    """
    return Response(content=metrics.render(), media_type="text/plain; version=0.0.4; charset=utf-8")


@app.get("/healthz", tags=["meta"])
def healthz() -> dict:
    """健康检查：数据库不可用时返回 degraded，便于容器探针区分。"""
    db_ok = True
    db_error = None
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - 仅在数据库异常时触发
        db_ok = False
        db_error = exc.__class__.__name__
    return {
        "status": "ok" if db_ok else "degraded",
        "database": "ok" if db_ok else f"error:{db_error}",
        "env": settings.app_env,
        "algorithm_version": settings.bazi_algorithm_version,
        "llm_mode": settings.llm_mode,
    }
