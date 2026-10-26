"""数据库引擎、会话与声明式基类。同步 SQLAlchemy 2.0（见计划 D7）。

`Base` 放在这里而不是 `models/base.py`：它只有 8 行，却是 9 个模型文件的
共同依赖。单独一个文件时，每个模型都要多一行 import，而它本身没有任何
独立语义（就是个 `DeclarativeBase` 子类），跟着引擎走更自然。
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timezone

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    """全局声明式基类。所有表通过 Alembic 迁移创建，禁止启动时 create_all。"""

    pass


def utcnow() -> datetime:
    """统一返回 naive UTC，MySQL DATETIME 列不存时区。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _build_engine(url: str):
    engine = create_engine(
        url,
        pool_pre_ping=True,
        pool_recycle=1800,
        pool_size=5,
        max_overflow=10,
        future=True,
    )

    @event.listens_for(engine, "connect")
    def _set_session_sql_mode(dbapi_connection, _record):  # pragma: no cover - 驱动细节
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("SET SESSION sql_mode='STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION'")
        finally:
            cursor.close()

    return engine


engine = _build_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """FastAPI 依赖：请求级会话，异常时回滚。"""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
