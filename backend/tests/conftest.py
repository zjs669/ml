"""测试基座：独立测试库 + 每个用例事务隔离。

测试库名来自 `TEST_DATABASE_URL`（默认 xuanshu_test），不会碰开发库。
建表用 `Base.metadata.create_all`（比跑到最新 alembic 版本更快），
并额外补建 ngram 全文索引，保证检索测试与生产同构。
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core import throttle
from app.core.config import settings
from app.core.db import get_session
from app.core.throttle import reset as reset_ratelimit
from app.main import app
from app.models import Base


def _server_url(url: str) -> str:
    return url.rsplit("/", 1)[0]


@pytest.fixture(scope="session")
def engine():
    url = settings.test_database_url
    server = create_engine(_server_url(url), isolation_level="AUTOCOMMIT")
    with server.connect() as conn:
        conn.execute(text("CREATE DATABASE IF NOT EXISTS xuanshu_test CHARACTER SET utf8mb4"))
    server.dispose()

    test_engine = create_engine(url, pool_pre_ping=True)
    Base.metadata.create_all(test_engine)
    with test_engine.begin() as conn:
        exists = conn.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.statistics "
                "WHERE table_schema = DATABASE() AND index_name = 'ft_chunk_content'"
            )
        ).scalar_one()
        if not exists:
            conn.execute(
                text(
                    "ALTER TABLE knowledge_chunks ADD FULLTEXT INDEX ft_chunk_content (content) "
                    "WITH PARSER ngram"
                )
            )
    yield test_engine
    test_engine.dispose()


@pytest.fixture(autouse=True)
def deterministic_settings(monkeypatch, tmp_path):
    """测试一律跑 mock 模型与 console 邮件。

    否则本地 `backend/.env` 一旦切到真实模型（LLM_MODE=openai_compatible），
    报告类用例会真的发网络请求：既慢又不稳定，还会把 token 消耗掉。
    需要验证真实模型的用例自己 monkeypatch 覆盖这几个值。
    """
    monkeypatch.setattr(settings, "llm_mode", "mock")
    monkeypatch.setattr(settings, "llm_api_key", "")
    monkeypatch.setattr(settings, "llm_daily_total_budget", 500)
    monkeypatch.setattr(settings, "mail_mode", "console")
    monkeypatch.setattr(settings, "mail_outbox_path", str(tmp_path / "mail_outbox.log"))
    # 本地 .env 可能为了跑 smoke 关了限流；单测必须开着，否则限流用例会静默通过
    monkeypatch.setattr(settings, "ratelimit_enabled", True)
    yield


@pytest.fixture
def session(engine) -> Iterator[Session]:
    """每个用例一个事务，结束回滚，用例之间互不污染。"""
    connection = engine.connect()
    transaction = connection.begin()
    factory = sessionmaker(
        bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
    )
    db = factory()
    try:
        yield db
    finally:
        db.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def client(session: Session) -> Iterator[TestClient]:
    def _override() -> Iterator[Session]:
        yield session

    app.dependency_overrides[get_session] = _override
    reset_ratelimit()
    throttle.reset_all()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    throttle.reset_all()


@pytest.fixture
def auth_client(client: TestClient) -> tuple[TestClient, dict[str, str]]:
    """注册一个新用户并返回带 Authorization 头的 client。"""
    import uuid

    email = f"t_{uuid.uuid4().hex[:10]}@example.com"
    response = client.post("/api/v1/auth/register", json={"email": email, "password": "Passw0rd123"})
    assert response.status_code == 201, response.text
    token = response.json()["access_token"]
    return client, {"Authorization": f"Bearer {token}"}


BIRTH = {
    "birth_datetime": "1990-06-15T09:10:00",
    "timezone": "Asia/Shanghai",
    "gender": "female",
    "time_known": True,
    "convention": {},
}


@pytest.fixture
def birth_payload() -> dict:
    return dict(BIRTH)
