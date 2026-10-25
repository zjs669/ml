"""数据库会话与引擎。同步 SQLAlchemy 2.0（见计划 D7）。"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timezone

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings


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
